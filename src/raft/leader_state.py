"""
Leader state and replicated state management.

Implements leader-specific state tracking:
- nextIndex for each follower (log replication)
- matchIndex for each follower (confirmed replication)
- Leader initialization and maintenance
"""

import logging
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ReplicationState:
    """Tracks replication state for a single follower."""
    
    def __init__(self, node_id: str, log_length: int):
        """
        Initialize replication state for a follower.
        
        Args:
            node_id: Follower node ID
            log_length: Length of leader's log
        """
        self.node_id = node_id
        self.next_index = log_length  # Next log entry to send to this follower
        self.match_index = 0  # Highest log index known to be replicated on this follower
        self.last_update = datetime.now()
    
    def update_next_index(self, index: int) -> bool:
        """
        Update next_index when AppendEntries succeeds.
        
        Args:
            index: New next_index value
            
        Returns:
            True if updated, False if already >= index
        """
        if index > self.next_index:
            self.next_index = index
            self.last_update = datetime.now()
            return True
        return False
    
    def decrement_next_index(self) -> None:
        """Decrement next_index (used after AppendEntries rejection)."""
        if self.next_index > 1:
            self.next_index -= 1
            self.last_update = datetime.now()
    
    def update_match_index(self, index: int) -> bool:
        """
        Update match_index when AppendEntries succeeds.
        
        Args:
            index: Log index that was replicated
            
        Returns:
            True if updated, False if already >= index
        """
        if index >= self.match_index:
            self.match_index = index
            self.last_update = datetime.now()
            return True
        return False
    
    def get_status(self) -> dict:
        """Get replication status."""
        return {
            "node_id": self.node_id,
            "next_index": self.next_index,
            "match_index": self.match_index,
            "last_update": self.last_update.isoformat()
        }


class LeaderState:
    """Manages leader-specific state and responsibilities."""
    
    def __init__(self, leader_id: str, nodes: list, log_length: int):
        """
        Initialize leader state.
        
        Args:
            leader_id: This leader's node ID
            nodes: List of all node IDs (including self)
            log_length: Current length of replicated log
        """
        self.leader_id = leader_id
        self.nodes = nodes
        self.log_length = log_length
        
        # Replication state for each follower
        self.replication_states: Dict[str, ReplicationState] = {}
        for node_id in nodes:
            if node_id != leader_id:
                self.replication_states[node_id] = ReplicationState(node_id, log_length)
        
        # Commit index tracking
        self.commit_index = 0
        self.leader_elected_at = datetime.now()
        
        logger.info(
            f"Leader {leader_id}: Initialized with {len(nodes)} nodes, "
            f"log_length={log_length}"
        )
    
    def get_next_index_for_follower(self, node_id: str) -> Optional[int]:
        """Get next_index for a follower."""
        state = self.replication_states.get(node_id)
        return state.next_index if state else None
    
    def get_match_index_for_follower(self, node_id: str) -> Optional[int]:
        """Get match_index for a follower."""
        state = self.replication_states.get(node_id)
        return state.match_index if state else None
    
    def handle_append_entries_success(self, node_id: str, last_log_index: int) -> bool:
        """
        Handle successful AppendEntries RPC response.
        
        Args:
            node_id: Follower that acknowledged
            last_log_index: Last log index on follower
            
        Returns:
            True if replication state was updated
        """
        state = self.replication_states.get(node_id)
        if not state:
            return False
        
        updated = state.update_match_index(last_log_index)
        state.update_next_index(last_log_index + 1)
        
        if updated:
            logger.debug(
                f"Leader {self.leader_id}: {node_id} replicated up to index {last_log_index}"
            )
        
        return updated
    
    def handle_append_entries_failure(self, node_id: str) -> bool:
        """
        Handle failed AppendEntries RPC response.
        
        Args:
            node_id: Follower that rejected
            
        Returns:
            True if next_index was decremented
        """
        state = self.replication_states.get(node_id)
        if not state:
            return False
        
        old_index = state.next_index
        state.decrement_next_index()
        
        if old_index > state.next_index:
            logger.debug(
                f"Leader {self.leader_id}: Decrementing {node_id} next_index "
                f"from {old_index} to {state.next_index}"
            )
            return True
        
        return False
    
    def calculate_commit_index(self) -> int:
        """
        Calculate new commit index based on replicated entries.
        
        Returns:
            New commit index (or current if no majority reached)
        """
        # Collect match_index values from all followers
        match_indices = [state.match_index for state in self.replication_states.values()]
        
        # Include leader's log length (leader always has everything up to current)
        match_indices.append(self.log_length)
        
        # Sort in descending order
        match_indices.sort(reverse=True)
        
        # Calculate majority (N/2 + 1)
        majority_idx = len(match_indices) // 2
        potential_commit = match_indices[majority_idx]
        
        if potential_commit > self.commit_index:
            logger.info(
                f"Leader {self.leader_id}: Advancing commit_index from "
                f"{self.commit_index} to {potential_commit}"
            )
            self.commit_index = potential_commit
        
        return self.commit_index
    
    def is_replication_complete(self, log_index: int) -> bool:
        """
        Check if a log entry is replicated to a majority.
        
        Args:
            log_index: Log index to check
            
        Returns:
            True if replicated to majority of followers (plus leader)
        """
        replicated_count = 0
        
        # Count leader
        if log_index <= self.log_length:
            replicated_count += 1
        
        # Count followers
        for state in self.replication_states.values():
            if state.match_index >= log_index:
                replicated_count += 1
        
        # Need majority
        majority = (len(self.nodes) // 2) + 1
        return replicated_count >= majority
    
    def get_replication_status(self) -> dict:
        """Get status of replication to all followers."""
        return {
            "leader_id": self.leader_id,
            "commit_index": self.commit_index,
            "log_length": self.log_length,
            "followers": {
                node_id: state.get_status()
                for node_id, state in self.replication_states.items()
            },
            "leader_uptime_seconds": (datetime.now() - self.leader_elected_at).total_seconds()
        }
    
    def is_caught_up(self, node_id: str, log_length: int) -> bool:
        """
        Check if a follower is caught up with current log.
        
        Args:
            node_id: Follower to check
            log_length: Current log length
            
        Returns:
            True if follower's match_index >= log_length
        """
        state = self.replication_states.get(node_id)
        return state and state.match_index >= log_length
    
    def all_caught_up(self) -> bool:
        """Check if all followers are caught up."""
        return all(
            state.match_index >= self.log_length
            for state in self.replication_states.values()
        )
    
    def update_log_length(self, new_length: int) -> None:
        """
        Update log length (when leader appends new entries).
        
        Args:
            new_length: New total log length
        """
        if new_length > self.log_length:
            self.log_length = new_length
            logger.debug(f"Leader {self.leader_id}: Log extended to {new_length}")
    
    def get_slow_followers(self, threshold: int = 5) -> list:
        """
        Get list of slow followers (with high next_index delta).
        
        Args:
            threshold: Minimum delta to consider slow
            
        Returns:
            List of (node_id, delta) tuples for slow followers
        """
        slow = []
        for node_id, state in self.replication_states.items():
            delta = self.log_length - state.next_index
            if delta >= threshold:
                slow.append((node_id, delta))
        
        return sorted(slow, key=lambda x: x[1], reverse=True)
    
    def __str__(self) -> str:
        """String representation."""
        status_str = f"Leader {self.leader_id}: "
        status_str += f"commit_index={self.commit_index}, "
        status_str += f"log_length={self.log_length}, "
        status_str += f"{len(self.replication_states)} followers"
        return status_str
