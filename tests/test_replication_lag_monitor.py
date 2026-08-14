"""
Comprehensive tests for ReplicationLagMonitor.

Tests cover:
- Lag measurement and tracking
- Per-follower metrics
- Priority calculation
- Adaptive heartbeat frequency
- Catch-up optimization
- Lag visualization and reporting
"""

import pytest
import time
from datetime import datetime, timedelta
from src.raft.replication_lag_monitor import (
    ReplicationLagMonitor, FollowerLagState, LagMetric, LagSeverity
)


class TestLagSeverity:
    """Tests for LagSeverity classification."""
    
    def test_severity_healthy(self):
        """Test healthy severity classification."""
        metric = LagMetric(
            timestamp=datetime.now(),
            follower_id="follower-1",
            lag_entries=5
        )
        assert metric.get_severity() == LagSeverity.HEALTHY
    
    def test_severity_moderate(self):
        """Test moderate severity classification."""
        metric = LagMetric(
            timestamp=datetime.now(),
            follower_id="follower-1",
            lag_entries=30
        )
        assert metric.get_severity() == LagSeverity.MODERATE
    
    def test_severity_high(self):
        """Test high severity classification."""
        metric = LagMetric(
            timestamp=datetime.now(),
            follower_id="follower-1",
            lag_entries=100
        )
        assert metric.get_severity() == LagSeverity.HIGH
    
    def test_severity_critical(self):
        """Test critical severity classification."""
        metric = LagMetric(
            timestamp=datetime.now(),
            follower_id="follower-1",
            lag_entries=500
        )
        assert metric.get_severity() == LagSeverity.CRITICAL


class TestFollowerLagState:
    """Tests for FollowerLagState tracking."""
    
    def test_lag_state_initialization(self):
        """Test FollowerLagState initialization."""
        state = FollowerLagState(follower_id="follower-1")
        assert state.follower_id == "follower-1"
        assert state.current_lag == 0
        assert state.max_lag == 0
        assert state.avg_lag == 0.0
    
    def test_update_lag_single(self):
        """Test updating lag with single value."""
        state = FollowerLagState(follower_id="follower-1")
        state.update_lag(10)
        
        assert state.current_lag == 10
        assert state.max_lag == 10
        assert state.min_lag == 10
        assert state.avg_lag == 10.0
    
    def test_update_lag_multiple(self):
        """Test updating lag with multiple values."""
        state = FollowerLagState(follower_id="follower-1")
        
        for lag in [5, 10, 15, 20]:
            state.update_lag(lag)
        
        assert state.current_lag == 20
        assert state.max_lag == 20
        assert state.min_lag == 5
        assert state.avg_lag == pytest.approx(12.5)
    
    def test_lag_history_limited(self):
        """Test lag history is limited to maxlen."""
        state = FollowerLagState(follower_id="follower-1")
        
        # History maxlen is 100
        for i in range(150):
            state.update_lag(i)
        
        assert len(state.lag_history) <= 100
    
    def test_catch_up_rate_tracking(self):
        """Test catch-up rate tracking."""
        state = FollowerLagState(follower_id="follower-1")
        
        state.update_catch_up_rate(10.5)
        state.update_catch_up_rate(12.0)
        state.update_catch_up_rate(11.5)
        
        avg_rate = state.get_avg_catch_up_rate()
        assert avg_rate == pytest.approx(11.33, rel=0.01)
    
    def test_severity_classification(self):
        """Test severity classification from state."""
        state = FollowerLagState(follower_id="follower-1")
        
        state.update_lag(5)
        assert state.get_severity() == LagSeverity.HEALTHY
        
        state.update_lag(30)
        assert state.get_severity() == LagSeverity.MODERATE
        
        state.update_lag(100)
        assert state.get_severity() == LagSeverity.HIGH
        
        state.update_lag(300)
        assert state.get_severity() == LagSeverity.CRITICAL
    
    def test_to_dict_conversion(self):
        """Test conversion to dictionary."""
        state = FollowerLagState(follower_id="follower-1")
        state.update_lag(15)
        state.update_catch_up_rate(5.0)
        
        data = state.to_dict()
        assert data["follower_id"] == "follower-1"
        assert data["current_lag"] == 15
        assert data["severity"] == "moderate"


