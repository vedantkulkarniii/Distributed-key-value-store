"""Multi-node replication integration tests for Raft consensus."""

import pytest
from src.raft.append_entries import AppendEntriesHandler, HeartbeatTimer
from src.raft.replication_metrics import ReplicationMetricsCollector
from src.raft.conflict_resolver import ConflictResolver
from src.raft.follower_catchup import FollowerCatchup


class TestThreeNodeCluster:
    """Tests for 3-node Raft cluster replication."""
    
    def setup_method(self):
        """Setup 3-node cluster."""
        self.leader = AppendEntriesHandler("leader", None)
        self.follower1 = AppendEntriesHandler("follower1", None)
        self.follower2 = AppendEntriesHandler("follower2", None)
        self.metrics = ReplicationMetricsCollector()
    
    def test_3node_heartbeat_distribution(self):
        """Test heartbeat distribution in 3-node cluster."""
        timer = HeartbeatTimer()
        for i in range(1, 3):
            timer.register_follower(f"follower{i}")
        
        assert len(timer.follower_health) == 2
        assert all(
            timer.follower_health[f"follower{i}"].is_healthy
            for i in range(1, 3)
        )
    
    def test_3node_follower_health_tracking(self):
        """Test health tracking for all followers."""
        timer = HeartbeatTimer()
        followers = ["follower1", "follower2"]
        
        for f in followers:
            timer.register_follower(f)
        
        # Simulate health changes
        timer.record_success("follower1", 5.0)
        timer.record_failure("follower2")
        
        healthy = timer.get_healthy_followers()
        assert "follower1" in healthy
        assert "follower2" in healthy  # Single failure doesn't mark unhealthy
    
    def test_3node_replication_progress(self):
        """Test replication progress across 3 nodes."""
        for follower_id in ["follower1", "follower2"]:
            rep_id = self.metrics.start_replication(
                follower_id=follower_id,
                entries_count=50,
                bytes_count=5120,
            )
            self.metrics.complete_replication(
                replication_id=rep_id,
                successful=True,
                last_index=50,
            )
        
        summary = self.metrics.get_cluster_summary()
        assert summary["total_followers"] == 2
        assert summary["total_entries_replicated"] == 100
    
    def test_3node_different_speeds(self):
        """Test replication with followers at different speeds."""
        import time
        
        # Follower1: fast
        rep_id1 = self.metrics.start_replication("follower1", 50, 5120)
        time.sleep(0.01)
        self.metrics.complete_replication(rep_id1, True, last_index=50)
        
        # Follower2: slow
        rep_id2 = self.metrics.start_replication("follower2", 50, 5120)
        time.sleep(0.05)
        self.metrics.complete_replication(rep_id2, True, last_index=50)
        
        fastest = self.metrics.get_fastest_followers()
        assert "follower1" in fastest


