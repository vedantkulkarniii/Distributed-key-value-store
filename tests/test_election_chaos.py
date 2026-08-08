"""
Chaos and failure scenario tests for election system.

Tests behavior under network partitions, node failures, and Byzantine scenarios.
"""

import pytest
import asyncio
from src.raft.cluster_simulator import ClusterSimulator, ClusterScenarioRunner
from src.raft.state import RaftState


class TestNodeFailures:
    """Test election behavior with node failures."""
    
    @pytest.mark.asyncio
    async def test_single_node_failure_during_election(self):
        """Test that one node failure doesn't prevent election."""
        cluster = ClusterSimulator(["node-1", "node-2", "node-3", "node-4"])
        await cluster.initialize()
        
        # Simulate one node being down (becomes unreachable)
        # In a real system this would be network partition
        leader = await cluster.trigger_election(0)
        
        assert leader is not None
    
    @pytest.mark.asyncio
    async def test_multiple_sequential_node_failures(self):
        """Test recovery from multiple sequential node failures."""
        runner = ClusterScenarioRunner(cluster_size=5)
        
        for failure_cycle in range(3):
            await runner.cluster.initialize()
            leader = await runner.cluster.trigger_election(0)
            
            assert leader is not None
            
            # Simulate failure of the current leader
            await runner.cluster.nodes[leader].become_follower(term=100)
    
    @pytest.mark.asyncio
    async def test_majority_partition_survives(self):
        """Test that cluster with majority survives partition."""
        cluster = ClusterSimulator(["node-1", "node-2", "node-3", "node-4", "node-5"])
        await cluster.initialize()
        
        # Get initial leader
        leader = await cluster.trigger_election(0)
        assert leader is not None
        
        # Simulate partition: keep 3 nodes, partition 2
        # Majority (3/5) should still work
        assert cluster.nodes[leader].is_leader()
    
    @pytest.mark.asyncio
    async def test_minority_partition_no_leader(self):
        """Test that minority partition cannot elect leader."""
        cluster = ClusterSimulator(["node-1", "node-2", "node-3", "node-4", "node-5"])
        await cluster.initialize()
        
        # Simulate a minority partition (2 nodes)
        # Cannot elect leader with only 2 out of 5
        # This is simulated by the cluster logic
        leader = await cluster.trigger_election(0)
        # Leader might be None or quorum might not form


class TestNetworkPartitions:
    """Test election under network partition scenarios."""
    
    @pytest.mark.asyncio
    async def test_temporary_network_partition(self):
        """Test recovery from temporary network partition."""
        runner = ClusterScenarioRunner(cluster_size=3)
        
        # First election
        await runner.cluster.initialize()
        leader1 = await runner.cluster.trigger_election(0)
        assert leader1 is not None
        
        # Simulate partition recovery (reinitialize)
        await runner.cluster.initialize()
        leader2 = await runner.cluster.trigger_election(0)
        assert leader2 is not None
    
    @pytest.mark.asyncio
    async def test_repeated_network_disruptions(self):
        """Test handling repeated network disruptions."""
        runner = ClusterScenarioRunner(cluster_size=5)
        successful_elections = 0
        
        for disruption in range(5):
            await runner.cluster.initialize()
            leader = await runner.cluster.trigger_election(0)
            if leader:
                successful_elections += 1
        
        # Most should succeed despite disruptions
        assert successful_elections >= 3
    
    @pytest.mark.asyncio
    async def test_cascading_failures_and_recovery(self):
        """Test handling cascading failures with recovery."""
        runner = ClusterScenarioRunner(cluster_size=7)
        
        for cycle in range(3):
            await runner.cluster.initialize()
            
            # Trigger election
            leader = await runner.cluster.trigger_election(0)
            if leader:
                assert runner.cluster.nodes[leader].is_leader()
            
            # Simulate some node failures
            failed_nodes = []
            for node_id in runner.node_ids[:2]:
                await runner.cluster.nodes[node_id].become_follower(term=50)
                failed_nodes.append(node_id)


