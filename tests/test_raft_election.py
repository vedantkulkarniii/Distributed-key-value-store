"""
Tests for Raft leader election (Phase 3).

Tests cover state transitions, election timeouts, vote counting, and RequestVote handling.
"""

import pytest
from src.raft.state import RaftState, NodeRole, RaftStateMachine
from src.raft.timeout import ElectionTimeoutManager, TimeoutConfig, TimeoutAggregator
from src.raft.persistence import RaftPersistentState
from src.raft.election import VoteCounter, RequestVoteProcessor, ElectionRunner


class MockPersistentState:
    """Mock persistent state for testing."""
    async def set_term(self, term):
        pass
    async def set_voted_for(self, candidate_id):
        pass


class TestNodeRole:
    """Test node role management."""
    
    def test_initial_state_is_follower(self):
        """Test that nodes start as followers."""
        role = NodeRole("node-1")
        assert role.is_follower()
        assert not role.is_candidate()
        assert not role.is_leader()
    
    @pytest.mark.asyncio
    async def test_become_follower(self):
        """Test transitioning to follower."""
        role = NodeRole("node-1")
        await role.become_follower(term=5, leader_id="node-2")
        
        assert role.is_follower()
        assert role.current_term == 5
        assert role.leader_id == "node-2"
        assert role.voted_for is None
    
    @pytest.mark.asyncio
    async def test_become_candidate_from_follower(self):
        """Test transitioning to candidate from follower."""
        role = NodeRole("node-1")
        await role.become_follower(term=1)
        await role.become_candidate()
        
        assert role.is_candidate()
        assert role.current_term == 2  # Term incremented
        assert role.voted_for == "node-1"  # Vote for self
    
    @pytest.mark.asyncio
    async def test_become_candidate_from_candidate_fails(self):
        """Test that can't become candidate from candidate."""
        role = NodeRole("node-1")
        await role.become_follower(term=1)
        await role.become_candidate()
        
        old_term = role.current_term
        await role.become_candidate()  # Should fail
        
        assert role.current_term == old_term  # Term unchanged
    
    @pytest.mark.asyncio
    async def test_become_leader_from_candidate(self):
        """Test transitioning to leader from candidate."""
        role = NodeRole("node-1")
        await role.become_follower(term=1)
        await role.become_candidate()
        await role.become_leader()
        
        assert role.is_leader()
        assert role.leader_id == "node-1"
    
    @pytest.mark.asyncio
    async def test_advance_term_becomes_follower(self):
        """Test that advancing term reverts to follower."""
        role = NodeRole("node-1")
        await role.become_candidate()
        assert role.is_candidate()
        
        role.advance_term(5)
        
        assert role.is_follower()
        assert role.current_term == 5
        assert role.voted_for is None
    
    def test_get_status(self):
        """Test getting role status."""
        role = NodeRole("node-1")
        status = role.get_status()
        
        assert status["node_id"] == "node-1"
        assert status["state"] == "follower"
        assert status["term"] == 0


class TestElectionTimeout:
    """Test election timeout management."""
    
    def test_timeout_initialization(self):
        """Test timeout initializes with randomized value."""
        timeout = ElectionTimeoutManager("node-1")
        
        assert timeout.min_timeout == 0.15
        assert timeout.max_timeout == 0.30
        assert timeout.min_timeout <= timeout.current_timeout <= timeout.max_timeout
    
    def test_timeout_reset_creates_new_value(self):
        """Test that reset creates new random timeout."""
        timeout = ElectionTimeoutManager("node-1")
        first_value = timeout.current_timeout
        
        # Reset multiple times
        for _ in range(10):
            timeout.reset()
            # Very unlikely to get same value twice
            # (but possible, so we just check it's in range)
            assert timeout.min_timeout <= timeout.current_timeout <= timeout.max_timeout
    
    def test_timeout_remaining(self):
        """Test remaining time calculation."""
        timeout = ElectionTimeoutManager("node-1", min_timeout=0.5, max_timeout=0.5)
        
        remaining = timeout.remaining_time()
        assert remaining > 0
        assert remaining <= 0.5
    
    def test_timeout_expiration(self):
        """Test timeout expiration detection."""
        timeout = ElectionTimeoutManager("node-1", min_timeout=0.01, max_timeout=0.01)
        
        import time
        time.sleep(0.02)  # Wait for timeout
        
        assert timeout.is_expired()
    
    def test_timeout_profiles(self):
        """Test preset timeout configurations."""
        standard = TimeoutConfig.get("standard")
        conservative = TimeoutConfig.get("conservative")
        aggressive = TimeoutConfig.get("aggressive")
        
        assert standard["min_timeout"] < conservative["min_timeout"]
        assert aggressive["min_timeout"] < standard["min_timeout"]


