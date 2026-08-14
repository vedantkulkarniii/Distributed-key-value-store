"""
Comprehensive tests for cluster management module

Tests cover:
- Node metrics tracking
- Cluster health monitoring
- Quorum validation
- Node join/leave/restart scenarios
- Cluster orchestration
- Status tracking
"""

import pytest
import asyncio
import time
from src.raft.cluster_management import (
    ClusterManager, ClusterOrchestrator, NodeStatus, 
    NodeMetrics, ClusterHealthReport
)


class TestNodeMetrics:
    """Test NodeMetrics class"""
    
    def test_create_node_metrics(self):
        """Test creating node metrics"""
        metrics = NodeMetrics(node_id="node_1")
        assert metrics.node_id == "node_1"
        assert metrics.status == NodeStatus.OFFLINE
        assert metrics.processed_commands == 0
    
    def test_node_healthy_status(self):
        """Test node health check"""
        metrics = NodeMetrics(node_id="node_1", status=NodeStatus.HEALTHY)
        assert metrics.is_healthy()
        
        metrics.status = NodeStatus.UNHEALTHY
        assert not metrics.is_healthy()
    
    def test_health_percentage_calculation(self):
        """Test health percentage calculation"""
        metrics = NodeMetrics(node_id="node_1")
        metrics.processed_commands = 100
        metrics.failed_commands = 10
        
        health = metrics.get_health_percentage()
        assert health == 90.0
    
    def test_health_percentage_no_commands(self):
        """Test health percentage with no commands"""
        metrics = NodeMetrics(node_id="node_1")
        health = metrics.get_health_percentage()
        assert health == 100.0
    
    def test_error_count_increment(self):
        """Test error count increments"""
        metrics = NodeMetrics(node_id="node_1")
        assert metrics.error_count == 0
        
        metrics.error_count += 1
        assert metrics.error_count == 1


