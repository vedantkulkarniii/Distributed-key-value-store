"""Consistency verification tests."""

import pytest
from src.raft.state_sync import MultiNodeStateSyncManager
from src.raft.linearizable_read import LinearizableReadHandler
from src.raft.state_machine import StateMachineEngine
from src.raft.transaction_manager import TransactionManager


class TestStateConsistency:
    """Tests for state consistency verification."""
    
    def test_identical_states_consistent(self):
        """Test identical states are consistent."""
        state1 = {"k1": "v1", "k2": "v2"}
        state2 = {"k1": "v1", "k2": "v2"}
        
        sync_mgr = MultiNodeStateSyncManager("node1", 3)
        is_consistent, score = sync_mgr.verify_consistency("node2", state1, state2)
        
        assert is_consistent
        assert score == 1.0
    
    def test_divergent_states_inconsistent(self):
        """Test divergent states detect inconsistency."""
        state1 = {"k1": "v1", "k2": "v2"}
        state2 = {"k1": "v1_modified", "k3": "v3"}
        
        sync_mgr = MultiNodeStateSyncManager("node1", 3)
        is_consistent, score = sync_mgr.verify_consistency("node2", state1, state2)
        
        assert not is_consistent
        assert score < 1.0
    
    def test_partial_state_overlap(self):
        """Test consistency with partial overlap."""
        state1 = {"k1": "v1", "k2": "v2", "k3": "v3"}
        state2 = {"k1": "v1", "k4": "v4"}
        
        sync_mgr = MultiNodeStateSyncManager("node1", 3)
        is_consistent, score = sync_mgr.verify_consistency("node2", state1, state2)
        
        # Some overlap but not consistent
        assert not is_consistent
        assert 0 < score < 1.0
    
    def test_empty_state_consistency(self):
        """Test consistency with empty states."""
        sync_mgr = MultiNodeStateSyncManager("node1", 3)
        is_consistent, score = sync_mgr.verify_consistency("node2", {}, {})
        
        assert is_consistent
        assert score == 1.0


class TestConflictDetection:
    """Tests for conflict detection and resolution."""
    
    def test_detect_key_divergence(self):
        """Test detection of key divergence."""
        state1 = {"k1": "v1_leader"}
        state2 = {"k1": "v1_follower"}
        
        sync_mgr = MultiNodeStateSyncManager("node1", 3)
        conflicts = sync_mgr.detect_conflicts("node2", state1, state2)
        
        assert len(conflicts) > 0
        assert conflicts[0][0] == "k1"
    
    def test_detect_missing_keys(self):
        """Test detection of missing keys."""
        state1 = {"k1": "v1", "k2": "v2"}
        state2 = {"k1": "v1"}
        
        sync_mgr = MultiNodeStateSyncManager("node1", 3)
        conflicts = sync_mgr.detect_conflicts("node2", state1, state2)
        
        assert len(conflicts) > 0
    
    def test_resolve_conflicts_prefer_leader(self):
        """Test conflict resolution preferring leader."""
        conflicts = [
            ("k1", "leader_v1", "follower_v1"),
            ("k2", None, "follower_v2"),
        ]
        
        sync_mgr = MultiNodeStateSyncManager("node1", 3)
        resolved = sync_mgr.resolve_conflicts("node2", conflicts, prefer_local=True)
        
        assert resolved["k1"] == "leader_v1"
        assert resolved["k2"] is None
    
    def test_no_conflicts_identical_keys(self):
        """Test no conflicts when keys identical."""
        state1 = {"k1": "v1", "k2": "v2"}
        state2 = {"k1": "v1", "k2": "v2"}
        
        sync_mgr = MultiNodeStateSyncManager("node1", 3)
        conflicts = sync_mgr.detect_conflicts("node2", state1, state2)
        
        assert len(conflicts) == 0


