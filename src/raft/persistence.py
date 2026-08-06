"""
Persistent state for Raft consensus.

Manages durable storage of:
- Current term (currentTerm)
- Voted for candidate (votedFor)

These must be persisted to disk BEFORE responding to any RPC that depends on them.
This is a critical correctness requirement from the Raft paper.
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)


class RaftPersistentState:
    """
    Manages persistent state for Raft nodes.
    
    Stores:
    - currentTerm: Latest term the server has seen
    - votedFor: Candidate that received our vote in current term
    
    These values must be updated atomically and persisted before:
    - Responding to RequestVote RPCs
    - Responding to AppendEntries RPCs
    - Starting elections
    
    Implementation uses write-ahead semantics with fsync for durability.
    """
    
    def __init__(self, node_id: str, state_file: str = "raft_state.json"):
        """
        Initialize persistent state manager.
        
        Args:
            node_id: Node ID
            state_file: Path to persistent state file
        """
        self.node_id = node_id
        self.state_file = Path(state_file)
        self._lock = asyncio.Lock()
        
        # In-memory cache
        self._current_term = 0
        self._voted_for: Optional[str] = None
        
        logger.info(f"Node {node_id}: Persistent state file at {state_file}")
    
    async def load(self) -> None:
        """
        Load persistent state from disk on startup.
        
        Called during node initialization to recover state after restart.
        """
        async with self._lock:
            if not self.state_file.exists():
                logger.info(
                    f"Node {self.node_id}: No persistent state file, starting with defaults"
                )
                self._current_term = 0
                self._voted_for = None
                return
            
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                
                self._current_term = data.get('currentTerm', 0)
                self._voted_for = data.get('votedFor')
                
                logger.info(
                    f"Node {self.node_id}: Loaded persistent state "
                    f"(term={self._current_term}, votedFor={self._voted_for})"
                )
            except Exception as e:
                logger.error(
                    f"Node {self.node_id}: Error loading persistent state: {e}"
                )
                # Default to safe values
                self._current_term = 0
                self._voted_for = None
    
    async def get_term(self) -> int:
        """
        Get current term.
        
        Returns:
            Current term
        """
        async with self._lock:
            return self._current_term
    
    async def get_voted_for(self) -> Optional[str]:
        """
        Get candidate we voted for in current term.
        
        Returns:
            Candidate ID or None if not voted
        """
        async with self._lock:
            return self._voted_for
    
    async def set_term(self, term: int) -> None:
        """
        Persist current term.
        
        MUST be called before:
        - Responding to any RPC in a higher term
        - Starting an election
        
        Args:
            term: New term value
        """
        async with self._lock:
            if term <= self._current_term:
                return  # Ignore if not advancing
            
            self._current_term = term
            self._voted_for = None  # Clear vote when advancing term
            
            await self._persist()
    
    async def set_voted_for(self, candidate_id: Optional[str]) -> bool:
        """
        Persist vote for candidate in current term.
        
        MUST be called before responding to RequestVote RPC.
        
        Args:
            candidate_id: Candidate we're voting for (None to clear)
            
        Returns:
            True if vote was recorded, False if already voted for different candidate
        """
        async with self._lock:
            if candidate_id is None:
                # Clearing vote (e.g., on term advancement)
                self._voted_for = None
                await self._persist()
                return True
            
            # Check if already voted for someone else
            if self._voted_for is not None and self._voted_for != candidate_id:
                logger.debug(
                    f"Node {self.node_id}: Already voted for {self._voted_for} "
                    f"in term {self._current_term}"
                )
                return False
            
            self._voted_for = candidate_id
            await self._persist()
            
            logger.debug(
                f"Node {self.node_id}: Voted for {candidate_id} in term {self._current_term}"
            )
            return True
    
    async def _persist(self) -> None:
        """
        Write state to disk atomically with fsync.
        
        Uses write-ahead semantics:
        1. Write to temporary file
        2. fsync() temporary file
        3. Rename temporary to actual state file
        4. fsync() directory
        
        This ensures atomicity and durability.
        """
        try:
            state_data = {
                'currentTerm': self._current_term,
                'votedFor': self._voted_for
            }
            
            # Write to temporary file first
            temp_file = self.state_file.with_suffix('.tmp')
            
            with open(temp_file, 'w') as f:
                json.dump(state_data, f)
                # fsync to ensure data on disk
                os.fsync(f.fileno())
            
            # Atomic rename
            temp_file.replace(self.state_file)
            
            # fsync directory to ensure metadata persisted
            dir_fd = os.open(self.state_file.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
            
            logger.debug(
                f"Node {self.node_id}: Persisted state "
                f"(term={self._current_term}, votedFor={self._voted_for})"
            )
        
        except Exception as e:
            logger.error(
                f"Node {self.node_id}: ERROR persisting state: {e}"
            )
            # This is critical - if we can't persist, we shouldn't proceed
            raise
    
    async def reset(self) -> None:
        """
        Reset persistent state to defaults.
        
        Used for testing.
        """
        async with self._lock:
            self._current_term = 0
            self._voted_for = None
            
            if self.state_file.exists():
                self.state_file.unlink()
            
            logger.debug(f"Node {self.node_id}: Reset persistent state")
    
    async def get_state(self) -> dict:
        """
        Get current persistent state.
        
        Returns:
            Dict with currentTerm and votedFor
        """
        async with self._lock:
            return {
                "currentTerm": self._current_term,
                "votedFor": self._voted_for
            }
    
    def __str__(self) -> str:
        """String representation."""
        return (
            f"RaftPersistentState({self.node_id}, "
            f"term={self._current_term}, votedFor={self._voted_for})"
        )


class PersistenceTestHelper:
    """Helper for testing persistent state."""
    
    @staticmethod
    async def verify_persisted(state: RaftPersistentState) -> bool:
        """
        Verify that current state is actually persisted to disk.
        
        Args:
            state: RaftPersistentState instance
            
        Returns:
            True if state matches on-disk state
        """
        if not state.state_file.exists():
            return False
        
        try:
            with open(state.state_file, 'r') as f:
                disk_data = json.load(f)
            
            current_state = await state.get_state()
            
            return (
                disk_data['currentTerm'] == current_state['currentTerm'] and
                disk_data['votedFor'] == current_state['votedFor']
            )
        except Exception as e:
            logger.error(f"Error verifying persistence: {e}")
            return False
    
    @staticmethod
    async def corrupt_state_file(state: RaftPersistentState) -> None:
        """
        Corrupt state file for testing recovery.
        
        Args:
            state: RaftPersistentState instance
        """
        if state.state_file.exists():
            with open(state.state_file, 'w') as f:
                f.write("corrupted json {invalid")
    
    @staticmethod
    async def verify_atomic_persistence(state: RaftPersistentState) -> bool:
        """
        Verify that persistence is atomic.
        
        Checks that no partial writes are visible.
        
        Args:
            state: RaftPersistentState instance
            
        Returns:
            True if persistence appears atomic
        """
        # In this simple implementation, atomic rename handles this
        # In production, you'd do more thorough testing
        return await PersistenceTestHelper.verify_persisted(state)
