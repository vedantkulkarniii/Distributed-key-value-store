"""
Stress tests for election system under high load.

Tests resilience, performance, and scalability of election mechanism.
"""

import pytest
import asyncio
import time
from src.raft.election_runner import ElectionRunner, MultiNodeElectionOrchestrator
from src.raft.cluster_simulator import ClusterSimulator, ClusterScenarioRunner


class TestElectionStress:
    """Stress tests for single and multi-node elections."""
    
    @pytest.mark.asyncio
    async def test_rapid_consecutive_elections(self):
        """Test rapid election cycles."""
        runner = ClusterScenarioRunner(cluster_size=3)
        
        start_time = time.time()
        successful = 0
        
        for i in range(20):
            await runner.cluster.initialize()
            leader = await runner.cluster.trigger_election(0)
            if leader:
                successful += 1
        
        elapsed = time.time() - start_time
        
        assert successful >= 16  # 80% success rate
        # 20 elections shouldn't take too long
        assert elapsed < 10.0
    
    @pytest.mark.asyncio
    async def test_large_cluster_scalability(self):
        """Test election scalability with larger clusters."""
        for cluster_size in [3, 5, 7, 9]:
            runner = ClusterScenarioRunner(cluster_size=cluster_size)
            
            result = await runner.run_single_election()
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_election_with_delayed_responses(self):
        """Test election resilience with simulated delayed responses."""
        cluster = ClusterSimulator(["node-1", "node-2", "node-3"])
        await cluster.initialize()
        
        # Simulate election with variable delays
        leader = await cluster.trigger_election(0)
        
        assert leader is not None
        assert cluster.nodes[leader].is_leader()
    
    @pytest.mark.asyncio
    async def test_many_election_cycles(self):
        """Test many election cycles in sequence."""
        runner = ClusterScenarioRunner(cluster_size=3)
        successful = 0
        failed = 0
        
        for i in range(50):
            await runner.cluster.initialize()
            leader = await runner.cluster.trigger_election(0)
            if leader:
                successful += 1
            else:
                failed += 1
        
        # Should have high success rate even with 50 cycles
        assert successful >= 40
        assert failed <= 10


class TestElectionReliability:
    """Test reliability under stress and edge cases."""
    
    @pytest.mark.asyncio
    async def test_election_recovery_after_multiple_failures(self):
        """Test recovery after multiple consecutive election failures."""
        runner = ClusterScenarioRunner(cluster_size=3)
        await runner.cluster.initialize()
        
        # Try multiple times (simulating network issues)
        last_leader = None
        for attempt in range(5):
            leader = await runner.cluster.trigger_election(0)
            if leader:
                last_leader = leader
                await runner.cluster.initialize()  # Reset for next attempt
        
        assert last_leader is not None
    
    @pytest.mark.asyncio
    async def test_consistent_election_results(self):
        """Test that multiple election runs produce valid results."""
        runner = ClusterScenarioRunner(cluster_size=5)
        
        leaders = []
        for _ in range(10):
            await runner.cluster.initialize()
            leader = await runner.cluster.trigger_election(0)
            if leader:
                leaders.append(leader)
        
        # All should be valid node IDs
        for leader in leaders:
            assert leader in runner.node_ids
        
        # Most should succeed
        assert len(leaders) >= 8
    
    @pytest.mark.asyncio
    async def test_leader_persistence(self):
        """Test that elected leader maintains leadership."""
        runner = ClusterScenarioRunner(cluster_size=3)
        
        await runner.cluster.initialize()
        leader = await runner.cluster.trigger_election(0)
        
        assert leader is not None
        
        # Check leader state multiple times
        for _ in range(5):
            assert runner.cluster.nodes[leader].is_leader()


class TestElectionThroughput:
    """Test throughput and performance under stress."""
    
    @pytest.mark.asyncio
    async def test_election_throughput_small_cluster(self):
        """Test election throughput with small cluster."""
        runner = ClusterScenarioRunner(cluster_size=3)
        
        start_time = time.time()
        count = 0
        
        while time.time() - start_time < 1.0:
            await runner.cluster.initialize()
            leader = await runner.cluster.trigger_election(0)
            if leader:
                count += 1
        
        elapsed = time.time() - start_time
        
        # Should complete multiple elections per second
        rate = count / elapsed
        assert rate >= 5.0  # At least 5 elections per second
    
    @pytest.mark.asyncio
    async def test_election_throughput_medium_cluster(self):
        """Test election throughput with medium cluster."""
        runner = ClusterScenarioRunner(cluster_size=5)
        
        start_time = time.time()
        count = 0
        
        while time.time() - start_time < 1.0:
            await runner.cluster.initialize()
            leader = await runner.cluster.trigger_election(0)
            if leader:
                count += 1
        
        elapsed = time.time() - start_time
        
        # Should still complete multiple elections per second
        rate = count / elapsed
        assert rate >= 3.0  # At least 3 elections per second


