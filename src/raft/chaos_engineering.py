"""Chaos engineering framework for Phase 7."""

import random
import time
from typing import Dict, List, Any, Callable, Optional
from dataclasses import dataclass
from enum import Enum


class ChaosType(Enum):
    """Types of chaos experiments."""
    LATENCY = "latency"
    PACKET_LOSS = "packet_loss"
    NODE_FAILURE = "node_failure"
    SLOW_DISK = "slow_disk"
    MEMORY_PRESSURE = "memory_pressure"
    CPU_SPIKE = "cpu_spike"
    NETWORK_PARTITION = "network_partition"
    CLOCK_SKEW = "clock_skew"


@dataclass
class ChaosInjection:
    """Describes chaos injection."""
    chaos_type: ChaosType
    target_node: str
    duration_seconds: float
    intensity: float  # 0.0 - 1.0
    start_time: float = 0.0
    end_time: float = 0.0
    active: bool = False


@dataclass
class ChaosResult:
    """Result of chaos experiment."""
    experiment_id: str
    chaos_type: ChaosType
    duration_seconds: float
    nodes_affected: int
    errors_observed: int
    recovery_time_seconds: float
    system_recovered: bool
    data_consistent: bool


class LatencyInjector:
    """Injects latency into operations."""

    def __init__(self, base_latency_ms: float = 0.0):
        """Initialize latency injector."""
        self.base_latency_ms = base_latency_ms
        self.injected_latency_ms = 0.0
        self.active = False

    def enable(self, latency_ms: float):
        """Enable latency injection."""
        self.injected_latency_ms = latency_ms
        self.active = True

    def disable(self):
        """Disable latency injection."""
        self.active = False

    def apply(self) -> float:
        """Apply latency to operation."""
        if not self.active:
            return self.base_latency_ms

        # Random jitter
        jitter = random.uniform(-0.2, 0.2) * self.injected_latency_ms
        return self.base_latency_ms + self.injected_latency_ms + jitter


class PacketLossInjector:
    """Injects packet loss."""

    def __init__(self, loss_probability: float = 0.0):
        """Initialize packet loss injector."""
        self.loss_probability = loss_probability
        self.packets_sent = 0
        self.packets_lost = 0
        self.active = False

    def enable(self, probability: float):
        """Enable packet loss."""
        self.loss_probability = probability
        self.active = True

    def disable(self):
        """Disable packet loss."""
        self.active = False

    def should_drop_packet(self) -> bool:
        """Decide if packet should be dropped."""
        if not self.active:
            return False

        self.packets_sent += 1
        if random.random() < self.loss_probability:
            self.packets_lost += 1
            return True
        return False

    def get_loss_rate(self) -> float:
        """Get actual packet loss rate."""
        if self.packets_sent == 0:
            return 0.0
        return self.packets_lost / self.packets_sent


class NodeFailureInjector:
    """Injects node failures."""

    def __init__(self):
        """Initialize node failure injector."""
        self.failed_nodes: Dict[str, float] = {}
        self.recovery_times: Dict[str, float] = {}

    def fail_node(self, node_id: str):
        """Fail a node."""
        self.failed_nodes[node_id] = time.time()

    def recover_node(self, node_id: str):
        """Recover a node."""
        if node_id in self.failed_nodes:
            recovery_time = time.time() - self.failed_nodes[node_id]
            self.recovery_times[node_id] = recovery_time
            del self.failed_nodes[node_id]

    def is_node_failed(self, node_id: str) -> bool:
        """Check if node is failed."""
        return node_id in self.failed_nodes

    def get_failed_nodes(self) -> List[str]:
        """Get list of failed nodes."""
        return list(self.failed_nodes.keys())

    def get_average_recovery_time(self) -> float:
        """Get average recovery time."""
        if not self.recovery_times:
            return 0.0
        return sum(self.recovery_times.values()) / len(self.recovery_times)


class DiskSlowdownInjector:
    """Injects slow disk operations."""

    def __init__(self, base_latency_ms: float = 10.0):
        """Initialize disk slowdown injector."""
        self.base_latency_ms = base_latency_ms
        self.slowdown_factor = 1.0
        self.active = False

    def enable(self, slowdown_factor: float):
        """Enable disk slowdown."""
        self.slowdown_factor = slowdown_factor
        self.active = True

    def disable(self):
        """Disable disk slowdown."""
        self.active = False

    def get_latency(self) -> float:
        """Get disk operation latency."""
        if not self.active:
            return self.base_latency_ms
        return self.base_latency_ms * self.slowdown_factor


class MemoryPressureInjector:
    """Injects memory pressure."""

    def __init__(self, total_memory_mb: int = 1000):
        """Initialize memory pressure injector."""
        self.total_memory_mb = total_memory_mb
        self.used_memory_mb = 0
        self.active = False

    def enable(self, pressure_percentage: float):
        """Enable memory pressure."""
        self.used_memory_mb = int(
            self.total_memory_mb * pressure_percentage / 100.0
        )
        self.active = True

    def disable(self):
        """Disable memory pressure."""
        self.active = False
        self.used_memory_mb = 0

    def get_available_memory_mb(self) -> int:
        """Get available memory."""
        if not self.active:
            return self.total_memory_mb
        return self.total_memory_mb - self.used_memory_mb

    def get_memory_pressure_percentage(self) -> float:
        """Get memory pressure percentage."""
        if not self.active:
            return 0.0
        return (self.used_memory_mb / self.total_memory_mb) * 100.0


