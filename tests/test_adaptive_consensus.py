"""
Tests for adaptive consensus optimization

Covers:
- Consensus metrics tracking
- Adaptive parameter optimization
- Condition detection
- Dynamic quorum sizing
- Performance monitoring
- Trend analysis
"""

import pytest
import asyncio
import time
from src.raft.adaptive_consensus import (
    AdaptiveConsensusOptimizer, DynamicQuorumSizer,
    ConsensusPerformanceMonitor, ConsensusMetrics, ConsensusCondition,
    AdaptiveParameters
)


class TestConsensusMetrics:
    """Test ConsensusMetrics class"""
    
    def test_create_metrics(self):
        """Test creating consensus metrics"""
        metrics = ConsensusMetrics()
        assert metrics.election_count == 0
        assert metrics.leader_changes == 0
    
    def test_ideal_condition(self):
        """Test ideal consensus condition detection"""
        metrics = ConsensusMetrics(
            avg_replication_lag_ms=50,
            leader_changes=2,
            follower_sync_rate=95
        )
        assert metrics.get_condition() == ConsensusCondition.IDEAL
    
    def test_degraded_condition(self):
        """Test degraded consensus condition"""
        metrics = ConsensusMetrics(
            avg_replication_lag_ms=200,
            leader_changes=8,
            follower_sync_rate=80
        )
        assert metrics.get_condition() == ConsensusCondition.DEGRADED
    
    def test_critical_condition(self):
        """Test critical consensus condition"""
        metrics = ConsensusMetrics(
            avg_replication_lag_ms=3000,
            leader_changes=20,
            follower_sync_rate=40
        )
        assert metrics.get_condition() == ConsensusCondition.CRITICAL


class TestAdaptiveParameters:
    """Test AdaptiveParameters class"""
    
    def test_initialization(self):
        """Test parameter initialization"""
        params = AdaptiveParameters()
        assert params.election_timeout_min_ms == 150
        assert params.heartbeat_interval_ms == 50
        assert params.batch_size == 100
    
    def test_scale_for_latency(self):
        """Test scaling parameters for network latency"""
        params = AdaptiveParameters()
        original_timeout = params.election_timeout_min_ms
        
        params.scale_for_latency(100)  # 100ms latency
        
        # Should increase timeouts
        assert params.election_timeout_min_ms > original_timeout
    
    def test_scale_for_high_load(self):
        """Test scaling for high system load"""
        params = AdaptiveParameters()
        original_batch = params.batch_size
        
        params.scale_for_load(85)  # High load
        
        # Should increase batch size
        assert params.batch_size > original_batch
    
    def test_scale_for_low_load(self):
        """Test scaling for low system load"""
        params = AdaptiveParameters()
        original_batch = params.batch_size
        
        params.scale_for_load(20)  # Low load
        
        # Should decrease batch size
        assert params.batch_size < original_batch


class TestAdaptiveConsensusOptimizer:
    """Test AdaptiveConsensusOptimizer class"""
    
    @pytest.fixture
    def optimizer(self):
        """Create optimizer for testing"""
        return AdaptiveConsensusOptimizer()
    
    def test_initialization(self, optimizer):
        """Test optimizer initialization"""
        assert optimizer.parameters is not None
        assert len(optimizer.metrics_history) == 0
    
    @pytest.mark.asyncio
    async def test_record_metrics(self, optimizer):
        """Test recording metrics"""
        metrics = ConsensusMetrics(avg_replication_lag_ms=100)
        await optimizer.record_metrics(metrics)
        
        assert len(optimizer.metrics_history) == 1
    
    @pytest.mark.asyncio
    async def test_optimization_on_critical_condition(self, optimizer):
        """Test optimization triggers on critical condition"""
        # Record critical metrics
        for _ in range(10):
            metrics = ConsensusMetrics(
                avg_replication_lag_ms=2500,
                network_latency_ms=100,
                follower_sync_rate=30
            )
            await optimizer.record_metrics(metrics)
        
        # Check that parameters were adjusted
        assert len(optimizer.adjustment_history) > 0
    
    @pytest.mark.asyncio
    async def test_optimization_on_degraded_condition(self, optimizer):
        """Test optimization on degraded condition"""
        for _ in range(10):
            metrics = ConsensusMetrics(
                avg_replication_lag_ms=400,
                network_latency_ms=30,
                follower_sync_rate=75
            )
            await optimizer.record_metrics(metrics)
        
        assert len(optimizer.adjustment_history) > 0
    
    @pytest.mark.asyncio
    async def test_optimization_on_ideal_condition(self, optimizer):
        """Test optimization on ideal condition"""
        for _ in range(10):
            metrics = ConsensusMetrics(
                avg_replication_lag_ms=40,
                network_latency_ms=5,
                follower_sync_rate=98
            )
            await optimizer.record_metrics(metrics)
        
        # In ideal condition, may optimize for performance
        stats = optimizer.get_optimization_stats()
        assert "current_parameters" in stats
    
    def test_get_current_parameters(self, optimizer):
        """Test getting current parameters"""
        params = optimizer.get_current_parameters()
        assert isinstance(params, AdaptiveParameters)
    
    def test_get_optimization_stats(self, optimizer):
        """Test getting optimization statistics"""
        stats = optimizer.get_optimization_stats()
        assert "total_adjustments" in stats
        assert "current_parameters" in stats
        assert "metrics_history_size" in stats


