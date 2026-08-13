"""Tests for incremental snapshot support."""

import pytest
from src.raft.incremental_snapshots import (
    SnapshotType,
    SnapshotDelta,
    SnapshotMetadata,
    IncrementalSnapshotManager,
    DeltaSnapshotManager,
)


class TestSnapshotDelta:
    """Tests for SnapshotDelta class."""

    def test_create_delta(self):
        """Test creating a delta."""
        delta = SnapshotDelta()
        assert len(delta.added_keys) == 0
        assert len(delta.deleted_keys) == 0

    def test_delta_size_calculation(self):
        """Test delta size calculation."""
        delta = SnapshotDelta()
        delta.added_keys = {"key1": "value1", "key2": "value2"}
        
        size = delta.size_bytes()
        assert size > 0

    def test_delta_with_modifications(self):
        """Test delta with key modifications."""
        delta = SnapshotDelta()
        delta.modified_keys = {"key1": "new_value"}
        delta.deleted_keys = ["key2"]
        
        assert len(delta.modified_keys) == 1
        assert "key2" in delta.deleted_keys


class TestIncrementalSnapshotManager:
    """Tests for incremental snapshot manager."""

    def test_manager_creation(self):
        """Test creating snapshot manager."""
        manager = IncrementalSnapshotManager("node1")
        assert manager.node_id == "node1"

    def test_create_full_snapshot(self):
        """Test creating full snapshot."""
        manager = IncrementalSnapshotManager("node1")
        state = {"key1": "value1", "key2": "value2"}
        
        success, snap_id, stats = manager.create_full_snapshot(state, term=1, index=10)
        
        assert success
        assert snap_id is not None
        assert stats["type"] == "full"
        assert stats["num_keys"] == 2

    def test_create_incremental_snapshot(self):
        """Test creating incremental snapshot."""
        manager = IncrementalSnapshotManager("node1")
        
        # Create base full snapshot
        state1 = {"key1": "value1", "key2": "value2"}
        manager.create_full_snapshot(state1, term=1, index=10)
        
        # Create incremental
        state2 = {"key1": "value1_modified", "key3": "value3"}
        success, snap_id, stats = manager.create_incremental_snapshot(state2, term=1, index=20)
        
        assert success
        assert stats["type"] == "incremental"

    def test_restore_from_incremental(self):
        """Test restoring state from incremental snapshots."""
        manager = IncrementalSnapshotManager("node1")
        
        state1 = {"key1": "value1"}
        base_id, _, _ = manager.create_full_snapshot(state1, 1, 10)
        
        state2 = {"key1": "value1", "key2": "value2"}
        delta_id, _, _ = manager.create_incremental_snapshot(state2, 1, 20)
        
        success, restored = manager.restore_from_incremental(base_id, [delta_id])
        
        assert success
        assert restored["key1"] == "value1"
        assert restored["key2"] == "value2"

    def test_size_reduction(self):
        """Test incremental snapshot size reduction."""
        manager = IncrementalSnapshotManager("node1")
        
        state1 = {f"key_{i}": f"value_{i}" for i in range(100)}
        manager.create_full_snapshot(state1, 1, 10)
        
        state2 = {f"key_{i}": f"value_{i}" for i in range(100)}
        state2["key_100"] = "new_key"
        _, snap_id, _ = manager.create_incremental_snapshot(state2, 1, 20)
        
        reduction = manager.get_snapshot_size_reduction(snap_id)
        assert reduction > 0
        assert reduction < 100

    def test_chain_depth(self):
        """Test incremental snapshot chain depth."""
        manager = IncrementalSnapshotManager("node1")
        
        state = {"key1": "value1"}
        manager.create_full_snapshot(state, 1, 10)
        
        # Create several incremental snapshots
        for i in range(5):
            state[f"key_{i}"] = f"value_{i}"
            manager.create_incremental_snapshot(state, 1, 20 + i)
        
        depth = manager.get_snapshot_chain_depth()
        assert depth >= 5

    def test_should_consolidate(self):
        """Test consolidation decision."""
        manager = IncrementalSnapshotManager("node1")
        
        state = {"key1": "value1"}
        manager.create_full_snapshot(state, 1, 10)
        
        # Create many incremental snapshots
        for i in range(15):
            state[f"key_{i}"] = f"value_{i}"
            manager.create_incremental_snapshot(state, 1, 20 + i)
        
        should_consolidate = manager.should_consolidate(max_chain_depth=10)
        assert should_consolidate

    def test_merge_incremental_snapshots(self):
        """Test merging incremental snapshots."""
        manager = IncrementalSnapshotManager("node1")
        
        state1 = {"key1": "value1"}
        manager.create_full_snapshot(state1, 1, 10)
        
        snapshots = []
        for i in range(3):
            state = {f"key_{i}": f"value_{i}"}
            _, snap_id, _ = manager.create_incremental_snapshot(state, 1, 20 + i)
            snapshots.append(snap_id)
        
        success, new_snap_id, stats = manager.merge_incremental_snapshots(snapshots)
        
        assert success
        assert new_snap_id is not None

    def test_statistics(self):
        """Test snapshot statistics."""
        manager = IncrementalSnapshotManager("node1")
        
        state = {"key1": "value1"}
        manager.create_full_snapshot(state, 1, 10)
        
        state["key2"] = "value2"
        manager.create_incremental_snapshot(state, 1, 20)
        
        stats = manager.get_statistics()
        
        assert stats["total_snapshots"] == 2
        assert stats["full_snapshots"] == 1
        assert stats["incremental_snapshots"] == 1

    def test_calculate_delta(self):
        """Test delta calculation."""
        manager = IncrementalSnapshotManager("node1")
        
        old_state = {"key1": "value1", "key2": "value2"}
        new_state = {"key1": "value1", "key2": "modified", "key3": "value3"}
        
        delta = manager._calculate_delta(old_state, new_state)
        
        assert "key3" in delta.added_keys
        assert "key2" in delta.modified_keys
        assert len(delta.deleted_keys) == 0


