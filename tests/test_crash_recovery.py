"""Tests for crash recovery handler."""

import pytest
from datetime import datetime, timedelta
from src.raft.crash_recovery import CrashRecoveryHandler, RecoveryPhase
from src.raft.snapshot_store import SnapshotStore


class TestCrashRecoveryHandler:
    """Test suite for CrashRecoveryHandler."""
    
    @pytest.fixture
    def recovery_handler(self):
        """Fixture for recovery handler."""
        return CrashRecoveryHandler("node1")
    
    @pytest.fixture
    def snapshot_store(self):
        """Fixture for snapshot store."""
        return SnapshotStore("node1")
    
    @pytest.fixture
    def sample_state(self):
        """Fixture for sample state."""
        return {
            "user:1": {"name": "Alice", "age": 30},
            "user:2": {"name": "Bob", "age": 25},
        }
    
    @pytest.fixture
    def log_entries(self):
        """Fixture for log entries."""
        return [
            {"index": 1, "command": {"op": "SET", "key": "user:1", "value": {"name": "Alice", "age": 30}}},
            {"index": 2, "command": {"op": "SET", "key": "user:2", "value": {"name": "Bob", "age": 25}}},
            {"index": 3, "command": {"op": "SET", "key": "user:3", "value": {"name": "Charlie", "age": 35}}},
            {"index": 4, "command": {"op": "DELETE", "key": "user:2"}},
        ]
    
    # Snapshot Recovery Tests
    
    def test_recover_from_snapshot(self, recovery_handler, snapshot_store, sample_state):
        """Test recovery from snapshot."""
        snapshot_store.create_snapshot(sample_state, term=1, index=10)
        
        success, state, error = recovery_handler.recover_from_snapshot(
            snapshot_store, term=1, index=10
        )
        
        assert success
        assert state == sample_state
        assert error is None
        assert recovery_handler.recovery_stats.snapshots_loaded == 1
    
    def test_recover_no_snapshot(self, recovery_handler, snapshot_store):
        """Test recovery when no snapshots exist."""
        success, state, error = recovery_handler.recover_from_snapshot(
            snapshot_store, term=1, index=10
        )
        
        assert success
        assert state == {}
        assert error is None
    
    def test_recover_snapshot_newer_term(self, recovery_handler, snapshot_store, sample_state):
        """Test rejection of snapshot from newer term."""
        snapshot_store.create_snapshot(sample_state, term=5, index=50)
        
        success, state, error = recovery_handler.recover_from_snapshot(
            snapshot_store, term=1, index=10  # Current term is lower
        )
        
        assert not success
        assert error is not None
    
    # Log Replay Tests
    
    def test_replay_log_entries(self, recovery_handler, sample_state, log_entries):
        """Test replaying log entries."""
        success, state, error = recovery_handler.replay_log_entries(
            sample_state, log_entries, last_applied_index=2
        )
        
        assert success
        assert error is None
        # Should have replayed entries 3 and 4
        assert "user:3" in state  # Added by entry 3
        assert "user:2" not in state  # Deleted by entry 4
    
    def test_replay_log_empty(self, recovery_handler, sample_state):
        """Test replaying with no new entries."""
        success, state, error = recovery_handler.replay_log_entries(
            sample_state, [], last_applied_index=10
        )
        
        assert success
        assert state == sample_state
        assert recovery_handler.recovery_stats.log_entries_replayed == 0
    
    def test_replay_log_all_applied(self, recovery_handler, sample_state, log_entries):
        """Test replaying when all entries already applied."""
        success, state, error = recovery_handler.replay_log_entries(
            sample_state, log_entries, last_applied_index=10  # All applied
        )
        
        assert success
        assert recovery_handler.recovery_stats.log_entries_replayed == 0
    
    def test_replay_log_with_errors(self, recovery_handler, sample_state):
        """Test log replay with malformed entries."""
        log_entries = [
            {"index": 1, "command": {"op": "SET", "key": "k1", "value": "v1"}},
            {"index": 2, "command": {}},  # Missing op
            {"index": 3, "command": {"op": "SET", "key": "k3", "value": "v3"}},
        ]
        
        success, state, error = recovery_handler.replay_log_entries(
            sample_state, log_entries, last_applied_index=0
        )
        
        assert success  # Should continue despite errors
        assert recovery_handler.recovery_stats.entries_failed > 0
    
    # State Validation Tests
    
    def test_validate_valid_state(self, recovery_handler, sample_state):
        """Test validation of valid state."""
        is_valid, error = recovery_handler.validate_recovered_state(sample_state)
        
        assert is_valid
        assert error is None
    
    def test_validate_non_dict_state(self, recovery_handler):
        """Test validation fails for non-dict."""
        is_valid, error = recovery_handler.validate_recovered_state("not a dict")
        
        assert not is_valid
        assert error is not None
    
    def test_validate_non_string_keys(self, recovery_handler):
        """Test validation fails for non-string keys."""
        invalid_state = {
            1: "value",  # Integer key
            "valid": "value"
        }
        
        is_valid, error = recovery_handler.validate_recovered_state(invalid_state)
        
        assert not is_valid
        assert error is not None
    
    def test_validate_empty_state(self, recovery_handler):
        """Test validation of empty state."""
        is_valid, error = recovery_handler.validate_recovered_state({})
        
        assert is_valid
        assert error is None
    
    # Full Recovery Tests
    
    def test_full_recovery_workflow(self, recovery_handler, snapshot_store, sample_state, log_entries):
        """Test complete recovery workflow."""
        # Create snapshot at index 2
        snapshot_store.create_snapshot(sample_state, term=1, index=2)
        
        success, state, error = recovery_handler.full_recovery(
            snapshot_store,
            log_entries,
            current_term=1,
            last_applied_index=2
        )
        
        assert success
        assert error is None
        assert recovery_handler.recovery_stats.phase == RecoveryPhase.COMPLETED
        assert recovery_handler.recovered_state == state
    
    def test_full_recovery_no_snapshot(self, recovery_handler, snapshot_store, log_entries):
        """Test recovery without snapshot."""
        success, state, error = recovery_handler.full_recovery(
            snapshot_store,
            log_entries,
            current_term=1,
            last_applied_index=0
        )
        
        assert success
        assert "user:1" in state
        assert "user:2" not in state  # Deleted in entry 4
    
    def test_full_recovery_with_errors(self, recovery_handler, snapshot_store):
        """Test recovery handles errors gracefully."""
        bad_log = [
            {"index": 1, "command": {"op": "SET", "key": "k", "value": "v"}},
            {"index": 2},  # Missing command
        ]
        
        success, state, error = recovery_handler.full_recovery(
            snapshot_store,
            bad_log,
            current_term=1,
            last_applied_index=0
        )
        
        # Should complete with partial state
        assert recovery_handler.recovery_stats.entries_failed > 0
    
    # Recovery History Tests
    
    def test_recovery_stats_tracking(self, recovery_handler, snapshot_store, log_entries):
        """Test recovery statistics tracking."""
        snapshot_store.create_snapshot({"k": "v"}, term=1, index=5)
        
        recovery_handler.full_recovery(
            snapshot_store, log_entries, current_term=1, last_applied_index=5
        )
        
        stats = recovery_handler.get_recovery_stats()
        
        assert stats["phase"] == "completed"
        assert stats["snapshots_loaded"] == 1
        assert stats["duration"] > 0
    
    def test_recovery_history(self, recovery_handler, snapshot_store):
        """Test recovery history tracking."""
        # Perform multiple recoveries
        for i in range(3):
            recovery_handler.full_recovery(
                snapshot_store, [], current_term=1, last_applied_index=0
            )
        
        history = recovery_handler.get_recovery_history()
        
        assert len(history) == 3
        assert all(s["phase"] == "completed" for s in history)
    
    def test_recovery_history_limit(self, recovery_handler, snapshot_store):
        """Test recovery history has size limit."""
        # Perform many recoveries
        for i in range(20):
            recovery_handler.full_recovery(
                snapshot_store, [], current_term=1, last_applied_index=0
            )
        
        history = recovery_handler.get_recovery_history()
        
        # Should keep only max_history items
        assert len(history) <= recovery_handler.max_history
    
    # Timing Tests
    
    def test_was_recovered_recently(self, recovery_handler, snapshot_store):
        """Test recent recovery detection."""
        recovery_handler.full_recovery(
            snapshot_store, [], current_term=1, last_applied_index=0
        )
        
        assert recovery_handler.was_recovered_recently(seconds=60)
    
    def test_was_not_recovered_recently(self, recovery_handler):
        """Test recent recovery detection when old."""
        recovery_handler.last_recovery_time = datetime.now() - timedelta(minutes=10)
        
        assert not recovery_handler.was_recovered_recently(seconds=60)
    
    def test_recovery_duration(self, recovery_handler, snapshot_store):
        """Test recovery duration calculation."""
        recovery_handler.full_recovery(
            snapshot_store, [], current_term=1, last_applied_index=0
        )
        
        stats = recovery_handler.get_recovery_stats()
        
        assert stats["duration"] >= 0
    
    # Edge Cases
    
    def test_recovery_with_large_state(self, recovery_handler, snapshot_store):
        """Test recovery with large state."""
        large_state = {f"key_{i}": f"value_{i}" * 100 for i in range(1000)}
        
        snapshot_store.create_snapshot(large_state, term=1, index=10)
        
        success, state, error = recovery_handler.full_recovery(
            snapshot_store, [], current_term=1, last_applied_index=10
        )
        
        assert success
        assert len(state) == 1000
    
    def test_recovery_preserves_complex_types(self, recovery_handler):
        """Test recovery preserves complex data types."""
        log_entries = [
            {
                "index": 1,
                "command": {
                    "op": "SET",
                    "key": "data",
                    "value": {
                        "nested": {
                            "list": [1, 2, 3],
                            "dict": {"a": 1, "b": 2}
                        }
                    }
                }
            }
        ]
        
        success, state, error = recovery_handler.full_recovery(
            SnapshotStore("node1"), log_entries, current_term=1, last_applied_index=0
        )
        
        assert success
        assert state["data"]["nested"]["list"] == [1, 2, 3]
    
    def test_recovery_handles_duplicate_deletes(self, recovery_handler):
        """Test recovery handles duplicate delete operations."""
        log_entries = [
            {"index": 1, "command": {"op": "SET", "key": "k1", "value": "v1"}},
            {"index": 2, "command": {"op": "DELETE", "key": "k1"}},
            {"index": 3, "command": {"op": "DELETE", "key": "k1"}},  # Delete again
        ]
        
        success, state, error = recovery_handler.full_recovery(
            SnapshotStore("node1"), log_entries, current_term=1, last_applied_index=0
        )
        
        assert success
        assert "k1" not in state
        assert recovery_handler.recovery_stats.log_entries_replayed == 3
