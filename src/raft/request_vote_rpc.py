"""
RequestVote RPC implementation (Phase 3).

Integrates with RPC layer for vote requests and responses.
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class RequestVoteRPC:
    """
    RequestVote RPC message and handler.
    
    Per Raft paper:
    - Candidate requests votes from all peers
    - Follower grants vote if conditions met
    """
    
    def __init__(self, term: int, candidate_id: str, last_log_index: int, last_log_term: int):
        """Initialize RequestVote RPC."""
        self.term = term
        self.candidate_id = candidate_id
        self.last_log_index = last_log_index
        self.last_log_term = last_log_term
    
    def to_dict(self) -> Dict:
        """Serialize to dict for network transmission."""
        return {
            "type": "RequestVote",
            "term": self.term,
            "candidate_id": self.candidate_id,
            "last_log_index": self.last_log_index,
            "last_log_term": self.last_log_term,
        }
    
    @staticmethod
    def from_dict(data: Dict) -> "RequestVoteRPC":
        """Deserialize from dict."""
        return RequestVoteRPC(
            term=data["term"],
            candidate_id=data["candidate_id"],
            last_log_index=data.get("last_log_index", 0),
            last_log_term=data.get("last_log_term", 0),
        )


class RequestVoteResponse:
    """RequestVote RPC response."""
    
    def __init__(self, term: int, vote_granted: bool):
        """Initialize response."""
        self.term = term
        self.vote_granted = vote_granted
    
    def to_dict(self) -> Dict:
        """Serialize to dict."""
        return {
            "type": "RequestVoteResponse",
            "term": self.term,
            "vote_granted": self.vote_granted,
        }
    
    @staticmethod
    def from_dict(data: Dict) -> "RequestVoteResponse":
        """Deserialize from dict."""
        return RequestVoteResponse(
            term=data["term"],
            vote_granted=data["vote_granted"],
        )


class RequestVoteHandler:
    """
    Handles incoming RequestVote RPC.
    
    Implements Raft rules for voting:
    1. If term < currentTerm, return false
    2. If votedFor is null or candidateId, continue
    3. If candidate's log is at least as up-to-date, grant vote
    """
    
    def __init__(self, node_id: str):
        """Initialize handler."""
        self.node_id = node_id
    
    async def handle_request_vote(
        self,
        current_term: int,
        voted_for: Optional[str],
        request: RequestVoteRPC
    ) -> RequestVoteResponse:
        """
        Handle incoming RequestVote RPC.
        
        Args:
            current_term: Node's current term
            voted_for: Who node voted for in this term
            request: RequestVote RPC
            
        Returns:
            RequestVoteResponse
        """
        logger.debug(
            f"Node {self.node_id}: Handling RequestVote from {request.candidate_id} "
            f"(term={request.term}, current_term={current_term})"
        )
        
        # Rule 1: If request term < current term, reject
        if request.term < current_term:
            logger.debug(
                f"Node {self.node_id}: Rejecting vote (stale term)"
            )
            return RequestVoteResponse(current_term, False)
        
        # Rule 2: If voted for different candidate, reject
        if voted_for is not None and voted_for != request.candidate_id:
            logger.debug(
                f"Node {self.node_id}: Rejecting vote (already voted for {voted_for})"
            )
            return RequestVoteResponse(request.term, False)
        
        # Rule 3: Check log up-to-date
        # Phase 4 will implement actual log comparison
        # For now, accept if rules 1-2 pass
        logger.info(
            f"Node {self.node_id}: Granted vote to {request.candidate_id}"
        )
        return RequestVoteResponse(request.term, True)
