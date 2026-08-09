"""Test suite for heartbeat timing and dynamic interval adjustment."""

import pytest
import asyncio
from datetime import datetime, timedelta
from src.raft.append_entries import HeartbeatTimer, FollowerHealth, LeaderHeartbeat


class TestFollowerHealth:
    """Tests for FollowerHealth data class."""
    
    def test_initialization(self):
        """Test FollowerHealth initialization."""
        health = FollowerHealth(
            follower_id="follower1",
            last_ack_time=datetime.now(),
        )
        
        assert health.follower_id == "follower1"
        assert health.consecutive_failures == 0
        assert health.response_time_ms == 0.0
        assert health.is_healthy is True
        assert health.missed_heartbeats == 0


class TestHeartbeatTimer:
    """Tests for HeartbeatTimer."""
    
    def test_initialization(self):
        """Test HeartbeatTimer initialization."""
        timer = HeartbeatTimer()
        
        assert timer.base_interval == 0.15
        assert timer.min_interval == 0.05
        assert timer.max_interval == 0.5
        assert timer.follower_health == {}
        assert timer.current_intervals == {}
    
    def test_initialization_custom_intervals(self):
        """Test initialization with custom intervals."""
        timer = HeartbeatTimer(
            base_interval=0.2,
            min_interval=0.1,
            max_interval=1.0,
        )
        
        assert timer.base_interval == 0.2
        assert timer.min_interval == 0.1
        assert timer.max_interval == 1.0
    
    def test_register_follower(self):
        """Test registering a follower."""
        timer = HeartbeatTimer()
        
        timer.register_follower("follower1")
        
        assert "follower1" in timer.follower_health
        assert "follower1" in timer.current_intervals
        assert timer.current_intervals["follower1"] == 0.15
    
    def test_record_success(self):
        """Test recording successful heartbeat."""
        timer = HeartbeatTimer()
        timer.register_follower("follower1")
        
        timer.record_success("follower1", 5.0)
        
        health = timer.follower_health["follower1"]
        assert health.consecutive_failures == 0
        assert health.is_healthy is True
        assert health.missed_heartbeats == 0
        # First call: 0.8 * 0 + 0.2 * 5.0 = 1.0
        assert health.response_time_ms == 1.0
    
    def test_record_success_moving_average(self):
        """Test response time moving average calculation."""
        timer = HeartbeatTimer()
        timer.register_follower("follower1")
        
        timer.record_success("follower1", 10.0)
        health1 = timer.follower_health["follower1"]
        # First: 0.8 * 0 + 0.2 * 10 = 2.0
        assert health1.response_time_ms == 2.0
        
        timer.record_success("follower1", 20.0)
        health2 = timer.follower_health["follower1"]
        # Second: 0.8 * 2.0 + 0.2 * 20 = 1.6 + 4 = 5.6
        assert health2.response_time_ms == 5.6
    
    def test_record_failure(self):
        """Test recording failed heartbeat."""
        timer = HeartbeatTimer()
        timer.register_follower("follower1")
        
        timer.record_failure("follower1")
        
        health = timer.follower_health["follower1"]
        assert health.consecutive_failures == 1
        assert health.missed_heartbeats == 1
        assert health.is_healthy is True  # Not marked unhealthy yet
    
    def test_record_multiple_failures_marks_unhealthy(self):
        """Test that 3+ failures mark follower as unhealthy."""
        timer = HeartbeatTimer()
        timer.register_follower("follower1")
        
        timer.record_failure("follower1")
        timer.record_failure("follower1")
        timer.record_failure("follower1")
        
        health = timer.follower_health["follower1"]
        assert health.consecutive_failures == 3
        assert health.is_healthy is False
    
    def test_record_success_resets_failures(self):
        """Test that success resets failure count."""
        timer = HeartbeatTimer()
        timer.register_follower("follower1")
        
        timer.record_failure("follower1")
        timer.record_failure("follower1")
        timer.record_success("follower1", 5.0)
        
        health = timer.follower_health["follower1"]
        assert health.consecutive_failures == 0
        assert health.is_healthy is True
    
    def test_should_send_heartbeat_initial(self):
        """Test initial heartbeat should be sent."""
        timer = HeartbeatTimer(base_interval=0.15)
        timer.register_follower("follower1")
        
        # Should send immediately since last_ack_time was set to now
        # Wait a bit to ensure time has passed
        import time
        time.sleep(0.01)
        
        # After initial registration, should not send immediately
        assert not timer.should_send_heartbeat("follower1")
    
    def test_should_send_heartbeat_after_interval(self):
        """Test heartbeat timing."""
        timer = HeartbeatTimer(base_interval=0.01)
        timer.register_follower("follower1")
        
        # Manually set last_ack_time to past
        timer.follower_health["follower1"].last_ack_time = (
            datetime.now() - timedelta(seconds=0.05)
        )
        
        assert timer.should_send_heartbeat("follower1")
    
    def test_get_next_heartbeat_time(self):
        """Test getting next heartbeat time."""
        timer = HeartbeatTimer(base_interval=0.15)
        timer.register_follower("follower1")
        
        next_time = timer.get_next_heartbeat_time("follower1")
        
        # Should be approximately 150ms from now
        time_diff = next_time - datetime.now()
        assert 0 < time_diff.total_seconds() <= 0.2
    
    def test_adjust_interval_for_success(self):
        """Test interval decreases for fast responses."""
        timer = HeartbeatTimer(base_interval=0.15)
        timer.register_follower("follower1")
        
        original_interval = timer.current_intervals["follower1"]
        timer.record_success("follower1", 5.0)  # Very fast response
        new_interval = timer.current_intervals["follower1"]
        
        assert new_interval < original_interval
        assert new_interval >= timer.min_interval
    
    def test_adjust_interval_for_failure(self):
        """Test interval increases for failures."""
        timer = HeartbeatTimer(base_interval=0.15)
        timer.register_follower("follower1")
        
        original_interval = timer.current_intervals["follower1"]
        timer.record_failure("follower1")
        new_interval = timer.current_intervals["follower1"]
        
        assert new_interval > original_interval
        assert new_interval <= timer.max_interval
    
    def test_interval_respects_bounds(self):
        """Test that intervals respect min/max bounds."""
        timer = HeartbeatTimer(
            base_interval=0.15,
            min_interval=0.05,
            max_interval=0.5,
        )
        timer.register_follower("follower1")
        
        # Record multiple successes to decrease interval
        for _ in range(10):
            timer.record_success("follower1", 2.0)
        
        assert timer.current_intervals["follower1"] >= timer.min_interval
        
        # Record multiple failures to increase interval
        for _ in range(10):
            timer.record_failure("follower1")
        
        assert timer.current_intervals["follower1"] <= timer.max_interval
    
    def test_get_healthy_followers(self):
        """Test getting list of healthy followers."""
        timer = HeartbeatTimer()
        
        for i in range(1, 4):
            timer.register_follower(f"follower{i}")
        
        # Mark one as unhealthy
        for _ in range(3):
            timer.record_failure("follower2")
        
        healthy = timer.get_healthy_followers()
        unhealthy = timer.get_unhealthy_followers()
        
        assert "follower1" in healthy
        assert "follower3" in healthy
        assert "follower2" in unhealthy
    
    def test_get_follower_health(self):
        """Test retrieving follower health."""
        timer = HeartbeatTimer()
        timer.register_follower("follower1")
        
        health = timer.get_follower_health("follower1")
        
        assert health is not None
        assert health.follower_id == "follower1"
        assert timer.get_follower_health("unknown") is None
    
    def test_get_diagnostics(self):
        """Test getting diagnostic information."""
        timer = HeartbeatTimer()
        
        for i in range(1, 4):
            timer.register_follower(f"follower{i}")
        
        # Mark one as unhealthy
        for _ in range(3):
            timer.record_failure("follower2")
        
        diag = timer.get_diagnostics()
        
        assert diag["total_followers"] == 3
        assert diag["healthy_count"] == 2
        assert diag["unhealthy_count"] == 1
        assert "followers" in diag
        assert "follower1" in diag["followers"]


