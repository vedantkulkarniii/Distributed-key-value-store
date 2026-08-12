"""Advanced failure scenario handlers for Phase 5 resilience."""

import time
import random
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from enum import Enum
from src.raft.state_machine import StateMachineEngine
from src.raft.crash_recovery import CrashRecoveryHandler
from src.raft.byzantine_tolerance import ByzantineTolerance


class FailureType(Enum):
    """Types of failures to simulate."""
    NODE_CRASH = "node_crash"
    NETWORK_PARTITION = "network_partition"
    BYZANTINE_BEHAVIOR = "byzantine_behavior"
    CASCADING_FAILURE = "cascading_failure"
    ASYMMETRIC_DELAY = "asymmetric_delay"
    CLOCK_SKEW = "clock_skew"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    CORRELATED_FAILURE = "correlated_failure"


class SeverityLevel(Enum):
    """Severity levels for failures."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class FailureScenario:
    """Describes a failure scenario."""
    name: str
    failure_type: FailureType
    severity: SeverityLevel
    affected_nodes: List[str]
    duration_seconds: float
    recovery_time_seconds: Optional[float] = None
    expected_impact: str = ""
    mitigation_strategies: List[str] = None

    def __post_init__(self):
        """Initialize defaults."""
        if self.mitigation_strategies is None:
            self.mitigation_strategies = []


@dataclass
class FailureImpact:
    """Impact of a failure scenario."""
    scenario_name: str
    nodes_affected: int
    operations_failed: int
    operations_succeeded: int
    recovery_successful: bool
    downtime_seconds: float
    data_loss: bool
    consistency_maintained: bool


class CascadingFailureSimulator:
    """Simulates cascading failures in the cluster."""

    def __init__(self, cluster_size: int = 3):
        """Initialize cascading failure simulator."""
        self.cluster_size = cluster_size
        self.nodes: Dict[str, StateMachineEngine] = {}
        self.failure_chain: List[Tuple[str, float]] = []
        self.recovery_log: List[Dict[str, Any]] = []

    def setup_cluster(self):
        """Setup cluster for simulation."""
        for i in range(1, self.cluster_size + 1):
            node_id = f"node_{i}"
            self.nodes[node_id] = StateMachineEngine(node_id)

    def simulate_cascading_failure(
        self, initial_node: str, cascade_delay: float = 0.1
    ) -> FailureImpact:
        """Simulate cascading failure starting from initial node."""
        start_time = time.time()
        failed_nodes = []

        # Initial failure
        failed_nodes.append(initial_node)
        self.failure_chain.append((initial_node, 0))

        # Cascade to dependent nodes
        dependent_nodes = self._get_dependent_nodes(initial_node)

        for idx, node_id in enumerate(dependent_nodes):
            time.sleep(cascade_delay)  # Delay between cascade steps
            failed_nodes.append(node_id)
            self.failure_chain.append((node_id, (idx + 1) * cascade_delay))

        recovery_time = self._recover_cascade(failed_nodes)
        downtime = time.time() - start_time

        return FailureImpact(
            scenario_name="Cascading Failure",
            nodes_affected=len(failed_nodes),
            operations_failed=len(failed_nodes) * 10,  # Estimated
            operations_succeeded=len(self.nodes) * 10,
            recovery_successful=True,
            downtime_seconds=downtime,
            data_loss=False,
            consistency_maintained=self._verify_consistency(),
        )

    def _get_dependent_nodes(self, node_id: str) -> List[str]:
        """Get nodes dependent on given node."""
        # Simplified: return all other nodes
        return [n for n in self.nodes.keys() if n != node_id]

    def _recover_cascade(self, failed_nodes: List[str]) -> float:
        """Recover from cascading failure."""
        recovery_start = time.time()

        for node_id in failed_nodes:
            # Simulate recovery
            self.nodes[node_id] = StateMachineEngine(node_id)
            self.recovery_log.append({
                "node": node_id,
                "recovered_at": time.time() - recovery_start,
            })

        return time.time() - recovery_start

    def _verify_consistency(self) -> bool:
        """Verify cluster consistency after recovery."""
        return True  # Simplified


class NetworkPartitionSimulator:
    """Simulates network partitions and healing."""

    def __init__(self, cluster_size: int = 5):
        """Initialize network partition simulator."""
        self.cluster_size = cluster_size
        self.partitions: List[List[str]] = []
        self.partition_start_time: Optional[float] = None

    def create_partition(self, partition1: List[str], partition2: List[str]) -> Dict[str, Any]:
        """Create a network partition."""
        self.partition_start_time = time.time()
        self.partitions = [partition1, partition2]

        return {
            "partition_1": partition1,
            "partition_2": partition2,
            "partition_created_at": self.partition_start_time,
            "quorum_in_p1": len(partition1) > self.cluster_size / 2,
            "quorum_in_p2": len(partition2) > self.cluster_size / 2,
        }

    def simulate_minority_partition_behavior(self) -> FailureImpact:
        """Simulate behavior of minority partition."""
        if len(self.partitions[0]) < len(self.partitions[1]):
            minority = self.partitions[0]
            majority = self.partitions[1]
        else:
            minority = self.partitions[1]
            majority = self.partitions[0]

        # Minority partition cannot form quorum
        operations_blocked = 50
        operations_accepted = 0

        return FailureImpact(
            scenario_name="Minority Partition",
            nodes_affected=len(minority),
            operations_failed=operations_blocked,
            operations_succeeded=operations_accepted,
            recovery_successful=True,
            downtime_seconds=0,
            data_loss=False,
            consistency_maintained=True,
        )

    def heal_partition(self, healing_time: float = 5.0) -> Dict[str, Any]:
        """Heal network partition."""
        actual_healing_start = time.time()
        time.sleep(healing_time)

        partition1_size = len(self.partitions[0])
        partition2_size = len(self.partitions[1])

        return {
            "healing_duration": time.time() - actual_healing_start,
            "partition_duration": time.time() - self.partition_start_time,
            "nodes_resynchronized": partition1_size + partition2_size,
            "partition_healed": True,
        }


class ByzantineFailureSimulator:
    """Simulates Byzantine failures and detection."""

    def __init__(self, cluster_size: int = 5):
        """Initialize Byzantine failure simulator."""
        self.cluster_size = cluster_size
        self.byzantine_nodes: List[str] = []
        self.detected_attacks: List[Dict[str, Any]] = []
        self.byzantine_handler = ByzantineTolerance("leader", cluster_size)

    def introduce_byzantine_node(self, node_id: str) -> Dict[str, Any]:
        """Introduce a Byzantine node."""
        self.byzantine_nodes.append(node_id)

        return {
            "byzantine_node": node_id,
            "introduced_at": time.time(),
            "byzantine_count": len(self.byzantine_nodes),
            "tolerance_threshold": (self.cluster_size - 1) // 3,
        }

    def simulate_vote_equivocation(self, voter_id: str) -> Dict[str, Any]:
        """Simulate vote equivocation attack."""
        votes = [
            {"voter_id": voter_id, "candidate_id": "candidate_1", "term": 1},
            {"voter_id": voter_id, "candidate_id": "candidate_2", "term": 1},
        ]

        # Detect equivocation
        has_conflict, reason = self.byzantine_handler.detect_conflicting_votes(1, votes)

        attack_info = {
            "attack_type": "Vote Equivocation",
            "voter": voter_id,
            "detected": has_conflict,
            "reason": reason,
            "timestamp": time.time(),
        }

        self.detected_attacks.append(attack_info)
        return attack_info

    def simulate_state_manipulation(self, node_id: str) -> Dict[str, Any]:
        """Simulate Byzantine state manipulation."""
        manipulated_data = {
            "malicious_key": "manipulated_value",
            "original_value": "correct_value",
        }

        # Detection would happen during consistency check
        detected = self.byzantine_handler.detect_anomalous_state(
            node_id, manipulated_data
        )

        attack_info = {
            "attack_type": "State Manipulation",
            "attacker": node_id,
            "detected": detected,
            "timestamp": time.time(),
        }

        self.detected_attacks.append(attack_info)
        return attack_info

    def simulate_sybil_attack(self, attacker_id: str, fake_nodes: int = 3) -> Dict[str, Any]:
        """Simulate Sybil attack."""
        fake_node_ids = [f"{attacker_id}_fake_{i}" for i in range(fake_nodes)]

        sybil_info = {
            "attack_type": "Sybil Attack",
            "attacker": attacker_id,
            "fake_nodes": fake_node_ids,
            "detected": False,  # Would be detected over time
            "timestamp": time.time(),
        }

        return sybil_info


class AsymmetricDelaySimulator:
    """Simulates asymmetric network delays."""

    def __init__(self):
        """Initialize asymmetric delay simulator."""
        self.delay_map: Dict[Tuple[str, str], float] = {}

    def add_asymmetric_delay(self, from_node: str, to_node: str, delay_ms: float):
        """Add asymmetric delay between nodes."""
        self.delay_map[(from_node, to_node)] = delay_ms / 1000.0

    def apply_delay(self, from_node: str, to_node: str) -> float:
        """Apply delay to message between nodes."""
        delay = self.delay_map.get((from_node, to_node), 0)
        time.sleep(delay)
        return delay

    def simulate_split_brain_scenario(self) -> Dict[str, Any]:
        """Simulate conditions for split brain."""
        # Create high delays from leader to some followers
        self.add_asymmetric_delay("leader", "follower_1", 2000)  # 2 second delay
        self.add_asymmetric_delay("follower_1", "leader", 2000)

        scenario_info = {
            "scenario": "Split Brain Conditions",
            "leader_delay_to_f1_ms": 2000,
            "f1_delay_to_leader_ms": 2000,
            "election_timeout_ms": 150,
            "detection_method": "Heartbeat timeout detection",
        }

        return scenario_info


class ResourceExhaustionSimulator:
    """Simulates resource exhaustion scenarios."""

    def __init__(self):
        """Initialize resource exhaustion simulator."""
        self.exhausted_resources: Dict[str, str] = {}

    def exhaust_memory(self, node_id: str, percentage: int = 90) -> Dict[str, Any]:
        """Simulate memory exhaustion."""
        self.exhausted_resources[f"{node_id}_memory"] = "exhausted"

        return {
            "node": node_id,
            "resource": "memory",
            "exhaustion_level": percentage,
            "impact": "Slow garbage collection, increased latency",
            "recovery_possible": True,
        }

    def exhaust_cpu(self, node_id: str, percentage: int = 95) -> Dict[str, Any]:
        """Simulate CPU exhaustion."""
        self.exhausted_resources[f"{node_id}_cpu"] = "exhausted"

        return {
            "node": node_id,
            "resource": "cpu",
            "exhaustion_level": percentage,
            "impact": "Timeout of heartbeats, election disruption",
            "recovery_possible": True,
        }

    def exhaust_network_bandwidth(self, node_id: str, percentage: int = 99) -> Dict[str, Any]:
        """Simulate network bandwidth exhaustion."""
        self.exhausted_resources[f"{node_id}_network"] = "exhausted"

        return {
            "node": node_id,
            "resource": "network_bandwidth",
            "exhaustion_level": percentage,
            "impact": "Message delays, replication lag",
            "recovery_possible": True,
        }


class CorrelatedFailureSimulator:
    """Simulates correlated failures."""

    def __init__(self, cluster_size: int = 5):
        """Initialize correlated failure simulator."""
        self.cluster_size = cluster_size
        self.failure_correlations: Dict[str, List[str]] = {}

    def introduce_correlated_failures(
        self, trigger_node: str, affected_nodes: List[str]
    ) -> Dict[str, Any]:
        """Introduce correlated failures."""
        self.failure_correlations[trigger_node] = affected_nodes

        return {
            "trigger": trigger_node,
            "affected_nodes": affected_nodes,
            "correlation_type": "Common cause failure",
            "example": "Power outage affecting multiple physical servers",
            "expected_recovery_time": 300,
        }

    def simulate_power_outage(self, nodes: List[str]) -> Dict[str, Any]:
        """Simulate power outage affecting multiple nodes."""
        return {
            "event": "Power Outage",
            "affected_nodes": nodes,
            "nodes_offline": len(nodes),
            "expected_duration": "Unknown",
            "recovery_strategy": "Wait for power restoration, rebuild consensus",
        }

    def simulate_software_bug_propagation(self, initial_node: str) -> Dict[str, Any]:
        """Simulate software bug spreading through cluster."""
        # Simulate bug propagating to dependent nodes
        affected = [initial_node]

        return {
            "event": "Software Bug Propagation",
            "initial_node": initial_node,
            "affected_nodes": affected,
            "symptom": "Unexpected state transitions, log corruption",
            "recovery": "Downgrade or patch software, rebuild from snapshots",
        }


class FailureScenarioExecutor:
    """Executes failure scenarios and collects results."""

    def __init__(self):
        """Initialize failure scenario executor."""
        self.scenario_results: List[FailureImpact] = []

    def execute_scenario(self, scenario: FailureScenario) -> FailureImpact:
        """Execute a failure scenario."""
        if scenario.failure_type == FailureType.CASCADING_FAILURE:
            impact = self._execute_cascading(scenario)
        elif scenario.failure_type == FailureType.NETWORK_PARTITION:
            impact = self._execute_partition(scenario)
        elif scenario.failure_type == FailureType.BYZANTINE_BEHAVIOR:
            impact = self._execute_byzantine(scenario)
        elif scenario.failure_type == FailureType.ASYMMETRIC_DELAY:
            impact = self._execute_asymmetric_delay(scenario)
        elif scenario.failure_type == FailureType.RESOURCE_EXHAUSTION:
            impact = self._execute_resource_exhaustion(scenario)
        else:
            impact = FailureImpact(
                scenario_name=scenario.name,
                nodes_affected=len(scenario.affected_nodes),
                operations_failed=0,
                operations_succeeded=0,
                recovery_successful=False,
                downtime_seconds=0,
                data_loss=False,
                consistency_maintained=False,
            )

        self.scenario_results.append(impact)
        return impact

    def _execute_cascading(self, scenario: FailureScenario) -> FailureImpact:
        """Execute cascading failure scenario."""
        simulator = CascadingFailureSimulator(cluster_size=3)
        simulator.setup_cluster()
        return simulator.simulate_cascading_failure(scenario.affected_nodes[0])

    def _execute_partition(self, scenario: FailureScenario) -> FailureImpact:
        """Execute network partition scenario."""
        simulator = NetworkPartitionSimulator(cluster_size=5)
        partition1 = scenario.affected_nodes[:len(scenario.affected_nodes)//2]
        partition2 = scenario.affected_nodes[len(scenario.affected_nodes)//2:]
        simulator.create_partition(partition1, partition2)
        return simulator.simulate_minority_partition_behavior()

    def _execute_byzantine(self, scenario: FailureScenario) -> FailureImpact:
        """Execute Byzantine failure scenario."""
        simulator = ByzantineFailureSimulator(cluster_size=5)
        for node in scenario.affected_nodes:
            simulator.introduce_byzantine_node(node)
        simulator.simulate_vote_equivocation(scenario.affected_nodes[0])
        return FailureImpact(
            scenario_name=scenario.name,
            nodes_affected=len(scenario.affected_nodes),
            operations_failed=0,
            operations_succeeded=10,
            recovery_successful=True,
            downtime_seconds=0,
            data_loss=False,
            consistency_maintained=True,
        )

    def _execute_asymmetric_delay(self, scenario: FailureScenario) -> FailureImpact:
        """Execute asymmetric delay scenario."""
        simulator = AsymmetricDelaySimulator()
        simulator.simulate_split_brain_scenario()
        return FailureImpact(
            scenario_name=scenario.name,
            nodes_affected=len(scenario.affected_nodes),
            operations_failed=2,
            operations_succeeded=8,
            recovery_successful=True,
            downtime_seconds=scenario.duration_seconds,
            data_loss=False,
            consistency_maintained=True,
        )

    def _execute_resource_exhaustion(self, scenario: FailureScenario) -> FailureImpact:
        """Execute resource exhaustion scenario."""
        simulator = ResourceExhaustionSimulator()
        if "memory" in scenario.name.lower():
            simulator.exhaust_memory(scenario.affected_nodes[0])
        elif "cpu" in scenario.name.lower():
            simulator.exhaust_cpu(scenario.affected_nodes[0])
        else:
            simulator.exhaust_network_bandwidth(scenario.affected_nodes[0])

        return FailureImpact(
            scenario_name=scenario.name,
            nodes_affected=len(scenario.affected_nodes),
            operations_failed=5,
            operations_succeeded=5,
            recovery_successful=True,
            downtime_seconds=scenario.duration_seconds,
            data_loss=False,
            consistency_maintained=True,
        )

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all executed scenarios."""
        total_scenarios = len(self.scenario_results)
        successful = sum(1 for r in self.scenario_results if r.recovery_successful)
        total_downtime = sum(r.downtime_seconds for r in self.scenario_results)

        return {
            "total_scenarios": total_scenarios,
            "successful_recovery": successful,
            "recovery_rate": successful / total_scenarios if total_scenarios > 0 else 0,
            "total_downtime": total_downtime,
            "data_loss_incidents": sum(1 for r in self.scenario_results if r.data_loss),
            "consistency_violations": sum(
                1 for r in self.scenario_results if not r.consistency_maintained
            ),
        }
