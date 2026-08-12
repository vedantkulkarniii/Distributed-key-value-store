"""Advanced failure scenario tests for Phase 5 resilience."""

import pytest
from src.raft.advanced_failure_scenarios import (
    FailureScenario,
    FailureType,
    SeverityLevel,
    FailureImpact,
    CascadingFailureSimulator,
    NetworkPartitionSimulator,
    ByzantineFailureSimulator,
    AsymmetricDelaySimulator,
    ResourceExhaustionSimulator,
    CorrelatedFailureSimulator,
    FailureScenarioExecutor,
)


class TestFailureScenarioClass:
    """Tests for FailureScenario class."""

    def test_create_failure_scenario(self):
        """Test creating a failure scenario."""
        scenario = FailureScenario(
            name="Node Crash",
            failure_type=FailureType.NODE_CRASH,
            severity=SeverityLevel.HIGH,
            affected_nodes=["node_1"],
            duration_seconds=10.0,
        )

        assert scenario.name == "Node Crash"
        assert scenario.severity == SeverityLevel.HIGH
        assert "node_1" in scenario.affected_nodes

    def test_failure_scenario_with_recovery_time(self):
        """Test failure scenario with recovery time."""
        scenario = FailureScenario(
            name="Network Partition",
            failure_type=FailureType.NETWORK_PARTITION,
            severity=SeverityLevel.CRITICAL,
            affected_nodes=["node_1", "node_2"],
            duration_seconds=30.0,
            recovery_time_seconds=5.0,
        )

        assert scenario.recovery_time_seconds == 5.0
        assert scenario.severity == SeverityLevel.CRITICAL


class TestCascadingFailureSimulator:
    """Tests for cascading failure scenarios."""

    def test_cascading_failure_setup(self):
        """Test cascading failure simulator setup."""
        simulator = CascadingFailureSimulator(cluster_size=3)
        simulator.setup_cluster()

        assert len(simulator.nodes) == 3

    def test_simulate_cascading_failure(self):
        """Test simulating cascading failure."""
        simulator = CascadingFailureSimulator(cluster_size=3)
        simulator.setup_cluster()

        impact = simulator.simulate_cascading_failure("node_1", cascade_delay=0.01)

        assert impact.scenario_name == "Cascading Failure"
        assert impact.nodes_affected >= 1
        assert impact.recovery_successful is True

    def test_cascading_failure_chain(self):
        """Test cascading failure chain tracking."""
        simulator = CascadingFailureSimulator(cluster_size=3)
        simulator.setup_cluster()

        simulator.simulate_cascading_failure("node_1", cascade_delay=0.01)

        assert len(simulator.failure_chain) > 0
        assert simulator.failure_chain[0][0] == "node_1"

    def test_cascading_failure_recovery_log(self):
        """Test cascading failure recovery logging."""
        simulator = CascadingFailureSimulator(cluster_size=3)
        simulator.setup_cluster()

        simulator.simulate_cascading_failure("node_1", cascade_delay=0.01)

        assert len(simulator.recovery_log) > 0
        for entry in simulator.recovery_log:
            assert "node" in entry
            assert "recovered_at" in entry


class TestNetworkPartitionSimulator:
    """Tests for network partition scenarios."""

    def test_create_partition(self):
        """Test creating network partition."""
        simulator = NetworkPartitionSimulator(cluster_size=5)
        result = simulator.create_partition(
            ["node_1", "node_2"], ["node_3", "node_4", "node_5"]
        )

        assert result["partition_1"] == ["node_1", "node_2"]
        assert result["partition_2"] == ["node_3", "node_4", "node_5"]

    def test_partition_quorum_calculation(self):
        """Test quorum calculation during partition."""
        simulator = NetworkPartitionSimulator(cluster_size=5)
        result = simulator.create_partition(
            ["node_1"], ["node_2", "node_3", "node_4", "node_5"]
        )

        # Minority partition cannot form quorum
        assert result["quorum_in_p1"] is False
        # Majority partition can form quorum
        assert result["quorum_in_p2"] is True

    def test_minority_partition_behavior(self):
        """Test behavior during minority partition."""
        simulator = NetworkPartitionSimulator(cluster_size=5)
        simulator.create_partition(
            ["node_1", "node_2"], ["node_3", "node_4", "node_5"]
        )

        impact = simulator.simulate_minority_partition_behavior()

        assert impact.nodes_affected == 2
        assert impact.operations_failed > 0
        assert impact.operations_succeeded == 0

    def test_partition_healing(self):
        """Test partition healing."""
        simulator = NetworkPartitionSimulator(cluster_size=5)
        simulator.create_partition(
            ["node_1", "node_2"], ["node_3", "node_4", "node_5"]
        )

        heal_result = simulator.heal_partition(healing_time=0.1)

        assert heal_result["partition_healed"] is True
        assert heal_result["nodes_resynchronized"] == 5


