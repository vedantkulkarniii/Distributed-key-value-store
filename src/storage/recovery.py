"""
Crash recovery and startup logic.

Handles reading the WAL on startup and replaying it to restore the in-memory
state machine to the point of failure.
"""

import logging
from pathlib import Path
from typing import Optional

from .store import KeyValueStore
from .wal import WriteAheadLog, PersistentKeyValueStore


logger = logging.getLogger(__name__)


class StorageEngine:
    """
    High-level storage engine with crash recovery.
    
    Combines in-memory store, WAL, and recovery logic into a single interface.
    """
    
    def __init__(self, wal_path: str = "kv_wal.log", enable_recovery: bool = True):
        """
        Initialize the storage engine with optional crash recovery.
        
        Args:
            wal_path: Path to the WAL file
            enable_recovery: Whether to replay WAL on startup (default: True)
        """
        self.wal_path = wal_path
        self.in_memory_store = KeyValueStore()
        self.persistent_store = PersistentKeyValueStore(
            self.in_memory_store,
            wal_path=wal_path
        )
        self._recovered = False
    
    async def start(self) -> None:
        """
        Initialize the storage engine and perform crash recovery.
        
        Should be called during application startup.
        """
        logger.info(f"Starting storage engine with WAL at {self.wal_path}")
        
        # Check if WAL file exists
        if Path(self.wal_path).exists():
            logger.info("WAL file found, starting crash recovery...")
            entries_replayed = await self.persistent_store.recover_from_wal()
            logger.info(f"Crash recovery complete: replayed {entries_replayed} WAL entries")
            self._recovered = True
        else:
            logger.info("No WAL file found, starting with empty store")
    
    async def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get a value by key."""
        return await self.persistent_store.get(key, default)
    
    async def set(self, key: str, value: str) -> None:
        """Set a key-value pair (persisted to WAL)."""
        await self.persistent_store.set(key, value)
    
    async def delete(self, key: str) -> bool:
        """Delete a key-value pair (persisted to WAL)."""
        return await self.persistent_store.delete(key)
    
    async def exists(self, key: str) -> bool:
        """Check if a key exists."""
        return await self.persistent_store.exists(key)
    
    async def clear(self) -> None:
        """Clear all entries (persisted to WAL)."""
        await self.persistent_store.clear()
    
    async def get_all(self) -> dict[str, str]:
        """Get all key-value pairs."""
        return await self.persistent_store.get_all()
    
    async def size(self) -> int:
        """Get the number of entries."""
        return await self.persistent_store.size()
    
    async def clear_wal(self) -> None:
        """Clear the WAL file (typically after snapshotting)."""
        await self.persistent_store.wal.clear_log()
    
    async def get_wal_size(self) -> int:
        """Get the size of the WAL file in bytes."""
        return await self.persistent_store.wal.get_size()
    
    @property
    def was_recovered(self) -> bool:
        """
        Check if the store was recovered from a previous crash.
        
        Returns:
            True if crash recovery was performed
        """
        return self._recovered
