"""
Comprehensive tests for ClusterManager.

Tests cover:
- Cluster initialization and lifecycle
- Node join/leave/restart scenarios
- Health monitoring and status tracking
- Quorum validation
- Cluster orchestration
- Metrics aggregation
- Failover scenarios
"""

import pytest
import time
from datetime import datetime, timedelta
from src.raft.cluster_manager import (
    ClusterManager, NodeMetrics, NodeStatus, ClusterMetrics
)


class TestNodeMetrics:
    """Tests for NodeMetrics dataclass."""
    
    def test_node_metrics_initialization(self):
        """Test NodeMetrics initialization."""
        metrics = NodeMetrics(node_id="node-1")
        assert metrics.node_id == "node-1"
        assert metrics.status == NodeStatus.UNKNOWN
        assert metrics.heartbeat_count == 0
        assert metrics.request_count == 0
        assert metrics.error_count == 0
    
    def test_error_rate_calculation_zero_requests(self):
        """Test error rate calculation with zero requests."""
        metrics = NodeMetrics(node_id="node-1")
        assert metrics.get_error_rate() == 0.0
    
    def test_error_rate_calculation_with_errors(self):
        """Test error rate calculation with errors."""
        metrics = NodeMetrics(node_id="node-1")
        metrics.request_count = 100
        metrics.error_count = 25
        assert metrics.get_error_rate() == 25.0
    
    def test_is_healthy_healthy_status(self):
        """Test is_healthy with healthy status."""
        metrics = NodeMetrics(node_id="node-1", status=NodeStatus.HEALTHY)
        assert metrics.is_healthy() is True
    
    def test_is_healthy_unhealthy_status(self):
        """Test is_healthy with unhealthy status."""
        metrics = NodeMetrics(node_id="node-1", status=NodeStatus.UNHEALTHY)
        assert metrics.is_healthy() is False
    
    def test_to_dict_conversion(self):
        """Test conversion to dictionary."""
        metrics = NodeMetrics(
            node_id="node-1",
            status=NodeStatus.HEALTHY,
            heartbeat_count=10,
            latency_ms=5.5
        )
        data = metrics.to_dict()
        assert data["node_id"] == "node-1"
        assert data["status"] == "healthy"
        assert data["heartbeat_count"] == 10
        assert data["latency_ms"] == 5.5


class TestClusterMetrics:
    """Tests for ClusterMetrics dataclass."""
    
    def test_cluster_metrics_initialization(self):
        """Test ClusterMetrics initialization."""
        metrics = ClusterMetrics()
        assert metrics.total_nodes == 0
        assert metrics.healthy_nodes == 0
        assert metrics.is_quorum_available is False
    
    def test_cluster_health_critical(self):
        """Test cluster health as critical."""
        metrics = ClusterMetrics(is_quorum_available=False)
        assert metrics.get_cluster_health() == "critical"
    
    def test_cluster_health_degraded(self):
        """Test cluster health as degraded."""
        metrics = ClusterMetrics(
            total_nodes=3,
            healthy_nodes=2,
            unhealthy_nodes=1,
            is_quorum_available=True
        )
        assert metrics.get_cluster_health() == "degraded"
    
    def test_cluster_health_healthy(self):
        """Test cluster health as healthy."""
        metrics = ClusterMetrics(
            total_nodes=3,
            healthy_nodes=3,
            unhealthy_nodes=0,
            is_quorum_available=True
        )
        assert metrics.get_cluster_health() == "healthy"
    
    def test_to_dict_conversion(self):
        """Test conversion to dictionary."""
        metrics = ClusterMetrics(
            total_nodes=3,
            healthy_nodes=3,
            current_leader="node-1"
        )
        data = metrics.to_dict()
        assert data["total_nodes"] == 3
        assert data["current_leader"] == "node-1"
        assert "cluster_health" in data


class TestClusterManagerInitialization:
    """Tests for ClusterManager initialization."""
    
    def test_cluster_manager_init(self):
        """Test ClusterManager initialization."""
        nodes = ["node-1", "node-2", "node-3"]
        manager = ClusterManager("node-1", nodes)
        
        assert manager.node_id == "node-1"
        assert len(manager.nodes) == 3
        assert manager.current_leader is None
        assert manager.is_running is False
    
    def test_quorum_calculation_three_nodes(self):
        """Test quorum calculation for 3 nodes."""
        nodes = ["node-1", "node-2", "node-3"]
        manager = ClusterManager("node-1", nodes)
        assert manager.cluster_metrics.quorum_size == 2
    
    def test_quorum_calculation_five_nodes(self):
        """Test quorum calculation for 5 nodes."""
        nodes = ["node-1", "node-2", "node-3", "node-4", "node-5"]
        manager = ClusterManager("node-1", nodes)
        assert manager.cluster_metrics.quorum_size == 3
    
    def test_initial_metrics_created(self):
        """Test initial metrics are created for all nodes."""
        nodes = ["node-1", "node-2", "node-3"]
        manager = ClusterManager("node-1", nodes)
        
        for node in nodes:
            assert node in manager.metrics
            assert manager.metrics[node].status == NodeStatus.UNKNOWN