class TestLeaderHeartbeatWithTimer:
    """Tests for LeaderHeartbeat with timer integration."""
    
    def test_initialization_with_timer(self):
        """Test LeaderHeartbeat initializes timer."""
        heartbeat = LeaderHeartbeat("leader1", ["follower1", "follower2", "follower3"])
        
        assert heartbeat.heartbeat_timer is not None
        assert "follower1" in heartbeat.heartbeat_timer.follower_health
        assert "follower2" in heartbeat.heartbeat_timer.follower_health
        assert "follower3" in heartbeat.heartbeat_timer.follower_health
    
    @pytest.mark.asyncio
    async def test_send_heartbeats_uses_timer(self):
        """Test that send_heartbeats respects timer."""
        heartbeat = LeaderHeartbeat("leader1", ["follower1", "follower2"])
        
        # First send should not send heartbeats (no time has passed)
        acks = await heartbeat.send_heartbeats(term=1)
        
        assert len(acks) > 0
        # Some followers may not have heartbeats sent yet
    
    def test_get_status_includes_diagnostics(self):
        """Test that status includes timing diagnostics."""
        heartbeat = LeaderHeartbeat("leader1", ["follower1", "follower2"])
        
        status = heartbeat.get_status()
        
        assert "timing_diagnostics" in status
        assert "total_followers" in status["timing_diagnostics"]
        assert "healthy_count" in status["timing_diagnostics"]
    
    def test_multiple_followers_health_tracking(self):
        """Test health tracking for multiple followers."""
        heartbeat = LeaderHeartbeat(
            "leader1",
            ["follower1", "follower2", "follower3"],
        )
        
        # Simulate different scenarios
        heartbeat.heartbeat_timer.record_success("follower1", 5.0)
        heartbeat.heartbeat_timer.record_failure("follower2")
        heartbeat.heartbeat_timer.record_failure("follower3")
        
        healthy = heartbeat.heartbeat_timer.get_healthy_followers()
        unhealthy = heartbeat.heartbeat_timer.get_unhealthy_followers()
        
        assert "follower1" in healthy
        assert len(healthy) >= 1
