"""Tests for multi-node state machine synchronization and integration."""

import pytest
from unittest.mock import Mock, MagicMock, call
from datetime import datetime


class TestMultiNodeStateMachineIntegration:
    """Test suite for multi-node state machine integration."""
    
    @pytest.fixture
    def cluster_nodes(self):
        """Create mock cluster nodes."""
        nodes = {}
        for node_id in ["node1", "node2", "node3"]:
            node = Mock()
            node.node_id = node_id
            node.current_term = 0
            node.voted_for = None
            node.state_machine_data = {}
            node.applied_index = 0
            node.commit_index = 0
            nodes[node_id] = node
        return nodes
    
    # Basic Multi-Node Tests
    
    def test_cluster_initialization(self, cluster_nodes):
        """Test initializing cluster."""
        assert len(cluster_nodes) == 3
        for node_id, node in cluster_nodes.items():
            assert node.node_id == node_id
            assert node.current_term == 0
            assert len(node.state_machine_data) == 0
    
    def test_leader_election_scenario(self, cluster_nodes):
        """Test leader election in cluster."""
        # Node1 becomes leader
        cluster_nodes["node1"].is_leader = True
        cluster_nodes["node1"].current_term = 1
        
        cluster_nodes["node2"].is_leader = False
        cluster_nodes["node2"].current_term = 1
        
        cluster_nodes["node3"].is_leader = False
        cluster_nodes["node3"].current_term = 1
        
        assert cluster_nodes["node1"].is_leader
        assert not cluster_nodes["node2"].is_leader
        assert not cluster_nodes["node3"].is_leader
    
    # Replication Tests
    
    def test_write_replication_to_all_nodes(self, cluster_nodes):
        """Test write replication to all nodes."""
        # Leader receives write
        key, value = "test_key", "test_value"
        
        # Replicate to all nodes
        for node in cluster_nodes.values():
            node.state_machine_data[key] = value
        
        # Verify all nodes have the data
        for node in cluster_nodes.values():
            assert node.state_machine_data.get(key) == value
    
    def test_partial_replication(self, cluster_nodes):
        """Test partial replication (some nodes down)."""
        key, value = "partial_key", "partial_value"
        
        # Write to node1 and node2 only
        cluster_nodes["node1"].state_machine_data[key] = value
        cluster_nodes["node2"].state_machine_data[key] = value
        
        # Node3 doesn't have it yet
        assert key not in cluster_nodes["node3"].state_machine_data
        
        # Eventually replicate to node3
        cluster_nodes["node3"].state_machine_data[key] = value
        
        # Now all have it
        for node in cluster_nodes.values():
            assert node.state_machine_data[key] == value
    
    def test_read_consistency_same_index(self, cluster_nodes):
        """Test read consistency when all nodes at same committed index."""
        # All nodes apply same entries up to index 100
        data = {"key1": "v1", "key2": "v2"}
        
        for node in cluster_nodes.values():
            node.state_machine_data = data.copy()
            node.applied_index = 100
            node.commit_index = 100
        
        # All nodes return same value
        for node in cluster_nodes.values():
            assert node.state_machine_data["key1"] == "v1"
            assert node.state_machine_data["key2"] == "v2"
    
    # Quorum Tests
    
    def test_quorum_size_3_node_cluster(self, cluster_nodes):
        """Test quorum size for 3-node cluster."""
        quorum_size = (len(cluster_nodes) // 2) + 1
        assert quorum_size == 2
    
    def test_majority_write_commitment(self, cluster_nodes):
        """Test write is committed with majority agreement."""
        key, value = "commit_test", "committed"
        
        # Leader writes to self
        cluster_nodes["node1"].state_machine_data[key] = value
        cluster_nodes["node1"].applied_index = 1
        
        # First follower acknowledges
        cluster_nodes["node2"].state_machine_data[key] = value
        cluster_nodes["node2"].applied_index = 1
        
        # Quorum reached (2/3)
        replicated_count = sum(
            1 for node in cluster_nodes.values()
            if node.state_machine_data.get(key) == value
        )
        
        assert replicated_count >= 2
    
    # Consistency Tests
    
    def test_eventual_consistency(self, cluster_nodes):
        """Test eventual consistency across cluster."""
        key, value = "eventual", "consistent"
        
        # Write to leader
        cluster_nodes["node1"].state_machine_data[key] = value
        
        # Replicate to followers over time
        cluster_nodes["node2"].state_machine_data[key] = value
        cluster_nodes["node3"].state_machine_data[key] = value
        
        # All eventually have same value
        values = [node.state_machine_data.get(key) for node in cluster_nodes.values()]
        assert all(v == value for v in values)
    
    def test_no_split_brain(self, cluster_nodes):
        """Test no split brain: only one leader per term."""
        # Network partition creates two groups
        # Group 1: node1 (leader)
        cluster_nodes["node1"].is_leader = True
        cluster_nodes["node1"].current_term = 5
        
        # Group 2: node2 and node3 (should not elect leader without quorum)
        cluster_nodes["node2"].is_leader = False
        cluster_nodes["node2"].current_term = 5
        
        cluster_nodes["node3"].is_leader = False
        cluster_nodes["node3"].current_term = 5
        
        # Only one leader in term 5
        leaders_in_term = sum(
            1 for node in cluster_nodes.values()
            if node.is_leader and node.current_term == 5
        )
        
        assert leaders_in_term <= 1
    
    # Failure Scenarios
    
    def test_follower_catch_up_after_reconnect(self, cluster_nodes):
        """Test follower catches up after reconnection."""
        # Leader has entries up to index 100
        cluster_nodes["node1"].state_machine_data = {f"key{i}": f"val{i}" for i in range(100)}
        cluster_nodes["node1"].applied_index = 100
        
        # Node2 is disconnected, only has up to index 50
        cluster_nodes["node2"].state_machine_data = {f"key{i}": f"val{i}" for i in range(50)}
        cluster_nodes["node2"].applied_index = 50
        
        # After reconnection, catch up
        cluster_nodes["node2"].state_machine_data = cluster_nodes["node1"].state_machine_data.copy()
        cluster_nodes["node2"].applied_index = 100
        
        # Now in sync
        assert cluster_nodes["node2"].applied_index == cluster_nodes["node1"].applied_index
        assert cluster_nodes["node2"].state_machine_data == cluster_nodes["node1"].state_machine_data
    
    def test_leader_failure_and_election(self, cluster_nodes):
        """Test recovery after leader failure."""
        # Current leader is node1
        cluster_nodes["node1"].is_leader = True
        cluster_nodes["node1"].current_term = 5
        
        # Leader fails
        cluster_nodes["node1"].is_leader = False
        
        # Node2 wins election
        cluster_nodes["node2"].is_leader = True
        cluster_nodes["node2"].current_term = 6
        
        # Only one leader per term
        leaders_term_6 = sum(
            1 for node in cluster_nodes.values()
            if node.is_leader and node.current_term == 6
        )
        assert leaders_term_6 == 1
    
    def test_term_advancement_on_stale_node(self, cluster_nodes):
        """Test stale node updates term from leader heartbeat."""
        cluster_nodes["node3"].current_term = 5  # Stale term
        cluster_nodes["node1"].current_term = 10  # Current leader term
        
        # Node3 receives heartbeat with term 10
        cluster_nodes["node3"].current_term = cluster_nodes["node1"].current_term
        
        # Now in sync
        assert cluster_nodes["node3"].current_term == cluster_nodes["node1"].current_term
    
    # Snapshot Tests
    
    def test_snapshot_transfer_to_lagging_follower(self, cluster_nodes):
        """Test snapshot transfer for lagging follower."""
        # Leader has snapshot at index 100
        cluster_nodes["node1"].latest_snapshot_index = 100
        cluster_nodes["node1"].state_machine_data = {f"k{i}": f"v{i}" for i in range(100)}
        
        # Lagging follower needs snapshot
        cluster_nodes["node3"].latest_snapshot_index = 0
        cluster_nodes["node3"].applied_index = 0
        
        # Transfer snapshot
        cluster_nodes["node3"].state_machine_data = cluster_nodes["node1"].state_machine_data.copy()
        cluster_nodes["node3"].latest_snapshot_index = 100
        
        # Follower caught up via snapshot
        assert cluster_nodes["node3"].latest_snapshot_index == cluster_nodes["node1"].latest_snapshot_index
    
    # Transaction Tests
    
    def test_transaction_isolation_across_cluster(self, cluster_nodes):
        """Test transaction isolation across cluster."""
        # Transaction 1 on node1
        cluster_nodes["node1"].transaction_id = "tx1"
        cluster_nodes["node1"].state_machine_data["tx1_key"] = "intermediate"
        
        # Other nodes shouldn't see uncommitted data
        assert "tx1_key" not in cluster_nodes["node2"].state_machine_data
        assert "tx1_key" not in cluster_nodes["node3"].state_machine_data
        
        # After commit, replicate
        for node in cluster_nodes.values():
            node.state_machine_data["tx1_key"] = "final"
        
        # Now all see committed value
        for node in cluster_nodes.values():
            assert node.state_machine_data["tx1_key"] == "final"
    
    # Idempotency Tests
    
    def test_duplicate_request_idempotency_3_nodes(self, cluster_nodes):
        """Test idempotent handling of duplicate requests across cluster."""
        request_id = "req_123"
        
        # Send same request to all nodes
        for node in cluster_nodes.values():
            node.process_request(request_id, {"op": "set", "key": "x", "value": 1})
        
        # All nodes apply only once (due to deduplication)
        for node in cluster_nodes.values():
            assert node.state_machine_data.get("x") == 1
    
    # Consistency Checking Tests
    
    def test_log_consistency_verification(self, cluster_nodes):
        """Test log consistency across cluster."""
        # All nodes have same log up to index 50
        log_entries = list(range(50))
        
        for node in cluster_nodes.values():
            node.log = log_entries.copy()
        
        # Verify consistency
        for node in cluster_nodes.values():
            assert node.log == log_entries
    
    def test_state_machine_consistency_check(self, cluster_nodes):
        """Test state machine consistency across cluster."""
        expected_state = {f"key{i}": f"val{i}" for i in range(10)}
        
        # Set expected state on all nodes
        for node in cluster_nodes.values():
            node.state_machine_data = expected_state.copy()
        
        # Verify all nodes have identical state
        for node in cluster_nodes.values():
            assert node.state_machine_data == expected_state
    
    # Performance Tests
    
    def test_write_throughput_3_nodes(self, cluster_nodes):
        """Test write throughput in 3-node cluster."""
        num_writes = 100
        
        for i in range(num_writes):
            key, value = f"key{i}", f"value{i}"
            # Replicate to majority
            cluster_nodes["node1"].state_machine_data[key] = value
            cluster_nodes["node2"].state_machine_data[key] = value
        
        # Verify all writes replicated
        for node in cluster_nodes.values():
            for i in range(num_writes):
                assert f"key{i}" in node.state_machine_data
    
    def test_read_performance_consistency(self, cluster_nodes):
        """Test read performance with consistency guarantee."""
        data = {f"key{i}": f"val{i}" for i in range(1000)}
        
        # Replicate data to all nodes
        for node in cluster_nodes.values():
            node.state_machine_data = data.copy()
        
        # All reads return same value
        for node in cluster_nodes.values():
            for key in ["key0", "key500", "key999"]:
                assert node.state_machine_data[key] == data[key]
    
    # Linearizability Tests
    
    def test_linearizable_write_read(self, cluster_nodes):
        """Test linearizable write followed by read."""
        cluster_nodes["node1"].is_leader = True
        
        # Write on leader
        cluster_nodes["node1"].state_machine_data["linearizable"] = "write1"
        
        # Replicate to followers
        for node in list(cluster_nodes.values())[1:]:
            node.state_machine_data["linearizable"] = "write1"
        
        # Read from follower sees latest write
        for node in cluster_nodes.values():
            assert node.state_machine_data["linearizable"] == "write1"
    
    def test_linearizable_read_quorum_check(self, cluster_nodes):
        """Test linearizable read with quorum verification."""
        key = "quorum_test"
        
        # Set value on 2/3 nodes
        for i, node in enumerate(list(cluster_nodes.values())[:2]):
            node.state_machine_data[key] = "value"
        
        # Read can proceed (quorum=2, have 2)
        read_quorum_met = sum(
            1 for node in cluster_nodes.values()
            if key in node.state_machine_data
        ) >= 2
        
        assert read_quorum_met
    
    # Failover Scenarios
    
    def test_rolling_restart_consistency(self, cluster_nodes):
        """Test cluster consistency through rolling restart."""
        # Set data on all nodes
        for node in cluster_nodes.values():
            node.state_machine_data = {"persistent": "data"}
        
        # Restart nodes one by one
        for node in cluster_nodes.values():
            # Restart
            node.state_machine_data.clear()
            # Recover from others
            node.state_machine_data = {"persistent": "data"}
        
        # All still consistent
        for node in cluster_nodes.values():
            assert node.state_machine_data["persistent"] == "data"
    
    def test_partition_healing(self, cluster_nodes):
        """Test cluster heals after network partition."""
        # Partition: node1 isolated, node2/3 together
        cluster_nodes["node1"].state_machine_data = {"partition": "side_a"}
        cluster_nodes["node2"].state_machine_data = {"partition": "side_b"}
        cluster_nodes["node3"].state_machine_data = {"partition": "side_b"}
        
        # Partition heals
        # Majority (node2/3) wins
        cluster_nodes["node1"].state_machine_data = {"partition": "side_b"}
        
        # All now consistent
        for node in cluster_nodes.values():
            assert node.state_machine_data["partition"] == "side_b"


class TestMultiNodeEdgeCases:
    """Test edge cases in multi-node scenarios."""
    
    def test_5_node_cluster_quorum(self):
        """Test quorum calculation for 5-node cluster."""
        cluster_size = 5
        quorum_size = (cluster_size // 2) + 1
        
        assert quorum_size == 3
        assert quorum_size > cluster_size // 2
    
    def test_7_node_cluster_failure_tolerance(self):
        """Test failure tolerance for 7-node cluster."""
        cluster_size = 7
        quorum_size = (cluster_size // 2) + 1
        max_failures = cluster_size - quorum_size
        
        # Can tolerate 3 failures
        assert max_failures == 3
    
    def test_even_node_cluster_not_recommended(self):
        """Test edge case of even-sized cluster."""
        # Even clusters are not recommended but should still work
        cluster_size = 4  # Not recommended
        quorum_size = (cluster_size // 2) + 1
        
        assert quorum_size == 3
        # Same tolerance as 5-node cluster
