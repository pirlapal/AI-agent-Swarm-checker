"""S3 storage operations for checkpoint persistence.

This module provides low-level S3 operations for storing and retrieving
checkpoint data, including TTL management via lifecycle policies.
"""

import logging
import os
from typing import TYPE_CHECKING, Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client
    from mypy_boto3_s3.type_defs import DeleteTypeDef, ObjectIdentifierTypeDef

logger = logging.getLogger(__name__)


# ========== Key Generation Functions ==========


def checkpoint_s3_key(thread_id: str, checkpoint_ns: str, checkpoint_id: str) -> str:
    """Generate S3 key for checkpoint data."""
    ns_part = checkpoint_ns if checkpoint_ns else "_default_"
    return f"checkpoints/{thread_id}/{ns_part}/{checkpoint_id}/checkpoint.json"


def writes_s3_key(
    thread_id: str,
    checkpoint_ns: str,
    checkpoint_id: str,
    task_id: str,
    idx: str,
) -> str:
    """Generate S3 key for pending write data."""
    ns_part = checkpoint_ns if checkpoint_ns else "_default_"
    return f"checkpoints/{thread_id}/{ns_part}/{checkpoint_id}/writes/{task_id}_{idx}.json"


def writes_prefix(thread_id: str, checkpoint_ns: str, checkpoint_id: str) -> str:
    """Generate S3 prefix for all writes of a checkpoint."""
    ns_part = checkpoint_ns if checkpoint_ns else "_default_"
    return f"checkpoints/{thread_id}/{ns_part}/{checkpoint_id}/writes/"


def thread_prefix(thread_id: str) -> str:
    """Generate S3 prefix for all data of a thread."""
    return f"checkpoints/{thread_id}/"


def namespace_prefix(thread_id: str, checkpoint_ns: str) -> str:
    """Generate S3 prefix for all checkpoints in a namespace."""
    ns_part = checkpoint_ns if checkpoint_ns else "_default_"
    return f"checkpoints/{thread_id}/{ns_part}/"


# ========== S3 Client Factory ==========


def create_s3_client(
    session: boto3.Session | None = None,
    region_name: str | None = None,
    endpoint_url: str | None = None,
    boto_config: Config | None = None,
) -> "S3Client":
    """Create an S3 client with appropriate configuration.

    Args:
        session: Pre-configured boto3 session instance
        region_name: AWS region name
        endpoint_url: Custom endpoint URL (for testing)
        boto_config: Boto3 config object

    Returns:
        Configured S3 client
    """
    client_kwargs: dict[str, Any] = {}

    if endpoint_url is not None:
        client_kwargs["endpoint_url"] = endpoint_url

    # Configure retries and user agent
    if boto_config is None:
        boto_config = Config(
            retries={"mode": "adaptive", "max_attempts": 5},
            user_agent_extra="langgraph-s3-checkpoint/1.0",
        )
    client_kwargs["config"] = boto_config

    # Create session if not provided
    if session is None:
        session_kwargs = {}
        if region_name is not None:
            session_kwargs["region_name"] = region_name
        else:
            session_kwargs["region_name"] = (
                os.environ.get("AWS_DEFAULT_REGION")
                or os.environ.get("AWS_REGION")
                or "us-east-1"
            )
        session = boto3.Session(**session_kwargs)

    return session.client("s3", **client_kwargs)


# ========== S3 Storage Class ==========


