"""Test suite for conflict detection and resolution utilities."""

import pytest
from src.raft.conflict_resolver import ConflictResolver, ConflictInfo


class TestConflictResolver:
    """Tests for ConflictResolver."""
    
    def test_initialization(self):
        """Test ConflictResolver initialization."""
        resolver = ConflictResolver()
        assert resolver.conflicts == {}
        assert resolver.recovery_attempts == {}
        assert resolver.backtrack_history == {}
    
    def test_detect_conflict_success(self):
        """Test that successful AppendEntries returns no conflict."""
        resolver = ConflictResolver()
        response = {"success": True}
        
        conflict = resolver.detect_conflict(
            follower_id="follower1",
            append_entries_response=response,
            leader_log_term=5,
            conflict_index=10,
        )
        
        assert conflict is None
    
    def test_detect_conflict_failure_term_mismatch(self):
        """Test conflict detection with term mismatch."""
        resolver = ConflictResolver()
        response = {"success": False, "term": 6}
        
        conflict = resolver.detect_conflict(
            follower_id="follower1",
            append_entries_response=response,
            leader_log_term=5,
            conflict_index=10,
        )
        
        assert conflict is not None
        assert conflict.follower_id == "follower1"
        assert conflict.conflict_index == 10
        assert conflict.leader_term == 5
        assert conflict.follower_term == 6
        assert conflict.conflict_type == "term_mismatch"
    
    def test_detect_conflict_missing_entry(self):
        """Test conflict detection with missing entry."""
        resolver = ConflictResolver()
        response = {"success": False, "term": 5, "last_index": 0}
        
        conflict = resolver.detect_conflict(
            follower_id="follower1",
            append_entries_response=response,
            leader_log_term=5,
            conflict_index=10,
        )
        
        assert conflict is not None
        assert conflict.conflict_type == "missing_entry"
    
    def test_detect_conflict_partial_divergence(self):
        """Test conflict detection with partial divergence."""
        resolver = ConflictResolver()
        response = {"success": False, "term": 5, "last_index": 8}
        
        conflict = resolver.detect_conflict(
            follower_id="follower1",
            append_entries_response=response,
            leader_log_term=5,
            conflict_index=10,
        )
        
        assert conflict is not None
        assert conflict.conflict_type == "partial_divergence"
    
    def test_multiple_conflicts_tracked(self):
        """Test tracking multiple conflicts for a follower."""
        resolver = ConflictResolver()
        
        # First conflict
        resolver.detect_conflict(
            follower_id="follower1",
            append_entries_response={"success": False, "term": 5},
            leader_log_term=4,
            conflict_index=10,
        )
        
        # Second conflict
        resolver.detect_conflict(
            follower_id="follower1",
            append_entries_response={"success": False, "term": 6},
            leader_log_term=5,
            conflict_index=9,
        )
        
        assert len(resolver.conflicts["follower1"]) == 2
        assert resolver.conflicts["follower1"][0].conflict_index == 10
        assert resolver.conflicts["follower1"][1].conflict_index == 9
    
    def test_recovery_strategy_backtrack(self):
        """Test backtrack recovery strategy selection."""
        resolver = ConflictResolver()
        
        conflict = resolver.detect_conflict(
            follower_id="follower1",
            append_entries_response={"success": False, "term": 5, "last_index": 8},
            leader_log_term=5,
            conflict_index=10,
        )
        
        assert conflict.recovery_strategy == "backtrack"
    
    def test_recovery_strategy_full_sync_after_failures(self):
        """Test full_sync strategy after multiple backtrack failures."""
        resolver = ConflictResolver()
        resolver.recovery_attempts["follower1"] = 3
        
        conflict = resolver.detect_conflict(
            follower_id="follower1",
            append_entries_response={"success": False, "term": 5, "last_index": 8},
            leader_log_term=5,
            conflict_index=10,
        )
        
        assert conflict.recovery_strategy == "full_sync"
    
    def test_recovery_strategy_snapshot_for_higher_term(self):
        """Test snapshot strategy for higher term mismatches."""
        resolver = ConflictResolver()
        
        conflict = resolver.detect_conflict(
            follower_id="follower1",
            append_entries_response={"success": False, "term": 7},
            leader_log_term=5,
            conflict_index=10,
        )
        
        assert conflict.recovery_strategy == "snapshot"
    
    def test_optimistic_log_sync_no_history(self):
        """Test optimistic log sync without prior history."""
        resolver = ConflictResolver()
        leader_log = [
            {"index": i, "term": 5, "data": f"entry_{i}"}
            for i in range(1, 11)
        ]
        
        sync_from, entries = resolver.optimistic_log_sync(
            follower_id="follower1",
            leader_log=leader_log,
            follower_last_index=10,
        )
        
        assert sync_from == 5  # Exponential backoff: 10 // 2
        assert len(entries) >= 5
    
    def test_optimistic_log_sync_with_history(self):
        """Test optimistic log sync using backtrack history."""
        resolver = ConflictResolver()
        resolver.backtrack_history["follower1"] = [5, 7, 9]
        
        leader_log = [
            {"index": i, "term": 5, "data": f"entry_{i}"}
            for i in range(1, 11)
        ]
        
        sync_from, entries = resolver.optimistic_log_sync(
            follower_id="follower1",
            leader_log=leader_log,
            follower_last_index=10,
        )
        
        # Should use the last successful sync point + 1
        assert sync_from == 10  # 9 + 1
        assert len(entries) == 1
    
    def test_record_successful_sync(self):
        """Test recording a successful sync point."""
        resolver = ConflictResolver()
        
        resolver.record_successful_sync("follower1", 5)
        resolver.record_successful_sync("follower1", 7)
        resolver.record_successful_sync("follower1", 9)
        
        assert resolver.backtrack_history["follower1"] == [5, 7, 9]
    
    def test_record_successful_sync_duplicate(self):
        """Test that duplicate lower indices are not recorded."""
        resolver = ConflictResolver()
        
        resolver.record_successful_sync("follower1", 9)
        resolver.record_successful_sync("follower1", 7)  # Lower than 9
        
        # Should only have 9, not 7
        assert resolver.backtrack_history["follower1"] == [9]
    
    def test_should_use_fast_backtrack_insufficient_history(self):
        """Test fast backtrack determination with insufficient history."""
        resolver = ConflictResolver()
        
        assert not resolver.should_use_fast_backtrack("follower1")
        
        resolver.backtrack_history["follower1"] = [5]
        assert not resolver.should_use_fast_backtrack("follower1")
    
    def test_should_use_fast_backtrack_sufficient_history(self):
        """Test fast backtrack determination with sufficient history."""
        resolver = ConflictResolver()
        resolver.backtrack_history["follower1"] = [5, 7]
        
        assert resolver.should_use_fast_backtrack("follower1")
    
    def test_get_conflict_summary_no_conflicts(self):
        """Test conflict summary when no conflicts exist."""
        resolver = ConflictResolver()
        
        summary = resolver.get_conflict_summary("follower1")
        
        assert summary["follower_id"] == "follower1"
        assert summary["total_conflicts"] == 0
        assert summary["latest_conflict"] is None
    
    def test_get_conflict_summary_with_conflicts(self):
        """Test conflict summary with existing conflicts."""
        resolver = ConflictResolver()
        
        resolver.detect_conflict(
            follower_id="follower1",
            append_entries_response={"success": False, "term": 5},
            leader_log_term=4,
            conflict_index=10,
        )
        
        resolver.recovery_attempts["follower1"] = 2
        resolver.backtrack_history["follower1"] = [5, 7]
        
        summary = resolver.get_conflict_summary("follower1")
        
        assert summary["total_conflicts"] == 1
        assert summary["latest_conflict"]["index"] == 10
        assert summary["recovery_attempts"] == 2
        assert summary["sync_history_length"] == 2
    
    def test_clear_resolved_conflicts(self):
        """Test clearing resolved conflicts."""
        resolver = ConflictResolver()
        
        resolver.detect_conflict(
            follower_id="follower1",
            append_entries_response={"success": False, "term": 5},
            leader_log_term=4,
            conflict_index=10,
        )
        resolver.recovery_attempts["follower1"] = 3
        
        resolver.clear_resolved_conflicts("follower1")
        
        assert "follower1" not in resolver.conflicts
        assert resolver.recovery_attempts["follower1"] == 0
    
    def test_increment_recovery_attempt(self):
        """Test incrementing recovery attempt count."""
        resolver = ConflictResolver()
        
        count1 = resolver.increment_recovery_attempt("follower1")
        assert count1 == 1
        
        count2 = resolver.increment_recovery_attempt("follower1")
        assert count2 == 2
        
        count3 = resolver.increment_recovery_attempt("follower2")
        assert count3 == 1
