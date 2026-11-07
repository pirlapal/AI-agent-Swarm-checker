"""Reporting tools for category-evaluator subagents.

The orchestrator uses Deep Agents' built-in tools (``task``,
``write_todos``, filesystem ops) plus two custom tools exposed via
:func:`build_orchestrator_tools`:

- ``catalog_documents`` -- runs one focused ``analyze_pdf`` per
  document at the start of the run, producing the per-file descriptors
  the orchestrator pastes into each subagent's ``task`` instruction.
- ``write_case_summary`` -- called once at the end to persist the
  master case-level report under
  ``reports/{workflow_id}/{case_id}/_case_summary.json``.

Per-category evaluator subagents receive:

- ``analyze_pdf``              (see :mod:`agent.pdf_analyzer`)
- ``write_rule_report``        -- record the outcome of ONE rule
- ``write_category_summary``   -- record the category-level conclusion

Every tool is built inside a factory that closes over
``(workflow_id, case_id[, category_id])`` so neither the orchestrator
nor a subagent can accidentally -- or deliberately -- write findings
under a different scope. Cross-category writes are refused.

Findings are persisted to S3 under::

    reports/{workflow_id}/{case_id}/{category_id}/{rule_id}.json
    reports/{workflow_id}/{case_id}/{category_id}/_summary.json
    reports/{workflow_id}/{case_id}/_case_summary.json

and also returned as structured JSON envelopes the streaming layer
surfaces as ``category_result`` / ``category_summary`` / ``case_summary``
WebSocket events.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

from services.storage import put_json_object

from .cataloger import build_catalog_tool
# TODO(map): import retained so re-enabling is a one-line change.
from .map_tool import build_show_property_map_tool  # noqa: F401
from .pdf_analyzer import build_analyze_pdf_tool
from .schemas import ThrottleConfig


_VALID_STATUSES = {"PASS", "FAIL", "NEEDS_REVIEW"}


def _case_reports_prefix(workflow_id: str, case_id: str) -> str:
    return f"reports/{workflow_id}/{case_id}/"


def build_evaluator_tools(
    workflow_id: str,
    case_id: str,
    category_id: str,
    *,
    plan_id: str = "",
    throttle: Optional[ThrottleConfig] = None,
):
    """Build the tool list for ONE category-evaluator subagent.

    Returns ``[analyze_pdf, write_rule_report, write_category_summary]``.
    The orchestrator does not receive these tools -- it only delegates via
    ``task`` to the subagent that owns them.

    ``throttle`` is forwarded to ``analyze_pdf`` so the frontend's
    per-call delay and Bedrock retry policy apply to every subagent.

    ``plan_id`` is the human-readable plan identifier derived from the
    uploaded filenames (e.g. ``138-24_1``). It is stamped onto every
    persisted ``write_rule_report`` / ``write_category_summary`` record
    so downstream consumers can group findings by plan without parsing
    filenames themselves.
    """

    reports_prefix = f"reports/{workflow_id}/{case_id}/{category_id}/"

    analyze_pdf = build_analyze_pdf_tool(
        workflow_id=workflow_id,
        case_id=case_id,
        category_id=category_id,
        throttle=throttle,
    )

    @tool
    def write_rule_report(
        rule_id: str,
        status: str,
        reason: str,
        evidence: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Record the evaluation outcome for ONE rule.

        Call this exactly once for every rule listed in your task
        instruction -- even if you had to assign ``NEEDS_REVIEW`` for a
        rule because the documents were ambiguous or missing.

        Args:
            rule_id: The rule identifier exactly as provided in the task
                instruction (do not invent new IDs).
            status: One of ``PASS``, ``FAIL``, ``NEEDS_REVIEW``.
            reason: Short natural-language justification for the status.
            evidence: Optional supporting references, each like
                ``{"file": "<filename>", "detail": "<quote or pointer>"}``.

        Persists the finding to
        ``reports/{workflow_id}/{case_id}/{category_id}/{rule_id}.json``
        and returns a JSON envelope the streaming layer surfaces as a
        ``category_result`` WebSocket event.
        """
        status_up = (status or "").strip().upper()
        if status_up not in _VALID_STATUSES:
            return json.dumps(
                {
                    "status": "error",
                    "error": (
                        f"Invalid status {status!r}. "
                        f"Expected one of {sorted(_VALID_STATUSES)}."
                    ),
                }
            )
        finding = {
            "workflow_id": workflow_id,
            "case_id": case_id,
            "plan_id": plan_id,
            "category_id": category_id,
            "rule_id": rule_id,
            "status": status_up,
            "reason": reason,
            "evidence": evidence or [],
            "recorded_at": int(time.time()),
        }
        try:
            put_json_object(f"{reports_prefix}{rule_id}.json", finding)
        except Exception as e:  # noqa: BLE001
            finding["persist_error"] = str(e)
        return json.dumps({"type": "category_result", "finding": finding})

    @tool
    def write_category_summary(summary: str, overall_status: str) -> str:
        """Final category-level output, emitted after ALL rules are reported.

        Args:
            summary: Short narrative summary across all rules for this
                category (pass/fail counts + highlights).
            overall_status: One of ``PASS``, ``FAIL``, ``NEEDS_REVIEW``.
                Typically ``FAIL`` if any rule failed, ``NEEDS_REVIEW``
                if any rule was indeterminate and none failed, otherwise
                ``PASS``.

        Persists to
        ``reports/{workflow_id}/{case_id}/{category_id}/_summary.json``.
        """
        overall_up = (overall_status or "").strip().upper()
        if overall_up not in _VALID_STATUSES:
            return json.dumps(
                {
                    "status": "error",
                    "error": (
                        f"Invalid overall_status {overall_status!r}. "
                        f"Expected one of {sorted(_VALID_STATUSES)}."
                    ),
                }
            )
        body = {
            "workflow_id": workflow_id,
            "case_id": case_id,
            "plan_id": plan_id,
            "category_id": category_id,
            "overall_status": overall_up,
            "summary": summary,
            "recorded_at": int(time.time()),
        }
        try:
            put_json_object(f"{reports_prefix}_summary.json", body)
        except Exception as e:  # noqa: BLE001
            body["persist_error"] = str(e)
        return json.dumps({"type": "category_summary", "summary": body})

    return [analyze_pdf, write_rule_report, write_category_summary]