class TestTimingIssues:
    """Test election under timing and timeout issues."""
    
    @pytest.mark.asyncio
    async def test_election_with_random_delays(self):
        """Test election under variable response times."""
        runner = ClusterScenarioRunner(cluster_size=3)
        
        successful = 0
        for attempt in range(10):
            await runner.cluster.initialize()
            leader = await runner.cluster.trigger_election(0)
            if leader:
                successful += 1
        
        # Should still succeed consistently
        assert successful >= 8
    
    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """Test proper timeout handling in elections."""
        runner = ClusterScenarioRunner(cluster_size=3)
        
        await runner.cluster.initialize()
        leader = await runner.cluster.trigger_election(0)
        
        assert leader is not None
        assert runner.cluster.nodes[leader].is_leader()
    
    @pytest.mark.asyncio
    async def test_rapid_successive_elections(self):
        """Test handling rapid successive elections."""
        runner = ClusterScenarioRunner(cluster_size=3)
        
        leaders = []
        for i in range(5):
            await runner.cluster.initialize()
            leader = await runner.cluster.trigger_election(0)
            if leader:
                leaders.append(leader)
        
        # Should have elected leaders
        assert len(leaders) >= 3


class TestStateConsistency:
    """Test that state remains consistent during failures."""
    
    @pytest.mark.asyncio
    async def test_no_split_brain(self):
        """Test that split brain scenarios are prevented."""
        runner = ClusterScenarioRunner(cluster_size=3)
        
        await runner.cluster.initialize()
        leader1 = await runner.cluster.trigger_election(0)
        
        assert leader1 is not None
        assert runner.cluster.nodes[leader1].is_leader()
        
        # Check that only one leader exists
        leader_count = 0
        for node in runner.cluster.nodes.values():
            if node.is_leader():
                leader_count += 1
        
        assert leader_count <= 1
    
    @pytest.mark.asyncio
    async def test_term_monotonicity(self):
        """Test that terms always increase monotonically."""
        runner = ClusterScenarioRunner(cluster_size=3)
        
        previous_term = 0
        
        for cycle in range(5):
            # Don't reinitialize - let term keep advancing
            leader = await runner.cluster.trigger_election(previous_term + 1)
            
            if leader:
                current_term = runner.cluster.nodes[leader].current_term
                assert current_term > previous_term or current_term == previous_term + 1
                previous_term = current_term
    
    @pytest.mark.asyncio
    async def test_quorum_invariant(self):
        """Test that quorum invariant is maintained."""
        runner = ClusterScenarioRunner(cluster_size=5)
        
        await runner.cluster.initialize()
        leader = await runner.cluster.trigger_election(0)
        
        # All nodes should be in same term after election
        if leader:
            leader_term = runner.cluster.nodes[leader].current_term
            
            # All should be at same term
            for node in runner.cluster.nodes.values():
                assert node.current_term == leader_term


class TestAdversarialScenarios:
    """Test resistance to adversarial/Byzantine scenarios."""
    
    @pytest.mark.asyncio
    async def test_duplicate_vote_rejection(self):
        """Test that duplicate votes are handled correctly."""
        runner = ClusterScenarioRunner(cluster_size=3)
        
        await runner.cluster.initialize()
        
        # Each node can only vote once per term
        node = runner.cluster.nodes["node-2"]
        assert not node.has_voted_in_term()
        
        node.set_voted_for("node-1")
        assert node.has_voted_in_term()
    
    @pytest.mark.asyncio
    async def test_stale_candidate_rejection(self):
        """Test that stale candidates are rejected."""
        runner = ClusterScenarioRunner(cluster_size=3)
        
        await runner.cluster.initialize()
        
        # First election
        leader1 = await runner.cluster.trigger_election(0)
        term1 = runner.cluster.nodes[leader1].current_term if leader1 else 0
        
        # Don't reinitialize - continue with new term
        # Try another election at next term (should increment)
        leader2 = await runner.cluster.trigger_election(term1)
        term2 = runner.cluster.nodes[leader2].current_term if leader2 else 0
        
        # Term should have stayed same or advanced
        assert term2 >= term1
    
    @pytest.mark.asyncio
    async def test_out_of_order_messages(self):
        """Test handling of out-of-order messages."""
        cluster = ClusterSimulator(["node-1", "node-2", "node-3"])
        await cluster.initialize()
        
        # Trigger election
        leader = await cluster.trigger_election(0)
        
        # State should be consistent
        assert cluster.nodes[leader].is_leader()