class TestReplicationLagMonitorInitialization:
    """Tests for monitor initialization."""
    
    def test_monitor_init(self):
        """Test monitor initialization."""
        followers = ["follower-1", "follower-2", "follower-3"]
        monitor = ReplicationLagMonitor("leader-1", followers)
        
        assert monitor.leader_id == "leader-1"
        assert len(monitor.follower_states) == 3
        assert all(f in monitor.follower_states for f in followers)
    
    def test_follower_states_initialized(self):
        """Test all follower states are initialized."""
        followers = ["follower-1", "follower-2"]
        monitor = ReplicationLagMonitor("leader-1", followers)
        
        for follower_id in followers:
            state = monitor.follower_states[follower_id]
            assert state.follower_id == follower_id
            assert state.current_lag == 0
            assert state.heartbeat_frequency_ms == 150


class TestLagReporting:
    """Tests for lag reporting."""
    
    def test_report_lag_single(self):
        """Test reporting single lag measurement."""
        monitor = ReplicationLagMonitor("leader-1", ["follower-1"])
        
        monitor.report_lag("follower-1", 5)
        
        state = monitor.follower_states["follower-1"]
        assert state.current_lag == 5
        assert monitor.total_measurements == 1
    
    def test_report_lag_multiple(self):
        """Test reporting multiple lag measurements."""
        monitor = ReplicationLagMonitor("leader-1", ["follower-1", "follower-2"])
        
        monitor.report_lag("follower-1", 10)
        monitor.report_lag("follower-2", 15)
        monitor.report_lag("follower-1", 12)
        
        assert monitor.total_measurements == 3
        assert monitor.follower_states["follower-1"].current_lag == 12
        assert monitor.follower_states["follower-2"].current_lag == 15
    
    def test_report_lag_with_catch_up(self):
        """Test reporting lag with catch-up flag."""
        monitor = ReplicationLagMonitor("leader-1", ["follower-1"])
        
        monitor.report_lag("follower-1", 20, catching_up=True)
        
        state = monitor.follower_states["follower-1"]
        assert state.current_lag == 20
        assert state.catch_up_start_time is not None
    
    def test_report_lag_unknown_follower(self):
        """Test reporting lag for unknown follower."""
        monitor = ReplicationLagMonitor("leader-1", ["follower-1"])
        
        # Should not raise, just log warning
        monitor.report_lag("unknown-follower", 10)
        assert monitor.total_measurements == 0


class TestCatchUpTracking:
    """Tests for catch-up progress tracking."""
    
    def test_report_catch_up_progress(self):
        """Test reporting catch-up progress."""
        monitor = ReplicationLagMonitor("leader-1", ["follower-1"])
        
        monitor.report_catch_up_progress("follower-1", 10.5)
        
        state = monitor.follower_states["follower-1"]
        assert state.get_avg_catch_up_rate() == pytest.approx(10.5)
    
    def test_catch_up_rate_averaging(self):
        """Test catch-up rate averaging."""
        monitor = ReplicationLagMonitor("leader-1", ["follower-1"])
        
        for rate in [8.0, 10.0, 12.0]:
            monitor.report_catch_up_progress("follower-1", rate)
        
        avg_rate = monitor.follower_states["follower-1"].get_avg_catch_up_rate()
        assert avg_rate == pytest.approx(10.0)


