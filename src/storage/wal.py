"""
Write-Ahead Log (WAL) implementation.

The WAL ensures that all state changes are persisted to disk before being applied
to the in-memory state machine. This guarantees durability and enables recovery
after crashes.

WAL entries are appended in order and represent operations to be applied.
"""

import asyncio
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass
class WALEntry:
    """
    A single entry in the write-ahead log.
    
    Attributes:
        timestamp: When the entry was created (ISO format string)
        operation: Type of operation ('SET', 'DELETE', 'CLEAR')
        key: The key affected (None for CLEAR)
        value: The value being set (None for DELETE or CLEAR)
        ttl_seconds: Optional TTL in seconds
    """
    timestamp: str
    operation: str
    key: Optional[str] = None
    value: Optional[Any] = None
    ttl_seconds: Optional[float] = None
    
    def to_json_line(self) -> str:
        """Convert entry to a JSON line for file storage."""
        return json.dumps(asdict(self)) + "\n"
    
    @classmethod
    def from_json_line(cls, line: str) -> "WALEntry":
        """Parse a WALEntry from a JSON line."""
        data = json.loads(line.strip())
        return cls(**data)


class WriteAheadLog:
    """
    Write-ahead log manager.
    
    Handles reading/writing WAL entries to disk with proper fsync() to ensure
    durability. Entries are stored as JSON lines (one per line) for easy recovery.
    """
    
    def __init__(self, log_path: str = "kv_wal.log"):
        """
        Initialize the WAL manager.
        
        Args:
            log_path: Path to the WAL file
        """
        self.log_path = Path(log_path)
        self._lock = asyncio.Lock()
        self._file_handle: Optional[object] = None
    
    async def append(self, entry: WALEntry) -> None:
        """
        Append an entry to the WAL with fsync() guarantee.
        
        This is critical for correctness: we MUST persist to disk before
        proceeding with any state change.
        
        Args:
            entry: The WALEntry to append
            
        Raises:
            IOError: If the write or fsync fails
        """
        async with self._lock:
            try:
                # Open in append mode, create if not exists
                with open(self.log_path, "a") as f:
                    f.write(entry.to_json_line())
                    # fsync to ensure data is on disk
                    os.fsync(f.fileno())
            except IOError as e:
                raise IOError(f"Failed to append to WAL at {self.log_path}: {e}")
    
    async def append_set(self, key: str, value: Any, ttl_seconds: Optional[float] = None) -> None:
        """
        Append a SET operation to the WAL.
        
        Args:
            key: The key being set
            value: The value being set
            ttl_seconds: Optional TTL in seconds
        """
        entry = WALEntry(
            timestamp=datetime.utcnow().isoformat(),
            operation="SET",
            key=key,
            value=value,
            ttl_seconds=ttl_seconds
        )
        await self.append(entry)
    
    async def append_delete(self, key: str) -> None:
        """
        Append a DELETE operation to the WAL.
        
        Args:
            key: The key being deleted
        """
        entry = WALEntry(
            timestamp=datetime.utcnow().isoformat(),
            operation="DELETE",
            key=key
        )
        await self.append(entry)
    
    async def append_clear(self) -> None:
        """Append a CLEAR operation to the WAL (clears all entries)."""
        entry = WALEntry(
            timestamp=datetime.utcnow().isoformat(),
            operation="CLEAR"
        )
        await self.append(entry)
    
    async def read_all(self) -> list[WALEntry]:
        """
        Read all entries from the WAL file.
        
        Used during startup for crash recovery.
        Gracefully handles empty files and malformed entries.
        
        Returns:
            List of all WALEntry objects in order
        """
        async with self._lock:
            if not self.log_path.exists():
                return []
            
            entries = []
            try:
                with open(self.log_path, "r") as f:
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if not line:  # Skip empty lines
                            continue
                        try:
                            entries.append(WALEntry.from_json_line(line))
                        except (json.JSONDecodeError, TypeError, KeyError) as e:
                            # Log and skip malformed entries
                            import logging
                            logger = logging.getLogger(__name__)
                            logger.warning(
                                f"Skipping malformed WAL entry at line {line_num}: {e}"
                            )
                            continue
            except IOError as e:
                raise IOError(f"Failed to read WAL from {self.log_path}: {e}")
            
            return entries
    
    async def clear_log(self) -> None:
        """
        Clear the WAL file (called after successful state machine snapshot).
        
        This is typically done during log compaction or snapshotting.
        """
        async with self._lock:
            if self.log_path.exists():
                self.log_path.unlink()
    
    async def rotate_log(self, backup_path: Optional[str] = None) -> None:
        """
        Rotate the WAL file to a backup and create a new empty log.
        
        Used for log compaction in Phase 7.
        
        Args:
            backup_path: Optional path to save the current log as backup
        """
        async with self._lock:
            if self.log_path.exists():
                if backup_path:
                    import shutil
                    shutil.copy2(self.log_path, backup_path)
                self.log_path.unlink()
    
    async def get_size(self) -> int:
        """
        Get the size of the WAL file in bytes.
        
        Args:
            Size of the log file, or 0 if it doesn't exist
        """
        async with self._lock:
            if self.log_path.exists():
                return self.log_path.stat().st_size
            return 0


