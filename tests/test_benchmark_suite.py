"""Tests for comprehensive benchmarking suite."""

import pytest
from src.raft.benchmark_suite import (
    BenchmarkMetric,
    BenchmarkSuite,
    TransactionBenchmark,
    NetworkBenchmark,
    StorageBenchmark,
    ClusterBenchmark,
)


class TestBenchmarkMetric:
    """Tests for BenchmarkMetric class."""

    def test_metric_creation(self):
        """Test creating metric."""
        metric = BenchmarkMetric(
            name="test",
            iterations=100,
            total_time=1.0,
            min_time=0.005,
            max_time=0.020,
            avg_time=0.010,
            std_dev=0.003,
            throughput=100.0,
        )
        
        assert metric.name == "test"
        assert metric.iterations == 100


class TestBenchmarkSuite:
    """Tests for BenchmarkSuite."""

    def test_suite_creation(self):
        """Test creating suite."""
        suite = BenchmarkSuite()
        assert len(suite.metrics) == 0

    def test_benchmark_simple(self):
        """Test simple benchmark."""
        suite = BenchmarkSuite()
        
        def simple_op():
            pass
        
        metric = suite.benchmark("test", simple_op, 100)
        
        assert metric.name == "test"
        assert metric.iterations == 100
        assert metric.throughput > 0

    def test_benchmark_with_args(self):
        """Test benchmark with arguments."""
        suite = BenchmarkSuite()
        
        def op_with_args(x, y):
            return x + y
        
        metric = suite.benchmark("add", op_with_args, 100, 1, 2)
        
        assert metric.name == "add"

    def test_benchmark_compare(self):
        """Test comparing functions."""
        suite = BenchmarkSuite()
        
        def fast_op():
            pass
        
        def slow_op():
            for _ in range(10):
                pass
        
        result = suite.benchmark_compare(fast_op, slow_op, 100)
        
        assert "improvement_percentage" in result
        assert "func2_faster" in result

    def test_benchmark_under_load(self):
        """Test benchmarking under load."""
        suite = BenchmarkSuite()
        
        def op():
            pass
        
        result = suite.benchmark_under_load(op, 0.1)
        
        assert result["operations"] > 0
        assert "throughput" in result

    def test_get_summary(self):
        """Test getting summary."""
        suite = BenchmarkSuite()
        
        def op():
            pass
        
        suite.benchmark("op1", op, 100)
        suite.benchmark("op2", op, 100)
        
        summary = suite.get_summary()
        
        assert summary["total_benchmarks"] == 2
        assert "metrics" in summary


class TestTransactionBenchmark:
    """Tests for transaction benchmarks."""

    def test_transaction_lifecycle(self):
        """Test transaction lifecycle benchmark."""
        result = TransactionBenchmark.benchmark_transaction_lifecycle({})
        
        assert "begin_latency_ms" in result
        assert "read_latency_ms" in result
        assert "write_latency_ms" in result
        assert "commit_latency_ms" in result

    def test_isolation_levels(self):
        """Test isolation level benchmarks."""
        result = TransactionBenchmark.benchmark_isolation_levels()
        
        assert "serializable" in result
        assert "repeatable_read" in result
        assert "read_committed" in result
        assert "read_uncommitted" in result


class TestNetworkBenchmark:
    """Tests for network benchmarks."""

    def test_message_latency(self):
        """Test message latency benchmark."""
        result = NetworkBenchmark.benchmark_message_latency()
        
        assert "latency_ms" in result
        assert "throughput_msg_per_sec" in result

    def test_message_latency_sizes(self):
        """Test message latency with different sizes."""
        sizes = [64, 256, 1024, 4096]
        results = []
        
        for size in sizes:
            result = NetworkBenchmark.benchmark_message_latency(size)
            results.append(result)
        
        assert len(results) == 4

    def test_replication(self):
        """Test replication benchmark."""
        result = NetworkBenchmark.benchmark_replication()
        
        assert "latency_ms" in result
        assert "throughput" in result


