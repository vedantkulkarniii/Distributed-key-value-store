"""Tests for lease-based read optimization."""

import pytest
from datetime import datetime, timedelta
from src.raft.lease_manager import LeaseManager, LeaseState, LeaseInfo


class TestLeaseInfo:
    """Test suite for LeaseInfo."""
    
    def test_lease_creation(self):
        """Test creating lease info."""
        lease = LeaseInfo("lease1", term=1, duration_ms=3000)
        
        assert lease.lease_id == "lease1"
        assert lease.term == 1
        assert lease.state == LeaseState.PENDING
    
    def test_lease_is_valid(self):
        """Test lease validity check."""
        lease = LeaseInfo("lease1", term=1, duration_ms=3000)
        lease.state = LeaseState.ACTIVE
        
        assert lease.is_valid()
    
    def test_lease_expiration(self):
        """Test lease expiration."""
        lease = LeaseInfo("lease1", term=1, duration_ms=10)  # 10ms
        lease.state = LeaseState.ACTIVE
        lease.expiration_time = datetime.now() - timedelta(milliseconds=100)
        
        assert lease.is_expired()
        assert not lease.is_valid()
    
    def test_lease_renewal(self):
        """Test lease renewal."""
        lease = LeaseInfo("lease1", term=1, duration_ms=3000)
        initial_exp = lease.expiration_time
        
        lease.renew(3000)
        
        assert lease.renewals == 1
        assert lease.expiration_time > initial_exp


