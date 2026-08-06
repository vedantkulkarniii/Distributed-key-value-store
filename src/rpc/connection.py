"""
Connection management utilities for RPC clients and servers.

Handles connection pooling, lifecycle management, and health monitoring.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta


logger = logging.getLogger(__name__)


class ConnectionPool:
    """
    Manages a pool of connections.
    
    Features:
    - Connection pooling and reuse
    - Health monitoring
    - Automatic cleanup of dead connections
    - Connection lifecycle tracking
    """
    
    def __init__(self, pool_name: str = "default"):
        """
        Initialize connection pool.
        
        Args:
            pool_name: Name for this pool (for logging)
        """
        self.pool_name = pool_name
        
        # Connection tracking
        self._connections: Dict[str, asyncio.StreamWriter] = {}
        self._readers: Dict[str, asyncio.StreamReader] = {}
        self._lock = asyncio.Lock()
        
        # Health tracking
        self._created_at: Dict[str, datetime] = {}
        self._last_used: Dict[str, datetime] = {}
        self._use_count: Dict[str, int] = {}
        
        # Pool configuration
        self.max_idle_time = timedelta(minutes=5)
        self.cleanup_interval = timedelta(seconds=60)
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def add_connection(self, conn_id: str, reader: asyncio.StreamReader,
                           writer: asyncio.StreamWriter) -> None:
        """
        Add a connection to the pool.
        
        Args:
            conn_id: Unique connection identifier
            reader: StreamReader for the connection
            writer: StreamWriter for the connection
        """
        async with self._lock:
            self._connections[conn_id] = writer
            self._readers[conn_id] = reader
            self._created_at[conn_id] = datetime.now()
            self._last_used[conn_id] = datetime.now()
            self._use_count[conn_id] = 0
            
            logger.debug(f"Connection pool {self.pool_name}: Added connection {conn_id}")
    
    async def get_connection(self, conn_id: str) -> tuple[Optional[asyncio.StreamReader],
                                                          Optional[asyncio.StreamWriter]]:
        """
        Get a connection from the pool.
        
        Args:
            conn_id: Unique connection identifier
            
        Returns:
            Tuple of (reader, writer) or (None, None) if not found
        """
        async with self._lock:
            if conn_id not in self._connections:
                return None, None
            
            # Check if connection is still valid
            writer = self._connections[conn_id]
            if writer.is_closing():
                logger.debug(
                    f"Connection pool {self.pool_name}: Connection {conn_id} closed"
                )
                await self._remove_connection_locked(conn_id)
                return None, None
            
            # Update usage stats
            self._last_used[conn_id] = datetime.now()
            self._use_count[conn_id] = self._use_count.get(conn_id, 0) + 1
            
            return self._readers[conn_id], writer
    
    async def remove_connection(self, conn_id: str) -> None:
        """
        Remove a connection from the pool.
        
        Args:
            conn_id: Connection identifier
        """
        async with self._lock:
            await self._remove_connection_locked(conn_id)
    
    async def _remove_connection_locked(self, conn_id: str) -> None:
        """
        Remove connection (caller must hold lock).
        
        Args:
            conn_id: Connection identifier
        """
        if conn_id not in self._connections:
            return
        
        writer = self._connections.pop(conn_id)
        self._readers.pop(conn_id, None)
        
        try:
            writer.close()
            await writer.wait_closed()
        except Exception as e:
            logger.debug(f"Error closing connection {conn_id}: {e}")
        
        # Clean up tracking
        self._created_at.pop(conn_id, None)
        self._last_used.pop(conn_id, None)
        self._use_count.pop(conn_id, None)
        
        logger.debug(f"Connection pool {self.pool_name}: Removed connection {conn_id}")
    
    async def cleanup_idle(self) -> int:
        """
        Remove idle connections that haven't been used recently.
        
        Returns:
            Number of connections removed
        """
        async with self._lock:
            current_time = datetime.now()
            to_remove = []
            
            for conn_id, last_used in self._last_used.items():
                if current_time - last_used > self.max_idle_time:
                    to_remove.append(conn_id)
            
            for conn_id in to_remove:
                await self._remove_connection_locked(conn_id)
            
            if to_remove:
                logger.info(
                    f"Connection pool {self.pool_name}: Cleaned up "
                    f"{len(to_remove)} idle connections"
                )
            
            return len(to_remove)
    
    async def start_cleanup_task(self) -> None:
        """Start periodic cleanup of idle connections."""
        if self._cleanup_task:
            return
        
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
    
    async def _cleanup_loop(self) -> None:
        """Periodic cleanup loop."""
        try:
            while True:
                await asyncio.sleep(self.cleanup_interval.total_seconds())
                await self.cleanup_idle()
        except asyncio.CancelledError:
            logger.debug(f"Connection pool {self.pool_name}: Cleanup task cancelled")
        except Exception as e:
            logger.error(f"Connection pool {self.pool_name}: Cleanup error: {e}")
    
    async def stop_cleanup_task(self) -> None:
        """Stop the cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
    
    async def close_all(self) -> None:
        """Close all connections in the pool."""
        async with self._lock:
            conn_ids = list(self._connections.keys())
            for conn_id in conn_ids:
                await self._remove_connection_locked(conn_id)
        
        await self.stop_cleanup_task()
        logger.info(f"Connection pool {self.pool_name}: Closed all connections")
    
    async def get_stats(self) -> Dict:
        """
        Get pool statistics.
        
        Returns:
            Dict with pool stats
        """
        async with self._lock:
            return {
                "pool_name": self.pool_name,
                "total_connections": len(self._connections),
                "total_uses": sum(self._use_count.values()),
                "oldest_connection_age": (
                    min(
                        (datetime.now() - dt).total_seconds()
                        for dt in self._created_at.values()
                    )
                    if self._created_at else 0
                ),
                "average_uses_per_connection": (
                    sum(self._use_count.values()) / len(self._connections)
                    if self._connections else 0
                )
            }


