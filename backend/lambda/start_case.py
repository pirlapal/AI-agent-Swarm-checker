"""Start-case Lambda.

Creates a CASE row under a workflow. The frontend calls this once at the
beginning of a run; the returned ``case_id`` is then used to upload case
files (via the existing ``/uploads/presign`` endpoint with ``kind=case``)
and to open N WebSocket connections -- one per category -- via
``POST /caseWsPresign``.

Payload (JSON)::

    {
      "user_prompt": "free-form text from the user",
      "case_file_names": ["contract.pdf", "appendix.txt"],  # optional
      "owner_id": "user-123"                                # optional
    }

Stored item shape (DynamoDB)::

    PK  = "WORKFLOW#<workflow_id>"
    SK  = "CASE#<case_id>"
    case_id, workflow_id, status="PENDING", user_prompt,
    case_files (list of {s3_key, filename}), created_at, updated_at
"""

from __future__ import annotations

import json
import os
import time
import uuid

import boto3

workflows_table_name = os.environ["WORKFLOWS_TABLE_NAME"]
aws_region = os.environ["DEPLOYMENT_REGION"]

dynamodb = boto3.client("dynamodb", region_name=aws_region)


def handler(event, context):
    print(json.dumps(event))

    path_parameters = event.get("pathParameters") or {}
    workflow_id = path_parameters.get("id")
    if not workflow_id:
        return _response(400, {"error": "Missing workflow id in path."})

    raw_body = event.get("body") or "{}"
    try:
        body = json.loads(raw_body)
    except Exception:
        return _response(400, {"error": "Invalid JSON body."})

    user_prompt = str(body.get("user_prompt", "") or "")
    case_file_names = body.get("case_file_names") or []
    owner_id = str(body.get("owner_id", "default"))

    # Verify the parent workflow exists; fail fast with a clear error.
    try:
        parent = dynamodb.get_item(
            TableName=workflows_table_name,
            Key={
                "PK": {"S": f"WORKFLOW#{workflow_id}"},
                "SK": {"S": "META"},
            },
        )
    except Exception as e:  # noqa: BLE001 - surface AWS errors verbatim
        print(f"Error fetching workflow: {e}")
        return _response(500, {"error": f"Failed to fetch workflow: {e}"})
    if not parent.get("Item"):
        return _response(404, {"error": f"Workflow {workflow_id} not found."})

    case_id = str(uuid.uuid4())
    now = int(time.time())

    case_files_dynamo = []
    for name in case_file_names:
        filename = str(name)
        s3_key = f"cases/{workflow_id}/{case_id}/{filename}"
        case_files_dynamo.append(
            {
                "M": {
                    "s3_key": {"S": s3_key},
                    "filename": {"S": filename},
                }
            }
        )

    item = {
        "PK": {"S": f"WORKFLOW#{workflow_id}"},
        "SK": {"S": f"CASE#{case_id}"},
        "case_id": {"S": case_id},
        "workflow_id": {"S": workflow_id},
        "owner_id": {"S": owner_id},
        "status": {"S": "PENDING"},
        "user_prompt": {"S": user_prompt},
        "case_files": {"L": case_files_dynamo},
        "created_at": {"N": str(now)},
        "updated_at": {"N": str(now)},
        "GSI1PK": {"S": f"CASE_OWNER#{owner_id}"},
        "GSI1SK": {"S": f"CASE#{now}#{case_id}"},
    }

    try:
        dynamodb.put_item(
            TableName=workflows_table_name,
            Item=item,
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
    except Exception as e:  # noqa: BLE001
        print(f"Error creating case: {e}")
        return _response(500, {"error": f"Failed to create case: {e}"})

    # Return the s3 keys the frontend should pre-sign and upload to.
    case_files_out = [
        {"s3_key": f["M"]["s3_key"]["S"], "filename": f["M"]["filename"]["S"]}
        for f in case_files_dynamo
    ]

    return _response(
        201,
        {
            "case_id": case_id,
            "workflow_id": workflow_id,
            "status": "PENDING",
            "case_files": case_files_out,
        },
    )


def _response(status_code: int, body: dict):
    return {
        "statusCode": status_code,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json",
        },
        "body": json.dumps(body),
    }
