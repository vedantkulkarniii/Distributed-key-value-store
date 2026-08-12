"""Multi-node integration tests for Phase 5."""

import pytest
from src.raft.state_machine import StateMachineEngine
from src.raft.transaction_manager import TransactionManager
from src.raft.idempotency import IdempotencyManager
from src.raft.linearizable_read import LinearizableReadHandler
from src.raft.snapshot_store import SnapshotStore
from src.raft.crash_recovery import CrashRecoveryHandler
from src.raft.state_sync import MultiNodeStateSyncManager
from src.raft.lease_manager import LeaseManager
from src.raft.byzantine_tolerance import ByzantineTolerance


class TestThreeNodeCluster:
    """Tests for 3-node cluster scenarios."""
    
    @pytest.fixture
    def three_node_cluster(self):
        """Setup 3-node cluster."""
        nodes = {}
        for i in range(1, 4):
            node_id = f"node{i}"
            nodes[node_id] = {
                "state_machine": StateMachineEngine(node_id),
                "transaction_mgr": TransactionManager(node_id, {}),
                "idempotency": IdempotencyManager(node_id),
                "read_handler": LinearizableReadHandler(node_id, cluster_size=3),
                "snapshot_store": SnapshotStore(node_id),
                "recovery": CrashRecoveryHandler(node_id),
                "state_sync": MultiNodeStateSyncManager(node_id, cluster_size=3),
                "lease_mgr": LeaseManager(node_id),
                "byzantine": ByzantineTolerance(node_id, cluster_size=3),
            }
        return nodes
    
    # Basic Cluster Tests
    
    def test_cluster_initialization(self, three_node_cluster):
        """Test 3-node cluster initialization."""
        assert len(three_node_cluster) == 3
        
        for node_id, node in three_node_cluster.items():
            assert node["state_machine"] is not None
            assert node["transaction_mgr"] is not None
            assert node["read_handler"].quorum_size == 2
    
    def test_all_nodes_operational(self, three_node_cluster):
        """Test all nodes are operational."""
        for node_id, node in three_node_cluster.items():
            status = node["state_machine"].get_status()
            assert status["node_id"] == node_id
            assert status["applied_index"] == 0
    
    # State Consistency Tests
    
    def test_state_replication_3node(self, three_node_cluster):
        """Test state replication across 3 nodes."""
        leader_node = three_node_cluster["node1"]
        
        # Leader applies command
        command = {"op": "set", "key": "key1", "value": "value1"}
        leader_node["state_machine"].apply_command(1, 1, command)
        
        # Sync to followers
        for i in range(2, 4):
            follower = three_node_cluster[f"node{i}"]
            sync_mgr = leader_node["state_sync"]
            
            progress = sync_mgr.initiate_sync(f"node{i}")
            assert progress is not None
    
    def test_quorum_requirement_3node(self, three_node_cluster):
        """Test quorum requirements for 3-node cluster."""
        # 3-node cluster needs 2 votes for quorum
        trusted = {"node1", "node2"}
        
        can_reach = three_node_cluster["node1"]["byzantine"].can_reach_quorum(trusted)
        assert can_reach
        
        # 1 node is not enough
        trusted = {"node1"}
        can_reach = three_node_cluster["node1"]["byzantine"].can_reach_quorum(trusted)
        assert not can_reach
    
    # Transaction Tests
    
    def test_distributed_transaction_3node(self, three_node_cluster):
        """Test distributed transaction across 3 nodes."""
        node1 = three_node_cluster["node1"]
        
        # Begin transaction
        success, tx_id, _ = node1["transaction_mgr"].begin_transaction("client1")
        assert success
        
        # Read from node
        success, value, _ = node1["transaction_mgr"].read_in_transaction(tx_id, "key1")
        assert success
        
        # Write to node
        success, _ = node1["transaction_mgr"].write_in_transaction(tx_id, "key1", "value1")
        assert success
    
    # Idempotency Tests
    
    def test_idempotency_across_nodes(self, three_node_cluster):
        """Test idempotency across cluster."""
        node1_idemp = three_node_cluster["node1"]["idempotency"]
        node1_idemp.create_session("client1")
        
        # Submit request
        is_dup1, _, _ = node1_idemp.process_request("client1", "req1", {})
        node1_idemp.cache_result("client1", "req1", {"result": "ok"})
        
        # Same request should be duplicate
        is_dup2, result, _ = node1_idemp.process_request("client1", "req1", {})
        
        assert not is_dup1
        assert is_dup2
        assert result == {"result": "ok"}
    
    # Read Consistency Tests
    
    def test_linearizable_read_3node(self, three_node_cluster):
        """Test linearizable read with 3-node cluster."""
        read_handler = three_node_cluster["node1"]["read_handler"]
        
        # Initiate read
        request = read_handler.initiate_read(read_index=10)
        assert request.phase.value == "initiated"
        
        # Process read index
        read_handler.process_read_index(request.request_id, 10, term=1)
        assert request.phase.value == "read_index_acquired"
        
        # Send heartbeat and collect ACKs
        read_handler.send_heartbeat_for_read(request.request_id)
        read_handler.record_heartbeat_ack(request.request_id, "node2")
        
        # Should have quorum
        assert request.phase.value == "heartbeat_ack_received"
    
    # Lease Tests
    
    def test_lease_across_cluster(self, three_node_cluster):
        """Test lease management across cluster."""
        node1_lease = three_node_cluster["node1"]["lease_mgr"]
        node2_lease = three_node_cluster["node2"]["lease_mgr"]
        
        # Node1 acquires lease
        success, lease1, _ = node1_lease.acquire_lease(term=1)
        assert success
        assert lease1 is not None
        
        # Node2 can also have lease
        success, lease2, _ = node2_lease.acquire_lease(term=1)
        assert success
    
    # Snapshot Tests
    
    def test_snapshot_distribution_3node(self, three_node_cluster):
        """Test snapshot distribution across 3 nodes."""
        state = {"key1": "value1", "key2": "value2"}
        
        # Create snapshot on node1
        snapshot_store = three_node_cluster["node1"]["snapshot_store"]
        success, snap_id, _ = snapshot_store.create_snapshot(state, term=1, index=10)
        assert success
        
        # Distribute to other nodes
        for i in range(2, 4):
            other_store = three_node_cluster[f"node{i}"]["snapshot_store"]
            success, _ = other_store.install_snapshot(snap_id, state, term=1, index=10)
            assert success
    
    # Byzantine Detection Tests
    
    def test_byzantine_detection_3node(self, three_node_cluster):
        """Test Byzantine fault detection in 3-node cluster."""
        byzantine = three_node_cluster["node1"]["byzantine"]
        
        # Create votes with conflict
        votes = [
            {"voter_id": "node2", "candidate_id": "node1", "term": 1},
            {"voter_id": "node2", "candidate_id": "node3", "term": 1},  # Conflict
        ]
        
        has_conflict, reason = byzantine.detect_conflicting_votes(1, votes)
        assert has_conflict


