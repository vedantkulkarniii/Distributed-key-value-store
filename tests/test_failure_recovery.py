"""Failure recovery workflow tests."""

import pytest
from src.raft.crash_recovery import CrashRecoveryHandler, RecoveryPhase
from src.raft.snapshot_store import SnapshotStore
from src.raft.state_machine import StateMachineEngine
from src.raft.transaction_manager import TransactionManager


class TestNodeCrashRecovery:
    """Tests for node crash and recovery scenarios."""
    
    @pytest.fixture
    def recovery_scenario(self):
        """Setup recovery scenario with state and log."""
        state = {"user:1": {"name": "Alice"}, "user:2": {"name": "Bob"}}
        log_entries = [
            {"index": 1, "command": {"op": "SET", "key": "user:1", "value": {"name": "Alice"}}},
            {"index": 2, "command": {"op": "SET", "key": "user:2", "value": {"name": "Bob"}}},
            {"index": 3, "command": {"op": "SET", "key": "user:3", "value": {"name": "Charlie"}}},
        ]
        return state, log_entries
    
    # Basic Recovery Tests
    
    def test_crash_and_restart(self, recovery_scenario):
        """Test crash and restart recovery."""
        state, log_entries = recovery_scenario
        
        # Setup
        snapshot_store = SnapshotStore("node1")
        snapshot_store.create_snapshot(state, term=1, index=2)
        
        recovery = CrashRecoveryHandler("node1")
        
        # Recover
        success, recovered_state, _ = recovery.full_recovery(
            snapshot_store, log_entries, term=1, last_applied_index=2
        )
        
        assert success
        assert recovered_state["user:1"]["name"] == "Alice"
        assert recovered_state["user:3"]["name"] == "Charlie"
    
    def test_recovery_preserves_data(self, recovery_scenario):
        """Test recovery preserves all data."""
        state, log_entries = recovery_scenario
        
        snapshot_store = SnapshotStore("node1")
        snapshot_store.create_snapshot(state, term=1, index=2)
        
        recovery = CrashRecoveryHandler("node1")
        success, recovered_state, _ = recovery.full_recovery(
            snapshot_store, log_entries, term=1, last_applied_index=2
        )
        
        assert len(recovered_state) >= 3
    
    def test_recovery_handles_missing_snapshot(self, recovery_scenario):
        """Test recovery without snapshot."""
        _, log_entries = recovery_scenario
        
        snapshot_store = SnapshotStore("node1")
        recovery = CrashRecoveryHandler("node1")
        
        success, recovered_state, _ = recovery.full_recovery(
            snapshot_store, log_entries, term=1, last_applied_index=0
        )
        
        assert success
        assert len(recovered_state) > 0
    
    # Failure Scenarios
    
    def test_recovery_from_multiple_crashes(self, recovery_scenario):
        """Test recovery from multiple crashes."""
        state, log_entries = recovery_scenario
        
        snapshot_store = SnapshotStore("node1")
        snapshot_store.create_snapshot(state, term=1, index=2)
        
        # First crash
        recovery1 = CrashRecoveryHandler("node1")
        success1, state1, _ = recovery1.full_recovery(
            snapshot_store, log_entries, term=1, last_applied_index=2
        )
        
        # Second crash
        recovery2 = CrashRecoveryHandler("node1")
        success2, state2, _ = recovery2.full_recovery(
            snapshot_store, log_entries, term=1, last_applied_index=2
        )
        
        assert success1 and success2
        assert state1 == state2
    
    def test_recovery_detects_corruption(self):
        """Test recovery detects corrupted state."""
        snapshot_store = SnapshotStore("node1")
        recovery = CrashRecoveryHandler("node1")
        
        # Invalid log entry
        bad_log = [{"index": 1}]  # Missing command
        
        success, _, _ = recovery.full_recovery(
            snapshot_store, bad_log, term=1, last_applied_index=0
        )
        
        # Should still complete but with errors
        assert recovery.recovery_stats.entries_failed > 0
    
    # Transaction Recovery Tests
    
    def test_transaction_recovery(self):
        """Test recovering transactions."""
        state = {}
        log_entries = [
            {"index": 1, "command": {"op": "SET", "key": "k1", "value": "v1"}},
            {"index": 2, "command": {"op": "SET", "key": "k2", "value": "v2"}},
        ]
        
        snapshot_store = SnapshotStore("node1")
        recovery = CrashRecoveryHandler("node1")
        
        success, recovered_state, _ = recovery.full_recovery(
            snapshot_store, log_entries, term=1, last_applied_index=0
        )
        
        assert success
        assert recovered_state["k1"] == "v1"
        assert recovered_state["k2"] == "v2"
    
    def test_partial_transaction_recovery(self):
        """Test partial transaction recovery."""
        log_entries = [
            {"index": 1, "command": {"op": "SET", "key": "k1", "value": "v1"}},
            {"index": 2, "command": {"op": "SET", "key": "k2", "value": "v2"}},
            {"index": 3, "command": {"op": "DELETE", "key": "k1"}},
        ]
        
        snapshot_store = SnapshotStore("node1")
        recovery = CrashRecoveryHandler("node1")
        
        success, recovered_state, _ = recovery.full_recovery(
            snapshot_store, log_entries, term=1, last_applied_index=0
        )
        
        assert success
        assert "k1" not in recovered_state
        assert recovered_state["k2"] == "v2"
    
    # State Consistency Tests
    
    def test_recovery_consistency(self):
        """Test recovery maintains consistency."""
        state = {"k1": "v1", "k2": "v2"}
        
        snapshot_store = SnapshotStore("node1")
        snapshot_store.create_snapshot(state, term=1, index=1)
        
        recovery = CrashRecoveryHandler("node1")
        success, recovered_state, _ = recovery.full_recovery(
            snapshot_store, [], term=1, last_applied_index=1
        )
        
        assert recovered_state == state
    
    def test_recovery_with_newer_entries(self):
        """Test recovery with entries newer than snapshot."""
        old_state = {"k1": "v1"}
        new_log_entries = [
            {"index": 2, "command": {"op": "SET", "key": "k2", "value": "v2"}},
            {"index": 3, "command": {"op": "SET", "key": "k3", "value": "v3"}},
        ]
        
        snapshot_store = SnapshotStore("node1")
        snapshot_store.create_snapshot(old_state, term=1, index=1)
        
        recovery = CrashRecoveryHandler("node1")
        success, recovered_state, _ = recovery.full_recovery(
            snapshot_store, new_log_entries, term=1, last_applied_index=1
        )
        
        assert success
        assert recovered_state["k1"] == "v1"
        assert recovered_state["k2"] == "v2"
        assert recovered_state["k3"] == "v3"


