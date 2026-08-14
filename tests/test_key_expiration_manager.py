"""
Comprehensive tests for KeyExpirationManager.

Tests cover:
- TTL tracking and enforcement
- Lazy deletion on access
- Proactive expiration scanning
- TTL statistics and metrics
- Expiration event callbacks
- Background cleanup tasks
"""

import pytest
import time
import threading
from datetime import datetime, timedelta
from src.raft.key_expiration_manager import (
    KeyExpirationManager, TTLEntry, ExpirationStrategy, ExpirationEvent
)


class TestTTLEntry:
    """Tests for TTLEntry dataclass."""
    
    def test_ttl_entry_initialization(self):
        """Test TTLEntry initialization."""
        future = datetime.now() + timedelta(seconds=10)
        entry = TTLEntry(key="test-key", expiration_time=future, original_ttl_seconds=10)
        
        assert entry.key == "test-key"
        assert entry.original_ttl_seconds == 10
        assert entry.access_count == 0
    
    def test_is_expired_false(self):
        """Test is_expired returns False for future time."""
        future = datetime.now() + timedelta(seconds=10)
        entry = TTLEntry(key="test", expiration_time=future, original_ttl_seconds=10)
        assert entry.is_expired() is False
    
    def test_is_expired_true(self):
        """Test is_expired returns True for past time."""
        past = datetime.now() - timedelta(seconds=1)
        entry = TTLEntry(key="test", expiration_time=past, original_ttl_seconds=10)
        assert entry.is_expired() is True
    
    def test_time_to_expiration(self):
        """Test time_to_expiration calculation."""
        future = datetime.now() + timedelta(seconds=10)
        entry = TTLEntry(key="test", expiration_time=future, original_ttl_seconds=10)
        
        remaining = entry.time_to_expiration()
        assert 9 <= remaining <= 10
    
    def test_get_remaining_ttl(self):
        """Test getting remaining TTL in seconds."""
        future = datetime.now() + timedelta(seconds=10)
        entry = TTLEntry(key="test", expiration_time=future, original_ttl_seconds=10)
        
        remaining = entry.get_remaining_ttl()
        assert remaining in [9, 10]
    
    def test_to_dict_conversion(self):
        """Test conversion to dictionary."""
        future = datetime.now() + timedelta(seconds=10)
        entry = TTLEntry(key="test", expiration_time=future, original_ttl_seconds=10)
        
        data = entry.to_dict()
        assert data["key"] == "test"
        assert "remaining_ttl_seconds" in data
        assert "access_count" in data


class TestKeyExpirationManagerInitialization:
    """Tests for manager initialization."""
    
    def test_manager_init_lazy(self):
        """Test manager initialization with LAZY strategy."""
        manager = KeyExpirationManager(strategy=ExpirationStrategy.LAZY)
        assert manager.strategy == ExpirationStrategy.LAZY
        assert len(manager.ttl_entries) == 0
    
    def test_manager_init_proactive(self):
        """Test manager initialization with PROACTIVE strategy."""
        manager = KeyExpirationManager(strategy=ExpirationStrategy.PROACTIVE)
        assert manager.strategy == ExpirationStrategy.PROACTIVE
    
    def test_manager_init_hybrid(self):
        """Test manager initialization with HYBRID strategy."""
        manager = KeyExpirationManager(strategy=ExpirationStrategy.HYBRID)
        assert manager.strategy == ExpirationStrategy.HYBRID


class TestSetTTL:
    """Tests for setting TTL on keys."""
    
    def test_set_ttl_new_key(self):
        """Test setting TTL for a new key."""
        manager = KeyExpirationManager()
        result = manager.set_ttl("key1", 10.0)
        
        assert result is True
        assert "key1" in manager.ttl_entries
    
    def test_set_ttl_update_existing(self):
        """Test updating TTL for existing key."""
        manager = KeyExpirationManager()
        manager.set_ttl("key1", 10.0)
        
        old_entry = manager.ttl_entries["key1"]
        old_expiration = old_entry.expiration_time
        
        time.sleep(0.1)
        result = manager.set_ttl("key1", 20.0)
        
        assert result is True
        new_entry = manager.ttl_entries["key1"]
        # New expiration should be later
        assert new_entry.expiration_time > old_expiration
    
    def test_set_ttl_invalid_ttl(self):
        """Test setting invalid TTL."""
        manager = KeyExpirationManager()
        
        result = manager.set_ttl("key1", -5.0)
        assert result is False
        
        result = manager.set_ttl("key1", 0.0)
        assert result is False
    
    def test_set_ttl_multiple_keys(self):
        """Test setting TTL for multiple keys."""
        manager = KeyExpirationManager()
        
        for i in range(5):
            result = manager.set_ttl(f"key{i}", 10.0)
            assert result is True
        
        assert len(manager.ttl_entries) == 5


