"""
In-memory key-value store implementation.

This module provides a simple, thread-safe (via asyncio) in-memory dictionary-backed
key-value store with support for GET, SET, and DELETE operations. Optional TTL support
allows entries to expire after a specified duration.
"""

import asyncio
import time
from typing import Any, Optional


class KeyValueStore:
    """
    Simple in-memory key-value store with optional TTL support.
    
    Thread-safe within asyncio context (uses asyncio.Lock for mutations).
    Expired entries are lazily removed on access and via a background cleanup task.
    """
    
    def __init__(self):
        """Initialize an empty key-value store."""
        self._store: dict[str, Any] = {}
        self._expiry: dict[str, float] = {}  # Maps keys to expiration timestamps
        self._lock = asyncio.Lock()
    
    def _is_expired(self, key: str) -> bool:
        """
        Check if a key has expired.
        
        Args:
            key: The key to check
            
        Returns:
            True if the key has an expiry time and it has passed
        """
        if key not in self._expiry:
            return False
        return time.time() >= self._expiry[key]
    
    def _remove_if_expired(self, key: str) -> None:
        """
        Remove a key if it has expired (caller must hold lock).
        
        Args:
            key: The key to check and potentially remove
        """
        if key in self._store and self._is_expired(key):
            del self._store[key]
            del self._expiry[key]
    
    async def get(self, key: str, default: Optional[Any] = None) -> Optional[Any]:
        """
        Retrieve a value by key.
        
        Args:
            key: The key to look up
            default: Value to return if key doesn't exist or is expired
            
        Returns:
            The value if the key exists and hasn't expired, default otherwise
        """
        async with self._lock:
            self._remove_if_expired(key)
            return self._store.get(key, default)
    
    async def set(self, key: str, value: Any, ttl_seconds: Optional[float] = None) -> None:
        """
        Set a key-value pair with optional TTL.
        
        Args:
            key: The key to set
            value: The value to associate with the key
            ttl_seconds: Optional time-to-live in seconds. If set, the entry expires after this duration.
        """
        async with self._lock:
            self._store[key] = value
            if ttl_seconds is not None:
                self._expiry[key] = time.time() + ttl_seconds
            elif key in self._expiry:
                # Remove expiry if setting without TTL
                del self._expiry[key]
    
    async def delete(self, key: str) -> bool:
        """
        Delete a key-value pair.
        
        Args:
            key: The key to delete
            
        Returns:
            True if the key existed (and wasn't expired) and was deleted, False otherwise
        """
        async with self._lock:
            self._remove_if_expired(key)
            if key in self._store:
                del self._store[key]
                if key in self._expiry:
                    del self._expiry[key]
                return True
            return False
    
    async def exists(self, key: str) -> bool:
        """
        Check if a key exists in the store.
        
        Args:
            key: The key to check
            
        Returns:
            True if the key exists and hasn't expired, False otherwise
        """
        async with self._lock:
            self._remove_if_expired(key)
            return key in self._store
    
    async def clear(self) -> None:
        """Clear all entries from the store."""
        async with self._lock:
            self._store.clear()
            self._expiry.clear()
    
    async def get_all(self) -> dict[str, Any]:
        """
        Get a snapshot of all non-expired key-value pairs.
        
        Returns:
            A copy of the current store contents (expired entries removed)
        """
        async with self._lock:
            # Remove all expired entries first
            expired_keys = [k for k in self._store if self._is_expired(k)]
            for k in expired_keys:
                del self._store[k]
                if k in self._expiry:
                    del self._expiry[k]
            return self._store.copy()
    
    async def size(self) -> int:
        """
        Get the number of non-expired entries in the store.
        
        Returns:
            The count of key-value pairs
        """
        async with self._lock:
            # Remove expired entries for accurate count
            expired_keys = [k for k in self._store if self._is_expired(k)]
            for k in expired_keys:
                del self._store[k]
                if k in self._expiry:
                    del self._expiry[k]
            return len(self._store)
    
    async def cleanup_expired(self) -> None:
        """
        Cleanup all expired entries. Can be called periodically or by background task.
        """
        async with self._lock:
            expired_keys = [k for k in self._store if self._is_expired(k)]
            for k in expired_keys:
                del self._store[k]
                if k in self._expiry:
                    del self._expiry[k]