class TestByzantineFailureSimulator:
    """Tests for Byzantine failure scenarios."""

    def test_introduce_byzantine_node(self):
        """Test introducing Byzantine node."""
        simulator = ByzantineFailureSimulator(cluster_size=5)
        result = simulator.introduce_byzantine_node("node_2")

        assert "node_2" in simulator.byzantine_nodes
        assert result["byzantine_node"] == "node_2"

    def test_vote_equivocation_detection(self):
        """Test vote equivocation detection."""
        simulator = ByzantineFailureSimulator(cluster_size=5)
        result = simulator.simulate_vote_equivocation("node_2")

        assert result["attack_type"] == "Vote Equivocation"
        assert result["detected"] is True

    def test_state_manipulation_detection(self):
        """Test state manipulation detection."""
        simulator = ByzantineFailureSimulator(cluster_size=5)
        result = simulator.simulate_state_manipulation("node_2")

        assert result["attack_type"] == "State Manipulation"
        assert result["timestamp"] is not None

    def test_sybil_attack_simulation(self):
        """Test Sybil attack simulation."""
        simulator = ByzantineFailureSimulator(cluster_size=5)
        result = simulator.simulate_sybil_attack("attacker", fake_nodes=3)

        assert result["attack_type"] == "Sybil Attack"
        assert len(result["fake_nodes"]) == 3

    def test_byzantine_tolerance_threshold(self):
        """Test Byzantine tolerance threshold."""
        simulator = ByzantineFailureSimulator(cluster_size=7)
        # For 7 nodes, can tolerate 2 Byzantine nodes
        tolerance = (simulator.cluster_size - 1) // 3
        assert tolerance == 2


class TestAsymmetricDelaySimulator:
    """Tests for asymmetric delay scenarios."""

    def test_add_asymmetric_delay(self):
        """Test adding asymmetric delay."""
        simulator = AsymmetricDelaySimulator()
        simulator.add_asymmetric_delay("node_1", "node_2", 100)

        assert ("node_1", "node_2") in simulator.delay_map
        assert simulator.delay_map[("node_1", "node_2")] == 0.1

    def test_delay_asymmetry(self):
        """Test delay asymmetry."""
        simulator = AsymmetricDelaySimulator()
        simulator.add_asymmetric_delay("node_1", "node_2", 100)
        simulator.add_asymmetric_delay("node_2", "node_1", 50)

        delay_12 = simulator.delay_map[("node_1", "node_2")]
        delay_21 = simulator.delay_map[("node_2", "node_1")]

        assert delay_12 != delay_21
        assert delay_12 > delay_21

    def test_split_brain_scenario(self):
        """Test split brain scenario."""
        simulator = AsymmetricDelaySimulator()
        result = simulator.simulate_split_brain_scenario()

        assert result["scenario"] == "Split Brain Conditions"
        assert result["leader_delay_to_f1_ms"] == 2000


