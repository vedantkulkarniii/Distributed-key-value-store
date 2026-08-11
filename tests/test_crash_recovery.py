"""Tests for crash recovery mechanism."""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock
from src.raft.crash_recovery import (
    CrashRecoveryManager,
    RecoveryPhase,
    RecoveryCheckpoint,
)


class TestRecoveryCheckpoint:
    """Test suite for RecoveryCheckpoint."""
    
    def test_checkpoint_creation(self):
        """Test creating recovery checkpoint."""
        checkpoint = RecoveryCheckpoint(
            phase=RecoveryPhase.LOADING_SNAPSHOT,
            timestamp=datetime.now().isoformat(),
        )
        
        assert checkpoint.phase == RecoveryPhase.LOADING_SNAPSHOT
        assert checkpoint.entries_replayed == 0
        assert checkpoint.errors_encountered == 0
    
    def test_checkpoint_with_data(self):
        """Test checkpoint with replay data."""
        checkpoint = RecoveryCheckpoint(
            phase=RecoveryPhase.REPLAYING_LOG,
            timestamp=datetime.now().isoformat(),
            entries_replayed=100,
            entries_skipped=50,
            errors_encountered=2,
            last_applied_index=150,
        )
        
        assert checkpoint.entries_replayed == 100
        assert checkpoint.entries_skipped == 50
        assert checkpoint.errors_encountered == 2
        assert checkpoint.last_applied_index == 150


