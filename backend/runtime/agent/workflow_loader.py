"""Workflow + case loader.

Reads the workflow definition (categories + rules) and the case row from
the shared DynamoDB table, and lists reference + case files from S3.

DynamoDB shape (from [create_workflow.py](../../lambda/create_workflow.py)
and [start_case.py](../../lambda/start_case.py)):

    Workflow META row:
      PK=WORKFLOW#{workflow_id}
      SK=META
      definition = {
        "categories": [
          {"category_id", "name", "rules": [{"rule_id", "name", "config"}]}
        ]
      }

    Case row:
      PK=WORKFLOW#{workflow_id}
      SK=CASE#{case_id}
      case_id, workflow_id, user_prompt, case_files: [{s3_key, filename}], ...

Rule ``config`` is stored as a JSON string (DDB ``S``) to avoid schema
constraints. We parse it back here.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

from services.storage import list_objects_under

logger = logging.getLogger("swarm-agentcore-workflow-loader")
logger.setLevel(logging.INFO)


_ddb_client = None


def _ddb():
    global _ddb_client
    if _ddb_client is None:
        region = (
            os.environ.get("AWS_DEFAULT_REGION")
            or os.environ.get("AWS_REGION")
            or "us-east-1"
        )
        _ddb_client = boto3.client("dynamodb", region_name=region)
    return _ddb_client


def _table_name() -> str:
    t = os.environ.get("WORKFLOWS_TABLE_NAME")
    if not t:
        raise RuntimeError("WORKFLOWS_TABLE_NAME env var is not set.")
    return t


def _unwrap(attr: Optional[Dict[str, Any]]) -> Any:
    """Best-effort unwrap of a DynamoDB AttributeValue into a plain Python value.

    Covers the types used in this project: S, N, BOOL, NULL, L, M.
    """
    if attr is None:
        return None
    if "S" in attr:
        return attr["S"]
    if "N" in attr:
        try:
            return int(attr["N"])
        except Exception:
            try:
                return float(attr["N"])
            except Exception:
                return attr["N"]
    if "BOOL" in attr:
        return bool(attr["BOOL"])
    if "NULL" in attr:
        return None
    if "L" in attr:
        return [_unwrap(x) for x in attr["L"]]
    if "M" in attr:
        return {k: _unwrap(v) for k, v in attr["M"].items()}
    return attr


_PLAN_ID_TRIM = re.compile(r"[-_\s]+$")
_PDF_SUFFIX = re.compile(r"\.pdf$", re.IGNORECASE)


def derive_plan_id(filenames: List[str], *, fallback: str = "") -> str:
    """Derive the human-readable plan identifier shared by a case's files.

    The uploaded PDFs for a case always share a prefix like ``138-24_1-``
    (e.g. ``138-24_1-SITE-PLAN.pdf``, ``138-24_1-STN-ENG-LETTER.pdf``).
    The shared prefix (trailing ``-`` / ``_`` / whitespace stripped) is
    the plan identifier we surface to the orchestrator and stamp onto
    every persisted record.

    Algorithm:

    1. Drop the ``.pdf`` suffix (case-insensitive) from each filename.
    2. Compute the longest common prefix across the stems.
    3. Strip trailing ``-`` / ``_`` / whitespace from the prefix.
    4. If the result is empty (single-file uploads, non-standard
       names, nothing in common), fall back to the first stem up to its
       first ``-`` and finally to ``fallback``.

    Examples::

        ["138-24_1-SITE-PLAN.pdf", "138-24_1-STN-ENG.pdf"] -> "138-24_1"
        ["ABC-2026-SITE-PLAN.pdf", "ABC-2026-ZONING.pdf"]  -> "ABC-2026"
        ["random.pdf"]                                      -> "random"
        []                                                  -> fallback
    """
    stems = [_PDF_SUFFIX.sub("", (f or "").strip()) for f in filenames if f]
    stems = [s for s in stems if s]
    if not stems:
        return (fallback or "").strip()

    common = stems[0]
    for s in stems[1:]:
        limit = min(len(common), len(s))
        i = 0
        while i < limit and common[i] == s[i]:
            i += 1
        common = common[:i]
        if not common:
            break

    common = _PLAN_ID_TRIM.sub("", common).strip()
    if common:
        return common

    # Fallback 1: stem of first file up to first '-' (handles one-file cases).
    first = stems[0]
    head = first.split("-", 1)[0].strip()
    if head:
        return head

    return (fallback or "").strip()


def load_workflow(workflow_id: str) -> Dict[str, Any]:
    """Load the full workflow META row.

    Returns a dict with at least ``workflow_id``, ``name``, ``definition``
    (with ``categories`` containing ``rules`` whose ``config`` has been
    JSON-parsed back into a dict).
    """
    resp = _ddb().get_item(
        TableName=_table_name(),
        Key={
            "PK": {"S": f"WORKFLOW#{workflow_id}"},
            "SK": {"S": "META"},
        },
    )
    item = resp.get("Item")
    if not item:
        raise KeyError(f"Workflow {workflow_id} not found.")

    data: Dict[str, Any] = {k: _unwrap(v) for k, v in item.items()}

    definition = data.get("definition") or {}
    categories = definition.get("categories") or []
    for cat in categories:
        rules = cat.get("rules") or []
        for rule in rules:
            raw_cfg = rule.get("config")
            if isinstance(raw_cfg, str):
                try:
                    rule["config"] = json.loads(raw_cfg)
                except Exception:
                    rule["config"] = {"_raw": raw_cfg}
    data["definition"] = {"categories": categories}
    return data


def load_category(workflow_id: str, category_id: str) -> Dict[str, Any]:
    """Return a single category dict (with rules) from the workflow."""
    wf = load_workflow(workflow_id)
    for cat in wf.get("definition", {}).get("categories", []) or []:
        if cat.get("category_id") == category_id:
            return cat
    raise KeyError(
        f"Category {category_id} not found in workflow {workflow_id}."
    )


def load_case(workflow_id: str, case_id: str) -> Dict[str, Any]:
    """Load the case row and augment ``case_files`` with a live S3 listing.

    The DDB row may list intended filenames; S3 is the source of truth
    for what was actually uploaded.
    """
    try:
        resp = _ddb().get_item(
            TableName=_table_name(),
            Key={
                "PK": {"S": f"WORKFLOW#{workflow_id}"},
                "SK": {"S": f"CASE#{case_id}"},
            },
        )
    except ClientError as e:
        logger.error(f"[load_case] err={e}")
        raise

    item = resp.get("Item")
    case: Dict[str, Any] = {k: _unwrap(v) for k, v in (item or {}).items()}
    case.setdefault("case_id", case_id)
    case.setdefault("workflow_id", workflow_id)

    # Augment with live S3 listing. This is authoritative.
    live = list_objects_under(f"cases/{workflow_id}/{case_id}/")
    plan_id = derive_plan_id(
        [obj["key"].split("/")[-1] for obj in live],
        fallback=case_id,
    )
    case["case_files_s3"] = [
        {
            "s3_key": obj["key"],
            "filename": obj["key"].split("/")[-1],
            "size": obj["size"],
            "last_modified": obj["last_modified"],
            "plan_id": plan_id,
        }
        for obj in live
    ]
    case["plan_id"] = plan_id
    return case


def list_category_refs(workflow_id: str, category_id: str) -> List[Dict[str, Any]]:
    """List reference files under ``refs/{workflow_id}/{category_id}/...``.

    References are curated per-category domain knowledge (regulations,
    policies, rubric docs) the agent should consult while evaluating rules.
    """
    prefix = f"refs/{workflow_id}/{category_id}/"
    live = list_objects_under(prefix)
    return [
        {
            "s3_key": obj["key"],
            "filename": obj["key"].split("/")[-1],
            "size": obj["size"],
            "last_modified": obj["last_modified"],
        }
        for obj in live
    ]


def list_all_refs(
    workflow_id: str,
    categories: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Collect reference files for EVERY category of a workflow.

    Used by the case orchestrator so it can hand the per-category
    reference manifest down to each evaluator subagent via the ``task``
    instruction. Returns a dict keyed by ``category_id``; missing or
    empty prefixes map to an empty list.
    """
    out: Dict[str, List[Dict[str, Any]]] = {}
    for cat in categories or []:
        cat_id = cat.get("category_id")
        if not cat_id:
            continue
        try:
            out[cat_id] = list_category_refs(workflow_id, cat_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                f"[list_all_refs] workflow={workflow_id} category={cat_id} "
                f"err={exc}; returning empty list"
            )
            out[cat_id] = []
    return out
