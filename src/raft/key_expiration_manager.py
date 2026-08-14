"""
Key Expiration & TTL Management.

Implements TTL tracking and expiration handling:
- TTL tracking and enforcement
- Lazy deletion on access
- Proactive expiration scanning
- TTL statistics and metrics
- Expiration event callbacks
- Background cleanup tasks
"""

import logging
import time
import threading
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from heapq import heappush, heappop, heappushpop
import threading

logger = logging.getLogger(__name__)


class ExpirationStrategy(Enum):
    """Strategy for handling expirations."""
    LAZY = "lazy"  # Delete on access
    PROACTIVE = "proactive"  # Periodic background cleanup
    HYBRID = "hybrid"  # Both lazy and proactive


class ExpirationEvent(Enum):
    """Types of expiration events."""
    EXPIRED_ON_ACCESS = "expired_on_access"
    EXPIRED_BY_SCAN = "expired_by_scan"
    TTL_UPDATED = "ttl_updated"
    TTL_REMOVED = "ttl_removed"


@dataclass
class TTLEntry:
    """Represents a key with TTL."""
    key: str
    expiration_time: datetime
    original_ttl_seconds: float
    creation_time: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    last_accessed: datetime = field(default_factory=datetime.now)
    
    def is_expired(self) -> bool:
        """Check if entry has expired."""
        return datetime.now() >= self.expiration_time
    
    def time_to_expiration(self) -> float:
        """Get seconds until expiration."""
        delta = self.expiration_time - datetime.now()
        return max(0.0, delta.total_seconds())
    
    def get_remaining_ttl(self) -> int:
        """Get remaining TTL in seconds."""
        return max(0, int(self.time_to_expiration()))
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "key": self.key,
            "expiration_time": self.expiration_time.isoformat(),
            "remaining_ttl_seconds": self.get_remaining_ttl(),
            "original_ttl_seconds": self.original_ttl_seconds,
            "access_count": self.access_count,
            "age_seconds": (datetime.now() - self.creation_time).total_seconds()
        }


@dataclass
class ExpirationStats:
    """Statistics about key expirations."""
    total_keys_with_ttl: int = 0
    total_expired: int = 0
    expired_on_access: int = 0
    expired_by_scan: int = 0
    current_ttl_entries: int = 0
    average_ttl_seconds: float = 0.0
    min_ttl_seconds: float = 0.0
    max_ttl_seconds: float = 0.0
    keys_expiring_in_minute: int = 0
    keys_expiring_in_hour: int = 0
    last_scan_time: Optional[datetime] = None
    last_scan_duration_ms: float = 0.0
    total_scans: int = 0
    total_expired_in_scans: int = 0
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "total_keys_with_ttl": self.total_keys_with_ttl,
            "total_expired": self.total_expired,
            "expired_on_access": self.expired_on_access,
            "expired_by_scan": self.expired_by_scan,
            "current_ttl_entries": self.current_ttl_entries,
            "average_ttl_seconds": round(self.average_ttl_seconds, 2),
            "min_ttl_seconds": round(self.min_ttl_seconds, 2),
            "max_ttl_seconds": round(self.max_ttl_seconds, 2),
            "keys_expiring_in_minute": self.keys_expiring_in_minute,
            "keys_expiring_in_hour": self.keys_expiring_in_hour,
            "last_scan_time": self.last_scan_time.isoformat() if self.last_scan_time else None,
            "last_scan_duration_ms": round(self.last_scan_duration_ms, 2),
            "total_scans": self.total_scans
        }


