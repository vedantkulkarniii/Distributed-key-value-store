"""
Advanced Request Routing & Load Balancing

Implements intelligent request routing strategies to optimize throughput
and latency across cluster nodes.

Features:
- Multiple routing strategies (Round-robin, Least-loaded, Latency-aware)
- Request affinity and session stickiness
- Dynamic load calculation
- Request prioritization
- Circuit breaker pattern
- Adaptive strategy selection
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable
from enum import Enum
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


class RoutingStrategy(Enum):
    """Request routing strategy types"""
    ROUND_ROBIN = "round_robin"
    LEAST_LOADED = "least_loaded"
    LATENCY_AWARE = "latency_aware"
    AFFINITY = "affinity"
    RANDOM = "random"
    ADAPTIVE = "adaptive"


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Rejecting requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class RequestMetrics:
    """Metrics for request routing"""
    node_id: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_latency_ms: float = 0.0
    last_request_time: float = field(default_factory=time.time)
    error_rate: float = 0.0
    
    def get_success_rate(self) -> float:
        """Get success rate percentage"""
        if self.total_requests == 0:
            return 100.0
        return (self.successful_requests / self.total_requests) * 100
    
    def update_error_rate(self):
        """Update error rate"""
        if self.total_requests == 0:
            self.error_rate = 0.0
        else:
            self.error_rate = (self.failed_requests / self.total_requests) * 100


@dataclass
class CircuitBreaker:
    """Circuit breaker for fault protection"""
    node_id: str
    state: CircuitState = CircuitState.CLOSED
    failure_threshold: int = 5
    reset_timeout: float = 30.0
    failure_count: int = 0
    last_failure_time: float = 0.0
    success_count_in_half_open: int = 0
    required_successes: int = 2
    
    def record_failure(self):
        """Record a failure"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
    
    def record_success(self):
        """Record a success"""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count_in_half_open += 1
            if self.success_count_in_half_open >= self.required_successes:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count_in_half_open = 0
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0
    
    def can_attempt_request(self) -> bool:
        """Check if request can be attempted"""
        if self.state == CircuitState.CLOSED:
            return True
        elif self.state == CircuitState.OPEN:
            # Try to transition to half-open
            if time.time() - self.last_failure_time >= self.reset_timeout:
                self.state = CircuitState.HALF_OPEN
                self.success_count_in_half_open = 0
                return True
            return False
        else:  # HALF_OPEN
            return True
    
    def is_healthy(self) -> bool:
        """Check if node is healthy"""
        return self.state == CircuitState.CLOSED


