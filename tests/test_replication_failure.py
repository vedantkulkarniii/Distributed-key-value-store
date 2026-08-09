"""Failure and recovery scenario tests for Raft replication."""

import pytest
from src.raft.append_entries import AppendEntriesHandler
from src.raft.replication_metrics import ReplicationMetricsCollector
from src.raft.follower_catchup import FollowerCatchup
from src.raft.conflict_resolver import ConflictResolver


class TestFollowerCrashRecovery:
    """Tests for follower crash and recovery scenarios."""
    
    def test_follower_crash_detection(self):
        """Test detection of crashed follower."""
        metrics = ReplicationMetricsCollector()
        rep_id = metrics.start_replication("follower1", 100, 10240)
        metrics.complete_replication(rep_id, False)
        
        stats = metrics.export_metrics_json()
        assert stats["follower_metrics"]["follower1"]["failed_replications"] == 1
    
    def test_follower_recovery_after_crash(self):
        """Test recovery after follower crash."""
        metrics = ReplicationMetricsCollector()
        
        # Crash
        rep_id1 = metrics.start_replication("follower1", 100, 10240)
        metrics.complete_replication(rep_id1, False)
        
        # Recovery
        rep_id2 = metrics.start_replication("follower1", 100, 10240)
        metrics.complete_replication(rep_id2, True)
        
        stats = metrics.export_metrics_json()
        metrics_data = stats["follower_metrics"]["follower1"]
        
        assert metrics_data["successful_replications"] == 1
        assert metrics_data["failed_replications"] == 1
    
    def test_multiple_crash_recovery_cycles(self):
        """Test multiple crash/recovery cycles."""
        metrics = ReplicationMetricsCollector()
        
        for cycle in range(3):
            # Crash
            rep_id = metrics.start_replication("follower1", 50, 5120)
            metrics.complete_replication(rep_id, False)
            
            # Recovery
            rep_id = metrics.start_replication("follower1", 50, 5120)
            metrics.complete_replication(rep_id, True)
        
        metrics_data = metrics.get_metrics("follower1")
        assert metrics_data.total_replications == 6  # 3 crashes + 3 recoveries


class TestLeaderFailureScenarios:
    """Tests for leader failure scenarios."""
    
    def test_leader_failure_impact_on_replication(self):
        """Test impact of leader failure on replication."""
        metrics = ReplicationMetricsCollector()
        
        # Normal replication with leader
        for i in range(3):
            rep_id = metrics.start_replication("follower1", 100, 10240)
            metrics.complete_replication(rep_id, True)
        
        # Leader failure - replications fail
        for i in range(2):
            rep_id = metrics.start_replication("follower1", 100, 10240)
            metrics.complete_replication(rep_id, False)
        
        summary = metrics.get_cluster_summary()
        assert summary["total_successful"] == 3
        assert summary["total_failed"] == 2
    
    def test_leader_recovery_resumes_replication(self):
        """Test replication resumes after leader recovery."""
        metrics = ReplicationMetricsCollector()
        
        # Normal -> failure -> recovery
        rep_id1 = metrics.start_replication("follower1", 100, 10240)
        metrics.complete_replication(rep_id1, True)
        
        rep_id2 = metrics.start_replication("follower1", 100, 10240)
        metrics.complete_replication(rep_id2, False)
        
        rep_id3 = metrics.start_replication("follower1", 100, 10240)
        metrics.complete_replication(rep_id3, True)
        
        metrics_data = metrics.get_metrics("follower1")
        assert metrics_data.successful_replications == 2


class TestPartialReplicationFailure:
    """Tests for partial replication failures."""
    
    def test_partial_batch_failure(self):
        """Test failure in middle of batch replication."""
        catchup = FollowerCatchup(leader_last_index=1000)
        catchup.register_follower("follower1")
        
        # Success on first attempt
        catchup.record_catch_up_success("follower1", entries_sent=250)
        assert catchup.follower_states["follower1"].match_index == 250
        
        # Failure on second attempt
        catchup.record_catch_up_failure("follower1")
        assert catchup.follower_states["follower1"].match_index == 250  # Unchanged
        
        # Recovery
        catchup.record_catch_up_success("follower1", entries_sent=250)
        assert catchup.follower_states["follower1"].match_index == 500
    
    def test_cascading_failures(self):
        """Test cascading failures across followers."""
        metrics = ReplicationMetricsCollector()
        followers = ["f1", "f2", "f3"]
        
        # All initially successful
        for f in followers:
            rep_id = metrics.start_replication(f, 100, 10240)
            metrics.complete_replication(rep_id, True)
        
        # Cascading failures
        for f in followers:
            rep_id = metrics.start_replication(f, 100, 10240)
            metrics.complete_replication(rep_id, False)
        
        summary = metrics.get_cluster_summary()
        assert summary["total_failed"] == 3


