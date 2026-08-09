"""Test suite for snapshot support and fast state transfer."""

import pytest
import time
from src.raft.snapshot import (
    SnapshotManager,
    SnapshotMetadata,
    SnapshotStatus,
    InstallSnapshotHandler,
)


class TestSnapshotMetadata:
    """Tests for SnapshotMetadata."""
    
    def test_initialization(self):
        """Test SnapshotMetadata initialization."""
        metadata = SnapshotMetadata(
            last_included_index=100,
            last_included_term=5,
            creation_timestamp=time.time(),
        )
        
        assert metadata.last_included_index == 100
        assert metadata.last_included_term == 5
        assert metadata.size_bytes == 0
        assert metadata.status == SnapshotStatus.PENDING
        assert metadata.checksum is None
    
    def test_metadata_with_checksum(self):
        """Test SnapshotMetadata with checksum."""
        metadata = SnapshotMetadata(
            last_included_index=100,
            last_included_term=5,
            creation_timestamp=time.time(),
            checksum="abc123",
        )
        
        assert metadata.checksum == "abc123"


class TestSnapshotManager:
    """Tests for SnapshotManager."""
    
    def test_initialization(self):
        """Test SnapshotManager initialization."""
        manager = SnapshotManager()
        
        assert manager.snapshots == {}
        assert manager.current_snapshot is None
        assert not manager.snapshot_in_progress
        assert manager.chunk_size == 64 * 1024
    
    def test_initialization_with_custom_size(self):
        """Test initialization with custom max size."""
        manager = SnapshotManager(max_snapshot_size=50 * 1024 * 1024)
        
        assert manager.max_snapshot_size == 50 * 1024 * 1024
    
    def test_create_snapshot_success(self):
        """Test successful snapshot creation."""
        manager = SnapshotManager()
        state_data = {"key1": "value1", "key2": "value2"}
        
        metadata = manager.create_snapshot(
            last_included_index=100,
            last_included_term=5,
            state_data=state_data,
        )
        
        assert metadata is not None
        assert metadata.last_included_index == 100
        assert metadata.last_included_term == 5
        assert metadata.status == SnapshotStatus.COMPLETE
        assert metadata.checksum is not None
    
    def test_create_snapshot_stores_metadata(self):
        """Test that create_snapshot stores metadata."""
        manager = SnapshotManager()
        state_data = {"key1": "value1"}
        
        metadata = manager.create_snapshot(
            last_included_index=100,
            last_included_term=5,
            state_data=state_data,
        )
        
        assert manager.current_snapshot == metadata
        assert manager.snapshots[100] == metadata
    
    def test_create_snapshot_too_large(self):
        """Test snapshot creation fails for oversized data."""
        manager = SnapshotManager(max_snapshot_size=100)
        large_data = {"data": "x" * 1000}
        
        metadata = manager.create_snapshot(
            last_included_index=100,
            last_included_term=5,
            state_data=large_data,
        )
        
        assert metadata is None
    
    def test_create_snapshot_in_progress(self):
        """Test that snapshot creation is prevented while one is in progress."""
        manager = SnapshotManager()
        manager.snapshot_in_progress = True
        
        metadata = manager.create_snapshot(
            last_included_index=100,
            last_included_term=5,
            state_data={"key": "value"},
        )
        
        assert metadata is None
    
    def test_get_current_snapshot(self):
        """Test retrieving the current snapshot."""
        manager = SnapshotManager()
        
        assert manager.get_current_snapshot() is None
        
        manager.create_snapshot(
            last_included_index=100,
            last_included_term=5,
            state_data={"key": "value"},
        )
        
        snapshot = manager.get_current_snapshot()
        assert snapshot is not None
        assert snapshot.last_included_index == 100
    
    def test_get_snapshot_by_index(self):
        """Test retrieving a snapshot by index."""
        manager = SnapshotManager()
        
        manager.create_snapshot(
            last_included_index=100,
            last_included_term=5,
            state_data={"key1": "value1"},
        )
        
        manager.create_snapshot(
            last_included_index=200,
            last_included_term=6,
            state_data={"key2": "value2"},
        )
        
        snapshot100 = manager.get_snapshot_by_index(100)
        assert snapshot100.last_included_index == 100
        
        snapshot200 = manager.get_snapshot_by_index(200)
        assert snapshot200.last_included_index == 200
        
        assert manager.get_snapshot_by_index(300) is None
    
    def test_should_take_snapshot_large_log(self):
        """Test snapshot determination for large logs."""
        manager = SnapshotManager()
        
        # Log size of 10MB should trigger snapshot
        assert manager.should_take_snapshot(
            log_size=10 * 1024 * 1024 + 1,
            log_entries=50000,
        )
    
    def test_should_take_snapshot_many_entries(self):
        """Test snapshot determination for many entries."""
        manager = SnapshotManager()
        
        # Many entries should trigger snapshot
        assert manager.should_take_snapshot(
            log_size=5 * 1024 * 1024,
            log_entries=100001,
        )
    
    def test_should_not_take_snapshot(self):
        """Test when snapshot should not be taken."""
        manager = SnapshotManager()
        
        assert not manager.should_take_snapshot(
            log_size=1 * 1024 * 1024,
            log_entries=10000,
        )
    
    def test_split_snapshot_into_chunks(self):
        """Test splitting snapshot data into chunks."""
        manager = SnapshotManager()
        manager.chunk_size = 100  # Use smaller chunks for testing
        
        snapshot_data = b"x" * 250
        chunks = manager.split_snapshot_into_chunks(snapshot_data)
        
        assert len(chunks) == 3
        assert len(chunks[0]) == 100
        assert len(chunks[1]) == 100
        assert len(chunks[2]) == 50
    
    def test_reassemble_snapshot(self):
        """Test reassembling chunks into snapshot."""
        manager = SnapshotManager()
        
        original_data = b"Hello World! This is a snapshot."
        chunks = [
            b"Hello ",
            b"World! ",
            b"This is a ",
            b"snapshot.",
        ]
        
        reassembled = manager.reassemble_snapshot(chunks)
        assert reassembled == original_data
    
    def test_split_and_reassemble_roundtrip(self):
        """Test splitting and reassembling produces original data."""
        manager = SnapshotManager()
        manager.chunk_size = 64
        
        original_data = b"x" * 200
        chunks = manager.split_snapshot_into_chunks(original_data)
        reassembled = manager.reassemble_snapshot(chunks)
        
        assert reassembled == original_data
    
    def test_verify_snapshot_integrity_valid(self):
        """Test verifying snapshot integrity with valid data."""
        manager = SnapshotManager()
        
        snapshot_data = b"snapshot data"
        import hashlib
        checksum = hashlib.md5(snapshot_data).hexdigest()
        
        assert manager.verify_snapshot_integrity(snapshot_data, checksum)
    
    def test_verify_snapshot_integrity_invalid(self):
        """Test verifying snapshot integrity with invalid data."""
        manager = SnapshotManager()
        
        snapshot_data = b"snapshot data"
        invalid_checksum = "invalid_checksum"
        
        assert not manager.verify_snapshot_integrity(snapshot_data, invalid_checksum)
    
    def test_get_snapshot_statistics_no_snapshots(self):
        """Test snapshot statistics with no snapshots."""
        manager = SnapshotManager()
        
        stats = manager.get_snapshot_statistics()
        
        assert stats["total_snapshots"] == 0
        assert stats["current_snapshot_index"] is None
        assert stats["current_snapshot_size"] == 0
    
    def test_get_snapshot_statistics_with_snapshots(self):
        """Test snapshot statistics with existing snapshots."""
        manager = SnapshotManager()
        
        manager.create_snapshot(
            last_included_index=100,
            last_included_term=5,
            state_data={"data": "value"},
        )
        
        stats = manager.get_snapshot_statistics()
        
        assert stats["total_snapshots"] == 1
        assert stats["current_snapshot_index"] == 100
        assert stats["current_snapshot_size"] > 0
    
    def test_multiple_snapshots_tracking(self):
        """Test tracking multiple snapshots."""
        manager = SnapshotManager()
        
        for i in range(1, 4):
            manager.create_snapshot(
                last_included_index=i * 100,
                last_included_term=i,
                state_data={"index": i * 100},
            )
        
        assert len(manager.snapshots) == 3
        assert manager.current_snapshot.last_included_index == 300


