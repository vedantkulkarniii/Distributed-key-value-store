"""
Raft state machine: Follower, Candidate, and Leader roles.

Implements the three states a Raft node can be in, with allowed transitions.
"""

import logging
from enum import Enum
from typing import Optional, Set
from datetime import datetime


logger = logging.getLogger(__name__)


class RaftState(Enum):
    """Raft node state."""
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"
    
    def __str__(self) -> str:
        return self.value


class NodeRole:
    """
    Represents the current role of a Raft node.
    
    Tracks:
    - Current state (Follower, Candidate, Leader)
    - Current term
    - Who we voted for
    - When state changed
    """
    
    def __init__(self, node_id: str, initial_state: RaftState = RaftState.FOLLOWER):
        """
        Initialize node role.
        
        Args:
            node_id: Unique node identifier
            initial_state: Starting state (usually Follower)
        """
        self.node_id = node_id
        self.current_state = initial_state
        self.current_term = 0
        self.voted_for: Optional[str] = None  # Candidate ID we voted for in current term
        
        # Timing
        self.state_changed_at = datetime.now()
        
        # Leader-specific
        self.leader_id: Optional[str] = None  # ID of current leader (if known)
        
        logger.info(
            f"Node {node_id}: Initialized in {initial_state} state"
        )
    
    # State query methods
    
    def is_follower(self) -> bool:
        """Check if in Follower state."""
        return self.current_state == RaftState.FOLLOWER
    
    def is_candidate(self) -> bool:
        """Check if in Candidate state."""
        return self.current_state == RaftState.CANDIDATE
    
    def is_leader(self) -> bool:
        """Check if in Leader state."""
        return self.current_state == RaftState.LEADER
    
    # State transition methods
    
    async def become_follower(self, term: int, leader_id: Optional[str] = None) -> None:
        """
        Transition to Follower state.
        
        Args:
            term: New term
            leader_id: Optional ID of current leader
        """
        # Can transition from any state
        if self.current_state == RaftState.FOLLOWER and self.current_term == term:
            # Already a follower in this term, no state change
            return
        
        old_state = self.current_state
        self.current_state = RaftState.FOLLOWER
        self.current_term = term
        self.leader_id = leader_id
        self.voted_for = None  # Clear vote when moving to new term
        self.state_changed_at = datetime.now()
        
        logger.info(
            f"Node {self.node_id}: Transitioned from {old_state} to Follower "
            f"(term={term}, leader={leader_id})"
        )
    
    async def become_candidate(self) -> None:
        """
        Transition to Candidate state.
        
        Can only transition from Follower.
        Increments term and votes for self.
        """
        if not self.is_follower():
            logger.warning(
                f"Node {self.node_id}: Cannot become candidate from {self.current_state}"
            )
            return
        
        # Increment term and vote for self
        self.current_term += 1
        self.voted_for = self.node_id
        self.leader_id = None
        
        old_state = self.current_state
        self.current_state = RaftState.CANDIDATE
        self.state_changed_at = datetime.now()
        
        logger.info(
            f"Node {self.node_id}: Transitioned from {old_state} to Candidate "
            f"(term={self.current_term})"
        )
    
    async def become_leader(self) -> None:
        """
        Transition to Leader state.
        
        Can only transition from Candidate.
        """
        if not self.is_candidate():
            logger.warning(
                f"Node {self.node_id}: Cannot become leader from {self.current_state}"
            )
            return
        
        old_state = self.current_state
        self.current_state = RaftState.LEADER
        self.leader_id = self.node_id
        self.state_changed_at = datetime.now()
        
        logger.info(
            f"Node {self.node_id}: Transitioned from {old_state} to Leader "
            f"(term={self.current_term})"
        )
    
    # Term management
    
    def advance_term(self, new_term: int) -> bool:
        """
        Advance to a higher term.
        
        Returns to Follower state when advancing term.
        
        Args:
            new_term: New term (must be > current_term)
            
        Returns:
            True if term was advanced, False if new_term <= current_term
        """
        if new_term <= self.current_term:
            return False
        
        old_term = self.current_term
        self.current_term = new_term
        
        # Advance term means return to follower
        if not self.is_follower():
            self.current_state = RaftState.FOLLOWER
            self.voted_for = None
            self.leader_id = None
            logger.info(
                f"Node {self.node_id}: Advanced term from {old_term} to {new_term}, "
                f"became Follower"
            )
        else:
            self.voted_for = None  # Clear vote for new term
            logger.debug(
                f"Node {self.node_id}: Advanced term from {old_term} to {new_term}"
            )
        
        return True
    
    # Vote management
    
    def set_voted_for(self, candidate_id: str) -> bool:
        """
        Record that we voted for a candidate in current term.
        
        Args:
            candidate_id: Candidate we're voting for
            
        Returns:
            True if vote was recorded, False if already voted for someone else
        """
        if self.voted_for is not None and self.voted_for != candidate_id:
            logger.debug(
                f"Node {self.node_id}: Already voted for {self.voted_for} in term {self.current_term}"
            )
            return False
        
        self.voted_for = candidate_id
        logger.debug(
            f"Node {self.node_id}: Voted for {candidate_id} in term {self.current_term}"
        )
        return True
    
    def has_voted_in_term(self) -> bool:
        """Check if we've already voted in current term."""
        return self.voted_for is not None
    
    # Status
    
    def get_status(self) -> dict:
        """
        Get current role status.
        
        Returns:
            Dict with role information
        """
        return {
            "node_id": self.node_id,
            "state": str(self.current_state),
            "term": self.current_term,
            "voted_for": self.voted_for,
            "leader_id": self.leader_id,
            "state_duration_seconds": (
                (datetime.now() - self.state_changed_at).total_seconds()
            )
        }
    
    def __str__(self) -> str:
        """String representation."""
        return (
            f"NodeRole({self.node_id}, state={self.current_state}, "
            f"term={self.current_term}, voted_for={self.voted_for})"
        )