def build_orchestrator_tools(
    workflow_id: str,
    case_id: str,
    case_files: List[Dict[str, Any]],
    all_refs: Dict[str, List[Dict[str, Any]]],
    *,
    plan_id: str = "",
    throttle: Optional[ThrottleConfig] = None,
):
    """Build the tool list for the case orchestrator agent.

    Returns
    ``[catalog_documents, analyze_pdf, write_case_summary]``.

    .. note:: The F4Map live-view tool ``show_property_map`` is
       temporarily **disabled** -- see the ``TODO(map)`` block below.
       The orchestrator still extracts the property address from the
       site-plan PDF (cheap, useful in logs and the case summary) but
       does not attempt to render a map.

    The orchestrator gets its own ``analyze_pdf`` here -- it uses it
    exactly once to extract the property address from the site-plan
    PDF. It does not get ``write_rule_report`` /
    ``write_category_summary`` -- those belong to evaluator subagents
    whose scopes are category-specific.

    ``plan_id`` is the human-readable plan identifier derived from the
    uploaded filenames; it is baked into the cataloger and the case
    summary so every persisted record and every streamed WS event
    carries it.

    ``throttle`` is forwarded to the cataloger and the orchestrator's
    ``analyze_pdf`` so their per-document Bedrock calls honour the
    same retry / backoff policy as the evaluators' ``analyze_pdf``.
    """

    case_prefix = _case_reports_prefix(workflow_id, case_id)

    catalog_documents = build_catalog_tool(
        workflow_id=workflow_id,
        case_id=case_id,
        case_files=case_files,
        all_refs=all_refs,
        plan_id=plan_id,
        throttle=throttle,
    )

    # Orchestrator gets its own analyze_pdf so it can extract the property
    # address from the site plan before calling show_property_map. The
    # tool is scoped to this case's prefix (cases/{wf}/{case}/ and
    # refs/{wf}/*) exactly like the subagents' analyze_pdf; passing a
    # sentinel ``category_id`` here only affects log labels.
    orchestrator_analyze_pdf = build_analyze_pdf_tool(
        workflow_id=workflow_id,
        case_id=case_id,
        category_id="_orchestrator",
        throttle=throttle,
    )

    # TODO(map): re-enable the F4Map live-view tool once ready.
    # show_property_map = build_show_property_map_tool(
    #     workflow_id=workflow_id,
    #     case_id=case_id,
    #     plan_id=plan_id,
    # )

    @tool
    def write_case_summary(
        summary: str,
        overall_status: str,
        per_category: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Record the case-level master report after every subagent has
        finished.

        Call this EXACTLY ONCE at the end of the run, after all
        evaluator subagents have returned. It persists the master
        report to
        ``reports/{workflow_id}/{case_id}/_case_summary.json`` and
        returns a JSON envelope the streaming layer surfaces as a
        ``case_summary`` WebSocket event.

        Args:
            summary: One-paragraph narrative across all categories
                (what was reviewed, overall conclusion, notable
                issues).
            overall_status: One of ``PASS``, ``FAIL``, ``NEEDS_REVIEW``.
                Conventionally: ``FAIL`` if any category failed,
                ``NEEDS_REVIEW`` if any category was indeterminate and
                none failed, otherwise ``PASS``.
            per_category: One entry per category, each like
                ``{"category_id": "...", "category_name": "...",
                   "status": "PASS|FAIL|NEEDS_REVIEW",
                   "summary": "<optional 1-liner>"}``.
                Use the statuses reported back by each subagent.
        """
        overall_up = (overall_status or "").strip().upper()
        if overall_up not in _VALID_STATUSES:
            return json.dumps(
                {
                    "status": "error",
                    "error": (
                        f"Invalid overall_status {overall_status!r}. "
                        f"Expected one of {sorted(_VALID_STATUSES)}."
                    ),
                }
            )

        normalised: List[Dict[str, Any]] = []
        for item in per_category or []:
            if not isinstance(item, dict):
                continue
            cat_id = str(item.get("category_id") or "").strip()
            if not cat_id:
                continue
            status_up = str(item.get("status") or "").strip().upper()
            if status_up not in _VALID_STATUSES:
                status_up = "NEEDS_REVIEW"
            normalised.append(
                {
                    "category_id": cat_id,
                    "category_name": str(item.get("category_name") or "").strip(),
                    "status": status_up,
                    "summary": str(item.get("summary") or "").strip(),
                }
            )

        body = {
            "workflow_id": workflow_id,
            "case_id": case_id,
            "plan_id": plan_id,
            "overall_status": overall_up,
            "summary": summary,
            "per_category": normalised,
            "recorded_at": int(time.time()),
        }
        try:
            put_json_object(f"{case_prefix}_case_summary.json", body)
        except Exception as e:  # noqa: BLE001
            body["persist_error"] = str(e)
        return json.dumps({"type": "case_summary", "summary": body})

    return [catalog_documents, orchestrator_analyze_pdf, write_case_summary]
    # TODO(map): when re-enabling, put show_property_map back in the list
    # (before write_case_summary), e.g.:
    # return [catalog_documents, orchestrator_analyze_pdf,
    #         show_property_map, write_case_summary]


__all__ = ["build_evaluator_tools", "build_orchestrator_tools"]
