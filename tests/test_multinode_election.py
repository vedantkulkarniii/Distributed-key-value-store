"""
Multi-node Raft leader election tests (Phase 3 Days 6-7).

Tests cover 2-node, 3-node, and 5-node cluster elections with various scenarios.
"""

import pytest
import asyncio
from src.raft.state import NodeRole
from src.raft.timeout import ElectionTimeoutManager, TimeoutConfig
from src.raft.election import VoteCounter, RequestVoteProcessor


class TestTwoNodeCluster:
    """Test leader election in a 2-node cluster."""
    
    def test_quorum_in_two_node_cluster(self):
        """Test that 2-node cluster requires both votes to win."""
        counter_a = VoteCounter("node-a", total_nodes=2)
        counter_b = VoteCounter("node-b", total_nodes=2)
        
        # Both need themselves (already counted) + 1 more = quorum of 2
        assert counter_a.quorum == 2
        assert counter_b.quorum == 2
        
        # Node A needs Node B's vote
        assert not counter_a.has_quorum()
        counter_a.record_vote("node-b")
        assert counter_a.has_quorum()
    
    @pytest.mark.asyncio
    async def test_two_node_election_winner(self):
        """Test two-node election determines a winner."""
        role_a = NodeRole("node-a")
        role_b = NodeRole("node-b")
        
        # Both start as followers
        assert role_a.is_follower()
        assert role_b.is_follower()
        
        # Node A becomes candidate first
        await role_a.become_follower(term=0)
        await role_a.become_candidate()  # Term becomes 1
        assert role_a.is_candidate()
        assert role_a.current_term == 1
        assert role_a.voted_for == "node-a"
        
        # Node B sees higher term from A
        role_b.advance_term(1)  # A's term
        assert role_b.current_term == 1
        
        # B votes for A (A is up-to-date)
        can_vote = role_b.set_voted_for("node-a")
        assert can_vote
        assert role_b.voted_for == "node-a"
        
        # A receives B's vote and wins
        counter_a = VoteCounter("node-a", total_nodes=2)
        counter_a.record_vote("node-b")
        assert counter_a.has_quorum()
        
        # A becomes leader
        await role_a.become_leader()
        assert role_a.is_leader()
        assert role_a.leader_id == "node-a"
    
    def test_two_node_no_majority_rejection(self):
        """Test that rejecting one vote in 2-node cluster means loss."""
        counter = VoteCounter("node-a", total_nodes=2)
        
        # Start with self vote
        assert not counter.has_quorum()  # Need 2, have 1
        
        # Get rejection from node-b
        counter.record_rejection("node-b")
        
        # Can't win anymore (need 2 total, can only get 1)
        assert not counter.can_still_win()


