"""
RPC message handlers for Raft consensus.

Handlers for RequestVote and AppendEntries RPCs that implement the core
Raft algorithm rules.
"""

import logging
from typing import Callable, Optional, Dict, Any
from abc import ABC, abstractmethod


logger = logging.getLogger(__name__)


class RPCHandler(ABC):
    """Base class for RPC handlers."""
    
    @abstractmethod
    async def handle(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle an RPC request.
        
        Args:
            data: RPC data dictionary
            
        Returns:
            Response data dictionary
        """
        pass


class RequestVoteHandler(RPCHandler):
    """
    Handler for RequestVote RPC.
    
    Called when a peer node is requesting this node's vote in an election.
    
    RequestVote RPC:
      Args:
        term - candidate's term
        candidateId - candidate requesting vote
        lastLogIndex - index of candidate's last log entry
        lastLogTerm - term of candidate's last log entry
      
      Results:
        term - currentTerm for candidate to update itself
        voteGranted - true means candidate received vote
    
    Receiver implementation rules:
      1. Reply false if term < currentTerm
      2. If votedFor is null or candidateId, and candidate's log is at
         least as up-to-date as receiver's log, grant vote
      3. Otherwise, reply false
    """
    
    def __init__(self, get_state: Callable, should_vote: Callable):
        """
        Initialize the RequestVote handler.
        
        Args:
            get_state: Async callable returning (term, voted_for, log_length, log_term)
            should_vote: Async callable(term, candidate_id, last_log_index, last_log_term) -> bool
        """
        self.get_state = get_state
        self.should_vote = should_vote
    
    async def handle(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle RequestVote RPC.
        
        Args:
            data: RequestVote RPC data
            
        Returns:
            Response with term and vote_granted
        """
        term = data.get('term')
        candidate_id = data.get('candidate_id')
        last_log_index = data.get('last_log_index', 0)
        last_log_term = data.get('last_log_term', 0)
        
        # Validate required fields
        if term is None or candidate_id is None:
            logger.warning("RequestVote missing required fields")
            return {"error": "Missing required fields"}
        
        try:
            # Get current state
            current_term, voted_for, log_length, log_term = await self.get_state()
            
            # Rule 1: Reply false if term < currentTerm
            if term < current_term:
                logger.debug(
                    f"Rejecting vote from {candidate_id}: "
                    f"stale term {term} < {current_term}"
                )
                return {
                    "term": current_term,
                    "vote_granted": False
                }
            
            # Rule 2: Check if we should grant vote
            vote_granted = await self.should_vote(
                term, candidate_id, last_log_index, last_log_term
            )
            
            if vote_granted:
                logger.info(
                    f"Granting vote to {candidate_id} for term {term}"
                )
            else:
                logger.debug(
                    f"Denying vote to {candidate_id}: "
                    f"voted_for={voted_for}, log not up-to-date"
                )
            
            return {
                "term": max(term, current_term),
                "vote_granted": vote_granted
            }
        
        except Exception as e:
            logger.error(f"Error handling RequestVote: {e}")
            return {"error": str(e)}


class AppendEntriesHandler(RPCHandler):
    """
    Handler for AppendEntries RPC.
    
    Called when leader sends log entries or heartbeat.
    
    AppendEntries RPC:
      Args:
        term - leader's term
        leaderId - leader's node ID
        prevLogIndex - index of log entry immediately preceding new ones
        prevLogTerm - term of prevLogIndex entry
        entries - log entries to store (empty for heartbeat)
        leaderCommit - leader's commitIndex
      
      Results:
        term - currentTerm for leader to update itself
        success - true if follower contained entry matching prevLogIndex and prevLogTerm
    
    Receiver implementation rules:
      1. Reply false if term < currentTerm
      2. Reply false if log doesn't contain an entry at prevLogIndex
         whose term matches prevLogTerm
      3. If an existing entry conflicts with a new one (same index but different
         terms), delete the existing entry and all that follow it
      4. Append any new entries not already in the log
      5. If leaderCommit > commitIndex, set commitIndex =
         min(leaderCommit, index of last new entry)
    """
    
    def __init__(self, 
                 get_term: Callable,
                 get_log_entry: Callable,
                 append_entries: Callable,
                 update_commit_index: Callable):
        """
        Initialize the AppendEntries handler.
        
        Args:
            get_term: Async callable() -> int (current term)
            get_log_entry: Async callable(index) -> (term, data) or None
            append_entries: Async callable(prev_index, entries) -> bool
            update_commit_index: Async callable(new_commit_index) -> None
        """
        self.get_term = get_term
        self.get_log_entry = get_log_entry
        self.append_entries = append_entries
        self.update_commit_index = update_commit_index
    
    async def handle(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle AppendEntries RPC.
        
        Args:
            data: AppendEntries RPC data
            
        Returns:
            Response with term and success
        """
        term = data.get('term')
        leader_id = data.get('leader_id')
        prev_log_index = data.get('prev_log_index', 0)
        prev_log_term = data.get('prev_log_term', 0)
        entries = data.get('entries', [])
        leader_commit = data.get('leader_commit', 0)
        
        # Validate required fields
        if term is None or leader_id is None:
            logger.warning("AppendEntries missing required fields")
            return {"error": "Missing required fields"}
        
        try:
            # Get current term
            current_term = await self.get_term()
            
            # Rule 1: Reply false if term < currentTerm
            if term < current_term:
                logger.debug(
                    f"Rejecting AppendEntries from {leader_id}: "
                    f"stale term {term} < {current_term}"
                )
                return {
                    "term": current_term,
                    "success": False
                }
            
            # Rule 2: Check if log contains entry at prevLogIndex with prevLogTerm
            if prev_log_index > 0:
                prev_entry = await self.get_log_entry(prev_log_index)
                if prev_entry is None:
                    logger.debug(
                        f"Rejecting AppendEntries from {leader_id}: "
                        f"no log entry at index {prev_log_index}"
                    )
                    return {
                        "term": current_term,
                        "success": False
                    }
                
                prev_entry_term = prev_entry[0] if isinstance(prev_entry, tuple) else prev_entry
                if prev_entry_term != prev_log_term:
                    logger.debug(
                        f"Rejecting AppendEntries from {leader_id}: "
                        f"term mismatch at index {prev_log_index} "
                        f"({prev_entry_term} != {prev_log_term})"
                    )
                    return {
                        "term": current_term,
                        "success": False
                    }
            
            # Rules 3-4: Append entries
            try:
                await self.append_entries(prev_log_index, entries)
            except Exception as e:
                logger.error(f"Error appending entries: {e}")
                return {"error": str(e)}
            
            # Rule 5: Update commit index
            if leader_commit > 0:
                try:
                    await self.update_commit_index(leader_commit)
                except Exception as e:
                    logger.error(f"Error updating commit index: {e}")
                    # Don't fail - continue
            
            logger.debug(
                f"AppendEntries from {leader_id} accepted "
                f"({len(entries)} entries, commit={leader_commit})"
            )
            
            return {
                "term": current_term,
                "success": True
            }
        
        except Exception as e:
            logger.error(f"Error handling AppendEntries: {e}")
            return {"error": str(e)}


class HeartbeatHandler(AppendEntriesHandler):
    """
    Simplified handler for heartbeat messages (empty AppendEntries).
    
    Used primarily for resetting election timeout on followers.
    """
    
    async def handle(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle heartbeat (empty AppendEntries).
        
        Args:
            data: Heartbeat data
            
        Returns:
            Response acknowledging heartbeat
        """
        # Heartbeat is just AppendEntries with no entries
        # All the validation logic is the same
        return await super().handle(data)


def create_request_vote_handler(state_provider) -> RequestVoteHandler:
    """
    Factory function to create a RequestVoteHandler.
    
    Args:
        state_provider: Object providing state query methods
        
    Returns:
        Configured RequestVoteHandler
    """
    async def get_state():
        term = await state_provider.get_current_term()
        voted_for = await state_provider.get_voted_for()
        last_log_index = await state_provider.get_last_log_index()
        last_log_term = await state_provider.get_last_log_term()
        return term, voted_for, last_log_index, last_log_term
    
    async def should_vote(term, candidate_id, last_log_index, last_log_term):
        voted_for = await state_provider.get_voted_for()
        current_term = await state_provider.get_current_term()
        current_last_log_index = await state_provider.get_last_log_index()
        current_last_log_term = await state_provider.get_last_log_term()
        
        # Check if we've already voted in this term
        if voted_for is not None and voted_for != candidate_id:
            return False
        
        # Check log up-to-dateness
        # (candidate's log is at least as up-to-date as receiver's log)
        if last_log_term < current_last_log_term:
            return False
        if last_log_term == current_last_log_term and last_log_index < current_last_log_index:
            return False
        
        return True
    
    return RequestVoteHandler(get_state, should_vote)


def create_append_entries_handler(log_provider) -> AppendEntriesHandler:
    """
    Factory function to create an AppendEntriesHandler.
    
    Args:
        log_provider: Object providing log query and update methods
        
    Returns:
        Configured AppendEntriesHandler
    """
    async def get_term():
        return await log_provider.get_current_term()
    
    async def get_log_entry(index):
        return await log_provider.get_log_entry(index)
    
    async def append_entries(prev_index, entries):
        # Append entries handling will be implemented in Raft module
        # For now, stub that accepts entries
        return True
    
    async def update_commit_index(new_commit_index):
        # Commit index update will be implemented in Raft module
        # For now, stub that accepts update
        pass
    
    return AppendEntriesHandler(get_term, get_log_entry, append_entries, update_commit_index)