class TestClusterLifecycle:
    """Tests for cluster start/stop lifecycle."""
    
    def test_start_cluster(self):
        """Test starting the cluster."""
        nodes = ["node-1", "node-2", "node-3"]
        manager = ClusterManager("node-1", nodes)
        
        result = manager.start_cluster()
        assert result is True
        assert manager.is_running is True
        
        for node in nodes:
            assert manager.metrics[node].status == NodeStatus.HEALTHY
    
    def test_stop_cluster(self):
        """Test stopping the cluster."""
        nodes = ["node-1", "node-2", "node-3"]
        manager = ClusterManager("node-1", nodes)
        manager.start_cluster()
        
        result = manager.stop_cluster()
        assert result is True
        assert manager.is_running is False
        
        for node in nodes:
            assert manager.metrics[node].status == NodeStatus.UNKNOWN


class TestNodeJoinLeave:
    """Tests for node join and leave scenarios."""
    
    def test_add_node_success(self):
        """Test adding a new node."""
        nodes = ["node-1", "node-2"]
        manager = ClusterManager("node-1", nodes)
        
        result = manager.add_node("node-3")
        assert result is True
        assert "node-3" in manager.nodes
        assert manager.metrics["node-3"].status == NodeStatus.JOINING
        assert "node-3" in manager.join_queue
    
    def test_add_node_duplicate(self):
        """Test adding a duplicate node."""
        nodes = ["node-1", "node-2"]
        manager = ClusterManager("node-1", nodes)
        
        result = manager.add_node("node-1")
        assert result is False
    
    def test_remove_node_success(self):
        """Test removing a node."""
        nodes = ["node-1", "node-2", "node-3"]
        manager = ClusterManager("node-1", nodes)
        
        result = manager.remove_node("node-3")
        assert result is True
        assert "node-3" not in manager.nodes
        assert manager.metrics["node-3"].status == NodeStatus.LEAVING
        assert "node-3" in manager.leave_queue
    
    def test_remove_nonexistent_node(self):
        """Test removing a non-existent node."""
        nodes = ["node-1", "node-2"]
        manager = ClusterManager("node-1", nodes)
        
        result = manager.remove_node("node-99")
        assert result is False
    
    def test_add_remove_updates_quorum(self):
        """Test that add/remove updates quorum."""
        nodes = ["node-1", "node-2"]
        manager = ClusterManager("node-1", nodes)
        assert manager.cluster_metrics.quorum_size == 1
        
        manager.add_node("node-3")
        assert manager.cluster_metrics.quorum_size == 2
        
        manager.add_node("node-4")
        assert manager.cluster_metrics.quorum_size == 2
        
        manager.remove_node("node-4")
        assert manager.cluster_metrics.quorum_size == 2


class TestNodeRestart:
    """Tests for node restart scenarios."""
    
    def test_restart_node_success(self):
        """Test restarting a node."""
        nodes = ["node-1", "node-2", "node-3"]
        manager = ClusterManager("node-1", nodes)
        manager.start_cluster()
        
        result = manager.restart_node("node-2")
        assert result is True
        assert manager.metrics["node-2"].status == NodeStatus.RESTARTING
        assert "node-2" in manager.restart_queue
    
    def test_restart_nonexistent_node(self):
        """Test restarting a non-existent node."""
        nodes = ["node-1", "node-2"]
        manager = ClusterManager("node-1", nodes)
        
        result = manager.restart_node("node-99")
        assert result is False


