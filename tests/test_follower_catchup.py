"""Test suite for catch-up mechanism for lagging followers."""

import pytest
from src.raft.follower_catchup import (
    FollowerCatchup,
    FollowerState,
    CatchupStrategy,
)


class TestFollowerState:
    """Tests for FollowerState."""
    
    def test_initialization(self):
        """Test FollowerState initialization."""
        state = FollowerState(follower_id="follower1")
        
        assert state.follower_id == "follower1"
        assert state.next_index == 1
        assert state.match_index == 0
        assert state.is_caught_up is False
        assert state.catchup_attempts == 0


class TestFollowerCatchup:
    """Tests for FollowerCatchup."""
    
    def test_initialization(self):
        """Test FollowerCatchup initialization."""
        catchup = FollowerCatchup(leader_last_index=100)
        
        assert catchup.leader_last_index == 100
        assert catchup.max_batch_size == 500
        assert catchup.max_catchup_attempts == 10
        assert catchup.follower_states == {}
    
    def test_register_follower(self):
        """Test registering a follower."""
        catchup = FollowerCatchup(leader_last_index=100)
        
        catchup.register_follower("follower1")
        
        assert "follower1" in catchup.follower_states
        state = catchup.follower_states["follower1"]
        assert state.next_index == 1
        assert state.match_index == 0
    
    def test_register_follower_with_custom_next_index(self):
        """Test registering follower with custom next_index."""
        catchup = FollowerCatchup(leader_last_index=100)
        
        catchup.register_follower("follower1", next_index=50)
        
        state = catchup.follower_states["follower1"]
        assert state.next_index == 50
    
    def test_is_lagging_true(self):
        """Test is_lagging returns True for lagging follower."""
        catchup = FollowerCatchup(leader_last_index=100)
        catchup.register_follower("follower1")
        
        catchup.follower_states["follower1"].match_index = 80
        
        assert catchup.is_lagging("follower1", lag_threshold=10)
    
    def test_is_lagging_false(self):
        """Test is_lagging returns False for caught-up follower."""
        catchup = FollowerCatchup(leader_last_index=100)
        catchup.register_follower("follower1")
        
        catchup.follower_states["follower1"].match_index = 100
        
        assert not catchup.is_lagging("follower1", lag_threshold=10)
    
    def test_is_lagging_unregistered_follower(self):
        """Test is_lagging for unregistered follower."""
        catchup = FollowerCatchup(leader_last_index=100)
        
        assert catchup.is_lagging("unknown")
    
    def test_needs_catchup_true(self):
        """Test needs_catchup returns True when needed."""
        catchup = FollowerCatchup(leader_last_index=100)
        catchup.register_follower("follower1")
        
        catchup.follower_states["follower1"].match_index = 50
        catchup.follower_states["follower1"].is_caught_up = False
        
        assert catchup.needs_catchup("follower1")
    
    def test_needs_catchup_false(self):
        """Test needs_catchup returns False when not needed."""
        catchup = FollowerCatchup(leader_last_index=100)
        catchup.register_follower("follower1")
        
        catchup.follower_states["follower1"].match_index = 100
        catchup.follower_states["follower1"].is_caught_up = True
        
        assert not catchup.needs_catchup("follower1")
    
    def test_get_catchup_strategy_exponential_backoff(self):
        """Test strategy selection for small lag."""
        catchup = FollowerCatchup(leader_last_index=100)
        catchup.register_follower("follower1")
        catchup.follower_states["follower1"].match_index = 90
        
        strategy = catchup.get_catchup_strategy("follower1")
        assert strategy == CatchupStrategy.EXPONENTIAL_BACKOFF
    
    def test_get_catchup_strategy_batch_replication(self):
        """Test strategy selection for moderate lag."""
        catchup = FollowerCatchup(leader_last_index=10000)
        catchup.register_follower("follower1")
        catchup.follower_states["follower1"].match_index = 8000
        
        strategy = catchup.get_catchup_strategy("follower1")
        assert strategy == CatchupStrategy.BATCH_REPLICATION
    
    def test_get_catchup_strategy_snapshot(self):
        """Test strategy selection for large lag."""
        catchup = FollowerCatchup(leader_last_index=100000)
        catchup.register_follower("follower1")
        catchup.follower_states["follower1"].match_index = 50000
        
        strategy = catchup.get_catchup_strategy("follower1")
        assert strategy == CatchupStrategy.SNAPSHOT
    
    def test_get_catchup_strategy_full_sync_after_failed_attempts(self):
        """Test strategy escalation after many failed attempts."""
        catchup = FollowerCatchup(leader_last_index=100, max_catchup_attempts=3)
        catchup.register_follower("follower1")
        catchup.follower_states["follower1"].catchup_attempts = 3
        
        strategy = catchup.get_catchup_strategy("follower1")
        assert strategy == CatchupStrategy.FULL_SYNC
    
    def test_calculate_catch_up_range_exponential_backoff(self):
        """Test range calculation for exponential backoff."""
        catchup = FollowerCatchup(leader_last_index=100)
        catchup.register_follower("follower1")
        catchup.follower_states["follower1"].match_index = 20
        
        log_entries = [{"index": i} for i in range(1, 101)]
        
        start, end = catchup.calculate_catch_up_range(
            "follower1",
            log_entries,
            strategy=CatchupStrategy.EXPONENTIAL_BACKOFF,
        )
        
        # Should be roughly in the middle
        assert start >= 20
        assert end <= 101  # end is exclusive, so 101 is the max for index 100
    
    def test_calculate_catch_up_range_batch_replication(self):
        """Test range calculation for batch replication."""
        catchup = FollowerCatchup(leader_last_index=10000)
        catchup.register_follower("follower1")
        catchup.follower_states["follower1"].next_index = 100
        
        log_entries = [{"index": i} for i in range(1, 10001)]
        
        start, end = catchup.calculate_catch_up_range(
            "follower1",
            log_entries,
            strategy=CatchupStrategy.BATCH_REPLICATION,
        )
        
        assert start == 100
        assert end > start
        assert end - start == int(catchup.follower_states["follower1"].batch_size)
    
    def test_calculate_catch_up_range_full_sync(self):
        """Test range calculation for full sync."""
        catchup = FollowerCatchup(leader_last_index=100)
        catchup.register_follower("follower1")
        
        log_entries = [{"index": i} for i in range(1, 101)]
        
        start, end = catchup.calculate_catch_up_range(
            "follower1",
            log_entries,
            strategy=CatchupStrategy.FULL_SYNC,
        )
        
        assert start == 1
        assert end == 101
    
    def test_record_catch_up_success(self):
        """Test recording successful catch-up progress."""
        catchup = FollowerCatchup(leader_last_index=100)
        catchup.register_follower("follower1")
        
        catchup.record_catch_up_success("follower1", entries_sent=50)
        
        state = catchup.follower_states["follower1"]
        assert state.match_index == 50
        assert state.next_index == 51
        assert state.catchup_attempts == 0
    
    def test_record_catch_up_success_marks_caught_up(self):
        """Test that success marks follower as caught up when appropriate."""
        catchup = FollowerCatchup(leader_last_index=100)
        catchup.register_follower("follower1")
        catchup.follower_states["follower1"].match_index = 80
        
        catchup.record_catch_up_success("follower1", entries_sent=20)
        
        state = catchup.follower_states["follower1"]
        assert state.is_caught_up is True
    
    def test_record_catch_up_failure(self):
        """Test recording failed catch-up attempt."""
        catchup = FollowerCatchup(leader_last_index=100)
        catchup.register_follower("follower1")
        
        catchup.record_catch_up_failure("follower1")
        catchup.record_catch_up_failure("follower1")
        
        state = catchup.follower_states["follower1"]
        assert state.catchup_attempts == 2
    
    def test_is_caught_up_complete_true(self):
        """Test is_caught_up_complete returns True when caught up."""
        catchup = FollowerCatchup(leader_last_index=100)
        catchup.register_follower("follower1")
        catchup.follower_states["follower1"].is_caught_up = True
        catchup.follower_states["follower1"].match_index = 100
        
        assert catchup.is_caught_up_complete("follower1")
    
    def test_is_caught_up_complete_false(self):
        """Test is_caught_up_complete returns False when not caught up."""
        catchup = FollowerCatchup(leader_last_index=100)
        catchup.register_follower("follower1")
        catchup.follower_states["follower1"].match_index = 80
        
        assert not catchup.is_caught_up_complete("follower1")
    
    def test_update_leader_index(self):
        """Test updating leader's last index."""
        catchup = FollowerCatchup(leader_last_index=100)
        catchup.register_follower("follower1")
        catchup.follower_states["follower1"].is_caught_up = True
        catchup.follower_states["follower1"].match_index = 100
        
        catchup.update_leader_index(150)
        
        state = catchup.follower_states["follower1"]
        assert catchup.leader_last_index == 150
        assert state.is_caught_up is False  # No longer caught up
    
    def test_get_catch_up_status(self):
        """Test retrieving catch-up status."""
        catchup = FollowerCatchup(leader_last_index=100)
        catchup.register_follower("follower1")
        catchup.follower_states["follower1"].match_index = 80
        
        status = catchup.get_catch_up_status("follower1")
        
        assert status["follower_id"] == "follower1"
        assert status["registered"] is True
        assert status["match_index"] == 80
        assert status["lag"] == 20
    
    def test_get_catch_up_status_unregistered(self):
        """Test retrieving status for unregistered follower."""
        catchup = FollowerCatchup(leader_last_index=100)
        
        status = catchup.get_catch_up_status("unknown")
        
        assert status["follower_id"] == "unknown"
        assert status["registered"] is False
    
    def test_get_cluster_catch_up_status(self):
        """Test retrieving cluster-wide catch-up status."""
        catchup = FollowerCatchup(leader_last_index=100)
        
        catchup.register_follower("follower1")
        catchup.follower_states["follower1"].is_caught_up = True
        catchup.follower_states["follower1"].match_index = 100
        
        catchup.register_follower("follower2")
        catchup.follower_states["follower2"].match_index = 70
        
        status = catchup.get_cluster_catch_up_status()
        
        assert status["total_followers"] == 2
        assert status["caught_up_followers"] == 1
        assert len(status["lagging_followers"]) == 1
        assert "follower2" in status["lagging_followers"]
    
    def test_reset_follower_catchup(self):
        """Test resetting catch-up state for a follower."""
        catchup = FollowerCatchup(leader_last_index=100)
        catchup.register_follower("follower1")
        
        state = catchup.follower_states["follower1"]
        state.catchup_attempts = 5
        state.batch_size = 250
        state.last_backtrack = 50
        
        catchup.reset_follower_catchup("follower1")
        
        assert state.catchup_attempts == 0
        assert state.batch_size == 100
        assert state.last_backtrack == 0
    
    def test_exponential_backoff_progression(self):
        """Test exponential backoff gets progressively closer."""
        catchup = FollowerCatchup(leader_last_index=200)
        catchup.register_follower("follower1")
        catchup.follower_states["follower1"].match_index = 100
        
        log_entries = [{"index": i} for i in range(1, 201)]
        
        # First attempt
        start1, end1 = catchup.calculate_catch_up_range(
            "follower1",
            log_entries,
            strategy=CatchupStrategy.EXPONENTIAL_BACKOFF,
        )
        
        # Record failure and try again
        catchup.record_catch_up_failure("follower1")
        
        start2, end2 = catchup.calculate_catch_up_range(
            "follower1",
            log_entries,
            strategy=CatchupStrategy.EXPONENTIAL_BACKOFF,
        )
        
        # Should be adjusting the range
        assert (start1, end1) != (start2, end2)
    
    def test_batch_size_increases(self):
        """Test batch size increases over time."""
        catchup = FollowerCatchup(leader_last_index=10000)
        catchup.register_follower("follower1")
        
        log_entries = [{"index": i} for i in range(1, 10001)]
        
        initial_batch_size = catchup.follower_states["follower1"].batch_size
        
        # Multiple attempts should increase batch size
        for _ in range(3):
            catchup.calculate_catch_up_range(
                "follower1",
                log_entries,
                strategy=CatchupStrategy.BATCH_REPLICATION,
            )
        
        final_batch_size = catchup.follower_states["follower1"].batch_size
        
        assert final_batch_size > initial_batch_size
    
    def test_multiple_followers_independent_state(self):
        """Test that multiple followers have independent catch-up state."""
        catchup = FollowerCatchup(leader_last_index=100)
        
        catchup.register_follower("follower1")
        catchup.register_follower("follower2")
        
        catchup.record_catch_up_success("follower1", entries_sent=50)
        catchup.record_catch_up_failure("follower2")
        
        state1 = catchup.follower_states["follower1"]
        state2 = catchup.follower_states["follower2"]
        
        assert state1.match_index == 50
        assert state1.catchup_attempts == 0
        assert state2.match_index == 0
        assert state2.catchup_attempts == 1