class TestPriorityCalculation:
    """Tests for priority score calculation."""
    
    def test_calculate_priority_scores_single_follower(self):
        """Test priority calculation for single follower."""
        monitor = ReplicationLagMonitor("leader-1", ["follower-1"])
        monitor.report_lag("follower-1", 50)  # Moderate lag
        
        scores = monitor.calculate_priority_scores()
        assert "follower-1" in scores
        assert scores["follower-1"] > 0
    
    def test_priority_scores_high_lag_priority(self):
        """Test that high lag gets higher priority."""
        monitor = ReplicationLagMonitor(
            "leader-1",
            ["follower-1", "follower-2"]
        )
        
        monitor.report_lag("follower-1", 5)   # Healthy
        monitor.report_lag("follower-2", 100) # High lag
        
        scores = monitor.calculate_priority_scores()
        assert scores["follower-2"] > scores["follower-1"]
    
    def test_priority_scores_with_catch_up(self):
        """Test priority with catch-up rates."""
        monitor = ReplicationLagMonitor(
            "leader-1",
            ["follower-1", "follower-2"]
        )
        
        monitor.report_lag("follower-1", 100)
        monitor.report_lag("follower-2", 100)
        
        # Higher catch-up rate reduces priority
        monitor.report_catch_up_progress("follower-1", 50.0)
        monitor.report_catch_up_progress("follower-2", 5.0)
        
        scores = monitor.calculate_priority_scores()
        # follower-2 should have higher priority (slower catch-up)
        assert scores["follower-2"] > scores["follower-1"]


class TestLaggedFollowersQuery:
    """Tests for identifying lagged followers."""
    
    def test_get_lagged_followers(self):
        """Test getting lagged followers."""
        monitor = ReplicationLagMonitor(
            "leader-1",
            ["follower-1", "follower-2", "follower-3"]
        )
        
        monitor.report_lag("follower-1", 5)
        monitor.report_lag("follower-2", 30)
        monitor.report_lag("follower-3", 100)
        
        lagged = monitor.get_lagged_followers(min_lag=10)
        assert len(lagged) == 2
        assert "follower-2" in lagged
        assert "follower-3" in lagged
    
    def test_get_lagged_followers_sorted(self):
        """Test lagged followers are sorted by lag."""
        monitor = ReplicationLagMonitor(
            "leader-1",
            ["follower-1", "follower-2", "follower-3"]
        )
        
        monitor.report_lag("follower-1", 50)
        monitor.report_lag("follower-2", 100)
        monitor.report_lag("follower-3", 75)
        
        lagged = monitor.get_lagged_followers(min_lag=1)
        # Should be sorted highest lag first
        assert lagged[0] == "follower-2"
        assert lagged[1] == "follower-3"
        assert lagged[2] == "follower-1"
    
    def test_get_lagged_followers_max_results(self):
        """Test max results limit for lagged followers."""
        monitor = ReplicationLagMonitor(
            "leader-1",
            ["follower-1", "follower-2", "follower-3"]
        )
        
        monitor.report_lag("follower-1", 10)
        monitor.report_lag("follower-2", 20)
        monitor.report_lag("follower-3", 30)
        
        lagged = monitor.get_lagged_followers(min_lag=1, max_results=2)
        assert len(lagged) == 2
    
    def test_get_critical_lag_followers(self):
        """Test getting critical lag followers."""
        monitor = ReplicationLagMonitor(
            "leader-1",
            ["follower-1", "follower-2", "follower-3"]
        )
        
        monitor.report_lag("follower-1", 5)
        monitor.report_lag("follower-2", 250)   # Critical
        monitor.report_lag("follower-3", 300)   # Critical
        
        critical = monitor.get_critical_lag_followers()
        assert len(critical) == 2
        assert "follower-2" in critical
        assert "follower-3" in critical