class TestClusterManager:
    """Test ClusterManager class"""
    
    @pytest.fixture
    def cluster_manager(self):
        """Create cluster manager for testing"""
        return ClusterManager("node_1", 3)
    
    def test_initialization(self, cluster_manager):
        """Test cluster manager initialization"""
        assert cluster_manager.node_id == "node_1"
        assert cluster_manager.total_nodes == 3
        assert cluster_manager.quorum_size == 2
        assert len(cluster_manager.node_metrics) == 3
    
    def test_initial_quorum(self, cluster_manager):
        """Test initial quorum validation"""
        assert cluster_manager.has_quorum()
    
    @pytest.mark.asyncio
    async def test_heartbeat_received(self, cluster_manager):
        """Test heartbeat reception"""
        await cluster_manager.on_heartbeat_received("node_2", time.time())
        
        metrics = cluster_manager.get_node_metrics("node_2")
        assert metrics.status == NodeStatus.HEALTHY
        assert "node_2" in cluster_manager.active_nodes
    
    @pytest.mark.asyncio
    async def test_heartbeat_timeout(self, cluster_manager):
        """Test heartbeat timeout"""
        await cluster_manager.on_heartbeat_timeout("node_2")
        
        metrics = cluster_manager.get_node_metrics("node_2")
        assert metrics.status == NodeStatus.UNHEALTHY
        assert metrics.error_count == 1
        assert "node_2" not in cluster_manager.active_nodes
    
    @pytest.mark.asyncio
    async def test_node_join(self, cluster_manager):
        """Test node joining cluster"""
        await cluster_manager.node_join("node_4")
        
        assert cluster_manager.total_nodes == 4
        assert "node_4" in cluster_manager.node_metrics
        metrics = cluster_manager.get_node_metrics("node_4")
        assert metrics.status == NodeStatus.BOOTSTRAPPING
    
    @pytest.mark.asyncio
    async def test_node_leave(self, cluster_manager):
        """Test node leaving cluster"""
        await cluster_manager.node_leave("node_2")
        
        metrics = cluster_manager.get_node_metrics("node_2")
        assert metrics.status == NodeStatus.OFFLINE
    
    @pytest.mark.asyncio
    async def test_node_restart(self, cluster_manager):
        """Test node restart"""
        await cluster_manager.node_restart("node_2")
        
        metrics = cluster_manager.get_node_metrics("node_2")
        assert metrics.status == NodeStatus.RECOVERING
        assert metrics.uptime_seconds == 0
    
    @pytest.mark.asyncio
    async def test_quorum_loss(self, cluster_manager):
        """Test quorum loss detection"""
        assert cluster_manager.has_quorum()
        
        await cluster_manager.on_heartbeat_timeout("node_2")
        await cluster_manager.on_heartbeat_timeout("node_3")
        
        assert not cluster_manager.has_quorum()
    
    def test_get_cluster_health(self, cluster_manager):
        """Test cluster health report"""
        health = cluster_manager.get_cluster_health()
        
        assert health.total_nodes == 3
        assert health.healthy_nodes >= 1
        assert health.cluster_quorum == 2
        assert isinstance(health.cluster_stability, float)
    
    def test_cluster_health_stable(self, cluster_manager):
        """Test cluster stability check"""
        health = cluster_manager.get_cluster_health()
        
        if health.quorum_available and health.cluster_stability > 70:
            assert health.is_stable()
    
    @pytest.mark.asyncio
    async def test_replication_lag_update(self, cluster_manager):
        """Test replication lag tracking"""
        await cluster_manager.update_replication_lag("node_2", 50.0)
        
        metrics = cluster_manager.get_node_metrics("node_2")
        assert metrics.replication_lag_ms == 50.0
    
    @pytest.mark.asyncio
    async def test_command_recording(self, cluster_manager):
        """Test command result recording"""
        await cluster_manager.record_command_result("node_1", True)
        await cluster_manager.record_command_result("node_1", False)
        
        metrics = cluster_manager.get_node_metrics("node_1")
        assert metrics.processed_commands == 2
        assert metrics.failed_commands == 1
    
    def test_get_healthy_nodes(self, cluster_manager):
        """Test getting healthy nodes list"""
        healthy = cluster_manager.get_healthy_nodes()
        assert len(healthy) >= 1
        assert "node_1" in healthy
    
    def test_get_all_metrics(self, cluster_manager):
        """Test getting all metrics"""
        all_metrics = cluster_manager.get_all_metrics()
        assert len(all_metrics) == 3
        assert "node_1" in all_metrics
    
    def test_cluster_status_summary(self, cluster_manager):
        """Test status summary string"""
        summary = cluster_manager.get_cluster_status_summary()
        assert "Cluster Status" in summary
        assert "healthy" in summary


class TestClusterHealthReport:
    """Test ClusterHealthReport class"""
    
    def test_create_health_report(self):
        """Test creating health report"""
        report = ClusterHealthReport(
            total_nodes=3,
            healthy_nodes=3,
            unhealthy_nodes=0,
            cluster_quorum=2,
            quorum_available=True,
            average_latency_ms=5.0,
            max_replication_lag_ms=10.0,
            cluster_stability=100.0
        )
        
        assert report.total_nodes == 3
        assert report.is_stable()
    
    def test_health_report_unstable(self):
        """Test unstable health report"""
        report = ClusterHealthReport(
            total_nodes=3,
            healthy_nodes=1,
            unhealthy_nodes=2,
            cluster_quorum=2,
            quorum_available=False,
            average_latency_ms=50.0,
            max_replication_lag_ms=100.0,
            cluster_stability=30.0
        )
        
        assert not report.is_stable()


