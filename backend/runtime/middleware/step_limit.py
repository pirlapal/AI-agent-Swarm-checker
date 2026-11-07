"""
Step Limit Middleware for V3 AI Agent.

Prevents infinite loops by pausing execution when the agent reaches a
configurable step threshold and requiring human approval to continue.

This implementation follows the same pattern as ModelCallLimitMiddleware,
using before_model/after_model hooks with state-based step tracking.

The step count is stored in agent state which:
- Persists across conversation turns (via S3Saver checkpointing)
- Is thread-specific (isolated per conversation)

IMPORTANT: We tested `awrap_model_call` to check if `request.config` contains
`langgraph_step` metadata. The test confirmed:
- `hasattr(request, 'config')` = False
- `request.runtime` has no `config` attribute either
- ModelRequest only has: messages, model, model_settings, override, response_format,
  runtime, state, system_message, system_prompt, tool_choice, tools

Therefore, we use state-based counting like ModelCallLimitMiddleware.

Flow:
1. before_model checks step count against threshold
2. If threshold reached and not approved, calls interrupt() for human approval
3. Frontend shows approval dialog with "Continue" and "Stop" buttons
4. On resume, user's choice is processed
5. If approved, extend approval window
6. If rejected, jump_to="end" immediately terminates the agent loop
7. after_model increments step count after successful model call

State Keys:
- _step_limit_count: Current step count (incremented each model call)
- _step_limit_approved_until: Step number until which user has approved

On rejection, uses jump_to="end" to immediately terminate without extra model calls.

Why not use built-in ModelCallLimitMiddleware?
- ModelCallLimitMiddleware only supports "end" or "error" exit_behavior
- It terminates the agent when limit is reached, no human approval option
- Our StepLimitMiddleware uses interrupt() to pause and ask for approval
- This allows users to extend the limit or gracefully stop
- HumanInTheLoopMiddleware is for tool-level approval, not model call limits

References:
- ModelCallLimitMiddleware pattern from langchain.agents.middleware
- https://docs.langchain.com/oss/python/langgraph/interrupts
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated, Any

from typing_extensions import NotRequired, override

from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    PrivateStateAttr,
    hook_config,
)
from langgraph.types import interrupt
from langchain_core.messages import AIMessage

if TYPE_CHECKING:
    from langgraph.runtime import Runtime

# Configure logging for CloudWatch
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("v3-agent-step-limit")
logger.setLevel(logging.INFO)


class StepLimitState(AgentState):
    """State schema for StepLimitMiddleware.

    Extends AgentState with step limit tracking fields.
    These are marked as private state attributes so they don't
    interfere with normal agent state operations.
    """
    _step_limit_count: NotRequired[Annotated[int, PrivateStateAttr]]
    _step_limit_approved_until: NotRequired[Annotated[int, PrivateStateAttr]]


class StepLimitMiddleware(AgentMiddleware[StepLimitState, Any]):
    """Tracks model call steps and requires human approval at threshold.

    This middleware monitors the number of model calls made during agent execution
    and pauses for human approval when the configured threshold is reached.

    Unlike ModelCallLimitMiddleware which terminates the agent, this middleware
    uses interrupt() to pause and wait for human decision, allowing the user to:
    - Continue: Extend the approval window for another threshold worth of steps
    - Stop: Set a flag allowing the agent to wrap up gracefully

    State Structure (verified via runtime inspection):
    - state: dict with keys like ['messages', '_step_limit_count', ...]
    - runtime: Runtime object with context, merge, override, previous, store, stream_writer
      (Note: runtime does NOT have a 'config' attribute)
    - ModelRequest in awrap_model_call also has NO 'config' attribute

    Example:
        ```python
        from middleware.step_limit import StepLimitMiddleware

        # Create middleware with 25 step threshold
        step_limit = StepLimitMiddleware(step_threshold=25)

        agent = create_agent("google_genai:gemini-2.0-flash", middleware=[step_limit])
        ```
    """

    state_schema = StepLimitState

    def __init__(self, *, step_threshold: int = 25) -> None:
        """Initialize the step limit middleware.

        Args:
            step_threshold: Number of model calls before requiring human approval.
                           Default is 25 steps.
        """
        super().__init__()

        if step_threshold < 1:
            msg = f"step_threshold must be at least 1, got {step_threshold}"
            raise ValueError(msg)

        self.step_threshold = step_threshold
        logger.info(f"[StepLimitMiddleware] Initialized with threshold: {step_threshold}")

    @hook_config(can_jump_to=["end"])
    @override
    def before_model(self, state: StepLimitState, runtime: Runtime) -> dict[str, Any] | None:
        """Check step count before making a model call.

        Uses @hook_config(can_jump_to=["end"]) so that on rejection,
        the graph jumps directly to end without an extra model call.
        """
        current_step = state.get("_step_limit_count", 0)
        approved_until = state.get("_step_limit_approved_until", 0)

        if current_step >= self.step_threshold and current_step > approved_until:
            logger.info(
                f"[StepLimitMiddleware] Step {current_step} reached threshold "
                f"(threshold={self.step_threshold}, approved_until={approved_until}). "
                f"Requesting human approval."
            )

            payload = {
                "type": "step_limit_reached",
                "current_step": current_step,
                "threshold": self.step_threshold,
                "message": f"Agent has reached {current_step} steps. Approve to continue?",
            }

            result = interrupt(payload)

            logger.info(f"[StepLimitMiddleware] Resumed with result: {result}")

            if isinstance(result, dict) and result.get("approved", False):
                new_approved_until = current_step + self.step_threshold
                logger.info(
                    f"[StepLimitMiddleware] User approved. "
                    f"Extending approval to step {new_approved_until}"
                )
                return {"_step_limit_approved_until": new_approved_until}
            else:
                logger.info("[StepLimitMiddleware] User rejected. Jumping to end.")
                return {
                    "jump_to": "end",
                    "messages": [AIMessage(content="Understood. Wrapping up the design work.")],
                }

        if current_step > 0 and current_step % 10 == 0:
            logger.info(
                f"[StepLimitMiddleware] Progress: step {current_step}/{self.step_threshold} "
                f"(approved_until={approved_until})"
            )

        return None

    @hook_config(can_jump_to=["end"])
    async def abefore_model(
        self,
        state: StepLimitState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:
        """Async version of before_model with inlined logic.

        interrupt() must be called within the correct async runnable context,
        so we cannot simply delegate to the sync before_model.
        """
        current_step = state.get("_step_limit_count", 0)
        approved_until = state.get("_step_limit_approved_until", 0)

        if current_step >= self.step_threshold and current_step > approved_until:
            logger.info(
                f"[StepLimitMiddleware] Step {current_step} reached threshold "
                f"(threshold={self.step_threshold}, approved_until={approved_until}). "
                f"Requesting human approval."
            )

            payload = {
                "type": "step_limit_reached",
                "current_step": current_step,
                "threshold": self.step_threshold,
                "message": f"Agent has reached {current_step} steps. Approve to continue?",
            }

            result = interrupt(payload)

            logger.info(f"[StepLimitMiddleware] Resumed with result: {result}")

            if isinstance(result, dict) and result.get("approved", False):
                new_approved_until = current_step + self.step_threshold
                logger.info(
                    f"[StepLimitMiddleware] User approved. "
                    f"Extending approval to step {new_approved_until}"
                )
                return {"_step_limit_approved_until": new_approved_until}
            else:
                logger.info("[StepLimitMiddleware] User rejected. Jumping to end.")
                return {
                    "jump_to": "end",
                    "messages": [AIMessage(content="Understood. Wrapping up the design work.")],
                }

        if current_step > 0 and current_step % 10 == 0:
            logger.info(
                f"[StepLimitMiddleware] Progress: step {current_step}/{self.step_threshold} "
                f"(approved_until={approved_until})"
            )

        return None

    @override
    def after_model(self, state: StepLimitState, runtime: Runtime) -> dict[str, Any] | None:
        """Increment step count after a model call.

        This is called AFTER each model invocation completes.
        We increment the step counter here so it accurately reflects
        completed model calls.

        Args:
            state: The current agent state (dict)
            runtime: The langgraph Runtime object

        Returns:
            State update with incremented step count.
        """
        current_step = state.get("_step_limit_count", 0)
        new_step = current_step + 1

        logger.info(f"[StepLimitMiddleware] after_model: incrementing step {current_step} -> {new_step}")

        return {"_step_limit_count": new_step}

    async def aafter_model(
        self,
        state: StepLimitState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:
        """Async version of after_model with inlined logic."""
        current_step = state.get("_step_limit_count", 0)
        new_step = current_step + 1

        logger.info(f"[StepLimitMiddleware] aafter_model: incrementing step {current_step} -> {new_step}")

        return {"_step_limit_count": new_step}


def create_step_limit_middleware(step_threshold: int = 25) -> StepLimitMiddleware:
    """Factory function to create StepLimitMiddleware.

    This is a convenience function that creates a StepLimitMiddleware instance
    with the specified threshold.

    Args:
        step_threshold: Number of steps before requiring human approval.
                       Default is 25 steps.

    Returns:
        A configured StepLimitMiddleware instance.
    """
    return StepLimitMiddleware(step_threshold=step_threshold)


__all__ = ["StepLimitMiddleware", "StepLimitState", "create_step_limit_middleware"]