class RaftStateMachine:
    """
    Manages Raft state machine transitions and term management.
    
    Enforces state machine rules:
    1. Only one leader per term
    2. Terms are strictly increasing
    3. State transitions follow allowed paths
    4. Persistent state persisted before RPC responses
    """
    
    def __init__(self, node_id: str, persistent_state_provider):
        """
        Initialize Raft state machine.
        
        Args:
            node_id: Node ID
            persistent_state_provider: Object providing persistent state methods
        """
        self.node_id = node_id
        self.role = NodeRole(node_id)
        self.persistent_state_provider = persistent_state_provider
    
    async def become_follower(self, term: int, leader_id: Optional[str] = None) -> None:
        """Become follower and persist state."""
        await self.role.become_follower(term, leader_id)
        
        # Persist state
        await self.persistent_state_provider.set_term(term)
        await self.persistent_state_provider.set_voted_for(None)
    
    async def become_candidate(self) -> None:
        """Become candidate and persist state."""
        old_term = self.role.current_term
        await self.role.become_candidate()
        
        # Persist incremented term and vote for self
        await self.persistent_state_provider.set_term(self.role.current_term)
        await self.persistent_state_provider.set_voted_for(self.node_id)
        
        logger.info(
            f"Node {self.node_id}: Starting election for term {self.role.current_term}"
        )
    
    async def become_leader(self) -> None:
        """Become leader."""
        await self.role.become_leader()
        logger.info(
            f"Node {self.node_id}: Won election and became leader for term {self.role.current_term}"
        )
    
    async def advance_term(self, new_term: int) -> bool:
        """
        Advance to higher term.
        
        Persists new term before returning.
        """
        if not self.role.advance_term(new_term):
            return False
        
        # Persist new term
        await self.persistent_state_provider.set_term(new_term)
        await self.persistent_state_provider.set_voted_for(None)
        
        return True
    
    async def vote_for(self, candidate_id: str) -> bool:
        """
        Vote for a candidate.
        
        Persists vote before returning.
        """
        if not self.role.set_voted_for(candidate_id):
            return False
        
        # Persist vote
        await self.persistent_state_provider.set_voted_for(candidate_id)
        
        return True
    
    def get_status(self) -> dict:
        """Get state machine status."""
        return self.role.get_status()


# State transition diagram

"""
Allowed state transitions in Raft:

                    Follower
                   /        \\
                  /          \\
             election       receive
            timeout          higher
              |              term
              |                |
              v                v
           Candidate -------> Follower
              |       \       ^
              |        \     /
          votes from    become
         majority       follower
              |              
              v              
            Leader

Rules:
1. Follower -> Candidate: On election timeout
2. Candidate -> Leader: On receiving majority votes
3. Candidate -> Follower: On receiving valid AppendEntries from leader
                           OR receiving higher term
4. Follower -> Follower: On receiving valid heartbeat (resets election timeout)
5. Leader -> Follower: On discovering higher term
6. Any state -> Follower: On discovering higher term (always enforced)

Persistent state:
- currentTerm: Must be persisted before sending any RPC
- votedFor: Must be persisted before voting
- log: Must be persisted before sending log to followers
"""
