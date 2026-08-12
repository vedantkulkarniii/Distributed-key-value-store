"""Performance benchmarking for Phase 5 features."""

import time
import statistics
from typing import Dict, List, Any
from dataclasses import dataclass, field
from src.raft.state_machine import StateMachineEngine
from src.raft.transaction_manager import TransactionManager, IsolationLevel
from src.raft.snapshot_store import SnapshotStore
from src.raft.crash_recovery import CrashRecoveryHandler
from src.raft.idempotency import IdempotencyManager
from src.raft.linearizable_read import LinearizableReadHandler
from src.raft.lease_manager import LeaseManager
from src.raft.request_pipeline import RequestPipeline


@dataclass
class BenchmarkResult:
    """Result of a benchmark test."""
    name: str
    iterations: int
    total_time: float
    min_time: float
    max_time: float
    avg_time: float
    std_dev: float
    throughput: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        """Format benchmark result as string."""
        return (
            f"{self.name}:\n"
            f"  Iterations: {self.iterations}\n"
            f"  Total Time: {self.total_time:.4f}s\n"
            f"  Avg Time: {self.avg_time*1000:.2f}ms\n"
            f"  Min/Max: {self.min_time*1000:.2f}ms / {self.max_time*1000:.2f}ms\n"
            f"  Std Dev: {self.std_dev*1000:.2f}ms\n"
            f"  Throughput: {self.throughput:.0f} ops/sec"
        )