class TestHeartbeatAndMetrics:
    """Tests for heartbeat and metrics tracking."""
    
    def test_update_node_heartbeat(self):
        """Test updating node heartbeat."""
        nodes = ["node-1", "node-2"]
        manager = ClusterManager("node-1", nodes)
        
        result = manager.update_node_heartbeat("node-2", latency_ms=5.5)
        assert result is True
        
        metrics = manager.metrics["node-2"]
        assert metrics.heartbeat_count == 1
        assert metrics.latency_ms == 5.5
        assert metrics.last_heartbeat is not None
        assert metrics.status == NodeStatus.HEALTHY
    
    def test_update_node_heartbeat_nonexistent(self):
        """Test updating heartbeat for non-existent node."""
        nodes = ["node-1", "node-2"]
        manager = ClusterManager("node-1", nodes)
        
        result = manager.update_node_heartbeat("node-99")
        assert result is False
    
    def test_update_node_metrics_healthy(self):
        """Test updating node metrics to healthy."""
        nodes = ["node-1", "node-2"]
        manager = ClusterManager("node-1", nodes)
        
        result = manager.update_node_metrics(
            "node-2",
            request_count=100,
            error_count=1,
            cpu_usage=30.0,
            memory_usage=50.0,
            replication_lag=5
        )
        assert result is True
        
        metrics = manager.metrics["node-2"]
        assert metrics.request_count == 100
        assert metrics.error_count == 1
        assert metrics.cpu_usage_percent == 30.0
        assert metrics.memory_usage_percent == 50.0
        assert metrics.log_replication_lag == 5
        assert metrics.status == NodeStatus.HEALTHY
    
    def test_update_node_metrics_degraded(self):
        """Test updating node metrics to degraded."""
        nodes = ["node-1", "node-2"]
        manager = ClusterManager("node-1", nodes)
        
        result = manager.update_node_metrics(
            "node-2",
            request_count=100,
            error_count=20,
            cpu_usage=75.0,
            memory_usage=60.0
        )
        assert result is True
        assert manager.metrics["node-2"].status == NodeStatus.DEGRADED
    
    def test_update_node_metrics_unhealthy(self):
        """Test updating node metrics to unhealthy."""
        nodes = ["node-1", "node-2"]
        manager = ClusterManager("node-1", nodes)
        
        result = manager.update_node_metrics(
            "node-2",
            request_count=100,
            error_count=60,
            cpu_usage=95.0
        )
        assert result is True
        assert manager.metrics["node-2"].status == NodeStatus.UNHEALTHY


class TestLeaderManagement:
    """Tests for leader management."""
    
    def test_set_leader_valid(self):
        """Test setting a valid leader."""
        nodes = ["node-1", "node-2", "node-3"]
        manager = ClusterManager("node-1", nodes)
        
        result = manager.set_leader("node-1")
        assert result is True
        assert manager.current_leader == "node-1"
        assert manager.cluster_metrics.current_leader == "node-1"
    
    def test_set_leader_invalid(self):
        """Test setting an invalid leader."""
        nodes = ["node-1", "node-2"]
        manager = ClusterManager("node-1", nodes)
        
        result = manager.set_leader("node-99")
        assert result is False


class TestQuorumValidation:
    """Tests for quorum validation."""
    
    def test_quorum_available_all_healthy(self):
        """Test quorum available when all nodes healthy."""
        nodes = ["node-1", "node-2", "node-3"]
        manager = ClusterManager("node-1", nodes)
        manager.start_cluster()
        
        result = manager.is_quorum_available()
        assert result is True
    
    def test_quorum_available_one_unhealthy(self):
        """Test quorum available with one unhealthy node."""
        nodes = ["node-1", "node-2", "node-3"]
        manager = ClusterManager("node-1", nodes)
        manager.start_cluster()
        manager.metrics["node-3"].status = NodeStatus.UNHEALTHY
        
        result = manager.is_quorum_available()
        assert result is True
    
    def test_quorum_unavailable_majority_unhealthy(self):
        """Test quorum unavailable when majority unhealthy."""
        nodes = ["node-1", "node-2", "node-3"]
        manager = ClusterManager("node-1", nodes)
        manager.start_cluster()
        manager.metrics["node-2"].status = NodeStatus.UNHEALTHY
        manager.metrics["node-3"].status = NodeStatus.UNHEALTHY
        
        result = manager.is_quorum_available()
        assert result is False


class TestHealthyUnhealthyNodes:
    """Tests for getting healthy/unhealthy nodes."""
    
    def test_get_healthy_nodes(self):
        """Test getting list of healthy nodes."""
        nodes = ["node-1", "node-2", "node-3"]
        manager = ClusterManager("node-1", nodes)
        manager.start_cluster()
        manager.metrics["node-3"].status = NodeStatus.UNHEALTHY
        
        healthy = manager.get_healthy_nodes()
        assert len(healthy) == 2
        assert "node-1" in healthy
        assert "node-2" in healthy
    
    def test_get_unhealthy_nodes(self):
        """Test getting list of unhealthy nodes."""
        nodes = ["node-1", "node-2", "node-3"]
        manager = ClusterManager("node-1", nodes)
        manager.start_cluster()
        manager.metrics["node-2"].status = NodeStatus.UNHEALTHY
        manager.metrics["node-3"].status = NodeStatus.DEGRADED
        
        unhealthy = manager.get_unhealthy_nodes()
        assert "node-2" in unhealthy


