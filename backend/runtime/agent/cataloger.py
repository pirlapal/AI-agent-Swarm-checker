"""Document cataloging tool for the case orchestrator.

One call to :func:`build_catalog_tool` produces a ``catalog_documents``
tool. When the orchestrator invokes it, we iterate over every case file
and every per-category reference file and call Bedrock (Converse) once
per document, asking for a compact JSON descriptor:

- ``kind``        : one-line document type (e.g. ``"site plan"``)
- ``summary``     : 2-4 sentence description of the document's contents
- ``key_fields``  : up to 8 salient label/value pairs a compliance
                    reviewer would care about

The result is returned to the agent as a JSON string so the orchestrator
can paste it verbatim into each subagent's ``task`` instruction. It is
also wrapped in a ``{"type": "catalog", ...}`` envelope so the streaming
layer surfaces a structured ``catalog`` WS event.

This mirrors Scottsdale's ``identify_label_docs.py`` "one invoke_model
per file" pattern, but packaged as a first-class agent tool so the
whole cataloging pass is observable in the WebSocket stream.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from services.storage import read_binary_object

from .pdf_analyzer import (
    _build_analyzer_model,
    _extract_text,
    _sanitize_doc_name,
)
from .schemas import ThrottleConfig

logger = logging.getLogger("swarm-agentcore-cataloger")
logger.setLevel(logging.INFO)


_CATALOG_PROMPT = (
    "You are classifying a single document for a compliance-review "
    "workflow. In 2-4 sentences describe what this document is (its "
    "type and purpose). Then list up to 8 key fields or values a "
    "compliance reviewer would care about (e.g. setback distances in "
    "feet, lot coverage percentage, foundation depth, permit number, "
    "zoning designation, date of issue). If a value is not present, "
    "omit that field rather than guessing.\n\n"
    "Respond ONLY with a single JSON object, no prose outside the "
    "JSON, matching this schema exactly:\n"
    "{\n"
    '  "kind": "<short document type, 1-6 words>",\n'
    '  "summary": "<2-4 sentences>",\n'
    '  "key_fields": [\n'
    '    {"label": "<field name>", "value": "<verbatim or concise>"}\n'
    "  ]\n"
    "}"
)


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_catalog_json(text: str) -> Dict[str, Any]:
    """Best-effort extraction of the JSON object from a model response.

    Claude sometimes wraps the JSON in code fences or prose. We first
    try a direct ``json.loads`` and fall back to finding the outermost
    ``{...}`` block.
    """
    if not text:
        return {"kind": "unknown", "summary": "(no response)", "key_fields": []}

    stripped = text.strip()
    # Strip common fence markers
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].lstrip("\n")

    try:
        obj = json.loads(stripped)
        if isinstance(obj, dict):
            return _normalise_entry(obj)
    except Exception:
        pass

    match = _JSON_OBJECT_RE.search(text)
    if match:
        try:
            obj = json.loads(match.group(0))
            if isinstance(obj, dict):
                return _normalise_entry(obj)
        except Exception:
            pass

    return {
        "kind": "unknown",
        "summary": text[:400].strip(),
        "key_fields": [],
    }


def _normalise_entry(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce arbitrary model output into our catalog-entry schema."""
    kind = str(raw.get("kind") or "unknown").strip() or "unknown"
    summary = str(raw.get("summary") or "").strip()
    key_fields_raw = raw.get("key_fields") or raw.get("fields") or []
    key_fields: List[Dict[str, str]] = []
    if isinstance(key_fields_raw, list):
        for kf in key_fields_raw[:8]:
            if isinstance(kf, dict):
                label = str(kf.get("label") or kf.get("name") or "").strip()
                value = str(kf.get("value") or "").strip()
                if label and value:
                    key_fields.append({"label": label[:80], "value": value[:400]})
    return {"kind": kind[:80], "summary": summary[:800], "key_fields": key_fields}


