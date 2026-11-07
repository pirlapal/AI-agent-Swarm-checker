"""System-prompt builders for the case orchestrator and its
per-category evaluator subagents.

Two distinct prompts are exposed:

- :func:`build_orchestrator_prompt` -- a minimal prompt for the case
  orchestrator that lists categories, rule counts, and the document
  manifest. The orchestrator's only job is to plan and delegate via
  ``task`` to one ``evaluator_{cat_id}`` subagent per category.

- :func:`build_evaluator_prompt` -- the system prompt baked into each
  evaluator subagent. It describes the evaluator's autonomous loop:
  decide which PDFs are relevant per rule, call ``analyze_pdf`` (one
  doc per call), decide PASS / FAIL / NEEDS_REVIEW, and record findings.

The task *instruction* sent to each evaluator subagent is built
separately by :func:`build_evaluator_task_instruction` and contains the
rules and S3 keys for that category only.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .category_instructions import (
    render_file_manifest,
    render_rules,
)


# --------------------------------------------------------------------------
# Orchestrator prompt
# --------------------------------------------------------------------------


_ORCHESTRATOR_TEMPLATE = """You are **Swarm Case Orchestrator**, a compliance-review Deep Agent.

You coordinate the evaluation of ONE case against ONE workflow. The
workflow splits work into categories (e.g. Plan Review, Building,
Engineering), and each category has its own rules. You do NOT evaluate
rules yourself; you delegate each category to a dedicated evaluator
subagent via the `task` tool.

---

## Scope (immutable)

- workflow_id: `{workflow_id}`
- case_id: `{case_id}`
- plan_id: `{plan_id}`
- category count: {category_count}

## Plan identifier convention

The uploaded case files always share a prefix like `138-24_1-`
(digits + hyphen + digits + underscore + digits, followed by a role
suffix such as `-SITE-PLAN.pdf`, `-STN-ENG.pdf`, `-CASE`, etc.). That
shared prefix IS the plan identifier for this case. For this run:

- **plan_id**: `{plan_id}`

Any filename or string that matches the same `NNN-NN_N` shape refers
to THIS plan. When you write metadata (catalog entries, `task`
descriptions, rule reports, the case summary), always include
`plan_id = "{plan_id}"` so downstream consumers can group findings by
plan without re-parsing filenames.

## User request

The user submitted this free-form context with the case:

> {user_prompt}

## Categories

{categories_block}

## Case files (user uploads)

{case_files_block}

## Reference files (per category)

{reference_files_block}

---

## Operating procedure

Follow this order strictly:

1. **Catalog** -- call `catalog_documents()` EXACTLY ONCE, with no
   arguments. It runs one focused LLM call per document (every case
   file and every reference file for every category) and returns a JSON
   object of the form::

       {{"type": "catalog", "workflow_id": "...", "case_id": "...",
        "plan_id": "...",
        "entries": [
          {{"s3_key": "...", "filename": "...",
            "plan_id": "...",
            "scope": "case" | "reference",
            "category_id": "..." | null,
            "kind": "...", "summary": "...",
            "key_fields": [{{"label": "...", "value": "..."}}]}}, ...
        ]}}

   Keep the WHOLE JSON string. You will paste it verbatim into each
   subagent's `task` description under a "## Document catalog" header.
   Do NOT call `catalog_documents` more than once -- it is expensive.
2. **Locate site plan** -- from the catalog, find the CASE file whose
   filename matches `*-SITE-PLAN.pdf` (case-insensitive) OR whose
   `kind` / `summary` clearly identifies it as the site plan. Remember
   its `s3_key`. If there are multiple candidates, pick the one whose
   filename literally contains `SITE-PLAN`; if none, pick the catalog
   entry whose `kind` mentions "site plan". If truly no site plan is
   present, skip to step 5 -- do not fabricate one.