class TestResourceExhaustionSimulator:
    """Tests for resource exhaustion scenarios."""

    def test_exhaust_memory(self):
        """Test memory exhaustion."""
        simulator = ResourceExhaustionSimulator()
        result = simulator.exhaust_memory("node_1", percentage=90)

        assert result["resource"] == "memory"
        assert result["exhaustion_level"] == 90
        assert result["recovery_possible"] is True

    def test_exhaust_cpu(self):
        """Test CPU exhaustion."""
        simulator = ResourceExhaustionSimulator()
        result = simulator.exhaust_cpu("node_2", percentage=95)

        assert result["resource"] == "cpu"
        assert result["exhaustion_level"] == 95
        assert "timeout" in result["impact"].lower()

    def test_exhaust_network_bandwidth(self):
        """Test network bandwidth exhaustion."""
        simulator = ResourceExhaustionSimulator()
        result = simulator.exhaust_network_bandwidth("node_3", percentage=99)

        assert result["resource"] == "network_bandwidth"
        assert result["exhaustion_level"] == 99
        assert "replication" in result["impact"].lower()

    def test_resource_exhaustion_tracking(self):
        """Test tracking exhausted resources."""
        simulator = ResourceExhaustionSimulator()
        simulator.exhaust_memory("node_1", 90)
        simulator.exhaust_cpu("node_2", 95)

        assert len(simulator.exhausted_resources) == 2


class TestCorrelatedFailureSimulator:
    """Tests for correlated failure scenarios."""

    def test_introduce_correlated_failures(self):
        """Test introducing correlated failures."""
        simulator = CorrelatedFailureSimulator(cluster_size=5)
        result = simulator.introduce_correlated_failures(
            "trigger", ["node_1", "node_2", "node_3"]
        )

        assert result["trigger"] == "trigger"
        assert len(result["affected_nodes"]) == 3

    def test_power_outage_simulation(self):
        """Test power outage simulation."""
        simulator = CorrelatedFailureSimulator(cluster_size=5)
        result = simulator.simulate_power_outage(["node_1", "node_2"])

        assert result["event"] == "Power Outage"
        assert result["nodes_offline"] == 2

    def test_software_bug_propagation(self):
        """Test software bug propagation."""
        simulator = CorrelatedFailureSimulator(cluster_size=5)
        result = simulator.simulate_software_bug_propagation("node_1")

        assert result["event"] == "Software Bug Propagation"
        assert "node_1" in result["affected_nodes"]


class TestFailureScenarioExecutor:
    """Tests for failure scenario execution."""

    def test_executor_initialization(self):
        """Test executor initialization."""
        executor = FailureScenarioExecutor()
        assert len(executor.scenario_results) == 0

    def test_execute_cascading_scenario(self):
        """Test executing cascading failure scenario."""
        executor = FailureScenarioExecutor()
        scenario = FailureScenario(
            name="Cascading Failure",
            failure_type=FailureType.CASCADING_FAILURE,
            severity=SeverityLevel.CRITICAL,
            affected_nodes=["node_1"],
            duration_seconds=10.0,
        )

        impact = executor.execute_scenario(scenario)

        assert impact.scenario_name == "Cascading Failure"
        assert len(executor.scenario_results) == 1

    def test_execute_partition_scenario(self):
        """Test executing network partition scenario."""
        executor = FailureScenarioExecutor()
        scenario = FailureScenario(
            name="Network Partition",
            failure_type=FailureType.NETWORK_PARTITION,
            severity=SeverityLevel.HIGH,
            affected_nodes=["node_1", "node_2", "node_3"],
            duration_seconds=30.0,
        )

        impact = executor.execute_scenario(scenario)

        assert impact.scenario_name == "Network Partition"

    def test_execute_byzantine_scenario(self):
        """Test executing Byzantine failure scenario."""
        executor = FailureScenarioExecutor()
        scenario = FailureScenario(
            name="Byzantine Attack",
            failure_type=FailureType.BYZANTINE_BEHAVIOR,
            severity=SeverityLevel.HIGH,
            affected_nodes=["node_1"],
            duration_seconds=5.0,
        )

        impact = executor.execute_scenario(scenario)

        assert impact.scenario_name == "Byzantine Attack"
        assert impact.recovery_successful is True

    def test_execute_multiple_scenarios(self):
        """Test executing multiple scenarios."""
        executor = FailureScenarioExecutor()

        scenarios = [
            FailureScenario(
                name="Cascading Failure",
                failure_type=FailureType.CASCADING_FAILURE,
                severity=SeverityLevel.CRITICAL,
                affected_nodes=["node_1"],
                duration_seconds=10.0,
            ),
            FailureScenario(
                name="Network Partition",
                failure_type=FailureType.NETWORK_PARTITION,
                severity=SeverityLevel.HIGH,
                affected_nodes=["node_1", "node_2"],
                duration_seconds=30.0,
            ),
        ]

        for scenario in scenarios:
            executor.execute_scenario(scenario)

        assert len(executor.scenario_results) == 2

    def test_executor_summary(self):
        """Test executor summary generation."""
        executor = FailureScenarioExecutor()

        scenarios = [
            FailureScenario(
                name="Test 1",
                failure_type=FailureType.CASCADING_FAILURE,
                severity=SeverityLevel.HIGH,
                affected_nodes=["node_1"],
                duration_seconds=10.0,
            ),
            FailureScenario(
                name="Test 2",
                failure_type=FailureType.NETWORK_PARTITION,
                severity=SeverityLevel.HIGH,
                affected_nodes=["node_1", "node_2"],
                duration_seconds=30.0,
            ),
        ]

        for scenario in scenarios:
            executor.execute_scenario(scenario)

        summary = executor.get_summary()

        assert summary["total_scenarios"] == 2
        assert summary["successful_recovery"] >= 0
        assert 0 <= summary["recovery_rate"] <= 1.0


