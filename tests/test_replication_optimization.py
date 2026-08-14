"""
Tests for replication lag monitoring & optimization

Covers:
- Lag metrics tracking
- Priority calculation
- Adaptive optimization
- Catch-up management
- Heartbeat adaptation
"""

import pytest
import asyncio
import time
from src.raft.replication_optimization import (
    ReplicationLagMonitor, LagMetric, LagPriority,
    AdaptiveHeartbeatManager, CatchUpOptimizer
)


class TestLagMetric:
    """Test LagMetric class"""
    
    def test_create_lag_metric(self):
        """Test creating lag metric"""
        metric = LagMetric(follower_id="follower_1")
        assert metric.follower_id == "follower_1"
        assert metric.lag_ms == 0.0
    
    def test_lag_priority_critical(self):
        """Test critical lag priority"""
        metric = LagMetric(follower_id="follower_1", lag_ms=6000)
        assert metric.get_priority() == LagPriority.CRITICAL
        assert metric.is_critical()
    
    def test_lag_priority_high(self):
        """Test high lag priority"""
        metric = LagMetric(follower_id="follower_1", lag_ms=2000)
        assert metric.get_priority() == LagPriority.HIGH
    
    def test_lag_priority_medium(self):
        """Test medium lag priority"""
        metric = LagMetric(follower_id="follower_1", lag_ms=500)
        assert metric.get_priority() == LagPriority.MEDIUM
    
    def test_lag_priority_low(self):
        """Test low lag priority"""
        metric = LagMetric(follower_id="follower_1", lag_ms=50)
        assert metric.get_priority() == LagPriority.LOW
    
    def test_max_lag_tracking(self):
        """Test maximum lag tracking"""
        metric = LagMetric(follower_id="follower_1")
        metric.lag_ms = 100
        metric.max_lag_observed = max(metric.max_lag_observed, metric.lag_ms)
        
        metric.lag_ms = 200
        metric.max_lag_observed = max(metric.max_lag_observed, metric.lag_ms)
        
        assert metric.max_lag_observed == 200
    
    def test_catch_up_rate(self):
        """Test catch-up success rate calculation"""
        metric = LagMetric(follower_id="follower_1")
        metric.catch_up_attempts = 10
        metric.catch_up_success = 8
        
        rate = metric.get_catch_up_rate()
        assert rate == 80.0