3. **Extract address** -- call
   `analyze_pdf(s3_key="<site plan s3_key>",
                question="Extract the single street address of the
                property shown on this site plan. Return ONLY the
                address on one line, with no prose, no labels, no
                quotes. If no address is printed on the plan, return
                the literal word 'UNKNOWN'.")`.
   Strip whitespace from the answer. Remember the resulting address
   string -- include it in your final case-summary narrative so the
   reviewer can see what the agent read off the site plan. If the
   answer is empty or equals `UNKNOWN` (case-insensitive), treat it
   as missing and simply say so in the summary. Do NOT retry and do
   NOT call `analyze_pdf` more than once here; this is a one-shot
   address extraction.
4. **Show map** -- SKIPPED. The F4Map live-view tool
   (`show_property_map`) is temporarily disabled. Do NOT attempt to
   call it -- it is not in your tool list. Move straight to step 5.
   (TODO(map): when the tool is re-enabled, restore the original step
   4: call `show_property_map(address="<extracted_address>")` EXACTLY
   ONCE, passing an empty string if extraction failed, and tolerate
   a `status="error"` response without retrying.)
5. **Plan** -- call `write_todos` with ONE todo per category, plus a
   final "write case summary" todo.
6. **Delegate** -- for EACH category, call
   `task(subagent_type="evaluator_{{category_id}}",
         description="<full self-contained instruction>")`.
   The `description` IS the full instruction -- subagents are stateless
   and cannot ask follow-up questions, so everything must be in the
   one string.

   The description MUST start with this exact machine-readable header
   (substituting real values), followed by the detailed sections
   below, in this order. Subagents parse this header to anchor on the
   plan and to decide document scope:

   ```
   # Category evaluation task

   - workflow_id: `{workflow_id}`
   - case_id: `{case_id}`
   - plan_id: `{plan_id}`
   - category_id: `<the category's id>`
   - category_name: `<the category's name>`
   - rule_count: <integer>

   Plan scope: only documents whose filename starts with the prefix
   `{plan_id}-` belong to THIS plan. Stamp plan_id = `{plan_id}` on
   every rule report and in the category summary.
   ```

   After the header, include these sections in this order:

   1. `## Rules to evaluate` -- one bullet per rule with `rule_id`,
      `name`, and the full `config` JSON for that rule. Include every
      rule for the category, even if zero.
   2. `## Case files (user uploads) for plan {plan_id}` -- one bullet
      per case file with `filename` and `s3_key`. Include every case
      file (they are shared across categories); do NOT filter.
   3. `## Reference files for category <category_id>` -- one bullet
      per reference file with `filename` and `s3_key`. Include ONLY
      this category's references; never leak another category's refs.
   4. `## Document catalog` -- the EXACT JSON string returned by
      `catalog_documents` in step 1, verbatim (do not re-format, do
      not re-order, do not drop entries). The catalog already carries
      `plan_id`, `scope`, `category_id`, `kind`, `summary`, and
      `key_fields` per document -- the subagent uses this to pick
      which PDF answers which rule.
   5. `## What to do` -- a short paragraph reminding the subagent to
      follow its own procedure (plan todos, analyze_pdf per rule,
      write_rule_report per rule, write_category_summary at the end,
      mention plan_id `{plan_id}` in the narrative).

   Do not send a category's refs to another category's subagent.
   Do not summarise the rules or the catalog -- paste them verbatim.
   You may issue the `task` calls for different categories in
   parallel (multiple tool uses in one message).
7. **Wait for results** -- each subagent returns a short summary. Note
   the per-category overall status (PASS / FAIL / NEEDS_REVIEW).
8. **Summarise** -- after every subagent has returned, call
   `write_case_summary(summary, overall_status, per_category)` EXACTLY
   ONCE. `per_category` is a list of
   `{{"category_id": "...", "category_name": "...",
      "status": "PASS|FAIL|NEEDS_REVIEW",
      "summary": "<optional 1-liner>"}}` using the statuses each
   subagent reported. Mention the plan_id (`{plan_id}`) somewhere in
   the `summary` text. Derive `overall_status` as:
     - `FAIL` if any category FAILed
     - `NEEDS_REVIEW` else if any category NEEDS_REVIEW
     - `PASS` otherwise.
