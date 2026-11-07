"""Case WebSocket pre-sign Lambda.

Issues a SigV4 pre-signed URL that a browser client can use to open a
WebSocket connection to the Swarm AgentCore Runtime scoped to ONE case.
In the orchestrator architecture the frontend opens a SINGLE WebSocket
per case -- the orchestrator then spawns one evaluator subagent per
category internally.

Payload (JSON)::

    {
      "workflow_id": "...",
      "case_id": "...",
      "user_id": "..."         # optional, surfaced in session_id for tracing
    }

Response (JSON)::

    {
      "url": "wss://...?X-Amz-Signature=...",
      "expires_in": 300,
      "session_id": "<ascii session id 33+ chars>"
    }

Auth: no Cognito check in v1 (see plan non-goals).
"""

from __future__ import annotations

import json
import os
import re
import uuid

from bedrock_agentcore.runtime import AgentCoreRuntimeClient

AGENT_RUNTIME_ARN = os.environ["AGENT_RUNTIME_ARN"]
PRESIGNED_URL_EXPIRY_SECONDS = int(
    os.environ.get("PRESIGNED_URL_EXPIRY_SECONDS", "300")
)
AWS_REGION = (
    os.environ.get("AWS_REGION")
    or os.environ.get("AWS_DEFAULT_REGION")
    or "us-east-1"
)

_client = AgentCoreRuntimeClient(region=AWS_REGION)

_VALID_ID = re.compile(r"^[A-Za-z0-9_\-]{1,128}$")


def handler(event, context):
    print(json.dumps(event))

    try:
        body = json.loads(event.get("body") or "{}")
    except Exception:
        return _response(400, {"error": "Invalid JSON body."})

    workflow_id = str(body.get("workflow_id", "")).strip()
    case_id = str(body.get("case_id", "")).strip()
    user_id = str(body.get("user_id", "anonymous")).strip() or "anonymous"

    for name, value in (
        ("workflow_id", workflow_id),
        ("case_id", case_id),
    ):
        if not value:
            return _response(400, {"error": f"Missing required field: {name}."})
        if not _VALID_ID.match(value):
            return _response(400, {"error": f"Invalid {name} format."})

    session_id = _build_session_id(
        user_id=user_id,
        workflow_id=workflow_id,
        case_id=case_id,
    )

    try:
        presigned_url = _client.generate_presigned_url(
            runtime_arn=AGENT_RUNTIME_ARN,
            session_id=session_id,
            expires=PRESIGNED_URL_EXPIRY_SECONDS,
        )
    except Exception as e:  # noqa: BLE001
        print(f"Error generating presigned URL: {e}")
        return _response(500, {"error": f"Failed to generate presigned URL: {e}"})

    return _response(
        200,
        {
            "url": presigned_url,
            "expires_in": PRESIGNED_URL_EXPIRY_SECONDS,
            "session_id": session_id,
        },
    )


def _build_session_id(
    *,
    user_id: str,
    workflow_id: str,
    case_id: str,
) -> str:
    parts = ["swarm", user_id, workflow_id, case_id, uuid.uuid4().hex]
    base = "-".join(parts)
    safe = re.sub(r"[^A-Za-z0-9_\-]", "-", base)
    if len(safe) < 33:
        safe = safe + "-" + uuid.uuid4().hex
    return safe[:128]


def _response(status_code: int, body: dict):
    return {
        "statusCode": status_code,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json",
        },
        "body": json.dumps(body),
    }
