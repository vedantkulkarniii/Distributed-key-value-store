"""Tests for read lease optimization."""

import pytest
import time
from datetime import datetime, timedelta
from src.raft.read_lease import (
    ReadLeaseManager,
    ReadLease,
    LeaseState,
)


class TestReadLease:
    """Test suite for ReadLease."""
    
    def test_lease_creation(self):
        """Test creating read lease."""
        lease = ReadLease(
            lease_id="lease1",
            node_id="node1",
            term=1,
            created_at=datetime.now(),
            lease_duration_ms=1000,
        )
        
        assert lease.lease_id == "lease1"
        assert lease.term == 1
        assert lease.heartbeat_acked_count == 1
    
    def test_lease_validity(self):
        """Test lease validity check."""
        lease = ReadLease(
            lease_id="lease1",
            node_id="node1",
            term=1,
            created_at=datetime.now(),
            lease_duration_ms=1000,
        )
        
        assert lease.is_valid()
    
    def test_lease_expiration(self):
        """Test lease expiration."""
        lease = ReadLease(
            lease_id="lease1",
            node_id="node1",
            term=1,
            created_at=datetime.now() - timedelta(milliseconds=1100),
            lease_duration_ms=1000,
        )
        
        assert not lease.is_valid()
    
    def test_lease_near_expiry(self):
        """Test lease near expiry detection."""
        lease = ReadLease(
            lease_id="lease1",
            node_id="node1",
            term=1,
            created_at=datetime.now() - timedelta(milliseconds=950),
            lease_duration_ms=1000,
        )
        
        assert lease.is_near_expiry(threshold_ms=100)
    
    def test_lease_state_valid(self):
        """Test lease state is valid."""
        lease = ReadLease(
            lease_id="lease1",
            node_id="node1",
            term=1,
            created_at=datetime.now(),
            lease_duration_ms=1000,
        )
        
        assert lease.get_state() == LeaseState.VALID
    
    def test_lease_state_expiring(self):
        """Test lease state is expiring."""
        lease = ReadLease(
            lease_id="lease1",
            node_id="node1",
            term=1,
            created_at=datetime.now() - timedelta(milliseconds=950),
            lease_duration_ms=1000,
        )
        
        assert lease.get_state() == LeaseState.EXPIRING
    
    def test_lease_state_expired(self):
        """Test lease state is expired."""
        lease = ReadLease(
            lease_id="lease1",
            node_id="node1",
            term=1,
            created_at=datetime.now() - timedelta(milliseconds=1100),
            lease_duration_ms=1000,
        )
        
        assert lease.get_state() == LeaseState.EXPIRED