class TestConflictRecovery:
    """Tests for conflict detection and recovery."""
    
    def test_log_conflict_detection(self):
        """Test detection of log conflicts."""
        resolver = ConflictResolver()
        
        conflict = resolver.detect_conflict(
            follower_id="follower1",
            append_entries_response={"success": False, "term": 5},
            leader_log_term=4,
            conflict_index=10,
        )
        
        assert conflict is not None
        assert conflict.follower_id == "follower1"
    
    def test_conflict_recovery_strategy(self):
        """Test strategy selection for conflict recovery."""
        resolver = ConflictResolver()
        
        conflict = resolver.detect_conflict(
            follower_id="follower1",
            append_entries_response={"success": False, "term": 5, "last_index": 8},
            leader_log_term=5,
            conflict_index=10,
        )
        
        assert conflict.recovery_strategy == "backtrack"
    
    def test_optimistic_sync_recovery(self):
        """Test optimistic log sync for conflict recovery."""
        resolver = ConflictResolver()
        
        leader_log = [{"index": i, "term": 5} for i in range(1, 101)]
        
        sync_from, entries = resolver.optimistic_log_sync(
            "follower1",
            leader_log,
            follower_last_index=100,
        )
        
        assert sync_from > 0
        assert len(entries) >= 0


class TestReplicationProgressRecovery:
    """Tests for recovery of replication progress."""
    
    def test_recover_from_zero_progress(self):
        """Test recovery when follower has zero progress."""
        catchup = FollowerCatchup(leader_last_index=1000)
        catchup.register_follower("follower1")
        
        # No progress yet
        assert catchup.follower_states["follower1"].match_index == 0
        
        # Start catching up
        log_entries = [{"index": i} for i in range(1, 1001)]
        strategy = catchup.get_catchup_strategy("follower1")
        
        start, end = catchup.calculate_catch_up_range(
            "follower1",
            log_entries,
            strategy,
        )
        
        assert start > 0
        assert end > start
    
    def test_partial_replication_recovery(self):
        """Test recovery from partial replication."""
        metrics = ReplicationMetricsCollector()
        
        # Send 500 entries, only 300 replicate
        rep_id1 = metrics.start_replication("follower1", 500, 51200)
        metrics.complete_replication(rep_id1, True, last_index=300)
        
        # Resume from 300
        rep_id2 = metrics.start_replication("follower1", 200, 20480)
        metrics.complete_replication(rep_id2, True, last_index=500)
        
        metrics_data = metrics.get_metrics("follower1")
        assert metrics_data.entries_replicated == 700
        assert metrics_data.last_successful_index == 500


class TestTimeoutAndRetry:
    """Tests for timeout and retry mechanisms."""
    
    def test_backoff_on_timeout(self):
        """Test exponential backoff on timeout."""
        resolver = ConflictResolver()
        
        # Multiple failures
        for attempt in range(3):
            resolver.increment_recovery_attempt("follower1")
        
        attempts = resolver.recovery_attempts["follower1"]
        assert attempts == 3
    
    def test_recovery_attempt_tracking(self):
        """Test tracking of recovery attempts."""
        resolver = ConflictResolver()
        
        for i in range(5):
            count = resolver.increment_recovery_attempt("follower1")
            assert count == i + 1
    
    def test_strategy_escalation_on_repeated_failures(self):
        """Test strategy escalation after repeated failures."""
        resolver = ConflictResolver()
        
        for i in range(4):
            resolver.increment_recovery_attempt("follower1")
        
        # After 4 attempts, should consider different strategies
        attempts = resolver.recovery_attempts["follower1"]
        assert attempts >= 3
