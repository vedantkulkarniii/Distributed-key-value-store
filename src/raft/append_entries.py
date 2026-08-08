"""
AppendEntries RPC handler for log replication and heartbeats (Phase 4 prep).

Implements:
- Heartbeat mechanism (empty entries)
- Log entry replication
- Follower commitment tracking
"""

import logging
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)


class AppendEntriesHandler:
    """
    Handles AppendEntries RPC from leader.
    
    Phase 4 will fully implement log replication.
    Here we prepare the structure.
    """
    
    def __init__(self, node_id: str):
        """Initialize handler."""
        self.node_id = node_id
        self.last_applied = 0
        self.commit_index = 0
    
    async def handle_append_entries(
        self,
        term: int,
        leader_id: str,
        prev_log_index: int,
        prev_log_term: int,
        entries: List[Dict],
        leader_commit: int
    ) -> bool:
        """
        Handle AppendEntries RPC.
        
        Phase 4: Full implementation with log checks.
        Now: Basic structure for heartbeats.
        """
        # Log the heartbeat or entries
        logger.debug(
            f"Node {self.node_id}: Received AppendEntries from {leader_id} "
            f"(term={term}, entries={len(entries)})"
        )
        
        # Phase 4: Will check prev_log_index and prev_log_term
        # Phase 4: Will append entries to log
        # Phase 4: Will update commit_index
        
        return True
    
    def apply_entries(self) -> int:
        """
        Apply committed entries to state machine.
        
        Returns:
            Number of entries applied
        """
        # Phase 4: Iterate from last_applied to commit_index
        # Phase 4: Apply each entry to state machine
        return 0


class LeaderHeartbeat:
    """Sends heartbeats to followers (Phase 4 prep)."""
    
    def __init__(self, node_id: str, followers: List[str]):
        """Initialize leader heartbeat."""
        self.node_id = node_id
        self.followers = followers
        self.heartbeat_interval = 0.15  # 150ms
    
    async def send_heartbeats(self, term: int) -> Dict[str, bool]:
        """
        Send heartbeats to all followers.
        
        Returns:
            Dict mapping follower_id -> ack_received
        """
        logger.debug(
            f"Leader {self.node_id}: Sending heartbeats to {len(self.followers)} followers"
        )
        
        # Phase 4: Will send actual AppendEntries RPC to each follower
        # Phase 4: Will collect responses
        
        return {follower: True for follower in self.followers}