class TestDynamicQuorumSizer:
    """Test DynamicQuorumSizer class"""
    
    @pytest.fixture
    def quorum_sizer(self):
        """Create quorum sizer for testing"""
        return DynamicQuorumSizer(cluster_size=5)
    
    def test_initialization(self, quorum_sizer):
        """Test quorum sizer initialization"""
        assert quorum_sizer.cluster_size == 5
        assert quorum_sizer.quorum_size == 3  # (5 // 2) + 1
    
    def test_register_node(self, quorum_sizer):
        """Test registering nodes"""
        quorum_sizer.register_node("node_1", reliability=0.95)
        quorum_sizer.register_node("node_2", reliability=0.85)
        
        assert len(quorum_sizer.node_reliability) == 2
    
    def test_update_reliability(self, quorum_sizer):
        """Test updating node reliability"""
        quorum_sizer.register_node("node_1", reliability=0.90)
        quorum_sizer.update_reliability("node_1", reliability=0.95)
        
        assert quorum_sizer.node_reliability["node_1"] == 0.95
    
    def test_calculate_optimal_quorum_static(self, quorum_sizer):
        """Test quorum calculation (static mode)"""
        for i in range(5):
            quorum_sizer.register_node(f"node_{i}", reliability=0.9)
        
        quorum_size, preferred_nodes = quorum_sizer.calculate_optimal_quorum()
        assert quorum_size == 3
    
    def test_calculate_optimal_quorum_dynamic(self, quorum_sizer):
        """Test dynamic quorum calculation"""
        quorum_sizer.dynamic_quorum_enabled = True
        
        # Register nodes with varying reliability
        quorum_sizer.register_node("node_1", reliability=0.99)
        quorum_sizer.register_node("node_2", reliability=0.95)
        quorum_sizer.register_node("node_3", reliability=0.50)
        quorum_sizer.register_node("node_4", reliability=0.40)
        quorum_sizer.register_node("node_5", reliability=0.30)
        
        quorum_size, preferred_nodes = quorum_sizer.calculate_optimal_quorum()
        
        # Should prefer most reliable nodes
        assert preferred_nodes[0] in ["node_1", "node_2"]
    
    def test_reliability_bounds(self, quorum_sizer):
        """Test reliability score bounds"""
        quorum_sizer.update_reliability("node_1", reliability=1.5)
        assert quorum_sizer.node_reliability.get("node_1", 0) <= 1.0
        
        quorum_sizer.update_reliability("node_1", reliability=-0.5)
        assert quorum_sizer.node_reliability.get("node_1", 0) >= 0.0
    
    def test_get_quorum_stats(self, quorum_sizer):
        """Test quorum statistics"""
        for i in range(5):
            quorum_sizer.register_node(f"node_{i}", reliability=0.85 + i*0.02)
        
        stats = quorum_sizer.get_quorum_stats()
        assert "cluster_size" in stats
        assert "static_quorum" in stats
        assert "average_reliability" in stats


