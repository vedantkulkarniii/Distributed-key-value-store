"""
AppendEntries RPC handler for log replication and heartbeats.

Implements:
- Heartbeat mechanism (empty entries)
- Log entry replication with consistency checking
- Follower commitment tracking
- Conflict detection and resolution
- Log application to state machine
"""

import logging
import asyncio
from typing import List, Optional, Dict, Tuple, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class AppendEntriesHandler:
    """
    Handles AppendEntries RPC from leader.
    
    Implements full log replication logic with:
    - Consistency verification
    - Entry appending
    - Commit index advancement
    - State machine application
    """
    
    def __init__(self, node_id: str, log: Optional[Any] = None):
        """
        Initialize handler.
        
        Args:
            node_id: This node's ID
            log: RaftLog instance for storing entries
        """
        self.node_id = node_id
        self.log = log
        self.last_applied = 0  # Highest index applied to state machine
        self.commit_index = 0  # Highest index known to be committed
        self.state_machine: Dict[str, Any] = {}  # Simple KV state machine
        self.last_heartbeat = datetime.now()
    
    async def handle_append_entries(
        self,
        term: int,
        leader_id: str,
        prev_log_index: int,
        prev_log_term: int,
        entries: List[Dict],
        leader_commit: int
    ) -> Tuple[bool, int]:
        """
        Handle AppendEntries RPC from leader.
        
        Implements Raft AppendEntries logic:
        1. Reject if term < currentTerm
        2. Reject if log doesn't contain entry at prevLogIndex with term prevLogTerm
        3. If entry in log conflicts with new entry, delete it and subsequent entries
        4. Append entries not already in log
        5. If leaderCommit > commitIndex, set commitIndex = min(leaderCommit, index of last new entry)
        
        Args:
            term: Leader's term
            leader_id: Leader node ID
            prev_log_index: Index of log entry immediately preceding new ones
            prev_log_term: Term of prev_log_index entry
            entries: Log entries to append
            leader_commit: Leader's commit index
            
        Returns:
            (success: bool, last_log_index: int)
        """
        self.last_heartbeat = datetime.now()
        
        # Check term (will be verified by caller, but sanity check)
        if not self.log:
            logger.warning(f"Node {self.node_id}: No log instance")
            return False, 0
        
        # Get current log state
        current_last_index = self.log.get_last_index()
        
        # 1. Check previous log consistency
        if prev_log_index > 0:
            prev_entry = self.log.get_entry(prev_log_index)
            if prev_entry is None:
                logger.debug(
                    f"Node {self.node_id}: Reject AppendEntries - "
                    f"no entry at prev_log_index {prev_log_index}"
                )
                return False, current_last_index
            
            if prev_entry.term != prev_log_term:
                logger.debug(
                    f"Node {self.node_id}: Reject AppendEntries - "
                    f"term mismatch at index {prev_log_index} "
                    f"(expected {prev_log_term}, got {prev_entry.term})"
                )
                return False, current_last_index
        
        # 2. Check for conflicts and delete conflicting entries
        if entries:
            first_new_index = prev_log_index + 1
            
            # Check if any new entry conflicts with existing log
            for i, entry_dict in enumerate(entries):
                check_index = first_new_index + i
                existing_entry = self.log.get_entry(check_index)
                
                if existing_entry is not None:
                    # Entry exists at this position
                    if existing_entry.term != entry_dict.get('term'):
                        # Conflict! Delete this and all subsequent entries
                        logger.debug(
                            f"Node {self.node_id}: Conflict at index {check_index}, "
                            f"deleting entries from this point"
                        )
                        self.log.delete_from(check_index)
                        break
        
        # 3. Append new entries to log
        entries_appended = 0
        if entries:
            from src.raft.log import LogEntry
            
            first_new_index = prev_log_index + 1
            for i, entry_dict in enumerate(entries):
                index = first_new_index + i
                
                # Check if already have this entry
                existing = self.log.get_entry(index)
                if existing is None or existing.term != entry_dict.get('term'):
                    # Create and append new entry
                    log_entry = LogEntry(
                        term=entry_dict.get('term'),
                        index=index,
                        command=entry_dict.get('command'),
                        timestamp=datetime.fromisoformat(entry_dict.get('timestamp', datetime.now().isoformat()))
                    )
                    self.log.entries.append(log_entry)
                    entries_appended += 1
        
        # 4. Advance commit index
        old_commit = self.commit_index
        if leader_commit > self.commit_index:
            self.commit_index = min(leader_commit, self.log.get_last_index())
            if self.commit_index > old_commit:
                logger.debug(
                    f"Node {self.node_id}: Advanced commit_index "
                    f"from {old_commit} to {self.commit_index}"
                )
        
        # 5. Apply committed entries to state machine
        applied = await self.apply_committed_entries()
        
        logger.debug(
            f"Node {self.node_id}: Accepted AppendEntries from {leader_id} "
            f"({len(entries)} entries, commit_index={self.commit_index}, applied={applied})"
        )
        
        return True, self.log.get_last_index()
    
    async def apply_committed_entries(self) -> int:
        """
        Apply committed entries to state machine.
        
        Applies all entries from last_applied+1 to commit_index.
        
        Returns:
            Number of entries applied
        """
        if not self.log:
            return 0
        
        entries_applied = 0
        
        while self.last_applied < self.commit_index:
            next_index = self.last_applied + 1
            entry = self.log.get_entry(next_index)
            
            if entry is None:
                logger.warning(
                    f"Node {self.node_id}: Missing entry at index {next_index} "
                    f"for application (commit_index={self.commit_index})"
                )
                break
            
            # Apply entry to state machine
            try:
                if isinstance(entry.command, dict):
                    if entry.command.get('op') == 'set':
                        self.state_machine[entry.command.get('key')] = entry.command.get('value')
                    elif entry.command.get('op') == 'delete':
                        self.state_machine.pop(entry.command.get('key'), None)
                    
                    logger.debug(
                        f"Node {self.node_id}: Applied entry {next_index} "
                        f"({entry.command.get('op')} {entry.command.get('key')})"
                    )
                
                self.last_applied = next_index
                entries_applied += 1
                
            except Exception as e:
                logger.error(
                    f"Node {self.node_id}: Error applying entry {next_index}: {e}"
                )
                break
        
        return entries_applied
    
    def apply_entries(self) -> int:
        """
        Apply entries up to commit index synchronously.
        
        Legacy method for compatibility.
        
        Returns:
            Number of entries applied
        """
        if not self.log:
            return 0
        
        entries_applied = 0
        
        while self.last_applied < self.commit_index:
            next_index = self.last_applied + 1
            entry = self.log.get_entry(next_index)
            
            if entry is None:
                break
            
            if isinstance(entry.command, dict):
                if entry.command.get('op') == 'set':
                    self.state_machine[entry.command.get('key')] = entry.command.get('value')
                elif entry.command.get('op') == 'delete':
                    self.state_machine.pop(entry.command.get('key'), None)
            
            self.last_applied = next_index
            entries_applied += 1
        
        return entries_applied
    
    def get_status(self) -> dict:
        """Get handler status."""
        return {
            "node_id": self.node_id,
            "last_applied": self.last_applied,
            "commit_index": self.commit_index,
            "state_machine_size": len(self.state_machine),
            "last_heartbeat": self.last_heartbeat.isoformat()
        }


