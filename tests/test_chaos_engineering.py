"""Tests for chaos engineering framework."""

import pytest
import random
from src.raft.chaos_engineering import (
    ChaosType,
    ChaosInjection,
    ChaosResult,
    LatencyInjector,
    PacketLossInjector,
    NodeFailureInjector,
    DiskSlowdownInjector,
    MemoryPressureInjector,
    CPUSpikeInjector,
    ChaosExperiment,
    ChaosScenario,
)


class TestLatencyInjector:
    """Tests for latency injection."""

    def test_latency_disabled(self):
        """Test latency when disabled."""
        injector = LatencyInjector(base_latency_ms=1.0)
        assert injector.apply() == 1.0

    def test_latency_enabled(self):
        """Test latency when enabled."""
        injector = LatencyInjector(base_latency_ms=1.0)
        injector.enable(latency_ms=10.0)
        
        latency = injector.apply()
        assert latency >= 10.0

    def test_latency_disabled_after_enable(self):
        """Test latency after disabling."""
        injector = LatencyInjector(base_latency_ms=1.0)
        injector.enable(latency_ms=10.0)
        injector.disable()
        
        assert injector.apply() == 1.0


class TestPacketLossInjector:
    """Tests for packet loss injection."""

    def test_packet_loss_disabled(self):
        """Test packet loss when disabled."""
        injector = PacketLossInjector(loss_probability=0.5)
        injector.disable()
        
        assert not injector.should_drop_packet()

    def test_packet_loss_enabled(self):
        """Test packet loss when enabled."""
        injector = PacketLossInjector()
        injector.enable(probability=0.5)
        
        # Send many packets
        drops = 0
        for _ in range(1000):
            if injector.should_drop_packet():
                drops += 1
        
        # Should approximate 50%
        loss_rate = injector.get_loss_rate()
        assert 0.3 < loss_rate < 0.7

    def test_packet_loss_rate(self):
        """Test packet loss rate calculation."""
        injector = PacketLossInjector()
        injector.enable(probability=0.1)
        
        for _ in range(100):
            injector.should_drop_packet()
        
        loss_rate = injector.get_loss_rate()
        assert loss_rate >= 0.0


class TestNodeFailureInjector:
    """Tests for node failure injection."""

    def test_fail_node(self):
        """Test failing a node."""
        injector = NodeFailureInjector()
        injector.fail_node("node1")
        
        assert injector.is_node_failed("node1")

    def test_recover_node(self):
        """Test recovering a node."""
        injector = NodeFailureInjector()
        injector.fail_node("node1")
        injector.recover_node("node1")
        
        assert not injector.is_node_failed("node1")

    def test_multiple_failures(self):
        """Test multiple node failures."""
        injector = NodeFailureInjector()
        
        for i in range(1, 4):
            injector.fail_node(f"node{i}")
        
        failed = injector.get_failed_nodes()
        assert len(failed) == 3

    def test_recovery_time(self):
        """Test recovery time tracking."""
        import time
        
        injector = NodeFailureInjector()
        injector.fail_node("node1")
        
        time.sleep(0.05)
        injector.recover_node("node1")
        
        avg_time = injector.get_average_recovery_time()
        assert avg_time >= 0.05


class TestDiskSlowdownInjector:
    """Tests for disk slowdown injection."""

    def test_disk_slowdown_disabled(self):
        """Test disk slowdown when disabled."""
        injector = DiskSlowdownInjector(base_latency_ms=10.0)
        assert injector.get_latency() == 10.0

    def test_disk_slowdown_enabled(self):
        """Test disk slowdown when enabled."""
        injector = DiskSlowdownInjector(base_latency_ms=10.0)
        injector.enable(slowdown_factor=5.0)
        
        assert injector.get_latency() == 50.0


class TestMemoryPressureInjector:
    """Tests for memory pressure injection."""

    def test_memory_pressure_disabled(self):
        """Test memory pressure when disabled."""
        injector = MemoryPressureInjector(total_memory_mb=1000)
        assert injector.get_available_memory_mb() == 1000

    def test_memory_pressure_enabled(self):
        """Test memory pressure when enabled."""
        injector = MemoryPressureInjector(total_memory_mb=1000)
        injector.enable(pressure_percentage=50.0)
        
        assert injector.get_available_memory_mb() == 500

    def test_memory_pressure_percentage(self):
        """Test memory pressure percentage."""
        injector = MemoryPressureInjector(total_memory_mb=1000)
        injector.enable(pressure_percentage=75.0)
        
        pressure = injector.get_memory_pressure_percentage()
        assert pressure == 75.0