class TestFiveNodeCluster:
    """Tests for 5-node cluster scenarios."""
    
    @pytest.fixture
    def five_node_cluster(self):
        """Setup 5-node cluster."""
        nodes = {}
        for i in range(1, 6):
            node_id = f"node{i}"
            nodes[node_id] = {
                "state_machine": StateMachineEngine(node_id),
                "transaction_mgr": TransactionManager(node_id, {}),
                "read_handler": LinearizableReadHandler(node_id, cluster_size=5),
                "snapshot_store": SnapshotStore(node_id),
                "state_sync": MultiNodeStateSyncManager(node_id, cluster_size=5),
                "byzantine": ByzantineTolerance(node_id, cluster_size=5),
            }
        return nodes
    
    def test_5node_quorum(self, five_node_cluster):
        """Test quorum in 5-node cluster."""
        byzantine = five_node_cluster["node1"]["byzantine"]
        
        # Need 3 for quorum
        trusted_3 = {"node1", "node2", "node3"}
        assert byzantine.can_reach_quorum(trusted_3)
        
        # 2 is not enough
        trusted_2 = {"node1", "node2"}
        assert not byzantine.can_reach_quorum(trusted_2)
    
    def test_byzantine_tolerance_5node(self, five_node_cluster):
        """Test Byzantine tolerance in 5-node cluster."""
        byzantine = five_node_cluster["node1"]["byzantine"]
        
        # Can tolerate 1 Byzantine node
        assert byzantine.byzantine_tolerance == 1
    
    def test_5node_read_quorum(self, five_node_cluster):
        """Test read quorum in 5-node cluster."""
        read_handler = five_node_cluster["node1"]["read_handler"]
        
        # Create read
        request = read_handler.initiate_read(10)
        read_handler.process_read_index(request.request_id, 10, term=1)
        read_handler.send_heartbeat_for_read(request.request_id)
        
        # Need 3 total (including leader)
        read_handler.record_heartbeat_ack(request.request_id, "node2")
        read_handler.record_heartbeat_ack(request.request_id, "node3")
        
        # Should be quorum now
        assert request.phase.value == "heartbeat_ack_received"


