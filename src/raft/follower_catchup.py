"""Catch-up Mechanism for Lagging Followers in Raft Replication.

Implements fast replication catch-up for followers that have fallen behind,
using exponential backoff and batch replication strategies.
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class CatchupStrategy(Enum):
    """Strategy for catching up a lagging follower."""
    
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    """Back off exponentially from leader's last index."""
    
    SNAPSHOT = "snapshot"
    """Use snapshot to quickly transfer state."""
    
    BATCH_REPLICATION = "batch_replication"
    """Send entries in large batches."""
    
    FULL_SYNC = "full_sync"
    """Full sync from log start."""


@dataclass
class FollowerState:
    """Tracks replication state for a specific follower."""
    
    follower_id: str
    """The follower's ID."""
    
    next_index: int = 1
    """Next index to send to this follower."""
    
    match_index: int = 0
    """Highest index known to be replicated."""
    
    is_caught_up: bool = False
    """Whether the follower is caught up with the leader."""
    
    catchup_attempts: int = 0
    """Number of catch-up attempts made."""
    
    last_backtrack: int = 0
    """Last index we tried during exponential backoff."""
    
    batch_size: int = 100
    """Current batch size for replication."""
    
    backoff_factor: float = 0.5
    """Factor for exponential backoff (0.5 = half)."""


