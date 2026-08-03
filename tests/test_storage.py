"""
Unit tests for the storage engine.

Tests cover basic operations (GET, SET, DELETE), TTL functionality,
and concurrent access patterns.
"""

import asyncio
import time
import pytest
from src.storage.store import KeyValueStore


@pytest.fixture
async def store():
    """Fixture providing a fresh KeyValueStore instance."""
    store = KeyValueStore()
    yield store
    await store.clear()


class TestBasicOperations:
    """Test basic GET, SET, DELETE operations."""
    
    @pytest.mark.asyncio
    async def test_set_and_get(self, store):
        """Test setting and retrieving a value."""
        await store.set("key1", "value1")
        result = await store.get("key1")
        assert result == "value1"
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_key(self, store):
        """Test getting a key that doesn't exist."""
        result = await store.get("nonexistent")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_with_default(self, store):
        """Test getting a key with a default value."""
        result = await store.get("nonexistent", default="default_value")
        assert result == "default_value"
    
    @pytest.mark.asyncio
    async def test_delete_existing_key(self, store):
        """Test deleting an existing key."""
        await store.set("key1", "value1")
        deleted = await store.delete("key1")
        assert deleted is True
        result = await store.get("key1")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_delete_nonexistent_key(self, store):
        """Test deleting a key that doesn't exist."""
        deleted = await store.delete("nonexistent")
        assert deleted is False
    
    @pytest.mark.asyncio
    async def test_set_overwrites_value(self, store):
        """Test that setting a key overwrites the previous value."""
        await store.set("key1", "value1")
        await store.set("key1", "value2")
        result = await store.get("key1")
        assert result == "value2"
    
    @pytest.mark.asyncio
    async def test_exists_existing_key(self, store):
        """Test checking existence of an existing key."""
        await store.set("key1", "value1")
        exists = await store.exists("key1")
        assert exists is True
    
    @pytest.mark.asyncio
    async def test_exists_nonexistent_key(self, store):
        """Test checking existence of a non-existent key."""
        exists = await store.exists("nonexistent")
        assert exists is False


class TestTTLOperations:
    """Test TTL (time-to-live) functionality."""
    
    @pytest.mark.asyncio
    async def test_ttl_expiration(self, store):
        """Test that entries expire after TTL."""
        await store.set("key1", "value1", ttl_seconds=0.1)
        result = await store.get("key1")
        assert result == "value1"
        
        # Wait for expiry
        await asyncio.sleep(0.15)
        result = await store.get("key1")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_ttl_delete_removes_expiry(self, store):
        """Test that deleting a key removes its expiry."""
        await store.set("key1", "value1", ttl_seconds=1.0)
        await store.delete("key1")
        
        # Reset with no TTL
        await store.set("key1", "value2")
        await asyncio.sleep(1.1)
        
        # Should still exist since TTL was removed
        result = await store.get("key1")
        assert result == "value2"
    
    @pytest.mark.asyncio
    async def test_ttl_reset_by_set(self, store):
        """Test that setting a key without TTL removes the previous TTL."""
        await store.set("key1", "value1", ttl_seconds=0.1)
        await asyncio.sleep(0.05)
        
        # Re-set without TTL
        await store.set("key1", "value2")
        await asyncio.sleep(0.1)
        
        # Should still exist
        result = await store.get("key1")
        assert result == "value2"
    
    @pytest.mark.asyncio
    async def test_exists_returns_false_for_expired(self, store):
        """Test that exists() returns False for expired keys."""
        await store.set("key1", "value1", ttl_seconds=0.1)
        assert await store.exists("key1") is True
        
        await asyncio.sleep(0.15)
        assert await store.exists("key1") is False