class TestRemoveTTL:
    """Tests for removing TTL."""
    
    def test_remove_ttl_existing(self):
        """Test removing TTL from existing key."""
        manager = KeyExpirationManager()
        manager.set_ttl("key1", 10.0)
        
        result = manager.remove_ttl("key1")
        assert result is True
        assert "key1" not in manager.ttl_entries
    
    def test_remove_ttl_nonexistent(self):
        """Test removing TTL from non-existent key."""
        manager = KeyExpirationManager()
        
        result = manager.remove_ttl("key1")
        assert result is False


class TestGetRemainingTTL:
    """Tests for getting remaining TTL."""
    
    def test_get_remaining_ttl_valid(self):
        """Test getting remaining TTL for valid key."""
        manager = KeyExpirationManager()
        manager.set_ttl("key1", 10.0)
        
        remaining = manager.get_remaining_ttl("key1")
        assert remaining is not None
        assert 9 <= remaining <= 10
    
    def test_get_remaining_ttl_nonexistent(self):
        """Test getting remaining TTL for non-existent key."""
        manager = KeyExpirationManager()
        
        remaining = manager.get_remaining_ttl("key1")
        assert remaining is None
    
    def test_get_remaining_ttl_increments_access_count(self):
        """Test that accessing increments access count."""
        manager = KeyExpirationManager()
        manager.set_ttl("key1", 10.0)
        
        entry = manager.ttl_entries["key1"]
        assert entry.access_count == 0
        
        manager.get_remaining_ttl("key1")
        assert entry.access_count == 1
        
        manager.get_remaining_ttl("key1")
        assert entry.access_count == 2


class TestLazyDeletion:
    """Tests for lazy deletion on access."""
    
    def test_check_and_delete_if_expired_not_expired(self):
        """Test checking non-expired key."""
        manager = KeyExpirationManager()
        manager.set_ttl("key1", 10.0)
        
        result = manager.check_and_delete_if_expired("key1")
        assert result is False
        assert "key1" in manager.ttl_entries
    
    def test_check_and_delete_if_expired_deleted(self):
        """Test checking expired key."""
        manager = KeyExpirationManager()
        future = datetime.now() - timedelta(seconds=1)
        
        entry = TTLEntry(key="key1", expiration_time=future, original_ttl_seconds=10)
        manager.ttl_entries["key1"] = entry
        
        result = manager.check_and_delete_if_expired("key1")
        assert result is True
        assert "key1" not in manager.ttl_entries
    
    def test_lazy_deletion_on_get_remaining_ttl(self):
        """Test lazy deletion when accessing expired key."""
        manager = KeyExpirationManager()
        future = datetime.now() - timedelta(seconds=1)
        
        entry = TTLEntry(key="key1", expiration_time=future, original_ttl_seconds=10)
        manager.ttl_entries["key1"] = entry
        
        remaining = manager.get_remaining_ttl("key1")
        assert remaining is None
        assert "key1" not in manager.ttl_entries


class TestBackgroundScanning:
    """Tests for background expiration scanning."""
    
    def test_start_background_scan(self):
        """Test starting background scan."""
        manager = KeyExpirationManager(strategy=ExpirationStrategy.PROACTIVE)
        
        result = manager.start_background_scan()
        assert result is True
        assert manager.is_scanning is True
        
        manager.stop_background_scan()
    
    def test_stop_background_scan(self):
        """Test stopping background scan."""
        manager = KeyExpirationManager(strategy=ExpirationStrategy.PROACTIVE)
        manager.start_background_scan()
        
        result = manager.stop_background_scan()
        assert result is True
        assert manager.is_scanning is False
    
    def test_background_scan_cannot_start_twice(self):
        """Test cannot start background scan twice."""
        manager = KeyExpirationManager(strategy=ExpirationStrategy.PROACTIVE)
        
        manager.start_background_scan()
        result = manager.start_background_scan()
        assert result is False
        
        manager.stop_background_scan()
    
    def test_lazy_strategy_no_background_scan(self):
        """Test background scan not needed for LAZY strategy."""
        manager = KeyExpirationManager(strategy=ExpirationStrategy.LAZY)
        
        result = manager.start_background_scan()
        assert result is False


