"""Pydantic request schemas for the swarm AgentCore WebSocket."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ThrottleConfig(BaseModel):
    """Frontend-controllable Bedrock throttling knobs.

    Plumbed from the ``start`` WebSocket message down to every
    ``ChatBedrockConverse`` instance used by the orchestrator, the
    cataloger, and each evaluator subagent's ``analyze_pdf`` tool.

    - ``pdf_delay_ms`` spaces out the per-PDF Bedrock calls so the
      three evaluator subagents (running concurrently inside the Deep
      Agent) don't all fire at once.
    - ``max_retries`` and ``backoff_mode`` configure boto3's built-in
      retry layer. ``adaptive`` is recommended for ThrottlingException
      because it uses a client-side token bucket that actually slows
      down as server-side throttling increases, whereas ``legacy`` caps
      retries at 4 with fixed backoff.
    """

    pdf_delay_ms: int = Field(
        default=0,
        ge=0,
        le=60_000,
        description="Delay before each analyze_pdf Bedrock call (ms).",
    )
    max_retries: int = Field(
        default=8,
        ge=1,
        le=20,
        description="Total attempts per Bedrock call, including the first.",
    )
    backoff_mode: Literal["adaptive", "standard", "legacy"] = Field(
        default="adaptive",
        description="boto3 retry mode. 'adaptive' is best for ThrottlingException.",
    )


class CaseStartRequest(BaseModel):
    """First message from the frontend on a new WebSocket connection.

    In the orchestrator architecture there is ONE WebSocket per case;
    the orchestrator Deep Agent internally spawns a subagent per
    category, so the client does not pick a category.

    Frontend sends::

        {
          "type": "start",
          "workflow_id": "...",
          "case_id": "...",
          "user_prompt": "...",
          "throttle": {
            "pdf_delay_ms": 2000,
            "max_retries": 10,
            "backoff_mode": "adaptive"
          }
        }

    ``throttle`` is optional; when omitted the server falls back to
    ``PDF_CALL_DELAY_MS`` / ``BEDROCK_MAX_RETRIES`` env vars and then to
    the ``ThrottleConfig`` field defaults.
    """

    workflow_id: str = Field(..., description="Workflow UUID")
    case_id: str = Field(
        ..., description="Case UUID created by POST /workflows/{id}/cases"
    )
    user_prompt: str = Field(default="", description="Free-form user context")
    thread_id: Optional[str] = None
    throttle: Optional[ThrottleConfig] = None


class CaseStopRequest(BaseModel):
    """Client-initiated cancellation of the running case orchestrator."""

    workflow_id: str
    case_id: str