class PerformanceBenchmark:
    """Performance benchmark suite for Phase 5 features."""

    def __init__(self):
        """Initialize benchmark suite."""
        self.results: List[BenchmarkResult] = []

    def benchmark_transaction_throughput(self, iterations: int = 1000) -> BenchmarkResult:
        """Benchmark transaction throughput."""
        state_machine = StateMachineEngine("node1")
        txn_mgr = TransactionManager("node1", state_machine.data)

        times = []
        for i in range(iterations):
            start = time.perf_counter()

            # Begin transaction
            _, tx_id, _ = txn_mgr.begin_transaction("client1")

            # Write operation
            txn_mgr.write_in_transaction(tx_id, f"key_{i}", f"value_{i}")

            # Commit
            txn_mgr.commit_transaction(tx_id)

            elapsed = time.perf_counter() - start
            times.append(elapsed)

        result = self._calculate_stats("Transaction Throughput", iterations, times)
        self.results.append(result)
        return result

    def benchmark_snapshot_compression(self, data_size: int = 10000) -> BenchmarkResult:
        """Benchmark snapshot compression efficiency."""
        # Create large dataset
        state = {f"key_{i}": f"value_{i}" * 10 for i in range(data_size)}

        snapshot_store = SnapshotStore("node1")
        times = []

        # Measure compression time
        start = time.perf_counter()
        success, snap_id, compression_stats = snapshot_store.create_snapshot(
            state, term=1, index=100
        )
        elapsed = time.perf_counter() - start
        times.append(elapsed)

        result = self._calculate_stats("Snapshot Compression", 1, times)
        result.metadata = {
            "data_size": data_size,
            "compression_ratio": compression_stats.get("ratio", 0),
            "original_size": compression_stats.get("original_size", 0),
            "compressed_size": compression_stats.get("compressed_size", 0),
        }
        self.results.append(result)
        return result

    def benchmark_idempotency_dedup(self, iterations: int = 1000) -> BenchmarkResult:
        """Benchmark idempotency deduplication."""
        idemp_mgr = IdempotencyManager("node1")
        idemp_mgr.create_session("client1")

        times = []
        for i in range(iterations):
            start = time.perf_counter()

            # First request
            is_dup1, _, _ = idemp_mgr.process_request("client1", f"req_{i}", {})

            # Cache result
            idemp_mgr.cache_result("client1", f"req_{i}", {"result": "ok"})

            # Duplicate detection
            is_dup2, result, _ = idemp_mgr.process_request("client1", f"req_{i}", {})

            elapsed = time.perf_counter() - start
            times.append(elapsed)

        result = self._calculate_stats("Idempotency Deduplication", iterations, times)
        self.results.append(result)
        return result

    def benchmark_linearizable_read(self, iterations: int = 1000) -> BenchmarkResult:
        """Benchmark linearizable read latency."""
        read_handler = LinearizableReadHandler("node1", cluster_size=3)

        times = []
        for i in range(iterations):
            start = time.perf_counter()

            # Initiate read
            request = read_handler.initiate_read(read_index=10 + i)

            # Process read index
            read_handler.process_read_index(request.request_id, 10 + i, term=1)

            # Collect ACKs
            read_handler.send_heartbeat_for_read(request.request_id)
            read_handler.record_heartbeat_ack(request.request_id, "node2")

            elapsed = time.perf_counter() - start
            times.append(elapsed)

        result = self._calculate_stats("Linearizable Read", iterations, times)
        self.results.append(result)
        return result

    def benchmark_lease_optimization(self, iterations: int = 1000) -> BenchmarkResult:
        """Benchmark lease-based read optimization."""
        lease_mgr = LeaseManager("node1")

        times = []
        for i in range(iterations):
            start = time.perf_counter()

            # Acquire lease
            success, lease, _ = lease_mgr.acquire_lease(term=1)

            # Check if lease is valid
            if lease:
                lease_mgr.is_lease_valid(lease)

            elapsed = time.perf_counter() - start
            times.append(elapsed)

        result = self._calculate_stats("Lease Optimization", iterations, times)
        self.results.append(result)
        return result

    def benchmark_crash_recovery(self, log_size: int = 100) -> BenchmarkResult:
        """Benchmark crash recovery time."""
        # Create large log
        log_entries = [
            {
                "index": i,
                "command": {"op": "SET", "key": f"key_{i}", "value": f"value_{i}"}
            }
            for i in range(1, log_size + 1)
        ]

        # Create snapshot
        state = {f"key_{i}": f"value_{i}" for i in range(1, log_size // 2)}
        snapshot_store = SnapshotStore("node1")
        snapshot_store.create_snapshot(state, term=1, index=log_size // 2)

        # Measure recovery time
        recovery = CrashRecoveryHandler("node1")
        start = time.perf_counter()

        success, recovered_state, stats = recovery.full_recovery(
            snapshot_store, log_entries, term=1, last_applied_index=0
        )

        elapsed = time.perf_counter() - start

        result = self._calculate_stats("Crash Recovery", 1, [elapsed])
        result.metadata = {
            "log_size": log_size,
            "recovered_keys": len(recovered_state),
            "recovery_success": success,
        }
        self.results.append(result)
        return result

    def benchmark_request_pipeline(self, iterations: int = 1000, batch_size: int = 10) -> BenchmarkResult:
        """Benchmark request pipeline batching."""
        pipeline = RequestPipeline("node1", batch_size=batch_size, max_batch_time_ms=100)

        times = []
        for i in range(iterations):
            start = time.perf_counter()

            # Enqueue request
            request_id = pipeline.enqueue_request(
                client_id="client1",
                request_id=f"req_{i}",
                operation={"op": "set", "key": f"key_{i}", "value": f"value_{i}"}
            )

            elapsed = time.perf_counter() - start
            times.append(elapsed)

        result = self._calculate_stats("Request Pipeline", iterations, times)
        result.metadata = {
            "batch_size": batch_size,
            "total_requests": iterations,
        }
        self.results.append(result)
        return result

    def benchmark_transaction_isolation(self, iterations: int = 100) -> BenchmarkResult:
        """Benchmark transaction isolation level overhead."""
        state_machine = StateMachineEngine("node1")
        txn_mgr = TransactionManager("node1", state_machine.data)

        times = []
        for i in range(iterations):
            start = time.perf_counter()

            # Serializable isolation
            _, tx_id, _ = txn_mgr.begin_transaction(
                "client1", IsolationLevel.SERIALIZABLE
            )
            txn_mgr.read_in_transaction(tx_id, f"key_{i}")
            txn_mgr.write_in_transaction(tx_id, f"key_{i}", f"value_{i}")
            txn_mgr.commit_transaction(tx_id)

            elapsed = time.perf_counter() - start
            times.append(elapsed)

        result = self._calculate_stats("Transaction Isolation (Serializable)", iterations, times)
        self.results.append(result)
        return result

    def benchmark_state_consistency_check(self, state_size: int = 10000) -> BenchmarkResult:
        """Benchmark state consistency verification."""
        from src.raft.state_sync import MultiNodeStateSyncManager

        # Create two large states
        state1 = {f"key_{i}": f"value_{i}" for i in range(state_size)}
        state2 = {f"key_{i}": f"value_{i}" for i in range(state_size)}

        sync_mgr = MultiNodeStateSyncManager("node1", cluster_size=3)

        start = time.perf_counter()
        is_consistent, score = sync_mgr.verify_consistency("node2", state1, state2)
        elapsed = time.perf_counter() - start

        result = self._calculate_stats("State Consistency Check", 1, [elapsed])
        result.metadata = {
            "state_size": state_size,
            "consistency_score": score,
            "is_consistent": is_consistent,
        }
        self.results.append(result)
        return result

    def _calculate_stats(self, name: str, iterations: int, times: List[float]) -> BenchmarkResult:
        """Calculate statistics from timing measurements."""
        total_time = sum(times)
        min_time = min(times)
        max_time = max(times)
        avg_time = statistics.mean(times)
        std_dev = statistics.stdev(times) if len(times) > 1 else 0
        throughput = iterations / total_time if total_time > 0 else 0

        return BenchmarkResult(
            name=name,
            iterations=iterations,
            total_time=total_time,
            min_time=min_time,
            max_time=max_time,
            avg_time=avg_time,
            std_dev=std_dev,
            throughput=throughput,
        )

    def run_all_benchmarks(self) -> Dict[str, BenchmarkResult]:
        """Run all benchmarks."""
        benchmarks = {
            "transaction_throughput": self.benchmark_transaction_throughput(),
            "snapshot_compression": self.benchmark_snapshot_compression(),
            "idempotency_dedup": self.benchmark_idempotency_dedup(),
            "linearizable_read": self.benchmark_linearizable_read(),
            "lease_optimization": self.benchmark_lease_optimization(),
            "crash_recovery": self.benchmark_crash_recovery(),
            "request_pipeline": self.benchmark_request_pipeline(),
            "transaction_isolation": self.benchmark_transaction_isolation(),
            "state_consistency_check": self.benchmark_state_consistency_check(),
        }
        return benchmarks

    def print_summary(self):
        """Print summary of all benchmarks."""
        print("\n" + "="*60)
        print("PHASE 5 PERFORMANCE BENCHMARK SUMMARY")
        print("="*60 + "\n")

        for result in self.results:
            print(result)
            print()

        print("="*60)
        print(f"Total Benchmarks: {len(self.results)}")
        total_time = sum(r.total_time for r in self.results)
        print(f"Total Benchmark Time: {total_time:.2f}s")
        print("="*60)

    def get_results_dict(self) -> Dict[str, Dict[str, Any]]:
        """Get results as dictionary."""
        return {
            r.name: {
                "iterations": r.iterations,
                "total_time": r.total_time,
                "avg_time_ms": r.avg_time * 1000,
                "min_time_ms": r.min_time * 1000,
                "max_time_ms": r.max_time * 1000,
                "std_dev_ms": r.std_dev * 1000,
                "throughput": r.throughput,
                "metadata": r.metadata,
            }
            for r in self.results
        }