class TestReadLeaseManager:
    """Test suite for ReadLeaseManager."""
    
    @pytest.fixture
    def manager(self):
        """Create read lease manager."""
        return ReadLeaseManager("node1", default_lease_duration_ms=1000)
    
    @pytest.fixture
    def state_data(self):
        """Create sample state machine data."""
        return {"key1": "value1", "key2": "value2"}
    
    # Lease Creation Tests
    
    def test_create_lease(self, manager):
        """Test creating lease."""
        success, lease_id, error = manager.create_lease(term=1)
        
        assert success
        assert lease_id is not None
        assert error is None
        assert manager.current_lease is not None
    
    def test_create_lease_increments_count(self, manager):
        """Test lease creation increments counter."""
        manager.create_lease(term=1)
        assert manager.total_leases_created == 1
        
        manager.create_lease(term=2)
        assert manager.total_leases_created == 2
    
    # Heartbeat ACK Tests
    
    def test_record_heartbeat_ack(self, manager):
        """Test recording heartbeat ACK."""
        manager.create_lease(term=1)
        
        success, ack_count = manager.record_heartbeat_ack()
        
        assert success
        assert ack_count == 2  # Self + 1 ACK
    
    def test_record_multiple_heartbeat_acks(self, manager):
        """Test multiple heartbeat ACKs."""
        manager.create_lease(term=1)
        
        manager.record_heartbeat_ack()
        manager.record_heartbeat_ack()
        
        success, ack_count = manager.record_heartbeat_ack()
        
        assert success
        assert ack_count == 4
    
    # Read Operations Tests
    
    def test_can_serve_read_from_lease(self, manager):
        """Test can serve read from valid lease."""
        manager.create_lease(term=1)
        
        assert manager.can_serve_read_from_lease()
    
    def test_cannot_serve_read_no_lease(self, manager):
        """Test cannot serve read without lease."""
        assert not manager.can_serve_read_from_lease()
    
    def test_cannot_serve_read_expired_lease(self, manager):
        """Test cannot serve read with expired lease."""
        success, lease_id, _ = manager.create_lease(term=1)
        assert success
        
        # Expire the lease
        manager.current_lease.created_at = datetime.now() - timedelta(milliseconds=1100)
        
        assert not manager.can_serve_read_from_lease()
    
    def test_serve_read_from_lease(self, manager, state_data):
        """Test serving read from lease."""
        manager.create_lease(term=1)
        
        success, value, error = manager.serve_read("key1", state_data)
        
        assert success
        assert value == "value1"
        assert error is None
        assert manager.lease_served_reads == 1
    
    def test_serve_read_without_lease_falls_back(self, manager, state_data):
        """Test read without lease falls back to quorum."""
        success, value, error = manager.serve_read("key1", state_data)
        
        assert not success
        assert error is not None
    
    def test_serve_read_with_quorum(self, manager, state_data):
        """Test serving read with quorum check."""
        success, value, error = manager.serve_read_with_quorum("key1", state_data)
        
        assert success
        assert value == "value1"
        assert manager.quorum_reads == 1
    
    def test_read_nonexistent_key_from_lease(self, manager, state_data):
        """Test reading nonexistent key from lease."""
        manager.create_lease(term=1)
        
        success, value, error = manager.serve_read("nonexistent", state_data)
        
        assert success
        assert value is None
    
    # Lease Renewal Tests
    
    def test_renew_lease(self, manager):
        """Test renewing lease."""
        manager.create_lease(term=1)
        original_lease_id = manager.current_lease.lease_id
        
        success, error = manager.renew_lease()
        
        assert success
        assert error is None
        # New lease has different ID
        assert manager.current_lease.lease_id != original_lease_id
    
    def test_renew_lease_resets_timer(self, manager):
        """Test lease renewal resets expiry timer."""
        manager.create_lease(term=1)
        manager.current_lease.created_at = datetime.now() - timedelta(milliseconds=900)
        
        assert manager.current_lease.is_near_expiry()
        
        manager.renew_lease()
        
        assert not manager.current_lease.is_near_expiry()
    
    def test_cannot_renew_without_lease(self, manager):
        """Test cannot renew without active lease."""
        success, error = manager.renew_lease()
        
        assert not success
        assert error is not None
    
    # Lease Invalidation Tests
    
    def test_invalidate_lease(self, manager):
        """Test invalidating lease."""
        manager.create_lease(term=1)
        
        success, error = manager.invalidate_lease()
        
        assert success
        assert manager.current_lease is None
        assert not manager.can_serve_read_from_lease()
    
    def test_invalidate_lease_on_term_change(self, manager):
        """Test lease invalidation on term change."""
        manager.create_lease(term=1)
        original_term = manager.current_lease.term
        
        manager.invalidate_lease()
        manager.create_lease(term=2)
        
        assert manager.current_lease.term == 2
        assert manager.current_lease.term > original_term
    
    # Status Tests
    
    def test_get_lease_status_active(self, manager):
        """Test getting status of active lease."""
        manager.create_lease(term=1)
        
        status = manager.get_lease_status()
        
        assert status["active"]
        assert status["lease_id"] is not None
        assert status["state"] == "valid"
    
    def test_get_lease_status_no_lease(self, manager):
        """Test getting status without lease."""
        status = manager.get_lease_status()
        
        assert not status["active"]
        assert status["current_lease"] is None
    
    def test_get_lease_status_details(self, manager):
        """Test lease status contains details."""
        manager.create_lease(term=1)
        
        status = manager.get_lease_status()
        
        assert "elapsed_ms" in status
        assert "remaining_ms" in status
        assert status["remaining_ms"] > 0
    
    # Statistics Tests
    
    def test_get_statistics(self, manager, state_data):
        """Test getting statistics."""
        manager.create_lease(term=1)
        manager.serve_read("key1", state_data)
        
        stats = manager.get_statistics()
        
        assert stats["total_leases_created"] == 1
        assert stats["total_read_operations"] == 1
        assert stats["lease_served_reads"] == 1
        assert 0 <= stats["lease_served_ratio"] <= 1
    
    def test_statistics_quorum_ratio(self, manager, state_data):
        """Test statistics include quorum read ratio."""
        manager.create_lease(term=1)
        manager.serve_read("key1", state_data)
        manager.serve_read_with_quorum("key2", state_data)
        
        stats = manager.get_statistics()
        
        assert stats["total_read_operations"] == 2
        assert stats["lease_served_reads"] == 1
        assert stats["quorum_reads"] == 1
        assert stats["lease_served_ratio"] == 0.5
        assert stats["quorum_ratio"] == 0.5
    
    # Performance Tests
    
    def test_read_performance_lease_vs_quorum(self, manager, state_data):
        """Test read performance with lease vs quorum."""
        manager.create_lease(term=1)
        
        # Reads with lease (fast path)
        for _ in range(100):
            manager.serve_read("key1", state_data)
        
        stats = manager.get_statistics()
        
        assert stats["lease_served_reads"] == 100
        assert stats["lease_served_ratio"] == 1.0
    
    # Edge Cases
    
    def test_lease_exact_expiry(self, manager):
        """Test lease at exact expiry point."""
        manager.create_lease(term=1)
        manager.current_lease.created_at = datetime.now() - timedelta(milliseconds=1000)
        
        # Just at boundary
        assert not manager.current_lease.is_valid()
    
    def test_multiple_lease_cycles(self, manager, state_data):
        """Test multiple lease creation/renewal cycles."""
        for term in range(1, 5):
            manager.create_lease(term=term)
            manager.serve_read("key1", state_data)
            manager.renew_lease()
        
        assert manager.total_leases_created >= 4
        assert manager.read_operations >= 4
    
    def test_lease_history(self, manager):
        """Test lease history tracking."""
        manager.create_lease(term=1)
        manager.create_lease(term=2)
        
        assert len(manager.lease_history) == 2
        assert manager.lease_history[0].term == 1
        assert manager.lease_history[1].term == 2
