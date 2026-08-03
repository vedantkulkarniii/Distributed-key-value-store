"""
In-memory key-value store implementation.

This module provides a simple, thread-safe (via asyncio) in-memory dictionary-backed
key-value store with support for GET, SET, and DELETE operations.
"""

import asyncio
from typing import Any, Optional


class KeyValueStore:
    """
    Simple in-memory key-value store.
    
    Thread-safe within asyncio context (uses asyncio.Lock for mutations).
    """
    
    def __init__(self):
        """Initialize an empty key-value store."""
        self._store: dict[str, Any] = {}
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a value by key.
        
        Args:
            key: The key to look up
            
        Returns:
            The value if the key exists, None otherwise
        """
        async with self._lock:
            return self._store.get(key)
    
    async def set(self, key: str, value: Any) -> None:
        """
        Set a key-value pair.
        
        Args:
            key: The key to set
            value: The value to associate with the key
        """
        async with self._lock:
            self._store[key] = value
    
    async def delete(self, key: str) -> bool:
        """
        Delete a key-value pair.
        
        Args:
            key: The key to delete
            
        Returns:
            True if the key existed and was deleted, False if it didn't exist
        """
        async with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False
    
    async def exists(self, key: str) -> bool:
        """
        Check if a key exists in the store.
        
        Args:
            key: The key to check
            
        Returns:
            True if the key exists, False otherwise
        """
        async with self._lock:
            return key in self._store
    
    async def clear(self) -> None:
        """Clear all entries from the store."""
        async with self._lock:
            self._store.clear()
    
    async def get_all(self) -> dict[str, Any]:
        """
        Get a snapshot of all key-value pairs.
        
        Returns:
            A copy of the current store contents
        """
        async with self._lock:
            return self._store.copy()
    
    async def size(self) -> int:
        """
        Get the number of entries in the store.
        
        Returns:
            The count of key-value pairs
        """
        async with self._lock:
            return len(self._store)
