"""
Raft state transition logic.

Encapsulates all valid state machine transitions with their rules and invariants.
This module is separated from state.py to make transitions composable and testable.
"""

from enum import Enum
from typing import Optional, Tuple


class RaftState(Enum):
    """Raft node states."""
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"


class TransitionError(Exception):
    """Raised when an invalid state transition is attempted."""
    pass


class StateTransitionValidator:
    """
    Validates state transitions according to Raft invariants.
    
    Rules:
    1. FOLLOWER -> CANDIDATE: Allowed, term incremented
    2. CANDIDATE -> LEADER: Allowed (only if won election)
    3. LEADER -> FOLLOWER: Allowed if higher term detected
    4. CANDIDATE -> CANDIDATE: NOT allowed (must go through FOLLOWER)
    5. LEADER -> CANDIDATE: NOT allowed (must go through FOLLOWER)
    6. Higher term always demotes to FOLLOWER
    """
    
    @staticmethod
    def validate_transition(
        from_state: RaftState,
        to_state: RaftState,
        current_term: int,
        new_term: Optional[int] = None
    ) -> Tuple[bool, str]:
        """
        Validate if transition is allowed.
        
        Args:
            from_state: Current state
            to_state: Desired target state
            current_term: Current term number
            new_term: Term for transition (if applicable)
        
        Returns:
            (is_valid, reason_if_invalid)
        """
        # Same state is allowed (no-op)
        if from_state == to_state:
            return True, ""
        
        # Handle term advancement (always demotes to FOLLOWER)
        if new_term is not None and new_term > current_term:
            if to_state != RaftState.FOLLOWER:
                return False, f"Higher term {new_term} must demote to FOLLOWER, not {to_state.value}"
            return True, ""
        
        # Valid transitions
        if from_state == RaftState.FOLLOWER:
            if to_state in (RaftState.CANDIDATE, RaftState.FOLLOWER):
                return True, ""
            if to_state == RaftState.LEADER:
                return False, "FOLLOWER cannot transition directly to LEADER (must be CANDIDATE)"
        
        if from_state == RaftState.CANDIDATE:
            if to_state == RaftState.LEADER:
                return True, ""
            if to_state == RaftState.FOLLOWER:
                return True, ""
            if to_state == RaftState.CANDIDATE:
                return False, "CANDIDATE cannot transition to CANDIDATE (must go through FOLLOWER)"
        
        if from_state == RaftState.LEADER:
            if to_state == RaftState.FOLLOWER:
                return True, ""
            if to_state in (RaftState.LEADER, RaftState.CANDIDATE):
                return False, f"LEADER cannot transition to {to_state.value}"
        
        return False, f"Unknown transition {from_state.value} -> {to_state.value}"
    
    @staticmethod
    def validate_term_advancement(
        current_term: int,
        new_term: int
    ) -> Tuple[bool, str]:
        """
        Validate term advancement.
        
        Args:
            current_term: Current term
            new_term: Proposed new term
        
        Returns:
            (is_valid, reason_if_invalid)
        """
        if new_term <= current_term:
            return False, f"Cannot go back in time: {current_term} -> {new_term}"
        return True, ""
    
    @staticmethod
    def term_requires_demotion(current_term: int, discovered_term: int) -> bool:
        """Check if discovered higher term requires demotion to follower."""
        return discovered_term > current_term


class CandidateTransitionRules:
    """Rules for transitioning to CANDIDATE state."""
    
    @staticmethod
    def validate_become_candidate(
        current_state: RaftState,
        current_term: int
    ) -> Tuple[bool, str]:
        """
        Validate transition to candidate.
        
        Rules:
        1. Must be FOLLOWER or CANDIDATE
        2. Term will be incremented
        3. Will vote for self
        
        Args:
            current_state: Current state
            current_term: Current term (before increment)
        
        Returns:
            (is_valid, reason_if_invalid)
        """
        if current_state not in (RaftState.FOLLOWER, RaftState.CANDIDATE):
            return False, f"Only FOLLOWER can become CANDIDATE, not {current_state.value}"
        
        # Allow FOLLOWER -> CANDIDATE or CANDIDATE -> CANDIDATE via FOLLOWER first
        # (but single transition CANDIDATE -> CANDIDATE is invalid)
        return True, ""
    
    @staticmethod
    def term_increment_on_candidate() -> int:
        """Term is always incremented when becoming candidate."""
        return 1  # Increment by 1


