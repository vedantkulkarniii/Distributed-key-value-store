"""
Tests for leader state and replication tracking.
"""

import pytest
from src.raft.leader_state import ReplicationState, LeaderState


class TestReplicationState:
    """Test individual follower replication state."""
    
    def test_replication_state_initialization(self):
        """Test replication state initializes correctly."""
        state = ReplicationState("node-2", log_length=10)
        
        assert state.node_id == "node-2"
        assert state.next_index == 10
        assert state.match_index == 0
    
    def test_update_next_index(self):
        """Test updating next_index."""
        state = ReplicationState("node-2", log_length=10)
        
        result = state.update_next_index(15)
        
        assert result is True
        assert state.next_index == 15
    
    def test_update_next_index_no_regression(self):
        """Test next_index doesn't go backwards."""
        state = ReplicationState("node-2", log_length=10)
        state.next_index = 15
        
        result = state.update_next_index(12)
        
        assert result is False
        assert state.next_index == 15
    
    def test_decrement_next_index(self):
        """Test decrementing next_index."""
        state = ReplicationState("node-2", log_length=10)
        state.next_index = 5
        
        state.decrement_next_index()
        
        assert state.next_index == 4
    
    def test_decrement_next_index_minimum(self):
        """Test next_index doesn't go below 1."""
        state = ReplicationState("node-2", log_length=10)
        state.next_index = 1
        
        state.decrement_next_index()
        
        assert state.next_index == 1
    
    def test_update_match_index(self):
        """Test updating match_index."""
        state = ReplicationState("node-2", log_length=10)
        
        result = state.update_match_index(5)
        
        assert result is True
        assert state.match_index == 5
    
    def test_update_match_index_no_regression(self):
        """Test match_index doesn't go backwards."""
        state = ReplicationState("node-2", log_length=10)
        state.match_index = 8
        
        result = state.update_match_index(6)
        
        assert result is False
        assert state.match_index == 8
    
    def test_get_status(self):
        """Test getting replication status."""
        state = ReplicationState("node-2", log_length=10)
        state.next_index = 8
        state.match_index = 7
        
        status = state.get_status()
        
        assert status["node_id"] == "node-2"
        assert status["next_index"] == 8
        assert status["match_index"] == 7
        assert "last_update" in status