class TestDeltaSnapshotManager:
    """Tests for delta snapshot manager."""

    def test_manager_creation(self):
        """Test creating delta snapshot manager."""
        manager = DeltaSnapshotManager("node1")
        assert manager.node_id == "node1"

    def test_create_delta_sequence(self):
        """Test creating delta sequence."""
        manager = DeltaSnapshotManager("node1")
        
        snapshots = [
            {"key1": "value1"},
            {"key1": "value1", "key2": "value2"},
            {"key1": "value1_modified", "key2": "value2"},
        ]
        
        success, seq_id, stats = manager.create_delta_sequence(snapshots, term=1, index=10)
        
        assert success
        assert seq_id is not None
        assert stats["num_deltas"] == 2

    def test_reconstruct_snapshot(self):
        """Test reconstructing snapshot from delta sequence."""
        manager = DeltaSnapshotManager("node1")
        
        snapshots = [
            {"key1": "v1"},
            {"key1": "v1", "key2": "v2"},
            {"key1": "v1_mod", "key2": "v2"},
        ]
        
        _, seq_id, _ = manager.create_delta_sequence(snapshots, 1, 10)
        
        # Reconstruct at delta index 1
        success, state = manager.reconstruct_snapshot(seq_id, 1)
        
        assert success
        assert state["key1"] == "v1"
        assert state["key2"] == "v2"

    def test_empty_snapshot_sequence(self):
        """Test handling empty snapshot sequence."""
        manager = DeltaSnapshotManager("node1")
        
        snapshots = [{"key1": "value1"}]
        
        success, _, _ = manager.create_delta_sequence(snapshots, 1, 10)
        
        assert not success


class TestIncrementalSnapshotIntegration:
    """Integration tests for incremental snapshots."""

    def test_full_then_multiple_incremental(self):
        """Test full snapshot followed by multiple incremental."""
        manager = IncrementalSnapshotManager("node1")
        
        # Full snapshot
        state = {"a": 1, "b": 2}
        full_id, _, _ = manager.create_full_snapshot(state, 1, 100)
        
        # Multiple incremental
        incremental_ids = []
        for i in range(3):
            state[f"key_{i}"] = i
            _, inc_id, _ = manager.create_incremental_snapshot(state, 1, 100 + i)
            incremental_ids.append(inc_id)
        
        # Restore final state
        success, restored = manager.restore_from_incremental(full_id, incremental_ids)
        
        assert success
        assert restored["a"] == 1
        assert restored["key_0"] == 0
        assert restored["key_2"] == 2

    def test_incremental_performance(self):
        """Test incremental snapshot performance."""
        manager = IncrementalSnapshotManager("node1")
        
        # Large state
        large_state = {f"key_{i}": f"value_{i}" for i in range(10000)}
        manager.create_full_snapshot(large_state, 1, 100)
        
        # Small modification
        large_state["key_5000"] = "modified"
        _, snap_id, stats = manager.create_incremental_snapshot(large_state, 1, 101)
        
        # Incremental should be much smaller
        assert stats["delta_size_bytes"] < len(json.dumps(large_state).encode())

    def test_snapshot_consolidation(self):
        """Test snapshot consolidation."""
        manager = IncrementalSnapshotManager("node1")
        
        state = {"key1": "value1"}
        manager.create_full_snapshot(state, 1, 10)
        
        # Create chain
        for i in range(12):
            state[f"key_{i}"] = f"value_{i}"
            manager.create_incremental_snapshot(state, 1, 10 + i)
        
        # Check consolidation is recommended
        assert manager.should_consolidate(max_chain_depth=10)
        
        # Consolidate
        snap_ids = list(manager.snapshots.keys())[1:]
        success, _, _ = manager.merge_incremental_snapshots(snap_ids)
        
        assert success


class TestSnapshotMetadata:
    """Tests for snapshot metadata."""

    def test_metadata_creation(self):
        """Test creating snapshot metadata."""
        from datetime import datetime
        
        metadata = SnapshotMetadata(
            snapshot_id="snap1",
            snapshot_type=SnapshotType.FULL,
            term=1,
            index=10,
            timestamp=datetime.now(),
        )
        
        assert metadata.snapshot_id == "snap1"
        assert metadata.snapshot_type == SnapshotType.FULL

    def test_metadata_incremental(self):
        """Test incremental metadata."""
        from datetime import datetime
        
        metadata = SnapshotMetadata(
            snapshot_id="delta1",
            snapshot_type=SnapshotType.INCREMENTAL,
            term=1,
            index=20,
            timestamp=datetime.now(),
            base_snapshot_id="snap1",
        )
        
        assert metadata.snapshot_type == SnapshotType.INCREMENTAL
        assert metadata.base_snapshot_id == "snap1"


import json