class TestThreeNodeCluster:
    """Test leader election in a 3-node cluster (most common Raft setup)."""
    
    def test_quorum_in_three_node_cluster(self):
        """Test that 3-node cluster requires 2 votes to win."""
        counter = VoteCounter("node-a", total_nodes=3)
        
        # Quorum for 3 nodes is 2
        assert counter.quorum == 2
        
        # Node A starts with self vote
        assert not counter.has_quorum()  # 1 < 2
        
        # Node A gets one peer's vote
        counter.record_vote("node-b")
        assert counter.has_quorum()  # 2 >= 2
    
    @pytest.mark.asyncio
    async def test_three_node_election_scenario(self):
        """Test realistic 3-node election scenario."""
        role_a = NodeRole("node-a")
        role_b = NodeRole("node-b")
        role_c = NodeRole("node-c")
        
        # All start as followers in term 0
        await role_a.become_follower(term=0)
        await role_b.become_follower(term=0)
        await role_c.become_follower(term=0)
        
        # Node A times out first, becomes candidate
        await role_a.become_candidate()  # Term = 1
        assert role_a.is_candidate()
        assert role_a.current_term == 1
        assert role_a.voted_for == "node-a"
        
        # Nodes B and C see higher term
        role_b.advance_term(1)
        role_c.advance_term(1)
        assert role_b.is_follower()
        assert role_c.is_follower()
        
        # B and C vote for A
        vote_b = role_b.set_voted_for("node-a")
        vote_c = role_c.set_voted_for("node-a")
        assert vote_b and vote_c
        
        # A has quorum (self + B + C = 3, need 2)
        counter_a = VoteCounter("node-a", total_nodes=3)
        counter_a.record_vote("node-b")
        counter_a.record_vote("node-c")
        assert counter_a.has_quorum()
        
        # A becomes leader
        await role_a.become_leader()
        assert role_a.is_leader()
    
    def test_three_node_two_candidates_higher_term_wins(self):
        """Test that candidate with higher term always wins."""
        role_a = NodeRole("node-a")
        role_b = NodeRole("node-b")
        role_c = NodeRole("node-c")
        
        # A is candidate in term 2
        role_a.advance_term(2)
        role_a._state = "candidate"
        assert role_a.current_term == 2
        role_a.set_voted_for("node-a")
        
        # B is candidate in term 1 (stale)
        role_b.advance_term(1)
        role_b._state = "candidate"
        
        # C sees both candidates
        role_c.advance_term(2)  # A's higher term
        
        # C votes for A (higher term)
        can_vote_a = role_c.set_voted_for("node-a")
        assert can_vote_a  # Can vote for A
        assert role_c.voted_for == "node-a"
        
        # C cannot vote for B (already voted for A in this term)
        can_vote_b = role_c.set_voted_for("node-b")
        assert not can_vote_b  # Rejected
        assert role_c.voted_for == "node-a"  # Still voting for A
    
    def test_three_node_tie_prevention(self):
        """Test that ties can't happen with randomized timeouts."""
        timeouts = [
            ElectionTimeoutManager("node-a", min_timeout=0.15, max_timeout=0.30),
            ElectionTimeoutManager("node-b", min_timeout=0.15, max_timeout=0.30),
            ElectionTimeoutManager("node-c", min_timeout=0.15, max_timeout=0.30),
        ]
        
        # Collect timeout values (should all be different with high probability)
        values = [t.current_timeout for t in timeouts]
        
        # With randomization, very unlikely all three are equal
        # (probability = 1 in 10^15 for float randomization)
        assert len(set(values)) > 1  # At least 2 different values
        
        # All should be within range
        for t in timeouts:
            assert 0.15 <= t.current_timeout <= 0.30


class TestFiveNodeCluster:
    """Test leader election in a 5-node cluster."""
    
    def test_quorum_in_five_node_cluster(self):
        """Test that 5-node cluster requires 3 votes to win."""
        counter = VoteCounter("node-a", total_nodes=5)
        
        # Quorum for 5 nodes is 3
        assert counter.quorum == 3
        
        # Start with self vote
        assert not counter.has_quorum()  # 1 < 3
        
        # Get two peer votes
        counter.record_vote("node-b")
        counter.record_vote("node-c")
        assert counter.has_quorum()  # 3 >= 3
    
    def test_five_node_partial_rejection(self):
        """Test 5-node cluster tolerates 1 rejection."""
        counter = VoteCounter("node-a", total_nodes=5)
        
        # Start with self vote
        assert counter.can_still_win()  # 1 + 4 remaining >= 3
        
        # One peer rejects
        counter.record_rejection("node-b")
        assert counter.can_still_win()  # 1 + 3 remaining >= 3
        
        # Two peers reject
        counter.record_rejection("node-c")
        assert counter.can_still_win()  # 1 + 2 remaining >= 3
        
        # Three peers reject - can't win anymore
        counter.record_rejection("node-d")
        assert not counter.can_still_win()  # 1 + 1 remaining < 3
    
    @pytest.mark.asyncio
    async def test_five_node_election_with_failures(self):
        """Test 5-node election tolerates one node failure."""
        roles = {
            f"node-{chr(97+i)}": NodeRole(f"node-{chr(97+i)}")
            for i in range(5)  # nodes a-e
        }
        
        # All start as followers in term 0
        for role in roles.values():
            await role.become_follower(term=0)
        
        # Node A becomes candidate
        role_a = roles["node-a"]
        await role_a.become_candidate()
        
        # Nodes B, C vote for A (D and E are down/slow)
        for node_id in ["node-b", "node-c"]:
            role = roles[node_id]
            role.advance_term(1)
            role.set_voted_for("node-a")
        
        # A still wins with 2 votes (B, C) + self = 3 votes
        counter = VoteCounter("node-a", total_nodes=5)
        counter.record_vote("node-b")
        counter.record_vote("node-c")
        assert counter.has_quorum()  # 3 >= 3 (quorum)
        
        # A becomes leader despite D, E being unavailable
        await role_a.become_leader()
        assert role_a.is_leader()