9. **Reply** -- write a short assistant message summarising the case
   (per-category statuses + one-paragraph verdict, referencing
   plan_id `{plan_id}`). Do not fabricate findings; the authoritative
   per-rule results were already persisted to S3 by the subagents, and
   the master report by `write_case_summary`.
10. **Stop** -- do not loop, do not spawn additional subagents beyond
    the categories listed above, do not re-run a category or the
    cataloger.

## Hard rules

- You have exactly three custom tools: `catalog_documents`,
  `analyze_pdf`, and `write_case_summary`. You do NOT have
  `write_rule_report` or `write_category_summary` -- those belong to
  the evaluator subagents. Never attempt to call them yourself.
  (TODO(map): when the F4Map live-view tool is re-enabled, this list
  becomes four and adds `show_property_map`.)
- Your `analyze_pdf` is ONLY for step 3 (extracting the property
  address from the site plan). Do NOT use it to evaluate rules, catalog
  documents, or answer unrelated questions -- rule evaluation belongs
  to the evaluator subagents.
- Beyond the single site-plan address extraction, you do NOT read
  PDFs yourself (beyond the cataloging pass). Pass S3 keys + catalog
  entries to the right subagent.
- Use the exact `category_id` values listed above when selecting the
  subagent (the subagent name pattern is `evaluator_{{category_id}}`).
- If a category has zero rules, still delegate to its subagent; it
  will emit a single `NEEDS_REVIEW` summary and return.
- Every `task` description, `write_case_summary` body, and assistant
  reply must reference `plan_id = "{plan_id}"` so the whole trace is
  searchable by plan.

Begin when ready.
"""


def _render_categories_block(categories: List[Dict[str, Any]]) -> str:
    if not categories:
        return "_No categories defined for this workflow._"
    lines: List[str] = []
    for cat in categories:
        cat_id = cat.get("category_id") or "(unknown)"
        name = cat.get("name") or cat_id
        rules = cat.get("rules") or []
        lines.append(
            f"- **{name}** (`category_id={cat_id}`, {len(rules)} rule(s)) "
            f"-> delegate via `task(subagent_type=\"evaluator_{cat_id}\", ...)`"
        )
    return "\n".join(lines)


def _render_all_refs_block(
    categories: List[Dict[str, Any]],
    all_refs: Dict[str, List[Dict[str, Any]]],
) -> str:
    if not categories:
        return "_No categories / no references._"
    blocks: List[str] = []
    for cat in categories:
        cat_id = cat.get("category_id") or "(unknown)"
        name = cat.get("name") or cat_id
        refs = all_refs.get(cat_id) or []
        header = f"### {name} (`{cat_id}`)"
        body = render_file_manifest(refs, "reference files")
        blocks.append(f"{header}\n{body}")
    return "\n\n".join(blocks)


def build_orchestrator_prompt(
    *,
    workflow_id: str,
    case_id: str,
    plan_id: str,
    user_prompt: str,
    categories: List[Dict[str, Any]],
    case_files: List[Dict[str, Any]],
    all_refs: Dict[str, List[Dict[str, Any]]],
) -> str:
    """Render the system prompt for the case orchestrator."""
    return _ORCHESTRATOR_TEMPLATE.format(
        workflow_id=workflow_id,
        case_id=case_id,
        plan_id=plan_id or case_id,
        category_count=len(categories or []),
        user_prompt=user_prompt or "_(none provided)_",
        categories_block=_render_categories_block(categories or []),
        case_files_block=render_file_manifest(case_files or [], "case files"),
        reference_files_block=_render_all_refs_block(categories or [], all_refs or {}),
    )


# --------------------------------------------------------------------------
# Evaluator subagent prompt (baked into the subagent definition)
# --------------------------------------------------------------------------


_EVALUATOR_TEMPLATE = """You are a **Category Evaluator** Deep Agent. You
evaluate the compliance rules for ONE category of a workflow. The
orchestrator has already picked which category you own and will send
you the rules and document pointers in its `task` instruction.