class S3Storage:
    """Low-level S3 storage operations for checkpoints."""

    def __init__(
        self,
        s3_client: "S3Client",
        bucket_name: str,
        ttl_seconds: int | None = None,
    ):
        """Initialize S3 storage.

        Args:
            s3_client: Configured S3 client
            bucket_name: S3 bucket for checkpoint storage
            ttl_seconds: Optional TTL in seconds for automatic cleanup
        """
        self.s3_client = s3_client
        self.bucket_name = bucket_name
        self.ttl_seconds = ttl_seconds

        # Configure lifecycle policy for TTL if set
        if ttl_seconds:
            self._ensure_lifecycle_policy()

    def _ensure_lifecycle_policy(self) -> None:
        """Configure S3 lifecycle policy for TTL-based expiration.

        Creates a tag-filtered lifecycle rule that expires objects based on their
        ttl-days tag. This allows automatic cleanup of old checkpoints.
        """
        if not self.ttl_seconds:
            return

        try:
            # Calculate expiration days (always round up, minimum 1 day)
            expiration_days = max(1, (self.ttl_seconds + 86399) // 86400)
            rule_id = f"checkpoint-ttl-expiration-{expiration_days}d"

            # Get existing rules
            try:
                response = self.s3_client.get_bucket_lifecycle_configuration(
                    Bucket=self.bucket_name
                )
                existing_rules = response.get("Rules", [])

                # Skip if rule already exists
                if any(rule.get("ID") == rule_id for rule in existing_rules):
                    logger.debug(
                        f"S3 lifecycle rule '{rule_id}' already exists in {self.bucket_name}"
                    )
                    return

            except ClientError as e:
                if e.response["Error"]["Code"] != "NoSuchLifecycleConfiguration":
                    raise
                existing_rules = []

            # Add new rule with tag filter for checkpoint TTL
            existing_rules.append(
                {
                    "ID": rule_id,
                    "Status": "Enabled",
                    "Filter": {
                        "Tag": {"Key": "ttl-days", "Value": str(expiration_days)}
                    },
                    "Expiration": {"Days": expiration_days},
                }
            )

            self.s3_client.put_bucket_lifecycle_configuration(
                Bucket=self.bucket_name,
                LifecycleConfiguration={"Rules": existing_rules},
            )

            logger.info(
                f"Added S3 lifecycle rule '{rule_id}' to {self.bucket_name}: "
                f"expire after {expiration_days} days"
            )

        except ClientError as e:
            # Don't fail if we can't set lifecycle - just log warning
            logger.warning(
                f"Failed to configure S3 lifecycle policy: {e.response['Error']['Code']} - "
                f"{e.response['Error'].get('Message', 'No message')}"
            )

    def put_object(self, key: str, data: str | bytes) -> None:
        """Store data to S3.

        Args:
            key: S3 object key
            data: Data to store (string or bytes)

        Raises:
            ClientError: If S3 operation fails
        """
        put_params: dict[str, Any] = {
            "Bucket": self.bucket_name,
            "Key": key,
            "Body": data if isinstance(data, bytes) else data.encode("utf-8"),
            "ContentType": "application/json",
        }

        # Add TTL tag if configured - used by lifecycle policy for expiration
        if self.ttl_seconds:
            expiration_days = max(1, (self.ttl_seconds + 86399) // 86400)
            put_params["Tagging"] = f"ttl-days={expiration_days}"

        try:
            self.s3_client.put_object(**put_params)
            logger.debug(
                f"S3 PUT: {key} ({len(data) if isinstance(data, (str, bytes)) else 0} bytes)"
            )
        except ClientError as err:
            logger.error(
                f"Failed to store to S3: key={key}, "
                f"error={err.response['Error']['Code']}, "
                f"message={err.response['Error'].get('Message', 'No message')}"
            )
            raise

    def get_object(self, key: str) -> bytes | None:
        """Retrieve data from S3.

        Args:
            key: S3 object key

        Returns:
            Retrieved data bytes, or None if not found

        Raises:
            ClientError: If S3 operation fails (except for not found)
        """
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
            data = response["Body"].read()
            logger.debug(f"S3 GET: {key} ({len(data)} bytes)")
            return data
        except ClientError as err:
            error_code = err.response["Error"]["Code"]
            if error_code == "NoSuchKey":
                logger.debug(f"S3 object not found: {key}")
                return None
            logger.error(
                f"Failed to retrieve from S3: key={key}, "
                f"error={error_code}, "
                f"message={err.response['Error'].get('Message', 'No message')}"
            )
            raise

    def list_objects(
        self,
        prefix: str,
        max_keys: int | None = None,
    ) -> list[dict[str, Any]]:
        """List objects with a given prefix.

        Args:
            prefix: S3 key prefix to filter objects
            max_keys: Maximum number of keys to return (None for all)

        Returns:
            List of object metadata dicts with 'Key' and 'LastModified'
        """
        objects = []
        paginator = self.s3_client.get_paginator("list_objects_v2")

        pagination_config = {}
        if max_keys:
            pagination_config["MaxItems"] = max_keys

        try:
            for page in paginator.paginate(
                Bucket=self.bucket_name,
                Prefix=prefix,
                PaginationConfig=pagination_config,
            ):
                for obj in page.get("Contents", []):
                    objects.append(
                        {
                            "Key": obj["Key"],
                            "LastModified": obj["LastModified"],
                            "Size": obj.get("Size", 0),
                        }
                    )
                    if max_keys and len(objects) >= max_keys:
                        return objects

            logger.debug(f"S3 LIST: {prefix} -> {len(objects)} objects")
            return objects

        except ClientError as err:
            logger.error(
                f"Failed to list S3 objects: prefix={prefix}, "
                f"error={err.response['Error']['Code']}"
            )
            raise

    def delete_object(self, key: str) -> bool:
        """Delete a single object from S3.

        Args:
            key: S3 object key to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
            logger.debug(f"S3 DELETE: {key}")
            return True
        except ClientError as err:
            logger.error(
                f"Failed to delete S3 object: key={key}, "
                f"error={err.response['Error']['Code']}"
            )
            return False

    def delete_objects_with_prefix(self, prefix: str) -> dict[str, list[str]]:
        """Delete all objects with a given prefix.

        Uses batch delete for efficiency (up to 1000 objects per request).

        Args:
            prefix: S3 key prefix for objects to delete

        Returns:
            Dictionary with 'deleted' and 'failed' keys containing lists of keys
        """
        deleted_keys: list[str] = []
        failed_keys: list[str] = []

        # List all objects with prefix
        objects = self.list_objects(prefix)
        if not objects:
            return {"deleted": [], "failed": []}

        # Batch delete (max 1000 per request)
        batch_size = 1000
        keys_to_delete = [obj["Key"] for obj in objects]

        for i in range(0, len(keys_to_delete), batch_size):
            batch = keys_to_delete[i : i + batch_size]

            objects_to_delete: list["ObjectIdentifierTypeDef"] = [
                {"Key": key} for key in batch
            ]
            delete_request: "DeleteTypeDef" = {"Objects": objects_to_delete}

            try:
                response = self.s3_client.delete_objects(
                    Bucket=self.bucket_name,
                    Delete=delete_request,
                )

                # Track deleted objects
                for deleted in response.get("Deleted", []):
                    if deleted.get("Key"):
                        deleted_keys.append(deleted["Key"])

                # Track failed objects
                for error in response.get("Errors", []):
                    if error.get("Key"):
                        failed_keys.append(error["Key"])
                        logger.error(
                            f"Failed to delete S3 object: key={error['Key']}, "
                            f"error={error.get('Code')}, message={error.get('Message')}"
                        )

            except ClientError as err:
                logger.error(
                    f"S3 batch delete failed: prefix={prefix}, "
                    f"error={err.response['Error']['Code']}"
                )
                failed_keys.extend(batch)

        logger.info(
            f"S3 batch delete: prefix={prefix}, "
            f"deleted={len(deleted_keys)}, failed={len(failed_keys)}"
        )

        return {"deleted": deleted_keys, "failed": failed_keys}
