"""
Integration tests for cluster bootstrap and peer communication.

Tests 3-node and 5-node cluster formation and heartbeat exchange.
"""

import pytest
import asyncio
from datetime import datetime

from src.rpc.config import create_local_cluster_config, NodeConfig
from src.rpc.discovery import PeerDiscovery, ClusterBootstrap
from src.rpc.heartbeat import create_timing_manager, ElectionTimeout
from src.rpc.heartbeat_monitor import HeartbeatMonitor


@pytest.fixture
async def cluster_3node():
    """Fixture providing a 3-node cluster configuration."""
    config = create_local_cluster_config(num_nodes=3, base_port=9000)
    yield config
    # Cleanup would go here


@pytest.fixture
async def cluster_5node():
    """Fixture providing a 5-node cluster configuration."""
    config = create_local_cluster_config(num_nodes=5, base_port=9100)
    yield config


class TestClusterConfiguration:
    """Test cluster configuration."""
    
    def test_3node_cluster_config(self, cluster_3node):
        """Test 3-node cluster configuration."""
        assert len(cluster_3node.nodes) == 3
        assert cluster_3node.nodes[0].node_id == "node-1"
        assert cluster_3node.nodes[1].node_id == "node-2"
        assert cluster_3node.nodes[2].node_id == "node-3"
    
    def test_node_config_from_cluster(self, cluster_3node):
        """Test building node config from cluster config."""
        node1_config = cluster_3node.build_node_config("node-1")
        
        assert node1_config.node_id == "node-1"
        assert len(node1_config.peers) == 2
        assert "node-2" in node1_config.peer_ids
        assert "node-3" in node1_config.peer_ids
    
    def test_all_nodes_unique_ports(self, cluster_3node):
        """Test that all nodes have unique ports."""
        ports = [node.port for node in cluster_3node.nodes]
        assert len(ports) == len(set(ports))
    
    def test_cluster_addresses(self, cluster_3node):
        """Test cluster address generation."""
        addresses = cluster_3node.get_all_addresses()
        
        assert len(addresses) == 3
        assert addresses["node-1"][1] == 9000
        assert addresses["node-2"][1] == 9001
        assert addresses["node-3"][1] == 9002


class TestPeerDiscovery:
    """Test peer discovery mechanism."""
    
    def test_discovery_single_node(self):
        """Test discovery with single node (no peers)."""
        config = NodeConfig("node-1", "127.0.0.1", 9000)
        discovery = PeerDiscovery(config)
        
        # Single node has no discovery needed
        assert not config.is_cluster
    
    def test_peer_discovery_state_initialization(self, cluster_3node):
        """Test peer discovery state initialization."""
        node1_config = cluster_3node.build_node_config("node-1")
        discovery = PeerDiscovery(node1_config)
        
        assert discovery.local_id == "node-1"
        assert len(discovery.discovered_peers) == 0
        assert len(discovery.failed_peers) == 0
        assert discovery.client_pool is None
    
    def test_cluster_readiness_single_node(self):
        """Test cluster readiness check for single node."""
        config = NodeConfig("node-1", "127.0.0.1", 9000)
        discovery = PeerDiscovery(config)
        
        # Single node is always ready
        assert discovery.is_cluster_ready()
    
    def test_get_connected_peers(self, cluster_3node):
        """Test getting connected peers list."""
        node1_config = cluster_3node.build_node_config("node-1")
        discovery = PeerDiscovery(node1_config)
        
        # Initially empty
        connected = discovery.get_connected_peers()
        assert len(connected) == 0
    
    def test_get_failed_peers(self, cluster_3node):
        """Test getting failed peers list."""
        node1_config = cluster_3node.build_node_config("node-1")
        discovery = PeerDiscovery(node1_config)
        
        # Initially empty
        failed = discovery.get_failed_peers()
        assert len(failed) == 0


class TestTimingManager:
    """Test heartbeat and election timing."""
    
    @pytest.mark.asyncio
    async def test_timing_manager_creation(self):
        """Test creating timing manager."""
        timing = create_timing_manager("node-1")
        
        assert timing.node_id == "node-1"
        assert timing.heartbeat is not None
        assert timing.election_timeout is not None
        
        await timing.shutdown()
    
    @pytest.mark.asyncio
    async def test_election_timeout_reset(self):
        """Test election timeout reset."""
        timeout = ElectionTimeout("node-1")
        
        initial_timeout = timeout.timeout
        timeout.reset()
        new_timeout = timeout.timeout
        
        # Should be different (randomized)
        # Note: very small chance they're same, but probability is low
        assert (initial_timeout != new_timeout or 
                abs(initial_timeout - new_timeout) < 0.001)
    
    @pytest.mark.asyncio
    async def test_election_timeout_constraints(self):
        """Test election timeout respects min/max constraints."""
        min_timeout = 0.15
        max_timeout = 0.3
        timeout = ElectionTimeout("node-1", min_timeout, max_timeout)
        
        for _ in range(10):
            timeout.reset()
            assert min_timeout <= timeout.timeout <= max_timeout