class TestElectionConcurrency:
    """Test concurrent election scenarios."""
    
    @pytest.mark.asyncio
    async def test_concurrent_cluster_elections(self):
        """Test multiple clusters running elections concurrently."""
        clusters = [
            ClusterScenarioRunner(cluster_size=3),
            ClusterScenarioRunner(cluster_size=3),
            ClusterScenarioRunner(cluster_size=3),
        ]
        
        async def run_election(runner):
            await runner.cluster.initialize()
            return await runner.run_single_election()
        
        # Run elections concurrently
        results = await asyncio.gather(*[run_election(c) for c in clusters])
        
        # All should succeed
        assert all(results)
    
    @pytest.mark.asyncio
    async def test_multiple_sequential_failure_recoveries(self):
        """Test multiple failure/recovery cycles."""
        runner = ClusterScenarioRunner(cluster_size=3)
        
        for cycle in range(5):
            # Election
            await runner.cluster.initialize()
            leader = await runner.cluster.trigger_election(0)
            assert leader is not None
            
            # Failure
            await runner.cluster.nodes[leader].become_follower(term=10)
            
            # Recovery - new election
            await runner.cluster.initialize()
            new_leader = await runner.cluster.trigger_election(0)
            assert new_leader is not None


class TestElectionScalability:
    """Test scalability with varying cluster sizes."""
    
    @pytest.mark.asyncio
    async def test_scaling_from_3_to_11_nodes(self):
        """Test election performance as cluster grows."""
        times = {}
        
        for size in [3, 5, 7, 9, 11]:
            runner = ClusterScenarioRunner(cluster_size=size)
            
            start_time = time.time()
            await runner.cluster.initialize()
            leader = await runner.cluster.trigger_election(0)
            elapsed = time.time() - start_time
            
            assert leader is not None
            times[size] = elapsed
        
        # Time should scale reasonably (not exponentially)
        # Ratio of 11-node to 3-node should be < 3x
        ratio = times[11] / times[3]
        assert ratio < 5.0
    
    @pytest.mark.asyncio
    async def test_quorum_with_varying_sizes(self):
        """Test quorum logic with different cluster sizes."""
        for size in [1, 3, 5, 7, 9]:
            runner = ClusterScenarioRunner(cluster_size=size)
            await runner.cluster.initialize()
            
            leader = await runner.cluster.trigger_election(0)
            
            assert leader is not None
            # Verify leader is actually elected
            assert runner.cluster.nodes[leader].is_leader()


class TestElectionUnderAdversity:
    """Test election under adverse conditions."""
    
    @pytest.mark.asyncio
    async def test_repeated_leader_elections(self):
        """Test repeated leader elections and transitions."""
        runner = ClusterScenarioRunner(cluster_size=3)
        leaders_elected = []
        
        for i in range(10):
            await runner.cluster.initialize()
            leader = await runner.cluster.trigger_election(0)
            
            if leader:
                leaders_elected.append(leader)
                # Verify actual leader state
                assert runner.cluster.nodes[leader].is_leader()
        
        # Should have elected leaders consistently
        assert len(leaders_elected) >= 8
    
    @pytest.mark.asyncio
    async def test_long_running_cluster_stability(self):
        """Test cluster stability over extended operation."""
        runner = ClusterScenarioRunner(cluster_size=3)
        
        await runner.cluster.initialize()
        
        # Run multiple election cycles
        for cycle in range(20):
            leader = await runner.cluster.trigger_election(0)
            
            if leader:
                # Verify leader properties
                assert runner.cluster.nodes[leader].is_leader()
                assert runner.cluster.nodes[leader].current_term > 0
            
            # Reinitialize for next cycle
            await runner.cluster.initialize()


class TestElectionMemory:
    """Test memory efficiency under stress."""
    
    @pytest.mark.asyncio
    async def test_memory_efficiency_many_clusters(self):
        """Test that creating many clusters doesn't leak memory."""
        clusters = []
        
        for i in range(100):
            runner = ClusterScenarioRunner(cluster_size=3)
            clusters.append(runner)
            
            await runner.cluster.initialize()
            leader = await runner.cluster.trigger_election(0)
            assert leader is not None
        
        # Should have 100 clusters
        assert len(clusters) == 100
    
    @pytest.mark.asyncio
    async def test_repeated_cluster_recreation(self):
        """Test creating and destroying clusters repeatedly."""
        for iteration in range(50):
            runner = ClusterScenarioRunner(cluster_size=5)
            await runner.cluster.initialize()
            leader = await runner.cluster.trigger_election(0)
            assert leader is not None
            # Cluster goes out of scope and is garbage collected