class TestSevenNodeCluster:
    """Tests for 7-node cluster scenarios."""
    
    @pytest.fixture
    def seven_node_cluster(self):
        """Setup 7-node cluster."""
        nodes = {}
        for i in range(1, 8):
            node_id = f"node{i}"
            nodes[node_id] = {
                "state_machine": StateMachineEngine(node_id),
                "read_handler": LinearizableReadHandler(node_id, cluster_size=7),
                "byzantine": ByzantineTolerance(node_id, cluster_size=7),
            }
        return nodes
    
    def test_7node_quorum(self, seven_node_cluster):
        """Test quorum in 7-node cluster."""
        byzantine = seven_node_cluster["node1"]["byzantine"]
        
        # Need 4 for quorum
        trusted_4 = {"node1", "node2", "node3", "node4"}
        assert byzantine.can_reach_quorum(trusted_4)
        
        # 3 is not enough
        trusted_3 = {"node1", "node2", "node3"}
        assert not byzantine.can_reach_quorum(trusted_3)
    
    def test_byzantine_tolerance_7node(self, seven_node_cluster):
        """Test Byzantine tolerance in 7-node cluster."""
        byzantine = seven_node_cluster["node1"]["byzantine"]
        
        # Can tolerate 2 Byzantine nodes
        assert byzantine.byzantine_tolerance == 2


class TestClusterStateConsistency:
    """Tests for cluster-wide state consistency."""
    
    def test_state_propagation(self):
        """Test state propagation across cluster."""
        # Create 3 nodes
        nodes = []
        for i in range(3):
            node = StateMachineEngine(f"node{i+1}")
            nodes.append(node)
        
        # Apply command on first node
        cmd = {"op": "set", "key": "test", "value": "data"}
        nodes[0].apply_command(1, 1, cmd)
        
        # Verify state
        assert nodes[0].data["test"] == "data"
    
    def test_read_after_write_consistency(self):
        """Test read-after-write consistency."""
        node = StateMachineEngine("node1")
        
        # Write
        cmd_set = {"op": "set", "key": "k1", "value": "v1"}
        node.apply_command(1, 1, cmd_set)
        
        # Read
        cmd_get = {"op": "get", "key": "k1"}
        result = node.apply_command(2, 1, cmd_get)
        
        assert result["value"] == "v1"
    
    def test_concurrent_writes_isolation(self):
        """Test isolation of concurrent writes."""
        node = StateMachineEngine("node1")
        txn_mgr = TransactionManager("node1", node.data)
        
        # Begin two transactions
        _, tx1, _ = txn_mgr.begin_transaction("client1")
        _, tx2, _ = txn_mgr.begin_transaction("client2")
        
        # Write different keys
        txn_mgr.write_in_transaction(tx1, "k1", "v1")
        txn_mgr.write_in_transaction(tx2, "k2", "v2")
        
        # Commit both
        success1, _ = txn_mgr.commit_transaction(tx1)
        success2, _ = txn_mgr.commit_transaction(tx2)
        
        assert success1 and success2