class TestVoteCounter:
    """Test vote counting for elections."""
    
    def test_vote_counter_initialization(self):
        """Test vote counter starts with self vote."""
        counter = VoteCounter("node-1", total_nodes=3)
        
        assert counter.quorum == 2
        assert "node-1" in counter.votes_received
        assert len(counter.votes_received) == 1
    
    def test_record_vote(self):
        """Test recording vote from peer."""
        counter = VoteCounter("node-1", total_nodes=3)
        
        counter.record_vote("node-2")
        
        assert "node-2" in counter.votes_received
        assert len(counter.votes_received) == 2
        assert counter.has_quorum()
    
    def test_quorum_check(self):
        """Test quorum checking for different cluster sizes."""
        # 3-node cluster
        counter3 = VoteCounter("node-1", total_nodes=3)
        assert counter3.quorum == 2
        assert not counter3.has_quorum()  # Only self vote
        
        counter3.record_vote("node-2")
        assert counter3.has_quorum()
        
        # 5-node cluster
        counter5 = VoteCounter("node-1", total_nodes=5)
        assert counter5.quorum == 3
        
        counter5.record_vote("node-2")
        assert not counter5.has_quorum()
        
        counter5.record_vote("node-3")
        assert counter5.has_quorum()
    
    def test_rejection(self):
        """Test recording vote rejection."""
        counter = VoteCounter("node-1", total_nodes=3)
        
        counter.record_rejection("node-2")
        
        assert "node-2" in counter.votes_rejected
        assert "node-2" not in counter.votes_received
    
    def test_can_still_win(self):
        """Test checking if election can still be won."""
        counter = VoteCounter("node-1", total_nodes=5)
        
        assert counter.can_still_win()  # 1 + 4 remaining >= 3 quorum
        
        counter.record_rejection("node-2")
        counter.record_rejection("node-3")
        counter.record_rejection("node-4")
        
        assert not counter.can_still_win()  # Only 1 + 1 < 3


class TestSingleNodeElection:
    """Test election in single-node cluster (trivial case)."""
    
    @pytest.mark.asyncio
    async def test_single_node_becomes_leader_automatically(self):
        """Test that single node wins election immediately."""
        role = NodeRole("node-1")
        counter = VoteCounter("node-1", total_nodes=1)
        
        # Single node has itself as quorum
        assert counter.quorum == 1
        assert counter.has_quorum()
        
        # Become candidate
        await role.become_follower(term=0)
        await role.become_candidate()
        
        # Immediately becomes leader
        await role.become_leader()
        
        assert role.is_leader()
        assert role.current_term == 1
    
    @pytest.mark.asyncio
    async def test_single_node_persistent_state(self):
        """Test that single node persists state correctly."""
        persistent_state = RaftPersistentState("node-1", state_file="test_single_node_state.json")
        
        await persistent_state.load()
        assert await persistent_state.get_term() == 0
        
        await persistent_state.set_term(1)
        assert await persistent_state.get_term() == 1
        
        await persistent_state.set_voted_for("node-1")
        assert await persistent_state.get_voted_for() == "node-1"
        
        # Clean up
        await persistent_state.reset()


class TestTermComparison:
    """Test term comparison and advancement logic."""
    
    def test_stale_term_rejected(self):
        """Test that stale terms are rejected."""
        role = NodeRole("node-1")
        
        success = role.advance_term(5)
        assert success
        assert role.current_term == 5
        
        # Try to go back to lower term
        success = role.advance_term(3)
        assert not success
        assert role.current_term == 5  # Unchanged
    
    def test_same_term_not_advanced(self):
        """Test that same term doesn't advance."""
        role = NodeRole("node-1")
        role.advance_term(5)
        
        success = role.advance_term(5)
        assert not success
    
    def test_higher_term_advances(self):
        """Test that higher term advances."""
        role = NodeRole("node-1")
        role.advance_term(5)
        
        success = role.advance_term(10)
        assert success
        assert role.current_term == 10


class TestElectionEdgeCases:
    """Test edge cases in election logic."""
    
    def test_concurrent_vote_requests_same_term(self):
        """Test handling multiple vote requests in same term."""
        role = NodeRole("node-1")
        
        # First vote request
        role.set_voted_for("candidate-1")
        assert role.voted_for == "candidate-1"
        
        # Second vote request from different candidate
        result = role.set_voted_for("candidate-2")
        assert not result  # Should be rejected
        assert role.voted_for == "candidate-1"  # Unchanged
    
    def test_vote_for_same_candidate_allowed(self):
        """Test that voting for same candidate twice is allowed."""
        role = NodeRole("node-1")
        
        result1 = role.set_voted_for("candidate-1")
        assert result1
        
        result2 = role.set_voted_for("candidate-1")
        assert result2  # Should be allowed
