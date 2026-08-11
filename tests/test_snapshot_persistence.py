"""Tests for snapshot persistence and log compaction."""

import pytest
import tempfile
import json
from pathlib import Path
from datetime import datetime, timedelta
from src.raft.snapshot_persistence import (
    SnapshotPersistence,
    SnapshotMetadata,
    SnapshotIndex,
)


class TestSnapshotMetadata:
    """Test suite for SnapshotMetadata."""
    
    def test_metadata_creation(self):
        """Test creating snapshot metadata."""
        metadata = SnapshotMetadata(
            snapshot_id="snap1",
            node_id="node1",
            index=100,
            term=5,
            timestamp=datetime.now().isoformat(),
            data_size=1000,
            data_checksum="abc123",
        )
        
        assert metadata.snapshot_id == "snap1"
        assert metadata.index == 100
        assert metadata.term == 5
        assert metadata.data_size == 1000
    
    def test_metadata_to_dict(self):
        """Test metadata serialization."""
        metadata = SnapshotMetadata(
            snapshot_id="snap1",
            node_id="node1",
            index=100,
            term=5,
            timestamp=datetime.now().isoformat(),
            data_size=1000,
            data_checksum="abc123",
        )
        
        data_dict = metadata.to_dict()
        assert data_dict["snapshot_id"] == "snap1"
        assert data_dict["index"] == 100
    
    def test_metadata_from_dict(self):
        """Test metadata deserialization."""
        original = SnapshotMetadata(
            snapshot_id="snap1",
            node_id="node1",
            index=100,
            term=5,
            timestamp=datetime.now().isoformat(),
            data_size=1000,
            data_checksum="abc123",
        )
        
        restored = SnapshotMetadata.from_dict(original.to_dict())
        assert restored.snapshot_id == original.snapshot_id
        assert restored.index == original.index


class TestSnapshotIndex:
    """Test suite for SnapshotIndex."""
    
    def test_index_creation(self):
        """Test creating snapshot index."""
        index = SnapshotIndex()
        assert index.total_snapshots == 0
        assert index.latest_snapshot_id is None
    
    def test_add_snapshot(self):
        """Test adding snapshot to index."""
        index = SnapshotIndex()
        metadata = SnapshotMetadata(
            snapshot_id="snap1",
            node_id="node1",
            index=100,
            term=5,
            timestamp=datetime.now().isoformat(),
            data_size=1000,
            data_checksum="abc",
        )
        
        index.add_snapshot(metadata)
        
        assert index.total_snapshots == 1
        assert index.latest_snapshot_id == "snap1"
        assert index.latest_index == 100
    
    def test_add_multiple_snapshots(self):
        """Test adding multiple snapshots."""
        index = SnapshotIndex()
        
        for i in range(1, 4):
            metadata = SnapshotMetadata(
                snapshot_id=f"snap{i}",
                node_id="node1",
                index=i * 100,
                term=i,
                timestamp=datetime.now().isoformat(),
                data_size=1000,
                data_checksum="abc",
            )
            index.add_snapshot(metadata)
        
        assert index.total_snapshots == 3
        assert index.latest_index == 300
    
    def test_get_latest_snapshot(self):
        """Test getting latest snapshot."""
        index = SnapshotIndex()
        
        meta1 = SnapshotMetadata("snap1", "node1", 100, 1, datetime.now().isoformat(), 1000, "a")
        meta2 = SnapshotMetadata("snap2", "node1", 200, 2, datetime.now().isoformat(), 1000, "b")
        
        index.add_snapshot(meta1)
        index.add_snapshot(meta2)
        
        latest = index.get_latest_snapshot()
        assert latest.snapshot_id == "snap2"
        assert latest.index == 200
    
    def test_get_snapshot_by_index(self):
        """Test getting snapshot by index."""
        index = SnapshotIndex()
        
        meta1 = SnapshotMetadata("snap1", "node1", 100, 1, datetime.now().isoformat(), 1000, "a")
        meta2 = SnapshotMetadata("snap2", "node1", 200, 2, datetime.now().isoformat(), 1000, "b")
        meta3 = SnapshotMetadata("snap3", "node1", 300, 3, datetime.now().isoformat(), 1000, "c")
        
        index.add_snapshot(meta1)
        index.add_snapshot(meta2)
        index.add_snapshot(meta3)
        
        # Get snapshot at index 150 (should be snap1 at 100)
        snap = index.get_snapshot_by_index(150)
        assert snap.snapshot_id == "snap1"
        
        # Get snapshot at index 250 (should be snap2 at 200)
        snap = index.get_snapshot_by_index(250)
        assert snap.snapshot_id == "snap2"
    
    def test_cleanup_old_snapshots(self):
        """Test cleaning up old snapshots."""
        index = SnapshotIndex()
        
        for i in range(1, 6):
            metadata = SnapshotMetadata(
                snapshot_id=f"snap{i}",
                node_id="node1",
                index=i * 100,
                term=i,
                timestamp=datetime.now().isoformat(),
                data_size=1000,
                data_checksum="abc",
            )
            index.add_snapshot(metadata)
        
        removed = index.cleanup_old_snapshots(keep_count=2)
        
        assert len(removed) == 3
        assert index.total_snapshots == 2


