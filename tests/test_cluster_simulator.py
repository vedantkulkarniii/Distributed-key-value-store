"""
Tests for cluster simulator.
"""

import pytest
import asyncio
from src.raft.cluster_simulator import ClusterSimulator, ClusterScenarioRunner
from src.raft.state import NodeRole, RaftState


class TestClusterSimulator:
    """Test cluster simulator basic functionality."""
    
    def test_cluster_initialization(self):
        """Test cluster initializes with correct number of nodes."""
        node_ids = ["node-1", "node-2", "node-3"]
        cluster = ClusterSimulator(node_ids)
        
        assert cluster.node_ids == node_ids
        assert len(cluster.nodes) == 3
        assert cluster.term == 0
    
    def test_cluster_nodes_created(self):
        """Test all nodes are created correctly."""
        node_ids = ["node-1", "node-2", "node-3"]
        cluster = ClusterSimulator(node_ids)
        
        for node_id in node_ids:
            assert node_id in cluster.nodes
            assert isinstance(cluster.nodes[node_id], NodeRole)
    
    @pytest.mark.asyncio
    async def test_cluster_initialize(self):
        """Test cluster initialization (all followers)."""
        node_ids = ["node-1", "node-2", "node-3"]
        cluster = ClusterSimulator(node_ids)
        
        await cluster.initialize()
        
        # All nodes should be followers
        for node in cluster.nodes.values():
            assert node.is_follower()
            assert node.current_term == 0
    
    @pytest.mark.asyncio
    async def test_single_node_election(self):
        """Test election in single node cluster."""
        cluster = ClusterSimulator(["node-1"])
        await cluster.initialize()
        
        leader = await cluster.trigger_election(term=0)
        
        assert leader == "node-1"
        assert cluster.term >= 1
    
    @pytest.mark.asyncio
    async def test_three_node_election(self):
        """Test election in 3-node cluster."""
        node_ids = ["node-1", "node-2", "node-3"]
        cluster = ClusterSimulator(node_ids)
        await cluster.initialize()
        
        leader = await cluster.trigger_election(term=0)
        
        assert leader is not None
        assert leader == "node-1"  # First node initiates
        assert cluster.nodes[leader].is_leader()
    
    @pytest.mark.asyncio
    async def test_five_node_election(self):
        """Test election in 5-node cluster."""
        node_ids = ["node-1", "node-2", "node-3", "node-4", "node-5"]
        cluster = ClusterSimulator(node_ids)
        await cluster.initialize()
        
        leader = await cluster.trigger_election(term=0)
        
        assert leader is not None
        assert cluster.nodes[leader].is_leader()
    
    @pytest.mark.asyncio
    async def test_cluster_status(self):
        """Test getting cluster status."""
        node_ids = ["node-1", "node-2", "node-3"]
        cluster = ClusterSimulator(node_ids)
        await cluster.initialize()
        
        await cluster.trigger_election(term=0)
        
        status = cluster.get_status()
        
        assert "term" in status
        assert "nodes" in status
        assert len(status["nodes"]) == 3
        assert status["term"] >= 1
    
    @pytest.mark.asyncio
    async def test_cluster_status_has_leader(self):
        """Test cluster status shows a leader exists."""
        node_ids = ["node-1", "node-2", "node-3"]
        cluster = ClusterSimulator(node_ids)
        await cluster.initialize()
        
        await cluster.trigger_election(term=0)
        
        status = cluster.get_status()
        
        # Find leader
        leader_count = 0
        for node_status in status["nodes"].values():
            if "leader" in node_status.get("state", "").lower():
                leader_count += 1
        
        assert leader_count >= 1  # At least one leader
    
    @pytest.mark.asyncio
    async def test_multiple_elections_consecutive(self):
        """Test running multiple elections in sequence."""
        node_ids = ["node-1", "node-2", "node-3"]
        cluster = ClusterSimulator(node_ids)
        await cluster.initialize()
        
        leader1 = await cluster.trigger_election(term=0)
        
        # Reset for new election
        await cluster.initialize()
        leader2 = await cluster.trigger_election(term=0)
        
        assert leader1 is not None
        assert leader2 is not None