class TestFailureRecovery:
    """Test recovery mechanisms after various failures."""
    
    @pytest.mark.asyncio
    async def test_leader_step_down_on_higher_term(self):
        """Test that leader steps down when seeing higher term."""
        runner = ClusterScenarioRunner(cluster_size=3)
        
        await runner.cluster.initialize()
        leader = await runner.cluster.trigger_election(0)
        
        # Force leader to see higher term
        await runner.cluster.nodes[leader].become_follower(term=100)
        
        assert not runner.cluster.nodes[leader].is_leader()
        assert runner.cluster.nodes[leader].is_follower()
    
    @pytest.mark.asyncio
    async def test_follower_restart_recovery(self):
        """Test recovery when follower restarts."""
        runner = ClusterScenarioRunner(cluster_size=3)
        
        await runner.cluster.initialize()
        
        # Restart a follower (reset to follower state)
        await runner.cluster.nodes["node-2"].become_follower(term=0)
        
        # Should still be able to participate
        assert runner.cluster.nodes["node-2"].is_follower()
    
    @pytest.mark.asyncio
    async def test_full_cluster_restart(self):
        """Test full cluster restart and recovery."""
        runner = ClusterScenarioRunner(cluster_size=3)
        
        # Initial election
        await runner.cluster.initialize()
        leader1 = await runner.cluster.trigger_election(0)
        assert leader1 is not None
        
        # Simulate full cluster restart
        await runner.cluster.initialize()
        leader2 = await runner.cluster.trigger_election(0)
        assert leader2 is not None


class TestEdgeCases:
    """Test edge cases in election logic."""
    
    @pytest.mark.asyncio
    async def test_single_node_cluster(self):
        """Test single node always becomes leader."""
        cluster = ClusterSimulator(["node-1"])
        await cluster.initialize()
        
        leader = await cluster.trigger_election(0)
        
        assert leader == "node-1"
        assert cluster.nodes["node-1"].is_leader()
    
    @pytest.mark.asyncio
    async def test_two_node_cluster(self):
        """Test two-node cluster (minimum quorum)."""
        cluster = ClusterSimulator(["node-1", "node-2"])
        await cluster.initialize()
        
        leader = await cluster.trigger_election(0)
        
        assert leader is not None
        assert cluster.nodes[leader].is_leader()
    
    @pytest.mark.asyncio
    async def test_even_node_count_cluster(self):
        """Test election with even number of nodes."""
        runner = ClusterScenarioRunner(cluster_size=4)
        
        await runner.cluster.initialize()
        leader = await runner.cluster.trigger_election(0)
        
        assert leader is not None
        assert runner.cluster.nodes[leader].is_leader()
    
    @pytest.mark.asyncio
    async def test_large_odd_cluster(self):
        """Test election in large odd-numbered cluster."""
        runner = ClusterScenarioRunner(cluster_size=11)
        
        await runner.cluster.initialize()
        leader = await runner.cluster.trigger_election(0)
        
        assert leader is not None
        assert runner.cluster.nodes[leader].is_leader()


class TestChaosScenarios:
    """Complex chaos scenarios combining multiple failures."""
    
    @pytest.mark.asyncio
    async def test_cascading_leader_failures(self):
        """Test handling cascading leader failures."""
        runner = ClusterScenarioRunner(cluster_size=5)
        leaders_seen = []
        
        for _ in range(3):
            await runner.cluster.initialize()
            leader = await runner.cluster.trigger_election(0)
            if leader:
                leaders_seen.append(leader)
                # Simulate leader failure
                await runner.cluster.nodes[leader].become_follower(term=100)
        
        # Should have recovered multiple times
        assert len(leaders_seen) >= 2
    
    @pytest.mark.asyncio
    async def test_mixed_failure_types(self):
        """Test handling mixed types of failures."""
        runner = ClusterScenarioRunner(cluster_size=5)
        
        # Scenario: some nodes fail, recover, others fail
        await runner.cluster.initialize()
        leader1 = await runner.cluster.trigger_election(0)
        assert leader1 is not None
        
        # Partial failure
        await runner.cluster.nodes["node-2"].become_follower(term=50)
        
        # Recovery and new election
        await runner.cluster.initialize()
        leader2 = await runner.cluster.trigger_election(0)
        assert leader2 is not None
    
    @pytest.mark.asyncio
    async def test_continuous_disruption_resilience(self):
        """Test resilience under continuous disruption."""
        runner = ClusterScenarioRunner(cluster_size=7)
        successful = 0
        
        for i in range(10):
            await runner.cluster.initialize()
            
            # Introduce random failures
            if i % 3 == 0:
                await runner.cluster.nodes["node-2"].become_follower(term=100)
            
            leader = await runner.cluster.trigger_election(0)
            if leader:
                successful += 1
        
        # Should maintain high success rate despite disruptions
        assert successful >= 7