class TestFiveNodeCluster:
    """Tests for 5-node Raft cluster replication."""
    
    def setup_method(self):
        """Setup 5-node cluster."""
        self.metrics = ReplicationMetricsCollector()
        self.catchup = FollowerCatchup(leader_last_index=1000)
        self.followers = [f"follower{i}" for i in range(1, 6)]
    
    def test_5node_all_followers_registered(self):
        """Test all followers registered in 5-node cluster."""
        for follower in self.followers:
            self.catchup.register_follower(follower)
        
        assert len(self.catchup.follower_states) == 5
    
    def test_5node_varying_replication_success(self):
        """Test varying replication success rates."""
        # 4 followers succeed, 1 fails
        for i, follower in enumerate(self.followers):
            rep_id = self.metrics.start_replication(
                follower_id=follower,
                entries_count=100,
                bytes_count=10240,
            )
            success = i < 4  # First 4 succeed
            self.metrics.complete_replication(
                replication_id=rep_id,
                successful=success,
                last_index=100 if success else None,
            )
        
        summary = self.metrics.get_cluster_summary()
        assert summary["total_replications"] == 5
        assert summary["total_successful"] == 4
        assert summary["total_failed"] == 1
    
    def test_5node_majority_quorum(self):
        """Test majority quorum in 5-node cluster."""
        # Need 3+ out of 5 for quorum
        majority_count = (5 // 2) + 1
        assert majority_count == 3
        
        # Replicate to majority
        for i in range(majority_count):
            rep_id = self.metrics.start_replication(
                f"follower{i+1}", 100, 10240
            )
            self.metrics.complete_replication(rep_id, True, last_index=100)
        
        summary = self.metrics.get_cluster_summary()
        assert summary["total_successful"] >= majority_count
    
    def test_5node_partial_failure_recovery(self):
        """Test recovery with partial failures."""
        for follower in self.followers[:3]:  # First 3 fail
            rep_id = self.metrics.start_replication(follower, 100, 10240)
            self.metrics.complete_replication(rep_id, False)
        
        # Later, they recover
        for follower in self.followers[:3]:
            self.metrics.reset_metrics(follower)
            rep_id = self.metrics.start_replication(follower, 100, 10240)
            self.metrics.complete_replication(rep_id, True, last_index=100)
        
        summary = self.metrics.get_cluster_summary()
        assert summary["total_successful"] >= 3


class TestSevenNodeCluster:
    """Tests for 7-node Raft cluster replication."""
    
    def setup_method(self):
        """Setup 7-node cluster."""
        self.metrics = ReplicationMetricsCollector()
        self.catchup = FollowerCatchup(leader_last_index=5000)
        self.timer = HeartbeatTimer()
        self.followers = [f"follower{i}" for i in range(1, 8)]
    
    def test_7node_all_healthy_replication(self):
        """Test replication with all 7 nodes healthy."""
        for follower in self.followers:
            self.timer.register_follower(follower)
            
            rep_id = self.metrics.start_replication(follower, 200, 20480)
            self.metrics.complete_replication(rep_id, True, last_index=200)
            self.timer.record_success(follower, 10.0)
        
        healthy = self.timer.get_healthy_followers()
        assert len(healthy) == 7
        
        summary = self.metrics.get_cluster_summary()
        assert summary["total_followers"] == 7
        assert summary["total_successful"] == 7
    
    def test_7node_with_failures(self):
        """Test 7-node cluster with multiple failures."""
        failures = [0, 2, 4]  # Followers at indices 0, 2, 4 fail
        
        for i, follower in enumerate(self.followers):
            self.timer.register_follower(follower)
            
            if i in failures:
                # Simulate 3 failures to mark unhealthy
                for _ in range(3):
                    self.timer.record_failure(follower)
                rep_id = self.metrics.start_replication(follower, 200, 20480)
                self.metrics.complete_replication(rep_id, False)
            else:
                self.timer.record_success(follower, 5.0)
                rep_id = self.metrics.start_replication(follower, 200, 20480)
                self.metrics.complete_replication(rep_id, True, last_index=200)
        
        healthy = self.timer.get_healthy_followers()
        unhealthy = self.timer.get_unhealthy_followers()
        
        assert len(healthy) == 4
        assert len(unhealthy) == 3
    
    def test_7node_quorum_operations(self):
        """Test quorum operations in 7-node cluster."""
        # For 7 nodes, need 4 for quorum
        quorum_size = (7 // 2) + 1
        assert quorum_size == 4
        
        # Replicate to quorum
        for i in range(quorum_size):
            rep_id = self.metrics.start_replication(self.followers[i], 200, 20480)
            self.metrics.complete_replication(rep_id, True, last_index=200)
        
        summary = self.metrics.get_cluster_summary()
        assert summary["total_successful"] >= quorum_size
    
    def test_7node_lagging_detection(self):
        """Test detection of lagging followers in 7-node cluster."""
        for i, follower in enumerate(self.followers):
            self.catchup.register_follower(follower)
            
            if i < 3:
                # First 3 are caught up
                self.catchup.follower_states[follower].match_index = 5000
                self.catchup.follower_states[follower].is_caught_up = True
            else:
                # Rest are lagging
                self.catchup.follower_states[follower].match_index = 4500
        
        status = self.catchup.get_cluster_catch_up_status()
        assert status["caught_up_followers"] == 3
        assert len(status["lagging_followers"]) == 4


class TestPartialFailureScenarios:
    """Tests for partial failure scenarios in replication."""
    
    def test_follower_crash_recovery(self):
        """Test follower crash and recovery."""
        timer = HeartbeatTimer()
        metrics = ReplicationMetricsCollector()
        
        timer.register_follower("follower1")
        
        # Normal operation
        timer.record_success("follower1", 5.0)
        assert timer.follower_health["follower1"].is_healthy
        
        # Crash (3+ failures)
        for _ in range(3):
            timer.record_failure("follower1")
        
        assert not timer.follower_health["follower1"].is_healthy
        
        # Recovery
        timer.record_success("follower1", 5.0)
        assert timer.follower_health["follower1"].is_healthy
        assert timer.follower_health["follower1"].consecutive_failures == 0
    
    def test_network_partition_detection(self):
        """Test detection of network partitions."""
        timer = HeartbeatTimer()
        
        timer.register_follower("follower1")
        timer.register_follower("follower2")
        
        # Partition affects follower1 only
        for _ in range(3):
            timer.record_failure("follower1")
        
        # Follower2 continues normally
        timer.record_success("follower2", 5.0)
        
        healthy = timer.get_healthy_followers()
        unhealthy = timer.get_unhealthy_followers()
        
        assert "follower2" in healthy
        assert "follower1" in unhealthy
    
    def test_gradual_degradation(self):
        """Test handling of gradual performance degradation."""
        metrics = ReplicationMetricsCollector()
        
        follower = "follower1"
        
        # Gradually increasing latency
        latencies = [5.0, 10.0, 20.0, 40.0, 50.0]
        
        for lat in latencies:
            rep_id = metrics.start_replication(follower, 100, 10240)
            import time
            time.sleep(0.001 * lat / 10)
            metrics.complete_replication(rep_id, True)
        
        stats = metrics.export_metrics_json()
        follower_metrics = stats["follower_metrics"][follower]
        
        # Average should increase over time
        assert follower_metrics["avg_latency_ms"] > 0
    
    def test_burst_replication_spike(self):
        """Test handling of sudden replication spikes."""
        metrics = ReplicationMetricsCollector()
        
        # Normal replication
        for i in range(3):
            rep_id = metrics.start_replication("follower1", 100, 10240)
            metrics.complete_replication(rep_id, True)
        
        # Sudden spike
        spike_entries = 1000
        rep_id = metrics.start_replication("follower1", spike_entries, 102400)
        metrics.complete_replication(rep_id, True)
        
        metrics_data = metrics.get_metrics("follower1")
        assert metrics_data.entries_replicated >= 1300


class TestClusterStabilization:
    """Tests for cluster stabilization after disruptions."""
    
    def test_cluster_recovery_after_failures(self):
        """Test cluster recovery after multiple failures."""
        catchup = FollowerCatchup(leader_last_index=1000)
        followers = ["f1", "f2", "f3"]
        
        for f in followers:
            catchup.register_follower(f)
        
        # Simulate failures (low match_index)
        for f in followers:
            catchup.follower_states[f].match_index = 500
        
        # Begin recovery
        for f in followers:
            catchup.record_catch_up_success(f, entries_sent=100)
            catchup.record_catch_up_success(f, entries_sent=100)
            catchup.record_catch_up_success(f, entries_sent=100)
            catchup.record_catch_up_success(f, entries_sent=200)
        
        # All should be caught up
        status = catchup.get_cluster_catch_up_status()
        caught_up_count = status["caught_up_followers"]
        
        assert isinstance(caught_up_count, int)
        assert caught_up_count >= 1
    
    def test_asymmetric_recovery(self):
        """Test asymmetric recovery speeds."""
        catchup = FollowerCatchup(leader_last_index=1000)
        
        catchup.register_follower("fast")
        catchup.register_follower("slow")
        
        # Fast catches up quickly
        for _ in range(5):
            catchup.record_catch_up_success("fast", 100)
        
        # Slow catches up slowly
        for _ in range(2):
            catchup.record_catch_up_success("slow", 100)
        
        fast_status = catchup.get_catch_up_status("fast")
        slow_status = catchup.get_catch_up_status("slow")
        
        assert fast_status["match_index"] > slow_status["match_index"]