class TestConsensusPerformanceMonitor:
    """Test ConsensusPerformanceMonitor class"""
    
    @pytest.fixture
    def monitor(self):
        """Create monitor for testing"""
        return ConsensusPerformanceMonitor()
    
    @pytest.mark.asyncio
    async def test_record_metrics(self, monitor):
        """Test recording metrics"""
        metrics = ConsensusMetrics(avg_replication_lag_ms=100)
        await monitor.record_metrics(metrics)
        
        assert len(monitor.metrics) == 1
    
    @pytest.mark.asyncio
    async def test_alert_on_high_lag(self, monitor):
        """Test alert generation on high lag"""
        for _ in range(10):
            metrics = ConsensusMetrics(avg_replication_lag_ms=1200)
            await monitor.record_metrics(metrics)
        
        report = monitor.get_performance_report()
        assert len(report["alerts"]) > 0
        assert len(report["suggestions"]) > 0
    
    @pytest.mark.asyncio
    async def test_alert_on_frequent_elections(self, monitor):
        """Test alert on frequent elections"""
        for _ in range(10):
            metrics = ConsensusMetrics(election_count=3)
            await monitor.record_metrics(metrics)
        
        report = monitor.get_performance_report()
        assert "alerts" in report
    
    @pytest.mark.asyncio
    async def test_no_alerts_on_good_performance(self, monitor):
        """Test no alerts when performance is good"""
        for _ in range(10):
            metrics = ConsensusMetrics(
                avg_replication_lag_ms=50,
                election_count=1,
                leader_changes=0
            )
            await monitor.record_metrics(metrics)
        
        report = monitor.get_performance_report()
        assert len(report["alerts"]) == 0
    
    @pytest.mark.asyncio
    async def test_performance_trend_improving(self, monitor):
        """Test trend detection (improving)"""
        # Record degraded metrics
        for _ in range(10):
            metrics = ConsensusMetrics(avg_replication_lag_ms=500)
            await monitor.record_metrics(metrics)
        
        # Record improved metrics
        for _ in range(10):
            metrics = ConsensusMetrics(avg_replication_lag_ms=100)
            await monitor.record_metrics(metrics)
        
        trend = monitor.get_performance_trend()
        assert trend["trend"] == "improving"
    
    @pytest.mark.asyncio
    async def test_performance_trend_degrading(self, monitor):
        """Test trend detection (degrading)"""
        # Record good metrics
        for _ in range(10):
            metrics = ConsensusMetrics(avg_replication_lag_ms=100)
            await monitor.record_metrics(metrics)
        
        # Record worse metrics
        for _ in range(10):
            metrics = ConsensusMetrics(avg_replication_lag_ms=500)
            await monitor.record_metrics(metrics)
        
        trend = monitor.get_performance_trend()
        assert trend["trend"] == "degrading"
    
    def test_get_performance_report_no_data(self, monitor):
        """Test report with no data"""
        report = monitor.get_performance_report()
        assert report["status"] == "no_data"


class TestAdaptiveConsensusScenarios:
    """Test complex adaptive consensus scenarios"""
    
    @pytest.mark.asyncio
    async def test_recovery_from_network_issues(self):
        """Test recovery as network improves"""
        optimizer = AdaptiveConsensusOptimizer()
        monitor = ConsensusPerformanceMonitor()
        
        # Simulate network issues
        for _ in range(10):
            metrics = ConsensusMetrics(
                avg_replication_lag_ms=2000,
                network_latency_ms=200,
                follower_sync_rate=50
            )
            await optimizer.record_metrics(metrics)
            await monitor.record_metrics(metrics)
        
        # Network improves
        for _ in range(10):
            metrics = ConsensusMetrics(
                avg_replication_lag_ms=100,
                network_latency_ms=20,
                follower_sync_rate=95
            )
            await optimizer.record_metrics(metrics)
            await monitor.record_metrics(metrics)
        
        # Check trend
        trend = monitor.get_performance_trend()
        assert trend["trend"] == "improving"
    
    @pytest.mark.asyncio
    async def test_heterogeneous_cluster_optimization(self):
        """Test optimization for heterogeneous cluster"""
        quorum_sizer = DynamicQuorumSizer(cluster_size=7)
        quorum_sizer.dynamic_quorum_enabled = True
        
        # Register nodes with mixed reliability
        reliabilities = [0.99, 0.95, 0.90, 0.70, 0.60, 0.50, 0.40]
        for i, rel in enumerate(reliabilities):
            quorum_sizer.register_node(f"node_{i}", reliability=rel)
        
        quorum_size, preferred_nodes = quorum_sizer.calculate_optimal_quorum()
        
        # Should select mostly reliable nodes
        selected_reliabilities = [
            quorum_sizer.node_reliability[n] for n in preferred_nodes
        ]
        assert all(r >= 0.6 for r in selected_reliabilities)