class KeyExpirationManager:
    """Manages key expiration and TTL lifecycle."""
    
    def __init__(
        self,
        strategy: ExpirationStrategy = ExpirationStrategy.HYBRID,
        scan_interval_seconds: float = 5.0,
        max_keys_per_scan: int = 1000
    ):
        """
        Initialize key expiration manager.
        
        Args:
            strategy: Expiration handling strategy
            scan_interval_seconds: How often to run proactive scans
            max_keys_per_scan: Maximum keys to process per scan
        """
        self.strategy = strategy
        self.scan_interval_seconds = scan_interval_seconds
        self.max_keys_per_scan = max_keys_per_scan
        
        # TTL tracking
        self.ttl_entries: Dict[str, TTLEntry] = {}
        self.expiration_heap: List[tuple] = []  # Min-heap of (expiration_time, key)
        self.expiration_callbacks: List[Callable[[str, ExpirationEvent], None]] = []
        
        # Statistics
        self.stats = ExpirationStats()
        self.lock = threading.RLock()
        
        # Background scanning
        self.is_scanning = False
        self.scan_thread: Optional[threading.Thread] = None
    
    def set_ttl(self, key: str, ttl_seconds: float) -> bool:
        """
        Set or update TTL for a key.
        
        Args:
            key: Key to set TTL for
            ttl_seconds: Time to live in seconds
            
        Returns:
            True if successful
        """
        if ttl_seconds <= 0:
            logger.warning(f"Invalid TTL for key {key}: {ttl_seconds}")
            return False
        
        with self.lock:
            expiration_time = datetime.now() + timedelta(seconds=ttl_seconds)
            
            # Check if updating existing key
            if key in self.ttl_entries:
                old_entry = self.ttl_entries[key]
                old_entry.expiration_time = expiration_time
                old_entry.original_ttl_seconds = ttl_seconds
                self._trigger_callback(key, ExpirationEvent.TTL_UPDATED)
            else:
                # New entry
                entry = TTLEntry(
                    key=key,
                    expiration_time=expiration_time,
                    original_ttl_seconds=ttl_seconds
                )
                self.ttl_entries[key] = entry
                self.stats.total_keys_with_ttl += 1
            
            # Add to heap for efficient expiration checking
            heappush(self.expiration_heap, (expiration_time, key))
            self._update_statistics()
            
            logger.debug(f"Set TTL for {key}: {ttl_seconds}s")
            return True
    
    def remove_ttl(self, key: str) -> bool:
        """
        Remove TTL for a key (make it permanent).
        
        Args:
            key: Key to remove TTL from
            
        Returns:
            True if removed
        """
        with self.lock:
            if key not in self.ttl_entries:
                return False
            
            del self.ttl_entries[key]
            self._trigger_callback(key, ExpirationEvent.TTL_REMOVED)
            self._update_statistics()
            return True
    
    def get_remaining_ttl(self, key: str) -> Optional[int]:
        """
        Get remaining TTL for a key.
        
        Args:
            key: Key to check
            
        Returns:
            Remaining TTL in seconds, or None if no TTL set
        """
        with self.lock:
            if key not in self.ttl_entries:
                return None
            
            entry = self.ttl_entries[key]
            entry.access_count += 1
            entry.last_accessed = datetime.now()
            
            # Check if expired (lazy deletion)
            if entry.is_expired():
                return None  # Treat as if key doesn't exist
            
            return entry.get_remaining_ttl()
    
    def check_and_delete_if_expired(self, key: str) -> bool:
        """
        Check if key has expired and delete it if so (lazy deletion).
        
        Args:
            key: Key to check
            
        Returns:
            True if key was deleted, False if not expired or doesn't exist
        """
        with self.lock:
            if key not in self.ttl_entries:
                return False
            
            entry = self.ttl_entries[key]
            
            if entry.is_expired():
                del self.ttl_entries[key]
                self.stats.expired_on_access += 1
                self.stats.total_expired += 1
                self._trigger_callback(key, ExpirationEvent.EXPIRED_ON_ACCESS)
                self._update_statistics()
                logger.debug(f"Key {key} expired and deleted on access")
                return True
            
            return False
    
    def start_background_scan(self) -> bool:
        """
        Start background expiration scanning.
        
        Returns:
            True if started
        """
        if self.strategy == ExpirationStrategy.LAZY:
            logger.warning("Background scan not needed for LAZY strategy")
            return False
        
        if self.is_scanning:
            logger.warning("Background scan already running")
            return False
        
        self.is_scanning = True
        self.scan_thread = threading.Thread(
            target=self._scan_worker,
            daemon=True
        )
        self.scan_thread.start()
        logger.info("Background expiration scanning started")
        return True
    
    def stop_background_scan(self) -> bool:
        """
        Stop background expiration scanning.
        
        Returns:
            True if stopped
        """
        if not self.is_scanning:
            return False
        
        self.is_scanning = False
        
        if self.scan_thread:
            self.scan_thread.join(timeout=5.0)
        
        logger.info("Background expiration scanning stopped")
        return True
    
    def _scan_worker(self) -> None:
        """Worker thread for background expiration scanning."""
        while self.is_scanning:
            try:
                self.perform_expiration_scan()
                time.sleep(self.scan_interval_seconds)
            except Exception as e:
                logger.error(f"Error in expiration scan worker: {e}")
    
    def perform_expiration_scan(self) -> int:
        """
        Perform proactive expiration scanning.
        
        Returns:
            Number of keys expired in this scan
        """
        with self.lock:
            start_time = time.time()
            expired_count = 0
            keys_to_delete = []
            
            # Check heap for expired entries
            while self.expiration_heap and expired_count < self.max_keys_per_scan:
                exp_time, key = self.expiration_heap[0]
                
                if datetime.now() < exp_time:
                    # Not expired yet, stop checking
                    break
                
                heappop(self.expiration_heap)
                
                # Verify the entry actually exists and is expired
                if key in self.ttl_entries:
                    entry = self.ttl_entries[key]
                    if entry.is_expired():
                        keys_to_delete.append(key)
                        expired_count += 1
                        self.stats.expired_by_scan += 1
                        self._trigger_callback(key, ExpirationEvent.EXPIRED_BY_SCAN)
            
            # Delete expired keys
            for key in keys_to_delete:
                del self.ttl_entries[key]
                self.stats.total_expired += 1
            
            # Update statistics
            self.stats.total_scans += 1
            self.stats.total_expired_in_scans += expired_count
            scan_duration = (time.time() - start_time) * 1000  # Convert to ms
            self.stats.last_scan_duration_ms = scan_duration
            self.stats.last_scan_time = datetime.now()
            
            self._update_statistics()
            
            if expired_count > 0:
                logger.debug(f"Expiration scan: deleted {expired_count} keys in {scan_duration:.2f}ms")
            
            return expired_count
    
    def register_expiration_callback(
        self,
        callback: Callable[[str, ExpirationEvent], None]
    ) -> None:
        """
        Register a callback for expiration events.
        
        Args:
            callback: Function to call on expiration events
        """
        self.expiration_callbacks.append(callback)
    
    def _trigger_callback(self, key: str, event: ExpirationEvent) -> None:
        """Trigger all registered callbacks."""
        for callback in self.expiration_callbacks:
            try:
                callback(key, event)
            except Exception as e:
                logger.error(f"Error in expiration callback: {e}")
    
    def _update_statistics(self) -> None:
        """Update statistics from current state."""
        self.stats.current_ttl_entries = len(self.ttl_entries)
        
        if self.ttl_entries:
            ttls = [e.original_ttl_seconds for e in self.ttl_entries.values()]
            self.stats.average_ttl_seconds = sum(ttls) / len(ttls)
            self.stats.min_ttl_seconds = min(ttls)
            self.stats.max_ttl_seconds = max(ttls)
            
            # Count keys expiring soon
            now = datetime.now()
            minute_from_now = now + timedelta(minutes=1)
            hour_from_now = now + timedelta(hours=1)
            
            self.stats.keys_expiring_in_minute = sum(
                1 for e in self.ttl_entries.values()
                if now < e.expiration_time <= minute_from_now
            )
            
            self.stats.keys_expiring_in_hour = sum(
                1 for e in self.ttl_entries.values()
                if minute_from_now < e.expiration_time <= hour_from_now
            )
    
    def get_ttl_entry(self, key: str) -> Optional[dict]:
        """
        Get full TTL entry information.
        
        Args:
            key: Key to query
            
        Returns:
            Entry dictionary or None
        """
        with self.lock:
            if key not in self.ttl_entries:
                return None
            
            entry = self.ttl_entries[key]
            
            # Check if expired (lazy deletion)
            if entry.is_expired():
                del self.ttl_entries[key]
                self.stats.expired_on_access += 1
                self.stats.total_expired += 1
                return None
            
            return entry.to_dict()
    
    def get_keys_expiring_soon(self, within_seconds: float) -> List[str]:
        """
        Get keys expiring within a time window.
        
        Args:
            within_seconds: Time window in seconds
            
        Returns:
            List of key IDs
        """
        with self.lock:
            threshold = datetime.now() + timedelta(seconds=within_seconds)
            return [
                key for key, entry in self.ttl_entries.items()
                if entry.expiration_time <= threshold and not entry.is_expired()
            ]
    
    def get_expiration_statistics(self) -> dict:
        """
        Get expiration statistics.
        
        Returns:
            Statistics dictionary
        """
        with self.lock:
            self._update_statistics()
            return self.stats.to_dict()
    
    def clear_all_ttls(self) -> int:
        """
        Clear all TTL entries.
        
        Returns:
            Number of entries cleared
        """
        with self.lock:
            count = len(self.ttl_entries)
            self.ttl_entries.clear()
            self.expiration_heap.clear()
            self.stats.current_ttl_entries = 0
            return count
    
    def get_keys_by_ttl_range(
        self,
        min_ttl_seconds: float,
        max_ttl_seconds: float
    ) -> List[str]:
        """
        Get keys with TTL in a specific range.
        
        Args:
            min_ttl_seconds: Minimum TTL
            max_ttl_seconds: Maximum TTL
            
        Returns:
            List of key IDs
        """
        with self.lock:
            return [
                key for key, entry in self.ttl_entries.items()
                if min_ttl_seconds <= entry.time_to_expiration() <= max_ttl_seconds
            ]
    
    def extend_ttl(self, key: str, additional_seconds: float) -> bool:
        """
        Extend TTL for an existing key.
        
        Args:
            key: Key to extend
            additional_seconds: Seconds to add
            
        Returns:
            True if extended
        """
        with self.lock:
            if key not in self.ttl_entries:
                return False
            
            entry = self.ttl_entries[key]
            new_expiration = entry.expiration_time + timedelta(seconds=additional_seconds)
            entry.expiration_time = new_expiration
            entry.original_ttl_seconds += additional_seconds
            
            heappush(self.expiration_heap, (new_expiration, key))
            self._update_statistics()
            return True
    
    def get_most_accessed_expiring_keys(self, count: int = 10) -> List[dict]:
        """
        Get most frequently accessed expiring keys.
        
        Args:
            count: Number of keys to return
            
        Returns:
            List of key information sorted by access count
        """
        with self.lock:
            # Sort by access count, then by remaining TTL
            sorted_keys = sorted(
                self.ttl_entries.values(),
                key=lambda e: (-e.access_count, -e.time_to_expiration())
            )
            
            return [
                e.to_dict() for e in sorted_keys[:count]
                if not e.is_expired()
            ]
    
    def get_expiration_distribution(self, buckets: int = 10) -> dict:
        """
        Get distribution of expirations over time.
        
        Args:
            buckets: Number of time buckets
            
        Returns:
            Distribution data
        """
        with self.lock:
            if not self.ttl_entries:
                return {}
            
            now = datetime.now()
            max_remaining = max(
                (e.expiration_time - now).total_seconds()
                for e in self.ttl_entries.values()
            )
            
            if max_remaining <= 0:
                return {}
            
            bucket_size = max_remaining / buckets
            distribution = {i: 0 for i in range(buckets)}
            
            for entry in self.ttl_entries.values():
                remaining = (entry.expiration_time - now).total_seconds()
                if remaining > 0:
                    bucket = int(remaining / bucket_size)
                    bucket = min(bucket, buckets - 1)
                    distribution[bucket] += 1
            
            return {
                "buckets": buckets,
                "bucket_size_seconds": bucket_size,
                "distribution": distribution
            }