class PersistentKeyValueStore:
    """
    Key-value store wrapper that adds WAL persistence.
    
    All operations are logged to the WAL before being applied to the in-memory store.
    This ensures durability and enables recovery.
    """
    
    def __init__(self, store: Any, wal_path: str = "kv_wal.log"):
        """
        Initialize with an in-memory store and WAL.
        
        Args:
            store: The in-memory KeyValueStore instance
            wal_path: Path to the WAL file
        """
        self.store = store
        self.wal = WriteAheadLog(wal_path)
    
    async def get(self, key: str, default: Optional[Any] = None) -> Optional[Any]:
        """Get a value (no WAL needed for reads)."""
        return await self.store.get(key, default)
    
    async def set(self, key: str, value: Any, ttl_seconds: Optional[float] = None) -> None:
        """
        Set a value with WAL persistence.
        
        WAL is written BEFORE the in-memory store is updated.
        """
        await self.wal.append_set(key, value, ttl_seconds)
        await self.store.set(key, value, ttl_seconds)
    
    async def delete(self, key: str) -> bool:
        """
        Delete a value with WAL persistence.
        
        WAL is written BEFORE the in-memory store is updated.
        """
        result = await self.store.delete(key)
        if result:
            await self.wal.append_delete(key)
        return result
    
    async def exists(self, key: str) -> bool:
        """Check if a key exists (no WAL needed for reads)."""
        return await self.store.exists(key)
    
    async def clear(self) -> None:
        """
        Clear all entries with WAL persistence.
        
        WAL is written BEFORE the in-memory store is updated.
        """
        await self.wal.append_clear()
        await self.store.clear()
    
    async def get_all(self) -> dict[str, Any]:
        """Get all entries (no WAL needed for reads)."""
        return await self.store.get_all()
    
    async def size(self) -> int:
        """Get store size (no WAL needed for reads)."""
        return await self.store.size()
    
    async def recover_from_wal(self) -> int:
        """
        Recover the in-memory store from the WAL.
        
        Called on startup. Replays all WAL entries to restore state.
        
        Returns:
            Number of entries replayed
        """
        entries = await self.wal.read_all()
        replayed = 0
        
        for entry in entries:
            if entry.operation == "SET":
                await self.store.set(entry.key, entry.value, entry.ttl_seconds)
                replayed += 1
            elif entry.operation == "DELETE":
                await self.store.delete(entry.key)
                replayed += 1
            elif entry.operation == "CLEAR":
                await self.store.clear()
                replayed += 1
        
        return replayed
