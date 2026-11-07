"""S3-based checkpoint saver for LangGraph.

This module provides a pure S3 checkpoint saver that eliminates DynamoDB
throughput limits by storing all checkpoint data (metadata and payload) in S3.

Benefits:
- S3 has 3,500 PUT/s per prefix vs DynamoDB's partition limits
- No capacity planning needed
- Cost effective for checkpoint storage
- Drop-in replacement for DynamoDBSaver (same BaseCheckpointSaver interface)
"""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import AsyncIterator, Iterator, Sequence
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import boto3
from botocore.config import Config
from langchain_core.runnables import RunnableConfig, run_in_executor
from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    CheckpointTuple,
    PendingWrite,
    get_checkpoint_id,
)

if TYPE_CHECKING:
    from langgraph.checkpoint.base import (
        ChannelVersions,
        Checkpoint,
        CheckpointMetadata,
    )

from .s3_storage import (
    S3Storage,
    checkpoint_s3_key,
    create_s3_client,
    namespace_prefix,
    thread_prefix,
    writes_prefix,
    writes_s3_key,
)
from .serialization import CheckpointSerializer, CompressionType

logger = logging.getLogger(__name__)


class S3Saver(BaseCheckpointSaver):
    """Saves and retrieves checkpoints using pure S3 storage.

    This checkpoint saver stores all data in S3, eliminating DynamoDB
    throughput limits that can occur with high-frequency checkpoint operations.

    Args:
        bucket_name: Name of the S3 bucket for checkpoint storage
        session: Pre-configured boto3 session instance for custom credentials
        region_name: AWS region name
        endpoint_url: Custom endpoint URL for the S3 service (for testing)
        boto_config: Botocore config object
        ttl_seconds: Optional TTL in seconds for automatic cleanup via S3 lifecycle
        enable_compression: If True, compresses checkpoint data before storing
    """

    def __init__(
        self,
        bucket_name: str,
        session: boto3.Session | None = None,
        region_name: str | None = None,
        endpoint_url: str | None = None,
        boto_config: Config | None = None,
        ttl_seconds: int | None = None,
        enable_compression: bool = False,
    ) -> None:
        super().__init__()

        self.bucket_name = bucket_name
        self.ttl_seconds = ttl_seconds

        # Initialize S3 client
        s3_client = create_s3_client(
            session=session,
            region_name=region_name,
            endpoint_url=endpoint_url,
            boto_config=boto_config,
        )

        # Initialize S3 storage helper
        self.storage = S3Storage(
            s3_client=s3_client,
            bucket_name=bucket_name,
            ttl_seconds=ttl_seconds,
        )

        # Initialize serializer
        self.serializer = CheckpointSerializer(
            self.serde,
            enable_compression=enable_compression,
        )

        logger.info(
            f"S3Saver initialized: bucket={bucket_name}, "
            f"ttl={ttl_seconds}s, compression={enable_compression}"
        )

    # ========== Core Checkpoint Operations ==========

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        """Retrieve a checkpoint tuple based on config.

        Args:
            config: Configuration containing thread_id, checkpoint_ns, and
                optionally checkpoint_id

        Returns:
            CheckpointTuple if found, None otherwise
        """
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = get_checkpoint_id(config)

        if checkpoint_id:
            # Get specific checkpoint by ID
            checkpoint_data = self._get_checkpoint(thread_id, checkpoint_ns, checkpoint_id)
        else:
            # Get latest checkpoint
            checkpoint_data = self._get_latest_checkpoint(thread_id, checkpoint_ns)

        if not checkpoint_data:
            return None

        # Get pending writes for this checkpoint
        pending_writes = self._get_pending_writes(
            thread_id,
            checkpoint_data["checkpoint_ns"],
            checkpoint_data["checkpoint_id"],
        )


        # Build checkpoint config
        checkpoint_config: RunnableConfig = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_data["checkpoint_ns"],
                "checkpoint_id": checkpoint_data["checkpoint_id"],
            }
        }

        # Build parent config
        parent_config: RunnableConfig | None = (
            {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_data["checkpoint_ns"],
                    "checkpoint_id": checkpoint_data["parent_checkpoint_id"],
                }
            }
            if checkpoint_data.get("parent_checkpoint_id")
            else None
        )

        return CheckpointTuple(
            config=checkpoint_config,
            checkpoint=checkpoint_data["checkpoint"],
            metadata=checkpoint_data["metadata"],
            parent_config=parent_config,
            pending_writes=pending_writes,
        )

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        """Asynchronously retrieve a checkpoint tuple from S3."""
        return await run_in_executor(None, self.get_tuple, config)

    def put(
        self,
        config: RunnableConfig,
        checkpoint: "Checkpoint",
        metadata: "CheckpointMetadata",
        new_versions: "ChannelVersions",
    ) -> RunnableConfig:
        """Store a checkpoint with its configuration and metadata.

        Args:
            config: Configuration for the checkpoint
            checkpoint: The checkpoint to store
            metadata: Additional metadata for the checkpoint
            new_versions: New channel versions as of this write

        Returns:
            Updated configuration after storing the checkpoint

        Raises:
            ValueError: If required config fields are missing
        """
        thread_id = config["configurable"].get("thread_id")
        if thread_id is None:
            raise ValueError("thread_id must be configured")

        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        parent_checkpoint_id = config["configurable"].get("checkpoint_id")
        checkpoint_id = checkpoint["id"]

        # Merge metadata
        metadata_to_store = dict(metadata)
        config_metadata = config.get("metadata", {})
        if isinstance(config_metadata, dict):
            metadata_to_store.update(config_metadata)

        # Serialize checkpoint + metadata together
        checkpoint_value = {"checkpoint": checkpoint, "metadata": metadata_to_store}
        payload_type, payload_data, compression_type = self.serializer.serialize(
            checkpoint_value
        )

        # Build S3 object data
        s3_data = {
            "checkpoint_id": checkpoint_id,
            "checkpoint_ns": checkpoint_ns,
            "thread_id": thread_id,
            "parent_checkpoint_id": parent_checkpoint_id,
            "payload_type": payload_type,
            "compression": compression_type.value if compression_type else None,
            "payload": base64.b64encode(payload_data).decode("utf-8"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Store to S3
        s3_key = checkpoint_s3_key(thread_id, checkpoint_ns, checkpoint_id)
        self.storage.put_object(s3_key, json.dumps(s3_data))

        logger.debug(
            f"Stored checkpoint: thread_id={thread_id}, "
            f"checkpoint_id={checkpoint_id}, size={len(payload_data) / 1024:.1f}KB"
        )

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: "Checkpoint",
        metadata: "CheckpointMetadata",
        new_versions: "ChannelVersions",
    ) -> RunnableConfig:
        """Asynchronously store a checkpoint."""
        return await run_in_executor(
            None, self.put, config, checkpoint, metadata, new_versions
        )

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Store intermediate writes linked to a checkpoint.

        Args:
            config: Configuration of the related checkpoint
            writes: List of (channel, value) tuples to store
            task_id: Identifier for the task creating the writes
            task_path: Path of the task creating the writes (for nested task tracking)

        Raises:
            ValueError: If required config fields are missing
        """
        thread_id = config["configurable"].get("thread_id")
        checkpoint_id = config["configurable"].get("checkpoint_id")
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")

        if thread_id is None or checkpoint_id is None:
            raise ValueError("Runnable config must contain thread_id and checkpoint_id")

        if not writes:
            return

        for idx, (channel, value) in enumerate(writes):
            # Handle special channels with fixed indices
            resolved_idx = str(int(WRITES_IDX_MAP.get(channel, idx)))

            # Serialize value
            value_type, value_data, compression_type = self.serializer.serialize(value)

            # Build write object
            write_data = {
                "task_id": task_id,
                "task_path": task_path,
                "channel": channel,
                "idx": resolved_idx,
                "checkpoint_id": checkpoint_id,
                "value_type": value_type,
                "compression": compression_type.value if compression_type else None,
                "payload": base64.b64encode(value_data).decode("utf-8"),
            }

            # Store to S3
            s3_key = writes_s3_key(
                thread_id, checkpoint_ns, checkpoint_id, task_id, resolved_idx
            )
            self.storage.put_object(s3_key, json.dumps(write_data))

            logger.debug(
                f"Stored write: checkpoint_id={checkpoint_id}, "
                f"task_id={task_id}, idx={resolved_idx}, "
                f"size={len(value_data) / 1024:.1f}KB"
            )

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Asynchronously store intermediate writes."""
        return await run_in_executor(
            None, self.put_writes, config, writes, task_id, task_path
        )

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        """List checkpoints from S3.

        Args:
            config: Config containing thread_id and optionally checkpoint_ns
            filter: Additional filtering criteria for metadata
            before: If provided, only checkpoints before this checkpoint ID
            limit: Maximum number of checkpoints to return

        Yields:
            Iterator[CheckpointTuple]: An iterator of checkpoint tuples

        Raises:
            ValueError: If config is None or doesn't contain thread_id
        """
        thread_id = config.get("configurable", {}).get("thread_id") if config else None
        if thread_id is None:
            raise ValueError("Runnable config must contain thread_id")

        checkpoint_ns = (
            config.get("configurable", {}).get("checkpoint_ns") if config else None
        )

        before_checkpoint_id = None
        if before is not None:
            before_checkpoint_id = before.get("configurable", {}).get("checkpoint_id")

        items_yielded = 0

        # Get prefix for listing
        prefix = namespace_prefix(thread_id, checkpoint_ns or "")

        # List all checkpoint objects
        objects = self.storage.list_objects(prefix)

        # Filter to checkpoint.json files only and sort by checkpoint_id (descending)
        checkpoint_objects = [
            obj for obj in objects if obj["Key"].endswith("/checkpoint.json")
        ]
        # Sort by key (checkpoint_id is timestamp-based, so lexicographic sort works)
        checkpoint_objects.sort(key=lambda x: x["Key"], reverse=True)

        for obj in checkpoint_objects:
            if limit is not None and items_yielded >= limit:
                break

            # Extract checkpoint_id from key
            # Key format: checkpoints/{thread_id}/{ns}/{checkpoint_id}/checkpoint.json
            key_parts = obj["Key"].split("/")
            if len(key_parts) < 4:
                continue
            checkpoint_id = key_parts[-2]

            # Apply before filter
            if before_checkpoint_id and checkpoint_id >= before_checkpoint_id:
                continue

            # Load checkpoint data
            data = self.storage.get_object(obj["Key"])
            if not data:
                continue

            checkpoint_data = self._parse_checkpoint_data(data)
            if not checkpoint_data:
                continue

            # Apply metadata filter
            if filter:
                metadata = checkpoint_data.get("metadata", {})
                if not all(metadata.get(k) == v for k, v in filter.items()):
                    continue

            # Get pending writes
            pending_writes = self._get_pending_writes(
                thread_id,
                checkpoint_data["checkpoint_ns"],
                checkpoint_data["checkpoint_id"],
            )

            # Build configs
            checkpoint_config: RunnableConfig = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_data["checkpoint_ns"],
                    "checkpoint_id": checkpoint_data["checkpoint_id"],
                }
            }

            parent_config: RunnableConfig | None = (
                {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_data["checkpoint_ns"],
                        "checkpoint_id": checkpoint_data["parent_checkpoint_id"],
                    }
                }
                if checkpoint_data.get("parent_checkpoint_id")
                else None
            )

            yield CheckpointTuple(
                config=checkpoint_config,
                checkpoint=checkpoint_data["checkpoint"],
                metadata=checkpoint_data["metadata"],
                parent_config=parent_config,
                pending_writes=pending_writes,
            )

            items_yielded += 1

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """Asynchronously list checkpoints."""
        for item in self.list(config, filter=filter, before=before, limit=limit):
            yield item

    def delete_thread(self, thread_id: str) -> None:
        """Delete all checkpoints and writes associated with a thread.

        Args:
            thread_id: The thread ID whose data should be deleted
        """
        prefix = thread_prefix(thread_id)
        result = self.storage.delete_objects_with_prefix(prefix)

        logger.info(
            f"Deleted thread {thread_id}: "
            f"deleted={len(result['deleted'])}, failed={len(result['failed'])}"
        )

    async def adelete_thread(self, thread_id: str) -> None:
        """Asynchronously delete all data for a thread."""
        return await run_in_executor(None, self.delete_thread, thread_id)

    # ========== Internal Helper Methods ==========

    def _get_checkpoint(
        self, thread_id: str, checkpoint_ns: str, checkpoint_id: str
    ) -> dict | None:
        """Retrieve a specific checkpoint by ID."""
        s3_key = checkpoint_s3_key(thread_id, checkpoint_ns, checkpoint_id)
        data = self.storage.get_object(s3_key)

        if not data:
            return None

        return self._parse_checkpoint_data(data)

    def _get_latest_checkpoint(
        self, thread_id: str, checkpoint_ns: str
    ) -> dict | None:
        """Get the latest checkpoint for a thread/namespace."""
        prefix = namespace_prefix(thread_id, checkpoint_ns)
        objects = self.storage.list_objects(prefix)

        # Filter to checkpoint.json files
        checkpoint_objects = [
            obj for obj in objects if obj["Key"].endswith("/checkpoint.json")
        ]

        if not checkpoint_objects:
            return None

        # Sort by key descending (checkpoint_id is timestamp-based)
        checkpoint_objects.sort(key=lambda x: x["Key"], reverse=True)

        # Get the most recent checkpoint
        latest_key = checkpoint_objects[0]["Key"]
        data = self.storage.get_object(latest_key)

        if not data:
            return None

        return self._parse_checkpoint_data(data)

    def _parse_checkpoint_data(self, data: bytes) -> dict | None:
        """Parse and deserialize checkpoint data from S3."""
        try:
            s3_data = json.loads(data.decode("utf-8"))

            # Decode and deserialize payload
            payload_data = base64.b64decode(s3_data["payload"])
            compression_str = s3_data.get("compression")
            compression_type = (
                CompressionType(compression_str) if compression_str else None
            )

            checkpoint_value = self.serializer.deserialize(
                s3_data["payload_type"],
                payload_data,
                compression_type,
            )

            return {
                "checkpoint": checkpoint_value["checkpoint"],
                "metadata": checkpoint_value["metadata"],
                "checkpoint_id": s3_data["checkpoint_id"],
                "checkpoint_ns": s3_data["checkpoint_ns"],
                "thread_id": s3_data["thread_id"],
                "parent_checkpoint_id": s3_data.get("parent_checkpoint_id"),
            }

        except Exception as e:
            logger.error(f"Failed to parse checkpoint data: {e}")
            return None

    def _get_pending_writes(
        self, thread_id: str, checkpoint_ns: str, checkpoint_id: str
    ) -> list[PendingWrite]:
        """Retrieve pending writes for a checkpoint."""
        prefix = writes_prefix(thread_id, checkpoint_ns, checkpoint_id)
        objects = self.storage.list_objects(prefix)

        writes: list[PendingWrite] = []

        for obj in objects:
            data = self.storage.get_object(obj["Key"])
            if not data:
                continue

            try:
                write_data = json.loads(data.decode("utf-8"))

                # Decode and deserialize payload
                payload_data = base64.b64decode(write_data["payload"])
                compression_str = write_data.get("compression")
                compression_type = (
                    CompressionType(compression_str) if compression_str else None
                )

                value = self.serializer.deserialize(
                    write_data["value_type"],
                    payload_data,
                    compression_type,
                )

                writes.append(
                    (write_data["task_id"], write_data["channel"], value)
                )

            except Exception as e:
                logger.error(f"Failed to parse write data from {obj['Key']}: {e}")
                continue

        return writes
