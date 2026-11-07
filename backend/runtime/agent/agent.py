"""Case-orchestrator Deep Agent factory.

One fresh Deep Agent per WebSocket connection, scoped to ONE
``(workflow_id, case_id)`` pair. Previously we built one agent per
``(workflow_id, case_id, category_id)`` -- the orchestrator architecture
collapses that to a single orchestrator agent that spawns one
``evaluator_{category_id}`` subagent per category via Deep Agents' ``task``
tool.

Key design points:
- The orchestrator has two custom tools (``catalog_documents``,
  ``write_case_summary``) plus Deep Agents built-ins (``task``,
  ``write_todos``, filesystem ops, ``compact_conversation``).
- Each evaluator subagent gets ``analyze_pdf`` + ``write_rule_report`` +
  ``write_category_summary`` scoped to its category.
- Deep Agents' built-in summarization middleware handles context
  compaction; we only add ``TokenLoggingMiddleware`` and the
  step-limit middleware on top.
- Checkpoints are per-case (thread_id = ``{wf}__{case}``) in S3.
- The virtual filesystem is a fresh ``InMemoryStore`` per WebSocket /
  per ``create_case_orchestrator`` call, namespaced by case for
  defense-in-depth. Scratch files live only for the duration of the
  session; authoritative outputs are persisted to S3 by the reporting
  tools.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import boto3
from botocore.config import Config as BotoConfig
from deepagents import create_deep_agent
from deepagents.backends import StoreBackend
from langchain_aws import ChatBedrockConverse
from langgraph.store.memory import InMemoryStore

from checkpoint.s3_saver import S3Saver
from middleware import (
    TokenLoggingMiddleware,
    create_step_limit_middleware,
)
from prompt import (
    build_evaluator_prompt,
    build_orchestrator_prompt,
)

from .schemas import ThrottleConfig
from .tools import build_evaluator_tools, build_orchestrator_tools
from .workflow_loader import (
    list_all_refs,
    load_case,
    load_workflow,
)

if "/app" not in sys.path:
    sys.path.insert(0, "/app")

logger = logging.getLogger("swarm-agentcore-agent")
logger.setLevel(logging.INFO)


def _resolve_throttle(throttle: Optional[ThrottleConfig]) -> ThrottleConfig:
    """Merge request-supplied throttle with env-var fallbacks.

    Precedence: explicit WS ``throttle`` field > env vars
    (``PDF_CALL_DELAY_MS`` / ``BEDROCK_MAX_RETRIES`` /
    ``BEDROCK_BACKOFF_MODE``) > ``ThrottleConfig`` defaults.

    Kept permissive: bad env values fall back to defaults instead of
    raising so ops can't brick the agent with a typo.
    """
    if throttle is not None:
        return throttle

    defaults = ThrottleConfig()
    kwargs: Dict[str, Any] = {}

    env_delay = os.environ.get("PDF_CALL_DELAY_MS")
    if env_delay:
        try:
            kwargs["pdf_delay_ms"] = int(env_delay)
        except ValueError:
            logger.warning(
                f"[throttle] ignoring invalid PDF_CALL_DELAY_MS={env_delay!r}"
            )

    env_retries = os.environ.get("BEDROCK_MAX_RETRIES")
    if env_retries:
        try:
            kwargs["max_retries"] = int(env_retries)
        except ValueError:
            logger.warning(
                f"[throttle] ignoring invalid BEDROCK_MAX_RETRIES={env_retries!r}"
            )

    env_mode = os.environ.get("BEDROCK_BACKOFF_MODE")
    if env_mode in ("adaptive", "standard", "legacy"):
        kwargs["backoff_mode"] = env_mode

    if not kwargs:
        return defaults
    try:
        return ThrottleConfig(**kwargs)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[throttle] env override rejected ({e}); using defaults")
        return defaults


def _boto_config_for(throttle: ThrottleConfig) -> BotoConfig:
    """Build a botocore Config honouring the resolved throttle policy.

    ``adaptive`` retry mode uses a client-side token bucket and scales
    with server-side throttling pressure -- recommended for Bedrock
    ThrottlingException (``legacy`` caps retries at 4 with fixed
    backoff, which is what was hitting the agent's stream error).
    """
    return BotoConfig(
        retries={
            "mode": throttle.backoff_mode,
            "total_max_attempts": throttle.max_retries,
        },
        read_timeout=120,
        connect_timeout=30,
    )


def _build_model(throttle: Optional[ThrottleConfig] = None) -> ChatBedrockConverse:
    model_id = os.environ.get(
        "BEDROCK_MODEL_ID",
        "us.anthropic.claude-sonnet-4-20250514-v1:0",
    )
    region = (
        os.environ.get("AWS_DEFAULT_REGION")
        or os.environ.get("AWS_REGION")
        or "us-east-1"
    )
    resolved = _resolve_throttle(throttle)
    logger.info(
        f"[model] ChatBedrockConverse model_id={model_id} region={region} "
        f"retry_mode={resolved.backoff_mode} max_attempts={resolved.max_retries}"
    )
    return ChatBedrockConverse(
        model=model_id,
        region_name=region,
        temperature=0,
        max_tokens=8192,
        config=_boto_config_for(resolved),
    )


def _thread_id(workflow_id: str, case_id: str) -> str:
    return f"{workflow_id}__{case_id}"


def _build_subagents(
    *,
    categories: List[Dict[str, Any]],
    workflow_id: str,
    case_id: str,
    plan_id: str,
    throttle: ThrottleConfig,
) -> List[Dict[str, Any]]:
    """One evaluator subagent per category."""
    subagents: List[Dict[str, Any]] = []
    for cat in categories or []:
        cat_id = cat.get("category_id")
        if not cat_id:
            logger.warning(f"[subagents] skipping category without id: {cat!r}")
            continue
        cat_name = cat.get("name") or cat_id
        cat_tools = build_evaluator_tools(
            workflow_id,
            case_id,
            cat_id,
            plan_id=plan_id,
            throttle=throttle,
        )
        subagents.append(
            {
                "name": f"evaluator_{cat_id}",
                "description": (
                    f"Evaluate compliance rules for the {cat_name!r} "
                    f"category (category_id={cat_id}). Provide the full "
                    f"rules list, case file S3 keys, and this category's "
                    f"reference file S3 keys in the task description."
                ),
                "system_prompt": build_evaluator_prompt(cat),
                "tools": cat_tools,
            }
        )
    return subagents


def create_case_orchestrator(
    workflow_id: str,
    case_id: str,
    user_prompt: str = "",
    throttle: Optional[ThrottleConfig] = None,
) -> Tuple[Any, Dict[str, Any], str, List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]], str]:
    """Build a fresh case-level Deep Agent.

    Returns a tuple
    ``(agent, config, thread_id, case_files, all_refs, plan_id)``.
    ``case_files`` and ``all_refs`` are returned so the streaming layer
    can surface the manifest to the UI without re-querying S3;
    ``plan_id`` is the human-readable identifier shared by this case's
    uploaded files (e.g. ``138-24_1``).
    """
    checkpoint_bucket = os.environ.get("CHECKPOINT_S3_BUCKET_NAME")
    if not checkpoint_bucket:
        raise RuntimeError("CHECKPOINT_S3_BUCKET_NAME env var is not set.")

    resolved_throttle = _resolve_throttle(throttle)
    logger.info(
        f"[create_case_orchestrator] workflow={workflow_id} case={case_id} "
        f"pdf_delay_ms={resolved_throttle.pdf_delay_ms} "
        f"max_retries={resolved_throttle.max_retries} "
        f"backoff_mode={resolved_throttle.backoff_mode}"
    )

    workflow = load_workflow(workflow_id)
    case = load_case(workflow_id, case_id)

    categories: List[Dict[str, Any]] = (
        workflow.get("definition", {}).get("categories") or []
    )
    case_files: List[Dict[str, Any]] = case.get("case_files_s3") or []
    all_refs = list_all_refs(workflow_id, categories)
    plan_id: str = (case.get("plan_id") or case_id or "").strip()

    effective_user_prompt = (
        (user_prompt or "").strip()
        or (case.get("user_prompt") or "").strip()
        or ""
    )

    system_prompt = build_orchestrator_prompt(
        workflow_id=workflow_id,
        case_id=case_id,
        plan_id=plan_id,
        user_prompt=effective_user_prompt,
        categories=categories,
        case_files=case_files,
        all_refs=all_refs,
    )

    subagents = _build_subagents(
        categories=categories,
        workflow_id=workflow_id,
        case_id=case_id,
        plan_id=plan_id,
        throttle=resolved_throttle,
    )

    region = (
        os.environ.get("AWS_DEFAULT_REGION")
        or os.environ.get("AWS_REGION")
        or "us-east-1"
    )
    boto_session = boto3.Session(region_name=region)

    checkpointer = S3Saver(
        bucket_name=checkpoint_bucket,
        session=boto_session,
        ttl_seconds=None,
    )

    # Namespace the virtual filesystem by case so sibling cases don't
    # stomp on each other. Subagents share this namespace within the
    # case -- that's intentional: write_file outputs from one evaluator
    # are visible to the orchestrator for the final summary.
    # Each path segment is a separate tuple component because LangGraph's
    # namespace validator rejects '/' inside a single component.
    #
    # Pass `store=` explicitly so StoreBackend doesn't rely on
    # langgraph.config.get_store() resolving through the AgentCore
    # WebSocket runtime -- that path returns None here and causes
    # `await None.aget(...)` inside StoreBackend.aread on the first
    # read_file tool call.
    store = InMemoryStore()
    backend = StoreBackend(
        store=store,
        namespace=lambda rt: ("filesystem", "swarm", workflow_id, case_id),
    )

    step_limit = int(os.environ.get("AGENT_STEP_LIMIT", "100"))

    model = _build_model(resolved_throttle)

    middleware = [
        TokenLoggingMiddleware(),
        create_step_limit_middleware(step_threshold=step_limit),
    ]

    agent = create_deep_agent(
        model=model,
        tools=build_orchestrator_tools(
            workflow_id=workflow_id,
            case_id=case_id,
            case_files=case_files,
            all_refs=all_refs,
            plan_id=plan_id,
            throttle=resolved_throttle,
        ),
        system_prompt=system_prompt,
        subagents=subagents,
        checkpointer=checkpointer,
        backend=backend,
        store=store,
        middleware=middleware,
    )

    thread_id = _thread_id(workflow_id, case_id)
    config: Dict[str, Any] = {
        "configurable": {
            "thread_id": thread_id,
            "workflow_id": workflow_id,
            "case_id": case_id,
            "plan_id": plan_id,
        },
        "recursion_limit": int(os.environ.get("AGENT_RECURSION_LIMIT", "500")),
    }

    logger.info(
        f"[create_case_orchestrator] agent ready thread_id={thread_id} "
        f"plan_id={plan_id} categories={len(categories)} "
        f"subagents={len(subagents)} case_files={len(case_files)} "
        f"refs={{cat:n -> ...}}"
    )

    return agent, config, thread_id, case_files, all_refs, plan_id


__all__ = ["create_case_orchestrator"]