class TestExpirationScanning:
    """Tests for expiration scanning."""
    
    def test_perform_expiration_scan_no_expired(self):
        """Test scanning with no expired keys."""
        manager = KeyExpirationManager()
        manager.set_ttl("key1", 10.0)
        manager.set_ttl("key2", 10.0)
        
        expired_count = manager.perform_expiration_scan()
        assert expired_count == 0
        assert len(manager.ttl_entries) == 2
    
    def test_perform_expiration_scan_with_expired(self):
        """Test scanning with expired keys."""
        manager = KeyExpirationManager()
        
        # Add non-expired key
        manager.set_ttl("key1", 10.0)
        
        # Add expired key
        future = datetime.now() - timedelta(seconds=1)
        entry = TTLEntry(key="key2", expiration_time=future, original_ttl_seconds=10)
        manager.ttl_entries["key2"] = entry
        import heapq
        heapq.heappush(manager.expiration_heap, (future, "key2"))
        
        expired_count = manager.perform_expiration_scan()
        assert expired_count == 1
        assert "key2" not in manager.ttl_entries
    
    def test_scan_respects_max_keys_per_scan(self):
        """Test scan respects max_keys_per_scan limit."""
        manager = KeyExpirationManager(max_keys_per_scan=2)
        
        # Add multiple expired keys
        for i in range(5):
            future = datetime.now() - timedelta(seconds=1)
            entry = TTLEntry(key=f"key{i}", expiration_time=future, original_ttl_seconds=10)
            manager.ttl_entries[f"key{i}"] = entry
            import heapq
            heapq.heappush(manager.expiration_heap, (future, f"key{i}"))
        
        expired_count = manager.perform_expiration_scan()
        assert expired_count == 2  # Limited by max_keys_per_scan


class TestExpirationCallbacks:
    """Tests for expiration callbacks."""
    
    def test_register_callback(self):
        """Test registering expiration callback."""
        manager = KeyExpirationManager()
        
        called_events = []
        def callback(key, event):
            called_events.append((key, event))
        
        manager.register_expiration_callback(callback)
        manager.set_ttl("key1", 10.0)
        
        # Check callback was called
        assert len(called_events) >= 1
    
    def test_callback_on_ttl_update(self):
        """Test callback called on TTL update."""
        manager = KeyExpirationManager()
        
        called_events = []
        def callback(key, event):
            called_events.append((key, event))
        
        manager.register_expiration_callback(callback)
        manager.set_ttl("key1", 10.0)
        
        # Update TTL
        manager.set_ttl("key1", 20.0)
        
        # Should have callback for update
        events = [e for k, e in called_events if e == ExpirationEvent.TTL_UPDATED]
        assert len(events) >= 1
    
    def test_callback_on_ttl_removed(self):
        """Test callback called when TTL removed."""
        manager = KeyExpirationManager()
        
        called_events = []
        def callback(key, event):
            called_events.append((key, event))
        
        manager.register_expiration_callback(callback)
        manager.set_ttl("key1", 10.0)
        manager.remove_ttl("key1")
        
        # Should have callback for removal
        events = [e for k, e in called_events if e == ExpirationEvent.TTL_REMOVED]
        assert len(events) >= 1


