"""
Election performance benchmarks (Phase 3 Day 6).

Measures election timing, throughput, and efficiency.
"""

import pytest
import asyncio
import time
from src.raft.state import NodeRole
from src.raft.timeout import ElectionTimeoutManager
from src.raft.election import VoteCounter


class TestElectionTiming:
    """Test election timing characteristics."""
    
    @pytest.mark.asyncio
    async def test_single_node_election_speed(self):
        """Test single-node election completes quickly."""
        role = NodeRole("node-1")
        
        start = time.time()
        
        await role.become_follower(term=0)
        await role.become_candidate()
        await role.become_leader()
        
        elapsed = time.time() - start
        
        # Should complete in less than 10ms
        assert elapsed < 0.01
    
    @pytest.mark.asyncio
    async def test_three_node_election_speed(self):
        """Test three-node election completes in reasonable time."""
        roles = {
            f"node-{i}": NodeRole(f"node-{i}")
            for i in range(1, 4)
        }
        
        for role in roles.values():
            await role.become_follower(term=0)
        
        start = time.time()
        
        # Node 1 becomes candidate
        await roles["node-1"].become_candidate()
        
        # Nodes 2, 3 vote
        roles["node-2"].advance_term(1)
        roles["node-3"].advance_term(1)
        roles["node-2"].set_voted_for("node-1")
        roles["node-3"].set_voted_for("node-1")
        
        # Node 1 becomes leader
        await roles["node-1"].become_leader()
        
        elapsed = time.time() - start
        
        # Should complete in less than 20ms
        assert elapsed < 0.02
    
    def test_vote_counter_performance(self):
        """Test vote counting is efficient."""
        counter = VoteCounter("node-1", total_nodes=100)
        
        start = time.time()
        
        # Record votes from all 99 other nodes
        for i in range(2, 101):
            counter.record_vote(f"node-{i}")
        
        elapsed = time.time() - start
        
        # Should handle 100 votes in less than 1ms
        assert elapsed < 0.001
        assert counter.has_quorum()


class TestElectionThroughput:
    """Test election throughput and capacity."""
    
    def test_multiple_elections_per_second(self):
        """Test system can handle multiple elections per second."""
        elections_per_second = 0
        
        start = time.time()
        end = start + 1.0  # One second
        
        while time.time() < end:
            counter = VoteCounter(f"node-{elections_per_second}", total_nodes=3)
            counter.record_vote(f"node-{elections_per_second}-2")
            counter.record_vote(f"node-{elections_per_second}-3")
            assert counter.has_quorum()
            elections_per_second += 1
        
        # Should complete at least 1000 elections per second
        assert elections_per_second >= 1000
    
    def test_vote_recording_throughput(self):
        """Test vote recording throughput."""
        counter = VoteCounter("node-1", total_nodes=1000)
        
        start = time.time()
        
        # Record 999 votes
        for i in range(2, 1000):
            counter.record_vote(f"node-{i}")
        
        elapsed = time.time() - start
        
        # Should record 999 votes in less than 10ms
        assert elapsed < 0.01
        
        # Throughput: votes per second
        throughput = (999 / elapsed) if elapsed > 0 else float('inf')
        assert throughput > 50000  # At least 50k votes/sec


class TestTimeoutPerformance:
    """Test election timeout performance."""
    
    def test_timeout_creation_speed(self):
        """Test timeout creation is fast."""
        start = time.time()
        
        # Create 10,000 timeout managers
        timeouts = [
            ElectionTimeoutManager(f"node-{i}")
            for i in range(10000)
        ]
        
        elapsed = time.time() - start
        
        # Should create 10k timeouts in less than 100ms
        assert elapsed < 0.1
        
        # All should be in valid range
        for t in timeouts:
            assert 0.15 <= t.current_timeout <= 0.30
    
    def test_timeout_reset_performance(self):
        """Test timeout reset performance."""
        timeout = ElectionTimeoutManager("node-1")
        
        start = time.time()
        
        # Reset 10,000 times
        for _ in range(10000):
            timeout.reset()
        
        elapsed = time.time() - start
        
        # Should reset 10k times in less than 50ms
        assert elapsed < 0.05


class TestStateTransitionPerformance:
    """Test state transition performance."""
    
    @pytest.mark.asyncio
    async def test_rapid_state_transitions(self):
        """Test rapid state transitions."""
        role = NodeRole("node-1")
        
        await role.become_follower(term=0)
        
        start = time.time()
        
        # Do 100 rapid transitions
        for i in range(100):
            term = i
            await role.become_follower(term=term)
            if i < 50:
                await role.become_candidate()
                await role.become_follower(term=term+1)
        
        elapsed = time.time() - start
        
        # Should complete 100 transitions in less than 100ms
        assert elapsed < 0.1
    
    @pytest.mark.asyncio
    async def test_term_advancement_speed(self):
        """Test term advancement is fast."""
        role = NodeRole("node-1")
        
        start = time.time()
        
        # Advance term 1000 times
        for i in range(1, 1001):
            role.advance_term(i)
        
        elapsed = time.time() - start
        
        # Should advance 1000 terms in less than 1ms
        assert elapsed < 0.001


class TestMemoryEfficiency:
    """Test memory efficiency of election components."""
    
    def test_vote_counter_memory(self):
        """Test vote counter memory efficiency."""
        # Create many vote counters
        counters = [
            VoteCounter(f"node-{i}", total_nodes=1000)
            for i in range(100)
        ]
        
        # Each should have roughly constant memory
        assert len(counters) == 100
        
        # Vote counting should not leak memory
        for counter in counters:
            for j in range(2, 1000):
                counter.record_vote(f"node-{j}")
    
    def test_timeout_manager_memory(self):
        """Test timeout manager memory efficiency."""
        managers = [
            ElectionTimeoutManager(f"node-{i}")
            for i in range(1000)
        ]
        
        # Should be able to create 1000 managers
        assert len(managers) == 1000
        
        # Should not consume excessive memory
        for manager in managers:
            manager.reset()


class TestScalability:
    """Test election system scalability."""
    
    def test_large_cluster_quorum_calculation(self):
        """Test quorum calculation for large clusters."""
        for size in [10, 50, 100, 500, 1000]:
            counter = VoteCounter("node-1", total_nodes=size)
            expected_quorum = (size // 2) + 1
            assert counter.quorum == expected_quorum
    
    def test_large_cluster_vote_recording(self):
        """Test vote recording scales for large clusters."""
        counter = VoteCounter("node-1", total_nodes=1000)
        
        start = time.time()
        
        # Record votes to reach quorum
        for i in range(2, (1000 // 2) + 2):
            counter.record_vote(f"node-{i}")
        
        elapsed = time.time() - start
        
        assert counter.has_quorum()
        
        # Should reach quorum quickly
        assert elapsed < 0.001
    
    def test_election_candidate_rejection_scale(self):
        """Test rejection recording scales."""
        counter = VoteCounter("node-1", total_nodes=500)
        
        start = time.time()
        
        # Record rejections
        for i in range(2, 300):
            counter.record_rejection(f"node-{i}")
        
        elapsed = time.time() - start
        
        # Should record 300 rejections quickly
        assert elapsed < 0.005
        
        # Should correctly indicate no path to victory
        assert not counter.can_still_win()
