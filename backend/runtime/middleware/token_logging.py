import logging
from typing import Dict, Any
from langchain.agents.middleware import AgentMiddleware, AgentState
from langgraph.runtime import Runtime

logger = logging.getLogger("v3-agent-token-logging")
logger.setLevel(logging.INFO)


class TokenLoggingMiddleware(AgentMiddleware):
    """
    Logs LLM token usage (input/output tokens) for cost tracking.

    Hooks into after_model() to extract usage_metadata from AIMessage responses.
    Model-agnostic: pulls the model id from the message's response_metadata
    when available.
    """

    def __init__(self):
        super().__init__()
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.call_count = 0

    def after_model(
        self,
        state: AgentState,
        runtime: Runtime
    ) -> Dict[str, Any] | None:
        """
        Called after model generates response.
        Extracts usage_metadata from the most recent AIMessage and logs token counts.
        """
        try:
            messages = state.get("messages", [])
            if not messages:
                return None

            from langchain_core.messages import AIMessage

            last_message = messages[-1]

            if isinstance(last_message, AIMessage) and hasattr(last_message, "usage_metadata"):
                usage = last_message.usage_metadata
                if not usage:
                    return None

                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)
                total_tokens = usage.get("total_tokens", 0)

                self.total_input_tokens += input_tokens
                self.total_output_tokens += output_tokens
                self.call_count += 1

                model_id = ""
                resp_meta = getattr(last_message, "response_metadata", None) or {}
                if isinstance(resp_meta, dict):
                    model_id = (
                        resp_meta.get("model_name")
                        or resp_meta.get("model_id")
                        or resp_meta.get("model")
                        or ""
                    )

                header = "LLM TOKEN USAGE"
                if model_id:
                    header = f"{header} ({model_id})"

                logger.info("=" * 60)
                logger.info(header)
                logger.info(f"Call #{self.call_count}")
                logger.info(f"Input Tokens:  {input_tokens:,}")
                logger.info(f"Output Tokens: {output_tokens:,}")
                logger.info(f"Total Tokens:  {total_tokens:,}")
                logger.info("-" * 60)
                logger.info("Session Totals:")
                logger.info(f"Total Input:   {self.total_input_tokens:,}")
                logger.info(f"Total Output:  {self.total_output_tokens:,}")
                logger.info(f"Grand Total:   {self.total_input_tokens + self.total_output_tokens:,}")
                logger.info("=" * 60)

        except Exception as e:
            logger.error(f"Error logging token usage: {str(e)}")

        return None