class TestLeaderFailureRecovery:
    """Tests for leader failure and recovery."""
    
    def test_leader_crash_recovery(self):
        """Test leader crash and recovery."""
        state = {"committed": "data"}
        
        snapshot_store = SnapshotStore("leader")
        snapshot_store.create_snapshot(state, term=1, index=10)
        
        recovery = CrashRecoveryHandler("leader")
        success, recovered_state, _ = recovery.full_recovery(
            snapshot_store, [], term=1, last_applied_index=10
        )
        
        assert success
        assert recovered_state == state
    
    def test_leader_continues_after_recovery(self):
        """Test leader continues operations after recovery."""
        state_machine = StateMachineEngine("leader")
        
        # Simulate crash and recovery
        state_machine.data = {"k1": "v1"}
        state_machine.applied_index = 10
        
        # Continue operations
        cmd = {"op": "set", "key": "k2", "value": "v2"}
        state_machine.apply_command(11, 1, cmd)
        
        assert state_machine.applied_index == 11
        assert state_machine.data["k2"] == "v2"


class TestFollowerFailureRecovery:
    """Tests for follower failure and recovery."""
    
    def test_follower_crash_recovery(self):
        """Test follower crash and recovery."""
        # Leader state
        leader_state = {"k1": "v1", "k2": "v2", "k3": "v3"}
        
        # Follower has partial state
        follower_state = {"k1": "v1"}
        
        # Create snapshot from follower's last known good state
        snapshot_store = SnapshotStore("follower")
        snapshot_store.create_snapshot(follower_state, term=1, index=1)
        
        recovery = CrashRecoveryHandler("follower")
        
        # Recover
        log_entries = [
            {"index": 2, "command": {"op": "SET", "key": "k2", "value": "v2"}},
            {"index": 3, "command": {"op": "SET", "key": "k3", "value": "v3"}},
        ]
        
        success, recovered_state, _ = recovery.full_recovery(
            snapshot_store, log_entries, term=1, last_applied_index=1
        )
        
        assert success
        assert recovered_state == leader_state
    
    def test_follower_catches_up_after_recovery(self):
        """Test follower catches up after recovery."""
        follower = StateMachineEngine("follower")
        
        # Recover to applied_index=5
        follower.applied_index = 5
        
        # Catch up with leader
        for i in range(6, 11):
            cmd = {"op": "set", "key": f"k{i}", "value": f"v{i}"}
            follower.apply_command(i, 1, cmd)
        
        assert follower.applied_index == 10
        assert len(follower.data) == 5


