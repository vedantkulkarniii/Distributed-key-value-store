"""Incremental snapshot support for Phase 6."""

import json
import time
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class SnapshotType(Enum):
    """Types of snapshots."""
    FULL = "full"
    INCREMENTAL = "incremental"
    DELTA = "delta"


@dataclass
class SnapshotDelta:
    """Represents changes since last snapshot."""
    added_keys: Dict[str, Any] = field(default_factory=dict)
    modified_keys: Dict[str, Any] = field(default_factory=dict)
    deleted_keys: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def size_bytes(self) -> int:
        """Calculate delta size in bytes."""
        size = 0
        for value in self.added_keys.values():
            size += len(json.dumps(value).encode())
        for value in self.modified_keys.values():
            size += len(json.dumps(value).encode())
        size += sum(len(k.encode()) for k in self.deleted_keys)
        return size


@dataclass
class SnapshotMetadata:
    """Metadata for snapshot."""
    snapshot_id: str
    snapshot_type: SnapshotType
    term: int
    index: int
    timestamp: datetime
    base_snapshot_id: Optional[str] = None
    full_size_bytes: int = 0
    incremental_size_bytes: int = 0
    compression_ratio: float = 0.0
    num_keys: int = 0
    applied_index: int = 0
    last_included_term: int = 0