class TestCPUSpikeInjector:
    """Tests for CPU spike injection."""

    def test_cpu_spike_trigger(self):
        """Test CPU spike trigger."""
        injector = CPUSpikeInjector()
        injector.trigger_spike(duration_seconds=1.0)
        
        assert injector.is_spike_active()

    def test_cpu_spike_duration(self):
        """Test CPU spike duration."""
        import time
        
        injector = CPUSpikeInjector()
        injector.trigger_spike(duration_seconds=0.05)
        
        assert injector.is_spike_active()
        time.sleep(0.1)
        
        assert not injector.is_spike_active()

    def test_cpu_utilization(self):
        """Test CPU utilization."""
        injector = CPUSpikeInjector()
        
        # Normal utilization
        util = injector.get_cpu_utilization()
        assert 0.0 <= util <= 1.0
        
        # During spike
        injector.trigger_spike(duration_seconds=1.0)
        util = injector.get_cpu_utilization()
        assert util == 0.95


class TestChaosInjection:
    """Tests for ChaosInjection class."""

    def test_injection_creation(self):
        """Test creating chaos injection."""
        injection = ChaosInjection(
            chaos_type=ChaosType.LATENCY,
            target_node="node1",
            duration_seconds=10.0,
            intensity=0.8,
        )
        
        assert injection.chaos_type == ChaosType.LATENCY
        assert not injection.active


class TestChaosExperiment:
    """Tests for chaos experiments."""

    def test_experiment_creation(self):
        """Test creating experiment."""
        exp = ChaosExperiment("exp1", cluster_size=3)
        assert exp.experiment_id == "exp1"

    def test_add_injection(self):
        """Test adding injection."""
        exp = ChaosExperiment("exp1")
        exp.add_injection(ChaosType.LATENCY, "node1", 10.0, 0.8)
        
        assert len(exp.injections) == 1

    def test_run_experiment(self):
        """Test running experiment."""
        exp = ChaosExperiment("exp1")
        exp.add_injection(ChaosType.LATENCY, "node1", 0.05, 0.5)
        
        result = exp.run()
        
        assert result.experiment_id == "exp1"
        assert result.system_recovered

    def test_multiple_injections(self):
        """Test multiple injections."""
        exp = ChaosExperiment("exp1")
        exp.add_injection(ChaosType.LATENCY, "node1", 0.05, 0.5)
        exp.add_injection(ChaosType.PACKET_LOSS, "node2", 0.05, 0.3)
        
        result = exp.run()
        
        assert result.nodes_affected == 2

    def test_get_status(self):
        """Test getting experiment status."""
        exp = ChaosExperiment("exp1")
        exp.add_injection(ChaosType.LATENCY, "node1", 10.0, 0.5)
        
        status = exp.get_status()
        
        assert status["experiment_id"] == "exp1"
        assert status["injections"] == 1


class TestChaosScenario:
    """Tests for predefined chaos scenarios."""

    def test_network_outage_scenario(self):
        """Test network outage scenario."""
        exp = ChaosScenario.network_outage("node1", 10.0)
        
        assert exp.experiment_id == "network_outage"
        assert len(exp.injections) == 1
        assert exp.injections[0].chaos_type == ChaosType.NETWORK_PARTITION

    def test_slow_disk_scenario(self):
        """Test slow disk scenario."""
        exp = ChaosScenario.slow_disk("node1", 10.0)
        
        assert exp.injections[0].chaos_type == ChaosType.SLOW_DISK

    def test_cascading_failures_scenario(self):
        """Test cascading failures scenario."""
        exp = ChaosScenario.cascading_failures(cluster_size=5, duration_seconds=10.0)
        
        assert len(exp.injections) == 3

    def test_high_latency_scenario(self):
        """Test high latency scenario."""
        exp = ChaosScenario.high_latency("node1", 10.0)
        
        assert exp.injections[0].chaos_type == ChaosType.LATENCY

    def test_combined_chaos_scenario(self):
        """Test combined chaos scenario."""
        exp = ChaosScenario.combined_chaos("node1", 10.0)
        
        assert len(exp.injections) == 3


class TestChaosIntegration:
    """Integration tests for chaos engineering."""

    def test_scenario_execution(self):
        """Test executing predefined scenario."""
        exp = ChaosScenario.network_outage("node1", 0.05)
        result = exp.run()
        
        assert result.system_recovered
        assert result.nodes_affected >= 1

    def test_cascading_scenario_execution(self):
        """Test cascading scenario."""
        exp = ChaosScenario.cascading_failures(cluster_size=3, duration_seconds=0.05)
        result = exp.run()
        
        assert result.nodes_affected >= 1

    def test_combined_scenario_execution(self):
        """Test combined scenario."""
        exp = ChaosScenario.combined_chaos("node1", 0.05)
        result = exp.run()
        
        assert result.system_recovered

    def test_sequential_experiments(self):
        """Test running sequential experiments."""
        results = []
        
        for i in range(3):
            exp = ChaosExperiment(f"exp{i}")
            exp.add_injection(ChaosType.LATENCY, "node1", 0.05, 0.5)
            result = exp.run()
            results.append(result)
        
        assert len(results) == 3