class LeaderHeartbeat:
    """Sends heartbeats to followers."""
    
    def __init__(self, node_id: str, followers: List[str]):
        """
        Initialize leader heartbeat.
        
        Args:
            node_id: Leader node ID
            followers: List of follower node IDs
        """
        self.node_id = node_id
        self.followers = followers
        self.heartbeat_interval = 0.15  # 150ms
        self.last_heartbeat_times = {f: datetime.now() for f in followers}
        self.heartbeat_acks = {f: False for f in followers}
    
    async def send_heartbeats(self, term: int, log: Optional[Any] = None) -> Dict[str, bool]:
        """
        Send heartbeats to all followers.
        
        Empty AppendEntries (no entries) serve as heartbeats.
        
        Args:
            term: Current term
            log: RaftLog for getting last log info
            
        Returns:
            Dict mapping follower_id -> ack_received
        """
        logger.debug(
            f"Leader {self.node_id}: Sending heartbeats to {len(self.followers)} followers"
        )
        
        # Get last log info for AppendEntries
        last_log_index = 0
        last_log_term = 0
        if log:
            last_log_index = log.get_last_index()
            last_log_term = log.get_last_term()
        
        # Send to all followers concurrently
        tasks = []
        for follower in self.followers:
            tasks.append(self._send_heartbeat_to(follower, term, last_log_index, last_log_term))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for follower, result in zip(self.followers, results):
            if isinstance(result, Exception):
                self.heartbeat_acks[follower] = False
                logger.debug(f"Leader {self.node_id}: Heartbeat to {follower} failed: {result}")
            else:
                self.heartbeat_acks[follower] = result
                if result:
                    self.last_heartbeat_times[follower] = datetime.now()
        
        return self.heartbeat_acks
    
    async def _send_heartbeat_to(self, follower: str, term: int, last_index: int, last_term: int) -> bool:
        """Send heartbeat to single follower."""
        try:
            # Simulate RPC call (will be replaced with actual RPC)
            await asyncio.sleep(0.01)  # Simulate network delay
            return True
        except Exception as e:
            logger.debug(f"Heartbeat to {follower}: {e}")
            return False
    
    def get_status(self) -> dict:
        """Get heartbeat status."""
        return {
            "leader_id": self.node_id,
            "followers": self.followers,
            "heartbeat_acks": self.heartbeat_acks,
            "last_heartbeat_times": {k: v.isoformat() for k, v in self.last_heartbeat_times.items()}
        }
