"""Load testing and stress testing framework for Phase 7."""

import time
import threading
from typing import Dict, List, Any, Callable, Optional
from dataclasses import dataclass
from enum import Enum
from queue import Queue


class LoadPattern(Enum):
    """Load patterns for testing."""
    CONSTANT = "constant"
    RAMP_UP = "ramp_up"
    SPIKE = "spike"
    WAVE = "wave"
    RANDOM = "random"


@dataclass
class LoadConfig:
    """Configuration for load test."""
    pattern: LoadPattern
    duration_seconds: int
    initial_threads: int
    max_threads: int
    operations_per_thread: int
    ramp_up_seconds: int = 10


@dataclass
class LoadMetrics:
    """Metrics from load test."""
    total_operations: int
    successful_operations: int
    failed_operations: int
    duration_seconds: float
    throughput_ops_per_sec: float
    avg_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    max_latency_ms: float
    error_rate: float


class LoadTester:
    """Executes load tests."""

    def __init__(self, operation: Callable, config: LoadConfig):
        """Initialize load tester."""
        self.operation = operation
        self.config = config
        self.metrics = LoadMetrics(
            total_operations=0,
            successful_operations=0,
            failed_operations=0,
            duration_seconds=0,
            throughput_ops_per_sec=0,
            avg_latency_ms=0,
            p95_latency_ms=0,
            p99_latency_ms=0,
            max_latency_ms=0,
            error_rate=0,
        )
        self.latencies: List[float] = []
        self.stop_event = threading.Event()

    def run(self) -> LoadMetrics:
        """Run load test."""
        start_time = time.time()
        threads = []

        if self.config.pattern == LoadPattern.CONSTANT:
            threads = self._run_constant_load()
        elif self.config.pattern == LoadPattern.RAMP_UP:
            threads = self._run_ramp_up_load()
        elif self.config.pattern == LoadPattern.SPIKE:
            threads = self._run_spike_load()
        elif self.config.pattern == LoadPattern.WAVE:
            threads = self._run_wave_load()
        else:
            threads = self._run_constant_load()

        # Wait for completion
        for thread in threads:
            thread.join(timeout=self.config.duration_seconds + 10)

        duration = time.time() - start_time
        self._calculate_metrics(duration)
        return self.metrics

    def _run_constant_load(self) -> List[threading.Thread]:
        """Run constant load pattern."""
        threads = []
        for _ in range(self.config.initial_threads):
            thread = threading.Thread(
                target=self._worker_thread, args=(self.config.operations_per_thread,)
            )
            thread.start()
            threads.append(thread)
        return threads

    def _run_ramp_up_load(self) -> List[threading.Thread]:
        """Run ramp up load pattern."""
        threads = []
        ops_per_phase = self.config.operations_per_thread // 5

        for phase in range(5):
            num_threads = (
                self.config.initial_threads
                + (self.config.max_threads - self.config.initial_threads)
                * phase
                // 5
            )

            for _ in range(num_threads):
                thread = threading.Thread(
                    target=self._worker_thread, args=(ops_per_phase,)
                )
                thread.start()
                threads.append(thread)

            time.sleep(self.config.ramp_up_seconds)

        return threads

    def _run_spike_load(self) -> List[threading.Thread]:
        """Run spike load pattern."""
        threads = []

        # Normal load
        for _ in range(self.config.initial_threads):
            thread = threading.Thread(
                target=self._worker_thread,
                args=(self.config.operations_per_thread // 2,),
            )
            thread.start()
            threads.append(thread)

        time.sleep(5)

        # Spike
        for _ in range(self.config.max_threads):
            thread = threading.Thread(
                target=self._worker_thread,
                args=(self.config.operations_per_thread // 2,),
            )
            thread.start()
            threads.append(thread)

        return threads

    def _run_wave_load(self) -> List[threading.Thread]:
        """Run wave load pattern."""
        threads = []
        waves = 3

        for wave in range(waves):
            for _ in range(self.config.max_threads):
                thread = threading.Thread(
                    target=self._worker_thread,
                    args=(self.config.operations_per_thread // waves,),
                )
                thread.start()
                threads.append(thread)

            time.sleep(2)

        return threads

    def _worker_thread(self, operations: int):
        """Worker thread."""
        for _ in range(operations):
            if self.stop_event.is_set():
                break

            try:
                start = time.perf_counter()
                self.operation()
                elapsed = (time.perf_counter() - start) * 1000

                self.latencies.append(elapsed)
                self.metrics.successful_operations += 1
            except Exception:
                self.metrics.failed_operations += 1

            self.metrics.total_operations += 1

    def _calculate_metrics(self, duration: float):
        """Calculate final metrics."""
        self.metrics.duration_seconds = duration

        if self.metrics.total_operations > 0:
            self.metrics.throughput_ops_per_sec = (
                self.metrics.total_operations / duration
            )
            self.metrics.error_rate = (
                self.metrics.failed_operations / self.metrics.total_operations * 100
            )

        if self.latencies:
            sorted_latencies = sorted(self.latencies)
            self.metrics.avg_latency_ms = sum(self.latencies) / len(self.latencies)
            self.metrics.max_latency_ms = max(self.latencies)
            self.metrics.p95_latency_ms = sorted_latencies[
                int(len(sorted_latencies) * 0.95)
            ]
            self.metrics.p99_latency_ms = sorted_latencies[
                int(len(sorted_latencies) * 0.99)
            ]

    def stop(self):
        """Stop load test."""
        self.stop_event.set()


class StressTest:
    """Stress test framework."""

    def __init__(self):
        """Initialize stress test."""
        self.results: List[Dict[str, Any]] = []

    def run_increasing_load(
        self,
        operation: Callable,
        initial_threads: int = 10,
        max_threads: int = 100,
        step: int = 10,
    ) -> List[Dict[str, Any]]:
        """Run test with increasing load."""
        results = []

        for num_threads in range(initial_threads, max_threads + 1, step):
            config = LoadConfig(
                pattern=LoadPattern.CONSTANT,
                duration_seconds=10,
                initial_threads=num_threads,
                max_threads=num_threads,
                operations_per_thread=100,
            )

            tester = LoadTester(operation, config)
            metrics = tester.run()

            result = {
                "threads": num_threads,
                "throughput": metrics.throughput_ops_per_sec,
                "avg_latency": metrics.avg_latency_ms,
                "p99_latency": metrics.p99_latency_ms,
                "error_rate": metrics.error_rate,
            }
            results.append(result)

        self.results = results
        return results

    def run_sustained_load(
        self, operation: Callable, duration_seconds: int = 60, threads: int = 50
    ) -> Dict[str, Any]:
        """Run sustained load test."""
        config = LoadConfig(
            pattern=LoadPattern.CONSTANT,
            duration_seconds=duration_seconds,
            initial_threads=threads,
            max_threads=threads,
            operations_per_thread=10000,
        )

        tester = LoadTester(operation, config)
        metrics = tester.run()

        return {
            "duration": metrics.duration_seconds,
            "threads": threads,
            "total_operations": metrics.total_operations,
            "successful": metrics.successful_operations,
            "failed": metrics.failed_operations,
            "throughput": metrics.throughput_ops_per_sec,
            "avg_latency_ms": metrics.avg_latency_ms,
            "p99_latency_ms": metrics.p99_latency_ms,
            "error_rate": metrics.error_rate,
        }

    def find_saturation_point(
        self,
        operation: Callable,
        initial_threads: int = 10,
        max_threads: int = 500,
    ) -> Dict[str, Any]:
        """Find system saturation point."""
        results = self.run_increasing_load(
            operation, initial_threads, max_threads, step=25
        )

        # Find where throughput starts declining
        max_throughput = 0
        saturation_threads = 0

        for i, result in enumerate(results):
            if result["throughput"] > max_throughput:
                max_throughput = result["throughput"]
                saturation_threads = result["threads"]
            elif result["throughput"] < max_throughput * 0.95:
                # Throughput declined significantly
                break

        return {
            "saturation_threads": saturation_threads,
            "max_throughput": max_throughput,
            "results": results,
        }

    def get_summary(self) -> Dict[str, Any]:
        """Get stress test summary."""
        if not self.results:
            return {}

        throughputs = [r["throughput"] for r in self.results]
        latencies = [r["avg_latency"] for r in self.results]

        return {
            "test_points": len(self.results),
            "max_throughput": max(throughputs) if throughputs else 0,
            "min_throughput": min(throughputs) if throughputs else 0,
            "avg_throughput": sum(throughputs) / len(throughputs) if throughputs else 0,
            "max_latency": max(latencies) if latencies else 0,
            "avg_latency": sum(latencies) / len(latencies) if latencies else 0,
        }


class EnduranceTest:
    """Long-running endurance test."""

    def __init__(self, operation: Callable, duration_hours: float = 1):
        """Initialize endurance test."""
        self.operation = operation
        self.duration_seconds = int(duration_hours * 3600)
        self.metrics: Dict[str, Any] = {}

    def run(self, num_threads: int = 50) -> Dict[str, Any]:
        """Run endurance test."""
        config = LoadConfig(
            pattern=LoadPattern.CONSTANT,
            duration_seconds=self.duration_seconds,
            initial_threads=num_threads,
            max_threads=num_threads,
            operations_per_thread=100000,
        )

        tester = LoadTester(self.operation, config)
        metrics = tester.run()

        self.metrics = {
            "duration_hours": self.duration_seconds / 3600,
            "threads": num_threads,
            "total_operations": metrics.total_operations,
            "successful": metrics.successful_operations,
            "failed": metrics.failed_operations,
            "throughput": metrics.throughput_ops_per_sec,
            "avg_latency_ms": metrics.avg_latency_ms,
            "error_rate": metrics.error_rate,
            "stability": metrics.error_rate < 1.0,
        }

        return self.metrics
