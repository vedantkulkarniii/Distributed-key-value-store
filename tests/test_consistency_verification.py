"""Consistency verification tests for log replication."""

import pytest
from src.raft.replication_metrics import ReplicationMetricsCollector
from src.raft.follower_catchup import FollowerCatchup


class TestLogConsistency:
    """Tests for log consistency across cluster."""
    
    def test_all_followers_consistent_state(self):
        """Test all followers reach consistent state."""
        catchup = FollowerCatchup(leader_last_index=100)
        followers = ["f1", "f2", "f3"]
        
        for f in followers:
            catchup.register_follower(f)
            catchup.record_catch_up_success(f, entries_sent=100)
        
        for f in followers:
            assert catchup.follower_states[f].match_index == 100
    
    def test_log_divergence_prevention(self):
        """Test prevention of log divergence."""
        metrics = ReplicationMetricsCollector()
        
        # Same data replicated consistently
        for follower in ["f1", "f2", "f3"]:
            rep_id = metrics.start_replication(follower, 100, 10240)
            metrics.complete_replication(rep_id, True, last_index=100)
        
        for follower in ["f1", "f2", "f3"]:
            m = metrics.get_metrics(follower)
            assert m.last_successful_index == 100
    
    def test_index_convergence(self):
        """Test convergence of match_index across followers."""
        catchup = FollowerCatchup(leader_last_index=500)
        
        followers = ["f1", "f2", "f3"]
        for f in followers:
            catchup.register_follower(f)
        
        # Gradually increase indices
        for round_num in range(5):
            entries_per_round = 100
            for f in followers:
                catchup.record_catch_up_success(f, entries_per_round)
        
        indices = [
            catchup.follower_states[f].match_index for f in followers
        ]
        
        # All should be at 500
        assert all(idx == 500 for idx in indices)


class TestMajorityAgreement:
    """Tests for majority agreement in replication."""
    
    def test_majority_commit_decision(self):
        """Test majority-based commit decisions."""
        metrics = ReplicationMetricsCollector()
        
        followers = ["f1", "f2", "f3", "f4", "f5"]
        
        # 3 out of 5 replicate successfully
        for i, f in enumerate(followers):
            rep_id = metrics.start_replication(f, 100, 10240)
            success = i < 3
            metrics.complete_replication(rep_id, success)
        
        summary = metrics.get_cluster_summary()
        assert summary["total_successful"] >= 3
    
    def test_quorum_safety(self):
        """Test quorum safety properties."""
        catchup = FollowerCatchup(leader_last_index=1000)
        
        followers = ["f1", "f2", "f3", "f4", "f5", "f6", "f7"]
        for f in followers:
            catchup.register_follower(f)
        
        # 4/7 replicate (quorum)
        for i in range(4):
            catchup.record_catch_up_success(followers[i], 1000)
        
        status = catchup.get_cluster_catch_up_status()
        assert status["caught_up_followers"] >= 4


class TestConsistencyGuarantees:
    """Tests for consistency guarantees."""
    
    def test_no_duplicate_commits(self):
        """Test no duplicate entries get committed."""
        metrics = ReplicationMetricsCollector()
        
        # Same entry replicated
        rep_id1 = metrics.start_replication("f1", 1, 100)
        metrics.complete_replication(rep_id1, True, last_index=1)
        
        rep_id2 = metrics.start_replication("f1", 1, 100)
        metrics.complete_replication(rep_id2, True, last_index=1)
        
        m = metrics.get_metrics("f1")
        assert m.last_successful_index == 1
    
    def test_ordered_replication(self):
        """Test entries replicate in order."""
        catchup = FollowerCatchup(leader_last_index=100)
        catchup.register_follower("f1")
        
        # Replicate in sequence
        for i in range(10):
            catchup.record_catch_up_success("f1", 10)
            assert catchup.follower_states["f1"].match_index == (i+1) * 10
    
    def test_commit_dependency_ordering(self):
        """Test commit respects entry ordering."""
        catchup = FollowerCatchup(leader_last_index=1000)
        followers = ["f1", "f2", "f3"]
        
        for f in followers:
            catchup.register_follower(f)
        
        # Must replicate in order
        for batch in range(5):
            entries_sent = 200
            for f in followers:
                catchup.record_catch_up_success(f, entries_sent)
        
        # All should be at 1000
        for f in followers:
            assert catchup.follower_states[f].match_index == 1000
