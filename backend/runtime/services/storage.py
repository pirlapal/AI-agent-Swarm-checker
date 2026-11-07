"""S3 read helpers scoped to the assets bucket.

The AgentCore runtime needs to:
- List case files under ``cases/{workflow_id}/{case_id}/...``
- Read case files and reference files
- List reference files under ``refs/{workflow_id}/{category_id}/...``

This module centralises those ops so tools and loaders don't each
instantiate their own boto3 client or worry about decoding binary bodies.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("swarm-agentcore-storage")


_s3_client = None


def get_s3_client():
    global _s3_client
    if _s3_client is None:
        region = (
            os.environ.get("AWS_DEFAULT_REGION")
            or os.environ.get("AWS_REGION")
            or "us-east-1"
        )
        _s3_client = boto3.client("s3", region_name=region)
    return _s3_client


def get_assets_bucket() -> str:
    bucket = os.environ.get("ASSETS_BUCKET_NAME")
    if not bucket:
        raise RuntimeError("ASSETS_BUCKET_NAME env var is not set.")
    return bucket


def list_objects_under(prefix: str, bucket: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all objects under a prefix in the assets bucket.

    Returns a list of ``{key, size, last_modified}`` dicts. Paginates
    transparently.
    """
    bucket = bucket or get_assets_bucket()
    client = get_s3_client()
    paginator = client.get_paginator("list_objects_v2")
    out: List[Dict[str, Any]] = []
    try:
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []) or []:
                out.append(
                    {
                        "key": obj["Key"],
                        "size": obj.get("Size", 0),
                        "last_modified": (
                            obj["LastModified"].isoformat()
                            if obj.get("LastModified")
                            else None
                        ),
                    }
                )
    except ClientError as e:
        logger.error(f"[list_objects_under] bucket={bucket} prefix={prefix} err={e}")
        raise
    return out


def read_text_object(
    key: str,
    bucket: Optional[str] = None,
    max_bytes: int = 500_000,
) -> str:
    """Read an S3 object as UTF-8 text.

    Args:
        key: S3 object key.
        bucket: Bucket name; defaults to the assets bucket.
        max_bytes: Cap the size returned to keep prompt bloat in check.
                   Text beyond this is truncated with a marker.

    Returns the decoded text. Binary / non-UTF-8 contents are decoded
    with ``errors="replace"`` so the agent sees something rather than
    failing the tool call.
    """
    bucket = bucket or get_assets_bucket()
    client = get_s3_client()
    try:
        resp = client.get_object(Bucket=bucket, Key=key)
    except ClientError as e:
        logger.error(f"[read_text_object] bucket={bucket} key={key} err={e}")
        raise
    raw: bytes = resp["Body"].read()
    truncated = False
    if len(raw) > max_bytes:
        raw = raw[:max_bytes]
        truncated = True
    text = raw.decode("utf-8", errors="replace")
    if truncated:
        text += f"\n... [truncated after {max_bytes} bytes] ..."
    return text


def read_binary_object(key: str, bucket: Optional[str] = None) -> bytes:
    bucket = bucket or get_assets_bucket()
    client = get_s3_client()
    resp = client.get_object(Bucket=bucket, Key=key)
    return resp["Body"].read()


def put_json_object(
    key: str,
    body: Dict[str, Any],
    bucket: Optional[str] = None,
) -> None:
    """Write a JSON document to the assets bucket. Used to persist rule
    findings under ``reports/{workflow_id}/{case_id}/{category_id}/...``.
    """
    import json as _json

    bucket = bucket or get_assets_bucket()
    client = get_s3_client()
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=_json.dumps(body, default=str).encode("utf-8"),
        ContentType="application/json",
    )