class TestStatistics:
    """Tests for statistics tracking."""
    
    def test_get_expiration_statistics(self):
        """Test getting expiration statistics."""
        manager = KeyExpirationManager()
        manager.set_ttl("key1", 10.0)
        manager.set_ttl("key2", 20.0)
        
        stats = manager.get_expiration_statistics()
        assert stats["current_ttl_entries"] == 2
        assert stats["total_keys_with_ttl"] == 2
    
    def test_statistics_include_ttl_ranges(self):
        """Test statistics include TTL ranges."""
        manager = KeyExpirationManager()
        manager.set_ttl("key1", 5.0)
        manager.set_ttl("key2", 15.0)
        manager.set_ttl("key3", 50.0)
        
        stats = manager.get_expiration_statistics()
        assert stats["min_ttl_seconds"] == 5.0
        assert stats["max_ttl_seconds"] == 50.0
        assert stats["average_ttl_seconds"] > 0
    
    def test_statistics_track_expirations(self):
        """Test statistics track expired keys."""
        manager = KeyExpirationManager()
        manager.set_ttl("key1", 10.0)
        
        # Manually expire a key
        manager.ttl_entries["key1"].expiration_time = datetime.now() - timedelta(seconds=1)
        manager.check_and_delete_if_expired("key1")
        
        stats = manager.get_expiration_statistics()
        assert stats["total_expired"] == 1
        assert stats["expired_on_access"] == 1


class TestGetTTLEntry:
    """Tests for getting full TTL entry."""
    
    def test_get_ttl_entry_valid(self):
        """Test getting valid TTL entry."""
        manager = KeyExpirationManager()
        manager.set_ttl("key1", 10.0)
        
        entry = manager.get_ttl_entry("key1")
        assert entry is not None
        assert entry["key"] == "key1"
    
    def test_get_ttl_entry_expired(self):
        """Test getting expired TTL entry."""
        manager = KeyExpirationManager()
        future = datetime.now() - timedelta(seconds=1)
        
        entry = TTLEntry(key="key1", expiration_time=future, original_ttl_seconds=10)
        manager.ttl_entries["key1"] = entry
        
        result = manager.get_ttl_entry("key1")
        assert result is None


class TestGetKeysExpiringsoon:
    """Tests for finding keys expiring soon."""
    
    def test_get_keys_expiring_soon(self):
        """Test finding keys expiring soon."""
        manager = KeyExpirationManager()
        manager.set_ttl("key1", 2.0)  # Expire soon
        manager.set_ttl("key2", 100.0)  # Expire later
        
        soon = manager.get_keys_expiring_soon(5.0)
        assert "key1" in soon
        assert "key2" not in soon
    
    def test_get_keys_expiring_soon_empty(self):
        """Test getting expiring keys when none exist."""
        manager = KeyExpirationManager()
        manager.set_ttl("key1", 10.0)
        
        soon = manager.get_keys_expiring_soon(1.0)
        assert len(soon) == 0


class TestClearAllTTLs:
    """Tests for clearing all TTLs."""
    
    def test_clear_all_ttls(self):
        """Test clearing all TTL entries."""
        manager = KeyExpirationManager()
        manager.set_ttl("key1", 10.0)
        manager.set_ttl("key2", 10.0)
        manager.set_ttl("key3", 10.0)
        
        count = manager.clear_all_ttls()
        assert count == 3
        assert len(manager.ttl_entries) == 0


class TestGetKeysByTTLRange:
    """Tests for getting keys by TTL range."""
    
    def test_get_keys_by_ttl_range(self):
        """Test getting keys within TTL range."""
        manager = KeyExpirationManager()
        manager.set_ttl("key1", 5.0)
        manager.set_ttl("key2", 15.0)
        manager.set_ttl("key3", 25.0)
        
        keys = manager.get_keys_by_ttl_range(10.0, 20.0)
        assert "key2" in keys
        assert "key1" not in keys
        assert "key3" not in keys


class TestExtendTTL:
    """Tests for extending TTL."""
    
    def test_extend_ttl_existing(self):
        """Test extending TTL for existing key."""
        manager = KeyExpirationManager()
        manager.set_ttl("key1", 10.0)
        
        entry_before = manager.ttl_entries["key1"]
        exp_before = entry_before.expiration_time
        
        time.sleep(0.1)
        result = manager.extend_ttl("key1", 5.0)
        
        assert result is True
        entry_after = manager.ttl_entries["key1"]
        assert entry_after.expiration_time > exp_before
    
    def test_extend_ttl_nonexistent(self):
        """Test extending TTL for non-existent key."""
        manager = KeyExpirationManager()
        
        result = manager.extend_ttl("key1", 5.0)
        assert result is False


