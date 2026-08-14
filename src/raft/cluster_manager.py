"""
Advanced Cluster Management & Monitoring.

Implements dynamic cluster management:
- Node join/leave/restart scenarios
- Cluster health monitoring (real-time)
- Node status tracking and metrics
- Automatic quorum validation
- Cluster orchestration (start/stop/scale)
- Member discovery and failover coordination
"""

import logging
import time
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json

logger = logging.getLogger(__name__)


class NodeStatus(Enum):
    """Node health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    JOINING = "joining"
    LEAVING = "leaving"
    RESTARTING = "restarting"
    UNKNOWN = "unknown"


@dataclass
class NodeMetrics:
    """Metrics for a cluster node."""
    node_id: str
    status: NodeStatus = NodeStatus.UNKNOWN
    heartbeat_count: int = 0
    last_heartbeat: Optional[datetime] = None
    latency_ms: float = 0.0
    request_count: int = 0
    error_count: int = 0
    uptime_seconds: float = 0.0
    cpu_usage_percent: float = 0.0
    memory_usage_percent: float = 0.0
    log_replication_lag: int = 0
    snapshot_status: str = "none"
    
    def get_error_rate(self) -> float:
        """Calculate error rate."""
        if self.request_count == 0:
            return 0.0
        return (self.error_count / self.request_count) * 100
    
    def is_healthy(self) -> bool:
        """Check if node is healthy based on metrics."""
        if self.status == NodeStatus.HEALTHY:
            return True
        if self.status in [NodeStatus.UNHEALTHY, NodeStatus.UNKNOWN]:
            return False
        return False
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "node_id": self.node_id,
            "status": self.status.value,
            "heartbeat_count": self.heartbeat_count,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "latency_ms": self.latency_ms,
            "request_count": self.request_count,
            "error_count": self.error_count,
            "error_rate": self.get_error_rate(),
            "uptime_seconds": self.uptime_seconds,
            "cpu_usage_percent": self.cpu_usage_percent,
            "memory_usage_percent": self.memory_usage_percent,
            "log_replication_lag": self.log_replication_lag,
            "snapshot_status": self.snapshot_status
        }


@dataclass
class ClusterMetrics:
    """Cluster-wide metrics and health status."""
    total_nodes: int = 0
    healthy_nodes: int = 0
    unhealthy_nodes: int = 0
    current_leader: Optional[str] = None
    quorum_size: int = 0
    is_quorum_available: bool = False
    total_requests: int = 0
    total_errors: int = 0
    average_latency_ms: float = 0.0
    max_replication_lag: int = 0
    min_replication_lag: int = 0
    last_update: datetime = field(default_factory=datetime.now)
    
    def get_cluster_health(self) -> str:
        """Get overall cluster health status."""
        if not self.is_quorum_available:
            return "critical"
        if self.unhealthy_nodes > 0:
            return "degraded"
        return "healthy"
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "total_nodes": self.total_nodes,
            "healthy_nodes": self.healthy_nodes,
            "unhealthy_nodes": self.unhealthy_nodes,
            "current_leader": self.current_leader,
            "quorum_size": self.quorum_size,
            "is_quorum_available": self.is_quorum_available,
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "average_latency_ms": self.average_latency_ms,
            "max_replication_lag": self.max_replication_lag,
            "min_replication_lag": self.min_replication_lag,
            "cluster_health": self.get_cluster_health(),
            "last_update": self.last_update.isoformat()
        }


class ClusterManager:
    """Manages cluster state, health, and orchestration."""
    
    def __init__(self, node_id: str, nodes: List[str]):
        """
        Initialize cluster manager.
        
        Args:
            node_id: This node's ID
            nodes: Initial list of cluster node IDs
        """
        self.node_id = node_id
        self.nodes: Set[str] = set(nodes)
        self.metrics: Dict[str, NodeMetrics] = {}
        self.cluster_metrics = ClusterMetrics()
        self.current_leader: Optional[str] = None
        self.is_running = False
        self.join_queue: List[str] = []
        self.leave_queue: List[str] = []
        self.restart_queue: List[str] = []
        
        # Initialize metrics for all nodes
        for node in self.nodes:
            self.metrics[node] = NodeMetrics(node_id=node)
        
        self._update_quorum()
    
    def _update_quorum(self) -> None:
        """Update quorum calculations."""
        self.cluster_metrics.total_nodes = len(self.nodes)
        self.cluster_metrics.quorum_size = (len(self.nodes) // 2) + 1
    
    def start_cluster(self) -> bool:
        """
        Start the cluster.
        
        Returns:
            True if successfully started
        """
        try:
            self.is_running = True
            for node_id in self.nodes:
                self.metrics[node_id].status = NodeStatus.HEALTHY
                logger.info(f"Started node {node_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to start cluster: {e}")
            self.is_running = False
            return False
    
    def stop_cluster(self) -> bool:
        """
        Stop the cluster.
        
        Returns:
            True if successfully stopped
        """
        try:
            self.is_running = False
            for node_id in self.nodes:
                self.metrics[node_id].status = NodeStatus.UNKNOWN
                logger.info(f"Stopped node {node_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to stop cluster: {e}")
            return False
    
    def add_node(self, node_id: str) -> bool:
        """
        Add a new node to the cluster (join scenario).
        
        Args:
            node_id: New node ID
            
        Returns:
            True if successfully added
        """
        if node_id in self.nodes:
            logger.warning(f"Node {node_id} already in cluster")
            return False
        
        try:
            self.join_queue.append(node_id)
            self.nodes.add(node_id)
            self.metrics[node_id] = NodeMetrics(
                node_id=node_id,
                status=NodeStatus.JOINING
            )
            self._update_quorum()
            logger.info(f"Node {node_id} joined cluster")
            return True
        except Exception as e:
            logger.error(f"Failed to add node {node_id}: {e}")
            return False
    
    def remove_node(self, node_id: str) -> bool:
        """
        Remove a node from the cluster (leave scenario).
        
        Args:
            node_id: Node ID to remove
            
        Returns:
            True if successfully removed
        """
        if node_id not in self.nodes:
            logger.warning(f"Node {node_id} not in cluster")
            return False
        
        try:
            self.leave_queue.append(node_id)
            self.nodes.discard(node_id)
            if node_id in self.metrics:
                self.metrics[node_id].status = NodeStatus.LEAVING
            self._update_quorum()
            logger.info(f"Node {node_id} left cluster")
            return True
        except Exception as e:
            logger.error(f"Failed to remove node {node_id}: {e}")
            return False
    
    def restart_node(self, node_id: str) -> bool:
        """
        Restart a node (restart scenario).
        
        Args:
            node_id: Node ID to restart
            
        Returns:
            True if restart initiated
        """
        if node_id not in self.nodes:
            logger.warning(f"Node {node_id} not in cluster")
            return False
        
        try:
            self.restart_queue.append(node_id)
            if node_id in self.metrics:
                self.metrics[node_id].status = NodeStatus.RESTARTING
            logger.info(f"Restarting node {node_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to restart node {node_id}: {e}")
            return False
    
    def update_node_heartbeat(self, node_id: str, latency_ms: float = 0.0) -> bool:
        """
        Update heartbeat for a node.
        
        Args:
            node_id: Node ID
            latency_ms: Heartbeat latency in milliseconds
            
        Returns:
            True if updated
        """
        if node_id not in self.metrics:
            return False
        
        metrics = self.metrics[node_id]
        metrics.heartbeat_count += 1
        metrics.last_heartbeat = datetime.now()
        metrics.latency_ms = latency_ms
        metrics.status = NodeStatus.HEALTHY
        return True
    
    def update_node_metrics(
        self,
        node_id: str,
        request_count: int = 0,
        error_count: int = 0,
        cpu_usage: float = 0.0,
        memory_usage: float = 0.0,
        replication_lag: int = 0
    ) -> bool:
        """
        Update comprehensive node metrics.
        
        Args:
            node_id: Node ID
            request_count: Total requests handled
            error_count: Number of errors
            cpu_usage: CPU usage percentage
            memory_usage: Memory usage percentage
            replication_lag: Log replication lag
            
        Returns:
            True if updated
        """
        if node_id not in self.metrics:
            return False
        
        metrics = self.metrics[node_id]
        metrics.request_count = request_count
        metrics.error_count = error_count
        metrics.cpu_usage_percent = cpu_usage
        metrics.memory_usage_percent = memory_usage
        metrics.log_replication_lag = replication_lag
        
        # Update status based on metrics
        error_rate = metrics.get_error_rate()
        if error_rate > 50 or cpu_usage > 90 or memory_usage > 90:
            metrics.status = NodeStatus.UNHEALTHY
        elif error_rate > 10 or cpu_usage > 70 or memory_usage > 70:
            metrics.status = NodeStatus.DEGRADED
        else:
            if metrics.status not in [NodeStatus.JOINING, NodeStatus.LEAVING]:
                metrics.status = NodeStatus.HEALTHY
        
        return True
    
    def set_leader(self, leader_id: str) -> bool:
        """
        Set the current leader.
        
        Args:
            leader_id: Leader node ID
            
        Returns:
            True if set
        """
        if leader_id not in self.nodes:
            logger.warning(f"Leader {leader_id} not in cluster")
            return False
        
        self.current_leader = leader_id
        self.cluster_metrics.current_leader = leader_id
        logger.info(f"Leader set to {leader_id}")
        return True
    
    def is_quorum_available(self) -> bool:
        """
        Check if quorum is available.
        
        Returns:
            True if sufficient healthy nodes for quorum
        """
        healthy_count = sum(
            1 for node in self.nodes
            if node in self.metrics and self.metrics[node].status == NodeStatus.HEALTHY
        )
        is_available = healthy_count >= self.cluster_metrics.quorum_size
        self.cluster_metrics.is_quorum_available = is_available
        return is_available
    
    def get_healthy_nodes(self) -> List[str]:
        """
        Get list of healthy nodes.
        
        Returns:
            List of healthy node IDs
        """
        return [
            node for node in self.nodes
            if node in self.metrics and self.metrics[node].status == NodeStatus.HEALTHY
        ]
    
    def get_unhealthy_nodes(self) -> List[str]:
        """
        Get list of unhealthy nodes.
        
        Returns:
            List of unhealthy node IDs
        """
        return [
            node for node in self.nodes
            if node in self.metrics and self.metrics[node].status in [
                NodeStatus.UNHEALTHY, NodeStatus.UNKNOWN
            ]
        ]
    
    def get_node_metrics(self, node_id: str) -> Optional[dict]:
        """
        Get metrics for a specific node.
        
        Args:
            node_id: Node ID
            
        Returns:
            Node metrics dictionary or None
        """
        if node_id not in self.metrics:
            return None
        return self.metrics[node_id].to_dict()
    
    def update_cluster_metrics(self) -> ClusterMetrics:
        """
        Update and return cluster-wide metrics.
        
        Returns:
            Updated ClusterMetrics
        """
        healthy_nodes = self.get_healthy_nodes()
        unhealthy_nodes = self.get_unhealthy_nodes()
        
        self.cluster_metrics.healthy_nodes = len(healthy_nodes)
        self.cluster_metrics.unhealthy_nodes = len(unhealthy_nodes)
        self.cluster_metrics.is_quorum_available = self.is_quorum_available()
        
        # Calculate average latency
        latencies = [
            self.metrics[node].latency_ms for node in healthy_nodes
            if self.metrics[node].latency_ms > 0
        ]
        if latencies:
            self.cluster_metrics.average_latency_ms = sum(latencies) / len(latencies)
        
        # Calculate replication lag statistics
        lags = [
            self.metrics[node].log_replication_lag for node in self.nodes
            if node in self.metrics
        ]
        if lags:
            self.cluster_metrics.max_replication_lag = max(lags)
            self.cluster_metrics.min_replication_lag = min(lags)
        
        # Calculate total requests and errors
        total_requests = sum(self.metrics[node].request_count for node in self.nodes)
        total_errors = sum(self.metrics[node].error_count for node in self.nodes)
        
        self.cluster_metrics.total_requests = total_requests
        self.cluster_metrics.total_errors = total_errors
        self.cluster_metrics.last_update = datetime.now()
        
        return self.cluster_metrics
    
    def get_cluster_status(self) -> dict:
        """
        Get comprehensive cluster status.
        
        Returns:
            Cluster status dictionary
        """
        self.update_cluster_metrics()
        return {
            "cluster_metrics": self.cluster_metrics.to_dict(),
            "nodes": {node: self.get_node_metrics(node) for node in self.nodes},
            "healthy_nodes": self.get_healthy_nodes(),
            "unhealthy_nodes": self.get_unhealthy_nodes(),
            "join_queue": self.join_queue,
            "leave_queue": self.leave_queue,
            "restart_queue": self.restart_queue
        }
    
    def get_slowest_nodes(self, count: int = 3) -> List[Tuple[str, float]]:
        """
        Get slowest nodes by latency.
        
        Args:
            count: Number of slowest nodes to return
            
        Returns:
            List of (node_id, latency_ms) tuples
        """
        nodes_by_latency = sorted(
            [(node, self.metrics[node].latency_ms) for node in self.nodes],
            key=lambda x: x[1],
            reverse=True
        )
        return nodes_by_latency[:count]
    
    def scale_cluster(self, target_size: int) -> bool:
        """
        Scale cluster to target size.
        
        Args:
            target_size: Target number of nodes
            
        Returns:
            True if scaling initiated
        """
        current_size = len(self.nodes)
        
        if target_size > current_size:
            # Scale up
            for i in range(target_size - current_size):
                new_node_id = f"node-{current_size + i}"
                self.add_node(new_node_id)
        elif target_size < current_size:
            # Scale down
            nodes_list = list(self.nodes)
            for i in range(current_size - target_size):
                self.remove_node(nodes_list[-(i + 1)])
        
        logger.info(f"Cluster scaled to {target_size} nodes")
        return True
    
    def get_member_list(self) -> List[str]:
        """
        Get current cluster membership.
        
        Returns:
            List of node IDs
        """
        return sorted(list(self.nodes))
    
    def validate_cluster_integrity(self) -> Tuple[bool, List[str]]:
        """
        Validate cluster integrity and consistency.
        
        Returns:
            Tuple of (is_valid, issues_list)
        """
        issues = []
        
        # Check quorum
        if not self.is_quorum_available():
            issues.append("Quorum not available")
        
        # Check leader
        if self.current_leader and self.current_leader not in self.nodes:
            issues.append(f"Leader {self.current_leader} not in cluster")
        
        # Check metrics consistency
        for node_id in self.nodes:
            if node_id not in self.metrics:
                issues.append(f"No metrics for node {node_id}")
        
        return len(issues) == 0, issues