class TestInstallSnapshotHandler:
    """Tests for InstallSnapshotHandler interface."""
    
    def test_interface_methods_exist(self):
        """Test that all interface methods are defined."""
        # This tests the interface contract
        handler = InstallSnapshotHandler()
        
        assert hasattr(handler, "handle_install_snapshot")
        assert hasattr(handler, "snapshot_received")
        assert hasattr(handler, "can_accept_snapshot")
    
    def test_handle_install_snapshot_not_implemented(self):
        """Test that handle_install_snapshot raises NotImplementedError."""
        handler = InstallSnapshotHandler()
        
        with pytest.raises(NotImplementedError):
            handler.handle_install_snapshot(
                term=5,
                leader_id="leader1",
                last_included_index=100,
                last_included_term=5,
                offset=0,
                data=b"data",
                done=False,
            )
    
    def test_snapshot_received_not_implemented(self):
        """Test that snapshot_received raises NotImplementedError."""
        handler = InstallSnapshotHandler()
        
        with pytest.raises(NotImplementedError):
            handler.snapshot_received()
    
    def test_can_accept_snapshot_not_implemented(self):
        """Test that can_accept_snapshot raises NotImplementedError."""
        handler = InstallSnapshotHandler()
        
        with pytest.raises(NotImplementedError):
            handler.can_accept_snapshot()