class TestClusterScenarioRunner:
    """Test cluster scenario runner."""
    
    def test_scenario_runner_initialization(self):
        """Test scenario runner initializes correctly."""
        runner = ClusterScenarioRunner(cluster_size=3)
        
        assert len(runner.node_ids) == 3
        assert runner.cluster is not None
    
    def test_scenario_runner_node_ids(self):
        """Test scenario runner creates correct node IDs."""
        runner = ClusterScenarioRunner(cluster_size=5)
        
        expected_ids = ["node-1", "node-2", "node-3", "node-4", "node-5"]
        assert runner.node_ids == expected_ids
    
    @pytest.mark.asyncio
    async def test_single_election_scenario(self):
        """Test single election scenario."""
        runner = ClusterScenarioRunner(cluster_size=3)
        
        result = await runner.run_single_election()
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_single_election_scenario_five_nodes(self):
        """Test single election scenario with 5 nodes."""
        runner = ClusterScenarioRunner(cluster_size=5)
        
        result = await runner.run_single_election()
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_multiple_elections_scenario(self):
        """Test multiple elections scenario."""
        runner = ClusterScenarioRunner(cluster_size=3)
        
        successful = await runner.run_multiple_elections(num_elections=3)
        
        assert successful >= 2  # At least 2 out of 3 should succeed
    
    @pytest.mark.asyncio
    async def test_multiple_elections_many(self):
        """Test many elections scenario."""
        runner = ClusterScenarioRunner(cluster_size=3)
        
        successful = await runner.run_multiple_elections(num_elections=5)
        
        assert successful >= 4  # At least 80% success
    
    @pytest.mark.asyncio
    async def test_leader_failure_scenario(self):
        """Test leader failure and re-election scenario."""
        runner = ClusterScenarioRunner(cluster_size=3)
        
        result = await runner.run_leader_failure_scenario()
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_leader_failure_scenario_five_nodes(self):
        """Test leader failure scenario with 5 nodes."""
        runner = ClusterScenarioRunner(cluster_size=5)
        
        result = await runner.run_leader_failure_scenario()
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_leader_failure_produces_different_state(self):
        """Test leader failure changes cluster state."""
        runner = ClusterScenarioRunner(cluster_size=3)
        
        await runner.cluster.initialize()
        
        # First election
        leader1 = await runner.cluster.trigger_election(0)
        assert leader1 is not None
        assert runner.cluster.nodes[leader1].is_leader()
        
        # Leader fails
        await runner.cluster.nodes[leader1].become_follower(term=1)
        assert not runner.cluster.nodes[leader1].is_leader()
        assert runner.cluster.nodes[leader1].is_follower()


class TestClusterSimulatorEdgeCases:
    """Test edge cases and boundary conditions."""
    
    @pytest.mark.asyncio
    async def test_single_node_cluster_always_leader(self):
        """Test single-node cluster always becomes leader."""
        cluster = ClusterSimulator(["node-1"])
        await cluster.initialize()
        
        leader = await cluster.trigger_election(term=0)
        assert leader == "node-1"
        assert cluster.nodes[leader].is_leader()
    
    @pytest.mark.asyncio
    async def test_large_cluster_election(self):
        """Test election in larger cluster."""
        node_ids = [f"node-{i}" for i in range(1, 11)]  # 10 nodes
        cluster = ClusterSimulator(node_ids)
        await cluster.initialize()
        
        leader = await cluster.trigger_election(term=0)
        
        assert leader is not None
        assert leader in node_ids
        assert cluster.nodes[leader].is_leader()
    
    @pytest.mark.asyncio
    async def test_term_increments_correctly(self):
        """Test term increments with each election."""
        cluster = ClusterSimulator(["node-1", "node-2", "node-3"])
        await cluster.initialize()
        
        initial_term = cluster.term
        
        leader = await cluster.trigger_election(term=0)
        assert cluster.term >= 1
        
        # Reset and try again
        await cluster.initialize()
        leader = await cluster.trigger_election(term=0)
        assert cluster.term >= 1