class RequestRouter:
    """Intelligent request routing system"""
    
    def __init__(self, nodes: List[str], strategy: RoutingStrategy = RoutingStrategy.ADAPTIVE):
        """Initialize request router
        
        Args:
            nodes: List of node IDs
            strategy: Initial routing strategy
        """
        self.nodes = nodes
        self.strategy = strategy
        self.request_metrics: Dict[str, RequestMetrics] = {}
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.affinity_map: Dict[str, str] = {}  # Client -> Node mapping
        self.request_counter = 0
        self.node_index = 0
        
        # Initialize metrics and circuit breakers
        for node in nodes:
            self.request_metrics[node] = RequestMetrics(node_id=node)
            self.circuit_breakers[node] = CircuitBreaker(node_id=node)
    
    def select_node(self, client_id: Optional[str] = None) -> Optional[str]:
        """Select node for request based on strategy
        
        Args:
            client_id: Optional client ID for affinity
            
        Returns:
            Selected node ID or None if no healthy nodes
        """
        # Check circuit breakers first
        healthy_nodes = [n for n in self.nodes if self.circuit_breakers[n].is_healthy()]
        
        if not healthy_nodes:
            return None
        
        if self.strategy == RoutingStrategy.ROUND_ROBIN:
            return self._round_robin(healthy_nodes)
        elif self.strategy == RoutingStrategy.LEAST_LOADED:
            return self._least_loaded(healthy_nodes)
        elif self.strategy == RoutingStrategy.LATENCY_AWARE:
            return self._latency_aware(healthy_nodes)
        elif self.strategy == RoutingStrategy.AFFINITY and client_id:
            return self._affinity(client_id, healthy_nodes)
        elif self.strategy == RoutingStrategy.ADAPTIVE:
            return self._adaptive(healthy_nodes)
        else:
            return healthy_nodes[0]
    
    def _round_robin(self, healthy_nodes: List[str]) -> str:
        """Round-robin selection"""
        selected = healthy_nodes[self.node_index % len(healthy_nodes)]
        self.node_index += 1
        return selected
    
    def _least_loaded(self, healthy_nodes: List[str]) -> str:
        """Least-loaded selection"""
        return min(
            healthy_nodes,
            key=lambda n: self.request_metrics[n].total_requests
        )
    
    def _latency_aware(self, healthy_nodes: List[str]) -> str:
        """Latency-aware selection"""
        return min(
            healthy_nodes,
            key=lambda n: self.request_metrics[n].avg_latency_ms
        )
    
    def _affinity(self, client_id: str, healthy_nodes: List[str]) -> str:
        """Session affinity selection"""
        if client_id in self.affinity_map:
            node = self.affinity_map[client_id]
            if node in healthy_nodes:
                return node
        
        # Assign new node
        selected = healthy_nodes[0]
        self.affinity_map[client_id] = selected
        return selected
    
    def _adaptive(self, healthy_nodes: List[str]) -> str:
        """Adaptive selection based on multiple factors"""
        # Weight by success rate, latency, and load
        scores = {}
        for node in healthy_nodes:
            metrics = self.request_metrics[node]
            success_rate = metrics.get_success_rate() / 100.0
            latency_factor = 1.0 / (metrics.avg_latency_ms + 1)
            load_factor = 1.0 / (metrics.total_requests + 1)
            
            score = (success_rate * 0.5) + (latency_factor * 0.3) + (load_factor * 0.2)
            scores[node] = score
        
        return max(scores, key=scores.get)
    
    async def record_request(self, node_id: str, success: bool, latency_ms: float):
        """Record request result
        
        Args:
            node_id: Node ID
            success: Whether request succeeded
            latency_ms: Request latency in milliseconds
        """
        if node_id not in self.request_metrics:
            return
        
        metrics = self.request_metrics[node_id]
        metrics.total_requests += 1
        metrics.last_request_time = time.time()
        
        # Update latency (exponential moving average)
        if metrics.total_requests == 1:
            metrics.avg_latency_ms = latency_ms
        else:
            metrics.avg_latency_ms = (metrics.avg_latency_ms * 0.7) + (latency_ms * 0.3)
        
        if success:
            metrics.successful_requests += 1
            self.circuit_breakers[node_id].record_success()
        else:
            metrics.failed_requests += 1
            self.circuit_breakers[node_id].record_failure()
        
        metrics.update_error_rate()
    
    def get_node_load(self) -> Dict[str, float]:
        """Get load for each node
        
        Returns:
            Dictionary of node loads (0-100)
        """
        loads = {}
        max_load = max((m.total_requests for m in self.request_metrics.values()), default=1)
        
        for node, metrics in self.request_metrics.items():
            loads[node] = (metrics.total_requests / max(max_load, 1)) * 100
        
        return loads
    
    def get_routing_stats(self) -> Dict:
        """Get comprehensive routing statistics
        
        Returns:
            Statistics dictionary
        """
        return {
            "strategy": self.strategy.value,
            "total_routes": self.request_counter,
            "nodes": {
                node: {
                    "total_requests": metrics.total_requests,
                    "successful_requests": metrics.successful_requests,
                    "failed_requests": metrics.failed_requests,
                    "success_rate": metrics.get_success_rate(),
                    "avg_latency_ms": metrics.avg_latency_ms,
                    "error_rate": metrics.error_rate,
                    "circuit_state": self.circuit_breakers[node].state.value
                }
                for node, metrics in self.request_metrics.items()
            }
        }
    
    def set_strategy(self, strategy: RoutingStrategy):
        """Change routing strategy
        
        Args:
            strategy: New routing strategy
        """
        self.strategy = strategy
        logger.info(f"Routing strategy changed to {strategy.value}")
    
    def reset_metrics(self):
        """Reset all metrics"""
        for node in self.nodes:
            self.request_metrics[node] = RequestMetrics(node_id=node)
        self.request_counter = 0
    
    def get_healthy_nodes(self) -> List[str]:
        """Get list of healthy nodes
        
        Returns:
            List of healthy node IDs
        """
        return [n for n in self.nodes if self.circuit_breakers[n].is_healthy()]
    
    def get_unhealthy_nodes(self) -> List[str]:
        """Get list of unhealthy nodes
        
        Returns:
            List of unhealthy node IDs
        """
        return [n for n in self.nodes if not self.circuit_breakers[n].is_healthy()]


class LoadBalancingPool:
    """Connection pool with load balancing"""
    
    def __init__(self, router: RequestRouter, max_connections: int = 100):
        """Initialize load balancing pool
        
        Args:
            router: RequestRouter instance
            max_connections: Maximum connections per node
        """
        self.router = router
        self.max_connections = max_connections
        self.active_connections: Dict[str, int] = defaultdict(int)
        self.waiting_requests: Dict[str, List] = defaultdict(list)
    
    async def acquire_connection(self, client_id: Optional[str] = None) -> Optional[str]:
        """Acquire connection from pool
        
        Args:
            client_id: Optional client ID for affinity
            
        Returns:
            Node ID or None
        """
        node = self.router.select_node(client_id)
        
        if not node:
            return None
        
        # Check connection limit
        if self.active_connections[node] >= self.max_connections:
            await asyncio.sleep(0.01)  # Wait briefly
            return await self.acquire_connection(client_id)
        
        self.active_connections[node] += 1
        return node
    
    def release_connection(self, node_id: str):
        """Release connection back to pool
        
        Args:
            node_id: Node ID
        """
        if self.active_connections[node_id] > 0:
            self.active_connections[node_id] -= 1
    
    def get_pool_stats(self) -> Dict:
        """Get pool statistics
        
        Returns:
            Statistics dictionary
        """
        return {
            "active_connections": dict(self.active_connections),
            "waiting_requests": {k: len(v) for k, v in self.waiting_requests.items()},
            "routing_stats": self.router.get_routing_stats()
        }
