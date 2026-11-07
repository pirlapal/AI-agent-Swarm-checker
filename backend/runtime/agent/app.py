"""Swarm AgentCore Application Entry Point.

Uses ``BedrockAgentCoreApp`` with ``@app.websocket`` + ``@app.ping``.
One WebSocket connection -> one fresh case orchestrator Deep Agent
scoped to a ``(workflow_id, case_id)`` pair. The orchestrator internally
spawns one evaluator subagent per category via Deep Agents' ``task``
tool.

Client -> server messages (JSON):

- ``{"type": "start", "workflow_id", "case_id", "user_prompt"}``
    Builds the case orchestrator and streams events until completion.
    ``category_id`` is accepted for backward compatibility but ignored
    -- the orchestrator covers every category in the workflow.
- ``{"type": "ping"}``
    Keep-alive; server replies with ``{"type": "pong"}``. Does not
    cancel.
- ``{"type": "stop"}``
    Cancels the current run. Server replies with ``{"type":
    "stopped"}``.

Server -> client events: see ``streaming.py``.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import traceback
from typing import Optional

from bedrock_agentcore import BedrockAgentCoreApp
from bedrock_agentcore.runtime import PingStatus
from starlette.websockets import WebSocketDisconnect

if "/app" not in sys.path:
    sys.path.insert(0, "/app")

from .agent import create_case_orchestrator
from .schemas import CaseStartRequest
from .streaming import stream_case_orchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("swarm-agentcore-app")
logger.setLevel(logging.INFO)


app = BedrockAgentCoreApp(debug=False)


@app.ping
def health_status():
    """Report HEALTHY unconditionally; we have no pre-warm step. AgentCore
    itself verifies the HTTP port is up."""
    return PingStatus.HEALTHY


@app.websocket
async def websocket_handler(websocket, context):
    """One connection == one case orchestrator.

    The agent is lazy: we wait for the first ``start`` message so the
    frontend can reuse a presigned URL across retries without us
    spinning up DDB / S3 fetches on dead connections.
    """
    await websocket.accept()
    logger.info(
        f"[ws_handler] accepted (runtime_session={getattr(context, 'session_id', 'n/a')})"
    )

    current_task: Optional[asyncio.Task] = None

    try:
        while True:
            message = await websocket.receive_json()
            msg_type = message.get("type")
            logger.info(f"[ws_handler] msg type={msg_type}")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if msg_type == "start":
                if current_task and not current_task.done():
                    logger.info(
                        "[ws_handler] start received while task running; ignoring"
                    )
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "A run is already in progress on this connection.",
                        }
                    )
                    continue
                try:
                    throttle_raw = message.get("throttle")
                    request = CaseStartRequest(
                        workflow_id=message["workflow_id"],
                        case_id=message["case_id"],
                        user_prompt=message.get("user_prompt", "") or "",
                        thread_id=message.get("thread_id"),
                        throttle=throttle_raw if isinstance(throttle_raw, dict) else None,
                    )
                except Exception as e:
                    logger.error(f"[ws_handler] invalid start: {e}")
                    await websocket.send_json(
                        {"type": "error", "message": f"Invalid start request: {e}"}
                    )
                    continue

                try:
                    (
                        agent,
                        config,
                        thread_id,
                        case_files,
                        all_refs,
                        plan_id,
                    ) = create_case_orchestrator(
                        workflow_id=request.workflow_id,
                        case_id=request.case_id,
                        user_prompt=request.user_prompt,
                        throttle=request.throttle,
                    )
                except Exception as e:
                    logger.error(
                        f"[ws_handler] create_case_orchestrator failed: {e}"
                    )
                    logger.error(traceback.format_exc())
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": f"Failed to build agent: {e}",
                        }
                    )
                    continue

                metadata_event = {
                    "type": "metadata",
                    "thread_id": thread_id,
                    "workflow_id": request.workflow_id,
                    "case_id": request.case_id,
                    "plan_id": plan_id,
                }
                await websocket.send_json(metadata_event)

                current_task = asyncio.create_task(
                    stream_case_orchestrator(
                        websocket,
                        agent,
                        config,
                        request.user_prompt,
                        workflow_id=request.workflow_id,
                        case_id=request.case_id,
                        plan_id=plan_id,
                        case_files=case_files,
                        all_refs=all_refs,
                    )
                )

            elif msg_type == "stop":
                if current_task and not current_task.done():
                    logger.info("[ws_handler] stopping current task")
                    current_task.cancel()
                    try:
                        await current_task
                    except asyncio.CancelledError:
                        pass
                    await websocket.send_json(
                        {"type": "stopped", "reason": "user_requested"}
                    )
                else:
                    await websocket.send_json(
                        {"type": "stopped", "reason": "no_task_running"}
                    )

            else:
                logger.warning(f"[ws_handler] unknown message type: {msg_type}")
                await websocket.send_json(
                    {"type": "error", "message": f"Unknown message type: {msg_type}"}
                )

    except WebSocketDisconnect as e:
        if e.code in (1000, 1001):
            logger.info(f"[ws_handler] client disconnected cleanly code={e.code}")
        else:
            logger.warning(
                f"[ws_handler] client disconnected code={e.code} reason={e.reason}"
            )

    except Exception as e:
        logger.error(f"[ws_handler] ws error: {e}")
        logger.error(traceback.format_exc())
        try:
            await websocket.send_json({"type": "error", "message": f"WS error: {e}"})
        except Exception:
            pass

    finally:
        if current_task and not current_task.done():
            current_task.cancel()
            try:
                await current_task
            except asyncio.CancelledError:
                pass
        logger.info("[ws_handler] connection closed")


if __name__ == "__main__":
    logger.info("Starting Swarm AgentCore agent with BedrockAgentCoreApp...")
    app.run()