def _catalog_one(
    s3_key: str,
    filename: str,
    throttle: Optional[ThrottleConfig] = None,
) -> Dict[str, Any]:
    """Run the per-doc Bedrock classifier and return a catalog entry.

    Never raises: any failure is captured inline so the orchestrator
    still gets a full list even if a single document is unreadable.
    """
    entry: Dict[str, Any] = {
        "s3_key": s3_key,
        "filename": filename,
        "kind": "unknown",
        "summary": "",
        "key_fields": [],
    }

    try:
        pdf_bytes = read_binary_object(s3_key)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"[catalog_one] download failed key={s3_key} err={exc}")
        entry["summary"] = f"ERROR: could not download: {exc}"
        return entry

    doc_name = _sanitize_doc_name(filename or s3_key.rsplit("/", 1)[-1])
    try:
        model = _build_analyzer_model(throttle)
        response = model.invoke(
            [
                HumanMessage(
                    content=[
                        {"type": "text", "text": _CATALOG_PROMPT},
                        {
                            "type": "document",
                            "document": {
                                "format": "pdf",
                                "name": doc_name,
                                "source": {"bytes": pdf_bytes},
                            },
                        },
                    ]
                )
            ]
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(f"[catalog_one] bedrock invoke failed key={s3_key} err={exc}")
        entry["summary"] = f"ERROR: classifier failed: {exc}"
        return entry

    parsed = _parse_catalog_json(_extract_text(response))
    entry.update(parsed)
    return entry


def build_catalog_tool(
    *,
    workflow_id: str,
    case_id: str,
    case_files: List[Dict[str, Any]],
    all_refs: Dict[str, List[Dict[str, Any]]],
    plan_id: str = "",
    throttle: Optional[ThrottleConfig] = None,
):
    """Create the orchestrator-side ``catalog_documents`` tool.

    The tool closes over the already-listed case/reference files so the
    agent does not need to supply arguments. Calling it exactly once
    is expected, at the start of the orchestrator's run.

    ``plan_id`` is the human-readable plan identifier derived from the
    uploaded filenames (e.g. ``138-24_1``). It is stamped on every
    catalog entry and on the top-level envelope so downstream consumers
    (subagents, streaming layer, frontend) can group by plan.

    ``throttle`` controls the per-doc Bedrock retry/backoff policy (same
    knobs surfaced on the evaluator subagents' ``analyze_pdf``).
    """

    # Snapshot the document set at agent construction time. If a new
    # file is uploaded mid-run it won't be catalogued until a new case
    # run is started -- this is the same trade-off the rest of the
    # pipeline makes (case_files was also snapshotted by load_case).
    _case_files = list(case_files or [])
    _all_refs = {cat_id: list(refs or []) for cat_id, refs in (all_refs or {}).items()}
    _throttle = throttle
    _plan_id = plan_id

    @tool
    def catalog_documents() -> str:
        """Classify every case file and reference file in scope for this
        case. Returns a JSON string with one entry per document::

            {
              "workflow_id": "...",
              "case_id": "...",
              "plan_id": "...",
              "entries": [
                {
                  "s3_key": "...",
                  "filename": "...",
                  "plan_id": "...",
                  "scope": "case" | "reference",
                  "category_id": "..." | null,
                  "kind": "<short type>",
                  "summary": "<2-4 sentences>",
                  "key_fields": [{"label": "...", "value": "..."}]
                },
                ...
              ]
            }

        Call this EXACTLY ONCE at the start of the run. Paste the JSON
        into each subagent's ``task`` description so evaluators can pick
        the right document per rule. The cataloging is idempotent but
        costs one LLM call per document, so do not call it again.
        """
        logger.info(
            f"[catalog_documents] workflow={workflow_id} case={case_id} "
            f"plan={_plan_id} case_files={len(_case_files)} "
            f"ref_categories={len(_all_refs)}"
        )

        entries: List[Dict[str, Any]] = []

        for f in _case_files:
            s3_key = f.get("s3_key") or ""
            filename = f.get("filename") or (
                s3_key.rsplit("/", 1)[-1] if s3_key else "unknown"
            )
            if not s3_key:
                continue
            entry = _catalog_one(s3_key, filename, _throttle)
            entry["scope"] = "case"
            entry["category_id"] = None
            entry["plan_id"] = _plan_id
            entries.append(entry)

        for cat_id, refs in _all_refs.items():
            for f in refs:
                s3_key = f.get("s3_key") or ""
                filename = f.get("filename") or (
                    s3_key.rsplit("/", 1)[-1] if s3_key else "unknown"
                )
                if not s3_key:
                    continue
                entry = _catalog_one(s3_key, filename, _throttle)
                entry["scope"] = "reference"
                entry["category_id"] = cat_id
                entry["plan_id"] = _plan_id
                entries.append(entry)

        payload = {
            "type": "catalog",
            "workflow_id": workflow_id,
            "case_id": case_id,
            "plan_id": _plan_id,
            "entries": entries,
        }
        return json.dumps(payload)

    return catalog_documents


__all__ = ["build_catalog_tool"]
