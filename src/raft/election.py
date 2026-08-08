"""
Election logic for Raft leader election.

Implements RequestVote RPC processing and vote counting for elections.
"""

import logging
from typing import Dict, List, Optional


logger = logging.getLogger(__name__)


class VoteCounter:
    """
    Counts votes during an election.
    
    Tracks who voted for us and determines if we have quorum.
    """
    
    def __init__(self, node_id: str, total_nodes: int):
        """
        Initialize vote counter.
        
        Args:
            node_id: This node's ID
            total_nodes: Total nodes in cluster
        """
        self.node_id = node_id
        self.total_nodes = total_nodes
        self.quorum = (total_nodes // 2) + 1
        
        # Track votes
        self.votes_received: set[str] = {node_id}  # We always vote for ourselves
        self.votes_rejected: set[str] = set()
        self.term: int = 0
        
        logger.debug(
            f"Node {node_id}: Quorum is {self.quorum}/{total_nodes}"
        )
    
    def record_vote(self, voter_id: str) -> None:
        """
        Record a vote received.
        
        Args:
            voter_id: Node that voted for us
        """
        if voter_id in self.votes_rejected:
            self.votes_rejected.remove(voter_id)
        
        self.votes_received.add(voter_id)
        
        logger.debug(
            f"Node {self.node_id}: Received vote from {voter_id} "
            f"({len(self.votes_received)}/{self.quorum})"
        )
    
    def record_rejection(self, voter_id: str) -> None:
        """
        Record a vote rejection.
        
        Args:
            voter_id: Node that rejected our vote request
        """
        if voter_id in self.votes_received:
            self.votes_received.discard(voter_id)
        
        self.votes_rejected.add(voter_id)
        
        logger.debug(
            f"Node {self.node_id}: Vote rejected by {voter_id} "
            f"({len(self.votes_received)}/{self.quorum})"
        )
    
    def has_quorum(self) -> bool:
        """
        Check if we have enough votes to win.
        
        Returns:
            True if votes >= quorum
        """
        return len(self.votes_received) >= self.quorum
    
    def can_win(self) -> bool:
        """
        Check if we can still win (account for remaining votes).
        
        Returns:
            True if possible to reach quorum with remaining votes
        """
        votes_possible = len(self.votes_received)
        remaining_nodes = self.total_nodes - len(self.votes_received) - len(self.votes_rejected)
        
        return votes_possible + remaining_nodes >= self.quorum
    
    def can_still_win(self) -> bool:
        """
        Alias for can_win() - check if we can still win with remaining votes.
        
        Returns:
            True if possible to reach quorum with remaining votes
        """
        return self.can_win()
    
    def get_status(self) -> Dict:
        """
        Get vote counting status.
        
        Returns:
            Dict with vote statistics
        """
        return {
            "node_id": self.node_id,
            "votes_received": len(self.votes_received),
            "votes_rejected": len(self.votes_rejected),
            "votes_pending": self.total_nodes - len(self.votes_received) - len(self.votes_rejected),
            "quorum": self.quorum,
            "total_nodes": self.total_nodes,
            "has_quorum": self.has_quorum(),
            "can_still_win": self.can_win(),
            "voters": sorted(list(self.votes_received))
        }
    
    def __str__(self) -> str:
        """String representation."""
        return (
            f"VoteCounter({self.node_id}, "
            f"votes={len(self.votes_received)}/{self.quorum}, "
            f"has_quorum={self.has_quorum()})"
        )


class RequestVoteProcessor:
    """
    Processes RequestVote RPC for election handling.
    
    Implements Raft paper rules for vote granting.
    """
    
    def __init__(self, node_id: str, state_provider, log_provider,
                 persistent_state_provider):
        """
        Initialize RequestVote processor.
        
        Args:
            node_id: This node's ID
            state_provider: Provides current state (term, voted_for)
            log_provider: Provides log status (last index/term)
            persistent_state_provider: Manages persistent state
        """
        self.node_id = node_id
        self.state_provider = state_provider
        self.log_provider = log_provider
        self.persistent_state_provider = persistent_state_provider
    
    async def process_request_vote(self, term: int, candidate_id: str,
                                  last_log_index: int, last_log_term: int
                                  ) -> tuple[int, bool]:
        """
        Process a RequestVote RPC.
        
        Implements Raft paper receiver rules:
        1. Reply false if term < currentTerm
        2. If votedFor is null or candidateId, and candidate's log is
           at least as up-to-date as receiver's log, grant vote
        
        Args:
            term: Candidate's term
            candidate_id: Candidate's node ID
            last_log_index: Candidate's last log index
            last_log_term: Candidate's last log term
            
        Returns:
            Tuple of (current_term, vote_granted)
        """
        current_term = await self.state_provider.get_current_term()
        voted_for = await self.state_provider.get_voted_for()
        
        # Rule 1: Reply false if term < currentTerm
        if term < current_term:
            logger.debug(
                f"Node {self.node_id}: Rejecting RequestVote from {candidate_id}: "
                f"stale term ({term} < {current_term})"
            )
            return current_term, False
        
        # Update term if this is higher
        if term > current_term:
            await self.state_provider.advance_term(term)
            current_term = term
            voted_for = None
        
        # Rule 2: Check if we can vote for this candidate
        # We can vote if:
        # 1. We haven't voted in this term, OR
        # 2. We already voted for this candidate
        
        if voted_for is not None and voted_for != candidate_id:
            logger.debug(
                f"Node {self.node_id}: Rejecting RequestVote from {candidate_id}: "
                f"already voted for {voted_for} in term {current_term}"
            )
            return current_term, False
        
        # Check if candidate's log is up-to-date
        our_last_index = await self.log_provider.get_last_log_index()
        our_last_term = await self.log_provider.get_last_log_term()
        
        if not self._is_log_up_to_date(last_log_term, last_log_index,
                                      our_last_term, our_last_index):
            logger.debug(
                f"Node {self.node_id}: Rejecting RequestVote from {candidate_id}: "
                f"candidate log not up-to-date "
                f"(candidate: term={last_log_term} index={last_log_index}, "
                f"ours: term={our_last_term} index={our_last_index})"
            )
            return current_term, False
        
        # All checks pass, grant vote
        await self.persistent_state_provider.set_voted_for(candidate_id)
        
        logger.info(
            f"Node {self.node_id}: Granting vote to {candidate_id} for term {term}"
        )
        
        return current_term, True
    
    @staticmethod
    def _is_log_up_to_date(candidate_last_term: int, candidate_last_index: int,
                          our_last_term: int, our_last_index: int) -> bool:
        """
        Check if candidate's log is at least as up-to-date as ours.
        
        Raft definition: Candidate's log is more up-to-date if:
        1. Its last term is higher than ours, OR
        2. Last terms are equal AND its last index >= ours
        
        Args:
            candidate_last_term: Candidate's last log term
            candidate_last_index: Candidate's last log index
            our_last_term: Our last log term
            our_last_index: Our last log index
            
        Returns:
            True if candidate is up-to-date, False otherwise
        """
        # Candidate has higher last term
        if candidate_last_term > our_last_term:
            return True
        
        # Same last term, check index
        if candidate_last_term == our_last_term:
            return candidate_last_index >= our_last_index
        
        # Candidate has lower term
        return False


class ElectionRunner:
    """
    Runs an election campaign for a candidate.
    
    Sends RequestVote RPCs to all peers and counts votes.
    """
    
    def __init__(self, node_id: str, peers: List[str], vote_counter: VoteCounter):
        """
        Initialize election runner.
        
        Args:
            node_id: This node's ID
            peers: List of peer node IDs
            vote_counter: VoteCounter for tracking votes
        """
        self.node_id = node_id
        self.peers = peers
        self.vote_counter = vote_counter
        self.started_at: Optional[datetime] = None
    
    def reset(self) -> None:
        """Reset for a new election."""
        self.vote_counter = VoteCounter(self.node_id, len(self.peers) + 1)
        self.started_at = None
        logger.debug(f"Node {self.node_id}: Reset election runner")
    
    def record_vote(self, peer_id: str, granted: bool) -> None:
        """
        Record a vote response.
        
        Args:
            peer_id: Peer that responded
            granted: Whether vote was granted
        """
        if granted:
            self.vote_counter.record_vote(peer_id)
        else:
            self.vote_counter.record_rejection(peer_id)
    
    def is_winner(self) -> bool:
        """Check if we have quorum."""
        return self.vote_counter.has_quorum()
    
    def is_viable(self) -> bool:
        """Check if we can still win."""
        return self.vote_counter.can_win()
    
    def get_status(self) -> Dict:
        """Get election status."""
        return self.vote_counter.get_status()
    
    def __str__(self) -> str:
        """String representation."""
        return f"ElectionRunner({self.vote_counter})"


# Import here to avoid circular dependency
from datetime import datetime
