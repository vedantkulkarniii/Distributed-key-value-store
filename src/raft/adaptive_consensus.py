"""
Adaptive Consensus Optimization

Dynamically optimizes Raft consensus parameters based on cluster conditions
and network characteristics.

Features:
- Adaptive timeout adjustment
- Heartbeat frequency optimization
- Batch size auto-tuning
- Network latency awareness
- Dynamic quorum sizing (for heterogeneous clusters)
- Consensus performance monitoring
- Self-tuning parameters
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
import logging
from collections import deque

logger = logging.getLogger(__name__)


class ConsensusCondition(Enum):
    """Current cluster consensus condition"""
    IDEAL = "ideal"  # Healthy, low latency
    DEGRADED = "degraded"  # Some issues but operational
    CRITICAL = "critical"  # Significant problems
    RECOVERING = "recovering"  # Recovering from issues


@dataclass
class ConsensusMetrics:
    """Metrics for consensus performance"""
    timestamp: float = field(default_factory=time.time)
    election_count: int = 0
    leader_changes: int = 0
    avg_replication_lag_ms: float = 0.0
    consensus_latency_ms: float = 0.0
    commit_rate: float = 0.0  # Commits per second
    follower_sync_rate: float = 0.0  # Percentage of followers in sync
    network_latency_ms: float = 0.0
    
    def get_condition(self) -> ConsensusCondition:
        """Determine current consensus condition"""
        if (self.avg_replication_lag_ms < 100 and
            self.leader_changes < 5 and
            self.follower_sync_rate > 90):
            return ConsensusCondition.IDEAL
        elif (self.avg_replication_lag_ms < 500 and
              self.leader_changes < 10 and
              self.follower_sync_rate > 70):
            return ConsensusCondition.DEGRADED
        elif self.avg_replication_lag_ms > 2000:
            return ConsensusCondition.CRITICAL
        else:
            return ConsensusCondition.RECOVERING


@dataclass
class AdaptiveParameters:
    """Adaptive consensus parameters"""
    election_timeout_min_ms: float = 150
    election_timeout_max_ms: float = 300
    heartbeat_interval_ms: float = 50
    batch_size: int = 100
    batch_timeout_ms: float = 10
    replication_chunk_size: int = 500
    max_inflight_requests: int = 10
    
    def scale_for_latency(self, network_latency_ms: float):
        """Scale parameters based on network latency"""
        multiplier = 1.0 + (network_latency_ms / 100.0)
        self.election_timeout_min_ms *= multiplier
        self.election_timeout_max_ms *= multiplier
        self.heartbeat_interval_ms *= multiplier
    
    def scale_for_load(self, load_percentage: float):
        """Scale parameters based on system load"""
        if load_percentage > 80:
            self.batch_size = int(self.batch_size * 1.5)
            self.batch_timeout_ms *= 1.2
        elif load_percentage < 30:
            self.batch_size = max(50, int(self.batch_size * 0.7))
            self.batch_timeout_ms *= 0.8


class AdaptiveConsensusOptimizer:
    """Optimizes consensus parameters automatically"""
    
    def __init__(self):
        """Initialize optimizer"""
        self.parameters = AdaptiveParameters()
        self.metrics_history: deque = deque(maxlen=100)
        self.last_optimization_time = time.time()
        self.optimization_interval_ms = 5000
        self.adjustment_history: List[Dict] = []
    
    async def record_metrics(self, metrics: ConsensusMetrics):
        """Record consensus metrics
        
        Args:
            metrics: ConsensusMetrics instance
        """
        self.metrics_history.append(metrics)
        
        # Check if optimization is needed
        if time.time() - self.last_optimization_time >= self.optimization_interval_ms / 1000:
            await self._optimize_parameters()
    
    async def _optimize_parameters(self):
        """Automatically optimize parameters"""
        if len(self.metrics_history) < 5:
            return
        
        recent_metrics = list(self.metrics_history)[-10:]
        avg_lag = sum(m.avg_replication_lag_ms for m in recent_metrics) / len(recent_metrics)
        avg_latency = sum(m.network_latency_ms for m in recent_metrics) / len(recent_metrics)
        avg_sync_rate = sum(m.follower_sync_rate for m in recent_metrics) / len(recent_metrics)
        
        # Determine condition
        latest = recent_metrics[-1]
        condition = latest.get_condition()
        
        logger.debug(f"Consensus condition: {condition.value}, lag: {avg_lag:.1f}ms, latency: {avg_latency:.1f}ms")
        
        # Adjust parameters
        if condition == ConsensusCondition.CRITICAL:
            await self._handle_critical_condition(avg_lag, avg_latency)
        elif condition == ConsensusCondition.DEGRADED:
            await self._handle_degraded_condition(avg_lag)
        elif condition == ConsensusCondition.IDEAL:
            await self._optimize_for_performance(avg_lag)
        
        self.last_optimization_time = time.time()
    
    async def _handle_critical_condition(self, lag_ms: float, latency_ms: float):
        """Handle critical condition with conservative adjustments"""
        old_params = self.parameters.__dict__.copy()
        
        # Increase timeouts to allow more time
        self.parameters.election_timeout_min_ms *= 1.5
        self.parameters.election_timeout_max_ms *= 1.5
        
        # Reduce batch sizes to be more responsive
        self.parameters.batch_size = max(20, int(self.parameters.batch_size * 0.5))
        
        # Reduce heartbeat frequency to reduce load
        self.parameters.heartbeat_interval_ms *= 1.5
        
        self._record_adjustment("critical", old_params)
        logger.warning(f"Applied critical condition adjustments (lag: {lag_ms:.1f}ms)")
    
    async def _handle_degraded_condition(self, lag_ms: float):
        """Handle degraded condition with moderate adjustments"""
        old_params = self.parameters.__dict__.copy()
        
        if lag_ms > 500:
            # Increase batch sizes to reduce round trips
            self.parameters.batch_size = int(self.parameters.batch_size * 1.2)
            self.parameters.batch_timeout_ms *= 1.1
        
        self._record_adjustment("degraded", old_params)
    
    async def _optimize_for_performance(self, lag_ms: float):
        """Optimize for performance in ideal conditions"""
        old_params = self.parameters.__dict__.copy()
        
        if lag_ms < 50:
            # Reduce batching to improve latency
            self.parameters.batch_size = max(50, int(self.parameters.batch_size * 0.9))
            self.parameters.batch_timeout_ms *= 0.9
            
            # Increase parallelism
            self.parameters.max_inflight_requests = int(self.parameters.max_inflight_requests * 1.1)
        
        self._record_adjustment("optimal", old_params)
    
    def _record_adjustment(self, reason: str, old_params: Dict):
        """Record parameter adjustment for tracking"""
        self.adjustment_history.append({
            "timestamp": time.time(),
            "reason": reason,
            "old_params": old_params,
            "new_params": self.parameters.__dict__.copy()
        })
        
        if len(self.adjustment_history) > 100:
            self.adjustment_history = self.adjustment_history[-100:]
    
    def get_current_parameters(self) -> AdaptiveParameters:
        """Get current adaptive parameters
        
        Returns:
            Current AdaptiveParameters
        """
        return self.parameters
    
    def get_optimization_stats(self) -> Dict:
        """Get optimization statistics
        
        Returns:
            Statistics dictionary
        """
        return {
            "total_adjustments": len(self.adjustment_history),
            "current_parameters": self.parameters.__dict__,
            "metrics_history_size": len(self.metrics_history),
            "recent_adjustments": self.adjustment_history[-5:] if self.adjustment_history else []
        }


class DynamicQuorumSizer:
    """Dynamically sizes quorum for heterogeneous clusters"""
    
    def __init__(self, cluster_size: int):
        """Initialize quorum sizer
        
        Args:
            cluster_size: Total number of nodes
        """
        self.cluster_size = cluster_size
        self.node_reliability: Dict[str, float] = {}
        self.quorum_size = (cluster_size // 2) + 1
        self.dynamic_quorum_enabled = False
    
    def register_node(self, node_id: str, reliability: float = 1.0):
        """Register node with reliability score
        
        Args:
            node_id: Node ID
            reliability: Reliability score (0-1)
        """
        self.node_reliability[node_id] = reliability
    
    def update_reliability(self, node_id: str, reliability: float):
        """Update node reliability score
        
        Args:
            node_id: Node ID
            reliability: New reliability score
        """
        if node_id in self.node_reliability:
            self.node_reliability[node_id] = max(0, min(1, reliability))
    
    def calculate_optimal_quorum(self) -> Tuple[int, List[str]]:
        """Calculate optimal quorum for current cluster state
        
        Returns:
            Tuple of (quorum_size, preferred_nodes)
        """
        if not self.dynamic_quorum_enabled:
            return self.quorum_size, list(self.node_reliability.keys())[:self.quorum_size]
        
        # Sort by reliability
        sorted_nodes = sorted(
            self.node_reliability.items(),
            key=lambda x: -x[1]
        )
        
        # Calculate dynamic quorum (need consensus from most reliable nodes)
        total_reliability = sum(r for _, r in sorted_nodes)
        target_reliability = total_reliability * 0.75  # Need 75% reliable nodes
        
        cumulative_reliability = 0
        preferred_count = 0
        for node_id, reliability in sorted_nodes:
            if cumulative_reliability >= target_reliability:
                break
            cumulative_reliability += reliability
            preferred_count += 1
        
        quorum_size = max(self.quorum_size, preferred_count)
        preferred_nodes = [n for n, _ in sorted_nodes[:preferred_count]]
        
        return quorum_size, preferred_nodes
    
    def get_quorum_stats(self) -> Dict:
        """Get quorum statistics
        
        Returns:
            Statistics dictionary
        """
        quorum_size, preferred_nodes = self.calculate_optimal_quorum()
        
        return {
            "cluster_size": self.cluster_size,
            "static_quorum": self.quorum_size,
            "dynamic_quorum": quorum_size,
            "total_nodes": len(self.node_reliability),
            "average_reliability": sum(self.node_reliability.values()) / max(len(self.node_reliability), 1),
            "preferred_nodes": preferred_nodes,
            "dynamic_enabled": self.dynamic_quorum_enabled
        }


class ConsensusPerformanceMonitor:
    """Monitors and reports consensus performance"""
    
    def __init__(self):
        """Initialize monitor"""
        self.metrics: List[ConsensusMetrics] = []
        self.performance_alerts: List[str] = []
        self.optimization_suggestions: List[str] = []
    
    async def record_metrics(self, metrics: ConsensusMetrics):
        """Record performance metrics
        
        Args:
            metrics: ConsensusMetrics instance
        """
        self.metrics.append(metrics)
        if len(self.metrics) > 1000:
            self.metrics = self.metrics[-1000:]
        
        await self._analyze_performance()
    
    async def _analyze_performance(self):
        """Analyze performance and generate insights"""
        if len(self.metrics) < 5:
            return
        
        recent = self.metrics[-10:]
        
        # Check for issues
        avg_lag = sum(m.avg_replication_lag_ms for m in recent) / len(recent)
        avg_elections = sum(m.election_count for m in recent) / len(recent)
        
        self.performance_alerts.clear()
        self.optimization_suggestions.clear()
        
        if avg_lag > 1000:
            self.performance_alerts.append(f"High replication lag: {avg_lag:.1f}ms")
            self.optimization_suggestions.append("Increase batch size or reduce heartbeat frequency")
        
        if avg_elections > 2:
            self.performance_alerts.append(f"Frequent elections: {avg_elections:.1f} per report")
            self.optimization_suggestions.append("Increase election timeout")
        
        leader_changes = sum(m.leader_changes for m in recent)
        if leader_changes > 5:
            self.performance_alerts.append(f"Frequent leader changes: {leader_changes}")
            self.optimization_suggestions.append("Check network stability")
    
    def get_performance_report(self) -> Dict:
        """Get comprehensive performance report
        
        Returns:
            Performance report dictionary
        """
        if not self.metrics:
            return {"status": "no_data"}
        
        recent = self.metrics[-10:]
        
        return {
            "status": "ok",
            "total_records": len(self.metrics),
            "recent_records": len(recent),
            "average_lag_ms": sum(m.avg_replication_lag_ms for m in recent) / len(recent),
            "average_consensus_latency_ms": sum(m.consensus_latency_ms for m in recent) / len(recent),
            "average_sync_rate": sum(m.follower_sync_rate for m in recent) / len(recent),
            "alerts": self.performance_alerts,
            "suggestions": self.optimization_suggestions
        }
    
    def get_performance_trend(self) -> Dict:
        """Get performance trend (improving/degrading/stable)
        
        Returns:
            Trend analysis
        """
        if len(self.metrics) < 20:
            return {"trend": "unknown"}
        
        old_metrics = self.metrics[-20:-10]
        new_metrics = self.metrics[-10:]
        
        old_avg_lag = sum(m.avg_replication_lag_ms for m in old_metrics) / len(old_metrics)
        new_avg_lag = sum(m.avg_replication_lag_ms for m in new_metrics) / len(new_metrics)
        
        if new_avg_lag < old_avg_lag * 0.9:
            return {"trend": "improving", "improvement_rate": (1 - new_avg_lag/old_avg_lag) * 100}
        elif new_avg_lag > old_avg_lag * 1.1:
            return {"trend": "degrading", "degradation_rate": (new_avg_lag/old_avg_lag - 1) * 100}
        else:
            return {"trend": "stable"}