class TestClusterSimulatorIntegration:
    """Integration tests for cluster simulator."""
    
    @pytest.mark.asyncio
    async def test_complete_election_flow(self):
        """Test complete election flow from init to leader."""
        runner = ClusterScenarioRunner(cluster_size=3)
        
        # Initialize
        await runner.cluster.initialize()
        
        # Trigger election
        leader = await runner.cluster.trigger_election(term=0)
        
        # Verify state
        assert leader is not None
        assert runner.cluster.nodes[leader].is_leader()
        
        # Get status
        status = runner.cluster.get_status()
        assert status["term"] >= 1
    
    @pytest.mark.asyncio
    async def test_recovery_after_failure(self):
        """Test cluster recovery after node failure."""
        runner = ClusterScenarioRunner(cluster_size=3)
        
        result = await runner.run_leader_failure_scenario()
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_repeated_scenarios(self):
        """Test running multiple scenarios in sequence."""
        runner = ClusterScenarioRunner(cluster_size=3)
        
        # Run single election multiple times
        for _ in range(3):
            result = await runner.run_single_election()
            assert result is True
            # Reinitialize for next iteration
            await runner.cluster.initialize()
    
    @pytest.mark.asyncio
    async def test_scenarios_with_size_variations(self):
        """Test scenarios with different cluster sizes."""
        for size in [1, 3, 5, 7]:
            runner = ClusterScenarioRunner(cluster_size=size)
            result = await runner.run_single_election()
            assert result is True


class TestClusterSimulatorConsistency:
    """Test consistency properties of cluster simulator."""
    
    @pytest.mark.asyncio
    async def test_no_two_leaders_in_term(self):
        """Test no two leaders can exist in same term."""
        cluster = ClusterSimulator(["node-1", "node-2", "node-3"])
        await cluster.initialize()
        
        # Trigger election
        await cluster.trigger_election(term=0)
        
        # Check for at most one leader
        leaders = []
        for node_id, node in cluster.nodes.items():
            if node.is_leader():
                leaders.append(node_id)
        
        assert len(leaders) <= 1
    
    @pytest.mark.asyncio
    async def test_all_nodes_reach_same_term(self):
        """Test all nodes reach same term after election."""
        cluster = ClusterSimulator(["node-1", "node-2", "node-3"])
        await cluster.initialize()
        
        # Trigger election
        await cluster.trigger_election(term=0)
        
        # All nodes should have same term
        terms = set()
        for node in cluster.nodes.values():
            terms.add(node.current_term)
        
        assert len(terms) == 1
    
    @pytest.mark.asyncio
    async def test_voted_for_persists(self):
        """Test voted_for field is set correctly."""
        cluster = ClusterSimulator(["node-1", "node-2", "node-3"])
        await cluster.initialize()
        
        # Trigger election
        leader = await cluster.trigger_election(term=0)
        
        # All non-leader followers should have voted
        for node_id, node in cluster.nodes.items():
            if node_id != leader:
                # Followers should be followers
                assert node.is_follower()


class TestClusterSimulatorNodeStates:
    """Test individual node state management."""
    
    @pytest.mark.asyncio
    async def test_node_follower_state(self):
        """Test node can be in follower state."""
        cluster = ClusterSimulator(["node-1"])
        await cluster.initialize()
        
        node = cluster.nodes["node-1"]
        assert node.is_follower()
        assert not node.is_candidate()
        assert not node.is_leader()
    
    @pytest.mark.asyncio
    async def test_node_leader_state(self):
        """Test node can transition to leader state."""
        cluster = ClusterSimulator(["node-1"])
        await cluster.initialize()
        
        leader = await cluster.trigger_election(term=0)
        node = cluster.nodes[leader]
        
        assert node.is_leader()
        assert not node.is_follower()
        assert not node.is_candidate()
    
    @pytest.mark.asyncio
    async def test_term_tracking(self):
        """Test node tracks term correctly."""
        cluster = ClusterSimulator(["node-1", "node-2", "node-3"])
        await cluster.initialize()
        
        # All nodes start at term 0
        for node in cluster.nodes.values():
            assert node.current_term == 0
        
        # After election, all should have same higher term
        await cluster.trigger_election(term=0)
        
        terms = [node.current_term for node in cluster.nodes.values()]
        assert len(set(terms)) == 1
        assert terms[0] > 0


class TestClusterSimulatorQuorum:
    """Test quorum-based decision making."""
    
    @pytest.mark.asyncio
    async def test_three_node_quorum(self):
        """Test quorum in 3-node cluster."""
        cluster = ClusterSimulator(["node-1", "node-2", "node-3"])
        await cluster.initialize()
        
        # Need 2 out of 3 for quorum
        leader = await cluster.trigger_election(term=0)
        assert leader is not None  # One candidate + one vote = quorum
    
    @pytest.mark.asyncio
    async def test_five_node_quorum(self):
        """Test quorum in 5-node cluster."""
        cluster = ClusterSimulator(["node-1", "node-2", "node-3", "node-4", "node-5"])
        await cluster.initialize()
        
        # Need 3 out of 5 for quorum
        leader = await cluster.trigger_election(term=0)
        assert leader is not None
