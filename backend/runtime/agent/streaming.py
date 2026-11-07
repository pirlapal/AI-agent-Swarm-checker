"""Stream LangGraph events from the case orchestrator to the WebSocket.

The orchestrator Deep Agent plans the categories, then spawns one
``evaluator_{category_id}`` subagent per category via ``task``. Both
layers stream tokens, tool calls, and internal ops through the same
LangGraph stream. This module flattens those events into structured
JSON envelopes the frontend can render.

WS event types (server -> client):

- ``metadata``        : one-time, sent on start with scope + thread_id
  (produced by :mod:`agent.app`, not here).
- ``manifest``        : one-time, sent on start with the case file list
  + per-category reference lists so the UI knows the docs in scope.
- ``token``           : streaming LLM text chunk (assistant-facing).
- ``tool_call``       : a non-internal tool was invoked (e.g. ``analyze_pdf``,
                       ``catalog_documents``, ``write_case_summary``).
- ``internal_step``   : a Deep Agents built-in (``write_todos``, ``task``,
                       filesystem ops, ``compact_conversation``) ran.
- ``subagent_start`` / ``subagent_end`` : lifecycle of ``task``-spawned
                       evaluator subagents.
- ``catalog``         : the orchestrator's ``catalog_documents`` call
                       finished -- carries the per-document descriptors.
- ``map_view``        : (TEMPORARILY DISABLED -- see TODO(map) below)
                       the orchestrator's ``show_property_map`` call
                       finished -- carries ``f4map_url`` + resolved
                       lat/lon so the UI can render a 3D map iframe.
                       May have ``status="error"`` if geocoding failed.
- ``category_result`` : a ``write_rule_report`` finished -- carries the
                       parsed finding.
- ``category_summary``: a ``write_category_summary`` finished -- carries
                       the parsed overall status.
- ``case_summary``    : the orchestrator's ``write_case_summary`` call
                       finished -- carries the master case report.
- ``done``            : stream complete.
- ``error``           : something went wrong.
"""

from __future__ import annotations

import json
import logging
import traceback
from typing import Any, Dict, List

from langchain_core.messages import AIMessageChunk, HumanMessage

logger = logging.getLogger("swarm-agentcore-streaming")
logger.setLevel(logging.INFO)


INTERNAL_TOOLS = {
    "write_todos",
    "read_file",
    "write_file",
    "edit_file",
    "ls",
    "glob",
    "grep",
    "task",
    "compact_conversation",
}


def _serialize_tool_call(tc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": tc.get("id", ""),
        "name": tc.get("name", ""),
        "args": tc.get("args", {}),
    }


def _format_internal_step(
    node_name: str, tool_name: str, tool_args: Dict[str, Any]
) -> Dict[str, Any]:
    subagent_label = (
        tool_args.get("subagent_type")
        or tool_args.get("agent_name")
        or tool_args.get("name")
        or "subagent"
    )
    descriptions = {
        "write_todos": "Updating task list",
        "read_file": f"Reading file: {tool_args.get('path', 'unknown')}",
        "write_file": f"Writing file: {tool_args.get('path', 'unknown')}",
        "edit_file": f"Editing file: {tool_args.get('path', 'unknown')}",
        "ls": f"Listing directory: {tool_args.get('path', '/')}",
        "glob": f"Searching files: {tool_args.get('pattern', '*')}",
        "grep": f"Searching content: {tool_args.get('pattern', '')}",
        "task": f"Delegating to sub-agent: {subagent_label}",
        "compact_conversation": "Compacting conversation context",
    }
    return {
        "type": "internal_step",
        "node": node_name,
        "tool": tool_name,
        "description": descriptions.get(tool_name, f"Internal op: {tool_name}"),
        "args": tool_args,
    }