class TestHeartbeatOptimization:
    """Tests for heartbeat frequency optimization."""
    
    def test_optimize_heartbeat_healthy(self):
        """Test heartbeat optimization for healthy nodes."""
        monitor = ReplicationLagMonitor("leader-1", ["follower-1"])
        monitor.report_lag("follower-1", 5)
        
        frequencies = monitor.optimize_heartbeat_frequency()
        # Healthy should have slower heartbeat
        assert frequencies["follower-1"] == 300
    
    def test_optimize_heartbeat_moderate(self):
        """Test heartbeat optimization for moderate lag."""
        monitor = ReplicationLagMonitor("leader-1", ["follower-1"])
        monitor.report_lag("follower-1", 30)
        
        frequencies = monitor.optimize_heartbeat_frequency()
        assert frequencies["follower-1"] == 150
    
    def test_optimize_heartbeat_high(self):
        """Test heartbeat optimization for high lag."""
        monitor = ReplicationLagMonitor("leader-1", ["follower-1"])
        monitor.report_lag("follower-1", 100)
        
        frequencies = monitor.optimize_heartbeat_frequency()
        assert frequencies["follower-1"] == 50
    
    def test_optimize_heartbeat_critical(self):
        """Test heartbeat optimization for critical lag."""
        monitor = ReplicationLagMonitor("leader-1", ["follower-1"])
        monitor.report_lag("follower-1", 300)
        
        frequencies = monitor.optimize_heartbeat_frequency()
        # Critical should have very fast heartbeat
        assert frequencies["follower-1"] == 10


class TestCatchUpEstimation:
    """Tests for catch-up time estimation."""
    
    def test_estimate_catch_up_time(self):
        """Test catch-up time estimation."""
        monitor = ReplicationLagMonitor("leader-1", ["follower-1"])
        monitor.report_lag("follower-1", 100)
        monitor.report_catch_up_progress("follower-1", 10.0)  # 10 entries/sec
        
        estimated_seconds = monitor.estimate_catch_up_time("follower-1")
        assert estimated_seconds == pytest.approx(10.0)  # 100 entries / 10 pers/sec
    
    def test_estimate_catch_up_time_with_target(self):
        """Test catch-up estimation with target lag."""
        monitor = ReplicationLagMonitor("leader-1", ["follower-1"])
        monitor.report_lag("follower-1", 100)
        monitor.report_catch_up_progress("follower-1", 20.0)
        
        estimated_seconds = monitor.estimate_catch_up_time("follower-1", target_lag=10)
        # (100 - 10) / 20 = 4.5 seconds
        assert estimated_seconds == pytest.approx(4.5)
    
    def test_estimate_catch_up_time_no_rate(self):
        """Test catch-up estimation with no rate."""
        monitor = ReplicationLagMonitor("leader-1", ["follower-1"])
        monitor.report_lag("follower-1", 100)
        
        estimated_seconds = monitor.estimate_catch_up_time("follower-1")
        assert estimated_seconds is None


class TestLagGrouping:
    """Tests for lag grouping by severity."""
    
    def test_get_lag_by_severity(self):
        """Test grouping followers by lag severity."""
        monitor = ReplicationLagMonitor(
            "leader-1",
            ["follower-1", "follower-2", "follower-3", "follower-4"]
        )
        
        monitor.report_lag("follower-1", 5)    # Healthy
        monitor.report_lag("follower-2", 30)   # Moderate
        monitor.report_lag("follower-3", 100)  # High
        monitor.report_lag("follower-4", 300)  # Critical
        
        grouped = monitor.get_lag_by_severity()
        assert "follower-1" in grouped["healthy"]
        assert "follower-2" in grouped["moderate"]
        assert "follower-3" in grouped["high"]
        assert "follower-4" in grouped["critical"]