class TestBulkOperations:
    """Test operations on multiple keys."""
    
    @pytest.mark.asyncio
    async def test_get_all(self, store):
        """Test retrieving all key-value pairs."""
        await store.set("key1", "value1")
        await store.set("key2", "value2")
        await store.set("key3", "value3")
        
        all_items = await store.get_all()
        assert len(all_items) == 3
        assert all_items["key1"] == "value1"
        assert all_items["key2"] == "value2"
        assert all_items["key3"] == "value3"
    
    @pytest.mark.asyncio
    async def test_get_all_excludes_expired(self, store):
        """Test that get_all() excludes expired entries."""
        await store.set("key1", "value1")
        await store.set("key2", "value2", ttl_seconds=0.1)
        await store.set("key3", "value3")
        
        await asyncio.sleep(0.15)
        all_items = await store.get_all()
        
        assert len(all_items) == 2
        assert "key1" in all_items
        assert "key2" not in all_items
        assert "key3" in all_items
    
    @pytest.mark.asyncio
    async def test_size(self, store):
        """Test getting the size of the store."""
        assert await store.size() == 0
        
        await store.set("key1", "value1")
        await store.set("key2", "value2")
        assert await store.size() == 2
        
        await store.delete("key1")
        assert await store.size() == 1
    
    @pytest.mark.asyncio
    async def test_size_excludes_expired(self, store):
        """Test that size() excludes expired entries."""
        await store.set("key1", "value1")
        await store.set("key2", "value2", ttl_seconds=0.1)
        await store.set("key3", "value3")
        
        assert await store.size() == 3
        await asyncio.sleep(0.15)
        assert await store.size() == 2
    
    @pytest.mark.asyncio
    async def test_clear(self, store):
        """Test clearing all entries."""
        await store.set("key1", "value1")
        await store.set("key2", "value2")
        await store.clear()
        
        assert await store.size() == 0
        assert await store.get("key1") is None


class TestConcurrency:
    """Test concurrent operations."""
    
    @pytest.mark.asyncio
    async def test_concurrent_sets(self, store):
        """Test concurrent SET operations."""
        async def set_key(key, value):
            await store.set(key, value)
        
        tasks = [set_key(f"key{i}", f"value{i}") for i in range(10)]
        await asyncio.gather(*tasks)
        
        assert await store.size() == 10
    
    @pytest.mark.asyncio
    async def test_concurrent_mixed_operations(self, store):
        """Test concurrent GET, SET, DELETE operations."""
        # Pre-populate
        for i in range(5):
            await store.set(f"key{i}", f"value{i}")
        
        async def mixed_ops():
            # Some GETs
            await store.get("key1")
            await store.get("key2")
            # Some SETs
            await store.set("key10", "value10")
            await store.set("key11", "value11")
            # Some DELETEs
            await store.delete("key1")
        
        tasks = [mixed_ops() for _ in range(5)]
        await asyncio.gather(*tasks)
        
        # Just verify no crashes occurred
        final_size = await store.size()
        assert final_size > 0


class TestCleanup:
    """Test cleanup of expired entries."""
    
    @pytest.mark.asyncio
    async def test_cleanup_expired(self, store):
        """Test manual cleanup of expired entries."""
        await store.set("key1", "value1")
        await store.set("key2", "value2", ttl_seconds=0.1)
        await store.set("key3", "value3")
        
        assert await store.size() == 3
        
        await asyncio.sleep(0.15)
        await store.cleanup_expired()
        
        assert await store.size() == 2
        assert await store.exists("key2") is False


class TestEdgeCases:
    """Test edge cases and corner conditions."""
    
    @pytest.mark.asyncio
    async def test_set_none_value(self, store):
        """Test setting None as a value."""
        await store.set("key1", None)
        result = await store.get("key1")
        assert result is None
        assert await store.exists("key1") is True
    
    @pytest.mark.asyncio
    async def test_set_complex_types(self, store):
        """Test setting complex types as values."""
        complex_value = {"nested": {"list": [1, 2, 3]}, "tuple": (4, 5, 6)}
        await store.set("complex", complex_value)
        result = await store.get("complex")
        assert result == complex_value
    
    @pytest.mark.asyncio
    async def test_empty_string_key(self, store):
        """Test empty string as a key."""
        await store.set("", "empty_key_value")
        result = await store.get("")
        assert result == "empty_key_value"
    
    @pytest.mark.asyncio
    async def test_very_long_key(self, store):
        """Test very long key."""
        long_key = "k" * 10000
        await store.set(long_key, "value")
        result = await store.get(long_key)
        assert result == "value"
    
    @pytest.mark.asyncio
    async def test_zero_ttl(self, store):
        """Test setting TTL to zero (expires immediately)."""
        await store.set("key1", "value1", ttl_seconds=0.0)
        # Should be expired immediately
        await asyncio.sleep(0.01)
        result = await store.get("key1")
        assert result is None