class ConnectionMonitor:
    """
    Monitors connection health and statistics.
    
    Tracks:
    - Connection success/failure rates
    - Connection latency
    - Connection errors
    """
    
    def __init__(self, node_id: str):
        """
        Initialize connection monitor.
        
        Args:
            node_id: Local node ID
        """
        self.node_id = node_id
        
        # Statistics per peer
        self._stats: Dict[str, dict] = {}
        self._lock = asyncio.Lock()
    
    async def record_success(self, peer_id: str, latency_ms: float) -> None:
        """
        Record successful connection.
        
        Args:
            peer_id: Peer node ID
            latency_ms: Connection latency in milliseconds
        """
        async with self._lock:
            if peer_id not in self._stats:
                self._stats[peer_id] = {
                    "successes": 0,
                    "failures": 0,
                    "total_latency_ms": 0,
                    "min_latency_ms": float('inf'),
                    "max_latency_ms": 0
                }
            
            stats = self._stats[peer_id]
            stats["successes"] += 1
            stats["total_latency_ms"] += latency_ms
            stats["min_latency_ms"] = min(stats["min_latency_ms"], latency_ms)
            stats["max_latency_ms"] = max(stats["max_latency_ms"], latency_ms)
    
    async def record_failure(self, peer_id: str, error: str) -> None:
        """
        Record failed connection attempt.
        
        Args:
            peer_id: Peer node ID
            error: Error message
        """
        async with self._lock:
            if peer_id not in self._stats:
                self._stats[peer_id] = {
                    "successes": 0,
                    "failures": 0,
                    "last_error": None
                }
            
            stats = self._stats[peer_id]
            stats["failures"] += 1
            stats["last_error"] = error
    
    async def get_stats(self, peer_id: str) -> Optional[Dict]:
        """
        Get connection statistics for a peer.
        
        Args:
            peer_id: Peer node ID
            
        Returns:
            Stats dict or None if no stats available
        """
        async with self._lock:
            if peer_id not in self._stats:
                return None
            
            stats = self._stats[peer_id].copy()
            
            # Calculate averages
            if stats["successes"] > 0:
                stats["avg_latency_ms"] = (
                    stats["total_latency_ms"] / stats["successes"]
                )
            else:
                stats["avg_latency_ms"] = None
            
            total = stats["successes"] + stats["failures"]
            if total > 0:
                stats["success_rate"] = stats["successes"] / total
            else:
                stats["success_rate"] = 0
            
            return stats
    
    async def get_all_stats(self) -> Dict[str, Dict]:
        """Get statistics for all peers."""
        async with self._lock:
            result = {}
            for peer_id in self._stats:
                stats = self._stats[peer_id].copy()
                
                if "total_latency_ms" in stats and stats["successes"] > 0:
                    stats["avg_latency_ms"] = (
                        stats["total_latency_ms"] / stats["successes"]
                    )
                
                total = stats.get("successes", 0) + stats.get("failures", 0)
                if total > 0:
                    stats["success_rate"] = stats.get("successes", 0) / total
                else:
                    stats["success_rate"] = 0
                
                result[peer_id] = stats
            
            return result
