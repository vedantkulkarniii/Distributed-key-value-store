"""
Log replication coordination for Raft followers and leaders.

Implements:
- Follower replication state management
- Log synchronization with consistency checking
- Replication progress tracking
- Catch-up logic for lagging followers
"""

import logging
from typing import List, Optional, Dict, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class FollowerReplication:
    """Manages replication state for a follower."""
    
    def __init__(self, follower_id: str, log_length: int):
        """
        Initialize follower replication.
        
        Args:
            follower_id: Follower node ID
            log_length: Initial log length (from leader)
        """
        self.follower_id = follower_id
        self.next_index = log_length  # Next entry to send
        self.match_index = 0  # Highest replicated index
        self.last_sync_time = datetime.now()
        self.sync_failures = 0
        self.max_backoff = 10  # Maximum exponential backoff in ms
    
    def handle_success(self, last_index: int) -> bool:
        """
        Handle successful replication response.
        
        Args:
            last_index: Last index replicated on follower
            
        Returns:
            True if replication state was updated
        """
        old_match = self.match_index
        self.match_index = max(self.match_index, last_index)
        self.next_index = max(self.next_index, last_index + 1)
        self.sync_failures = 0  # Reset backoff
        self.last_sync_time = datetime.now()
        
        return self.match_index > old_match
    
    def handle_failure(self) -> None:
        """Handle failed replication response."""
        if self.next_index > 1:
            self.next_index -= 1
        self.sync_failures += 1
        self.last_sync_time = datetime.now()
    
    def get_backoff_ms(self) -> int:
        """Get exponential backoff in milliseconds."""
        backoff = min(2 ** self.sync_failures, self.max_backoff)
        return backoff
    
    def is_caught_up(self, log_length: int) -> bool:
        """Check if follower is caught up with leader."""
        return self.match_index >= log_length
    
    def needs_catchup(self, threshold: int = 5) -> bool:
        """Check if follower needs catch-up (far behind)."""
        return (self.next_index - self.match_index) > threshold
    
    def get_status(self) -> dict:
        """Get replication status."""
        return {
            "follower_id": self.follower_id,
            "next_index": self.next_index,
            "match_index": self.match_index,
            "sync_failures": self.sync_failures,
            "backoff_ms": self.get_backoff_ms(),
            "last_sync": self.last_sync_time.isoformat()
        }


class ReplicationCoordinator:
    """Coordinates replication across all followers."""
    
    def __init__(self, leader_id: str, followers: List[str], log_length: int):
        """
        Initialize replication coordinator.
        
        Args:
            leader_id: Leader node ID
            followers: List of follower IDs
            log_length: Current log length
        """
        self.leader_id = leader_id
        self.followers = followers
        self.log_length = log_length
        self.follower_state: Dict[str, FollowerReplication] = {}
        
        for follower in followers:
            self.follower_state[follower] = FollowerReplication(follower, log_length)
        
        logger.info(
            f"Replication coordinator initialized for {leader_id} "
            f"with {len(followers)} followers, log_length={log_length}"
        )
    
    def update_log_length(self, new_length: int) -> None:
        """Update log length and adjust replication targets."""
        if new_length > self.log_length:
            self.log_length = new_length
            logger.debug(f"Leader {self.leader_id}: Log extended to {new_length}")
    
    def handle_replication_success(self, follower_id: str, last_index: int) -> bool:
        """Handle successful replication to follower."""
        if follower_id not in self.follower_state:
            return False
        
        return self.follower_state[follower_id].handle_success(last_index)
    
    def handle_replication_failure(self, follower_id: str) -> None:
        """Handle failed replication to follower."""
        if follower_id in self.follower_state:
            self.follower_state[follower_id].handle_failure()
    
    def get_next_index(self, follower_id: str) -> Optional[int]:
        """Get next index to send to follower."""
        if follower_id not in self.follower_state:
            return None
        return self.follower_state[follower_id].next_index
    
    def get_match_index(self, follower_id: str) -> Optional[int]:
        """Get match index for follower."""
        if follower_id not in self.follower_state:
            return None
        return self.follower_state[follower_id].match_index
    
    def calculate_commit_index(self) -> int:
        """
        Calculate commit index based on replication to majority.
        
        Returns:
            New commit index
        """
        # Collect match indices from all followers
        match_indices = [state.match_index for state in self.follower_state.values()]
        match_indices.append(self.log_length)  # Include leader's own log
        
        # Sort in descending order
        match_indices.sort(reverse=True)
        
        # Find majority index
        majority_size = len(self.followers) // 2  # Not +1, we want floor
        if majority_size < len(match_indices):
            return match_indices[majority_size]
        
        return 0
    
    def get_lagging_followers(self) -> List[Tuple[str, int]]:
        """Get list of lagging followers and their lag."""
        lagging = []
        for follower_id, state in self.follower_state.items():
            lag = self.log_length - state.match_index
            if lag > 0:
                lagging.append((follower_id, lag))
        
        return sorted(lagging, key=lambda x: x[1], reverse=True)
    
    def all_caught_up(self) -> bool:
        """Check if all followers are caught up."""
        return all(
            state.is_caught_up(self.log_length)
            for state in self.follower_state.values()
        )
    
    def get_followers_needing_catchup(self) -> List[str]:
        """Get followers that need catch-up replication."""
        return [
            follower_id
            for follower_id, state in self.follower_state.items()
            if state.needs_catchup()
        ]
    
    def get_replication_status(self) -> dict:
        """Get overall replication status."""
        return {
            "leader_id": self.leader_id,
            "log_length": self.log_length,
            "commit_index": self.calculate_commit_index(),
            "followers": {
                follower_id: state.get_status()
                for follower_id, state in self.follower_state.items()
            },
            "lagging": self.get_lagging_followers(),
            "all_caught_up": self.all_caught_up()
        }