class TestNodeMetricsRetrieval:
    """Tests for retrieving node metrics."""
    
    def test_get_node_metrics_valid(self):
        """Test getting metrics for valid node."""
        nodes = ["node-1", "node-2"]
        manager = ClusterManager("node-1", nodes)
        manager.update_node_heartbeat("node-2", latency_ms=10.0)
        
        metrics = manager.get_node_metrics("node-2")
        assert metrics is not None
        assert metrics["node_id"] == "node-2"
        assert metrics["latency_ms"] == 10.0
    
    def test_get_node_metrics_invalid(self):
        """Test getting metrics for invalid node."""
        nodes = ["node-1", "node-2"]
        manager = ClusterManager("node-1", nodes)
        
        metrics = manager.get_node_metrics("node-99")
        assert metrics is None


class TestClusterMetricsAggregation:
    """Tests for cluster-wide metrics aggregation."""
    
    def test_update_cluster_metrics(self):
        """Test updating cluster metrics."""
        nodes = ["node-1", "node-2", "node-3"]
        manager = ClusterManager("node-1", nodes)
        manager.start_cluster()
        
        manager.update_node_heartbeat("node-1", latency_ms=5.0)
        manager.update_node_heartbeat("node-2", latency_ms=6.0)
        manager.update_node_heartbeat("node-3", latency_ms=7.0)
        
        cluster_metrics = manager.update_cluster_metrics()
        assert cluster_metrics.total_nodes == 3
        assert cluster_metrics.healthy_nodes == 3
        assert cluster_metrics.average_latency_ms == pytest.approx(6.0, rel=0.1)
    
    def test_cluster_status_all_healthy(self):
        """Test cluster status when all nodes healthy."""
        nodes = ["node-1", "node-2", "node-3"]
        manager = ClusterManager("node-1", nodes)
        manager.start_cluster()
        manager.set_leader("node-1")
        
        status = manager.get_cluster_status()
        assert status["cluster_metrics"]["total_nodes"] == 3
        assert status["cluster_metrics"]["healthy_nodes"] == 3
        assert status["cluster_metrics"]["current_leader"] == "node-1"
        assert len(status["nodes"]) == 3
    
    def test_cluster_status_mixed_health(self):
        """Test cluster status with mixed node health."""
        nodes = ["node-1", "node-2", "node-3"]
        manager = ClusterManager("node-1", nodes)
        manager.start_cluster()
        manager.metrics["node-3"].status = NodeStatus.UNHEALTHY
        
        status = manager.get_cluster_status()
        assert status["cluster_metrics"]["healthy_nodes"] == 2
        assert status["cluster_metrics"]["unhealthy_nodes"] == 1


class TestSlowestNodes:
    """Tests for identifying slowest nodes."""
    
    def test_get_slowest_nodes(self):
        """Test getting slowest nodes."""
        nodes = ["node-1", "node-2", "node-3"]
        manager = ClusterManager("node-1", nodes)
        
        manager.update_node_heartbeat("node-1", latency_ms=5.0)
        manager.update_node_heartbeat("node-2", latency_ms=15.0)
        manager.update_node_heartbeat("node-3", latency_ms=10.0)
        
        slowest = manager.get_slowest_nodes(2)
        assert len(slowest) == 2
        assert slowest[0][0] == "node-2"
        assert slowest[0][1] == 15.0
        assert slowest[1][0] == "node-3"


class TestClusterScaling:
    """Tests for cluster scaling."""
    
    def test_scale_cluster_up(self):
        """Test scaling cluster up."""
        nodes = ["node-1", "node-2"]
        manager = ClusterManager("node-1", nodes)
        
        result = manager.scale_cluster(4)
        assert result is True
        assert len(manager.nodes) == 4
    
    def test_scale_cluster_down(self):
        """Test scaling cluster down."""
        nodes = ["node-1", "node-2", "node-3", "node-4"]
        manager = ClusterManager("node-1", nodes)
        
        result = manager.scale_cluster(2)
        assert result is True
        assert len(manager.nodes) == 2
    
    def test_scale_cluster_no_change(self):
        """Test scaling cluster with no change."""
        nodes = ["node-1", "node-2", "node-3"]
        manager = ClusterManager("node-1", nodes)
        
        result = manager.scale_cluster(3)
        assert result is True
        assert len(manager.nodes) == 3