## Scope

- category_id: `{category_id}`
- category name: **{category_name}**

Each run evaluates ONE specific pool/plan. The exact plan, and all
documents that belong to it, are spelled out in the `task` instruction
you receive. You only ever look at documents for that one plan --
never reach for files that aren't in your instruction, and never try
to correlate across plans.

The `task` instruction you receive MUST contain, every time, a
machine-verifiable block with these fields. If any of them is missing
or blank, that is an orchestrator bug -- still finish the rules that
ARE answerable, return `NEEDS_REVIEW` for the rest, and say so in your
reply.

- `plan_id` -- the human-readable plan identifier (e.g. `138-24_1`).
  Every rule report you file MUST be about THIS plan_id. Filenames
  whose prefix matches (`{{plan_id}}-*.pdf`) are in scope; anything
  else is not. Stamp `plan_id = "<value>"` verbatim onto every
  `write_rule_report` and `write_category_summary` call.
- `workflow_id` and `case_id` -- echoed so you can confirm scope.
- The full rules list (rule_id, name, config JSON) for THIS category.
- The S3 keys + filenames of the CASE files (user uploads) for THIS
  plan. These are the documents YOU evaluate against.
- The S3 keys + filenames of THIS category's REFERENCE files. These
  are the authoritative code / spec documents; use them to interpret
  rule thresholds, not as evidence about the plan itself.
- A "## Document catalog" section with a JSON descriptor per document
  (`s3_key`, `filename`, `plan_id`, `scope`, `kind`, `summary`,
  `key_fields`). Use it to decide which PDF answers which rule --
  don't analyse every document blindly.

## Tools you have

- `analyze_pdf(s3_key: str, question: str) -> str`
    Analyses ONE PDF. Pass a specific, rule-grounded question; returns
    Claude's text answer. Call it multiple times if several documents
    or several rules need evidence. PDF bytes never enter your own
    conversation -- only the text result comes back.
- `write_rule_report(rule_id, status, reason, evidence)`
    Records the outcome of ONE rule. `status` is PASS / FAIL /
    NEEDS_REVIEW. `evidence` is an optional list of
    `{{"file": "...", "detail": "..."}}` entries. `plan_id` is
    stamped automatically by the tool from the scope it was built
    with -- you do NOT need to pass it, but your `reason` SHOULD
    mention it so the audit trail is self-describing.
- `write_category_summary(summary, overall_status)`
    Final category verdict. Call EXACTLY ONCE after every rule has a
    report. As above, `plan_id` is attached automatically but include
    it in your narrative `summary` text so the streamed event is
    human-readable.
- Standard Deep Agents built-ins: `write_todos`, `write_file`,
  `read_file`, `ls`, `compact_conversation`.

## Operating procedure

1. **Anchor on the plan** -- read the `plan_id`, workflow_id, and
   case_id from the top of your instruction. Read the case-file and
   reference-file lists and the document catalog. If `plan_id` is
   missing or blank, log the anomaly in your final reply and continue
   with whatever scope you have.
2. **Plan** -- call `write_todos` with one todo per rule plus a final
   "write category summary" todo. Mark items in_progress / completed
   as you go.