class TestClusterOrchestrator:
    """Test ClusterOrchestrator class"""
    
    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator for testing"""
        manager = ClusterManager("node_1", 3)
        return ClusterOrchestrator(manager)
    
    @pytest.mark.asyncio
    async def test_scale_up(self, orchestrator):
        """Test scaling up cluster"""
        result = await orchestrator.scale_cluster(5)
        
        assert result
        assert orchestrator.cluster_manager.total_nodes == 5
    
    @pytest.mark.asyncio
    async def test_scale_down(self, orchestrator):
        """Test scaling down cluster"""
        result = await orchestrator.scale_cluster(2)
        
        assert result
        assert orchestrator.cluster_manager.total_nodes == 2
    
    @pytest.mark.asyncio
    async def test_health_check(self, orchestrator):
        """Test health check operation"""
        health = await orchestrator.perform_health_check()
        
        assert isinstance(health, ClusterHealthReport)
        assert health.total_nodes > 0
    
    @pytest.mark.asyncio
    async def test_node_recovery(self, orchestrator):
        """Test node recovery"""
        result = await orchestrator.recover_unhealthy_node("node_2")
        
        assert result
        assert len(orchestrator.operation_history) > 0
    
    @pytest.mark.asyncio
    async def test_operation_history(self, orchestrator):
        """Test operation history tracking"""
        await orchestrator.scale_cluster(5)
        await orchestrator.recover_unhealthy_node("node_1")
        
        assert len(orchestrator.operation_history) == 2
        assert orchestrator.operation_history[0]["type"] == "scale"
        assert orchestrator.operation_history[1]["type"] == "recovery"


class TestMultiNodeScenarios:
    """Test complex multi-node scenarios"""
    
    @pytest.mark.asyncio
    async def test_cascading_failures(self):
        """Test cascading node failures"""
        manager = ClusterManager("node_1", 5)
        
        # Simulate cascading failures
        for i in range(2, 5):
            await manager.on_heartbeat_timeout(f"node_{i}")
        
        assert not manager.has_quorum()
    
    @pytest.mark.asyncio
    async def test_network_partition_recovery(self):
        """Test recovery from network partition"""
        manager = ClusterManager("node_1", 5)
        
        # Simulate partition
        for i in range(2, 5):
            await manager.on_heartbeat_timeout(f"node_{i}")
        
        assert not manager.has_quorum()
        
        # Simulate recovery
        for i in range(2, 5):
            await manager.on_heartbeat_received(f"node_{i}", time.time())
        
        assert manager.has_quorum()
    
    @pytest.mark.asyncio
    async def test_cluster_scale_with_failures(self):
        """Test scaling cluster with existing failures"""
        orchestrator = ClusterOrchestrator(ClusterManager("node_1", 3))
        
        # Create some failures
        await orchestrator.cluster_manager.on_heartbeat_timeout("node_2")
        
        # Scale up
        await orchestrator.scale_cluster(5)
        
        assert orchestrator.cluster_manager.total_nodes == 5
    
    @pytest.mark.asyncio
    async def test_continuous_monitoring(self):
        """Test continuous cluster monitoring"""
        manager = ClusterManager("node_1", 3)
        
        # Simulate continuous heartbeats
        for _ in range(10):
            await manager.on_heartbeat_received("node_2", time.time())
            await manager.on_heartbeat_received("node_3", time.time())
        
        health = manager.get_cluster_health()
        assert health.healthy_nodes >= 2


# Performance tests
class TestClusterPerformance:
    """Test cluster manager performance"""
    
    def test_large_cluster_initialization(self):
        """Test initialization of large cluster"""
        manager = ClusterManager("node_1", 50)
        
        assert manager.total_nodes == 50
        assert len(manager.node_metrics) == 50
    
    @pytest.mark.asyncio
    async def test_many_heartbeats(self):
        """Test handling many heartbeats"""
        manager = ClusterManager("node_1", 10)
        
        start = time.time()
        for i in range(1000):
            node_id = f"node_{(i % 10) + 1}"
            await manager.on_heartbeat_received(node_id, time.time())
        elapsed = time.time() - start
        
        assert elapsed < 5.0  # Should handle 1000 heartbeats in < 5 seconds
    
    @pytest.mark.asyncio
    async def test_frequent_status_updates(self):
        """Test frequent status updates"""
        manager = ClusterManager("node_1", 10)
        
        start = time.time()
        for i in range(500):
            await manager.record_command_result(f"node_{(i % 10) + 1}", i % 2 == 0)
        elapsed = time.time() - start
        
        assert elapsed < 2.0