class TestGapAnalysis:
    """Tests for replication gap analysis."""
    
    def test_get_replication_gap_analysis(self):
        """Test gap analysis."""
        monitor = ReplicationLagMonitor(
            "leader-1",
            ["follower-1", "follower-2", "follower-3"]
        )
        
        monitor.report_lag("follower-1", 10)
        monitor.report_lag("follower-2", 20)
        monitor.report_lag("follower-3", 30)
        
        analysis = monitor.get_replication_gap_analysis()
        assert analysis["total_followers"] == 3
        assert analysis["max_lag"] == 30
        assert analysis["min_lag"] == 10
        assert analysis["avg_lag"] == 20.0
        assert analysis["total_cluster_lag"] == 60
    
    def test_gap_analysis_counts_healthy(self):
        """Test gap analysis counts healthy followers."""
        monitor = ReplicationLagMonitor(
            "leader-1",
            ["f1", "f2", "f3", "f4", "f5"]
        )
        
        monitor.report_lag("f1", 5)
        monitor.report_lag("f2", 8)
        monitor.report_lag("f3", 30)
        monitor.report_lag("f4", 100)
        monitor.report_lag("f5", 300)
        
        analysis = monitor.get_replication_gap_analysis()
        assert analysis["healthy_followers"] == 2
        assert analysis["degraded_followers"] == 1
        assert analysis["critical_followers"] == 2


class TestFullOptimizationPass:
    """Tests for full optimization pass."""
    
    def test_optimize_replication(self):
        """Test full optimization pass."""
        monitor = ReplicationLagMonitor(
            "leader-1",
            ["follower-1", "follower-2"]
        )
        
        monitor.report_lag("follower-1", 100)
        monitor.report_lag("follower-2", 5)
        
        result = monitor.optimize_replication()
        assert "priorities" in result
        assert "frequencies" in result
        assert "critical_followers" in result
        assert "analysis" in result
    
    def test_optimize_replication_interval(self):
        """Test optimization respects interval."""
        monitor = ReplicationLagMonitor("leader-1", ["follower-1"])
        
        result1 = monitor.optimize_replication()
        assert "priorities" in result1
        
        # Immediate second call should be skipped
        result2 = monitor.optimize_replication()
        assert result2 == {}


class TestFollowerStatus:
    """Tests for follower status reporting."""
    
    def test_get_follower_status(self):
        """Test getting follower status."""
        monitor = ReplicationLagMonitor("leader-1", ["follower-1"])
        monitor.report_lag("follower-1", 50)
        monitor.report_catch_up_progress("follower-1", 10.0)
        
        status = monitor.get_follower_status("follower-1")
        assert status is not None
        assert status["follower_id"] == "follower-1"
        assert status["lag_metrics"]["current_lag"] == 50
        assert status["estimated_catch_up_seconds"] is not None
    
    def test_get_follower_status_unknown(self):
        """Test getting status for unknown follower."""
        monitor = ReplicationLagMonitor("leader-1", ["follower-1"])
        
        status = monitor.get_follower_status("unknown-follower")
        assert status is None


class TestClusterReport:
    """Tests for cluster lag reports."""
    
    def test_get_cluster_lag_report(self):
        """Test generating cluster lag report."""
        monitor = ReplicationLagMonitor(
            "leader-1",
            ["follower-1", "follower-2"]
        )
        
        monitor.report_lag("follower-1", 20)
        monitor.report_lag("follower-2", 50)
        
        report = monitor.get_cluster_lag_report()
        assert report["leader"] == "leader-1"
        assert report["total_measurements"] == 2
        assert "overall_analysis" in report
        assert "severity_breakdown" in report
        assert "follower_statuses" in report
        assert "optimization_recommendations" in report


class TestMetricsReset:
    """Tests for metrics reset."""
    
    def test_reset_metrics(self):
        """Test resetting all metrics."""
        monitor = ReplicationLagMonitor(
            "leader-1",
            ["follower-1", "follower-2"]
        )
        
        monitor.report_lag("follower-1", 100)
        monitor.report_lag("follower-2", 50)
        monitor.report_catch_up_progress("follower-1", 10.0)
        
        monitor.reset_metrics()
        
        assert monitor.total_measurements == 0
        assert len(monitor.global_lag_history) == 0
        for state in monitor.follower_states.values():
            assert state.current_lag == 0
            assert len(state.lag_history) == 0