class TestLeaderState:
    """Test leader state management."""
    
    def test_leader_state_initialization(self):
        """Test leader state initializes correctly."""
        nodes = ["node-1", "node-2", "node-3"]
        leader = LeaderState("node-1", nodes, log_length=10)
        
        assert leader.leader_id == "node-1"
        assert leader.log_length == 10
        assert len(leader.replication_states) == 2  # Two followers
    
    def test_leader_state_replication_states(self):
        """Test replication states created for all followers."""
        nodes = ["node-1", "node-2", "node-3", "node-4"]
        leader = LeaderState("node-1", nodes, log_length=5)
        
        assert "node-2" in leader.replication_states
        assert "node-3" in leader.replication_states
        assert "node-4" in leader.replication_states
        assert "node-1" not in leader.replication_states  # Not for self
    
    def test_get_next_index_for_follower(self):
        """Test getting next_index for a follower."""
        nodes = ["node-1", "node-2", "node-3"]
        leader = LeaderState("node-1", nodes, log_length=10)
        
        next_index = leader.get_next_index_for_follower("node-2")
        
        assert next_index == 10
    
    def test_get_match_index_for_follower(self):
        """Test getting match_index for a follower."""
        nodes = ["node-1", "node-2", "node-3"]
        leader = LeaderState("node-1", nodes, log_length=10)
        
        match_index = leader.get_match_index_for_follower("node-2")
        
        assert match_index == 0  # Initially 0
    
    def test_handle_append_entries_success(self):
        """Test handling successful AppendEntries."""
        nodes = ["node-1", "node-2", "node-3"]
        leader = LeaderState("node-1", nodes, log_length=10)
        
        # Start by setting next_index lower
        leader.replication_states["node-2"].next_index = 8
        
        result = leader.handle_append_entries_success("node-2", last_log_index=8)
        
        assert result is True
        assert leader.get_match_index_for_follower("node-2") == 8
        assert leader.get_next_index_for_follower("node-2") == 9
    
    def test_handle_append_entries_failure(self):
        """Test handling failed AppendEntries."""
        nodes = ["node-1", "node-2", "node-3"]
        leader = LeaderState("node-1", nodes, log_length=10)
        leader.replication_states["node-2"].next_index = 8
        
        result = leader.handle_append_entries_failure("node-2")
        
        assert result is True
        assert leader.get_next_index_for_follower("node-2") == 7
    
    def test_calculate_commit_index_single_follower(self):
        """Test commit index calculation with single follower."""
        nodes = ["node-1", "node-2"]
        leader = LeaderState("node-1", nodes, log_length=5)
        
        # Simulate follower replication
        leader.handle_append_entries_success("node-2", last_log_index=3)
        
        commit_index = leader.calculate_commit_index()
        
        # With 2 nodes, need 2/2 = 1 (majority of 2 is 1, but we need actual majority)
        # Actually, with 2 nodes we need both to commit (N/2 + 1 = 2)
        assert commit_index >= 3
    
    def test_calculate_commit_index_three_nodes(self):
        """Test commit index calculation with three nodes."""
        nodes = ["node-1", "node-2", "node-3"]
        leader = LeaderState("node-1", nodes, log_length=10)
        
        # Replicate to one follower
        leader.handle_append_entries_success("node-2", last_log_index=7)
        
        commit_index = leader.calculate_commit_index()
        
        # With 3 nodes, need 2 to have it (including leader)
        # Leader has 10, node-2 has 7, so majority is at 7
        assert commit_index >= 7
    
    def test_is_replication_complete(self):
        """Test checking if replication is complete."""
        nodes = ["node-1", "node-2", "node-3"]
        leader = LeaderState("node-1", nodes, log_length=10)
        
        # Entry 5 is on leader
        # Need majority (2/3 including leader)
        # Initially only on leader, so just 1/3
        assert not leader.is_replication_complete(5)  # Only on leader (1/3)
        
        # Replicate to one follower
        leader.handle_append_entries_success("node-2", last_log_index=5)
        
        # Now 2/3 (leader + node-2) = majority
        assert leader.is_replication_complete(5)
    
    def test_is_caught_up(self):
        """Test checking if follower is caught up."""
        nodes = ["node-1", "node-2"]
        leader = LeaderState("node-1", nodes, log_length=10)
        
        assert not leader.is_caught_up("node-2", 10)
        
        leader.handle_append_entries_success("node-2", last_log_index=10)
        
        assert leader.is_caught_up("node-2", 10)
    
    def test_all_caught_up(self):
        """Test checking if all followers are caught up."""
        nodes = ["node-1", "node-2", "node-3"]
        leader = LeaderState("node-1", nodes, log_length=5)
        
        assert not leader.all_caught_up()
        
        leader.handle_append_entries_success("node-2", last_log_index=5)
        assert not leader.all_caught_up()
        
        leader.handle_append_entries_success("node-3", last_log_index=5)
        assert leader.all_caught_up()
    
    def test_update_log_length(self):
        """Test updating log length."""
        nodes = ["node-1", "node-2"]
        leader = LeaderState("node-1", nodes, log_length=5)
        
        leader.update_log_length(10)
        
        assert leader.log_length == 10
    
    def test_get_slow_followers(self):
        """Test identifying slow followers."""
        nodes = ["node-1", "node-2", "node-3", "node-4"]
        leader = LeaderState("node-1", nodes, log_length=100)
        
        # Set different replication levels
        leader.replication_states["node-2"].next_index = 95  # 5 behind
        leader.replication_states["node-3"].next_index = 70  # 30 behind
        leader.replication_states["node-4"].next_index = 100  # caught up
        
        slow = leader.get_slow_followers(threshold=5)
        
        # node-3 should be slow (30 >= 5), node-4 should not (0 < 5)
        assert len(slow) >= 1
        assert ("node-3", 30) in slow
    
    def test_get_replication_status(self):
        """Test getting replication status."""
        nodes = ["node-1", "node-2", "node-3"]
        leader = LeaderState("node-1", nodes, log_length=10)
        
        status = leader.get_replication_status()
        
        assert status["leader_id"] == "node-1"
        assert status["commit_index"] == 0
        assert status["log_length"] == 10
        assert "followers" in status
        assert len(status["followers"]) == 2