class TestMostAccessedKeys:
    """Tests for finding most accessed expiring keys."""
    
    def test_get_most_accessed_expiring_keys(self):
        """Test getting most accessed expiring keys."""
        manager = KeyExpirationManager()
        manager.set_ttl("key1", 10.0)
        manager.set_ttl("key2", 10.0)
        manager.set_ttl("key3", 10.0)
        
        # Access keys different times
        for _ in range(5):
            manager.get_remaining_ttl("key1")
        
        for _ in range(2):
            manager.get_remaining_ttl("key2")
        
        keys = manager.get_most_accessed_expiring_keys(2)
        assert len(keys) == 2
        # key1 should be first (accessed more)
        assert keys[0]["key"] == "key1"


class TestExpirationDistribution:
    """Tests for expiration distribution."""
    
    def test_get_expiration_distribution(self):
        """Test getting expiration distribution."""
        manager = KeyExpirationManager()
        manager.set_ttl("key1", 10.0)
        manager.set_ttl("key2", 20.0)
        manager.set_ttl("key3", 50.0)
        
        distribution = manager.get_expiration_distribution(buckets=5)
        assert "buckets" in distribution
        assert "distribution" in distribution
        assert len(distribution["distribution"]) == 5


class TestComplexScenarios:
    """Tests for complex expiration scenarios."""
    
    def test_mixed_ttl_operations(self):
        """Test mixed TTL operations."""
        manager = KeyExpirationManager()
        
        # Add keys
        manager.set_ttl("key1", 10.0)
        manager.set_ttl("key2", 20.0)
        manager.set_ttl("key3", 30.0)
        
        # Check TTL
        remaining = manager.get_remaining_ttl("key1")
        assert remaining is not None
        
        # Extend one
        manager.extend_ttl("key2", 10.0)
        
        # Remove one
        manager.remove_ttl("key3")
        
        # Verify state
        assert "key1" in manager.ttl_entries
        assert "key2" in manager.ttl_entries
        assert "key3" not in manager.ttl_entries
    
    def test_expiration_under_load(self):
        """Test expiration tracking under load."""
        manager = KeyExpirationManager()
        
        # Add many keys
        for i in range(100):
            manager.set_ttl(f"key{i}", 30.0)
        
        # Access some
        for i in range(0, 50, 5):
            manager.get_remaining_ttl(f"key{i}")
        
        # Verify all still exist
        assert len(manager.ttl_entries) == 100
        
        stats = manager.get_expiration_statistics()
        assert stats["current_ttl_entries"] == 100


class TestThreadSafety:
    """Tests for thread safety."""
    
    def test_concurrent_ttl_operations(self):
        """Test concurrent TTL operations."""
        manager = KeyExpirationManager()
        results = []
        
        def add_keys(start, count):
            for i in range(start, start + count):
                manager.set_ttl(f"key{i}", 10.0)
                results.append(f"added-key{i}")
        
        threads = [
            threading.Thread(target=add_keys, args=(0, 25)),
            threading.Thread(target=add_keys, args=(25, 25)),
            threading.Thread(target=add_keys, args=(50, 25)),
        ]
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join()
        
        # All keys should exist
        assert len(manager.ttl_entries) == 75


class TestEdgeCases:
    """Tests for edge cases."""
    
    def test_very_small_ttl(self):
        """Test setting very small TTL."""
        manager = KeyExpirationManager()
        result = manager.set_ttl("key1", 0.001)
        assert result is True
    
    def test_very_large_ttl(self):
        """Test setting very large TTL."""
        manager = KeyExpirationManager()
        result = manager.set_ttl("key1", 86400 * 365)  # 1 year
        assert result is True
    
    def test_many_keys_expiring_at_once(self):
        """Test many keys expiring simultaneously."""
        manager = KeyExpirationManager(max_keys_per_scan=100)
        
        # Add expired keys
        for i in range(50):
            future = datetime.now() - timedelta(seconds=1)
            entry = TTLEntry(key=f"key{i}", expiration_time=future, original_ttl_seconds=10)
            manager.ttl_entries[f"key{i}"] = entry
            import heapq
            heapq.heappush(manager.expiration_heap, (future, f"key{i}"))
        
        expired_count = manager.perform_expiration_scan()
        assert expired_count == 50