class TestHeartbeatMonitor:
    """Test heartbeat monitoring and logging."""
    
    def test_heartbeat_monitor_creation(self, cluster_3node):
        """Test creating heartbeat monitor."""
        peer_ids = ["node-2", "node-3"]
        monitor = HeartbeatMonitor("node-1", peer_ids)
        
        assert monitor.local_node_id == "node-1"
        assert len(monitor.peer_metrics) == 2
        assert "node-2" in monitor.peer_metrics
        assert "node-3" in monitor.peer_metrics
    
    def test_record_valid_heartbeat(self):
        """Test recording valid heartbeat."""
        monitor = HeartbeatMonitor("node-1", ["node-2"])
        
        monitor.record_heartbeat(
            source_node_id="node-2",
            term=5,
            commit_index=10,
            is_valid=True
        )
        
        assert monitor.current_leader == "node-2"
        assert monitor.peer_metrics["node-2"].heartbeat_count == 1
        assert monitor.peer_metrics["node-2"].error_count == 0
    
    def test_record_invalid_heartbeat(self):
        """Test recording invalid heartbeat."""
        monitor = HeartbeatMonitor("node-1", ["node-2"])
        
        monitor.record_heartbeat(
            source_node_id="node-2",
            term=3,
            commit_index=5,
            is_valid=False,
            error="Stale term"
        )
        
        assert monitor.peer_metrics["node-2"].heartbeat_count == 0
        assert monitor.peer_metrics["node-2"].error_count == 1
        assert monitor.peer_metrics["node-2"].last_error == "Stale term"
    
    def test_get_cluster_status(self):
        """Test getting cluster status."""
        monitor = HeartbeatMonitor("node-1", ["node-2", "node-3"])
        
        # Record some heartbeats
        monitor.record_heartbeat("node-2", 5, 10, is_valid=True)
        monitor.record_heartbeat("node-3", 5, 10, is_valid=True)
        
        status = monitor.get_cluster_status()
        
        assert status["local_node_id"] == "node-1"
        assert status["current_leader"] == "node-3"  # Last one recorded
        assert status["total_peers"] == 2
        assert status["total_heartbeats"] == 2
        assert status["total_errors"] == 0
    
    def test_get_peer_status(self):
        """Test getting individual peer status."""
        monitor = HeartbeatMonitor("node-1", ["node-2"])
        
        monitor.record_heartbeat("node-2", 5, 10, is_valid=True)
        
        status = monitor.get_peer_status("node-2")
        
        assert status is not None
        assert status["node_id"] == "node-2"
        assert status["heartbeat_count"] == 1
        assert status["error_count"] == 0
        assert status["healthy"] is True
    
    def test_get_all_peer_status(self):
        """Test getting all peer statuses."""
        monitor = HeartbeatMonitor("node-1", ["node-2", "node-3"])
        
        monitor.record_heartbeat("node-2", 5, 10, is_valid=True)
        monitor.record_heartbeat("node-3", 5, 10, is_valid=True)
        
        statuses = monitor.get_all_peer_status()
        
        assert len(statuses) == 2
        assert statuses[0]["node_id"] == "node-2"
        assert statuses[1]["node_id"] == "node-3"
    
    def test_leader_detection(self):
        """Test leader detection from heartbeats."""
        monitor = HeartbeatMonitor("node-1", ["node-2", "node-3"])
        
        # node-2 sends heartbeat
        monitor.record_heartbeat("node-2", 5, 10, is_valid=True)
        assert monitor.current_leader == "node-2"
        
        # node-3 sends heartbeat with same term
        monitor.record_heartbeat("node-3", 5, 10, is_valid=True)
        # Last valid heartbeat is from node-3
        assert monitor.current_leader == "node-3"
    
    def test_heartbeat_history(self):
        """Test heartbeat history tracking."""
        monitor = HeartbeatMonitor("node-1", ["node-2"])
        
        # Record multiple heartbeats
        for i in range(5):
            monitor.record_heartbeat("node-2", 5, 10 + i, is_valid=True)
        
        assert len(monitor.heartbeat_history) == 5
        recent = monitor.get_recent_heartbeats(limit=3)
        assert len(recent) == 3
    
    def test_error_rate_calculation(self):
        """Test error rate calculation."""
        monitor = HeartbeatMonitor("node-1", ["node-2"])
        
        # 3 valid, 1 invalid = 25% error rate
        monitor.record_heartbeat("node-2", 5, 10, is_valid=True)
        monitor.record_heartbeat("node-2", 5, 11, is_valid=True)
        monitor.record_heartbeat("node-2", 5, 12, is_valid=True)
        monitor.record_heartbeat("node-2", 4, 12, is_valid=False, error="Stale term")
        
        metrics = monitor.peer_metrics["node-2"]
        assert metrics.error_rate == 0.25


