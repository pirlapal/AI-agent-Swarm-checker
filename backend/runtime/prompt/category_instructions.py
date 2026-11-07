"""Renderers for the per-rule block inside the system prompt."""

from __future__ import annotations

import json
from typing import Any, Dict, List


def render_rule(rule: Dict[str, Any], index: int) -> str:
    """Render ONE rule as a clearly numbered, structured block.

    Each rule row from DynamoDB has::

        {
          "rule_id": "...",
          "name": "...",
          "config": { ...arbitrary user-defined check config... }
        }

    We surface rule_id explicitly so the model MUST use it when calling
    ``write_rule_report``.
    """
    rule_id = rule.get("rule_id") or f"rule-{index}"
    name = rule.get("name") or "(unnamed rule)"
    config = rule.get("config") or {}
    cfg_str = json.dumps(config, indent=2, default=str) if config else "{}"
    return (
        f"### Rule {index}: {name}\n"
        f"- rule_id: `{rule_id}`\n"
        f"- config:\n```json\n{cfg_str}\n```"
    )


def render_rules(rules: List[Dict[str, Any]]) -> str:
    if not rules:
        return "_No rules defined for this category. Emit a single "\
               "`write_category_summary` with status `NEEDS_REVIEW`._"
    return "\n\n".join(render_rule(r, i + 1) for i, r in enumerate(rules))


def render_file_manifest(files: List[Dict[str, Any]], label: str) -> str:
    if not files:
        return f"_No {label} available._"
    lines = [f"- `{f['s3_key']}` ({f.get('size', '?')} bytes)" for f in files]
    return "\n".join(lines)