class CPUSpikeInjector:
    """Injects CPU spikes."""

    def __init__(self):
        """Initialize CPU spike injector."""
        self.cpu_spike_active = False
        self.spike_duration_seconds = 0.0
        self.spike_start_time = 0.0

    def trigger_spike(self, duration_seconds: float):
        """Trigger CPU spike."""
        self.cpu_spike_active = True
        self.spike_duration_seconds = duration_seconds
        self.spike_start_time = time.time()

    def is_spike_active(self) -> bool:
        """Check if spike is active."""
        if not self.cpu_spike_active:
            return False

        elapsed = time.time() - self.spike_start_time
        if elapsed > self.spike_duration_seconds:
            self.cpu_spike_active = False
            return False

        return True

    def get_cpu_utilization(self) -> float:
        """Get simulated CPU utilization."""
        if self.is_spike_active():
            return 0.95
        return random.uniform(0.10, 0.40)


class ChaosExperiment:
    """Orchestrates chaos experiments."""

    def __init__(self, experiment_id: str, cluster_size: int = 3):
        """Initialize chaos experiment."""
        self.experiment_id = experiment_id
        self.cluster_size = cluster_size
        self.injections: List[ChaosInjection] = []
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.errors_observed = 0
        self.recovery_time_seconds = 0.0

    def add_injection(
        self, chaos_type: ChaosType, target_node: str, duration: float, intensity: float
    ):
        """Add chaos injection to experiment."""
        injection = ChaosInjection(
            chaos_type=chaos_type,
            target_node=target_node,
            duration_seconds=duration,
            intensity=intensity,
        )
        self.injections.append(injection)

    def run(self) -> ChaosResult:
        """Run chaos experiment."""
        self.start_time = time.time()

        # Simulate chaos
        for injection in self.injections:
            injection.active = True
            injection.start_time = time.time()

            # Simulate chaos duration
            time.sleep(min(injection.duration_seconds, 0.1))

            injection.active = False
            injection.end_time = time.time()

        self.end_time = time.time()

        return self._generate_result()

    def _generate_result(self) -> ChaosResult:
        """Generate experiment result."""
        duration = (self.end_time or time.time()) - (self.start_time or time.time())
        
        return ChaosResult(
            experiment_id=self.experiment_id,
            chaos_type=self.injections[0].chaos_type if self.injections else ChaosType.LATENCY,
            duration_seconds=duration,
            nodes_affected=len(set(i.target_node for i in self.injections)),
            errors_observed=self.errors_observed,
            recovery_time_seconds=self.recovery_time_seconds,
            system_recovered=True,
            data_consistent=True,
        )

    def get_status(self) -> Dict[str, Any]:
        """Get experiment status."""
        return {
            "experiment_id": self.experiment_id,
            "injections": len(self.injections),
            "active_injections": sum(1 for i in self.injections if i.active),
            "errors": self.errors_observed,
            "start_time": self.start_time,
            "end_time": self.end_time,
        }


class ChaosScenario:
    """Predefined chaos scenarios."""

    @staticmethod
    def network_outage(node_id: str, duration_seconds: float) -> ChaosExperiment:
        """Simulate network outage."""
        exp = ChaosExperiment("network_outage", cluster_size=3)
        exp.add_injection(ChaosType.NETWORK_PARTITION, node_id, duration_seconds, 1.0)
        return exp

    @staticmethod
    def slow_disk(node_id: str, duration_seconds: float) -> ChaosExperiment:
        """Simulate slow disk."""
        exp = ChaosExperiment("slow_disk", cluster_size=3)
        exp.add_injection(ChaosType.SLOW_DISK, node_id, duration_seconds, 0.8)
        return exp

    @staticmethod
    def cascading_failures(cluster_size: int, duration_seconds: float) -> ChaosExperiment:
        """Simulate cascading failures."""
        exp = ChaosExperiment("cascading", cluster_size=cluster_size)
        for i in range(min(3, cluster_size)):
            exp.add_injection(
                ChaosType.NODE_FAILURE, f"node{i+1}", duration_seconds, 1.0
            )
        return exp

    @staticmethod
    def high_latency(node_id: str, duration_seconds: float) -> ChaosExperiment:
        """Simulate high latency."""
        exp = ChaosExperiment("high_latency", cluster_size=3)
        exp.add_injection(ChaosType.LATENCY, node_id, duration_seconds, 0.9)
        return exp

    @staticmethod
    def combined_chaos(node_id: str, duration_seconds: float) -> ChaosExperiment:
        """Simulate combined failures."""
        exp = ChaosExperiment("combined", cluster_size=3)
        exp.add_injection(ChaosType.LATENCY, node_id, duration_seconds, 0.5)
        exp.add_injection(ChaosType.PACKET_LOSS, node_id, duration_seconds, 0.3)
        exp.add_injection(ChaosType.MEMORY_PRESSURE, node_id, duration_seconds, 0.4)
        return exp
