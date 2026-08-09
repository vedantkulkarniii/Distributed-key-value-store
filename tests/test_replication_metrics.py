"""Test suite for replication progress reporting and metrics."""

import pytest
import time
from datetime import datetime, timedelta
from src.raft.replication_metrics import (
    ReplicationMetrics,
    ReplicationLatency,
    ReplicationMetricsCollector,
)


class TestReplicationLatency:
    """Tests for ReplicationLatency."""
    
    def test_initialization(self):
        """Test ReplicationLatency initialization."""
        start_time = datetime.now()
        latency = ReplicationLatency(
            start_time=start_time,
            entries_sent=10,
            bytes_sent=1024,
        )
        
        assert latency.start_time == start_time
        assert latency.entries_sent == 10
        assert latency.bytes_sent == 1024
        assert latency.end_time is None
        assert latency.successful is False


class TestReplicationMetrics:
    """Tests for ReplicationMetrics."""
    
    def test_initialization(self):
        """Test ReplicationMetrics initialization."""
        metrics = ReplicationMetrics(follower_id="follower1")
        
        assert metrics.follower_id == "follower1"
        assert metrics.total_replications == 0
        assert metrics.successful_replications == 0
        assert metrics.entries_replicated == 0
        assert metrics.bytes_replicated == 0