class TestMembership:
    """Tests for membership management."""
    
    def test_get_member_list(self):
        """Test getting member list."""
        nodes = ["node-3", "node-1", "node-2"]
        manager = ClusterManager("node-1", nodes)
        
        members = manager.get_member_list()
        assert members == ["node-1", "node-2", "node-3"]


class TestClusterIntegrity:
    """Tests for cluster integrity validation."""
    
    def test_validate_integrity_healthy_cluster(self):
        """Test validating healthy cluster."""
        nodes = ["node-1", "node-2", "node-3"]
        manager = ClusterManager("node-1", nodes)
        manager.start_cluster()
        manager.set_leader("node-1")
        
        is_valid, issues = manager.validate_cluster_integrity()
        assert is_valid is True
        assert len(issues) == 0
    
    def test_validate_integrity_no_quorum(self):
        """Test validating cluster with no quorum."""
        nodes = ["node-1", "node-2", "node-3"]
        manager = ClusterManager("node-1", nodes)
        manager.start_cluster()
        manager.metrics["node-2"].status = NodeStatus.UNHEALTHY
        manager.metrics["node-3"].status = NodeStatus.UNHEALTHY
        
        is_valid, issues = manager.validate_cluster_integrity()
        assert is_valid is False
        assert "Quorum not available" in issues
    
    def test_validate_integrity_invalid_leader(self):
        """Test validating cluster with invalid leader."""
        nodes = ["node-1", "node-2"]
        manager = ClusterManager("node-1", nodes)
        manager.current_leader = "node-99"
        
        is_valid, issues = manager.validate_cluster_integrity()
        assert is_valid is False
        assert any("Leader" in issue for issue in issues)


class TestComplexScenarios:
    """Tests for complex cluster scenarios."""
    
    def test_sequential_node_failures(self):
        """Test sequential node failures."""
        nodes = ["node-1", "node-2", "node-3"]
        manager = ClusterManager("node-1", nodes)
        manager.start_cluster()
        
        assert manager.is_quorum_available() is True
        
        manager.metrics["node-2"].status = NodeStatus.UNHEALTHY
        assert manager.is_quorum_available() is True
        
        manager.metrics["node-3"].status = NodeStatus.UNHEALTHY
        assert manager.is_quorum_available() is False
    
    def test_mixed_operations(self):
        """Test mixed cluster operations."""
        nodes = ["node-1", "node-2"]
        manager = ClusterManager("node-1", nodes)
        manager.start_cluster()
        manager.set_leader("node-1")
        
        # Add nodes
        manager.add_node("node-3")
        manager.add_node("node-4")
        
        # Update metrics
        manager.update_node_heartbeat("node-3", 5.0)
        manager.update_node_metrics("node-3", request_count=50, error_count=1)
        
        # Remove a node
        manager.remove_node("node-4")
        
        status = manager.get_cluster_status()
        assert len(status["nodes"]) == 3
        assert manager.current_leader == "node-1"
    
    def test_rolling_restart_scenario(self):
        """Test rolling restart scenario."""
        nodes = ["node-1", "node-2", "node-3"]
        manager = ClusterManager("node-1", nodes)
        manager.start_cluster()
        
        for node in nodes:
            manager.restart_node(node)
            assert node in manager.restart_queue
            assert manager.metrics[node].status == NodeStatus.RESTARTING


class TestEdgeCases:
    """Tests for edge cases."""
    
    def test_single_node_cluster(self):
        """Test single node cluster."""
        manager = ClusterManager("node-1", ["node-1"])
        assert manager.cluster_metrics.quorum_size == 1
        assert manager.is_quorum_available() is False  # Unknown status
    
    def test_empty_cluster_operations(self):
        """Test operations on single node."""
        manager = ClusterManager("node-1", ["node-1"])
        manager.start_cluster()
        
        healthy = manager.get_healthy_nodes()
        assert "node-1" in healthy
    
    def test_negative_metrics_handling(self):
        """Test handling of edge case metric values."""
        nodes = ["node-1"]
        manager = ClusterManager("node-1", nodes)
        
        # Should handle gracefully
        result = manager.update_node_metrics(
            "node-1",
            request_count=0,
            error_count=0,
            cpu_usage=0.0,
            memory_usage=0.0
        )
        assert result is True