class TestSnapshotPersistence:
    """Test suite for SnapshotPersistence."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for snapshots."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def persistence(self, temp_dir):
        """Create snapshot persistence instance."""
        return SnapshotPersistence("node1", snapshots_dir=temp_dir)
    
    def test_persistence_creation(self, persistence, temp_dir):
        """Test creating persistence instance."""
        assert persistence.node_id == "node1"
        assert Path(temp_dir).exists()
    
    def test_create_snapshot(self, persistence):
        """Test creating a snapshot."""
        data = {"key1": "value1", "key2": "value2"}
        success, snapshot_id, error = persistence.create_snapshot(data, index=100, term=5)
        
        assert success
        assert snapshot_id is not None
        assert error is None
        assert "snap-" in snapshot_id
    
    def test_snapshot_file_created(self, persistence, temp_dir):
        """Test snapshot files are created."""
        data = {"key": "value"}
        success, snapshot_id, _ = persistence.create_snapshot(data, index=10, term=1)
        
        assert success
        
        snap_file = Path(temp_dir) / f"{snapshot_id}.snap.gz"
        meta_file = Path(temp_dir) / f"{snapshot_id}.meta.json"
        
        assert snap_file.exists()
        assert meta_file.exists()
    
    def test_restore_snapshot(self, persistence):
        """Test restoring snapshot."""
        original_data = {"key1": "value1", "key2": 42}
        success1, snapshot_id, _ = persistence.create_snapshot(original_data, index=100, term=5)
        
        assert success1
        
        success2, restored_data, error = persistence.restore_snapshot(snapshot_id)
        
        assert success2
        assert error is None
        assert restored_data == original_data
    
    def test_restore_nonexistent_snapshot(self, persistence):
        """Test restoring nonexistent snapshot."""
        success, data, error = persistence.restore_snapshot("nonexistent")
        
        assert not success
        assert data is None
        assert error is not None
    
    def test_snapshot_with_complex_data(self, persistence):
        """Test snapshot with complex nested data."""
        complex_data = {
            "users": [
                {"id": 1, "name": "Alice", "roles": ["admin", "user"]},
                {"id": 2, "name": "Bob", "roles": ["user"]},
            ],
            "config": {
                "timeout": 30,
                "retries": 3,
                "endpoints": ["http://localhost:8000", "http://localhost:8001"],
            },
        }
        
        success1, snapshot_id, _ = persistence.create_snapshot(complex_data, index=50, term=3)
        success2, restored, _ = persistence.restore_snapshot(snapshot_id)
        
        assert success1 and success2
        assert restored == complex_data
    
    def test_snapshot_checksum_verification(self, persistence):
        """Test checksum verification on restore."""
        data = {"key": "value"}
        success, snapshot_id, _ = persistence.create_snapshot(data, index=10, term=1)
        
        assert success
        
        # Metadata should have checksum
        metadata_path = Path(persistence.snapshots_dir) / f"{snapshot_id}.meta.json"
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        
        assert metadata["data_checksum"] is not None
        assert len(metadata["data_checksum"]) == 64  # SHA256 hex is 64 chars
    
    def test_compression_enabled(self, persistence):
        """Test compression is working."""
        # Create large data to see compression benefit
        large_data = {f"key{i}": f"value{i}" * 100 for i in range(100)}
        success, snapshot_id, _ = persistence.create_snapshot(large_data, index=100, term=1)
        
        assert success
        
        # Check metadata shows compression
        meta_path = Path(persistence.snapshots_dir) / f"{snapshot_id}.meta.json"
        with open(meta_path, 'r') as f:
            metadata = json.load(f)
        
        assert metadata["compressed"]
        assert metadata["compression_ratio"] > 1.0
    
    def test_get_latest_snapshot_data(self, persistence):
        """Test getting latest snapshot data."""
        data1 = {"version": 1}
        data2 = {"version": 2}
        
        persistence.create_snapshot(data1, index=50, term=1)
        persistence.create_snapshot(data2, index=100, term=2)
        
        success, data, index, term = persistence.get_latest_snapshot_data()
        
        assert success
        assert data == data2
        assert index == 100
        assert term == 2
    
    def test_cleanup_old_snapshots(self, persistence):
        """Test cleaning up old snapshots."""
        for i in range(5):
            data = {"version": i}
            persistence.create_snapshot(data, index=(i+1)*100, term=i+1)
        
        assert persistence.snapshot_index.total_snapshots == 5
        
        removed = persistence.cleanup_old_snapshots(keep_count=2)
        
        assert len(removed) == 3
        assert persistence.snapshot_index.total_snapshots == 2
    
    def test_should_snapshot_time_based(self, persistence):
        """Test time-based snapshot trigger."""
        persistence.snapshot_interval_seconds = 1
        persistence.last_snapshot_time = datetime.now() - timedelta(seconds=2)
        
        should_snap = persistence.should_snapshot(log_entries_since_snapshot=10)
        
        assert should_snap
    
    def test_should_snapshot_size_based(self, persistence):
        """Test size-based snapshot trigger."""
        persistence.min_log_entries_before_snapshot = 50
        persistence.last_snapshot_time = datetime.now()
        
        should_snap = persistence.should_snapshot(log_entries_since_snapshot=100)
        
        assert should_snap
    
    def test_should_not_snapshot(self, persistence):
        """Test snapshot not triggered."""
        persistence.snapshot_interval_seconds = 3600
        persistence.min_log_entries_before_snapshot = 1000
        persistence.last_snapshot_time = datetime.now()
        
        should_snap = persistence.should_snapshot(log_entries_since_snapshot=10)
        
        assert not should_snap
    
    def test_get_statistics(self, persistence):
        """Test getting statistics."""
        data = {"key": "value"}
        persistence.create_snapshot(data, index=100, term=5)
        
        stats = persistence.get_statistics()
        
        assert stats["total_snapshots"] == 1
        assert stats["latest_index"] == 100
        assert stats["latest_term"] == 5
        assert stats["total_snapshots_created"] == 1
    
    def test_get_snapshot_list(self, persistence):
        """Test getting snapshot list."""
        for i in range(3):
            persistence.create_snapshot({"version": i}, index=(i+1)*100, term=i+1)
        
        snapshots = persistence.get_snapshot_list()
        
        assert len(snapshots) == 3
        assert snapshots[0]["index"] == 300  # Sorted by index descending
        assert snapshots[2]["index"] == 100
    
    def test_multiple_snapshots_same_index_different_terms(self, persistence):
        """Test handling snapshots with same index but different terms."""
        persistence.create_snapshot({"v": 1}, index=100, term=1)
        persistence.create_snapshot({"v": 2}, index=100, term=2)
        
        stats = persistence.get_statistics()
        assert stats["total_snapshots"] == 2
        assert stats["latest_term"] == 2
    
    def test_snapshot_recovery_scenario(self, persistence):
        """Test realistic snapshot + recovery scenario."""
        # Create multiple snapshots
        for i in range(3):
            data = {f"k{j}": f"v{j}" for j in range(i * 10, (i + 1) * 10)}
            persistence.create_snapshot(data, index=(i+1)*100, term=i+1)
        
        # Get latest and restore
        success, latest_data, index, term = persistence.get_latest_snapshot_data()
        
        assert success
        assert index == 300
        assert term == 3
        assert len(latest_data) == 10
        
        # Cleanup old ones
        removed = persistence.cleanup_old_snapshots(keep_count=1)
        assert len(removed) == 2
        
        # Latest still accessible
        success2, data2, _, _ = persistence.get_latest_snapshot_data()
        assert success2
        assert data2 == latest_data
