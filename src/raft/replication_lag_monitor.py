"""
Replication Lag Monitoring & Optimization.

Implements replication lag tracking and optimization:
- Per-follower lag metrics
- Lag-based prioritization
- Adaptive heartbeat frequency
- Catch-up optimization strategies
- Lag visualization data structures
"""

import logging
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import deque

logger = logging.getLogger(__name__)


class LagSeverity(Enum):
    """Classification of replication lag severity."""
    HEALTHY = "healthy"  # Lag <= 10 entries
    MODERATE = "moderate"  # Lag 11-50 entries
    HIGH = "high"  # Lag 51-200 entries
    CRITICAL = "critical"  # Lag > 200 entries


@dataclass
class LagMetric:
    """Single replication lag measurement."""
    timestamp: datetime
    follower_id: str
    lag_entries: int
    is_catching_up: bool = False
    catch_up_rate: float = 0.0  # entries per second
    
    def get_severity(self) -> LagSeverity:
        """Classify lag severity."""
        if self.lag_entries <= 10:
            return LagSeverity.HEALTHY
        elif self.lag_entries <= 50:
            return LagSeverity.MODERATE
        elif self.lag_entries <= 200:
            return LagSeverity.HIGH
        else:
            return LagSeverity.CRITICAL


@dataclass
class FollowerLagState:
    """Current lag state for a single follower."""
    follower_id: str
    current_lag: int = 0
    max_lag: int = 0
    min_lag: int = 0
    avg_lag: float = 0.0
    lag_history: deque = field(default_factory=lambda: deque(maxlen=100))
    last_update: datetime = field(default_factory=datetime.now)
    catch_up_start_time: Optional[datetime] = None
    catch_up_rate_samples: deque = field(default_factory=lambda: deque(maxlen=50))
    priority_score: float = 0.0
    heartbeat_frequency_ms: int = 150  # Default heartbeat frequency
    
    def update_lag(self, new_lag: int, catching_up: bool = False) -> None:
        """
        Update lag measurement.
        
        Args:
            new_lag: New lag value
            catching_up: Whether node is in catch-up mode
        """
        self.current_lag = new_lag
        self.lag_history.append(new_lag)
        
        if not self.lag_history:
            self.avg_lag = new_lag
        else:
            self.avg_lag = sum(self.lag_history) / len(self.lag_history)
        
        self.max_lag = max(self.max_lag, new_lag)
        self.min_lag = min(self.min_lag, new_lag) if self.min_lag > 0 else new_lag
        
        if catching_up and not self.catch_up_start_time:
            self.catch_up_start_time = datetime.now()
        elif not catching_up:
            self.catch_up_start_time = None
        
        self.last_update = datetime.now()
    
    def update_catch_up_rate(self, rate: float) -> None:
        """
        Update catch-up rate.
        
        Args:
            rate: Entries per second
        """
        self.catch_up_rate_samples.append(rate)
    
    def get_avg_catch_up_rate(self) -> float:
        """Get average catch-up rate."""
        if not self.catch_up_rate_samples:
            return 0.0
        return sum(self.catch_up_rate_samples) / len(self.catch_up_rate_samples)
    
    def get_severity(self) -> LagSeverity:
        """Get current lag severity."""
        if self.current_lag <= 10:
            return LagSeverity.HEALTHY
        elif self.current_lag <= 50:
            return LagSeverity.MODERATE
        elif self.current_lag <= 200:
            return LagSeverity.HIGH
        else:
            return LagSeverity.CRITICAL
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "follower_id": self.follower_id,
            "current_lag": self.current_lag,
            "max_lag": self.max_lag,
            "min_lag": self.min_lag,
            "avg_lag": round(self.avg_lag, 2),
            "severity": self.get_severity().value,
            "priority_score": round(self.priority_score, 2),
            "heartbeat_frequency_ms": self.heartbeat_frequency_ms,
            "catch_up_rate": round(self.get_avg_catch_up_rate(), 2)
        }


