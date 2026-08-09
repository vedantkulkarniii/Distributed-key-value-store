"""
Tests for log replication coordination.

Tests cover:
- Follower replication state management
- Replication progress tracking
- Catch-up logic
- Commit index calculation
"""

import pytest
from datetime import datetime
from src.raft.log_replication import FollowerReplication, ReplicationCoordinator


class TestFollowerReplication:
    """Test follower replication state management."""
    
    def test_initialization(self):
        """Test replication state initialization."""
        rep = FollowerReplication("follower-1", log_length=10)
        
        assert rep.follower_id == "follower-1"
        assert rep.next_index == 10
        assert rep.match_index == 0
        assert rep.sync_failures == 0
    
    def test_handle_success(self):
        """Test handling successful replication."""
        rep = FollowerReplication("follower-1", log_length=10)
        
        updated = rep.handle_success(8)
        
        assert updated is True
        assert rep.match_index == 8
        assert rep.next_index >= 8  # Should be at least 8
        assert rep.sync_failures == 0
    
    def test_handle_failure(self):
        """Test handling failed replication."""
        rep = FollowerReplication("follower-1", log_length=10)
        
        old_next = rep.next_index
        rep.handle_failure()
        
        assert rep.next_index == old_next - 1
        assert rep.sync_failures == 1
    
    def test_exponential_backoff(self):
        """Test exponential backoff calculation."""
        rep = FollowerReplication("follower-1", log_length=10)
        
        backoffs = []
        for _ in range(5):
            backoff = rep.get_backoff_ms()
            backoffs.append(backoff)
            rep.handle_failure()
        
        # Should increase exponentially
        assert backoffs[0] < backoffs[1]
        assert backoffs[1] < backoffs[2]
    
    def test_is_caught_up(self):
        """Test caught-up detection."""
        rep = FollowerReplication("follower-1", log_length=10)
        
        assert not rep.is_caught_up(10)
        
        rep.handle_success(9)
        assert rep.is_caught_up(9)  # match_index >= log_length
    
    def test_needs_catchup(self):
        """Test catch-up detection."""
        rep = FollowerReplication("follower-1", log_length=20)
        rep.match_index = 5
        
        # Delta = next_index - match_index = 20 - 5 = 15 > threshold
        assert rep.needs_catchup(threshold=10)
        assert not rep.needs_catchup(threshold=20)
    
    def test_get_status(self):
        """Test status reporting."""
        rep = FollowerReplication("follower-1", log_length=10)
        
        status = rep.get_status()
        
        assert status['follower_id'] == "follower-1"
        assert status['next_index'] == 10
        assert status['match_index'] == 0
        assert 'backoff_ms' in status
        assert 'last_sync' in status


class TestReplicationCoordinator:
    """Test replication coordinator."""
    
    def test_initialization(self):
        """Test coordinator initialization."""
        followers = ["follower-1", "follower-2", "follower-3"]
        coord = ReplicationCoordinator("leader", followers, log_length=10)
        
        assert coord.leader_id == "leader"
        assert len(coord.follower_state) == 3
        assert all(f in coord.follower_state for f in followers)
    
    def test_update_log_length(self):
        """Test updating log length."""
        followers = ["follower-1", "follower-2"]
        coord = ReplicationCoordinator("leader", followers, log_length=10)
        
        coord.update_log_length(15)
        
        assert coord.log_length == 15
    
    def test_handle_replication_success(self):
        """Test handling replication success."""
        followers = ["follower-1", "follower-2"]
        coord = ReplicationCoordinator("leader", followers, log_length=10)
        
        updated = coord.handle_replication_success("follower-1", last_index=8)
        
        assert updated is True
        assert coord.get_match_index("follower-1") == 8
    
    def test_handle_replication_failure(self):
        """Test handling replication failure."""
        followers = ["follower-1", "follower-2"]
        coord = ReplicationCoordinator("leader", followers, log_length=10)
        
        old_next = coord.get_next_index("follower-1")
        coord.handle_replication_failure("follower-1")
        
        assert coord.get_next_index("follower-1") == old_next - 1
    
    def test_calculate_commit_index_single_follower(self):
        """Test commit index calculation with single follower."""
        followers = ["follower-1"]
        coord = ReplicationCoordinator("leader", followers, log_length=10)
        
        # No replication yet, commit is min of all match indices
        assert coord.calculate_commit_index() == 10  # leader's own log
        
        # Replicate to follower
        coord.handle_replication_success("follower-1", last_index=8)
        commit = coord.calculate_commit_index()
        
        # With 1 follower, majority requires 0 followers (floor(1/2) = 0)
        assert commit >= 8
    
    def test_calculate_commit_index_three_followers(self):
        """Test commit index calculation with three followers."""
        followers = ["f1", "f2", "f3"]
        coord = ReplicationCoordinator("leader", followers, log_length=10)
        
        # Replicate to 2 followers (majority of 3)
        coord.handle_replication_success("f1", last_index=9)
        coord.handle_replication_success("f2", last_index=7)
        
        commit = coord.calculate_commit_index()
        
        # Match indices: [9, 7] + leader=10, sorted = [10, 9, 7]
        # Index at position 3//2=1 is 9
        assert commit == 9
    
    def test_get_lagging_followers(self):
        """Test identifying lagging followers."""
        followers = ["f1", "f2", "f3"]
        coord = ReplicationCoordinator("leader", followers, log_length=10)
        
        # Simulate varying replication progress
        coord.handle_replication_success("f1", last_index=9)
        coord.handle_replication_success("f2", last_index=5)
        # f3 not replicated (match_index=0)
        
        lagging = coord.get_lagging_followers()
        
        # f1 has lag 1, f2 has lag 5, f3 has lag 10
        assert len(lagging) >= 2
        assert any(f[0] == "f3" and f[1] == 10 for f in lagging)
        assert any(f[0] == "f2" and f[1] == 5 for f in lagging)
    
    def test_all_caught_up(self):
        """Test all caught up detection."""
        followers = ["f1", "f2"]
        coord = ReplicationCoordinator("leader", followers, log_length=10)
        
        assert not coord.all_caught_up()
        
        # Replicate to all
        coord.handle_replication_success("f1", last_index=10)
        coord.handle_replication_success("f2", last_index=10)
        
        assert coord.all_caught_up()
    
    def test_get_followers_needing_catchup(self):
        """Test identifying followers needing catch-up."""
        followers = ["f1", "f2", "f3"]
        coord = ReplicationCoordinator("leader", followers, log_length=100)
        
        # f1: lag=100 (needs catchup)
        # f2: lag=3 (doesn't need)
        coord.handle_replication_success("f2", last_index=97)
        
        needing_catchup = coord.get_followers_needing_catchup()
        
        assert "f1" in needing_catchup
        assert "f3" in needing_catchup
        assert "f2" not in needing_catchup
    
    def test_replication_status(self):
        """Test replication status reporting."""
        followers = ["f1", "f2"]
        coord = ReplicationCoordinator("leader", followers, log_length=10)
        
        coord.handle_replication_success("f1", last_index=8)
        
        status = coord.get_replication_status()
        
        assert status['leader_id'] == "leader"
        assert status['log_length'] == 10
        assert 'followers' in status
        assert 'lagging' in status
        assert 'all_caught_up' in status