class TestCrashRecoveryManager:
    """Test suite for CrashRecoveryManager."""
    
    @pytest.fixture
    def mock_snapshot_manager(self):
        """Create mock snapshot manager."""
        manager = Mock()
        manager.get_latest_snapshot_data.return_value = (False, None, None, None)
        return manager
    
    @pytest.fixture
    def mock_wal_manager(self):
        """Create mock WAL manager."""
        manager = Mock()
        manager.get_all_entries.return_value = []
        return manager
    
    @pytest.fixture
    def recovery_manager(self, mock_snapshot_manager, mock_wal_manager):
        """Create recovery manager instance."""
        return CrashRecoveryManager("node1", mock_snapshot_manager, mock_wal_manager)
    
    # Basic Initialization Tests
    
    def test_recovery_manager_creation(self, recovery_manager):
        """Test creating recovery manager."""
        assert recovery_manager.node_id == "node1"
        assert not recovery_manager.recovery_in_progress
        assert recovery_manager.total_recoveries == 0
    
    def test_begin_recovery(self, recovery_manager):
        """Test beginning recovery."""
        success, error = recovery_manager.begin_recovery()
        
        assert success
        assert error is None
        assert recovery_manager.recovery_in_progress
        assert recovery_manager.recovery_phase == RecoveryPhase.INITIALIZING
    
    def test_begin_recovery_already_in_progress(self, recovery_manager):
        """Test cannot begin recovery twice."""
        recovery_manager.begin_recovery()
        success, error = recovery_manager.begin_recovery()
        
        assert not success
        assert error is not None
    
    # Snapshot Recovery Tests
    
    def test_recover_from_snapshot_no_snapshot(self, recovery_manager):
        """Test recovery when no snapshot exists."""
        recovery_manager.begin_recovery()
        
        state_data = {}
        success, error, last_index, last_term = recovery_manager.recover_from_snapshot(state_data)
        
        assert success
        assert error is None
        assert last_index == 0
        assert last_term == 0
    
    def test_recover_from_snapshot_with_data(self, recovery_manager, mock_snapshot_manager):
        """Test recovery from snapshot with data."""
        recovery_manager.begin_recovery()
        
        snapshot_data = {"key1": "value1", "key2": "value2"}
        mock_snapshot_manager.get_latest_snapshot_data.return_value = (
            True, snapshot_data, 100, 5
        )
        
        state_data = {}
        success, error, last_index, last_term = recovery_manager.recover_from_snapshot(state_data)
        
        assert success
        assert error is None
        assert last_index == 100
        assert last_term == 5
        assert state_data == snapshot_data
    
    def test_recover_from_snapshot_error(self, recovery_manager, mock_snapshot_manager):
        """Test snapshot recovery error handling."""
        recovery_manager.begin_recovery()
        
        mock_snapshot_manager.get_latest_snapshot_data.side_effect = Exception("Snapshot error")
        
        state_data = {}
        success, error, last_index, last_term = recovery_manager.recover_from_snapshot(state_data)
        
        assert not success
        assert error is not None
        assert recovery_manager.total_errors > 0
    
    def test_snapshot_recovery_checkpoint(self, recovery_manager, mock_snapshot_manager):
        """Test snapshot recovery creates checkpoint."""
        recovery_manager.begin_recovery()
        
        snapshot_data = {"key": "value"}
        mock_snapshot_manager.get_latest_snapshot_data.return_value = (
            True, snapshot_data, 50, 2
        )
        
        state_data = {}
        recovery_manager.recover_from_snapshot(state_data)
        
        assert len(recovery_manager.recovery_checkpoints) == 1
        checkpoint = recovery_manager.recovery_checkpoints[0]
        assert checkpoint.phase == RecoveryPhase.LOADING_SNAPSHOT
        assert checkpoint.last_applied_index == 50
    
    # WAL Replay Tests
    
    def test_replay_wal_entries_no_entries(self, recovery_manager, mock_wal_manager):
        """Test WAL replay with no entries."""
        recovery_manager.begin_recovery()
        
        mock_state_machine = Mock()
        state_data = {}
        
        success, error, entries_applied = recovery_manager.replay_wal_entries(
            state_data, from_index=0, state_machine=mock_state_machine
        )
        
        assert success
        assert error is None
        assert entries_applied == 0
    
    def test_replay_wal_entries_single_entry(self, recovery_manager, mock_wal_manager):
        """Test replaying single WAL entry."""
        recovery_manager.begin_recovery()
        
        wal_entries = [
            {"index": 1, "term": 1, "command": {"op": "set", "key": "k1", "value": "v1"}}
        ]
        mock_wal_manager.get_all_entries.return_value = wal_entries
        
        mock_state_machine = Mock()
        state_data = {}
        
        success, error, entries_applied = recovery_manager.replay_wal_entries(
            state_data, from_index=0, state_machine=mock_state_machine
        )
        
        assert success
        assert entries_applied == 1
        mock_state_machine.apply_command.assert_called_once()
    
    def test_replay_wal_entries_skip_old(self, recovery_manager, mock_wal_manager):
        """Test that old entries are skipped."""
        recovery_manager.begin_recovery()
        
        wal_entries = [
            {"index": 1, "term": 1, "command": {"op": "set", "key": "k1"}},
            {"index": 2, "term": 1, "command": {"op": "set", "key": "k2"}},
            {"index": 3, "term": 1, "command": {"op": "set", "key": "k3"}},
        ]
        mock_wal_manager.get_all_entries.return_value = wal_entries
        
        mock_state_machine = Mock()
        state_data = {}
        
        success, error, entries_applied = recovery_manager.replay_wal_entries(
            state_data, from_index=1, state_machine=mock_state_machine  # Skip first
        )
        
        assert success
        assert entries_applied == 2  # Only indices 2 and 3
    
    def test_replay_wal_entries_error_handling(self, recovery_manager, mock_wal_manager):
        """Test error handling in WAL replay."""
        recovery_manager.begin_recovery()
        
        wal_entries = [
            {"index": 1, "term": 1, "command": {"op": "set", "key": "k1"}},
            {"index": 2, "term": 1, "command": None},  # Bad entry
            {"index": 3, "term": 1, "command": {"op": "set", "key": "k3"}},
        ]
        mock_wal_manager.get_all_entries.return_value = wal_entries
        
        mock_state_machine = Mock()
        state_data = {}
        
        success, error, entries_applied = recovery_manager.replay_wal_entries(
            state_data, from_index=0, state_machine=mock_state_machine
        )
        
        assert success
        assert entries_applied == 2  # Skips bad entry
    
    def test_wal_replay_checkpoint(self, recovery_manager, mock_wal_manager):
        """Test WAL replay creates checkpoint."""
        recovery_manager.begin_recovery()
        
        wal_entries = [
            {"index": 1, "term": 1, "command": {"op": "set", "key": "k1"}}
        ]
        mock_wal_manager.get_all_entries.return_value = wal_entries
        
        mock_state_machine = Mock()
        state_data = {}
        
        recovery_manager.replay_wal_entries(state_data, from_index=0, state_machine=mock_state_machine)
        
        assert len(recovery_manager.recovery_checkpoints) == 1
        checkpoint = recovery_manager.recovery_checkpoints[0]
        assert checkpoint.phase == RecoveryPhase.REPLAYING_LOG
        assert checkpoint.entries_replayed == 1
    
    # State Verification Tests
    
    def test_verify_state_consistency(self, recovery_manager):
        """Test state consistency verification."""
        recovery_manager.begin_recovery()
        
        state_data = {"key1": "value1", "key2": "value2"}
        success, error, results = recovery_manager.verify_state_consistency(state_data)
        
        assert success
        assert error is None
        assert results["total_keys"] == 2
        assert not results["has_null_values"]
    
    def test_verify_state_with_null_values(self, recovery_manager):
        """Test verification detects null values."""
        recovery_manager.begin_recovery()
        
        state_data = {"key1": "value1", "key2": None}
        success, error, results = recovery_manager.verify_state_consistency(state_data)
        
        assert success
        assert results["has_null_values"]
        assert results["null_value_count"] == 1
    
    def test_verify_state_with_expected_keys(self, recovery_manager):
        """Test verification with expected keys."""
        recovery_manager.begin_recovery()
        
        state_data = {"key1": "value1", "key2": "value2", "extra": "data"}
        expected_keys = {"key1", "key2", "key3"}
        
        success, error, results = recovery_manager.verify_state_consistency(
            state_data, expected_keys=expected_keys
        )
        
        assert success
        assert "key3" in results["missing_expected_keys"]
        assert "extra" in results["extra_keys"]
    
    def test_verify_state_checkpoint(self, recovery_manager):
        """Test verification creates checkpoint."""
        recovery_manager.begin_recovery()
        
        state_data = {"key": "value"}
        recovery_manager.verify_state_consistency(state_data)
        
        assert len(recovery_manager.recovery_checkpoints) == 1
        checkpoint = recovery_manager.recovery_checkpoints[0]
        assert checkpoint.phase == RecoveryPhase.VERIFYING_STATE
    
    # Recovery Completion Tests
    
    def test_complete_recovery(self, recovery_manager):
        """Test completing recovery."""
        recovery_manager.begin_recovery()
        
        success, error, stats = recovery_manager.complete_recovery()
        
        assert success
        assert error is None
        assert not recovery_manager.recovery_in_progress
        assert recovery_manager.recovery_phase == RecoveryPhase.COMPLETE
        assert recovery_manager.successful_recoveries == 1
    
    def test_abort_recovery(self, recovery_manager):
        """Test aborting recovery."""
        recovery_manager.begin_recovery()
        
        success, error = recovery_manager.abort_recovery("Test abort")
        
        assert success
        assert not recovery_manager.recovery_in_progress
        assert recovery_manager.failed_recoveries == 1
    
    def test_abort_recovery_not_started(self, recovery_manager):
        """Test cannot abort recovery that wasn't started."""
        success, error = recovery_manager.abort_recovery("No recovery")
        
        assert not success
    
    # Progress and Status Tests
    
    def test_get_recovery_progress(self, recovery_manager):
        """Test getting recovery progress."""
        recovery_manager.begin_recovery()
        
        progress = recovery_manager.get_recovery_progress()
        
        assert progress["in_progress"]
        assert progress["phase"] == "initializing"
        assert progress["total_recoveries"] == 1
        assert progress["successful_recoveries"] == 0
    
    def test_get_recovery_checkpoints(self, recovery_manager):
        """Test getting recovery checkpoints."""
        recovery_manager.begin_recovery()
        
        state_data = {}
        recovery_manager.recover_from_snapshot(state_data)
        
        checkpoints = recovery_manager.get_recovery_checkpoints()
        
        assert len(checkpoints) == 1
        assert checkpoints[0]["phase"] == "loading_snapshot"
    
    # Full Recovery Tests
    
    def test_perform_full_recovery_success(
        self, recovery_manager, mock_snapshot_manager, mock_wal_manager
    ):
        """Test full recovery from start to finish."""
        snapshot_data = {"key1": "value1"}
        mock_snapshot_manager.get_latest_snapshot_data.return_value = (
            True, snapshot_data, 50, 2
        )
        
        wal_entries = [
            {"index": 51, "term": 2, "command": {"op": "set", "key": "k2"}}
        ]
        mock_wal_manager.get_all_entries.return_value = wal_entries
        
        mock_state_machine = Mock()
        state_data = {}
        
        success, error, results = recovery_manager.perform_full_recovery(
            state_data, mock_state_machine
        )
        
        assert success
        assert error is None
        assert "snapshot_recovery" in results
        assert "wal_replay" in results
        assert "verification" in results
        assert "recovery_stats" in results
    
    def test_perform_full_recovery_no_snapshot(
        self, recovery_manager, mock_wal_manager
    ):
        """Test full recovery with no snapshot."""
        mock_wal_manager.get_all_entries.return_value = []
        
        mock_state_machine = Mock()
        state_data = {}
        
        success, error, results = recovery_manager.perform_full_recovery(
            state_data, mock_state_machine
        )
        
        assert success
        assert "snapshot_recovery" in results
    
    def test_perform_full_recovery_error(
        self, recovery_manager, mock_snapshot_manager
    ):
        """Test full recovery with error."""
        mock_snapshot_manager.get_latest_snapshot_data.side_effect = Exception("Error")
        
        mock_state_machine = Mock()
        state_data = {}
        
        success, error, results = recovery_manager.perform_full_recovery(
            state_data, mock_state_machine
        )
        
        assert not success
        assert error is not None
        assert recovery_manager.failed_recoveries == 1
    
    # Statistics Tests
    
    def test_recovery_statistics(self, recovery_manager):
        """Test recovery statistics tracking."""
        # Perform multiple recoveries
        for i in range(3):
            recovery_manager.begin_recovery()
            recovery_manager.complete_recovery()
        
        assert recovery_manager.total_recoveries == 3
        assert recovery_manager.successful_recoveries == 3
        assert recovery_manager.failed_recoveries == 0
    
    def test_entries_statistics(
        self, recovery_manager, mock_wal_manager
    ):
        """Test entries statistics tracking."""
        recovery_manager.begin_recovery()
        
        wal_entries = [
            {"index": 1, "term": 1, "command": {"op": "set"}},
            {"index": 2, "term": 1, "command": {"op": "set"}},
        ]
        mock_wal_manager.get_all_entries.return_value = wal_entries
        
        mock_state_machine = Mock()
        state_data = {}
        
        recovery_manager.replay_wal_entries(state_data, from_index=0, state_machine=mock_state_machine)
        
        assert recovery_manager.total_entries_replayed == 2