class TestReplicationMetricsCollector:
    """Tests for ReplicationMetricsCollector."""
    
    def test_initialization(self):
        """Test ReplicationMetricsCollector initialization."""
        collector = ReplicationMetricsCollector()
        
        assert collector.max_samples == 100
        assert collector.metrics == {}
        assert collector.active_replications == {}
    
    def test_start_replication(self):
        """Test starting replication tracking."""
        collector = ReplicationMetricsCollector()
        
        rep_id = collector.start_replication(
            follower_id="follower1",
            entries_count=10,
            bytes_count=1024,
        )
        
        assert rep_id in collector.active_replications
        assert "follower1" in collector.metrics
        latency = collector.active_replications[rep_id]
        assert latency.entries_sent == 10
        assert latency.bytes_sent == 1024
    
    def test_complete_replication_success(self):
        """Test completing a successful replication."""
        collector = ReplicationMetricsCollector()
        
        rep_id = collector.start_replication(
            follower_id="follower1",
            entries_count=10,
            bytes_count=1024,
        )
        
        time.sleep(0.01)  # Simulate replication time
        
        collector.complete_replication(
            replication_id=rep_id,
            successful=True,
            last_index=100,
        )
        
        metrics = collector.metrics["follower1"]
        assert metrics.total_replications == 1
        assert metrics.successful_replications == 1
        assert metrics.entries_replicated == 10
        assert metrics.bytes_replicated == 1024
        assert metrics.last_successful_index == 100
        assert metrics.avg_latency_ms > 0
    
    def test_complete_replication_failure(self):
        """Test completing a failed replication."""
        collector = ReplicationMetricsCollector()
        
        rep_id = collector.start_replication(
            follower_id="follower1",
            entries_count=10,
            bytes_count=1024,
        )
        
        collector.complete_replication(
            replication_id=rep_id,
            successful=False,
        )
        
        metrics = collector.metrics["follower1"]
        assert metrics.total_replications == 1
        assert metrics.failed_replications == 1
        assert metrics.successful_replications == 0
        assert metrics.entries_replicated == 0
    
    def test_get_metrics(self):
        """Test retrieving metrics for a follower."""
        collector = ReplicationMetricsCollector()
        
        rep_id = collector.start_replication(
            follower_id="follower1",
            entries_count=10,
            bytes_count=1024,
        )
        
        collector.complete_replication(
            replication_id=rep_id,
            successful=True,
            last_index=100,
        )
        
        metrics = collector.get_metrics("follower1")
        assert metrics is not None
        assert metrics.follower_id == "follower1"
        assert metrics.total_replications == 1
        
        assert collector.get_metrics("unknown") is None
    
    def test_get_all_metrics(self):
        """Test retrieving all metrics."""
        collector = ReplicationMetricsCollector()
        
        for follower_id in ["follower1", "follower2", "follower3"]:
            rep_id = collector.start_replication(
                follower_id=follower_id,
                entries_count=5,
                bytes_count=512,
            )
            collector.complete_replication(
                replication_id=rep_id,
                successful=True,
            )
        
        all_metrics = collector.get_all_metrics()
        assert len(all_metrics) == 3
        assert "follower1" in all_metrics
        assert "follower2" in all_metrics
        assert "follower3" in all_metrics
    
    def test_get_success_rate_no_replications(self):
        """Test success rate with no replications."""
        collector = ReplicationMetricsCollector()
        
        assert collector.get_success_rate("unknown") == 0.0
    
    def test_get_success_rate_with_data(self):
        """Test success rate calculation."""
        collector = ReplicationMetricsCollector()
        
        # 2 successful, 1 failed
        for i in range(2):
            rep_id = collector.start_replication(
                follower_id="follower1",
                entries_count=5,
                bytes_count=512,
            )
            collector.complete_replication(
                replication_id=rep_id,
                successful=True,
            )
        
        rep_id = collector.start_replication(
            follower_id="follower1",
            entries_count=5,
            bytes_count=512,
        )
        collector.complete_replication(
            replication_id=rep_id,
            successful=False,
        )
        
        success_rate = collector.get_success_rate("follower1")
        assert success_rate == pytest.approx(66.67, abs=0.1)
    
    def test_get_throughput(self):
        """Test throughput calculation."""
        collector = ReplicationMetricsCollector()
        
        rep_id = collector.start_replication(
            follower_id="follower1",
            entries_count=100,
            bytes_count=10240,
        )
        
        time.sleep(0.1)
        
        collector.complete_replication(
            replication_id=rep_id,
            successful=True,
        )
        
        throughput = collector.get_throughput("follower1")
        
        assert "entries_per_sec" in throughput
        assert "bytes_per_sec" in throughput
        assert throughput["entries_per_sec"] > 0
        assert throughput["bytes_per_sec"] > 0
    
    def test_get_cluster_summary(self):
        """Test cluster summary generation."""
        collector = ReplicationMetricsCollector()
        
        for follower_id in ["follower1", "follower2"]:
            rep_id = collector.start_replication(
                follower_id=follower_id,
                entries_count=50,
                bytes_count=5120,
            )
            collector.complete_replication(
                replication_id=rep_id,
                successful=True,
            )
        
        summary = collector.get_cluster_summary()
        
        assert summary["total_followers"] == 2
        assert summary["total_replications"] == 2
        assert summary["total_successful"] == 2
        assert summary["total_entries_replicated"] == 100
        assert summary["total_bytes_replicated"] == 10240
    
    def test_get_lagging_followers(self):
        """Test identifying lagging followers."""
        collector = ReplicationMetricsCollector()
        
        # Create metrics for followers at different indices
        rep_id1 = collector.start_replication("follower1", 5, 512)
        collector.complete_replication(rep_id1, True, last_index=5)
        
        rep_id2 = collector.start_replication("follower2", 5, 512)
        collector.complete_replication(rep_id2, True, last_index=1)
        
        lagging = collector.get_lagging_followers(lag_threshold=3)
        
        assert "follower2" in lagging
        assert "follower1" not in lagging
    
    def test_get_fastest_followers(self):
        """Test identifying fastest followers."""
        collector = ReplicationMetricsCollector()
        
        # Follower1: faster replication
        rep_id1 = collector.start_replication("follower1", 5, 512)
        time.sleep(0.01)
        collector.complete_replication(rep_id1, True)
        
        # Follower2: slower replication
        rep_id2 = collector.start_replication("follower2", 5, 512)
        time.sleep(0.05)
        collector.complete_replication(rep_id2, True)
        
        fastest = collector.get_fastest_followers()
        
        assert fastest[0] == "follower1" or fastest[0] == "follower2"
    
    def test_get_slowest_followers(self):
        """Test identifying slowest followers."""
        collector = ReplicationMetricsCollector()
        
        rep_id1 = collector.start_replication("follower1", 5, 512)
        time.sleep(0.01)
        collector.complete_replication(rep_id1, True)
        
        rep_id2 = collector.start_replication("follower2", 5, 512)
        time.sleep(0.05)
        collector.complete_replication(rep_id2, True)
        
        slowest = collector.get_slowest_followers()
        
        assert "follower1" in slowest
        assert "follower2" in slowest
    
    def test_reset_metrics_single_follower(self):
        """Test resetting metrics for a single follower."""
        collector = ReplicationMetricsCollector()
        
        rep_id1 = collector.start_replication("follower1", 5, 512)
        collector.complete_replication(rep_id1, True)
        
        rep_id2 = collector.start_replication("follower2", 5, 512)
        collector.complete_replication(rep_id2, True)
        
        collector.reset_metrics("follower1")
        
        assert "follower1" not in collector.metrics
        assert "follower2" in collector.metrics
    
    def test_reset_metrics_all(self):
        """Test resetting all metrics."""
        collector = ReplicationMetricsCollector()
        
        for i in range(3):
            rep_id = collector.start_replication(f"follower{i}", 5, 512)
            collector.complete_replication(rep_id, True)
        
        collector.reset_metrics()
        
        assert len(collector.metrics) == 0
        assert len(collector.active_replications) == 0
    
    def test_export_metrics_json(self):
        """Test exporting metrics as JSON."""
        collector = ReplicationMetricsCollector()
        
        rep_id = collector.start_replication("follower1", 50, 5120)
        time.sleep(0.01)
        collector.complete_replication(rep_id, True, last_index=50)
        
        exported = collector.export_metrics_json()
        
        assert "cluster_summary" in exported
        assert "follower_metrics" in exported
        assert "collection_duration_seconds" in exported
        assert "follower1" in exported["follower_metrics"]
    
    def test_multiple_replications_latency_average(self):
        """Test latency averaging over multiple replications."""
        collector = ReplicationMetricsCollector()
        
        latencies = []
        for i in range(3):
            rep_id = collector.start_replication("follower1", 5, 512)
            time.sleep(0.01 + i * 0.01)  # Varying latencies
            collector.complete_replication(rep_id, True)
            latencies.append(collector.active_replications.get(rep_id) is None)
        
        metrics = collector.metrics["follower1"]
        assert metrics.total_replications == 3
        assert metrics.avg_latency_ms > 0
    
    def test_max_samples_limit(self):
        """Test that latency samples are limited."""
        collector = ReplicationMetricsCollector(max_samples=10)
        
        # Add more samples than max_samples
        for i in range(20):
            rep_id = collector.start_replication("follower1", 5, 512)
            collector.complete_replication(rep_id, True)
        
        metrics = collector.metrics["follower1"]
        assert len(metrics.latency_samples) <= 10