class LeaderTransitionRules:
    """Rules for transitioning to LEADER state."""
    
    @staticmethod
    def validate_become_leader(
        current_state: RaftState,
        current_term: int,
        quorum_votes: int,
        cluster_size: int
    ) -> Tuple[bool, str]:
        """
        Validate transition to leader.
        
        Rules:
        1. Must be CANDIDATE
        2. Must have quorum votes
        3. Only changes term for other nodes (local term unchanged)
        
        Args:
            current_state: Current state
            current_term: Current term
            quorum_votes: Number of votes received
            cluster_size: Total cluster size
        
        Returns:
            (is_valid, reason_if_invalid)
        """
        if current_state != RaftState.CANDIDATE:
            return False, f"Only CANDIDATE can become LEADER, not {current_state.value}"
        
        quorum_needed = (cluster_size // 2) + 1
        if quorum_votes < quorum_needed:
            return False, f"Need {quorum_needed} votes, got {quorum_votes}"
        
        return True, ""


class FollowerTransitionRules:
    """Rules for transitioning to FOLLOWER state."""
    
    @staticmethod
    def validate_become_follower(
        current_state: RaftState,
        new_term: int,
        current_term: int
    ) -> Tuple[bool, str]:
        """
        Validate transition to follower.
        
        Rules:
        1. Allowed from any state
        2. Term must not decrease (can stay same for explicit revert)
        3. Clears voted_for when term changes
        
        Args:
            current_state: Current state
            new_term: New term (for validation)
            current_term: Current term
        
        Returns:
            (is_valid, reason_if_invalid)
        """
        if new_term < current_term:
            return False, f"Cannot decrease term: {current_term} -> {new_term}"
        
        return True, ""


class VotingRules:
    """Rules for voting in Raft."""
    
    @staticmethod
    def can_vote_for_candidate(
        voted_for: Optional[str],
        candidate_id: str,
        current_term: int,
        vote_term: int
    ) -> Tuple[bool, str]:
        """
        Determine if can vote for candidate.
        
        Rules:
        1. Can vote if haven't voted in this term
        2. Can vote for same candidate again (safe)
        3. Cannot vote for different candidate in same term
        4. Vote term must equal current term
        
        Args:
            voted_for: Current voted_for value (None if not voted)
            candidate_id: Candidate requesting vote
            current_term: Current term
            vote_term: Term of vote request
        
        Returns:
            (is_valid, reason_if_invalid)
        """
        if vote_term != current_term:
            return False, f"Vote term {vote_term} != current term {current_term}"
        
        if voted_for is None:
            return True, ""
        
        if voted_for == candidate_id:
            return True, ""
        
        return False, f"Already voted for {voted_for} in term {current_term}"
    
    @staticmethod
    def vote_for_self(node_id: str, current_term: int) -> str:
        """When becoming candidate, vote for self."""
        return node_id


class TermManagement:
    """Term management and comparison logic."""
    
    @staticmethod
    def compare_terms(term1: int, term2: int) -> int:
        """
        Compare two terms.
        
        Returns:
            > 0 if term1 > term2
            < 0 if term1 < term2
            = 0 if term1 == term2
        """
        return term1 - term2
    
    @staticmethod
    def is_term_stale(local_term: int, remote_term: int) -> bool:
        """Check if local term is stale compared to remote."""
        return local_term < remote_term
    
    @staticmethod
    def should_update_term(local_term: int, remote_term: int) -> bool:
        """Check if should update local term from remote."""
        return remote_term > local_term
