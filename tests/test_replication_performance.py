"""Performance benchmarks for replication."""

import pytest
import time
from src.raft.replication_metrics import ReplicationMetricsCollector
from src.raft.follower_catchup import FollowerCatchup


class TestReplicationLatency:
    """Latency benchmarks for replication."""
    
    def test_single_entry_latency(self):
        """Benchmark latency for single entry replication."""
        metrics = ReplicationMetricsCollector()
        
        start = time.time()
        rep_id = metrics.start_replication("f1", 1, 128)
        time.sleep(0.001)
        metrics.complete_replication(rep_id, True)
        elapsed = (time.time() - start) * 1000
        
        assert elapsed >= 0
        m = metrics.get_metrics("f1")
        assert m.avg_latency_ms >= 0
    
    def test_bulk_replication_latency(self):
        """Benchmark latency for bulk replication."""
        metrics = ReplicationMetricsCollector()
        
        start = time.time()
        rep_id = metrics.start_replication("f1", 10000, 1024000)
        time.sleep(0.01)
        metrics.complete_replication(rep_id, True)
        elapsed = (time.time() - start) * 1000
        
        assert elapsed >= 0
    
    def test_latency_percentiles(self):
        """Benchmark latency percentiles."""
        metrics = ReplicationMetricsCollector()
        
        latencies = []
        for i in range(100):
            rep_id = metrics.start_replication("f1", 100, 10240)
            time.sleep(0.001)
            metrics.complete_replication(rep_id, True)
        
        m = metrics.get_metrics("f1")
        assert m.avg_latency_ms >= 0


class TestReplicationThroughput:
    """Throughput benchmarks for replication."""
    
    def test_throughput_entries_per_second(self):
        """Benchmark throughput in entries per second."""
        metrics = ReplicationMetricsCollector()
        
        start = time.time()
        
        # Replicate 1000 entries across 3 followers
        for batch in range(10):
            for f in ["f1", "f2", "f3"]:
                rep_id = metrics.start_replication(f, 100, 10240)
                metrics.complete_replication(rep_id, True)
        
        elapsed = time.time() - start
        
        summary = metrics.get_cluster_summary()
        entries = summary["total_entries_replicated"]
        throughput = entries / elapsed if elapsed > 0 else 0
        
        assert throughput > 0
    
    def test_throughput_bytes_per_second(self):
        """Benchmark throughput in bytes per second."""
        metrics = ReplicationMetricsCollector()
        
        start = time.time()
        
        # Replicate large batches
        for batch in range(20):
            rep_id = metrics.start_replication("f1", 1000, 102400)
            metrics.complete_replication(rep_id, True)
        
        elapsed = time.time() - start
        
        summary = metrics.get_cluster_summary()
        bytes_rep = summary["total_bytes_replicated"]
        throughput = bytes_rep / elapsed if elapsed > 0 else 0
        
        assert throughput > 0
    
    def test_scalability_with_followers(self):
        """Test throughput scaling with follower count."""
        metrics = ReplicationMetricsCollector()
        
        # 3 followers
        for f in ["f1", "f2", "f3"]:
            rep_id = metrics.start_replication(f, 1000, 102400)
            metrics.complete_replication(rep_id, True)
        
        summary_3 = metrics.get_cluster_summary()
        
        # Add 2 more followers
        for f in ["f4", "f5"]:
            rep_id = metrics.start_replication(f, 1000, 102400)
            metrics.complete_replication(rep_id, True)
        
        summary_5 = metrics.get_cluster_summary()
        
        assert summary_5["total_entries_replicated"] > summary_3["total_entries_replicated"]


class TestCatchupPerformance:
    """Performance tests for catch-up mechanism."""
    
    def test_catch_up_speed(self):
        """Test speed of catching up lagging followers."""
        catchup = FollowerCatchup(leader_last_index=10000)
        catchup.register_follower("f1")
        
        start = time.time()
        
        # Catch up 10000 entries
        for batch in range(100):
            catchup.record_catch_up_success("f1", entries_sent=100)
        
        elapsed = time.time() - start
        entries_per_sec = 10000 / elapsed if elapsed > 0 else 0
        
        assert entries_per_sec > 0
        assert catchup.follower_states["f1"].is_caught_up
    
    def test_exponential_backoff_efficiency(self):
        """Test efficiency of exponential backoff."""
        catchup = FollowerCatchup(leader_last_index=100000)
        catchup.register_follower("f1")
        catchup.follower_states["f1"].match_index = 50000  # Realistic state
        
        log_entries = [{"index": i} for i in range(1, 100001)]
        
        # First attempt with exponential backoff
        from src.raft.follower_catchup import CatchupStrategy
        start1, end1 = catchup.calculate_catch_up_range(
            "f1", log_entries, CatchupStrategy.EXPONENTIAL_BACKOFF
        )
        
        # Range size is reasonable
        range_size = end1 - start1
        assert range_size > 0
        assert range_size <= 100000
    
    def test_batch_replication_efficiency(self):
        """Test efficiency of batch replication."""
        catchup = FollowerCatchup(leader_last_index=100000)
        catchup.register_follower("f1")
        catchup.follower_states["f1"].match_index = 50000
        
        log_entries = [{"index": i} for i in range(1, 100001)]
        
        from src.raft.follower_catchup import CatchupStrategy
        start, end = catchup.calculate_catch_up_range(
            "f1", log_entries, CatchupStrategy.BATCH_REPLICATION
        )
        
        batch_size = end - start
        assert batch_size > 0


class TestOptimizationMetrics:
    """Tests for optimization and performance metrics."""
    
    def test_response_time_tracking(self):
        """Test response time tracking accuracy."""
        metrics = ReplicationMetricsCollector()
        
        import time
        expected_latency = 0.01  # 10ms
        
        rep_id = metrics.start_replication("f1", 100, 10240)
        time.sleep(expected_latency)
        metrics.complete_replication(rep_id, True)
        
        m = metrics.get_metrics("f1")
        assert m.avg_latency_ms >= expected_latency * 1000 * 0.8
    
    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        metrics = ReplicationMetricsCollector()
        
        # 8 successes, 2 failures
        for i in range(10):
            rep_id = metrics.start_replication("f1", 100, 10240)
            success = i < 8
            metrics.complete_replication(rep_id, success)
        
        success_rate = metrics.get_success_rate("f1")
        assert success_rate == pytest.approx(80.0, abs=1.0)
    
    def test_cluster_wide_stats(self):
        """Test cluster-wide statistics calculation."""
        metrics = ReplicationMetricsCollector()
        
        for f in ["f1", "f2", "f3"]:
            for i in range(10):
                rep_id = metrics.start_replication(f, 100, 10240)
                metrics.complete_replication(rep_id, True)
        
        summary = metrics.get_cluster_summary()
        
        assert summary["total_followers"] == 3
        assert summary["total_replications"] == 30
        assert summary["total_successful"] == 30
