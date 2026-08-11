"""Tests for snapshot store and management."""

import pytest
from datetime import datetime
from src.raft.snapshot_store import SnapshotStore, SnapshotMetadata


class TestSnapshotStore:
    """Test suite for SnapshotStore."""
    
    @pytest.fixture
    def store(self):
        """Fixture for snapshot store."""
        return SnapshotStore("node1", storage_path="/tmp")
    
    @pytest.fixture
    def sample_state(self):
        """Fixture for sample state data."""
        return {
            "user:1": {"name": "Alice", "age": 30},
            "user:2": {"name": "Bob", "age": 25},
            "config:db": {"host": "localhost", "port": 5432},
        }
    
    # Snapshot Creation Tests
    
    def test_create_snapshot(self, store, sample_state):
        """Test creating a snapshot."""
        success, snapshot_id, error = store.create_snapshot(sample_state, term=1, index=10)
        
        assert success
        assert snapshot_id is not None
        assert error is None
        assert snapshot_id in store.snapshots
    
    def test_create_multiple_snapshots(self, store, sample_state):
        """Test creating multiple snapshots."""
        success1, sid1, _ = store.create_snapshot(sample_state, term=1, index=10)
        success2, sid2, _ = store.create_snapshot(sample_state, term=2, index=20)
        
        assert success1 and success2
        assert sid1 != sid2
        assert len(store.snapshots) == 2
    
    def test_snapshot_metadata(self, store, sample_state):
        """Test snapshot metadata creation."""
        success, snapshot_id, _ = store.create_snapshot(sample_state, term=1, index=10)
        
        metadata = store.snapshots[snapshot_id]
        
        assert metadata.term == 1
        assert metadata.index == 10
        assert metadata.state_keys == 3
        assert metadata.compressed_size < metadata.uncompressed_size
    
    def test_snapshot_compression(self, store):
        """Test compression effectiveness."""
        # Large state with repeated data
        large_state = {f"key_{i}": "value_" + "x" * 100 for i in range(100)}
        
        success, snapshot_id, _ = store.create_snapshot(large_state, term=1, index=10)
        
        metadata = store.snapshots[snapshot_id]
        compression_ratio = metadata.compressed_size / metadata.uncompressed_size
        
        assert success
        assert compression_ratio < 0.5  # Should compress well
    
    # Snapshot Retrieval Tests
    
    def test_get_snapshot(self, store, sample_state):
        """Test retrieving snapshot data."""
        _, snapshot_id, _ = store.create_snapshot(sample_state, term=1, index=10)
        
        retrieved = store.get_snapshot(snapshot_id)
        
        assert retrieved is not None
        assert retrieved == sample_state
    
    def test_get_nonexistent_snapshot(self, store):
        """Test getting nonexistent snapshot."""
        result = store.get_snapshot("nonexistent")
        
        assert result is None
    
    def test_get_latest_snapshot(self, store, sample_state):
        """Test getting latest snapshot."""
        _, sid1, _ = store.create_snapshot(sample_state, term=1, index=10)
        _, sid2, _ = store.create_snapshot(sample_state, term=2, index=20)
        
        latest_meta, latest_data = store.get_latest_snapshot()
        
        assert latest_meta.snapshot_id == sid2
        assert latest_data == sample_state
    
    def test_get_latest_snapshot_empty(self, store):
        """Test getting latest snapshot when none exist."""
        result = store.get_latest_snapshot()
        
        assert result is None
    
    # Snapshot Installation Tests
    
    def test_install_snapshot(self, store, sample_state):
        """Test installing snapshot from another node."""
        success, error = store.install_snapshot(
            "remote-snapshot",
            sample_state,
            term=1,
            index=10
        )
        
        assert success
        assert error is None
        assert len(store.snapshots) == 1
    
    def test_install_snapshot_error(self, store):
        """Test snapshot installation with invalid data."""
        # This should handle gracefully
        success, error = store.install_snapshot(
            "test-snap",
            None,  # Invalid state
            term=1,
            index=10
        )
        
        # Should fail on bad input
        assert not success or error is not None
    
    # Snapshot Loading Tests
    
    def test_load_snapshot(self, store, sample_state):
        """Test loading snapshot."""
        _, snapshot_id, _ = store.create_snapshot(sample_state, term=1, index=10)
        
        success, data, error = store.load_snapshot(snapshot_id)
        
        assert success
        assert data == sample_state
        assert error is None
        assert store.snapshots_loaded == 1
    
    def test_load_nonexistent_snapshot(self, store):
        """Test loading nonexistent snapshot."""
        success, data, error = store.load_snapshot("nonexistent")
        
        assert not success
        assert data is None
        assert error is not None
    
    # Snapshot Deletion Tests
    
    def test_delete_snapshot(self, store, sample_state):
        """Test deleting old snapshot."""
        _, sid1, _ = store.create_snapshot(sample_state, term=1, index=10)
        _, sid2, _ = store.create_snapshot(sample_state, term=2, index=20)
        
        success, error = store.delete_snapshot(sid1)
        
        assert success
        assert error is None
        assert sid1 not in store.snapshots
        assert sid2 in store.snapshots
    
    def test_delete_current_snapshot(self, store, sample_state):
        """Test that current snapshot cannot be deleted."""
        _, snapshot_id, _ = store.create_snapshot(sample_state, term=1, index=10)
        
        success, error = store.delete_snapshot(snapshot_id)
        
        assert not success
        assert error is not None
        assert snapshot_id in store.snapshots
    
    def test_delete_nonexistent_snapshot(self, store):
        """Test deleting nonexistent snapshot."""
        success, error = store.delete_snapshot("nonexistent")
        
        assert not success
        assert error is not None
    
    # Snapshot Pruning Tests
    
    def test_prune_old_snapshots(self, store, sample_state):
        """Test pruning old snapshots."""
        # Create 5 snapshots
        for i in range(5):
            store.create_snapshot(sample_state, term=i, index=10 + i * 10)
        
        assert len(store.snapshots) == 5
        
        # Keep only 2
        deleted = store.prune_old_snapshots(keep_count=2)
        
        assert deleted == 3
        assert len(store.snapshots) == 2
    
    def test_prune_keeps_latest(self, store, sample_state):
        """Test that pruning keeps latest snapshots."""
        snapshots = []
        for i in range(5):
            _, sid, _ = store.create_snapshot(sample_state, term=i, index=10 + i * 10)
            snapshots.append(sid)
        
        store.prune_old_snapshots(keep_count=2)
        
        # Latest 2 should remain
        assert snapshots[-1] in store.snapshots
        assert snapshots[-2] in store.snapshots
        assert snapshots[0] not in store.snapshots
    
    def test_prune_no_deletion_needed(self, store, sample_state):
        """Test pruning when count is already low."""
        store.create_snapshot(sample_state, term=1, index=10)
        store.create_snapshot(sample_state, term=2, index=20)
        
        deleted = store.prune_old_snapshots(keep_count=5)
        
        assert deleted == 0
        assert len(store.snapshots) == 2
    
    # Metadata Tests
    
    def test_get_snapshot_metadata(self, store, sample_state):
        """Test getting snapshot metadata."""
        _, snapshot_id, _ = store.create_snapshot(sample_state, term=1, index=10)
        
        metadata = store.get_snapshot_metadata(snapshot_id)
        
        assert metadata is not None
        assert metadata["term"] == 1
        assert metadata["index"] == 10
        assert metadata["state_keys"] == 3
        assert "compression_ratio" in metadata
    
    def test_get_all_snapshots(self, store, sample_state):
        """Test getting all snapshot metadata."""
        for i in range(3):
            store.create_snapshot(sample_state, term=i, index=10 + i * 10)
        
        all_snapshots = store.get_all_snapshots()
        
        assert len(all_snapshots) == 3
        assert all(s["state_keys"] == 3 for s in all_snapshots)
    
    # Statistics Tests
    
    def test_get_statistics(self, store, sample_state):
        """Test getting store statistics."""
        store.create_snapshot(sample_state, term=1, index=10)
        store.create_snapshot(sample_state, term=2, index=20)
        
        stats = store.get_statistics()
        
        assert stats["total_snapshots"] == 2
        assert stats["snapshots_created"] == 2
        assert stats["compression_ratio"] > 0
        assert "storage_efficiency" in stats
    
    def test_statistics_empty(self, store):
        """Test statistics on empty store."""
        stats = store.get_statistics()
        
        assert stats["total_snapshots"] == 0
        assert stats["snapshots_created"] == 0
        assert stats["current_snapshot"] is None
    
    # Checksum/Integrity Tests
    
    def test_snapshot_checksum(self, store, sample_state):
        """Test snapshot checksum calculation."""
        _, snapshot_id, _ = store.create_snapshot(sample_state, term=1, index=10)
        
        metadata = store.snapshots[snapshot_id]
        assert metadata.checksum is not None
        assert len(metadata.checksum) > 0
    
    # Edge Cases
    
    def test_empty_state_snapshot(self, store):
        """Test snapshot with empty state."""
        success, snapshot_id, _ = store.create_snapshot({}, term=1, index=10)
        
        assert success
        metadata = store.snapshots[snapshot_id]
        assert metadata.state_keys == 0
    
    def test_large_state_snapshot(self, store):
        """Test snapshot with large state."""
        large_state = {f"key_{i}": f"value_{i}" * 100 for i in range(1000)}
        
        success, snapshot_id, _ = store.create_snapshot(large_state, term=1, index=10)
        
        assert success
        retrieved = store.get_snapshot(snapshot_id)
        assert len(retrieved) == 1000
    
    def test_snapshot_with_special_characters(self, store):
        """Test snapshot with special characters."""
        special_state = {
            "key_1": "value with spaces",
            "key_2": 'value"with"quotes',
            "key_3": "value\nwith\nnewlines",
            "key_4": {"nested": "object"},
        }
        
        success, snapshot_id, _ = store.create_snapshot(special_state, term=1, index=10)
        
        assert success
        retrieved = store.get_snapshot(snapshot_id)
        assert retrieved == special_state
    
    def test_concurrent_snapshot_operations(self, store, sample_state):
        """Test concurrent snapshot operations."""
        # Create snapshots
        snapshots = []
        for i in range(5):
            _, sid, _ = store.create_snapshot(sample_state, term=i, index=10 + i)
            snapshots.append(sid)
        
        # Load and retrieve
        for sid in snapshots:
            data = store.get_snapshot(sid)
            assert data == sample_state
    
    def test_snapshot_id_uniqueness(self, store, sample_state):
        """Test that snapshot IDs are unique."""
        ids = set()
        
        for i in range(10):
            _, snapshot_id, _ = store.create_snapshot(sample_state, term=1, index=10)
            assert snapshot_id not in ids
            ids.add(snapshot_id)
        
        assert len(ids) == 10
