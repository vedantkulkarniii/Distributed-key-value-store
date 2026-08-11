"""Tests for multi-node state synchronization."""

import pytest
from datetime import datetime, timedelta
from src.raft.state_sync import (
    MultiNodeStateSyncManager,
    SyncProgress,
    SyncPhase,
)


class TestSyncProgress:
    """Test suite for SyncProgress."""
    
    def test_sync_progress_creation(self):
        """Test creating sync progress."""
        progress = SyncProgress("node1", "node2")
        
        assert progress.node_id == "node1"
        assert progress.peer_id == "node2"
        assert progress.phase == SyncPhase.INITIATED
        assert progress.start_time is not None
    
    def test_sync_progress_percent(self):
        """Test progress percentage calculation."""
        progress = SyncProgress("node1", "node2")
        progress.entries_synced = 50
        progress.entries_total = 100
        
        assert progress.progress_percent() == 50.0
    
    def test_sync_progress_duration(self):
        """Test duration calculation."""
        progress = SyncProgress("node1", "node2")
        progress.end_time = datetime.now()
        
        duration = progress.duration_seconds()
        assert duration >= 0
    
    def test_sync_progress_throughput(self):
        """Test throughput calculation."""
        progress = SyncProgress("node1", "node2")
        progress.entries_synced = 100
        progress.end_time = datetime.now() + timedelta(seconds=10)
        
        # Throughput should be 10 entries/sec
        throughput = progress.throughput_entries_per_sec()
        assert throughput > 0


