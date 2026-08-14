"""
Tests for advanced request routing & load balancing

Covers:
- Routing strategies (Round-robin, Least-loaded, Latency-aware, etc.)
- Circuit breaker pattern
- Request metrics tracking
- Load calculation
- Connection pooling
- Session affinity
"""

import pytest
import asyncio
import time
from src.raft.advanced_request_routing import (
    RequestRouter, RoutingStrategy, CircuitBreaker, CircuitState,
    RequestMetrics, LoadBalancingPool
)


class TestRequestMetrics:
    """Test RequestMetrics class"""
    
    def test_create_metrics(self):
        """Test creating request metrics"""
        metrics = RequestMetrics(node_id="node_1")
        assert metrics.node_id == "node_1"
        assert metrics.total_requests == 0
        assert metrics.successful_requests == 0
    
    def test_success_rate_calculation(self):
        """Test success rate calculation"""
        metrics = RequestMetrics(node_id="node_1")
        metrics.total_requests = 10
        metrics.successful_requests = 8
        assert metrics.get_success_rate() == 80.0
    
    def test_error_rate_update(self):
        """Test error rate update"""
        metrics = RequestMetrics(node_id="node_1")
        metrics.total_requests = 10
        metrics.failed_requests = 2
        metrics.update_error_rate()
        assert metrics.error_rate == 20.0
    
    def test_error_rate_zero_requests(self):
        """Test error rate with zero requests"""
        metrics = RequestMetrics(node_id="node_1")
        metrics.update_error_rate()
        assert metrics.error_rate == 0.0


