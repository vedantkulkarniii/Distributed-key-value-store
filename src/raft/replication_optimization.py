"""
Replication Lag Monitoring & Optimization

Tracks and optimizes replication lag across cluster nodes,
implementing adaptive strategies for faster state synchronization.

Features:
- Per-follower lag metrics
- Lag-based prioritization
- Adaptive heartbeat frequency
- Catch-up optimization
- Lag visualization
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class LagPriority(Enum):
    """Replication lag priority levels"""
    CRITICAL = "critical"  # > 5000ms lag
    HIGH = "high"  # 1000-5000ms
    MEDIUM = "medium"  # 100-1000ms
    LOW = "low"  # < 100ms


@dataclass
class LagMetric:
    """Replication lag metric for a follower"""
    follower_id: str
    lag_ms: float = 0.0
    last_update: float = field(default_factory=time.time)
    max_lag_observed: float = 0.0
    catch_up_attempts: int = 0
    catch_up_success: int = 0
    
    def get_priority(self) -> LagPriority:
        """Get replication priority based on lag"""
        if self.lag_ms > 5000:
            return LagPriority.CRITICAL
        elif self.lag_ms > 1000:
            return LagPriority.HIGH
        elif self.lag_ms > 100:
            return LagPriority.MEDIUM
        else:
            return LagPriority.LOW
    
    def get_catch_up_rate(self) -> float:
        """Get catch-up success rate"""
        if self.catch_up_attempts == 0:
            return 100.0
        return (self.catch_up_success / self.catch_up_attempts) * 100
    
    def is_critical(self) -> bool:
        """Check if lag is critical"""
        return self.lag_ms > 5000


@dataclass
class LagOptimizationStrategy:
    """Strategy for optimizing replication lag"""
    follower_id: str
    increased_heartbeat_frequency: float = 1.0  # Multiplier
    batch_size_multiplier: float = 1.0
    priority_boost: int = 0
    aggressive_mode: bool = False


class ReplicationLagMonitor:
    """Monitors and optimizes replication lag"""
    
    def __init__(self, leader_id: str):
        """Initialize lag monitor
        
        Args:
            leader_id: ID of leader node
        """
        self.leader_id = leader_id
        self.lag_metrics: Dict[str, LagMetric] = {}
        self.optimization_strategies: Dict[str, LagOptimizationStrategy] = {}
        self.lag_history: Dict[str, List[Tuple[float, float]]] = {}
        self.total_lag_events = 0
        self.average_lag_ms = 0.0
        self.peak_lag_ms = 0.0
    
    def register_follower(self, follower_id: str):
        """Register follower for lag tracking
        
        Args:
            follower_id: Follower node ID
        """
        if follower_id not in self.lag_metrics:
            self.lag_metrics[follower_id] = LagMetric(follower_id=follower_id)
            self.lag_history[follower_id] = []
            self.optimization_strategies[follower_id] = LagOptimizationStrategy(
                follower_id=follower_id
            )
    
    async def update_lag(self, follower_id: str, lag_ms: float):
        """Update replication lag for follower
        
        Args:
            follower_id: Follower ID
            lag_ms: Lag in milliseconds
        """
        if follower_id not in self.lag_metrics:
            self.register_follower(follower_id)
        
        metric = self.lag_metrics[follower_id]
        metric.lag_ms = lag_ms
        metric.last_update = time.time()
        metric.max_lag_observed = max(metric.max_lag_observed, lag_ms)
        
        # Track history
        self.lag_history[follower_id].append((time.time(), lag_ms))
        if len(self.lag_history[follower_id]) > 1000:
            self.lag_history[follower_id] = self.lag_history[follower_id][-1000:]
        
        # Update statistics
        self.total_lag_events += 1
        self.peak_lag_ms = max(self.peak_lag_ms, lag_ms)
        self._update_average_lag()
        
        # Apply optimization if needed
        if metric.get_priority() == LagPriority.CRITICAL:
            await self._apply_aggressive_optimization(follower_id)
    
    def get_lag(self, follower_id: str) -> float:
        """Get current lag for follower
        
        Args:
            follower_id: Follower ID
            
        Returns:
            Lag in milliseconds
        """
        metric = self.lag_metrics.get(follower_id)
        return metric.lag_ms if metric else 0.0
    
    def get_priority_order(self) -> List[str]:
        """Get followers ordered by replication priority
        
        Returns:
            List of follower IDs ordered by priority
        """
        priority_map = {
            LagPriority.CRITICAL: 0,
            LagPriority.HIGH: 1,
            LagPriority.MEDIUM: 2,
            LagPriority.LOW: 3
        }
        
        return sorted(
            self.lag_metrics.keys(),
            key=lambda f: (
                priority_map[self.lag_metrics[f].get_priority()],
                -self.lag_metrics[f].lag_ms
            )
        )
    
    async def _apply_aggressive_optimization(self, follower_id: str):
        """Apply aggressive optimization for critical lag
        
        Args:
            follower_id: Follower ID
        """
        strategy = self.optimization_strategies[follower_id]
        strategy.increased_heartbeat_frequency = 10.0
        strategy.batch_size_multiplier = 5.0
        strategy.priority_boost = 10
        strategy.aggressive_mode = True
        
        logger.warning(f"Applying aggressive optimization for {follower_id} (lag: {self.lag_metrics[follower_id].lag_ms}ms)")
    
    def get_optimization_strategy(self, follower_id: str) -> LagOptimizationStrategy:
        """Get optimization strategy for follower
        
        Args:
            follower_id: Follower ID
            
        Returns:
            Optimization strategy
        """
        return self.optimization_strategies.get(
            follower_id,
            LagOptimizationStrategy(follower_id=follower_id)
        )
    
    async def record_catch_up_attempt(self, follower_id: str, success: bool):
        """Record catch-up attempt result
        
        Args:
            follower_id: Follower ID
            success: Whether catch-up succeeded
        """
        if follower_id not in self.lag_metrics:
            return
        
        metric = self.lag_metrics[follower_id]
        metric.catch_up_attempts += 1
        if success:
            metric.catch_up_success += 1
            
            # Reduce optimization if successful
            strategy = self.optimization_strategies[follower_id]
            if metric.get_priority() != LagPriority.CRITICAL:
                strategy.increased_heartbeat_frequency = max(1.0, strategy.increased_heartbeat_frequency - 0.5)
                strategy.aggressive_mode = False
    
    def get_lag_distribution(self) -> Dict[LagPriority, int]:
        """Get distribution of lag priorities
        
        Returns:
            Count of followers in each priority level
        """
        distribution = {priority: 0 for priority in LagPriority}
        for metric in self.lag_metrics.values():
            distribution[metric.get_priority()] += 1
        return distribution
    
    def get_critical_followers(self) -> List[str]:
        """Get list of critically lagged followers
        
        Returns:
            List of follower IDs with critical lag
        """
        return [fid for fid, metric in self.lag_metrics.items() 
                if metric.is_critical()]
    
    def _update_average_lag(self):
        """Update average lag calculation"""
        if not self.lag_metrics:
            self.average_lag_ms = 0.0
            return
        
        total_lag = sum(m.lag_ms for m in self.lag_metrics.values())
        self.average_lag_ms = total_lag / len(self.lag_metrics)
    
    def get_lag_statistics(self) -> Dict:
        """Get comprehensive lag statistics
        
        Returns:
            Dictionary of statistics
        """
        return {
            "average_lag_ms": self.average_lag_ms,
            "peak_lag_ms": self.peak_lag_ms,
            "total_events": self.total_lag_events,
            "critical_followers": len(self.get_critical_followers()),
            "lag_distribution": self.get_lag_distribution()
        }
    
    def get_catch_up_rates(self) -> Dict[str, float]:
        """Get catch-up success rates for all followers
        
        Returns:
            Dictionary of catch-up rates
        """
        return {
            fid: metric.get_catch_up_rate()
            for fid, metric in self.lag_metrics.items()
        }
    
    def get_lag_trend(self, follower_id: str, window_size: int = 10) -> str:
        """Get lag trend (improving/worsening/stable)
        
        Args:
            follower_id: Follower ID
            window_size: Number of samples to consider
            
        Returns:
            Trend indicator: "improving", "worsening", "stable"
        """
        if follower_id not in self.lag_history:
            return "unknown"
        
        history = self.lag_history[follower_id]
        if len(history) < window_size:
            return "unknown"
        
        recent = [lag for _, lag in history[-window_size:]]
        first_half = sum(recent[:len(recent)//2]) / (len(recent)//2)
        second_half = sum(recent[len(recent)//2:]) / (len(recent) - len(recent)//2)
        
        if second_half < first_half * 0.9:
            return "improving"
        elif second_half > first_half * 1.1:
            return "worsening"
        else:
            return "stable"


class AdaptiveHeartbeatManager:
    """Manages adaptive heartbeat frequency based on lag"""
    
    def __init__(self, lag_monitor: ReplicationLagMonitor):
        """Initialize manager
        
        Args:
            lag_monitor: ReplicationLagMonitor instance
        """
        self.lag_monitor = lag_monitor
        self.base_heartbeat_ms = 150
        self.heartbeat_frequencies: Dict[str, float] = {}
    
    def get_heartbeat_interval(self, follower_id: str) -> float:
        """Get heartbeat interval for follower
        
        Args:
            follower_id: Follower ID
            
        Returns:
            Interval in milliseconds
        """
        strategy = self.lag_monitor.get_optimization_strategy(follower_id)
        base = self.base_heartbeat_ms / strategy.increased_heartbeat_frequency
        return max(10, base)  # Minimum 10ms
    
    def update_all_intervals(self):
        """Update all heartbeat intervals based on current lag"""
        for follower_id in self.lag_monitor.lag_metrics.keys():
            interval = self.get_heartbeat_interval(follower_id)
            self.heartbeat_frequencies[follower_id] = interval


class CatchUpOptimizer:
    """Optimizes catch-up process for lagged followers"""
    
    def __init__(self, lag_monitor: ReplicationLagMonitor):
        """Initialize optimizer
        
        Args:
            lag_monitor: ReplicationLagMonitor instance
        """
        self.lag_monitor = lag_monitor
        self.default_batch_size = 100
    
    def get_batch_size(self, follower_id: str) -> int:
        """Get optimal batch size for follower
        
        Args:
            follower_id: Follower ID
            
        Returns:
            Recommended batch size
        """
        strategy = self.lag_monitor.get_optimization_strategy(follower_id)
        return int(self.default_batch_size * strategy.batch_size_multiplier)
    
    async def execute_catch_up(self, follower_id: str, entries_to_send: int) -> bool:
        """Execute catch-up process
        
        Args:
            follower_id: Follower ID
            entries_to_send: Number of entries to send
            
        Returns:
            Success status
        """
        batch_size = self.get_batch_size(follower_id)
        success = True
        
        # Simulate sending batches
        for i in range(0, entries_to_send, batch_size):
            batch = min(batch_size, entries_to_send - i)
            # In real implementation, would send batch
            await asyncio.sleep(0.001)  # Simulate network
        
        await self.lag_monitor.record_catch_up_attempt(follower_id, success)
        return success
