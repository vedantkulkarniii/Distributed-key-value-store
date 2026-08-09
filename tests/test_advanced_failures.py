"""Advanced failure scenario tests."""

import pytest
from src.raft.replication_metrics import ReplicationMetricsCollector
from src.raft.follower_catchup import FollowerCatchup
from src.raft.conflict_resolver import ConflictResolver
from src.raft.append_entries import HeartbeatTimer


class TestByzantineScenarios:
    """Byzantine failure scenario tests."""
    
    def test_slow_follower_detection(self):
        """Test detection of slow but responsive followers."""
        timer = HeartbeatTimer()
        timer.register_follower("f1")
        
        # Record slow but successful responses
        for i in range(10):
            timer.record_success("f1", response_time_ms=100.0)
        
        health = timer.get_follower_health("f1")
        assert health.is_healthy  # Slow but working
        assert health.response_time_ms > 50  # Average is high
    
    def test_intermittent_failures(self):
        """Test handling of intermittent failures."""
        metrics = ReplicationMetricsCollector()
        
        # Alternating success/failure
        for i in range(20):
            rep_id = metrics.start_replication("f1", 100, 10240)
            success = (i % 2) == 0
            metrics.complete_replication(rep_id, success)
        
        success_rate = metrics.get_success_rate("f1")
        assert success_rate == pytest.approx(50.0, abs=1.0)
    
    def test_asymmetric_failures(self):
        """Test asymmetric failures (f1->f2 works, f2->f1 fails)."""
        metrics = ReplicationMetricsCollector()
        
        # f1 can replicate to f2
        rep_id = metrics.start_replication("f2", 100, 10240)
        metrics.complete_replication(rep_id, True)
        
        # f2 cannot replicate to f1
        rep_id = metrics.start_replication("f1", 100, 10240)
        metrics.complete_replication(rep_id, False)
        
        m1 = metrics.get_metrics("f1")
        m2 = metrics.get_metrics("f2")
        
        assert m1.failed_replications == 1
        assert m2.successful_replications == 1


class TestNetworkPartitions:
    """Network partition scenario tests."""
    
    def test_partition_detection(self):
        """Test detection of network partitions."""
        timer = HeartbeatTimer()
        followers = ["f1", "f2", "f3"]
        
        for f in followers:
            timer.register_follower(f)
        
        # Partition affects f1, f2
        for f in ["f1", "f2"]:
            for _ in range(3):
                timer.record_failure(f)
        
        # f3 unaffected
        timer.record_success("f3", 5.0)
        
        unhealthy = timer.get_unhealthy_followers()
        assert "f1" in unhealthy
        assert "f2" in unhealthy
    
    def test_partition_recovery_asymmetry(self):
        """Test asymmetric recovery from partitions."""
        metrics = ReplicationMetricsCollector()
        
        # Partition: both f1 and f2 fail
        for f in ["f1", "f2"]:
            rep_id = metrics.start_replication(f, 100, 10240)
            metrics.complete_replication(rep_id, False)
        
        # Partial recovery: only f1 recovers
        rep_id = metrics.start_replication("f1", 100, 10240)
        metrics.complete_replication(rep_id, True)
        
        m1 = metrics.get_metrics("f1")
        m2 = metrics.get_metrics("f2")
        
        assert m1.successful_replications == 1
        assert m2.successful_replications == 0


class TestCascadingFailures:
    """Cascading failure scenario tests."""
    
    def test_cascading_failure_propagation(self):
        """Test propagation of cascading failures."""
        metrics = ReplicationMetricsCollector()
        
        # f1 fails
        rep_id = metrics.start_replication("f1", 100, 10240)
        metrics.complete_replication(rep_id, False)
        
        # f2 fails in response
        rep_id = metrics.start_replication("f2", 100, 10240)
        metrics.complete_replication(rep_id, False)
        
        # f3 fails next
        rep_id = metrics.start_replication("f3", 100, 10240)
        metrics.complete_replication(rep_id, False)
        
        summary = metrics.get_cluster_summary()
        assert summary["total_failed"] == 3
    
    def test_quorum_loss_recovery(self):
        """Test recovery from quorum loss."""
        catchup = FollowerCatchup(leader_last_index=1000)
        followers = ["f1", "f2", "f3", "f4", "f5"]
        
        for f in followers:
            catchup.register_follower(f)
        
        # 3 out of 5 fail (lost quorum)
        for f in followers[:3]:
            catchup.record_catch_up_failure(f)
        
        # Recovery: first two come back
        catchup.record_catch_up_success(followers[0], 1000)
        catchup.record_catch_up_success(followers[1], 1000)
        
        status = catchup.get_cluster_catch_up_status()
        assert status["caught_up_followers"] == 2