class TestStorageBenchmark:
    """Tests for storage benchmarks."""

    def test_snapshot_creation(self):
        """Test snapshot creation benchmark."""
        result = StorageBenchmark.benchmark_snapshot_creation(1000000)
        
        assert result["data_size_bytes"] == 1000000
        assert "latency_ms" in result

    def test_snapshot_recovery(self):
        """Test snapshot recovery benchmark."""
        result = StorageBenchmark.benchmark_snapshot_recovery(1000000)
        
        assert result["data_size_bytes"] == 1000000
        assert "latency_ms" in result

    def test_snapshot_sizes(self):
        """Test snapshots of different sizes."""
        sizes = [100000, 1000000, 10000000]
        
        for size in sizes:
            result = StorageBenchmark.benchmark_snapshot_creation(size)
            assert result["data_size_bytes"] == size


class TestClusterBenchmark:
    """Tests for cluster benchmarks."""

    def test_leader_election(self):
        """Test leader election benchmark."""
        result = ClusterBenchmark.benchmark_leader_election()
        
        assert "latency_ms" in result
        assert "throughput" in result

    def test_failover(self):
        """Test failover benchmark."""
        result = ClusterBenchmark.benchmark_failover(cluster_size=3)
        
        assert result["cluster_size"] == 3
        assert "latency_ms" in result

    def test_failover_sizes(self):
        """Test failover with different cluster sizes."""
        sizes = [3, 5, 7]
        
        for size in sizes:
            result = ClusterBenchmark.benchmark_failover(size)
            assert result["cluster_size"] == size

    def test_cluster_consistency(self):
        """Test cluster consistency benchmark."""
        result = ClusterBenchmark.benchmark_cluster_consistency(3)
        
        assert result["cluster_size"] == 3
        assert "latency_ms" in result

    def test_consistency_sizes(self):
        """Test consistency with different cluster sizes."""
        sizes = [3, 5, 7]
        
        for size in sizes:
            result = ClusterBenchmark.benchmark_cluster_consistency(size)
            assert result["cluster_size"] == size


class TestBenchmarkIntegration:
    """Integration tests for benchmarking."""

    def test_comprehensive_benchmark(self):
        """Test comprehensive benchmarking."""
        suite = BenchmarkSuite()
        
        def op1():
            pass
        
        def op2():
            for _ in range(5):
                pass
        
        # Run multiple benchmarks
        suite.benchmark("fast", op1, 1000)
        suite.benchmark("slow", op2, 1000)
        
        summary = suite.get_summary()
        
        assert len(summary["metrics"]) == 2

    def test_all_benchmark_types(self):
        """Test all benchmark types."""
        # Transaction
        txn_result = TransactionBenchmark.benchmark_transaction_lifecycle({})
        assert txn_result is not None
        
        # Network
        net_result = NetworkBenchmark.benchmark_message_latency()
        assert net_result is not None
        
        # Storage
        storage_result = StorageBenchmark.benchmark_snapshot_creation(1000000)
        assert storage_result is not None
        
        # Cluster
        cluster_result = ClusterBenchmark.benchmark_failover(3)
        assert cluster_result is not None

    def test_benchmark_accuracy(self):
        """Test benchmark measurement accuracy."""
        suite = BenchmarkSuite()
        
        counter = {"count": 0}
        
        def counted_op():
            counter["count"] += 1
        
        metric = suite.benchmark("count", counted_op, 50)
        
        assert counter["count"] == 50
        assert metric.iterations == 50

    def test_benchmark_metrics_consistency(self):
        """Test metric consistency."""
        suite = BenchmarkSuite()
        
        def op():
            pass
        
        metric = suite.benchmark("test", op, 100)
        
        # Verify metric properties
        assert metric.min_time <= metric.avg_time <= metric.max_time
        assert metric.throughput > 0
        assert metric.std_dev >= 0