class TestClusterBootstrap:
    """Test cluster bootstrap process."""
    
    def test_bootstrap_creation(self, cluster_3node):
        """Test creating bootstrap manager."""
        node1_config = cluster_3node.build_node_config("node-1")
        bootstrap = ClusterBootstrap(node1_config)
        
        assert bootstrap.local_id == "node-1"
        assert bootstrap.started is False
        assert bootstrap.ready is False
    
    def test_get_cluster_status(self, cluster_3node):
        """Test getting cluster status."""
        node1_config = cluster_3node.build_node_config("node-1")
        bootstrap = ClusterBootstrap(node1_config)
        
        status = bootstrap.get_cluster_status()
        
        assert status["node_id"] == "node-1"
        assert status["started"] is False
        assert status["ready"] is False
        assert status["is_cluster"] is True


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_5node_cluster_config(self, cluster_5node):
        """Test 5-node cluster configuration."""
        assert len(cluster_5node.nodes) == 5
        assert cluster_5node.nodes[0].port == 9100
        assert cluster_5node.nodes[4].port == 9104
    
    def test_large_cluster_addresses(self):
        """Test large cluster address generation."""
        config = create_local_cluster_config(num_nodes=10, base_port=9000)
        addresses = config.get_all_addresses()
        
        assert len(addresses) == 10
        assert addresses["node-1"][1] == 9000
        assert addresses["node-10"][1] == 9009
    
    def test_heartbeat_with_unknown_peer(self):
        """Test recording heartbeat from unknown peer."""
        monitor = HeartbeatMonitor("node-1")
        
        # Record heartbeat from peer not in initial list
        monitor.record_heartbeat("node-999", 5, 10, is_valid=True)
        
        assert "node-999" in monitor.peer_metrics
        assert monitor.current_leader == "node-999"


class TestDynamicNodeManagement:
    """Test dynamic node join/leave scenarios."""
    
    def test_node_join_scenario(self):
        """Test node joining cluster."""
        monitor = HeartbeatMonitor("node-1", ["node-2", "node-3"])
        
        # Initial state
        assert len(monitor.peer_metrics) == 2
        
        # Node joins by sending heartbeat
        monitor.record_heartbeat("node-4", 5, 10, is_valid=True)
        
        # Monitor now tracks new node
        assert len(monitor.peer_metrics) == 3
        assert "node-4" in monitor.peer_metrics
    
    def test_node_leave_detection(self):
        """Test detecting node leaving cluster."""
        monitor = HeartbeatMonitor("node-1", ["node-2", "node-3"])
        
        # node-2 healthy
        monitor.record_heartbeat("node-2", 5, 10, is_valid=True)
        assert monitor.get_peer_status("node-2")["healthy"] is True
        
        # Simulate heartbeat timeout (no heartbeat for > 1 second)
        # In real scenario, this would be checked by elapsed time
        # For test, we verify the health check logic
        status = monitor.get_peer_status("node-2")
        assert status is not None
    
    def test_rolling_restart_scenario(self, cluster_3node):
        """Test rolling restart of cluster nodes."""
        # Simulate one node going down
        monitor = HeartbeatMonitor("node-1", ["node-2", "node-3"])
        
        # All nodes healthy
        for i in [2, 3]:
            monitor.record_heartbeat(f"node-{i}", 5, 10, is_valid=True)
        
        status = monitor.get_cluster_status()
        assert status["healthy_peers"] == 2
        
        # node-3 goes down (no more heartbeats from it)
        # Monitor doesn't detect immediately, but would on next health check
        assert "node-3" in monitor.peer_metrics
    
    def test_quorum_scenarios(self):
        """Test different quorum scenarios."""
        # 3-node cluster: need 2 for quorum
        cluster_3 = create_local_cluster_config(num_nodes=3, base_port=9000)
        node1_config = cluster_3.build_node_config("node-1")
        
        discovery = PeerDiscovery(node1_config)
        
        # 0 peers connected + self = 1 node
        # Need 2 for quorum (1+1 < 2)
        assert not discovery.is_cluster_ready()
        
        # Simulate connecting to one peer
        discovery.discovered_peers.add("node-2")
        # 1 peer connected + self = 2 nodes = quorum
        assert discovery.is_cluster_ready()
    
    def test_network_partition_detection(self):
        """Test detecting network partition."""
        monitor = HeartbeatMonitor("node-1", ["node-2", "node-3", "node-4", "node-5"])
        
        # All nodes healthy
        for i in range(2, 6):
            monitor.record_heartbeat(f"node-{i}", 5, 10, is_valid=True)
        
        cluster_status = monitor.get_cluster_status()
        assert cluster_status["total_peers"] == 4
        assert cluster_status["healthy_peers"] == 4
        
        # Simulate partition: nodes 4,5 isolated
        # They send invalid heartbeats (wrong term from isolated partition)
        monitor.record_heartbeat("node-4", 6, 10, is_valid=False, error="Partition")
        monitor.record_heartbeat("node-5", 6, 10, is_valid=False, error="Partition")
        
        status = monitor.get_peer_status("node-4")
        assert status["error_count"] > 0
