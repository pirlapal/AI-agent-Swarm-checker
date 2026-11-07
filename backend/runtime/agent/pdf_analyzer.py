"""PDF analysis tool for category-evaluator subagents.

Each ``analyze_pdf`` call is an **isolated LLM invocation**: the tool
downloads ONE PDF from S3, sends it to ``ChatBedrockConverse`` as a native
document block along with a focused question, and returns Claude's text
analysis to the caller. The PDF bytes never enter the subagent's own
conversation history -- only the text analysis does, which keeps
``SummarizationMiddleware`` working normally and avoids the Bedrock
Converse ``document.name`` bug (deepagents issue #2355).

This mirrors the Scottsdale ``identify_label_docs`` pattern (one
``invoke_model`` per file) while being callable on demand by the agent
rather than in a fixed pre-processing loop.

Throttling:
- Bedrock ``ChatBedrockConverse`` here uses a ``botocore.config.Config``
  whose retry mode comes from the per-run :class:`ThrottleConfig`
  (defaults: ``adaptive`` mode, 8 attempts). This replaces boto3's
  legacy 4-attempt fixed backoff that was surfacing as
  ``ThrottlingException: reached max retries: 4`` under concurrent
  evaluator subagents.
- ``analyze_pdf`` is async and awaits ``asyncio.sleep(pdf_delay_ms)``
  before each call so the frontend can space out the ~10 PDF calls the
  three evaluator subagents fire nearly simultaneously.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Optional

from botocore.config import Config as BotoConfig
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from services.storage import read_binary_object

from .schemas import ThrottleConfig

logger = logging.getLogger("swarm-agentcore-pdf-analyzer")
logger.setLevel(logging.INFO)


_DEFAULT_MODEL_ID = "us.anthropic.claude-sonnet-4-20250514-v1:0"

# Bedrock Converse constraints for the document ``name`` field:
# only alphanumerics, whitespace, hyphens, parentheses and square
# brackets; no dots; no more than one consecutive whitespace.
_UNSAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9 \-\(\)\[\]]")
_MULTI_WS = re.compile(r"\s{2,}")


def _sanitize_doc_name(filename: str) -> str:
    """Produce a Bedrock-safe document name from an arbitrary filename."""
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    cleaned = _UNSAFE_NAME_CHARS.sub("-", stem).strip() or "document"
    cleaned = _MULTI_WS.sub(" ", cleaned)
    return cleaned[:200]


def _env_throttle_fallback() -> ThrottleConfig:
    """Build a ThrottleConfig from env vars for callers that don't have
    an explicit config (currently only :mod:`agent.cataloger` going
    through ``_build_analyzer_model()`` with no arg).

    Keeps parity with :func:`agent.agent._resolve_throttle` so env
    overrides apply everywhere.
    """
    defaults = ThrottleConfig()
    kwargs: dict[str, Any] = {}

    env_retries = os.environ.get("BEDROCK_MAX_RETRIES")
    if env_retries:
        try:
            kwargs["max_retries"] = int(env_retries)
        except ValueError:
            pass

    env_mode = os.environ.get("BEDROCK_BACKOFF_MODE")
    if env_mode in ("adaptive", "standard", "legacy"):
        kwargs["backoff_mode"] = env_mode

    env_delay = os.environ.get("PDF_CALL_DELAY_MS")
    if env_delay:
        try:
            kwargs["pdf_delay_ms"] = int(env_delay)
        except ValueError:
            pass

    if not kwargs:
        return defaults
    try:
        return ThrottleConfig(**kwargs)
    except Exception:  # noqa: BLE001
        return defaults


def _build_analyzer_model(
    throttle: Optional[ThrottleConfig] = None,
) -> ChatBedrockConverse:
    model_id = os.environ.get("BEDROCK_MODEL_ID", _DEFAULT_MODEL_ID)
    region = (
        os.environ.get("AWS_DEFAULT_REGION")
        or os.environ.get("AWS_REGION")
        or "us-east-1"
    )
    max_tokens = int(os.environ.get("PDF_ANALYZER_MAX_TOKENS", "4096"))
    resolved = throttle or _env_throttle_fallback()
    boto_cfg = BotoConfig(
        retries={
            "mode": resolved.backoff_mode,
            "total_max_attempts": resolved.max_retries,
        },
        read_timeout=120,
        connect_timeout=30,
    )
    return ChatBedrockConverse(
        model=model_id,
        region_name=region,
        temperature=0,
        max_tokens=max_tokens,
        config=boto_cfg,
    )


def _extract_text(response: Any) -> str:
    """Best-effort text extraction from a ChatBedrockConverse response."""
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text") or block.get("content") or ""
                if isinstance(text, str) and text:
                    parts.append(text)
        return "".join(parts)
    return str(content) if content is not None else ""


def build_analyze_pdf_tool(
    *,
    workflow_id: str,
    case_id: str,
    category_id: str,
    throttle: Optional[ThrottleConfig] = None,
):
    """Factory returning a scoped ``analyze_pdf`` tool.

    The tool enforces that every S3 key requested falls under the
    workflow's ``cases/{workflow_id}/{case_id}/`` or ``refs/{workflow_id}/``
    prefixes. Cross-case / arbitrary reads are refused.

    ``throttle`` controls the per-call delay and the Bedrock retry
    policy. If ``None``, env-var fallbacks
    (``PDF_CALL_DELAY_MS`` / ``BEDROCK_MAX_RETRIES`` /
    ``BEDROCK_BACKOFF_MODE``) apply; otherwise defaults from
    :class:`ThrottleConfig`.
    """

    case_prefix = f"cases/{workflow_id}/{case_id}/"
    refs_prefix = f"refs/{workflow_id}/"
    resolved = throttle or _env_throttle_fallback()

    def _assert_allowed(s3_key: str) -> None:
        if not (s3_key.startswith(case_prefix) or s3_key.startswith(refs_prefix)):
            raise ValueError(
                f"s3_key {s3_key!r} is outside this agent's scope. "
                f"Allowed prefixes: {case_prefix}*, {refs_prefix}*"
            )

    @tool
    async def analyze_pdf(s3_key: str, question: str) -> str:
        """Analyse ONE PDF document by asking a focused question about it.

        Downloads the PDF from S3 and sends it to Claude (Bedrock Converse)
        as a native document block together with your question. Returns
        Claude's analysis as plain text. Each call processes exactly one
        file, so invoke this tool multiple times if a rule needs evidence
        from several documents.

        Args:
            s3_key: Full S3 key of the PDF, as listed in your task
                instruction. The key MUST live under ``cases/{workflow_id}/
                {case_id}/`` or ``refs/{workflow_id}/``; other keys are
                refused.
            question: A specific question about the document, grounded in
                the rule you are evaluating. Example: ``"Does this plan
                show setback distances? If so, list the north, south,
                east and west setbacks in feet."``

        Returns:
            Claude's text answer. If the call fails, a short error string
            is returned instead of raising, so the subagent can recover
            and report ``NEEDS_REVIEW`` rather than crashing.
        """
        try:
            _assert_allowed(s3_key)
        except ValueError as exc:
            logger.warning(f"[analyze_pdf] scope violation: {exc}")
            return f"ERROR: {exc}"

        try:
            pdf_bytes = read_binary_object(s3_key)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[analyze_pdf] download failed key={s3_key} err={exc}")
            return f"ERROR: could not download {s3_key}: {exc}"

        filename = s3_key.rsplit("/", 1)[-1]
        doc_name = _sanitize_doc_name(filename)

        if resolved.pdf_delay_ms > 0:
            await asyncio.sleep(resolved.pdf_delay_ms / 1000.0)

        logger.info(
            f"[analyze_pdf] workflow={workflow_id} case={case_id} "
            f"category={category_id} key={s3_key} size={len(pdf_bytes)} "
            f"delay_ms={resolved.pdf_delay_ms}"
        )

        try:
            model = _build_analyzer_model(resolved)
            response = await model.ainvoke(
                [
                    HumanMessage(
                        content=[
                            {"type": "text", "text": question},
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
            logger.error(
                f"[analyze_pdf] bedrock invoke failed key={s3_key} err={exc}"
            )
            return (
                f"ERROR: Bedrock analysis of {filename!r} failed: {exc}. "
                f"Consider reporting NEEDS_REVIEW for the current rule."
            )

        text = _extract_text(response)
        if not text:
            return (
                f"WARNING: Claude returned no text for {filename!r}. "
                f"Consider NEEDS_REVIEW."
            )
        return text

    return analyze_pdf


__all__ = ["build_analyze_pdf_tool"]