class ReplicationLagMonitor:
    """Monitors and optimizes replication lag across cluster."""
    
    def __init__(self, leader_id: str, followers: List[str]):
        """
        Initialize replication lag monitor.
        
        Args:
            leader_id: Leader node ID
            followers: List of follower node IDs
        """
        self.leader_id = leader_id
        self.followers = followers
        self.follower_states: Dict[str, FollowerLagState] = {}
        self.global_lag_history: deque = deque(maxlen=1000)
        self.lag_samples_per_second: int = 10
        
        # Initialize follower states
        for follower in followers:
            self.follower_states[follower] = FollowerLagState(follower_id=follower)
        
        # Tracking
        self.total_measurements: int = 0
        self.last_optimization_time: datetime = datetime.now()
        self.optimization_interval_seconds: float = 5.0
    
    def report_lag(
        self,
        follower_id: str,
        lag_entries: int,
        catching_up: bool = False
    ) -> None:
        """
        Report lag measurement for a follower.
        
        Args:
            follower_id: Follower node ID
            lag_entries: Number of log entries behind
            catching_up: Whether node is in catch-up mode
        """
        if follower_id not in self.follower_states:
            logger.warning(f"Unknown follower {follower_id}")
            return
        
        state = self.follower_states[follower_id]
        state.update_lag(lag_entries, catching_up)
        
        metric = LagMetric(
            timestamp=datetime.now(),
            follower_id=follower_id,
            lag_entries=lag_entries,
            is_catching_up=catching_up
        )
        self.global_lag_history.append(metric)
        self.total_measurements += 1
    
    def report_catch_up_progress(self, follower_id: str, entries_per_second: float) -> None:
        """
        Report catch-up progress for a follower.
        
        Args:
            follower_id: Follower node ID
            entries_per_second: Replication rate
        """
        if follower_id not in self.follower_states:
            return
        
        self.follower_states[follower_id].update_catch_up_rate(entries_per_second)
    
    def calculate_priority_scores(self) -> Dict[str, float]:
        """
        Calculate priority scores for each follower.
        
        Higher score = higher priority for replication.
        
        Returns:
            Dict of follower_id -> priority_score
        """
        scores = {}
        
        # Base priority on lag severity
        severity_weights = {
            LagSeverity.HEALTHY: 1.0,
            LagSeverity.MODERATE: 5.0,
            LagSeverity.HIGH: 15.0,
            LagSeverity.CRITICAL: 30.0
        }
        
        total_lag = sum(state.current_lag for state in self.follower_states.values())
        
        for follower_id, state in self.follower_states.items():
            # Base score from severity
            severity = state.get_severity()
            base_score = severity_weights[severity]
            
            # Adjust based on lag proportion
            if total_lag > 0:
                lag_proportion = state.current_lag / total_lag
                base_score *= (1.0 + lag_proportion)
            
            # Adjust based on catch-up rate (faster catch-up = lower priority)
            catch_up_rate = state.get_avg_catch_up_rate()
            if catch_up_rate > 0:
                base_score *= (100.0 / (100.0 + catch_up_rate))
            
            state.priority_score = base_score
            scores[follower_id] = base_score
        
        return scores
    
    def get_lagged_followers(
        self,
        min_lag: int = 1,
        max_results: Optional[int] = None
    ) -> List[str]:
        """
        Get followers with lag above threshold.
        
        Args:
            min_lag: Minimum lag to include
            max_results: Maximum results to return (sorted by lag)
            
        Returns:
            List of follower IDs sorted by lag (highest first)
        """
        lagged = [
            (fid, state.current_lag)
            for fid, state in self.follower_states.items()
            if state.current_lag >= min_lag
        ]
        
        lagged.sort(key=lambda x: x[1], reverse=True)
        
        if max_results:
            lagged = lagged[:max_results]
        
        return [fid for fid, _ in lagged]
    
    def get_critical_lag_followers(self) -> List[str]:
        """
        Get followers with critical lag.
        
        Returns:
            List of follower IDs with critical lag
        """
        return [
            fid for fid, state in self.follower_states.items()
            if state.get_severity() == LagSeverity.CRITICAL
        ]
    
    def optimize_heartbeat_frequency(self) -> Dict[str, int]:
        """
        Optimize heartbeat frequency based on lag.
        
        Lower frequency for healthy followers, higher for lagged ones.
        
        Returns:
            Dict of follower_id -> heartbeat_frequency_ms
        """
        frequencies = {}
        
        for follower_id, state in self.follower_states.items():
            severity = state.get_severity()
            
            # Adjust frequency based on severity
            if severity == LagSeverity.HEALTHY:
                frequency = 300  # Slower for healthy
            elif severity == LagSeverity.MODERATE:
                frequency = 150  # Default
            elif severity == LagSeverity.HIGH:
                frequency = 50   # Faster for high lag
            else:  # CRITICAL
                frequency = 10   # Very fast for critical
            
            state.heartbeat_frequency_ms = frequency
            frequencies[follower_id] = frequency
        
        return frequencies
    
    def estimate_catch_up_time(self, follower_id: str, target_lag: int = 0) -> Optional[float]:
        """
        Estimate time to catch up for a follower.
        
        Args:
            follower_id: Follower node ID
            target_lag: Target lag level (0 for fully caught up)
            
        Returns:
            Estimated seconds to catch up, or None if not catching up
        """
        if follower_id not in self.follower_states:
            return None
        
        state = self.follower_states[follower_id]
        catch_up_rate = state.get_avg_catch_up_rate()
        
        if catch_up_rate <= 0:
            return None
        
        lag_to_close = max(0, state.current_lag - target_lag)
        return lag_to_close / catch_up_rate
    
    def get_lag_by_severity(self) -> Dict[str, List[str]]:
        """
        Group followers by lag severity.
        
        Returns:
            Dict of severity -> list of follower IDs
        """
        grouped = {
            severity.value: [] for severity in LagSeverity
        }
        
        for follower_id, state in self.follower_states.items():
            severity = state.get_severity()
            grouped[severity.value].append(follower_id)
        
        return grouped
    
    def get_replication_gap_analysis(self) -> dict:
        """
        Analyze overall replication gaps in cluster.
        
        Returns:
            Analysis including max gap, average gap, distribution
        """
        if not self.follower_states:
            return {}
        
        lags = [state.current_lag for state in self.follower_states.values()]
        
        return {
            "total_followers": len(self.follower_states),
            "max_lag": max(lags),
            "min_lag": min(lags),
            "avg_lag": sum(lags) / len(lags),
            "median_lag": sorted(lags)[len(lags) // 2],
            "total_cluster_lag": sum(lags),
            "healthy_followers": len([l for l in lags if l <= 10]),
            "degraded_followers": len([l for l in lags if 10 < l <= 50]),
            "critical_followers": len([l for l in lags if l > 50])
        }
    
    def optimize_replication(self) -> dict:
        """
        Run full replication optimization pass.
        
        Includes priority calculation, heartbeat optimization, etc.
        
        Returns:
            Optimization recommendations
        """
        now = datetime.now()
        time_since_last_optimization = (now - self.last_optimization_time).total_seconds()
        
        if time_since_last_optimization < self.optimization_interval_seconds:
            return {}
        
        # Calculate priorities
        priorities = self.calculate_priority_scores()
        
        # Optimize heartbeat frequencies
        frequencies = self.optimize_heartbeat_frequency()
        
        # Identify critical followers
        critical = self.get_critical_lag_followers()
        
        # Get gap analysis
        analysis = self.get_replication_gap_analysis()
        
        self.last_optimization_time = now
        
        return {
            "priorities": priorities,
            "frequencies": frequencies,
            "critical_followers": critical,
            "analysis": analysis,
            "timestamp": now.isoformat()
        }
    
    def get_follower_status(self, follower_id: str) -> Optional[dict]:
        """
        Get comprehensive status for a follower.
        
        Args:
            follower_id: Follower node ID
            
        Returns:
            Status dictionary or None
        """
        if follower_id not in self.follower_states:
            return None
        
        state = self.follower_states[follower_id]
        catch_up_time = self.estimate_catch_up_time(follower_id)
        
        return {
            "follower_id": follower_id,
            "lag_metrics": state.to_dict(),
            "estimated_catch_up_seconds": catch_up_time,
            "last_update": state.last_update.isoformat()
        }
    
    def get_cluster_lag_report(self) -> dict:
        """
        Generate comprehensive cluster lag report.
        
        Returns:
            Detailed lag report
        """
        self.optimize_replication()
        
        follower_statuses = {
            fid: self.get_follower_status(fid)
            for fid in self.followers
        }
        
        return {
            "leader": self.leader_id,
            "total_measurements": self.total_measurements,
            "overall_analysis": self.get_replication_gap_analysis(),
            "severity_breakdown": self.get_lag_by_severity(),
            "follower_statuses": follower_statuses,
            "optimization_recommendations": self.optimize_replication(),
            "timestamp": datetime.now().isoformat()
        }
    
    def reset_metrics(self) -> None:
        """Reset all metrics for fresh monitoring."""
        for state in self.follower_states.values():
            state.lag_history.clear()
            state.catch_up_rate_samples.clear()
            state.current_lag = 0
            state.max_lag = 0
            state.min_lag = 0
            state.avg_lag = 0.0
            state.catch_up_start_time = None
        
        self.global_lag_history.clear()
        self.total_measurements = 0
        logger.info("Replication lag metrics reset")
    
    def get_lag_trend(self, follower_id: str, window_size: int = 10) -> List[int]:
        """
        Get lag trend for a follower.
        
        Args:
            follower_id: Follower node ID
            window_size: Number of recent measurements to return
            
        Returns:
            List of recent lag measurements
        """
        if follower_id not in self.follower_states:
            return []
        
        state = self.follower_states[follower_id]
        history = list(state.lag_history)
        return history[-window_size:]
    
    def is_replication_healthy(self, max_acceptable_lag: int = 50) -> bool:
        """
        Check if overall replication is healthy.
        
        Args:
            max_acceptable_lag: Maximum acceptable lag
            
        Returns:
            True if all followers below threshold
        """
        return all(
            state.current_lag <= max_acceptable_lag
            for state in self.follower_states.values()
        )