class TestLagTrend:
    """Tests for lag trend analysis."""
    
    def test_get_lag_trend(self):
        """Test getting lag trend."""
        monitor = ReplicationLagMonitor("leader-1", ["follower-1"])
        
        for lag in [10, 15, 20, 25, 30]:
            monitor.report_lag("follower-1", lag)
        
        trend = monitor.get_lag_trend("follower-1")
        assert len(trend) == 5
        assert trend[-1] == 30  # Latest lag
    
    def test_get_lag_trend_limited_window(self):
        """Test lag trend with window size limit."""
        monitor = ReplicationLagMonitor("leader-1", ["follower-1"])
        
        for lag in range(1, 21):
            monitor.report_lag("follower-1", lag)
        
        trend = monitor.get_lag_trend("follower-1", window_size=5)
        assert len(trend) == 5
        assert trend[-1] == 20


class TestHealthCheck:
    """Tests for replication health check."""
    
    def test_is_replication_healthy_all_good(self):
        """Test health check when all followers in good state."""
        monitor = ReplicationLagMonitor(
            "leader-1",
            ["follower-1", "follower-2", "follower-3"]
        )
        
        monitor.report_lag("follower-1", 10)
        monitor.report_lag("follower-2", 20)
        monitor.report_lag("follower-3", 30)
        
        assert monitor.is_replication_healthy(max_acceptable_lag=50) is True
    
    def test_is_replication_healthy_with_lag(self):
        """Test health check with excessive lag."""
        monitor = ReplicationLagMonitor(
            "leader-1",
            ["follower-1", "follower-2"]
        )
        
        monitor.report_lag("follower-1", 100)
        monitor.report_lag("follower-2", 50)
        
        assert monitor.is_replication_healthy(max_acceptable_lag=50) is False
    
    def test_is_replication_healthy_strict(self):
        """Test health check with strict threshold."""
        monitor = ReplicationLagMonitor("leader-1", ["follower-1"])
        monitor.report_lag("follower-1", 15)
        
        assert monitor.is_replication_healthy(max_acceptable_lag=10) is False


class TestComplexScenarios:
    """Tests for complex monitoring scenarios."""
    
    def test_progressive_lag_increase(self):
        """Test monitoring progressive lag increase."""
        monitor = ReplicationLagMonitor("leader-1", ["follower-1"])
        
        # Simulate progressive lag
        for lag in range(0, 101, 10):
            monitor.report_lag("follower-1", lag)
        
        state = monitor.follower_states["follower-1"]
        assert state.max_lag == 100
        assert state.current_lag == 100
        assert len(state.lag_history) == 11
    
    def test_catch_up_scenario(self):
        """Test full catch-up scenario."""
        monitor = ReplicationLagMonitor("leader-1", ["follower-1"])
        
        # Start with high lag
        monitor.report_lag("follower-1", 100, catching_up=True)
        monitor.report_catch_up_progress("follower-1", 20.0)
        
        # Simulate catch-up
        for lag in range(80, 0, -10):
            monitor.report_lag("follower-1", lag, catching_up=True)
        
        state = monitor.follower_states["follower-1"]
        assert state.current_lag < state.max_lag
        assert state.catch_up_start_time is not None
    
    def test_multiple_follower_coordination(self):
        """Test monitoring multiple followers."""
        followers = ["f1", "f2", "f3", "f4", "f5"]
        monitor = ReplicationLagMonitor("leader-1", followers)
        
        # Vary lag across followers
        for i, follower in enumerate(followers):
            monitor.report_lag(follower, (i + 1) * 20)
        
        report = monitor.get_cluster_lag_report()
        assert report["total_measurements"] == 5
        analysis = report["overall_analysis"]
        assert analysis["max_lag"] == 100
        assert analysis["min_lag"] == 20