class TestReplicationLagMonitor:
    """Test ReplicationLagMonitor class"""
    
    @pytest.fixture
    def lag_monitor(self):
        """Create lag monitor for testing"""
        return ReplicationLagMonitor("leader_1")
    
    def test_register_follower(self, lag_monitor):
        """Test follower registration"""
        lag_monitor.register_follower("follower_1")
        
        assert "follower_1" in lag_monitor.lag_metrics
        assert "follower_1" in lag_monitor.optimization_strategies
    
    @pytest.mark.asyncio
    async def test_update_lag(self, lag_monitor):
        """Test lag update"""
        lag_monitor.register_follower("follower_1")
        await lag_monitor.update_lag("follower_1", 100.0)
        
        assert lag_monitor.get_lag("follower_1") == 100.0
    
    @pytest.mark.asyncio
    async def test_critical_lag_detection(self, lag_monitor):
        """Test critical lag detection"""
        lag_monitor.register_follower("follower_1")
        await lag_monitor.update_lag("follower_1", 6000)
        
        critical = lag_monitor.get_critical_followers()
        assert "follower_1" in critical
    
    def test_priority_ordering(self, lag_monitor):
        """Test follower ordering by priority"""
        lag_monitor.register_follower("follower_1")
        lag_monitor.register_follower("follower_2")
        lag_monitor.register_follower("follower_3")
        
        lag_monitor.lag_metrics["follower_1"].lag_ms = 100  # LOW
        lag_monitor.lag_metrics["follower_2"].lag_ms = 6000  # CRITICAL
        lag_monitor.lag_metrics["follower_3"].lag_ms = 2000  # HIGH
        
        order = lag_monitor.get_priority_order()
        assert order[0] == "follower_2"  # Critical first
        assert order[1] == "follower_3"  # High next
        assert order[2] == "follower_1"  # Low last
    
    @pytest.mark.asyncio
    async def test_lag_history_tracking(self, lag_monitor):
        """Test lag history tracking"""
        lag_monitor.register_follower("follower_1")
        
        for i in range(10):
            await lag_monitor.update_lag("follower_1", float(i * 10))
        
        history = lag_monitor.lag_history["follower_1"]
        assert len(history) == 10
    
    def test_lag_statistics(self, lag_monitor):
        """Test lag statistics calculation"""
        lag_monitor.register_follower("follower_1")
        lag_monitor.lag_metrics["follower_1"].lag_ms = 100
        lag_monitor._update_average_lag()
        
        stats = lag_monitor.get_lag_statistics()
        assert "average_lag_ms" in stats
        assert "peak_lag_ms" in stats
        assert "total_events" in stats
    
    @pytest.mark.asyncio
    async def test_catch_up_recording(self, lag_monitor):
        """Test catch-up attempt recording"""
        lag_monitor.register_follower("follower_1")
        
        await lag_monitor.record_catch_up_attempt("follower_1", True)
        await lag_monitor.record_catch_up_attempt("follower_1", True)
        await lag_monitor.record_catch_up_attempt("follower_1", False)
        
        rate = lag_monitor.get_catch_up_rates()["follower_1"]
        assert rate == (2/3) * 100
    
    def test_lag_trend_analysis(self, lag_monitor):
        """Test lag trend analysis"""
        lag_monitor.register_follower("follower_1")
        
        # Simulate improving lag
        for lag in [100, 90, 80, 70, 60]:
            lag_monitor.lag_history["follower_1"].append((time.time(), lag))
        
        trend = lag_monitor.get_lag_trend("follower_1")
        assert trend in ["improving", "worsening", "stable"]
    
    def test_lag_distribution(self, lag_monitor):
        """Test lag distribution calculation"""
        lag_monitor.register_follower("follower_1")
        lag_monitor.register_follower("follower_2")
        
        lag_monitor.lag_metrics["follower_1"].lag_ms = 50  # LOW
        lag_monitor.lag_metrics["follower_2"].lag_ms = 6000  # CRITICAL
        
        dist = lag_monitor.get_lag_distribution()
        assert dist[LagPriority.LOW] == 1
        assert dist[LagPriority.CRITICAL] == 1


class TestAdaptiveHeartbeatManager:
    """Test AdaptiveHeartbeatManager class"""
    
    @pytest.fixture
    def heartbeat_manager(self):
        """Create heartbeat manager for testing"""
        monitor = ReplicationLagMonitor("leader_1")
        return AdaptiveHeartbeatManager(monitor)
    
    def test_base_heartbeat_interval(self, heartbeat_manager):
        """Test base heartbeat interval"""
        heartbeat_manager.lag_monitor.register_follower("follower_1")
        interval = heartbeat_manager.get_heartbeat_interval("follower_1")
        
        assert interval == heartbeat_manager.base_heartbeat_ms
    
    def test_increased_heartbeat_for_critical_lag(self, heartbeat_manager):
        """Test increased heartbeat for critical lag"""
        heartbeat_manager.lag_monitor.register_follower("follower_1")
        strategy = heartbeat_manager.lag_monitor.optimization_strategies["follower_1"]
        strategy.increased_heartbeat_frequency = 10.0
        
        interval = heartbeat_manager.get_heartbeat_interval("follower_1")
        expected = heartbeat_manager.base_heartbeat_ms / 10.0
        assert interval == expected
    
    def test_minimum_heartbeat_interval(self, heartbeat_manager):
        """Test minimum heartbeat interval"""
        heartbeat_manager.lag_monitor.register_follower("follower_1")
        strategy = heartbeat_manager.lag_monitor.optimization_strategies["follower_1"]
        strategy.increased_heartbeat_frequency = 1000.0  # Very high
        
        interval = heartbeat_manager.get_heartbeat_interval("follower_1")
        assert interval >= 10  # Minimum is 10ms
    
    def test_update_all_intervals(self, heartbeat_manager):
        """Test updating all intervals"""
        heartbeat_manager.lag_monitor.register_follower("follower_1")
        heartbeat_manager.lag_monitor.register_follower("follower_2")
        
        heartbeat_manager.update_all_intervals()
        
        assert "follower_1" in heartbeat_manager.heartbeat_frequencies
        assert "follower_2" in heartbeat_manager.heartbeat_frequencies