class IncrementalSnapshotManager:
    """Manages incremental snapshots."""

    def __init__(self, node_id: str):
        """Initialize incremental snapshot manager."""
        self.node_id = node_id
        self.snapshots: Dict[str, SnapshotMetadata] = {}
        self.deltas: Dict[str, SnapshotDelta] = {}
        self.last_full_snapshot: Optional[str] = None
        self.current_state: Dict[str, Any] = {}

    def create_full_snapshot(
        self, state: Dict[str, Any], term: int, index: int
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Create a full snapshot."""
        snapshot_id = f"snapshot_{self.node_id}_{int(time.time() * 1000)}"
        
        start_time = time.time()
        size = len(json.dumps(state).encode())

        metadata = SnapshotMetadata(
            snapshot_id=snapshot_id,
            snapshot_type=SnapshotType.FULL,
            term=term,
            index=index,
            timestamp=datetime.now(),
            full_size_bytes=size,
            num_keys=len(state),
            applied_index=index,
            last_included_term=term,
        )

        self.snapshots[snapshot_id] = metadata
        self.last_full_snapshot = snapshot_id
        self.current_state = state.copy()

        stats = {
            "snapshot_id": snapshot_id,
            "type": "full",
            "size_bytes": size,
            "num_keys": len(state),
            "duration_ms": (time.time() - start_time) * 1000,
        }

        return True, snapshot_id, stats

    def create_incremental_snapshot(
        self, new_state: Dict[str, Any], term: int, index: int
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Create an incremental snapshot."""
        if not self.last_full_snapshot:
            # Fall back to full snapshot
            return self.create_full_snapshot(new_state, term, index)

        snapshot_id = f"delta_{self.node_id}_{int(time.time() * 1000)}"
        start_time = time.time()

        # Calculate delta
        delta = self._calculate_delta(self.current_state, new_state)

        metadata = SnapshotMetadata(
            snapshot_id=snapshot_id,
            snapshot_type=SnapshotType.INCREMENTAL,
            term=term,
            index=index,
            timestamp=datetime.now(),
            base_snapshot_id=self.last_full_snapshot,
            incremental_size_bytes=delta.size_bytes(),
            num_keys=len(new_state),
            applied_index=index,
            last_included_term=term,
        )

        self.snapshots[snapshot_id] = metadata
        self.deltas[snapshot_id] = delta
        self.current_state = new_state.copy()

        # Calculate compression ratio
        full_size = len(json.dumps(new_state).encode())
        compression_ratio = delta.size_bytes() / full_size if full_size > 0 else 0

        stats = {
            "snapshot_id": snapshot_id,
            "type": "incremental",
            "delta_size_bytes": delta.size_bytes(),
            "full_size_bytes": full_size,
            "compression_ratio": compression_ratio,
            "added_keys": len(delta.added_keys),
            "modified_keys": len(delta.modified_keys),
            "deleted_keys": len(delta.deleted_keys),
            "duration_ms": (time.time() - start_time) * 1000,
        }

        return True, snapshot_id, stats

    def _calculate_delta(
        self, old_state: Dict[str, Any], new_state: Dict[str, Any]
    ) -> SnapshotDelta:
        """Calculate delta between two states."""
        delta = SnapshotDelta()

        # Find added and modified keys
        for key, value in new_state.items():
            if key not in old_state:
                delta.added_keys[key] = value
            elif old_state[key] != value:
                delta.modified_keys[key] = value

        # Find deleted keys
        for key in old_state:
            if key not in new_state:
                delta.deleted_keys.append(key)

        return delta

    def restore_from_incremental(
        self, base_snapshot_id: str, delta_snapshot_ids: List[str]
    ) -> Tuple[bool, Dict[str, Any]]:
        """Restore state from incremental snapshots."""
        if base_snapshot_id not in self.snapshots:
            return False, {}

        # Start with base snapshot
        state = self.current_state.copy()

        # Apply deltas in order
        for delta_id in delta_snapshot_ids:
            if delta_id not in self.deltas:
                return False, {}

            delta = self.deltas[delta_id]
            # Apply added
            state.update(delta.added_keys)
            # Apply modified
            state.update(delta.modified_keys)
            # Apply deleted
            for key in delta.deleted_keys:
                state.pop(key, None)

        return True, state

    def merge_incremental_snapshots(
        self, snapshot_ids: List[str]
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Merge multiple incremental snapshots into new full snapshot."""
        # Reconstruct state
        success, state = self.restore_from_incremental(
            self.last_full_snapshot, snapshot_ids
        )
        if not success:
            return False, "", {}

        # Create new full snapshot
        metadata = self.snapshots[self.last_full_snapshot]
        return self.create_full_snapshot(
            state, metadata.last_included_term, metadata.applied_index
        )

    def get_snapshot_size_reduction(self, snapshot_id: str) -> float:
        """Get size reduction percentage for incremental snapshot."""
        if snapshot_id not in self.snapshots:
            return 0.0

        metadata = self.snapshots[snapshot_id]
        if metadata.snapshot_type == SnapshotType.FULL:
            return 0.0

        if not metadata.full_size_bytes:
            return 0.0

        reduction = 1.0 - (
            metadata.incremental_size_bytes / metadata.full_size_bytes
        )
        return max(0.0, reduction * 100)

    def get_snapshot_chain_depth(self) -> int:
        """Get depth of incremental snapshot chain."""
        depth = 0
        current_id = None

        for snap_id, metadata in self.snapshots.items():
            if metadata.snapshot_type == SnapshotType.INCREMENTAL:
                if metadata.base_snapshot_id:
                    depth += 1

        return depth

    def should_consolidate(self, max_chain_depth: int = 10) -> bool:
        """Check if incremental chain should be consolidated."""
        return self.get_snapshot_chain_depth() > max_chain_depth

    def get_statistics(self) -> Dict[str, Any]:
        """Get snapshot statistics."""
        total_full = sum(
            1 for m in self.snapshots.values() if m.snapshot_type == SnapshotType.FULL
        )
        total_incremental = sum(
            1
            for m in self.snapshots.values()
            if m.snapshot_type == SnapshotType.INCREMENTAL
        )
        total_size = sum(
            m.incremental_size_bytes + m.full_size_bytes
            for m in self.snapshots.values()
        )
        avg_compression = sum(
            self.get_snapshot_size_reduction(snap_id)
            for snap_id in self.snapshots
        ) / len(self.snapshots) if self.snapshots else 0

        return {
            "total_snapshots": len(self.snapshots),
            "full_snapshots": total_full,
            "incremental_snapshots": total_incremental,
            "total_size_bytes": total_size,
            "average_compression_ratio": avg_compression,
            "chain_depth": self.get_snapshot_chain_depth(),
        }


class DeltaSnapshotManager:
    """Manages delta-based snapshots."""

    def __init__(self, node_id: str):
        """Initialize delta snapshot manager."""
        self.node_id = node_id
        self.full_snapshots: Dict[str, Dict[str, Any]] = {}
        self.delta_sequences: Dict[str, List[SnapshotDelta]] = {}

    def create_delta_sequence(
        self, snapshots: List[Dict[str, Any]], term: int, index: int
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Create a delta sequence from snapshots."""
        if len(snapshots) < 2:
            return False, "", {}

        sequence_id = f"delta_seq_{self.node_id}_{int(time.time() * 1000)}"
        deltas = []

        # First snapshot is the base
        base_snapshot = snapshots[0]
        self.full_snapshots[sequence_id] = base_snapshot.copy()

        # Calculate deltas for subsequent snapshots
        current = base_snapshot.copy()
        for i in range(1, len(snapshots)):
            delta = self._calculate_snapshot_delta(current, snapshots[i])
            deltas.append(delta)
            current = snapshots[i].copy()

        self.delta_sequences[sequence_id] = deltas

        stats = {
            "sequence_id": sequence_id,
            "base_snapshot_size": len(json.dumps(base_snapshot).encode()),
            "num_deltas": len(deltas),
            "total_delta_size": sum(d.size_bytes() for d in deltas),
        }

        return True, sequence_id, stats

    def _calculate_snapshot_delta(
        self, old: Dict[str, Any], new: Dict[str, Any]
    ) -> SnapshotDelta:
        """Calculate delta between snapshots."""
        delta = SnapshotDelta()

        for key, value in new.items():
            if key not in old:
                delta.added_keys[key] = value
            elif old[key] != value:
                delta.modified_keys[key] = value

        for key in old:
            if key not in new:
                delta.deleted_keys.append(key)

        return delta

    def reconstruct_snapshot(
        self, sequence_id: str, delta_index: int
    ) -> Tuple[bool, Dict[str, Any]]:
        """Reconstruct snapshot at specific delta index."""
        if sequence_id not in self.full_snapshots:
            return False, {}

        state = self.full_snapshots[sequence_id].copy()
        deltas = self.delta_sequences.get(sequence_id, [])

        for i in range(min(delta_index, len(deltas))):
            delta = deltas[i]
            state.update(delta.added_keys)
            state.update(delta.modified_keys)
            for key in delta.deleted_keys:
                state.pop(key, None)

        return True, state