class TestFailureScenarioEdgeCases:
    """Tests for edge cases in failure scenarios."""

    def test_single_node_cascade(self):
        """Test cascading failure on single node."""
        simulator = CascadingFailureSimulator(cluster_size=1)
        simulator.setup_cluster()

        impact = simulator.simulate_cascading_failure("node_1", cascade_delay=0.01)

        assert impact.nodes_affected >= 1

    def test_even_partition(self):
        """Test even partition (unusual for Raft)."""
        simulator = NetworkPartitionSimulator(cluster_size=4)
        # Even partition - neither has quorum
        result = simulator.create_partition(["node_1", "node_2"], ["node_3", "node_4"])

        # Neither partition has quorum with even split
        assert result["quorum_in_p1"] is False
        assert result["quorum_in_p2"] is False

    def test_all_byzantine_nodes(self):
        """Test scenario with multiple Byzantine nodes."""
        simulator = ByzantineFailureSimulator(cluster_size=5)

        for i in range(1, 4):
            simulator.introduce_byzantine_node(f"node_{i}")

        assert len(simulator.byzantine_nodes) == 3

    def test_asymmetric_zero_delay(self):
        """Test asymmetric delay with zero delay."""
        simulator = AsymmetricDelaySimulator()
        simulator.add_asymmetric_delay("node_1", "node_2", 0)

        assert simulator.delay_map[("node_1", "node_2")] == 0.0

    def test_resource_exhaustion_multiple_resources(self):
        """Test exhausting multiple resources."""
        simulator = ResourceExhaustionSimulator()

        simulator.exhaust_memory("node_1")
        simulator.exhaust_cpu("node_1")
        simulator.exhaust_network_bandwidth("node_1")

        assert len(simulator.exhausted_resources) == 3


class TestFailureScenarioConsistency:
    """Tests for consistency during failures."""

    def test_cascading_failure_consistency(self):
        """Test consistency during cascading failure."""
        simulator = CascadingFailureSimulator(cluster_size=3)
        simulator.setup_cluster()

        impact = simulator.simulate_cascading_failure("node_1", cascade_delay=0.01)

        assert impact.consistency_maintained is True

    def test_partition_data_loss(self):
        """Test data loss during partition."""
        simulator = NetworkPartitionSimulator(cluster_size=5)
        simulator.create_partition(["node_1"], ["node_2", "node_3", "node_4", "node_5"])

        impact = simulator.simulate_minority_partition_behavior()

        # Well-designed system should not lose data
        assert impact.data_loss is False

    def test_byzantine_consistency(self):
        """Test consistency against Byzantine failures."""
        executor = FailureScenarioExecutor()
        scenario = FailureScenario(
            name="Byzantine",
            failure_type=FailureType.BYZANTINE_BEHAVIOR,
            severity=SeverityLevel.HIGH,
            affected_nodes=["node_1"],
            duration_seconds=5.0,
        )

        impact = executor.execute_scenario(scenario)

        assert impact.consistency_maintained is True