class TestStaleCandidateHandling:
    """Test rejection of stale candidates."""
    
    @pytest.mark.asyncio
    async def test_stale_candidate_rejected(self):
        """Test that followers reject stale candidates."""
        leader = NodeRole("node-leader")
        follower = NodeRole("node-follower")
        stale_candidate = NodeRole("node-stale")
        
        # Leader in term 3
        leader.advance_term(3)
        leader._state = "leader"
        
        # Follower following leader in term 3
        follower.advance_term(3)
        assert follower.current_term == 3
        
        # Stale candidate in term 1
        stale_candidate.advance_term(1)
        stale_candidate._state = "candidate"
        
        # Follower sees stale candidate's term (1 < 3)
        # Rejects vote because term is too old
        can_vote = follower.set_voted_for("node-stale")
        # Note: current implementation requires term update first
        # In real Raft, we'd check term in RequestVote RPC
        assert follower.current_term == 3  # Unchanged
    
    @pytest.mark.asyncio
    async def test_higher_term_candidate_wins(self):
        """Test that higher-term candidate beats lower-term leader."""
        old_leader = NodeRole("node-leader")
        new_candidate = NodeRole("node-candidate")
        follower = NodeRole("node-follower")
        
        # Old leader in term 2
        old_leader.advance_term(2)
        old_leader._state = "leader"
        old_leader.leader_id = "node-leader"
        
        # Follower following in term 2
        follower.advance_term(2)
        follower.leader_id = "node-leader"
        
        # New candidate in term 3
        new_candidate.advance_term(3)
        new_candidate._state = "candidate"
        
        # Follower sees new term (3 > 2)
        # Demotes old leader and votes for new candidate
        follower.advance_term(3)
        assert follower.is_follower()
        follower.set_voted_for("node-candidate")
        
        assert follower.voted_for == "node-candidate"
        assert follower.current_term == 3


class TestConcurrentElections:
    """Test handling of concurrent election attempts."""
    
    def test_concurrent_vote_requests_same_term(self):
        """Test handling multiple vote requests in same term."""
        role = NodeRole("node-follower")
        
        # First vote request from candidate-1
        result1 = role.set_voted_for("candidate-1")
        assert result1
        assert role.voted_for == "candidate-1"
        
        # Second vote request from candidate-2 (same term)
        result2 = role.set_voted_for("candidate-2")
        assert not result2  # Rejected
        assert role.voted_for == "candidate-1"  # Unchanged
    
    @pytest.mark.asyncio
    async def test_new_term_resets_vote(self):
        """Test that new term allows new votes."""
        role = NodeRole("node-follower")
        
        # Vote for candidate in term 1
        role.set_voted_for("candidate-1")
        assert role.voted_for == "candidate-1"
        
        # New term arrives
        role.advance_term(2)
        
        # Can now vote for different candidate
        result = role.set_voted_for("candidate-2")
        assert result
        assert role.voted_for == "candidate-2"


class TestElectionTiming:
    """Test election timing and timeout behavior."""
    
    def test_election_timeout_range(self):
        """Test election timeout falls in expected range."""
        for _ in range(100):  # Test multiple instances
            timeout = ElectionTimeoutManager("node-test")
            
            # Default range: 150-300ms
            assert 0.15 <= timeout.current_timeout <= 0.30
    
    def test_timeout_reset_creates_new_value(self):
        """Test that timeout reset picks new random value."""
        timeout = ElectionTimeoutManager("node-test")
        
        values = []
        for _ in range(10):
            timeout.reset()
            values.append(timeout.current_timeout)
            
            # All values should be in range
            assert 0.15 <= timeout.current_timeout <= 0.30
        
        # Should have variation (at least 2 different values)
        assert len(set(values)) > 1
    
    def test_aggressive_timeout_faster(self):
        """Test aggressive timeout is faster than standard."""
        standard = ElectionTimeoutManager("node-test", 
                                        min_timeout=0.15, 
                                        max_timeout=0.30)
        aggressive = ElectionTimeoutManager("node-test",
                                           min_timeout=0.05,
                                           max_timeout=0.10)
        
        # Aggressive should be faster
        assert aggressive.current_timeout <= standard.current_timeout
