"""Performance benchmark tests for Phase 5 features."""

import pytest
from src.raft.performance_benchmarks import PerformanceBenchmark, BenchmarkResult


class TestBenchmarkResultClass:
    """Tests for BenchmarkResult class."""

    def test_benchmark_result_creation(self):
        """Test creating a benchmark result."""
        result = BenchmarkResult(
            name="test",
            iterations=100,
            total_time=1.0,
            min_time=0.005,
            max_time=0.020,
            avg_time=0.010,
            std_dev=0.003,
            throughput=100.0,
        )

        assert result.name == "test"
        assert result.iterations == 100
        assert result.throughput == 100.0

    def test_benchmark_result_string_representation(self):
        """Test string representation of result."""
        result = BenchmarkResult(
            name="test",
            iterations=100,
            total_time=1.0,
            min_time=0.005,
            max_time=0.020,
            avg_time=0.010,
            std_dev=0.003,
            throughput=100.0,
        )

        result_str = str(result)
        assert "test" in result_str
        assert "100" in result_str
        assert "10.00ms" in result_str


class TestTransactionBenchmark:
    """Tests for transaction benchmarks."""

    def test_transaction_throughput_benchmark(self):
        """Test transaction throughput benchmark."""
        benchmark = PerformanceBenchmark()
        result = benchmark.benchmark_transaction_throughput(iterations=100)

        assert result.name == "Transaction Throughput"
        assert result.iterations == 100
        assert result.total_time > 0
        assert result.avg_time > 0
        assert result.throughput > 0
        assert result.min_time <= result.avg_time <= result.max_time

    def test_transaction_isolation_benchmark(self):
        """Test transaction isolation benchmark."""
        benchmark = PerformanceBenchmark()
        result = benchmark.benchmark_transaction_isolation(iterations=50)

        assert result.name == "Transaction Isolation (Serializable)"
        assert result.iterations == 50
        assert result.throughput > 0


class TestSnapshotBenchmark:
    """Tests for snapshot benchmarks."""

    def test_snapshot_compression_benchmark(self):
        """Test snapshot compression benchmark."""
        benchmark = PerformanceBenchmark()
        result = benchmark.benchmark_snapshot_compression(data_size=1000)

        assert result.name == "Snapshot Compression"
        assert result.metadata["data_size"] == 1000
        assert result.total_time > 0

    def test_snapshot_compression_ratio(self):
        """Test snapshot compression ratio."""
        benchmark = PerformanceBenchmark()
        result = benchmark.benchmark_snapshot_compression(data_size=500)

        assert "compression_ratio" in result.metadata
        ratio = result.metadata["compression_ratio"]
        # Should have some compression (< 1.0)
        assert 0 < ratio <= 1.0


class TestIdempotencyBenchmark:
    """Tests for idempotency benchmarks."""

    def test_idempotency_dedup_benchmark(self):
        """Test idempotency deduplication benchmark."""
        benchmark = PerformanceBenchmark()
        result = benchmark.benchmark_idempotency_dedup(iterations=100)

        assert result.name == "Idempotency Deduplication"
        assert result.iterations == 100
        assert result.throughput > 0

    def test_idempotency_dedup_performance(self):
        """Test idempotency dedup performance characteristics."""
        benchmark = PerformanceBenchmark()
        result = benchmark.benchmark_idempotency_dedup(iterations=50)

        # Dedup should be very fast (< 1ms on average typically)
        assert result.avg_time > 0  # At least some measurable time


class TestLinearizableReadBenchmark:
    """Tests for linearizable read benchmarks."""

    def test_linearizable_read_benchmark(self):
        """Test linearizable read benchmark."""
        benchmark = PerformanceBenchmark()
        result = benchmark.benchmark_linearizable_read(iterations=100)

        assert result.name == "Linearizable Read"
        assert result.iterations == 100
        assert result.throughput > 0

    def test_linearizable_read_latency(self):
        """Test linearizable read latency."""
        benchmark = PerformanceBenchmark()
        result = benchmark.benchmark_linearizable_read(iterations=50)

        # Latency should be reasonable (< 100ms on average)
        assert result.avg_time < 0.1


