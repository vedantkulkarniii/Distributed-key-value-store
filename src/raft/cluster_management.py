"""
Advanced Cluster Management & Monitoring

This module provides comprehensive cluster management capabilities for the
distributed KV store, including dynamic node management, health monitoring,
and cluster orchestration.

Features:
- Dynamic node join/leave/restart
- Real-time cluster health monitoring
- Node status tracking
- Automatic quorum validation
- Cluster orchestration (start/stop/scale)
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class NodeStatus(Enum):
    """Node status enumeration"""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    RECOVERING = "recovering"
    BOOTSTRAPPING = "bootstrapping"
    OFFLINE = "offline"


@dataclass
class NodeMetrics:
    """Metrics for a single node"""
    node_id: str
    status: NodeStatus = NodeStatus.OFFLINE
    last_heartbeat: float = 0.0
    response_time_ms: float = 0.0
    error_count: int = 0
    uptime_seconds: float = 0.0
    replication_lag_ms: float = 0.0
    processed_commands: int = 0
    failed_commands: int = 0
    
    def is_healthy(self) -> bool:
        """Check if node is healthy"""
        return self.status == NodeStatus.HEALTHY
    
    def get_health_percentage(self) -> float:
        """Calculate health percentage (0-100)"""
        if self.processed_commands == 0:
            return 100.0
        success_rate = (self.processed_commands - self.failed_commands) / self.processed_commands
        return success_rate * 100


@dataclass
class ClusterHealthReport:
    """Comprehensive cluster health report"""
    total_nodes: int
    healthy_nodes: int
    unhealthy_nodes: int
    cluster_quorum: int
    quorum_available: bool
    average_latency_ms: float
    max_replication_lag_ms: float
    cluster_stability: float  # 0-100
    timestamp: float = field(default_factory=time.time)
    
    def is_stable(self) -> bool:
        """Check if cluster is stable"""
        return self.quorum_available and self.cluster_stability > 70


class ClusterManager:
    """Advanced cluster management system"""
    
    def __init__(self, node_id: str, total_nodes: int):
        """Initialize cluster manager
        
        Args:
            node_id: Current node ID
            total_nodes: Initial cluster size
        """
        self.node_id = node_id
        self.total_nodes = total_nodes
        self.node_metrics: Dict[str, NodeMetrics] = {}
        self.active_nodes: Set[str] = set()
        self.failed_nodes: Set[str] = set()
        self.last_quorum_check = 0.0
        self.quorum_size = (total_nodes // 2) + 1
        self.cluster_start_time = time.time()
        
        # Initialize metrics for all nodes
        for i in range(total_nodes):
            node = f"node_{i+1}"
            self.node_metrics[node] = NodeMetrics(node_id=node)
            if node == node_id:
                self.node_metrics[node].status = NodeStatus.HEALTHY
                self.active_nodes.add(node)
    
    async def on_heartbeat_received(self, from_node: str, timestamp: float):
        """Process heartbeat from peer
        
        Args:
            from_node: Node ID sending heartbeat
            timestamp: Heartbeat timestamp
        """
        if from_node not in self.node_metrics:
            return
        
        metrics = self.node_metrics[from_node]
        metrics.last_heartbeat = timestamp
        metrics.status = NodeStatus.HEALTHY
        self.active_nodes.add(from_node)
        self.failed_nodes.discard(from_node)
    
    async def on_heartbeat_timeout(self, for_node: str):
        """Handle heartbeat timeout
        
        Args:
            for_node: Node ID that timed out
        """
        if for_node not in self.node_metrics:
            return
        
        metrics = self.node_metrics[for_node]
        metrics.status = NodeStatus.UNHEALTHY
        metrics.error_count += 1
        self.active_nodes.discard(for_node)
        self.failed_nodes.add(for_node)
    
    async def node_join(self, node_id: str):
        """Handle new node joining cluster
        
        Args:
            node_id: Node joining cluster
        """
        if node_id not in self.node_metrics:
            self.node_metrics[node_id] = NodeMetrics(node_id=node_id)
            self.total_nodes += 1
            self.quorum_size = (self.total_nodes // 2) + 1
        
        self.node_metrics[node_id].status = NodeStatus.BOOTSTRAPPING
        logger.info(f"Node {node_id} joining cluster")
    
    async def node_leave(self, node_id: str):
        """Handle node leaving cluster
        
        Args:
            node_id: Node leaving cluster
        """
        if node_id in self.node_metrics:
            self.node_metrics[node_id].status = NodeStatus.OFFLINE
            self.active_nodes.discard(node_id)
            logger.info(f"Node {node_id} leaving cluster")
    
    async def node_restart(self, node_id: str):
        """Handle node restart
        
        Args:
            node_id: Node being restarted
        """
        if node_id in self.node_metrics:
            metrics = self.node_metrics[node_id]
            metrics.status = NodeStatus.RECOVERING
            metrics.uptime_seconds = 0
            logger.info(f"Node {node_id} restarting")
    
    def has_quorum(self) -> bool:
        """Check if cluster has quorum
        
        Returns:
            True if quorum available
        """
        healthy_count = sum(1 for m in self.node_metrics.values() 
                          if m.status == NodeStatus.HEALTHY)
        return healthy_count >= self.quorum_size
    
    def get_cluster_health(self) -> ClusterHealthReport:
        """Get comprehensive cluster health report
        
        Returns:
            Cluster health report
        """
        healthy_nodes = sum(1 for m in self.node_metrics.values() 
                           if m.status == NodeStatus.HEALTHY)
        unhealthy_nodes = sum(1 for m in self.node_metrics.values() 
                             if m.status == NodeStatus.UNHEALTHY)
        
        avg_latency = sum(m.response_time_ms for m in self.node_metrics.values()) / max(len(self.node_metrics), 1)
        max_lag = max((m.replication_lag_ms for m in self.node_metrics.values()), default=0)
        
        # Calculate cluster stability (0-100)
        stability = (healthy_nodes / max(self.total_nodes, 1)) * 100
        
        return ClusterHealthReport(
            total_nodes=self.total_nodes,
            healthy_nodes=healthy_nodes,
            unhealthy_nodes=unhealthy_nodes,
            cluster_quorum=self.quorum_size,
            quorum_available=self.has_quorum(),
            average_latency_ms=avg_latency,
            max_replication_lag_ms=max_lag,
            cluster_stability=stability
        )
    
    def get_node_metrics(self, node_id: str) -> Optional[NodeMetrics]:
        """Get metrics for specific node
        
        Args:
            node_id: Node ID
            
        Returns:
            Node metrics or None
        """
        return self.node_metrics.get(node_id)
    
    def get_all_metrics(self) -> Dict[str, NodeMetrics]:
        """Get all node metrics
        
        Returns:
            Dictionary of all node metrics
        """
        return self.node_metrics.copy()
    
    async def update_replication_lag(self, node_id: str, lag_ms: float):
        """Update replication lag for node
        
        Args:
            node_id: Node ID
            lag_ms: Lag in milliseconds
        """
        if node_id in self.node_metrics:
            self.node_metrics[node_id].replication_lag_ms = lag_ms
    
    async def record_command_result(self, node_id: str, success: bool):
        """Record command success/failure
        
        Args:
            node_id: Node ID
            success: Whether command succeeded
        """
        if node_id not in self.node_metrics:
            return
        
        metrics = self.node_metrics[node_id]
        metrics.processed_commands += 1
        if not success:
            metrics.failed_commands += 1
    
    def get_healthy_nodes(self) -> List[str]:
        """Get list of healthy nodes
        
        Returns:
            List of healthy node IDs
        """
        return [nid for nid, metrics in self.node_metrics.items() 
                if metrics.status == NodeStatus.HEALTHY]
    
    def get_cluster_status_summary(self) -> str:
        """Get human-readable cluster status summary
        
        Returns:
            Status summary string
        """
        health = self.get_cluster_health()
        return (f"Cluster Status: {health.healthy_nodes}/{health.total_nodes} healthy, "
                f"Stability: {health.cluster_stability:.1f}%, "
                f"Avg Latency: {health.average_latency_ms:.2f}ms")


class ClusterOrchestrator:
    """Orchestrates cluster operations"""
    
    def __init__(self, cluster_manager: ClusterManager):
        """Initialize orchestrator
        
        Args:
            cluster_manager: ClusterManager instance
        """
        self.cluster_manager = cluster_manager
        self.operation_history: List[dict] = []
    
    async def scale_cluster(self, new_size: int) -> bool:
        """Scale cluster to new size
        
        Args:
            new_size: Target cluster size
            
        Returns:
            Success status
        """
        current_size = self.cluster_manager.total_nodes
        
        if new_size > current_size:
            # Add nodes
            for i in range(current_size, new_size):
                await self.cluster_manager.node_join(f"node_{i+1}")
        elif new_size < current_size:
            # Remove nodes
            for i in range(new_size, current_size):
                await self.cluster_manager.node_leave(f"node_{i+1}")
        
        self.operation_history.append({
            "type": "scale",
            "from": current_size,
            "to": new_size,
            "timestamp": time.time()
        })
        
        return True
    
    async def perform_health_check(self) -> ClusterHealthReport:
        """Perform comprehensive health check
        
        Returns:
            Health report
        """
        return self.cluster_manager.get_cluster_health()
    
    async def recover_unhealthy_node(self, node_id: str) -> bool:
        """Attempt to recover unhealthy node
        
        Args:
            node_id: Node to recover
            
        Returns:
            Success status
        """
        await self.cluster_manager.node_restart(node_id)
        
        self.operation_history.append({
            "type": "recovery",
            "node": node_id,
            "timestamp": time.time()
        })
        
        return True