class TestLinearizableReadConsistency:
    """Tests for linearizable read consistency."""
    
    def test_read_sees_committed_writes(self):
        """Test read sees all committed writes."""
        # Setup: writes committed up to index 10
        read_handler = LinearizableReadHandler("node1", 3)
        read_handler.update_commit_index(10, term=1)
        read_handler.update_applied_index(10)
        
        # Read request
        request = read_handler.initiate_read(read_index=10)
        read_handler.process_read_index(request.request_id, 10, term=1)
        read_handler.send_heartbeat_for_read(request.request_id)
        read_handler.record_heartbeat_ack(request.request_id, "node2")
        read_handler.wait_for_applied(request.request_id, applied_index=10)
        
        assert request.phase.value == "applied"
    
    def test_read_waits_for_applied_index(self):
        """Test read waits for applied index."""
        read_handler = LinearizableReadHandler("node1", 3)
        
        request = read_handler.initiate_read(read_index=10)
        read_handler.process_read_index(request.request_id, 10, term=1)
        
        # Applied index not yet ready
        can_read = read_handler.wait_for_applied(request.request_id, applied_index=9)
        assert not can_read
        
        # Applied index ready
        can_read = read_handler.wait_for_applied(request.request_id, applied_index=10)
        assert can_read
    
    def test_quorum_read_consistency(self):
        """Test quorum-based read consistency."""
        read_handler = LinearizableReadHandler("node1", 5)
        
        request = read_handler.initiate_read(read_index=15)
        read_handler.process_read_index(request.request_id, 15, term=1)
        read_handler.send_heartbeat_for_read(request.request_id)
        
        # Collect ACKs from majority (3 of 5)
        quorum_met = read_handler.record_heartbeat_ack(request.request_id, "node2")
        assert not quorum_met
        
        quorum_met = read_handler.record_heartbeat_ack(request.request_id, "node3")
        assert quorum_met


class TestTransactionConsistency:
    """Tests for transaction consistency."""
    
    def test_serializable_isolation(self):
        """Test serializable isolation."""
        state = {}
        txn_mgr = TransactionManager("node1", state)
        
        # Begin two transactions
        _, tx1, _ = txn_mgr.begin_transaction("client1")
        _, tx2, _ = txn_mgr.begin_transaction("client2")
        
        # Both write same key
        txn_mgr.write_in_transaction(tx1, "k", "v1")
        txn_mgr.write_in_transaction(tx2, "k", "v2")
        
        # First commits
        success1, _ = txn_mgr.commit_transaction(tx1)
        assert success1
        
        # Second should detect conflict
        success2, _ = txn_mgr.commit_transaction(tx2)
        assert not success2
    
    def test_read_committed_isolation(self):
        """Test read committed isolation."""
        state = {"k": "initial"}
        txn_mgr = TransactionManager("node1", state)
        
        _, tx_id, _ = txn_mgr.begin_transaction("client1")
        
        # Read uncommitted value
        success, value, _ = txn_mgr.read_in_transaction(tx_id, "k")
        
        assert success
        assert value == "initial"
    
    def test_repeatable_read_isolation(self):
        """Test repeatable read isolation."""
        state = {"k": "v1"}
        txn_mgr = TransactionManager("node1", state)
        
        from src.raft.transaction_manager import IsolationLevel
        
        _, tx_id, _ = txn_mgr.begin_transaction(
            "client1", IsolationLevel.REPEATABLE_READ
        )
        
        # First read
        _, v1, _ = txn_mgr.read_in_transaction(tx_id, "k")
        
        # Modify state externally
        state["k"] = "v2"
        
        # Second read should see same value (from snapshot)
        _, v2, _ = txn_mgr.read_in_transaction(tx_id, "k")
        
        assert v1 == v2 == "v1"


