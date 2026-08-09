"""Stress tests and system limits for replication."""

import pytest
from src.raft.replication_metrics import ReplicationMetricsCollector
from src.raft.follower_catchup import FollowerCatchup


class TestLargeBatchReplication:
    """Tests for large batch replication."""
    
    def test_large_batch_single_follower(self):
        """Test large batch replication to single follower."""
        metrics = ReplicationMetricsCollector()
        
        # Large batch: 50,000 entries = 5MB
        rep_id = metrics.start_replication("f1", 50000, 5242880)
        metrics.complete_replication(rep_id, True, last_index=50000)
        
        m = metrics.get_metrics("f1")
        assert m.entries_replicated == 50000
        assert m.bytes_replicated == 5242880
    
    def test_large_batch_multiple_followers(self):
        """Test large batch to multiple followers."""
        metrics = ReplicationMetricsCollector()
        
        for f in ["f1", "f2", "f3"]:
            rep_id = metrics.start_replication(f, 10000, 1048576)
            metrics.complete_replication(rep_id, True, last_index=10000)
        
        summary = metrics.get_cluster_summary()
        assert summary["total_entries_replicated"] == 30000


class TestHighFrequencyUpdates:
    """Tests for high-frequency updates."""
    
    def test_rapid_sequential_replications(self):
        """Test rapid sequential replications."""
        metrics = ReplicationMetricsCollector()
        
        # 1000 small replications in rapid succession
        for i in range(1000):
            rep_id = metrics.start_replication("f1", 10, 1024)
            metrics.complete_replication(rep_id, True)
        
        m = metrics.get_metrics("f1")
        assert m.total_replications == 1000
        assert m.entries_replicated == 10000
    
    def test_concurrent_follower_updates(self):
        """Test concurrent updates to multiple followers."""
        metrics = ReplicationMetricsCollector()
        
        followers = ["f1", "f2", "f3", "f4", "f5"]
        
        # 100 rounds of replication
        for round_num in range(100):
            for f in followers:
                rep_id = metrics.start_replication(f, 100, 10240)
                metrics.complete_replication(rep_id, True)
        
        summary = metrics.get_cluster_summary()
        assert summary["total_replications"] == 500
        assert summary["total_entries_replicated"] == 50000


class TestMemoryEfficiency:
    """Tests for memory efficiency."""
    
    def test_no_memory_leak_on_many_followers(self):
        """Test no memory leak with many followers."""
        catchup = FollowerCatchup(leader_last_index=100000)
        
        # Register 100 followers
        for i in range(100):
            catchup.register_follower(f"f{i}")
        
        assert len(catchup.follower_states) == 100
        
        # All should be independent
        catchup.record_catch_up_success("f0", 100)
        assert catchup.follower_states["f1"].match_index == 0
    
    def test_efficient_metric_collection(self):
        """Test efficient metric collection."""
        metrics = ReplicationMetricsCollector(max_samples=100)
        
        # Add 1000 replications (but keep only 100 samples)
        for i in range(1000):
            rep_id = metrics.start_replication("f1", 1, 100)
            metrics.complete_replication(rep_id, True)
        
        m = metrics.get_metrics("f1")
        # Should have kept only recent 100 samples
        assert len(m.latency_samples) <= 100


class TestSystemLimits:
    """Tests for system limits and boundaries."""
    
    def test_very_large_log_catchup(self):
        """Test catch-up with very large logs."""
        catchup = FollowerCatchup(leader_last_index=1000, max_batch_size=500)
        catchup.register_follower("f1")
        catchup.follower_states["f1"].match_index = 500
        catchup.follower_states["f1"].next_index = 501  # Set next_index
        
        log_entries = [{"index": i} for i in range(1, 1001)]
        
        from src.raft.follower_catchup import CatchupStrategy
        start, end = catchup.calculate_catch_up_range(
            "f1", log_entries, CatchupStrategy.BATCH_REPLICATION
        )
        
        # Should find a reasonable range
        assert start == 501  # next_index
        assert end <= 1001
        assert end > start
    
    def test_many_replications_to_one_follower(self):
        """Test many replications to one follower."""
        metrics = ReplicationMetricsCollector()
        
        # 10,000 replications to same follower
        for i in range(10000):
            rep_id = metrics.start_replication("f1", 1, 100)
            metrics.complete_replication(rep_id, True)
        
        m = metrics.get_metrics("f1")
        assert m.total_replications == 10000
    
    def test_many_followers_single_replication(self):
        """Test single batch to many followers."""
        metrics = ReplicationMetricsCollector()
        
        # One large replication to 100 followers
        for i in range(100):
            rep_id = metrics.start_replication(f"f{i}", 10000, 1024000)
            metrics.complete_replication(rep_id, True)
        
        summary = metrics.get_cluster_summary()
        assert summary["total_followers"] == 100
        assert summary["total_entries_replicated"] == 1000000


class TestStressScenarios:
    """Comprehensive stress scenarios."""
    
    def test_sustained_high_load(self):
        """Test sustained high load."""
        metrics = ReplicationMetricsCollector()
        
        # 100 followers, 100 rounds
        followers = [f"f{i}" for i in range(100)]
        
        for round_num in range(100):
            for f in followers:
                rep_id = metrics.start_replication(f, 1000, 102400)
                metrics.complete_replication(rep_id, True)
        
        summary = metrics.get_cluster_summary()
        assert summary["total_replications"] == 10000
        assert summary["total_entries_replicated"] == 10000000
    
    def test_alternating_load_stress(self):
        """Test alternating between high and low load."""
        metrics = ReplicationMetricsCollector()
        
        for cycle in range(10):
            # High load: 50 reps instead of 100 for speed
            for i in range(50):
                rep_id = metrics.start_replication("f1", 1000, 102400)
                metrics.complete_replication(rep_id, True)
            
            # Low load
            rep_id = metrics.start_replication("f1", 1, 100)
            metrics.complete_replication(rep_id, True)
        
        m = metrics.get_metrics("f1")
        # 50 * 10 * 1000 + 10 = 500010
        assert m.entries_replicated == 500010
