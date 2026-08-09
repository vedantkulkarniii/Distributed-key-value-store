"""Replication Progress Reporting and Metrics Collection.

This module tracks and reports metrics on log replication progress,
including latency, throughput, and replication state across the cluster.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import time


@dataclass
class ReplicationLatency:
    """Latency metrics for a replication operation."""
    
    start_time: datetime
    """When the replication started."""
    
    end_time: Optional[datetime] = None
    """When the replication completed."""
    
    entries_sent: int = 0
    """Number of entries sent."""
    
    bytes_sent: int = 0
    """Number of bytes sent."""
    
    latency_ms: float = 0.0
    """Latency in milliseconds."""
    
    successful: bool = False
    """Whether the replication was successful."""


@dataclass
class ReplicationMetrics:
    """Comprehensive metrics for replication state."""
    
    follower_id: str
    """The follower being replicated to."""
    
    total_replications: int = 0
    """Total number of replication attempts."""
    
    successful_replications: int = 0
    """Number of successful replications."""
    
    failed_replications: int = 0
    """Number of failed replications."""
    
    entries_replicated: int = 0
    """Total entries successfully replicated."""
    
    bytes_replicated: int = 0
    """Total bytes successfully replicated."""
    
    avg_latency_ms: float = 0.0
    """Average latency in milliseconds."""
    
    min_latency_ms: float = float('inf')
    """Minimum latency in milliseconds."""
    
    max_latency_ms: float = 0.0
    """Maximum latency in milliseconds."""
    
    last_replication_time: Optional[datetime] = None
    """When the last replication occurred."""
    
    last_successful_index: int = 0
    """Index of the last successfully replicated entry."""
    
    replication_rate_entries_per_sec: float = 0.0
    """Replication rate in entries per second."""
    
    replication_rate_bytes_per_sec: float = 0.0
    """Replication rate in bytes per second."""
    
    latency_samples: List[float] = field(default_factory=list)
    """Recent latency samples for moving average."""


class ReplicationMetricsCollector:
    """Collects and reports replication metrics across the cluster.
    
    Tracks:
    - Per-follower replication latency
    - Aggregate throughput metrics
    - Success/failure rates
    - Replication progress
    """
    
    def __init__(self, max_samples: int = 100):
        """Initialize the metrics collector.
        
        Args:
            max_samples: Maximum number of latency samples to keep per follower.
        """
        self.max_samples = max_samples
        self.metrics: Dict[str, ReplicationMetrics] = {}
        """Metrics indexed by follower_id."""
        
        self.active_replications: Dict[str, ReplicationLatency] = {}
        """Currently active replication operations."""
        
        self.collection_start_time = datetime.now()
        """When metrics collection started."""
    
    def start_replication(
        self,
        follower_id: str,
        entries_count: int,
        bytes_count: int,
    ) -> str:
        """Start tracking a replication operation.
        
        Args:
            follower_id: The target follower.
            entries_count: Number of entries being sent.
            bytes_count: Number of bytes being sent.
        
        Returns:
            A replication ID for tracking.
        """
        replication_id = f"{follower_id}_{int(time.time() * 1000)}"
        
        latency = ReplicationLatency(
            start_time=datetime.now(),
            entries_sent=entries_count,
            bytes_sent=bytes_count,
        )
        
        self.active_replications[replication_id] = latency
        
        # Ensure metrics exist for this follower
        if follower_id not in self.metrics:
            self.metrics[follower_id] = ReplicationMetrics(follower_id=follower_id)
        
        return replication_id
    
    def complete_replication(
        self,
        replication_id: str,
        successful: bool,
        last_index: Optional[int] = None,
    ) -> None:
        """Complete a replication operation.
        
        Args:
            replication_id: The replication ID from start_replication.
            successful: Whether the replication was successful.
            last_index: The index of the last replicated entry.
        """
        if replication_id not in self.active_replications:
            return
        
        latency = self.active_replications[replication_id]
        latency.end_time = datetime.now()
        latency.successful = successful
        
        # Calculate latency
        time_delta = latency.end_time - latency.start_time
        latency.latency_ms = time_delta.total_seconds() * 1000
        
        # Extract follower_id from replication_id
        follower_id = replication_id.split("_")[0]
        
        # Update metrics
        metrics = self.metrics.get(follower_id)
        if metrics:
            metrics.total_replications += 1
            metrics.last_replication_time = datetime.now()
            
            if successful:
                metrics.successful_replications += 1
                metrics.entries_replicated += latency.entries_sent
                metrics.bytes_replicated += latency.bytes_sent
                
                if last_index is not None:
                    metrics.last_successful_index = last_index
                
                # Update latency statistics
                metrics.latency_samples.append(latency.latency_ms)
                if len(metrics.latency_samples) > self.max_samples:
                    metrics.latency_samples.pop(0)
                
                metrics.avg_latency_ms = sum(metrics.latency_samples) / len(
                    metrics.latency_samples
                )
                metrics.min_latency_ms = min(
                    metrics.min_latency_ms, latency.latency_ms
                )
                metrics.max_latency_ms = max(
                    metrics.max_latency_ms, latency.latency_ms
                )
            else:
                metrics.failed_replications += 1
        
        # Clean up
        del self.active_replications[replication_id]
    
    def get_metrics(self, follower_id: str) -> Optional[ReplicationMetrics]:
        """Get metrics for a specific follower.
        
        Args:
            follower_id: The follower ID.
        
        Returns:
            ReplicationMetrics or None if not found.
        """
        return self.metrics.get(follower_id)
    
    def get_all_metrics(self) -> Dict[str, ReplicationMetrics]:
        """Get metrics for all followers.
        
        Returns:
            Dictionary of all metrics.
        """
        return self.metrics.copy()
    
    def get_success_rate(self, follower_id: str) -> float:
        """Get success rate for a follower.
        
        Args:
            follower_id: The follower ID.
        
        Returns:
            Success rate as a percentage (0-100).
        """
        metrics = self.metrics.get(follower_id)
        if not metrics or metrics.total_replications == 0:
            return 0.0
        
        return (metrics.successful_replications / metrics.total_replications) * 100
    
    def get_throughput(self, follower_id: str) -> Dict[str, float]:
        """Get throughput metrics for a follower.
        
        Args:
            follower_id: The follower ID.
        
        Returns:
            Dictionary with entries_per_sec and bytes_per_sec.
        """
        metrics = self.metrics.get(follower_id)
        if not metrics or not metrics.last_replication_time:
            return {"entries_per_sec": 0.0, "bytes_per_sec": 0.0}
        
        time_elapsed = (datetime.now() - self.collection_start_time).total_seconds()
        if time_elapsed == 0:
            time_elapsed = 1.0
        
        entries_per_sec = metrics.entries_replicated / time_elapsed
        bytes_per_sec = metrics.bytes_replicated / time_elapsed
        
        return {
            "entries_per_sec": entries_per_sec,
            "bytes_per_sec": bytes_per_sec,
        }
    
    def get_cluster_summary(self) -> Dict[str, Any]:
        """Get a summary of replication metrics across the cluster.
        
        Returns:
            Dictionary with cluster-wide metrics.
        """
        total_replications = sum(m.total_replications for m in self.metrics.values())
        total_successful = sum(
            m.successful_replications for m in self.metrics.values()
        )
        total_failed = sum(m.failed_replications for m in self.metrics.values())
        total_entries = sum(m.entries_replicated for m in self.metrics.values())
        total_bytes = sum(m.bytes_replicated for m in self.metrics.values())
        
        avg_latencies = [
            m.avg_latency_ms for m in self.metrics.values() if m.avg_latency_ms > 0
        ]
        avg_latency = sum(avg_latencies) / len(avg_latencies) if avg_latencies else 0
        
        return {
            "total_followers": len(self.metrics),
            "total_replications": total_replications,
            "total_successful": total_successful,
            "total_failed": total_failed,
            "overall_success_rate": (
                (total_successful / total_replications * 100)
                if total_replications > 0
                else 0.0
            ),
            "total_entries_replicated": total_entries,
            "total_bytes_replicated": total_bytes,
            "average_latency_ms": avg_latency,
            "active_replications": len(self.active_replications),
        }
    
    def get_lagging_followers(self, lag_threshold: int = 10) -> List[str]:
        """Get list of followers lagging behind the leader.
        
        Args:
            lag_threshold: Minimum lag to be considered lagging.
        
        Returns:
            List of lagging follower IDs.
        """
        # This would typically compare against leader's last_index
        # For now, return followers with low last_successful_index
        lagging = []
        for fid, metrics in self.metrics.items():
            if metrics.last_successful_index < lag_threshold:
                lagging.append(fid)
        
        return lagging
    
    def get_fastest_followers(self) -> List[str]:
        """Get followers with lowest average replication latency.
        
        Returns:
            List of follower IDs sorted by latency (fastest first).
        """
        followers_by_latency = sorted(
            self.metrics.items(),
            key=lambda x: x[1].avg_latency_ms if x[1].avg_latency_ms > 0 else float('inf'),
        )
        
        return [fid for fid, _ in followers_by_latency]
    
    def get_slowest_followers(self) -> List[str]:
        """Get followers with highest average replication latency.
        
        Returns:
            List of follower IDs sorted by latency (slowest first).
        """
        followers_by_latency = sorted(
            self.metrics.items(),
            key=lambda x: x[1].avg_latency_ms if x[1].avg_latency_ms > 0 else float('inf'),
            reverse=True,
        )
        
        return [fid for fid, _ in followers_by_latency]
    
    def reset_metrics(self, follower_id: Optional[str] = None) -> None:
        """Reset metrics for a follower or all followers.
        
        Args:
            follower_id: The follower to reset, or None for all followers.
        """
        if follower_id:
            if follower_id in self.metrics:
                del self.metrics[follower_id]
        else:
            self.metrics.clear()
            self.active_replications.clear()
            self.collection_start_time = datetime.now()
    
    def export_metrics_json(self) -> Dict[str, Any]:
        """Export metrics in JSON-serializable format.
        
        Returns:
            Dictionary with JSON-serializable metrics.
        """
        exported = {}
        
        for fid, metrics in self.metrics.items():
            exported[fid] = {
                "follower_id": metrics.follower_id,
                "total_replications": metrics.total_replications,
                "successful_replications": metrics.successful_replications,
                "failed_replications": metrics.failed_replications,
                "entries_replicated": metrics.entries_replicated,
                "bytes_replicated": metrics.bytes_replicated,
                "avg_latency_ms": metrics.avg_latency_ms,
                "min_latency_ms": metrics.min_latency_ms,
                "max_latency_ms": metrics.max_latency_ms,
                "last_successful_index": metrics.last_successful_index,
                "success_rate": self.get_success_rate(fid),
                "throughput": self.get_throughput(fid),
            }
        
        return {
            "cluster_summary": self.get_cluster_summary(),
            "follower_metrics": exported,
            "collection_duration_seconds": (
                datetime.now() - self.collection_start_time
            ).total_seconds(),
        }