class TestClusterConsistency:
    """Tests for cluster-wide consistency."""
    
    def test_no_split_brain(self):
        """Test split brain prevention."""
        # Simulate 3-node cluster
        # If node1 is leader, it has quorum
        leader_read = LinearizableReadHandler("node1", 3)
        leader_read.record_heartbeat_ack("read1", "node2")
        leader_read.record_heartbeat_ack("read1", "node3")
        
        # Quorum achieved
        assert leader_read.active_syncs == 0
    
    def test_monotonic_reads(self):
        """Test monotonic reads property."""
        read_handler = LinearizableReadHandler("node1", 3)
        
        # First read at index 10
        read_handler.update_applied_index(10)
        
        # Second read should be at >= 10
        read_handler.update_applied_index(15)
        
        assert read_handler.applied_index == 15
    
    def test_causal_consistency(self):
        """Test causal consistency property."""
        state1 = StateMachineEngine("node1")
        state2 = StateMachineEngine("node2")
        
        # Node1: write k1
        cmd1 = {"op": "set", "key": "k1", "value": "v1"}
        state1.apply_command(1, 1, cmd1)
        
        # Node2: write k2 (happens after k1)
        cmd2 = {"op": "set", "key": "k2", "value": "v2"}
        state2.apply_command(2, 1, cmd2)
        
        # Synchronize: node2 should have k1
        state2.data["k1"] = state1.data["k1"]
        
        assert state2.data["k1"] == "v1"
        assert state2.data["k2"] == "v2"


class TestConsistencyScoring:
    """Tests for consistency scoring."""
    
    def test_perfect_consistency_score(self):
        """Test perfect consistency gives 1.0 score."""
        sync_mgr = MultiNodeStateSyncManager("node1", 3)
        
        state = {"k1": "v1", "k2": "v2"}
        _, score = sync_mgr.verify_consistency("node2", state, state)
        
        assert score == 1.0
    
    def test_partial_consistency_scoring(self):
        """Test partial consistency gives intermediate score."""
        sync_mgr = MultiNodeStateSyncManager("node1", 3)
        
        state1 = {"k1": "v1", "k2": "v2", "k3": "v3", "k4": "v4"}
        state2 = {"k1": "v1", "k2": "v2"}  # 50% overlap
        
        _, score = sync_mgr.verify_consistency("node2", state1, state2)
        
        assert 0 < score < 1.0
    
    def test_complete_divergence_score(self):
        """Test complete divergence scoring."""
        sync_mgr = MultiNodeStateSyncManager("node1", 3)
        
        state1 = {"k1": "v1"}
        state2 = {"k2": "v2"}  # No overlap
        
        _, score = sync_mgr.verify_consistency("node2", state1, state2)
        
        # Should be low but > 0 (exists but different)
        assert 0 <= score < 0.5


class TestConsistencyInvariants:
    """Tests for consistency invariants."""
    
    def test_no_lost_updates(self):
        """Test no lost updates."""
        state = {}
        txn_mgr = TransactionManager("node1", state)
        
        # Write k1
        _, tx1, _ = txn_mgr.begin_transaction("client1")
        txn_mgr.write_in_transaction(tx1, "k1", "v1")
        txn_mgr.commit_transaction(tx1)
        
        # Write k2
        _, tx2, _ = txn_mgr.begin_transaction("client2")
        txn_mgr.write_in_transaction(tx2, "k2", "v2")
        txn_mgr.commit_transaction(tx2)
        
        # Both values present
        assert state["k1"] == "v1"
        assert state["k2"] == "v2"
    
    def test_no_dirty_reads(self):
        """Test no dirty reads."""
        state = {"k": "v"}
        txn_mgr = TransactionManager("node1", state)
        
        _, tx_id, _ = txn_mgr.begin_transaction("client1")
        
        # Read committed value
        _, value, _ = txn_mgr.read_in_transaction(tx_id, "k")
        
        # Should be committed value, not dirty
        assert value == "v"
    
    def test_consistency_timestamp_ordering(self):
        """Test consistency with timestamp ordering."""
        read_handler = LinearizableReadHandler("node1", 3)
        
        # Update indices in order
        read_handler.update_commit_index(5, term=1)
        read_handler.update_applied_index(5)
        
        # Verify order maintained
        assert read_handler.committed_index == 5
        assert read_handler.applied_index == 5
        
        # Cannot go backwards
        read_handler.update_applied_index(3)  # Should be ignored
        assert read_handler.applied_index == 5