class TestCatchUpOptimizer:
    """Test CatchUpOptimizer class"""
    
    @pytest.fixture
    def catch_up_optimizer(self):
        """Create catch-up optimizer for testing"""
        monitor = ReplicationLagMonitor("leader_1")
        return CatchUpOptimizer(monitor)
    
    def test_default_batch_size(self, catch_up_optimizer):
        """Test default batch size"""
        catch_up_optimizer.lag_monitor.register_follower("follower_1")
        batch_size = catch_up_optimizer.get_batch_size("follower_1")
        
        assert batch_size == catch_up_optimizer.default_batch_size
    
    def test_increased_batch_for_optimization(self, catch_up_optimizer):
        """Test increased batch size for optimization"""
        catch_up_optimizer.lag_monitor.register_follower("follower_1")
        strategy = catch_up_optimizer.lag_monitor.optimization_strategies["follower_1"]
        strategy.batch_size_multiplier = 5.0
        
        batch_size = catch_up_optimizer.get_batch_size("follower_1")
        expected = int(catch_up_optimizer.default_batch_size * 5.0)
        assert batch_size == expected
    
    @pytest.mark.asyncio
    async def test_execute_catch_up(self, catch_up_optimizer):
        """Test catch-up execution"""
        catch_up_optimizer.lag_monitor.register_follower("follower_1")
        
        result = await catch_up_optimizer.execute_catch_up("follower_1", 1000)
        
        assert result
        metric = catch_up_optimizer.lag_monitor.lag_metrics["follower_1"]
        assert metric.catch_up_attempts == 1


class TestLagMonitoringScenarios:
    """Test realistic lag monitoring scenarios"""
    
    @pytest.mark.asyncio
    async def test_follower_catch_up_scenario(self):
        """Test follower catch-up scenario"""
        monitor = ReplicationLagMonitor("leader_1")
        monitor.register_follower("follower_1")
        
        # Simulate increasing lag
        for lag in range(100, 6000, 1000):
            await monitor.update_lag("follower_1", float(lag))
        
        assert len(monitor.get_critical_followers()) == 1
        
        # Simulate catch-up
        await monitor.record_catch_up_attempt("follower_1", True)
        await monitor.update_lag("follower_1", 100)
        
        assert len(monitor.get_critical_followers()) == 0
    
    @pytest.mark.asyncio
    async def test_multiple_followers_different_lag(self):
        """Test monitoring multiple followers with different lag"""
        monitor = ReplicationLagMonitor("leader_1")
        
        lags = {"follower_1": 100, "follower_2": 2000, "follower_3": 6000}
        for follower, lag in lags.items():
            monitor.register_follower(follower)
            await monitor.update_lag(follower, float(lag))
        
        order = monitor.get_priority_order()
        assert order[0] == "follower_3"  # Critical
        assert order[1] == "follower_2"  # High
        assert order[2] == "follower_1"  # Low
    
    @pytest.mark.asyncio
    async def test_lag_oscillation_handling(self):
        """Test handling of lag oscillations"""
        monitor = ReplicationLagMonitor("leader_1")
        monitor.register_follower("follower_1")
        
        # Simulate oscillating lag
        lags = [100, 500, 200, 600, 150, 400]
        for lag in lags:
            await monitor.update_lag("follower_1", float(lag))
        
        trend = monitor.get_lag_trend("follower_1")
        assert trend in ["improving", "worsening", "stable"]


# Performance tests
class TestPerformance:
    """Performance tests for lag monitoring"""
    
    @pytest.mark.asyncio
    async def test_many_followers_lag_updates(self):
        """Test lag updates for many followers"""
        monitor = ReplicationLagMonitor("leader_1")
        
        # Register many followers
        for i in range(100):
            monitor.register_follower(f"follower_{i}")
        
        # Update lag for all
        start = time.time()
        for i in range(100):
            await monitor.update_lag(f"follower_{i}", float(i * 10))
        elapsed = time.time() - start
        
        assert elapsed < 1.0  # Should be fast
    
    @pytest.mark.asyncio
    async def test_large_history_tracking(self):
        """Test performance with large lag history"""
        monitor = ReplicationLagMonitor("leader_1")
        monitor.register_follower("follower_1")
        
        # Generate large history
        start = time.time()
        for i in range(5000):
            await monitor.update_lag("follower_1", float(i % 1000))
        elapsed = time.time() - start
        
        assert elapsed < 5.0  # Should handle well
        assert len(monitor.lag_history["follower_1"]) <= 1000  # Should cap history
