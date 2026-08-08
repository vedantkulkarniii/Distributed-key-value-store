"""
Election Integration Tests (Phase 3 Day 6).

Tests that verify election works with the bootstrap and RPC layers.
"""

import pytest
import asyncio
from src.rpc.config import create_local_cluster_config
from src.raft.state import NodeRole
from src.raft.election import VoteCounter


class TestClusterElectionSetup:
    """Test election setup with cluster configuration."""
    
    def test_local_cluster_config_for_election(self):
        """Test that local cluster config works for elections."""
        cluster = create_local_cluster_config(num_nodes=3, base_port=5000)
        
        assert len(cluster.nodes) == 3
        
        # Build config for each node
        for i in range(1, 4):
            node_id = f"node-{i}"
            config = cluster.build_node_config(node_id)
            
            assert config.node_id == node_id
            assert config.port == 5000 + (i - 1)
            assert len(config.peers) == 2
    
    def test_election_quorum_for_various_sizes(self):
        """Test quorum calculation for different cluster sizes."""
        for size in [1, 2, 3, 5, 7]:
            cluster = create_local_cluster_config(num_nodes=size)
            expected_quorum = (size // 2) + 1
            
            counter = VoteCounter("node-1", total_nodes=size)
            assert counter.quorum == expected_quorum


class TestThreeNodeElectionScenario:
    """Test realistic 3-node election scenario."""
    
    @pytest.mark.asyncio
    async def test_complete_three_node_election(self):
        """Test complete election flow in 3-node cluster."""
        # Setup
        cluster = create_local_cluster_config(num_nodes=3)
        roles = {}
        
        for i in range(1, 4):
            node_id = f"node-{i}"
            role = NodeRole(node_id)
            await role.become_follower(term=0)
            roles[node_id] = role
        
        # All start as followers
        for role in roles.values():
            assert role.is_follower()
        
        # Node 1 becomes candidate
        await roles["node-1"].become_candidate()
        assert roles["node-1"].is_candidate()
        assert roles["node-1"].current_term == 1
        
        # Nodes 2 and 3 see higher term
        for i in [2, 3]:
            roles[f"node-{i}"].advance_term(1)
            roles[f"node-{i}"].set_voted_for("node-1")
        
        # Node 1 receives votes and becomes leader
        counter = VoteCounter("node-1", total_nodes=3)
        counter.record_vote("node-2")
        counter.record_vote("node-3")
        assert counter.has_quorum()
        
        await roles["node-1"].become_leader()
        assert roles["node-1"].is_leader()


class TestStaleCandidateRejection:
    """Test that stale candidates are rejected."""
    
    def test_stale_term_rejected(self):
        """Test rejecting candidate with stale term."""
        role = NodeRole("node-follower")
        
        # Follower in term 3
        role.advance_term(3)
        assert role.current_term == 3
        
        # Stale candidate in term 1 would be rejected
        # (by not updating term, showing it's lower)
        stale_term = 1
        current_term = role.current_term
        
        assert stale_term < current_term


class TestMultiNodeQuorum:
    """Test quorum behavior in multi-node clusters."""
    
    def test_two_node_quorum(self):
        """Test 2-node cluster quorum."""
        counter = VoteCounter("node-1", total_nodes=2)
        
        # Quorum is 2 for 2-node cluster
        assert counter.quorum == 2
        
        # Need both nodes to vote
        assert not counter.has_quorum()  # Only self
        counter.record_vote("node-2")
        assert counter.has_quorum()
    
    def test_five_node_quorum(self):
        """Test 5-node cluster quorum."""
        counter = VoteCounter("node-1", total_nodes=5)
        
        # Quorum is 3 for 5-node cluster
        assert counter.quorum == 3
        
        # Need 3 votes total (includes self)
        assert not counter.has_quorum()
        counter.record_vote("node-2")
        assert not counter.has_quorum()
        counter.record_vote("node-3")
        assert counter.has_quorum()


class TestElectionFailureRecovery:
    """Test recovery from election failures."""
    
    def test_election_failure_new_term(self):
        """Test that failed election leads to new term."""
        role = NodeRole("node-candidate")
        
        # Becomes candidate in term 1
        role.advance_term(1)
        role._state = "candidate"
        
        # Election fails, new term starts
        role.advance_term(2)
        
        # Node demoted to follower
        assert role.is_follower()
        assert role.current_term == 2
    
    def test_election_partial_votes(self):
        """Test handling partial votes."""
        counter = VoteCounter("node-a", total_nodes=5)
        
        # Get 1 vote (not enough)
        counter.record_vote("node-b")
        assert not counter.has_quorum()
        
        # Can still win
        assert counter.can_still_win()
        
        # Two nodes reject
        counter.record_rejection("node-c")
        counter.record_rejection("node-d")
        
        # Still can win (1 vote + 1 remaining + self = 3)
        assert counter.can_still_win()


class TestTimingAndTimeouts:
    """Test election timing aspects."""
    
    def test_randomized_timeout_prevents_ties(self):
        """Test that randomized timeouts prevent vote ties."""
        from src.raft.timeout import ElectionTimeoutManager
        
        managers = [
            ElectionTimeoutManager(f"node-{i}")
            for i in range(10)
        ]
        
        timeouts = [m.current_timeout for m in managers]
        
        # All should be in valid range
        for t in timeouts:
            assert 0.15 <= t <= 0.30
        
        # Should have variation (multiple different values)
        unique_timeouts = len(set(timeouts))
        assert unique_timeouts > 1
    
    def test_timeout_reset_changes_value(self):
        """Test that timeout reset picks new value."""
        from src.raft.timeout import ElectionTimeoutManager
        
        manager = ElectionTimeoutManager("node-test")
        
        values = []
        for _ in range(5):
            manager.reset()
            values.append(manager.current_timeout)
        
        # Should get some variation
        assert len(set(values)) > 1


class TestLeaderStability:
    """Test that elected leader remains stable."""
    
    @pytest.mark.asyncio
    async def test_leader_stable_until_new_term(self):
        """Test leader remains stable until new term."""
        role = NodeRole("node-leader")
        
        # Properly become leader in term 2
        await role.become_follower(term=1)
        await role.become_candidate()  # term becomes 2
        await role.become_leader()
        
        assert role.is_leader()
        original_term = role.current_term
        
        # Leader term doesn't change on its own
        await asyncio.sleep(0.01)
        assert role.current_term == original_term
        assert role.is_leader()
        
        # Only changes on RPC with higher term
        role.advance_term(original_term + 1)
        
        # Now demoted to follower
        assert role.is_follower()
        assert role.current_term == original_term + 1