class TestNetworkPartitionRecovery:
    """Tests for recovery from network partitions."""
    
    def test_partition_heals_recovery(self):
        """Test recovery when partition heals."""
        # Leader side
        leader_state = {"committed": "data"}
        leader_snapshot = SnapshotStore("leader")
        leader_snapshot.create_snapshot(leader_state, term=2, index=20)
        
        # Follower side - stale state
        follower_state = {"stale": "data"}
        follower_snapshot = SnapshotStore("follower")
        follower_snapshot.create_snapshot(follower_state, term=1, index=10)
        
        # Partition heals - follower receives leader snapshot
        recovery = CrashRecoveryHandler("follower")
        success, recovered_state, _ = recovery.full_recovery(
            leader_snapshot, [], term=2, last_applied_index=20
        )
        
        assert success
        assert recovered_state == leader_state
    
    def test_minority_partition_recovery(self):
        """Test recovery for node in minority partition."""
        # Node falls behind during partition
        stale_state = {"index": 10}
        snapshot_store = SnapshotStore("node")
        snapshot_store.create_snapshot(stale_state, term=1, index=10)
        
        recovery = CrashRecoveryHandler("node")
        
        # After partition heals, catch up
        catch_up_entries = [
            {"index": i, "command": {"op": "SET", "key": f"k{i}", "value": f"v{i}"}}
            for i in range(11, 21)
        ]
        
        success, recovered_state, _ = recovery.full_recovery(
            snapshot_store, catch_up_entries, term=2, last_applied_index=10
        )
        
        assert success
        assert len(recovered_state) >= 10


class TestRecoveryPerformance:
    """Tests for recovery performance."""
    
    def test_fast_recovery_with_snapshot(self):
        """Test fast recovery with snapshot."""
        large_state = {f"k{i}": f"v{i}" for i in range(1000)}
        
        snapshot_store = SnapshotStore("node")
        snapshot_store.create_snapshot(large_state, term=1, index=1000)
        
        recovery = CrashRecoveryHandler("node")
        success, recovered_state, _ = recovery.full_recovery(
            snapshot_store, [], term=1, last_applied_index=1000
        )
        
        assert success
        assert len(recovered_state) == 1000
        # Should be fast (instant from snapshot)
        assert recovery.recovery_stats.duration_seconds() < 1.0
    
    def test_recovery_with_large_log(self):
        """Test recovery with large log."""
        large_log = [
            {"index": i, "command": {"op": "SET", "key": f"k{i}", "value": f"v{i}"}}
            for i in range(1, 101)
        ]
        
        snapshot_store = SnapshotStore("node")
        recovery = CrashRecoveryHandler("node")
        
        success, recovered_state, _ = recovery.full_recovery(
            snapshot_store, large_log, term=1, last_applied_index=0
        )
        
        assert success
        assert len(recovered_state) == 100