def _build_manifest_event(
    *,
    workflow_id: str,
    case_id: str,
    plan_id: str,
    case_files: List[Dict[str, Any]],
    all_refs: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    return {
        "type": "manifest",
        "workflow_id": workflow_id,
        "case_id": case_id,
        "plan_id": plan_id,
        "case_files": case_files or [],
        "reference_files_by_category": all_refs or {},
    }


def _coerce_messages(raw: Any) -> List[Any]:
    """Unwrap LangGraph ``Overwrite`` wrappers and tolerate non-list shapes.

    Nodes inside Deep Agents may return ``{"messages": Overwrite(value=[...])}``
    to bypass the add-messages reducer. LangGraph has a known bug
    (`langchain-ai/langgraph#6909 <https://github.com/langchain-ai/langgraph/issues/6909>`_,
    fixed in PR #6910/#7167) where the wrapper is surfaced to consumers of
    the ``updates`` stream instead of the unwrapped payload. Iterating the
    wrapper raises ``TypeError: 'Overwrite' object is not iterable``.

    This helper unwraps the wrapper defensively so the streamer keeps
    working regardless of LangGraph version. Supports both the object form
    (``.value``) and the dict wire form (``{"__overwrite__": [...]}``).
    Returns ``[]`` for any shape that isn't a list/tuple after unwrapping.
    """
    if raw is None:
        return []
    inner = getattr(raw, "value", None)
    if inner is None and isinstance(raw, dict):
        inner = raw.get("__overwrite__")
    if inner is not None:
        raw = inner
    if isinstance(raw, list):
        return raw
    if isinstance(raw, tuple):
        return list(raw)
    return []


async def stream_case_orchestrator(
    websocket,
    agent,
    config: Dict[str, Any],
    user_prompt: str,
    *,
    workflow_id: str,
    case_id: str,
    plan_id: str = "",
    case_files: List[Dict[str, Any]],
    all_refs: Dict[str, List[Dict[str, Any]]],
) -> None:
    """Kick off a case run and stream events to ``websocket``.

    The orchestrator system prompt already contains the full plan +
    manifest; we also emit a structured ``manifest`` event first so the
    UI has a machine-readable copy without parsing prompts.
    """
    active_subagent = None
    try:
        await websocket.send_json(
            _build_manifest_event(
                workflow_id=workflow_id,
                case_id=case_id,
                plan_id=plan_id,
                case_files=case_files,
                all_refs=all_refs,
            )
        )

        initial_user_message = (
            user_prompt.strip()
            if user_prompt and user_prompt.strip()
            else "Begin the case review now."
        )
        input_data = {"messages": [HumanMessage(content=initial_user_message)]}

        stream_iter = agent.astream(
            input_data,
            config=config,
            stream_mode=["messages", "updates"],
            subgraphs=True,
        )

        async for stream_item in stream_iter:
            # langgraph stream with subgraphs=True returns (namespace, mode, chunk)
            if isinstance(stream_item, tuple) and len(stream_item) == 3:
                namespace, mode, chunk = stream_item
            elif isinstance(stream_item, tuple) and len(stream_item) == 2:
                mode, chunk = stream_item
                namespace = ()
            else:
                continue

            is_subagent = any(
                (isinstance(p, str) and p.startswith("subagent:"))
                for p in (namespace or ())
            )

            if mode == "messages":
                token, _metadata = chunk
                if isinstance(token, AIMessageChunk):
                    if token.content:
                        text = token.content
                        if isinstance(text, list):
                            text = "".join(
                                p.get("text", "")
                                for p in text
                                if isinstance(p, dict) and p.get("type") == "text"
                            )
                        if text:
                            await websocket.send_json(
                                {
                                    "type": "token",
                                    "content": text,
                                    "subagent": _subagent_name(namespace),
                                }
                            )

                    if getattr(token, "tool_call_chunks", None):
                        for tc_chunk in token.tool_call_chunks:
                            name = tc_chunk.get("name")
                            if not name:
                                continue
                            if name == "task" and not is_subagent:
                                # Let the updates stream pick up subagent start/end.
                                continue

            elif mode == "updates":
                if not isinstance(chunk, dict):
                    continue
                for node_name, node_update in chunk.items():
                    if not isinstance(node_update, dict):
                        continue

                    # Detect sub-agent lifecycle via namespace markers.
                    if is_subagent and active_subagent is None:
                        subagent_name = _subagent_name(namespace) or "subagent"
                        active_subagent = subagent_name
                        await websocket.send_json(
                            {
                                "type": "subagent_start",
                                "subagent": subagent_name,
                                "namespace": ":".join(
                                    str(p) for p in (namespace or ())
                                ),
                            }
                        )

                    messages = _coerce_messages(node_update.get("messages"))
                    for msg in messages:
                        tool_calls = getattr(msg, "tool_calls", None) or []
                        for tc in tool_calls:
                            name = tc.get("name", "")
                            if name in INTERNAL_TOOLS:
                                await websocket.send_json(
                                    {
                                        **_format_internal_step(
                                            node_name, name, tc.get("args", {}) or {}
                                        ),
                                        "subagent": _subagent_name(namespace),
                                    }
                                )
                            else:
                                await websocket.send_json(
                                    {
                                        "type": "tool_call",
                                        "subagent": _subagent_name(namespace),
                                        **_serialize_tool_call(tc),
                                    }
                                )

                        # ToolMessage -> parse result envelope for findings.
                        if msg.__class__.__name__ == "ToolMessage":
                            content = getattr(msg, "content", "") or ""
                            tool_name = getattr(msg, "name", "") or ""
                            if tool_name in (
                                "write_rule_report",
                                "write_category_summary",
                                "catalog_documents",
                                "write_case_summary",
                                # TODO(map): re-enable when the F4Map
                                # live-view tool is brought back online.
                                # "show_property_map",
                            ):
                                payload = _try_parse_json(content)
                                if isinstance(payload, dict) and payload.get("type"):
                                    payload["subagent"] = _subagent_name(namespace)
                                    await websocket.send_json(payload)

                    if is_subagent and active_subagent is not None and not namespace:
                        await websocket.send_json(
                            {
                                "type": "subagent_end",
                                "subagent": active_subagent,
                            }
                        )
                        active_subagent = None

        await websocket.send_json({"type": "done"})

    except Exception as e:
        logger.error(f"[stream_case_orchestrator] error: {e}")
        logger.error(traceback.format_exc())
        try:
            await websocket.send_json(
                {"type": "error", "message": f"Stream error: {e}"}
            )
        except Exception:
            pass


def _subagent_name(namespace) -> str:
    """Extract the most recent ``subagent:<name>`` label from a namespace tuple."""
    if not namespace:
        return ""
    for p in reversed(list(namespace)):
        if isinstance(p, str) and p.startswith("subagent:"):
            return p.split(":", 1)[1]
    return ""


def _try_parse_json(content: Any) -> Any:
    if isinstance(content, (dict, list)):
        return content
    if not isinstance(content, str):
        return None
    s = content.strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return None


__all__ = ["stream_case_orchestrator"]