class TestLeaderStateMultiFollower:
    """Test leader state with multiple followers."""
    
    def test_replication_to_five_nodes(self):
        """Test replication tracking with five nodes."""
        nodes = [f"node-{i}" for i in range(1, 6)]
        leader = LeaderState("node-1", nodes, log_length=20)
        
        # All followers start at next_index = log_length
        for node_id in nodes[1:]:
            assert leader.get_next_index_for_follower(node_id) == 20
    
    def test_partial_replication(self):
        """Test calculating commit index with partial replication."""
        nodes = ["node-1", "node-2", "node-3", "node-4", "node-5"]
        leader = LeaderState("node-1", nodes, log_length=10)
        
        # Replicate to some followers
        leader.handle_append_entries_success("node-2", 7)
        leader.handle_append_entries_success("node-3", 9)
        # node-4 and node-5 not replicated yet
        
        commit_index = leader.calculate_commit_index()
        
        # Need 3 out of 5 (majority)
        # We have: leader(10), node-2(7), node-3(9)
        # Majority would be at index 7
        assert commit_index >= 7
    
    def test_failure_recovery(self):
        """Test recovery from replication failures."""
        nodes = ["node-1", "node-2", "node-3"]
        leader = LeaderState("node-1", nodes, log_length=10)
        
        # Set initial next_index lower
        leader.replication_states["node-2"].next_index = 8
        
        # Success on index 8
        leader.handle_append_entries_success("node-2", 8)
        assert leader.get_next_index_for_follower("node-2") == 9
        
        # Then fail
        leader.handle_append_entries_failure("node-2")
        assert leader.get_next_index_for_follower("node-2") == 8
        
        # Retry and succeed
        leader.handle_append_entries_success("node-2", 9)
        assert leader.get_next_index_for_follower("node-2") == 10


class TestLeaderStateQuorumLogic:
    """Test quorum-based decision making in leader state."""
    
    def test_quorum_calculation_three_nodes(self):
        """Test quorum calculation for 3-node cluster."""
        nodes = ["node-1", "node-2", "node-3"]
        leader = LeaderState("node-1", nodes, log_length=10)
        
        # Need 2/3 for majority (including leader)
        leader.handle_append_entries_success("node-2", 10)
        
        # Still only 2 total (leader + node-2), but that's majority
        assert leader.is_replication_complete(10)
    
    def test_quorum_calculation_five_nodes(self):
        """Test quorum calculation for 5-node cluster."""
        nodes = ["node-1", "node-2", "node-3", "node-4", "node-5"]
        leader = LeaderState("node-1", nodes, log_length=10)
        
        # Need 3/5 for majority
        leader.handle_append_entries_success("node-2", 10)
        assert not leader.is_replication_complete(10)  # Only 2/5
        
        leader.handle_append_entries_success("node-3", 10)
        assert leader.is_replication_complete(10)  # 3/5 - majority
    
    def test_no_quorum_with_failures(self):
        """Test that we don't have quorum with too many failures."""
        nodes = ["node-1", "node-2", "node-3", "node-4", "node-5"]
        leader = LeaderState("node-1", nodes, log_length=10)
        
        # Only replicated to one follower
        leader.handle_append_entries_success("node-2", 10)
        
        # Only 2/5, need 3
        assert not leader.is_replication_complete(10)