class TestLeaseManager:
    """Test suite for LeaseManager."""
    
    @pytest.fixture
    def manager(self):
        """Fixture for lease manager."""
        return LeaseManager("node1", clock_skew_ms=150)
    
    # Lease Acquisition Tests
    
    def test_acquire_lease(self, manager):
        """Test acquiring lease."""
        success, lease, error = manager.acquire_lease(term=1)
        
        assert success
        assert lease is not None
        assert error is None
        assert lease.state == LeaseState.ACTIVE
    
    def test_acquire_multiple_leases(self, manager):
        """Test acquiring multiple leases."""
        success1, lease1, _ = manager.acquire_lease(term=1)
        success2, lease2, _ = manager.acquire_lease(term=2)
        
        assert success1 and success2
        assert lease1.lease_id != lease2.lease_id
    
    def test_lease_reuse_if_valid(self, manager):
        """Test that valid lease is reused."""
        success1, lease1, _ = manager.acquire_lease(term=1)
        success2, lease2, _ = manager.acquire_lease(term=1)
        
        assert success1 and success2
        assert lease1.lease_id == lease2.lease_id
    
    # Read Serving Tests
    
    def test_can_serve_read_with_valid_lease(self, manager):
        """Test reading with valid lease."""
        manager.acquire_lease(term=1)
        
        can_serve, reason = manager.can_serve_read()
        
        assert can_serve
        assert reason is None
    
    def test_cannot_serve_read_without_lease(self, manager):
        """Test reading without lease."""
        can_serve, reason = manager.can_serve_read()
        
        assert not can_serve
        assert reason is not None
    
    def test_serve_read_increments_counter(self, manager):
        """Test that serving reads increments counter."""
        manager.acquire_lease(term=1)
        
        success, _ = manager.serve_read()
        
        assert success
        assert manager.successful_reads == 1
    
    def test_serve_read_denied_increments_counter(self, manager):
        """Test that denied reads increment counter."""
        success, _ = manager.serve_read()
        
        assert not success
        assert manager.reads_denied == 1
    
    # Lease Renewal Tests
    
    def test_renew_lease(self, manager):
        """Test renewing lease."""
        manager.acquire_lease(term=1)
        initial_exp = manager.current_lease.expiration_time
        
        success, error = manager.renew_lease()
        
        assert success
        assert error is None
        assert manager.current_lease.expiration_time > initial_exp
        assert manager.current_lease.renewals == 1
    
    def test_renew_nonexistent_lease(self, manager):
        """Test renewing when no lease exists."""
        success, error = manager.renew_lease()
        
        assert not success
        assert error is not None
    
    # Clock Skew Tests
    
    def test_clock_skew_protection(self, manager):
        """Test clock skew protection."""
        manager.acquire_lease(term=1)
        
        # Simulate lease near expiration
        manager.current_lease.expiration_time = (
            datetime.now() + timedelta(milliseconds=100)  # Less than clock_skew_ms
        )
        
        can_serve, reason = manager.can_serve_read()
        
        assert not can_serve
        assert "clock skew" in reason.lower()
    
    # Lease Revocation Tests
    
    def test_revoke_lease(self, manager):
        """Test revoking lease."""
        manager.acquire_lease(term=1)
        
        success = manager.revoke_lease()
        
        assert success
        assert manager.current_lease is None
    
    def test_revoke_nonexistent_lease(self, manager):
        """Test revoking when no lease exists."""
        success = manager.revoke_lease()
        
        assert not success
    
    # Heartbeat ACK Tests
    
    def test_record_heartbeat_ack(self, manager):
        """Test recording heartbeat ACK."""
        manager.acquire_lease(term=1)
        
        manager.record_heartbeat_ack("node2")
        
        assert manager.current_lease.heartbeats_acked == 1
    
    def test_record_multiple_heartbeat_acks(self, manager):
        """Test recording multiple ACKs."""
        manager.acquire_lease(term=1)
        
        for i in range(5):
            manager.record_heartbeat_ack(f"node{i}")
        
        assert manager.current_lease.heartbeats_acked == 5
    
    # Health Check Tests
    
    def test_check_lease_health_active(self, manager):
        """Test lease health check when active."""
        manager.acquire_lease(term=1)
        
        health = manager.check_lease_health()
        
        assert health["active"]
        assert health["can_serve_read"]
        assert health["reads_served"] == 0
    
    def test_check_lease_health_no_lease(self, manager):
        """Test health check without lease."""
        health = manager.check_lease_health()
        
        assert not health["active"]
        assert health["reason"] == "No active lease"
    
    # Statistics Tests
    
    def test_get_statistics(self, manager):
        """Test getting statistics."""
        manager.acquire_lease(term=1)
        manager.serve_read()
        manager.serve_read()
        manager.serve_read()
        
        stats = manager.get_statistics()
        
        assert stats["total_leases"] == 1
        assert stats["successful_reads"] == 3
        assert 0 <= stats["success_rate"] <= 1
    
    def test_statistics_empty(self, manager):
        """Test statistics when no activity."""
        stats = manager.get_statistics()
        
        assert stats["total_leases"] == 0
        assert stats["successful_reads"] == 0
        assert stats["success_rate"] == 0
    
    # Cleanup Tests
    
    def test_cleanup_expired_leases(self, manager):
        """Test cleanup of expired leases."""
        # Create leases
        manager.acquire_lease(term=1)
        manager.acquire_lease(term=2)
        manager.acquire_lease(term=3)
        
        # Mark first two as expired
        lease_ids = list(manager.lease_history.keys())
        for lid in lease_ids[:2]:
            manager.lease_history[lid].expiration_time = (
                datetime.now() - timedelta(milliseconds=100)
            )
        
        cleaned = manager.cleanup_expired_leases()
        
        assert cleaned == 2
        assert len(manager.lease_history) == 1
    
    # Edge Cases
    
    def test_lease_with_zero_duration(self, manager):
        """Test lease with zero duration."""
        manager.lease_duration_ms = 0
        success, lease, _ = manager.acquire_lease(term=1)
        
        # Should still work but be immediately invalid
        assert success
        assert not lease.is_valid()
    
    def test_rapid_lease_cycles(self, manager):
        """Test rapid acquire/revoke cycles."""
        for i in range(10):
            success, _, _ = manager.acquire_lease(term=i)
            assert success
            manager.revoke_lease()
        
        assert manager.total_leases == 10
    
    def test_high_concurrency_simulation(self, manager):
        """Test high volume reads under lease."""
        manager.acquire_lease(term=1)
        
        for i in range(100):
            success, _ = manager.serve_read()
            if success:
                assert manager.successful_reads == i + 1
    
    def test_renewal_threshold_detection(self, manager):
        """Test renewal threshold detection."""
        manager.acquire_lease(term=1)
        manager.renewal_threshold_ms = 2900  # Close to renewal
        
        # Simulate passage of time
        manager.current_lease.expiration_time = (
            datetime.now() + timedelta(milliseconds=2800)
        )
        
        # Should detect need for renewal
        manager.serve_read()
        
        assert manager.current_lease.state == LeaseState.RENEWING