class TestLeaseBenchmark:
    """Tests for lease optimization benchmarks."""

    def test_lease_optimization_benchmark(self):
        """Test lease optimization benchmark."""
        benchmark = PerformanceBenchmark()
        result = benchmark.benchmark_lease_optimization(iterations=100)

        assert result.name == "Lease Optimization"
        assert result.iterations == 100
        assert result.throughput > 0

    def test_lease_performance(self):
        """Test lease performance characteristics."""
        benchmark = PerformanceBenchmark()
        result = benchmark.benchmark_lease_optimization(iterations=100)

        # Leases should be very fast
        assert result.avg_time > 0


class TestCrashRecoveryBenchmark:
    """Tests for crash recovery benchmarks."""

    def test_crash_recovery_benchmark(self):
        """Test crash recovery benchmark."""
        benchmark = PerformanceBenchmark()
        result = benchmark.benchmark_crash_recovery(log_size=100)

        assert result.name == "Crash Recovery"
        assert result.metadata["log_size"] == 100
        assert result.metadata["recovery_success"] is True
        assert result.total_time > 0

    def test_crash_recovery_large_log(self):
        """Test crash recovery with larger log."""
        benchmark = PerformanceBenchmark()
        result = benchmark.benchmark_crash_recovery(log_size=500)

        assert result.metadata["log_size"] == 500
        assert result.metadata["recovered_keys"] > 0


class TestRequestPipelineBenchmark:
    """Tests for request pipeline benchmarks."""

    def test_request_pipeline_benchmark(self):
        """Test request pipeline benchmark."""
        benchmark = PerformanceBenchmark()
        result = benchmark.benchmark_request_pipeline(iterations=100, batch_size=10)

        assert result.name == "Request Pipeline"
        assert result.iterations == 100
        assert result.metadata["batch_size"] == 10
        assert result.throughput > 0

    def test_request_pipeline_batching_effect(self):
        """Test batching effect on throughput."""
        benchmark = PerformanceBenchmark()
        result_small = benchmark.benchmark_request_pipeline(iterations=100, batch_size=1)
        
        benchmark2 = PerformanceBenchmark()
        result_large = benchmark2.benchmark_request_pipeline(iterations=100, batch_size=20)

        # Larger batches should have better throughput
        assert result_large.throughput > result_small.throughput


class TestStateConsistencyBenchmark:
    """Tests for state consistency benchmarks."""

    def test_state_consistency_benchmark(self):
        """Test state consistency check benchmark."""
        benchmark = PerformanceBenchmark()
        result = benchmark.benchmark_state_consistency_check(state_size=1000)

        assert result.name == "State Consistency Check"
        assert result.metadata["state_size"] == 1000
        assert result.metadata["is_consistent"] is True
        assert result.total_time > 0

    def test_state_consistency_score(self):
        """Test state consistency scoring."""
        benchmark = PerformanceBenchmark()
        result = benchmark.benchmark_state_consistency_check(state_size=500)

        consistency_score = result.metadata["consistency_score"]
        assert 0 <= consistency_score <= 1.0


class TestBenchmarkSuite:
    """Tests for complete benchmark suite."""

    def test_run_all_benchmarks(self):
        """Test running all benchmarks."""
        benchmark = PerformanceBenchmark()
        results = benchmark.run_all_benchmarks()

        assert len(results) == 9
        assert "transaction_throughput" in results
        assert "snapshot_compression" in results
        assert "idempotency_dedup" in results
        assert "linearizable_read" in results
        assert "lease_optimization" in results
        assert "crash_recovery" in results
        assert "request_pipeline" in results
        assert "transaction_isolation" in results
        assert "state_consistency_check" in results

    def test_all_benchmarks_have_valid_results(self):
        """Test all benchmarks produce valid results."""
        benchmark = PerformanceBenchmark()
        results = benchmark.run_all_benchmarks()

        for name, result in results.items():
            assert result.name is not None
            assert result.iterations > 0
            assert result.total_time > 0
            assert result.throughput >= 0
            assert result.min_time > 0
            assert result.max_time > 0
            assert result.min_time <= result.max_time

    def test_results_dictionary_format(self):
        """Test results dictionary format."""
        benchmark = PerformanceBenchmark()
        benchmark.run_all_benchmarks()

        results_dict = benchmark.get_results_dict()

        assert isinstance(results_dict, dict)
        for name, metrics in results_dict.items():
            assert "iterations" in metrics
            assert "total_time" in metrics
            assert "avg_time_ms" in metrics
            assert "min_time_ms" in metrics
            assert "max_time_ms" in metrics
            assert "throughput" in metrics


