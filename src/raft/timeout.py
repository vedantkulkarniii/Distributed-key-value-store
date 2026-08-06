"""
Election timeout management for Raft.

Implements randomized election timeouts to prevent split votes.
"""

import random
import logging
from typing import Optional, Callable
from datetime import datetime, timedelta


logger = logging.getLogger(__name__)


class ElectionTimeoutManager:
    """
    Manages election timeout for Raft nodes.
    
    Key properties:
    - Randomized timeout in range [minTimeout, maxTimeout]
    - Resets when receiving valid heartbeat
    - Triggers election when expires
    - Prevents split votes through randomization
    """
    
    # Standard Raft timing (RFC)
    DEFAULT_MIN_TIMEOUT = 0.15  # 150ms
    DEFAULT_MAX_TIMEOUT = 0.30  # 300ms
    
    def __init__(self, node_id: str,
                 min_timeout: float = DEFAULT_MIN_TIMEOUT,
                 max_timeout: float = DEFAULT_MAX_TIMEOUT):
        """
        Initialize election timeout manager.
        
        Args:
            node_id: Node ID
            min_timeout: Minimum timeout in seconds
            max_timeout: Maximum timeout in seconds
        """
        self.node_id = node_id
        self.min_timeout = min_timeout
        self.max_timeout = max_timeout
        
        # Validation
        if min_timeout <= 0:
            raise ValueError("min_timeout must be > 0")
        if max_timeout <= min_timeout:
            raise ValueError("max_timeout must be > min_timeout")
        if max_timeout - min_timeout < 0.01:
            logger.warning(
                f"Node {node_id}: Timeout range very small "
                f"({max_timeout - min_timeout:.3f}s)"
            )
        
        # Current timeout value (randomized)
        self.current_timeout = self._randomize_timeout()
        self.started_at = datetime.now()
        self.last_reset = datetime.now()
        
        logger.info(
            f"Node {node_id}: Election timeout range "
            f"{min_timeout:.3f}s - {max_timeout:.3f}s"
        )
    
    def _randomize_timeout(self) -> float:
        """
        Generate a new randomized timeout value.
        
        Returns:
            Random timeout in [min_timeout, max_timeout]
        """
        return random.uniform(self.min_timeout, self.max_timeout)
    
    def reset(self) -> float:
        """
        Reset the election timeout.
        
        Called when receiving valid heartbeat from leader.
        Generates new random timeout value.
        
        Returns:
            The new timeout value in seconds
        """
        self.current_timeout = self._randomize_timeout()
        self.last_reset = datetime.now()
        
        logger.debug(
            f"Node {self.node_id}: Reset election timeout to {self.current_timeout:.3f}s"
        )
        
        return self.current_timeout
    
    def remaining_time(self) -> float:
        """
        Get remaining time before timeout expires.
        
        Returns:
            Seconds remaining (0.0 if expired)
        """
        elapsed = (datetime.now() - self.last_reset).total_seconds()
        remaining = max(0.0, self.current_timeout - elapsed)
        return remaining
    
    def is_expired(self) -> bool:
        """
        Check if election timeout has expired.
        
        Returns:
            True if timeout expired
        """
        return self.remaining_time() <= 0.0
    
    def time_since_reset(self) -> float:
        """
        Get time elapsed since last reset.
        
        Returns:
            Elapsed time in seconds
        """
        return (datetime.now() - self.last_reset).total_seconds()
    
    def get_status(self) -> dict:
        """
        Get timeout status.
        
        Returns:
            Dict with timeout information
        """
        return {
            "node_id": self.node_id,
            "min_timeout": self.min_timeout,
            "max_timeout": self.max_timeout,
            "current_timeout": self.current_timeout,
            "remaining_time": self.remaining_time(),
            "time_since_reset": self.time_since_reset(),
            "expired": self.is_expired()
        }
    
    def __str__(self) -> str:
        """String representation."""
        return (
            f"ElectionTimeout({self.node_id}, "
            f"remaining={self.remaining_time():.3f}s, "
            f"current={self.current_timeout:.3f}s)"
        )