class FollowerCatchup:
    """Manages catch-up mechanism for lagging followers.
    
    Detects when followers have fallen behind and employs various
    strategies to get them caught up quickly.
    """
    
    def __init__(
        self,
        leader_last_index: int,
        max_batch_size: int = 500,
        max_catchup_attempts: int = 10,
    ):
        """Initialize the catch-up manager.
        
        Args:
            leader_last_index: The leader's current last log index.
            max_batch_size: Maximum entries in a batch.
            max_catchup_attempts: Maximum catch-up attempts before switching strategy.
        """
        self.leader_last_index = leader_last_index
        self.max_batch_size = max_batch_size
        self.max_catchup_attempts = max_catchup_attempts
        self.follower_states: Dict[str, FollowerState] = {}
        """Track replication state per follower."""
        
        self.catchup_history: Dict[str, List[int]] = {}
        """History of catch-up attempts per follower."""
    
    def register_follower(self, follower_id: str, next_index: int = 1) -> None:
        """Register a follower for catch-up tracking.
        
        Args:
            follower_id: The follower's ID.
            next_index: Initial next_index for this follower.
        """
        self.follower_states[follower_id] = FollowerState(
            follower_id=follower_id,
            next_index=next_index,
            match_index=0,
        )
        self.catchup_history[follower_id] = []
    
    def is_lagging(self, follower_id: str, lag_threshold: int = 10) -> bool:
        """Check if a follower is lagging behind the leader.
        
        Args:
            follower_id: The follower's ID.
            lag_threshold: Minimum lag to be considered lagging.
        
        Returns:
            True if the follower is lagging, False otherwise.
        """
        if follower_id not in self.follower_states:
            return True
        
        state = self.follower_states[follower_id]
        lag = self.leader_last_index - state.match_index
        
        return lag >= lag_threshold
    
    def needs_catchup(self, follower_id: str) -> bool:
        """Check if a follower needs catch-up.
        
        Args:
            follower_id: The follower's ID.
        
        Returns:
            True if catch-up is needed, False otherwise.
        """
        if follower_id not in self.follower_states:
            return True
        
        state = self.follower_states[follower_id]
        return not state.is_caught_up and state.match_index < self.leader_last_index
    
    def get_catchup_strategy(self, follower_id: str) -> CatchupStrategy:
        """Determine the best catch-up strategy for a follower.
        
        Args:
            follower_id: The follower's ID.
        
        Returns:
            The recommended catch-up strategy.
        """
        if follower_id not in self.follower_states:
            return CatchupStrategy.EXPONENTIAL_BACKOFF
        
        state = self.follower_states[follower_id]
        lag = self.leader_last_index - state.match_index
        
        # Very large lag: use snapshot
        if lag > 10000:
            return CatchupStrategy.SNAPSHOT
        
        # Many failed attempts: escalate to full sync
        if state.catchup_attempts >= self.max_catchup_attempts:
            return CatchupStrategy.FULL_SYNC
        
        # Moderate lag: use batch replication
        if lag > 1000:
            return CatchupStrategy.BATCH_REPLICATION
        
        # Small lag: use exponential backoff
        return CatchupStrategy.EXPONENTIAL_BACKOFF
    
    def calculate_catch_up_range(
        self,
        follower_id: str,
        log_entries: List[Dict],
        strategy: Optional[CatchupStrategy] = None,
    ) -> Tuple[int, int]:
        """Calculate the range of entries to send for catch-up.
        
        Args:
            follower_id: The follower's ID.
            log_entries: Available log entries.
            strategy: The catch-up strategy to use (auto-selected if None).
        
        Returns:
            Tuple of (start_index, end_index) for entries to send.
        """
        if follower_id not in self.follower_states:
            self.register_follower(follower_id)
        
        state = self.follower_states[follower_id]
        
        if strategy is None:
            strategy = self.get_catchup_strategy(follower_id)
        
        if strategy == CatchupStrategy.EXPONENTIAL_BACKOFF:
            return self._exponential_backoff_range(state, log_entries)
        elif strategy == CatchupStrategy.BATCH_REPLICATION:
            return self._batch_replication_range(state, log_entries)
        elif strategy == CatchupStrategy.FULL_SYNC:
            return self._full_sync_range(state, log_entries)
        else:  # SNAPSHOT
            return (0, 0)  # Special handling for snapshots
    
    def _exponential_backoff_range(
        self,
        state: FollowerState,
        log_entries: List[Dict],
    ) -> Tuple[int, int]:
        """Calculate range using exponential backoff.
        
        Args:
            state: The follower's state.
            log_entries: Available log entries.
        
        Returns:
            Tuple of (start_index, end_index).
        """
        # Start from approximately halfway between match_index and leader_last_index
        if state.last_backtrack == 0:
            # First attempt: try at halfway point
            midpoint = (state.match_index + self.leader_last_index) // 2
            state.last_backtrack = midpoint
        else:
            # Apply backoff: move closer to match_index
            gap = state.last_backtrack - state.match_index
            state.last_backtrack = state.match_index + int(gap * state.backoff_factor)
        
        # Collect entries from last_backtrack to leader_last_index
        start_idx = max(state.last_backtrack, state.match_index + 1)
        end_idx = min(start_idx + state.batch_size, self.leader_last_index + 1)
        
        return (start_idx, end_idx)
    
    def _batch_replication_range(
        self,
        state: FollowerState,
        log_entries: List[Dict],
    ) -> Tuple[int, int]:
        """Calculate range for batch replication.
        
        Args:
            state: The follower's state.
            log_entries: Available log entries.
        
        Returns:
            Tuple of (start_index, end_index).
        """
        # Increase batch size gradually
        state.batch_size = min(state.batch_size * 1.5, self.max_batch_size)
        
        start_idx = state.next_index
        end_idx = min(start_idx + int(state.batch_size), self.leader_last_index + 1)
        
        return (start_idx, end_idx)
    
    def _full_sync_range(
        self,
        state: FollowerState,
        log_entries: List[Dict],
    ) -> Tuple[int, int]:
        """Calculate range for full sync.
        
        Args:
            state: The follower's state.
            log_entries: Available log entries.
        
        Returns:
            Tuple of (start_index, end_index).
        """
        # Send everything from the beginning
        return (1, self.leader_last_index + 1)
    
    def record_catch_up_success(
        self,
        follower_id: str,
        entries_sent: int,
    ) -> None:
        """Record successful catch-up progress.
        
        Args:
            follower_id: The follower's ID.
            entries_sent: Number of entries successfully sent.
        """
        if follower_id not in self.follower_states:
            self.register_follower(follower_id)
        
        state = self.follower_states[follower_id]
        state.match_index += entries_sent
        state.next_index = state.match_index + 1
        state.catchup_attempts = 0  # Reset on success
        state.last_backtrack = 0
        
        # Check if caught up
        if state.match_index >= self.leader_last_index:
            state.is_caught_up = True
        
        # Record in history
        self.catchup_history[follower_id].append(state.match_index)
    
    def record_catch_up_failure(self, follower_id: str) -> None:
        """Record failed catch-up attempt.
        
        Args:
            follower_id: The follower's ID.
        """
        if follower_id not in self.follower_states:
            self.register_follower(follower_id)
        
        state = self.follower_states[follower_id]
        state.catchup_attempts += 1
    
    def is_caught_up_complete(self, follower_id: str) -> bool:
        """Check if a follower's catch-up is complete.
        
        Args:
            follower_id: The follower's ID.
        
        Returns:
            True if the follower is fully caught up, False otherwise.
        """
        if follower_id not in self.follower_states:
            return False
        
        state = self.follower_states[follower_id]
        return state.is_caught_up and state.match_index >= self.leader_last_index
    
    def update_leader_index(self, new_last_index: int) -> None:
        """Update the leader's last index when log grows.
        
        Args:
            new_last_index: The new last index of the leader's log.
        """
        self.leader_last_index = new_last_index
        
        # Mark all as needing catch-up if leader index advanced
        for state in self.follower_states.values():
            if state.match_index < new_last_index:
                state.is_caught_up = False
    
    def get_catch_up_status(self, follower_id: str) -> Dict:
        """Get catch-up status for a follower.
        
        Args:
            follower_id: The follower's ID.
        
        Returns:
            Dictionary with catch-up status information.
        """
        if follower_id not in self.follower_states:
            return {
                "follower_id": follower_id,
                "registered": False,
            }
        
        state = self.follower_states[follower_id]
        lag = self.leader_last_index - state.match_index
        
        return {
            "follower_id": follower_id,
            "registered": True,
            "is_caught_up": state.is_caught_up,
            "match_index": state.match_index,
            "next_index": state.next_index,
            "lag": lag,
            "catchup_attempts": state.catchup_attempts,
            "batch_size": int(state.batch_size),
            "strategy": self.get_catchup_strategy(follower_id).value,
        }
    
    def get_cluster_catch_up_status(self) -> Dict:
        """Get catch-up status for all followers.
        
        Returns:
            Dictionary with cluster-wide catch-up information.
        """
        caught_up = []
        lagging = []
        
        for fid, state in self.follower_states.items():
            lag = self.leader_last_index - state.match_index
            
            if state.is_caught_up:
                caught_up.append(fid)
            else:
                lagging.append((fid, lag))
        
        # Sort lagging by lag amount
        lagging.sort(key=lambda x: x[1], reverse=True)
        
        return {
            "leader_last_index": self.leader_last_index,
            "total_followers": len(self.follower_states),
            "caught_up_followers": len(caught_up),
            "lagging_followers": [fid for fid, _ in lagging],
            "lagging_details": [
                {"follower_id": fid, "lag": lag}
                for fid, lag in lagging
            ],
        }
    
    def reset_follower_catchup(self, follower_id: str) -> None:
        """Reset catch-up state for a follower.
        
        Args:
            follower_id: The follower's ID.
        """
        if follower_id in self.follower_states:
            state = self.follower_states[follower_id]
            state.catchup_attempts = 0
            state.last_backtrack = 0
            state.batch_size = 100
            self.catchup_history[follower_id] = []