3. **For each rule**:
   a. Read the rule's `config` and the "## Document catalog" section
      of the instruction. Using the catalog's `kind`, `summary`, and
      `key_fields`, decide which of the provided documents are
      relevant. Prefer documents whose catalog summary or key_fields
      match the rule's subject (e.g. a setback rule -> a site plan
      whose key_fields include setback distances). Fall back to
      filenames (which start with the plan_id prefix) only when the
      catalog is unhelpful.
   b. For each relevant document, call
      `analyze_pdf(s3_key=..., question=...)` with a focused, specific
      question grounded in the rule (quote numeric thresholds where
      the rule has them).
   c. Combine the returned text into a decision: PASS, FAIL, or
      NEEDS_REVIEW. NEEDS_REVIEW is appropriate when the documents
      are ambiguous or silent on the rule, OR when the plan_id
      context is missing and you cannot confirm scope.
   d. Call `write_rule_report(rule_id, status, reason, evidence)`
      exactly once for this rule. Use the rule_id EXACTLY as given;
      never invent new IDs or rename them. Mention the plan_id in
      `reason` (e.g. "For plan 138-24_1, the north setback of 6 ft
      violates the 10 ft minimum in Section 4.1.").
4. **After all rules** -- call `write_category_summary(summary,
   overall_status)` exactly once. Reference the plan_id in the
   `summary` text. Derive `overall_status` as:
     - `FAIL`         if any rule FAILed
     - `NEEDS_REVIEW` else if any rule NEEDS_REVIEW
     - `PASS`         otherwise (including when the category has no rules)
5. **Return** -- reply with a short (1--3 sentence) summary for the
   orchestrator that names the plan_id and the per-rule counts. The
   authoritative findings are in S3 / the streaming events; your
   reply is just a status line.

## Context management

Your conversation is compacted automatically when it approaches the
token budget; large tool outputs are offloaded to the virtual
filesystem. You may also proactively call `compact_conversation`
between rules if many `analyze_pdf` calls have accumulated.

## Hard rules

- NEVER invent filenames, S3 keys, plan_ids, or rule IDs. Use only
  what the instruction provides.
- NEVER call `analyze_pdf` with an S3 key outside this case's scope;
  the tool will refuse.
- NEVER mix documents from a different plan. If a filename's prefix
  doesn't match the instruction's `plan_id`, treat it as out of
  scope even if it shows up in the catalog (it should not).
- EMIT exactly one `write_rule_report` per rule, even if
  `NEEDS_REVIEW`.
- EMIT exactly one `write_category_summary` at the end.
- Do NOT spawn further subagents; finish the category inline.
"""


def build_evaluator_prompt(category: Dict[str, Any]) -> str:
    """Render the system prompt baked into one category's evaluator subagent."""
    return _EVALUATOR_TEMPLATE.format(
        category_id=category.get("category_id") or "(unknown)",
        category_name=category.get("name") or "(unnamed)",
    )


# --------------------------------------------------------------------------
# Evaluator task instruction (sent at delegation time)
# --------------------------------------------------------------------------


_INSTRUCTION_TEMPLATE = """# Category evaluation task

- workflow_id: `{workflow_id}`
- case_id: `{case_id}`
- plan_id: `{plan_id}`
- category_id: `{category_id}`
- category_name: `{category_name}`
- rule_count: {rule_count}

Plan scope: only documents whose filename starts with the prefix
`{plan_id}-` belong to THIS plan. Stamp `plan_id = "{plan_id}"` on
every `write_rule_report` and in the category summary. Filenames
that start with the same prefix (e.g. `{plan_id}-SITE-PLAN.pdf`,
`{plan_id}-STN-ENG.pdf`) all belong to THIS plan.

## Rules to evaluate

{rules_block}

## Case files (user uploads) for plan {plan_id}

{case_files_block}

## Reference files for category {category_id}

{reference_files_block}

## Document catalog

{catalog_block}

## What to do

Follow your category-evaluator procedure:
1. Anchor on `plan_id = {plan_id}`; treat anything outside that scope
   as out-of-band.
2. Plan todos (one per rule + summary).
3. For every rule: consult the document catalog above, decide which
   docs are relevant (prefer entries whose `key_fields`/`summary`
   match the rule; fall back to filenames with the `{plan_id}-`
   prefix), call `analyze_pdf` per doc with a focused question,
   decide PASS / FAIL / NEEDS_REVIEW, and call
   `write_rule_report(rule_id, status, reason, evidence)` once.
4. After all rules: call `write_category_summary(summary,
   overall_status)` exactly once, mentioning plan_id `{plan_id}` in
   the narrative.
5. Reply with a 1-3 sentence status summary for the orchestrator
   (name the plan_id `{plan_id}` and the PASS / FAIL / NEEDS_REVIEW
   counts).

Scope reminder: use only the S3 keys listed above. Cross-category /
cross-case / cross-plan reads are refused by the tools.
"""


def _render_file_manifest_for_instruction(
    files: List[Dict[str, Any]], label: str
) -> str:
    if not files:
        return f"_No {label} available._"
    lines: List[str] = []
    for f in files:
        key = f.get("s3_key", "")
        name = f.get("filename") or (key.rsplit("/", 1)[-1] if key else "?")
        size = f.get("size", "?")
        lines.append(f"- filename: `{name}` | s3_key: `{key}` | size: {size}")
    return "\n".join(lines)


def build_evaluator_task_instruction(
    *,
    workflow_id: str,
    case_id: str,
    category: Dict[str, Any],
    case_files: List[Dict[str, Any]],
    category_refs: List[Dict[str, Any]],
    user_prompt: Optional[str] = None,
    catalog_json: Optional[str] = None,
    plan_id: str = "",
) -> str:
    """Build the ``instruction`` string the orchestrator passes to a
    category evaluator subagent via ``task(...)``.

    Kept pure-string so the orchestrator can produce it via the ``task``
    tool without needing access to raw Python objects. If
    ``catalog_json`` is provided, it is embedded verbatim under a
    "## Document catalog" section; otherwise a placeholder note is
    rendered.
    """
    cat_id = category.get("category_id") or "(unknown)"
    cat_name = category.get("name") or cat_id
    rules = category.get("rules") or []
    rules_block = render_rules(rules)

    if catalog_json and catalog_json.strip():
        catalog_block = (
            "```json\n"
            + catalog_json.strip()
            + "\n```"
        )
    else:
        catalog_block = (
            "_No catalog was produced for this run. Fall back to "
            "filenames and rule context when picking documents._"
        )

    instr = _INSTRUCTION_TEMPLATE.format(
        category_id=cat_id,
        category_name=cat_name,
        workflow_id=workflow_id,
        case_id=case_id,
        plan_id=plan_id or case_id,
        rule_count=len(rules),
        rules_block=rules_block,
        case_files_block=_render_file_manifest_for_instruction(
            case_files or [], "case files"
        ),
        reference_files_block=_render_file_manifest_for_instruction(
            category_refs or [], "reference files"
        ),
        catalog_block=catalog_block,
    )

    if user_prompt and user_prompt.strip():
        instr += (
            "\n\n## User context\n\n"
            "> " + user_prompt.strip().replace("\n", "\n> ") + "\n"
        )
    return instr


# --------------------------------------------------------------------------
# Backward-compatibility shim: keep the old name so any leftover imports
# don't crash during staged rollout. Will be removed once callers move.
# --------------------------------------------------------------------------


def build_category_system_prompt(*args: Any, **kwargs: Any) -> str:  # pragma: no cover
    """Deprecated. Use :func:`build_evaluator_prompt` instead."""
    raise RuntimeError(
        "build_category_system_prompt is deprecated; the orchestrator "
        "architecture uses build_orchestrator_prompt + build_evaluator_prompt."
    )


__all__ = [
    "build_orchestrator_prompt",
    "build_evaluator_prompt",
    "build_evaluator_task_instruction",
    "build_category_system_prompt",
]


# ``json`` import is kept for potential future structured rendering; silence
# "unused" linters without an actual reference.
_ = json
