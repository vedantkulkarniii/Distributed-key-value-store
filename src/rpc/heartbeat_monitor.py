"""
Heartbeat monitoring and logging for cluster health tracking.

Tracks incoming heartbeats from leaders and provides cluster health metrics.
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field


logger = logging.getLogger(__name__)


@dataclass
class HeartbeatRecord:
    """Record of a received heartbeat."""
    timestamp: datetime
    source_node_id: str
    term: int
    commit_index: int
    is_valid: bool
    error: Optional[str] = None
    
    @property
    def age_seconds(self) -> float:
        """Get age of heartbeat in seconds."""
        return (datetime.now() - self.timestamp).total_seconds()


@dataclass
class NodeHealthMetrics:
    """Health metrics for a single peer node."""
    node_id: str
    last_heartbeat: Optional[HeartbeatRecord] = None
    heartbeat_count: int = 0
    error_count: int = 0
    last_error: Optional[str] = None
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    
    @property
    def uptime_seconds(self) -> float:
        """Get uptime in seconds."""
        return (datetime.now() - self.first_seen).total_seconds()
    
    @property
    def is_healthy(self) -> bool:
        """Check if node appears healthy."""
        if not self.last_heartbeat:
            return False
        
        # Node is healthy if heartbeat received within last 1 second
        return self.last_heartbeat.age_seconds < 1.0
    
    @property
    def error_rate(self) -> float:
        """Get error rate (0.0 - 1.0)."""
        total = self.heartbeat_count + self.error_count
        if total == 0:
            return 0.0
        return self.error_count / total
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "node_id": self.node_id,
            "healthy": self.is_healthy,
            "heartbeat_count": self.heartbeat_count,
            "error_count": self.error_count,
            "error_rate": f"{self.error_rate:.2%}",
            "uptime_seconds": f"{self.uptime_seconds:.1f}",
            "last_heartbeat_age": (
                f"{self.last_heartbeat.age_seconds:.2f}s"
                if self.last_heartbeat else "never"
            ),
            "last_error": self.last_error
        }


class HeartbeatMonitor:
    """
    Monitors incoming heartbeats and provides cluster health metrics.
    
    Tracks:
    - Heartbeat frequency from each peer
    - Valid vs invalid heartbeats
    - Errors and issues
    - Cluster health status
    """
    
    def __init__(self, local_node_id: str, peer_ids: List[str] = None):
        """
        Initialize heartbeat monitor.
        
        Args:
            local_node_id: ID of local node
            peer_ids: List of peer node IDs (optional)
        """
        self.local_node_id = local_node_id
        
        # Health metrics per peer
        self.peer_metrics: Dict[str, NodeHealthMetrics] = {}
        
        # Track leader
        self.current_leader: Optional[str] = None
        self.last_leader_change: datetime = datetime.now()
        
        # Heartbeat history (keep last N)
        self.heartbeat_history: List[HeartbeatRecord] = []
        self.max_history_size = 100
        
        # Initialize metrics for known peers
        if peer_ids:
            for peer_id in peer_ids:
                self.peer_metrics[peer_id] = NodeHealthMetrics(peer_id)
    
    def record_heartbeat(self, source_node_id: str, term: int, 
                        commit_index: int, is_valid: bool = True,
                        error: Optional[str] = None) -> None:
        """
        Record receipt of a heartbeat.
        
        Args:
            source_node_id: ID of node sending heartbeat
            term: Term in heartbeat
            commit_index: Commit index in heartbeat
            is_valid: Whether heartbeat was valid/accepted
            error: Error message if not valid
        """
        # Create record
        record = HeartbeatRecord(
            timestamp=datetime.now(),
            source_node_id=source_node_id,
            term=term,
            commit_index=commit_index,
            is_valid=is_valid,
            error=error
        )
        
        # Update or create peer metrics
        if source_node_id not in self.peer_metrics:
            self.peer_metrics[source_node_id] = NodeHealthMetrics(source_node_id)
        
        metrics = self.peer_metrics[source_node_id]
        
        if is_valid:
            metrics.heartbeat_count += 1
            metrics.last_heartbeat = record
            logger.debug(
                f"Node {self.local_node_id}: Received valid heartbeat from "
                f"{source_node_id} (term={term}, count={metrics.heartbeat_count})"
            )
        else:
            metrics.error_count += 1
            metrics.last_error = error
            logger.warning(
                f"Node {self.local_node_id}: Received invalid heartbeat from "
                f"{source_node_id}: {error}"
            )
        
        metrics.last_seen = datetime.now()
        
        # Track current leader
        if is_valid and source_node_id != self.current_leader:
            old_leader = self.current_leader
            self.current_leader = source_node_id
            self.last_leader_change = datetime.now()
            
            if old_leader:
                logger.info(
                    f"Node {self.local_node_id}: Leader changed from "
                    f"{old_leader} to {source_node_id}"
                )
            else:
                logger.info(
                    f"Node {self.local_node_id}: Identified leader: {source_node_id}"
                )
        
        # Add to history
        self.heartbeat_history.append(record)
        if len(self.heartbeat_history) > self.max_history_size:
            self.heartbeat_history.pop(0)
    
    def get_peer_status(self, node_id: str) -> Optional[Dict]:
        """
        Get health status of a peer.
        
        Args:
            node_id: ID of peer
            
        Returns:
            Dict with peer metrics or None if peer not tracked
        """
        if node_id not in self.peer_metrics:
            return None
        
        return self.peer_metrics[node_id].to_dict()
    
    def get_cluster_status(self) -> Dict:
        """
        Get overall cluster health status.
        
        Returns:
            Dict with cluster metrics
        """
        total_peers = len(self.peer_metrics)
        healthy_peers = sum(
            1 for m in self.peer_metrics.values() if m.is_healthy
        )
        
        return {
            "local_node_id": self.local_node_id,
            "current_leader": self.current_leader,
            "leader_stable": (
                (datetime.now() - self.last_leader_change).total_seconds() > 1.0
                if self.current_leader else False
            ),
            "total_peers": total_peers,
            "healthy_peers": healthy_peers,
            "unhealthy_peers": total_peers - healthy_peers,
            "cluster_health_percent": (
                (healthy_peers / total_peers * 100) if total_peers > 0 else 0
            ),
            "total_heartbeats": sum(m.heartbeat_count for m in self.peer_metrics.values()),
            "total_errors": sum(m.error_count for m in self.peer_metrics.values())
        }
    
    def get_all_peer_status(self) -> List[Dict]:
        """
        Get status of all tracked peers.
        
        Returns:
            List of peer status dicts
        """
        return [
            metrics.to_dict()
            for metrics in sorted(
                self.peer_metrics.values(),
                key=lambda m: m.node_id
            )
        ]
    
    def get_recent_heartbeats(self, limit: int = 20) -> List[Dict]:
        """
        Get recent heartbeat records.
        
        Args:
            limit: Maximum number of records to return
            
        Returns:
            List of recent heartbeat records
        """
        recent = self.heartbeat_history[-limit:]
        return [
            {
                "timestamp": hb.timestamp.isoformat(),
                "source": hb.source_node_id,
                "term": hb.term,
                "commit_index": hb.commit_index,
                "valid": hb.is_valid,
                "error": hb.error
            }
            for hb in reversed(recent)
        ]
    
    def log_cluster_summary(self) -> None:
        """Log a summary of cluster health."""
        status = self.get_cluster_status()
        logger.info(
            f"Node {self.local_node_id} cluster status: "
            f"leader={status['current_leader']}, "
            f"peers={status['healthy_peers']}/{status['total_peers']} healthy, "
            f"heartbeats={status['total_heartbeats']}, "
            f"errors={status['total_errors']}"
        )


class HeartbeatLogger:
    """
    Detailed logger for heartbeat activity.
    
    Logs all heartbeat-related events to file for debugging and analysis.
    """
    
    def __init__(self, node_id: str, log_file: Optional[str] = None):
        """
        Initialize heartbeat logger.
        
        Args:
            node_id: Node ID
            log_file: Optional file path for logging (None = console only)
        """
        self.node_id = node_id
        self.monitor = HeartbeatMonitor(node_id)
        
        # Create dedicated logger if file specified
        if log_file:
            self.file_logger = logging.getLogger(f"heartbeat.{node_id}")
            handler = logging.FileHandler(log_file)
            handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s'
            ))
            self.file_logger.addHandler(handler)
        else:
            self.file_logger = None
    
    def log_heartbeat(self, record: HeartbeatRecord) -> None:
        """Log a heartbeat record."""
        msg = (
            f"Heartbeat from {record.source_node_id}: "
            f"term={record.term}, commit={record.commit_index}, "
            f"valid={record.is_valid}"
        )
        
        if record.error:
            msg += f", error={record.error}"
        
        if self.file_logger:
            self.file_logger.info(msg)
        else:
            logger.debug(msg)
    
    def log_summary(self) -> None:
        """Log cluster summary."""
        self.monitor.log_cluster_summary()
