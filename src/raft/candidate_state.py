"""
Candidate state management (Phase 3).

Handles candidate-specific state and election logic.
"""

import logging

logger = logging.getLogger(__name__)


class CandidateState:
    """
    Manages state and behavior of a candidate node.
    
    Candidates:
    - Request votes from peers
    - Track received votes
    - Become leaders or revert to followers
    """
    
    def __init__(self, node_id: str, term: int):
        """Initialize candidate state."""
        self.node_id = node_id
        self.current_term = term
        self.voted_for = node_id  # Candidate votes for itself
        self.votes_received = {node_id}  # Start with self vote
        self.votes_rejected = set()
    
    def receive_vote(self, peer_id: str) -> bool:
        """
        Record vote from peer.
        
        Returns:
            True if vote recorded, False if duplicate
        """
        if peer_id in self.votes_received:
            return False
        
        self.votes_received.add(peer_id)
        logger.debug(
            f"Node {self.node_id}: Received vote from {peer_id} "
            f"({len(self.votes_received)} votes)"
        )
        return True
    
    def receive_rejection(self, peer_id: str) -> bool:
        """
        Record vote rejection.
        
        Returns:
            True if rejection recorded, False if duplicate
        """
        if peer_id in self.votes_rejected:
            return False
        
        self.votes_rejected.add(peer_id)
        logger.debug(
            f"Node {self.node_id}: Vote rejected by {peer_id} "
            f"({len(self.votes_rejected)} rejections)"
        )
        return True
    
    def advance_term(self, new_term: int) -> bool:
        """
        Advance to new term.
        
        Candidate becomes follower in higher term.
        
        Returns:
            True if term advanced, False if trying to go backwards
        """
        if new_term < self.current_term:
            return False
        
        if new_term > self.current_term:
            self.current_term = new_term
            logger.info(
                f"Node {self.node_id}: Reverted to follower (new term={new_term})"
            )
        
        return True
    
    def get_status(self) -> dict:
        """Get candidate status."""
        return {
            "node_id": self.node_id,
            "state": "candidate",
            "term": self.current_term,
            "votes_received": len(self.votes_received),
            "votes_rejected": len(self.votes_rejected),
        }