class TestCircuitBreaker:
    """Test CircuitBreaker class"""
    
    def test_initial_state_closed(self):
        """Test initial circuit breaker state"""
        cb = CircuitBreaker(node_id="node_1")
        assert cb.state == CircuitState.CLOSED
        assert cb.can_attempt_request()
    
    def test_failure_threshold(self):
        """Test failure threshold transition"""
        cb = CircuitBreaker(node_id="node_1", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert not cb.can_attempt_request()
    
    def test_half_open_recovery(self):
        """Test recovery from open to half-open"""
        cb = CircuitBreaker(node_id="node_1", failure_threshold=1, reset_timeout=0.1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        
        time.sleep(0.15)
        assert cb.can_attempt_request()
        assert cb.state == CircuitState.HALF_OPEN
    
    def test_half_open_success_closes(self):
        """Test success in half-open closes circuit"""
        cb = CircuitBreaker(
            node_id="node_1",
            failure_threshold=1,
            required_successes=2
        )
        cb.record_failure()
        cb.state = CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
    
    def test_is_healthy(self):
        """Test healthy status"""
        cb = CircuitBreaker(node_id="node_1")
        assert cb.is_healthy()
        cb.state = CircuitState.OPEN
        assert not cb.is_healthy()


class TestRequestRouter:
    """Test RequestRouter class"""
    
    @pytest.fixture
    def router(self):
        """Create router for testing"""
        return RequestRouter(["node_1", "node_2", "node_3"])
    
    def test_initialization(self, router):
        """Test router initialization"""
        assert len(router.nodes) == 3
        assert len(router.request_metrics) == 3
        assert len(router.circuit_breakers) == 3
    
    def test_round_robin_routing(self, router):
        """Test round-robin routing strategy"""
        router.set_strategy(RoutingStrategy.ROUND_ROBIN)
        selections = [router.select_node() for _ in range(9)]
        
        # Should distribute evenly
        assert selections.count("node_1") == 3
        assert selections.count("node_2") == 3
        assert selections.count("node_3") == 3
    
    def test_least_loaded_routing(self, router):
        """Test least-loaded routing"""
        router.set_strategy(RoutingStrategy.LEAST_LOADED)
        
        # Add load to node_1 and node_2
        router.request_metrics["node_1"].total_requests = 10
        router.request_metrics["node_2"].total_requests = 5
        router.request_metrics["node_3"].total_requests = 0
        
        # Should select least loaded
        selected = router.select_node()
        assert selected == "node_3"
    
    def test_latency_aware_routing(self, router):
        """Test latency-aware routing"""
        router.set_strategy(RoutingStrategy.LATENCY_AWARE)
        
        router.request_metrics["node_1"].avg_latency_ms = 100
        router.request_metrics["node_2"].avg_latency_ms = 50
        router.request_metrics["node_3"].avg_latency_ms = 200
        
        selected = router.select_node()
        assert selected == "node_2"
    
    def test_affinity_routing(self, router):
        """Test affinity routing"""
        router.set_strategy(RoutingStrategy.AFFINITY)
        
        # First request for client_1
        node1 = router.select_node(client_id="client_1")
        # Subsequent requests should go to same node
        node2 = router.select_node(client_id="client_1")
        
        assert node1 == node2
    
    def test_adaptive_routing(self, router):
        """Test adaptive routing strategy"""
        router.set_strategy(RoutingStrategy.ADAPTIVE)
        
        # Setup metrics
        router.request_metrics["node_1"].successful_requests = 90
        router.request_metrics["node_1"].total_requests = 100
        router.request_metrics["node_1"].avg_latency_ms = 10
        
        router.request_metrics["node_2"].successful_requests = 50
        router.request_metrics["node_2"].total_requests = 100
        router.request_metrics["node_2"].avg_latency_ms = 100
        
        # Should select best performing node
        selected = router.select_node()
        assert selected == "node_1"
    
    @pytest.mark.asyncio
    async def test_record_request_success(self, router):
        """Test recording successful request"""
        await router.record_request("node_1", success=True, latency_ms=50)
        
        metrics = router.request_metrics["node_1"]
        assert metrics.total_requests == 1
        assert metrics.successful_requests == 1
        assert metrics.failed_requests == 0
    
    @pytest.mark.asyncio
    async def test_record_request_failure(self, router):
        """Test recording failed request"""
        await router.record_request("node_1", success=False, latency_ms=100)
        
        metrics = router.request_metrics["node_1"]
        assert metrics.total_requests == 1
        assert metrics.successful_requests == 0
        assert metrics.failed_requests == 1
    
    @pytest.mark.asyncio
    async def test_latency_exponential_moving_average(self, router):
        """Test latency EMA calculation"""
        await router.record_request("node_1", success=True, latency_ms=100)
        assert router.request_metrics["node_1"].avg_latency_ms == 100
        
        await router.record_request("node_1", success=True, latency_ms=200)
        # EMA = 100 * 0.7 + 200 * 0.3 = 130
        assert abs(router.request_metrics["node_1"].avg_latency_ms - 130) < 1
    
    def test_circuit_breaker_protection(self, router):
        """Test circuit breaker prevents requests"""
        cb = router.circuit_breakers["node_1"]
        cb.failure_threshold = 1
        cb.record_failure()
        
        # Should not be selectable
        assert "node_1" not in router.get_healthy_nodes()
    
    def test_get_node_load(self, router):
        """Test load calculation"""
        router.request_metrics["node_1"].total_requests = 10
        router.request_metrics["node_2"].total_requests = 5
        router.request_metrics["node_3"].total_requests = 0
        
        loads = router.get_node_load()
        assert loads["node_1"] == 100  # Highest load
        assert loads["node_3"] == 0  # Lowest load
    
    def test_get_routing_stats(self, router):
        """Test routing statistics"""
        router.request_metrics["node_1"].total_requests = 10
        stats = router.get_routing_stats()
        
        assert "strategy" in stats
        assert "total_routes" in stats
        assert "nodes" in stats
    
    def test_healthy_nodes_tracking(self, router):
        """Test healthy nodes tracking"""
        assert len(router.get_healthy_nodes()) == 3
        
        router.circuit_breakers["node_1"].state = CircuitState.OPEN
        assert len(router.get_healthy_nodes()) == 2
        assert "node_1" not in router.get_healthy_nodes()
    
    def test_unhealthy_nodes_tracking(self, router):
        """Test unhealthy nodes tracking"""
        assert len(router.get_unhealthy_nodes()) == 0
        
        router.circuit_breakers["node_1"].state = CircuitState.OPEN
        assert len(router.get_unhealthy_nodes()) == 1
        assert "node_1" in router.get_unhealthy_nodes()


class TestLoadBalancingPool:
    """Test LoadBalancingPool class"""
    
    @pytest.fixture
    def pool(self):
        """Create pool for testing"""
        router = RequestRouter(["node_1", "node_2"])
        return LoadBalancingPool(router, max_connections=5)
    
    @pytest.mark.asyncio
    async def test_acquire_connection(self, pool):
        """Test acquiring connection"""
        node = await pool.acquire_connection()
        assert node in ["node_1", "node_2"]
        assert pool.active_connections[node] == 1
    
    @pytest.mark.asyncio
    async def test_acquire_multiple_connections(self, pool):
        """Test acquiring multiple connections"""
        nodes = []
        for _ in range(3):
            node = await pool.acquire_connection()
            nodes.append(node)
        
        assert sum(pool.active_connections.values()) == 3
    
    def test_release_connection(self, pool):
        """Test releasing connection"""
        pool.active_connections["node_1"] = 2
        pool.release_connection("node_1")
        assert pool.active_connections["node_1"] == 1
    
    def test_pool_statistics(self, pool):
        """Test pool statistics"""
        pool.active_connections["node_1"] = 3
        stats = pool.get_pool_stats()
        
        assert "active_connections" in stats
        assert stats["active_connections"]["node_1"] == 3


class TestRoutingScenarios:
    """Test complex routing scenarios"""
    
    @pytest.mark.asyncio
    async def test_gradual_node_degradation(self):
        """Test handling gradual node degradation"""
        router = RequestRouter(["node_1", "node_2", "node_3"])
        router.set_strategy(RoutingStrategy.ADAPTIVE)
        
        # Simulate gradual degradation of node_1
        for i in range(10):
            await router.record_request("node_1", success=(i < 2), latency_ms=50 + i*20)
            await router.record_request("node_2", success=True, latency_ms=10)
            await router.record_request("node_3", success=True, latency_ms=20)
        
        # Should prefer healthier nodes
        selected = router.select_node()
        assert selected != "node_1"
    
    @pytest.mark.asyncio
    async def test_multiple_strategy_switching(self):
        """Test switching between strategies"""
        router = RequestRouter(["node_1", "node_2"])
        
        router.set_strategy(RoutingStrategy.ROUND_ROBIN)
        node1 = router.select_node()
        
        router.set_strategy(RoutingStrategy.LEAST_LOADED)
        node2 = router.select_node()
        
        router.set_strategy(RoutingStrategy.LATENCY_AWARE)
        node3 = router.select_node()
        
        # All selections should be valid
        assert all(n in ["node_1", "node_2"] for n in [node1, node2, node3])
    
    @pytest.mark.asyncio
    async def test_recovery_from_circuit_open(self):
        """Test recovery from opened circuit"""
        router = RequestRouter(["node_1"])
        cb = router.circuit_breakers["node_1"]
        cb.failure_threshold = 2
        cb.reset_timeout = 0.05
        
        # Trigger circuit open
        await router.record_request("node_1", success=False, latency_ms=100)
        await router.record_request("node_1", success=False, latency_ms=100)
        
        assert cb.state == CircuitState.OPEN
        assert router.select_node() is None
        
        # Wait for reset
        await asyncio.sleep(0.1)
        
        # Should be in half-open
        node = router.select_node()
        assert node is not None
        
        # Record success
        await router.record_request("node_1", success=True, latency_ms=50)
        await router.record_request("node_1", success=True, latency_ms=50)
        
        assert cb.state == CircuitState.CLOSED