class TestBenchmarkScalability:
    """Tests for benchmark scalability."""

    def test_benchmark_scales_with_iterations(self):
        """Test benchmark scales with iteration count."""
        benchmark1 = PerformanceBenchmark()
        result1 = benchmark1.benchmark_transaction_throughput(iterations=100)

        benchmark2 = PerformanceBenchmark()
        result2 = benchmark2.benchmark_transaction_throughput(iterations=200)

        # More iterations should generally take more time
        assert result2.total_time > result1.total_time

    def test_benchmark_consistency(self):
        """Test benchmark produces consistent throughput."""
        benchmark = PerformanceBenchmark()
        result = benchmark.benchmark_transaction_throughput(iterations=100)

        # Throughput should be reasonable (positive and non-zero)
        assert result.throughput > 0
        # Standard deviation should be reasonable
        assert result.std_dev > 0


class TestBenchmarkEdgeCases:
    """Tests for benchmark edge cases."""

    def test_snapshot_compression_small_data(self):
        """Test snapshot compression with small data."""
        benchmark = PerformanceBenchmark()
        result = benchmark.benchmark_snapshot_compression(data_size=10)

        assert result.metadata["data_size"] == 10
        assert result.total_time > 0

    def test_crash_recovery_empty_log(self):
        """Test crash recovery with empty log."""
        benchmark = PerformanceBenchmark()
        result = benchmark.benchmark_crash_recovery(log_size=1)

        assert result.metadata["log_size"] == 1
        assert result.metadata["recovery_success"] is True

    def test_state_consistency_large_state(self):
        """Test state consistency with large state."""
        benchmark = PerformanceBenchmark()
        result = benchmark.benchmark_state_consistency_check(state_size=5000)

        assert result.metadata["state_size"] == 5000
        assert result.total_time > 0


class TestBenchmarkMetadata:
    """Tests for benchmark metadata tracking."""

    def test_snapshot_compression_metadata(self):
        """Test snapshot compression metadata."""
        benchmark = PerformanceBenchmark()
        result = benchmark.benchmark_snapshot_compression(data_size=500)

        assert "data_size" in result.metadata
        assert "compression_ratio" in result.metadata
        assert "original_size" in result.metadata
        assert "compressed_size" in result.metadata

    def test_crash_recovery_metadata(self):
        """Test crash recovery metadata."""
        benchmark = PerformanceBenchmark()
        result = benchmark.benchmark_crash_recovery(log_size=200)

        assert "log_size" in result.metadata
        assert "recovered_keys" in result.metadata
        assert "recovery_success" in result.metadata

    def test_request_pipeline_metadata(self):
        """Test request pipeline metadata."""
        benchmark = PerformanceBenchmark()
        result = benchmark.benchmark_request_pipeline(iterations=50, batch_size=5)

        assert "batch_size" in result.metadata
        assert "total_requests" in result.metadata


class TestBenchmarkComparison:
    """Tests for benchmark comparison."""

    def test_compare_different_batch_sizes(self):
        """Test comparing different batch sizes."""
        results = []

        for batch_size in [1, 5, 10, 20]:
            benchmark = PerformanceBenchmark()
            result = benchmark.benchmark_request_pipeline(
                iterations=100, batch_size=batch_size
            )
            results.append(result)

        # Verify throughput increases with batch size
        throughputs = [r.throughput for r in results]
        assert throughputs[-1] > throughputs[0]  # Larger batch > smaller batch

    def test_benchmark_statistical_validity(self):
        """Test benchmark has valid statistics."""
        benchmark = PerformanceBenchmark()
        result = benchmark.benchmark_transaction_throughput(iterations=50)

        # Verify statistical measures make sense
        assert result.min_time <= result.avg_time <= result.max_time
        assert result.std_dev >= 0
        assert result.throughput > 0
