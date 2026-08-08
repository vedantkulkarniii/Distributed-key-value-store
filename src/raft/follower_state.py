"""
Follower state management and logic (Phase 3/4).

Handles follower-specific state and rules.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class FollowerState:
    """
    Manages state and behavior of a follower node.
    
    Followers:
    - Vote in elections
    - Accept AppendEntries from leader
    - Apply committed entries
    """
    
    def __init__(self, node_id: str, term: int = 0):
        """Initialize follower state."""
        self.node_id = node_id
        self.current_term = term
        self.voted_for: Optional[str] = None
        self.leader_id: Optional[str] = None
        self.last_heartbeat = 0
    
    def can_vote_for(self, candidate_id: str) -> bool:
        """
        Check if can vote for candidate in current term.
        
        Follows Raft voting rule: one vote per term.
        """
        if self.voted_for is None:
            return True
        
        return self.voted_for == candidate_id
    
    def vote_for(self, candidate_id: str) -> bool:
        """
        Vote for candidate in current term.
        
        Returns:
            True if vote recorded, False if already voted for different candidate
        """
        if not self.can_vote_for(candidate_id):
            logger.warning(
                f"Node {self.node_id}: Cannot vote for {candidate_id} "
                f"(already voted for {self.voted_for})"
            )
            return False
        
        self.voted_for = candidate_id
        logger.debug(
            f"Node {self.node_id}: Voted for {candidate_id} (term={self.current_term})"
        )
        return True
    
    def set_leader(self, leader_id: str, term: int) -> None:
        """
        Set the leader for this term.
        
        Args:
            leader_id: ID of leader
            term: Term number
        """
        if term > self.current_term:
            self.current_term = term
            self.voted_for = None  # Reset vote in new term
        
        self.leader_id = leader_id
        logger.info(
            f"Node {self.node_id}: Leader is {leader_id} (term={self.current_term})"
        )
    
    def advance_term(self, new_term: int) -> bool:
        """
        Advance to new term.
        
        Returns:
            True if term advanced, False if trying to go backwards
        """
        if new_term < self.current_term:
            return False
        
        if new_term > self.current_term:
            self.current_term = new_term
            self.voted_for = None  # Reset vote in new term
            self.leader_id = None  # Uncertain until heartbeat
            logger.info(
                f"Node {self.node_id}: Advanced to term {new_term}"
            )
        
        return True
    
    def get_status(self) -> dict:
        """Get follower status."""
        return {
            "node_id": self.node_id,
            "state": "follower",
            "term": self.current_term,
            "voted_for": self.voted_for,
            "leader_id": self.leader_id,
        }