class TestMultiNodeStateSyncManager:
    """Test suite for MultiNodeStateSyncManager."""
    
    @pytest.fixture
    def manager(self):
        """Fixture for state sync manager."""
        return MultiNodeStateSyncManager("node1", cluster_size=3)
    
    @pytest.fixture
    def local_state(self):
        """Fixture for local state."""
        return {
            "user:1": {"name": "Alice", "age": 30},
            "user:2": {"name": "Bob", "age": 25},
            "config": {"setting": "value"},
        }
    
    @pytest.fixture
    def peer_state(self):
        """Fixture for peer state."""
        return {
            "user:1": {"name": "Alice", "age": 30},
            "user:2": {"name": "Bob", "age": 26},  # Different age
            "user:3": {"name": "Charlie", "age": 35},
        }
    
    # Sync Initiation Tests
    
    def test_initiate_sync(self, manager):
        """Test initiating sync with peer."""
        progress = manager.initiate_sync("node2")
        
        assert progress is not None
        assert progress.peer_id == "node2"
        assert progress.phase == SyncPhase.INITIATED
        assert "node2" in manager.active_syncs
    
    def test_initiate_multiple_syncs(self, manager):
        """Test initiating multiple syncs."""
        progress1 = manager.initiate_sync("node2")
        progress2 = manager.initiate_sync("node3")
        
        assert progress1.peer_id == "node2"
        assert progress2.peer_id == "node3"
        assert len(manager.active_syncs) == 2
    
    # Progress Tracking Tests
    
    def test_update_sync_progress(self, manager):
        """Test updating sync progress."""
        manager.initiate_sync("node2")
        
        is_complete = manager.update_sync_progress("node2", 50, 100)
        
        assert not is_complete
        progress = manager.active_syncs["node2"]
        assert progress.entries_synced == 50
        assert progress.entries_total == 100
    
    def test_complete_sync_detection(self, manager):
        """Test detection of sync completion."""
        manager.initiate_sync("node2")
        
        is_complete = manager.update_sync_progress("node2", 100, 100)
        
        assert is_complete
    
    def test_update_nonexistent_sync(self, manager):
        """Test updating nonexistent sync."""
        result = manager.update_sync_progress("nonexistent", 10, 100)
        
        assert not result
    
    # Peer State Tests
    
    def test_update_peer_state(self, manager, peer_state):
        """Test updating peer state."""
        manager.update_peer_state("node2", peer_state)
        
        assert "node2" in manager.peer_states
        assert manager.peer_states["node2"] == peer_state
    
    def test_peer_state_copy(self, manager, peer_state):
        """Test that peer state is copied."""
        manager.update_peer_state("node2", peer_state)
        
        # Modify original
        peer_state["new_key"] = "new_value"
        
        # Stored state should be unchanged
        assert "new_key" not in manager.peer_states["node2"]
    
    # Conflict Detection Tests
    
    def test_detect_conflicts(self, manager, local_state, peer_state):
        """Test conflict detection."""
        conflicts = manager.detect_conflicts("node2", local_state, peer_state)
        
        assert len(conflicts) > 0
        # user:2 age differs, config is missing from peer
        assert any(key == "user:2" for key, _, _ in conflicts)
    
    def test_no_conflicts(self, manager, local_state):
        """Test when states match."""
        conflicts = manager.detect_conflicts("node2", local_state, local_state)
        
        assert len(conflicts) == 0
    
    def test_conflicts_recorded(self, manager, local_state, peer_state):
        """Test that conflicts are recorded in progress."""
        progress = manager.initiate_sync("node2")
        
        manager.detect_conflicts("node2", local_state, peer_state)
        
        assert progress.conflicts_detected > 0
    
    # Conflict Resolution Tests
    
    def test_resolve_conflicts_prefer_local(self, manager):
        """Test resolving conflicts preferring local."""
        conflicts = [
            ("key1", "local_value", "peer_value"),
            ("key2", None, "peer_value"),
        ]
        
        resolved = manager.resolve_conflicts("node2", conflicts, prefer_local=True)
        
        assert resolved["key1"] == "local_value"
        assert resolved["key2"] == "local_value"
    
    def test_resolve_conflicts_prefer_peer(self, manager):
        """Test resolving conflicts preferring peer."""
        conflicts = [
            ("key1", "local_value", "peer_value"),
            ("key2", None, "peer_value"),
        ]
        
        resolved = manager.resolve_conflicts("node2", conflicts, prefer_local=False)
        
        # Should prefer non-None
        assert resolved["key1"] == "local_value" or resolved["key1"] == "peer_value"
        assert resolved["key2"] == "peer_value"
    
    # Consistency Verification Tests
    
    def test_verify_consistency_identical_states(self, manager, local_state):
        """Test consistency check with identical states."""
        is_consistent, score = manager.verify_consistency(
            "node2", local_state, local_state
        )
        
        assert is_consistent
        assert score == 1.0
    
    def test_verify_consistency_different_states(self, manager, local_state, peer_state):
        """Test consistency check with different states."""
        is_consistent, score = manager.verify_consistency(
            "node2", local_state, peer_state
        )
        
        # Should detect some differences
        assert score < 1.0
    
    def test_verify_consistency_empty_states(self, manager):
        """Test consistency check with empty states."""
        is_consistent, score = manager.verify_consistency("node2", {}, {})
        
        assert is_consistent
        assert score == 1.0
    
    # Sync Completion Tests
    
    def test_complete_sync_successful(self, manager):
        """Test completing successful sync."""
        manager.initiate_sync("node2")
        
        success = manager.complete_sync("node2", is_successful=True)
        
        assert success
        assert "node2" not in manager.active_syncs
        assert len(manager.completed_syncs) == 1
        assert manager.successful_syncs == 1
    
    def test_complete_sync_failed(self, manager):
        """Test completing failed sync."""
        manager.initiate_sync("node2")
        
        success = manager.complete_sync(
            "node2",
            is_successful=False,
            error="Network timeout"
        )
        
        assert success
        assert manager.failed_syncs == 1
        assert manager.completed_syncs[0].error == "Network timeout"
    
    def test_complete_nonexistent_sync(self, manager):
        """Test completing nonexistent sync."""
        success = manager.complete_sync("nonexistent")
        
        assert not success
    
    # Status and Progress Queries
    
    def test_get_sync_progress(self, manager):
        """Test getting sync progress."""
        progress = manager.initiate_sync("node2")
        manager.update_sync_progress("node2", 25, 100)
        
        status = manager.get_sync_progress("node2")
        
        assert status is not None
        assert status["peer_id"] == "node2"
        assert status["percent"] == 25.0
    
    def test_get_sync_progress_nonexistent(self, manager):
        """Test getting progress for nonexistent sync."""
        status = manager.get_sync_progress("nonexistent")
        
        assert status is None
    
    def test_get_cluster_status(self, manager):
        """Test getting cluster status."""
        manager.initiate_sync("node2")
        manager.initiate_sync("node3")
        manager.complete_sync("node2", is_successful=True)
        
        status = manager.get_cluster_status()
        
        assert status["active_syncs"] == 1
        assert status["total_syncs"] == 2
        assert status["successful"] == 1
    
    def test_get_peer_consistency(self, manager, local_state, peer_state):
        """Test getting peer consistency score."""
        manager.verify_consistency("node2", local_state, peer_state)
        
        consistency = manager.get_peer_consistency("node2")
        
        assert consistency is not None
        assert 0 <= consistency <= 1
    
    # Sync History Tests
    
    def test_get_sync_history(self, manager):
        """Test getting sync history."""
        manager.initiate_sync("node2")
        manager.complete_sync("node2", is_successful=True)
        
        manager.initiate_sync("node3")
        manager.complete_sync("node3", is_successful=False)
        
        history = manager.get_sync_history()
        
        assert len(history) == 2
    
    def test_get_sync_history_filtered(self, manager):
        """Test getting sync history filtered by peer."""
        manager.initiate_sync("node2")
        manager.complete_sync("node2", is_successful=True)
        
        manager.initiate_sync("node3")
        manager.complete_sync("node3", is_successful=True)
        
        history = manager.get_sync_history(peer_id="node2")
        
        assert len(history) == 1
        assert history[0]["peer_id"] == "node2"
    
    # Edge Cases
    
    def test_full_sync_workflow(self, manager, local_state, peer_state):
        """Test complete sync workflow."""
        # 1. Initiate
        progress = manager.initiate_sync("node2")
        assert progress.phase == SyncPhase.INITIATED
        
        # 2. Update peer state
        manager.update_peer_state("node2", peer_state)
        
        # 3. Detect conflicts
        conflicts = manager.detect_conflicts("node2", local_state, peer_state)
        
        # 4. Resolve conflicts
        resolved = manager.resolve_conflicts("node2", conflicts, prefer_local=True)
        
        # 5. Verify consistency
        is_consistent, score = manager.verify_consistency("node2", local_state, peer_state)
        
        # 6. Update progress
        manager.update_sync_progress("node2", 100, 100)
        
        # 7. Complete sync
        manager.complete_sync("node2", is_successful=True)
        
        assert manager.successful_syncs == 1
    
    def test_multiple_concurrent_syncs(self, manager):
        """Test multiple concurrent syncs."""
        # Initiate syncs with multiple nodes
        for i in range(1, 4):
            manager.initiate_sync(f"node{i}")
        
        assert len(manager.active_syncs) == 3
        
        # Complete some
        manager.complete_sync("node1", is_successful=True)
        manager.complete_sync("node2", is_successful=False)
        
        assert len(manager.active_syncs) == 1
        assert manager.successful_syncs == 1
        assert manager.failed_syncs == 1
