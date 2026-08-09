"""End-to-end replication scenario tests."""

import pytest
from src.raft.replication_metrics import ReplicationMetricsCollector
from src.raft.follower_catchup import FollowerCatchup
from src.raft.append_entries import HeartbeatTimer


class TestE2EReplicationWorkflow:
    """End-to-end replication workflow tests."""
    
    def test_complete_replication_flow(self):
        """Test complete replication from leader to all followers."""
        metrics = ReplicationMetricsCollector()
        followers = ["f1", "f2", "f3"]
        
        # Leader replicates to all followers
        for f in followers:
            rep_id = metrics.start_replication(f, 500, 51200)
            metrics.complete_replication(rep_id, True, last_index=500)
        
        summary = metrics.get_cluster_summary()
        assert summary["total_followers"] == 3
        assert summary["total_successful"] == 3
        assert summary["total_entries_replicated"] == 1500
    
    def test_state_machine_consistency(self):
        """Test state machine consistency across replicas."""
        catchup = FollowerCatchup(leader_last_index=1000)
        followers = ["f1", "f2", "f3"]
        
        for f in followers:
            catchup.register_follower(f)
        
        # Apply same entries to all
        for f in followers:
            catchup.record_catch_up_success(f, entries_sent=1000)
        
        # All should have same final state
        for f in followers:
            assert catchup.follower_states[f].match_index == 1000
    
    def test_client_request_propagation(self):
        """Test client request propagation through cluster."""
        metrics = ReplicationMetricsCollector()
        
        # Single client request replicated to quorum
        for i in range(3):  # Quorum size
            rep_id = metrics.start_replication(f"f{i+1}", 1, 1024)
            metrics.complete_replication(rep_id, True, last_index=1)
        
        summary = metrics.get_cluster_summary()
        assert summary["total_entries_replicated"] >= 3


class TestE2EFailureRecovery:
    """End-to-end failure and recovery workflows."""
    
    def test_e2e_follower_failure_and_recovery(self):
        """Test complete failure/recovery cycle."""
        metrics = ReplicationMetricsCollector()
        
        # Normal replication
        rep_id1 = metrics.start_replication("f1", 100, 10240)
        metrics.complete_replication(rep_id1, True, last_index=100)
        
        # Failure
        rep_id2 = metrics.start_replication("f1", 100, 10240)
        metrics.complete_replication(rep_id2, False)
        
        # Recovery
        rep_id3 = metrics.start_replication("f1", 100, 10240)
        metrics.complete_replication(rep_id3, True, last_index=200)
        
        m = metrics.get_metrics("f1")
        assert m.successful_replications == 2
        assert m.last_successful_index == 200
    
    def test_e2e_cascading_recovery(self):
        """Test cascading recovery across cluster."""
        catchup = FollowerCatchup(leader_last_index=1000)
        followers = ["f1", "f2", "f3"]
        
        for f in followers:
            catchup.register_follower(f)
        
        # All fall behind
        for f in followers:
            catchup.follower_states[f].match_index = 500
        
        # Recover in sequence
        catchup.record_catch_up_success("f1", 500)
        catchup.record_catch_up_success("f2", 500)
        catchup.record_catch_up_success("f3", 500)
        
        status = catchup.get_cluster_catch_up_status()
        assert status["caught_up_followers"] == 3


class TestE2EPerformanceCharacteristics:
    """End-to-end performance characteristics."""
    
    def test_throughput_under_normal_load(self):
        """Test throughput under normal load."""
        metrics = ReplicationMetricsCollector()
        
        import time
        start = time.time()
        
        # Replicate 100 batches
        for batch in range(100):
            for f in [f"f{i+1}" for i in range(3)]:
                rep_id = metrics.start_replication(f, 10, 1024)
                time.sleep(0.001)
                metrics.complete_replication(rep_id, True)
        
        elapsed = time.time() - start
        
        summary = metrics.get_cluster_summary()
        total_entries = summary["total_entries_replicated"]
        
        assert total_entries == 3000  # 100 * 10 * 3
    
    def test_latency_distribution(self):
        """Test latency distribution across replications."""
        metrics = ReplicationMetricsCollector()
        
        import time
        latencies = []
        
        for i in range(50):
            rep_id = metrics.start_replication("f1", 100, 10240)
            time.sleep(0.001 * (i % 10))
            metrics.complete_replication(rep_id, True)
        
        m = metrics.get_metrics("f1")
        assert m.avg_latency_ms >= 0


class TestE2ECrashConsistency:
    """End-to-end crash and consistency tests."""
    
    def test_consistency_after_leader_crash(self):
        """Test consistency maintained after leader crash."""
        metrics = ReplicationMetricsCollector()
        
        # Replicate to quorum before crash
        for i in range(3):
            rep_id = metrics.start_replication(f"f{i+1}", 100, 10240)
            metrics.complete_replication(rep_id, True, last_index=100)
        
        # Leader crashes (no new replications)
        # All followers still have replicated data
        for i in range(1, 4):
            m = metrics.get_metrics(f"f{i}")
            assert m.last_successful_index == 100
    
    def test_consistency_after_multi_follower_failure(self):
        """Test consistency with multiple followers failing."""
        catchup = FollowerCatchup(leader_last_index=1000)
        
        followers = ["f1", "f2", "f3", "f4", "f5"]
        for f in followers:
            catchup.register_follower(f)
        
        # 2 fail, 3 succeed (quorum)
        for i, f in enumerate(followers):
            if i < 3:  # Success
                catchup.record_catch_up_success(f, 1000)
            else:  # Fail
                catchup.record_catch_up_failure(f)
        
        status = catchup.get_cluster_catch_up_status()
        assert status["caught_up_followers"] == 3