class TimeoutAggregator:
    """
    Aggregates and analyzes election timeouts across a cluster.
    
    Used for testing and analysis of timeout behavior.
    """
    
    def __init__(self):
        """Initialize timeout aggregator."""
        self.timeouts: dict[str, ElectionTimeoutManager] = {}
    
    def register(self, manager: ElectionTimeoutManager) -> None:
        """
        Register a timeout manager.
        
        Args:
            manager: ElectionTimeoutManager to track
        """
        self.timeouts[manager.node_id] = manager
    
    def get_all_remaining(self) -> dict[str, float]:
        """
        Get remaining time for all nodes.
        
        Returns:
            Dict mapping node_id -> remaining seconds
        """
        return {
            node_id: manager.remaining_time()
            for node_id, manager in self.timeouts.items()
        }
    
    def get_min_remaining(self) -> tuple[str, float]:
        """
        Get node with minimum remaining time.
        
        Returns:
            Tuple of (node_id, remaining_seconds)
        """
        min_node = min(
            self.timeouts.items(),
            key=lambda x: x[1].remaining_time()
        )
        return min_node[0], min_node[1].remaining_time()
    
    def get_max_remaining(self) -> tuple[str, float]:
        """
        Get node with maximum remaining time.
        
        Returns:
            Tuple of (node_id, remaining_seconds)
        """
        max_node = max(
            self.timeouts.items(),
            key=lambda x: x[1].remaining_time()
        )
        return max_node[0], max_node[1].remaining_time()
    
    def next_to_timeout(self) -> Optional[str]:
        """
        Get node that will timeout first.
        
        Returns:
            Node ID or None if no nodes
        """
        if not self.timeouts:
            return None
        
        min_node, _ = self.get_min_remaining()
        return min_node
    
    def get_statistics(self) -> dict:
        """
        Get statistics about timeouts in cluster.
        
        Returns:
            Dict with timeout statistics
        """
        remaining_times = self.get_all_remaining()
        
        if not remaining_times:
            return {}
        
        times = list(remaining_times.values())
        return {
            "total_nodes": len(times),
            "min_remaining": min(times),
            "max_remaining": max(times),
            "avg_remaining": sum(times) / len(times),
            "spread": max(times) - min(times),
            "all_timeouts": remaining_times
        }


class SplitVotePrevention:
    """
    Analyzes whether current timeout configuration prevents split votes.
    
    In Raft, split votes happen when two candidates start elections too close in time.
    Randomized timeouts prevent this by making it very unlikely that multiple nodes
    timeout within a small window.
    """
    
    @staticmethod
    def analyze_cluster(aggregator: TimeoutAggregator, n_nodes: int) -> dict:
        """
        Analyze likelihood of split votes in cluster.
        
        Args:
            aggregator: TimeoutAggregator with registered nodes
            n_nodes: Total nodes in cluster
            
        Returns:
            Dict with analysis results
        """
        stats = aggregator.get_statistics()
        
        if not stats:
            return {"error": "No timeouts registered"}
        
        spread = stats["spread"]
        min_timeout = min(m.min_timeout for m in aggregator.timeouts.values())
        
        # Probability analysis
        # If timeout range is [a, b], probability that N nodes timeout within window W is:
        # P ≈ (W / (b - a))^(N-1)
        
        # For safe election: spread should be > heartbeat interval
        heartbeat_interval = min_timeout / 2  # Typical: 75ms
        
        return {
            "total_nodes": n_nodes,
            "timeout_spread": spread,
            "heartbeat_interval": heartbeat_interval,
            "quorum_needed": (n_nodes // 2) + 1,
            "is_safe": spread > heartbeat_interval * 10,  # Conservative estimate
            "min_remaining": stats["min_remaining"],
            "max_remaining": stats["max_remaining"],
            "avg_remaining": stats["avg_remaining"]
        }


# Timeout configuration presets

class TimeoutConfig:
    """Common timeout configurations."""
    
    # Standard Raft (RFC 5157)
    STANDARD = {
        "min_timeout": 0.15,  # 150ms
        "max_timeout": 0.30   # 300ms
    }
    
    # Conservative (slow networks, high latency)
    CONSERVATIVE = {
        "min_timeout": 0.5,   # 500ms
        "max_timeout": 1.0    # 1000ms
    }
    
    # Aggressive (LAN, low latency)
    AGGRESSIVE = {
        "min_timeout": 0.05,  # 50ms
        "max_timeout": 0.1    # 100ms
    }
    
    # Testing (very fast for unit tests)
    TEST = {
        "min_timeout": 0.01,  # 10ms
        "max_timeout": 0.02   # 20ms
    }
    
    @staticmethod
    def get(profile: str = "standard") -> dict:
        """
        Get timeout configuration by profile.
        
        Args:
            profile: "standard", "conservative", "aggressive", or "test"
            
        Returns:
            Dict with min_timeout and max_timeout
        """
        profiles = {
            "standard": TimeoutConfig.STANDARD,
            "conservative": TimeoutConfig.CONSERVATIVE,
            "aggressive": TimeoutConfig.AGGRESSIVE,
            "test": TimeoutConfig.TEST
        }
        
        if profile not in profiles:
            logger.warning(f"Unknown timeout profile: {profile}, using standard")
            return TimeoutConfig.STANDARD
        
        return profiles[profile]
