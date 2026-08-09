"""
Raft replicated log implementation.

Maintains a durable log of state machine commands replicated across cluster.
Supports:
- Append-only log entries
- Term-based entry tracking
- Log consistency verification
- Snapshot integration (Phase 5)
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class LogEntry:
    """Single entry in replicated log."""
    
    term: int           # Term when entry was received
    index: int          # Position in log (1-indexed)
    command: Any        # State machine command (dict/JSON)
    timestamp: datetime # When entry was created
    
    def __eq__(self, other):
        """Check if entries are identical."""
        if not isinstance(other, LogEntry):
            return False
        return (self.term == other.term and 
                self.index == other.index and 
                self.command == other.command)
    
    def __hash__(self):
        """Hash for use in sets/dicts."""
        return hash((self.term, self.index))
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "term": self.term,
            "index": self.index,
            "command": self.command,
            "timestamp": self.timestamp.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'LogEntry':
        """Create from dictionary."""
        return cls(
            term=data["term"],
            index=data["index"],
            command=data["command"],
            timestamp=datetime.fromisoformat(data["timestamp"])
        )


class RaftLog:
    """Replicated log for Raft state machine."""
    
    def __init__(self, node_id: str):
        """
        Initialize log.
        
        Args:
            node_id: Node identifier for logging
        """
        self.node_id = node_id
        self.entries: List[LogEntry] = []  # 1-indexed (entries[0] unused)
        self.entries.append(None)  # Placeholder for index 0
        
        # Snapshot state (Phase 5)
        self.last_included_index = 0
        self.last_included_term = 0
        
        logger.info(f"Log initialized for {node_id}")
    
    def append(self, term: int, command: Any) -> LogEntry:
        """
        Append entry to log.
        
        Args:
            term: Current term
            command: State machine command
            
        Returns:
            Created log entry
        """
        index = len(self.entries)
        entry = LogEntry(
            term=term,
            index=index,
            command=command,
            timestamp=datetime.now()
        )
        
        self.entries.append(entry)
        logger.debug(f"Node {self.node_id}: Appended entry at index {index}")
        
        return entry
    
    def get_entry(self, index: int) -> Optional[LogEntry]:
        """
        Get entry at index.
        
        Args:
            index: Log index (1-indexed)
            
        Returns:
            Log entry or None if not exists
        """
        if index < 1 or index >= len(self.entries):
            return None
        return self.entries[index]
    
    def get_entries(self, start_index: int, end_index: Optional[int] = None) -> List[LogEntry]:
        """
        Get range of entries.
        
        Args:
            start_index: Starting index (1-indexed)
            end_index: Ending index (1-indexed, inclusive). None = to end
            
        Returns:
            List of entries
        """
        if end_index is None:
            end_index = len(self.entries) - 1
        
        if start_index < 1 or start_index > end_index:
            return []
        
        return self.entries[start_index:end_index + 1]
    
    def get_last_entry(self) -> Optional[LogEntry]:
        """Get last entry in log."""
        if len(self.entries) <= 1:
            return None
        return self.entries[-1]
    
    def get_last_index(self) -> int:
        """Get index of last entry."""
        return len(self.entries) - 1
    
    def get_last_term(self) -> int:
        """Get term of last entry."""
        last_entry = self.get_last_entry()
        if last_entry:
            return last_entry.term
        return self.last_included_term
    
    def length(self) -> int:
        """Get log length (number of entries)."""
        return len(self.entries) - 1  # Exclude placeholder
    
    def delete_from(self, index: int) -> None:
        """
        Delete all entries from index onwards.
        
        Used when follower receives conflicting entries.
        
        Args:
            index: Starting index to delete (1-indexed)
        """
        if index < 1 or index >= len(self.entries):
            return
        
        deleted_count = len(self.entries) - index
        self.entries = self.entries[:index]
        
        logger.debug(f"Node {self.node_id}: Deleted {deleted_count} entries from index {index}")
    
    def is_consistent_with(self, prev_index: int, prev_term: int) -> bool:
        """
        Check if log is consistent with previous entry.
        
        Used by followers to validate AppendEntries.
        
        Args:
            prev_index: Previous log index
            prev_term: Previous log term
            
        Returns:
            True if consistent, False if conflict
        """
        if prev_index == 0:
            # No previous entry, always consistent
            return True
        
        prev_entry = self.get_entry(prev_index)
        if prev_entry is None:
            return False
        
        return prev_entry.term == prev_term
    
    def contains_entry_at_term(self, index: int, term: int) -> bool:
        """
        Check if log contains specific entry at term.
        
        Args:
            index: Log index
            term: Expected term
            
        Returns:
            True if entry exists with matching term
        """
        entry = self.get_entry(index)
        if entry is None:
            return False
        return entry.term == term
    
    def get_conflicting_index(self, index: int, term: int) -> int:
        """
        Find first conflicting entry.
        
        Used by leader for OptimisticLog optimization.
        
        Args:
            index: Index where conflict detected
            term: Term of entry at that index
            
        Returns:
            Index of first conflicting entry, or index if no conflict
        """
        # Walk backwards to find first entry with different term
        current = min(index, self.get_last_index())
        
        while current >= 1:
            entry = self.get_entry(current)
            if entry is None:
                return current + 1
            if entry.term != term:
                return current
            current -= 1
        
        return 1
    
    def apply_entries(self, entries: List[LogEntry], prev_index: int) -> bool:
        """
        Apply entries from leader (AppendEntries).
        
        Args:
            entries: Entries to apply
            prev_index: Index before new entries
            
        Returns:
            True if applied, False if conflict
        """
        if not entries:
            return True
        
        # Check consistency
        first_new_index = prev_index + 1
        
        if first_new_index < len(self.entries):
            # Potential conflict
            existing = self.entries[first_new_index]
            if existing and existing.term != entries[0].term:
                # Conflict detected
                logger.debug(
                    f"Node {self.node_id}: Conflict at index {first_new_index} "
                    f"(existing term {existing.term}, new term {entries[0].term})"
                )
                return False
        
        # Delete conflicting entries and append new ones
        if first_new_index < len(self.entries):
            self.delete_from(first_new_index)
        
        # Append entries
        for i, entry in enumerate(entries):
            expected_index = first_new_index + i
            self.entries.append(entry)
        
        logger.debug(
            f"Node {self.node_id}: Applied {len(entries)} entries "
            f"(indices {first_new_index} to {first_new_index + len(entries) - 1})"
        )
        
        return True
    
    def get_status(self) -> dict:
        """Get log status."""
        last_entry = self.get_last_entry()
        
        return {
            "node_id": self.node_id,
            "length": self.length(),
            "last_index": self.get_last_index(),
            "last_term": self.get_last_term(),
            "entries": len(self.entries) - 1,
            "last_included_index": self.last_included_index,
            "last_included_term": self.last_included_term
        }
    
    def validate(self) -> bool:
        """
        Validate log invariants.
        
        Returns:
            True if all invariants hold
        """
        # Check indices are sequential
        for i in range(1, len(self.entries)):
            entry = self.entries[i]
            if entry.index != i:
                logger.warning(
                    f"Node {self.node_id}: Index mismatch at position {i} "
                    f"(entry index {entry.index})"
                )
                return False
        
        # Check terms are non-decreasing (mostly)
        for i in range(2, len(self.entries)):
            prev_term = self.entries[i - 1].term
            curr_term = self.entries[i].term
            if curr_term < prev_term:
                logger.warning(
                    f"Node {self.node_id}: Term regression at index {i} "
                    f"({curr_term} < {prev_term})"
                )
                return False
        
        return True
    
    def __str__(self) -> str:
        """String representation."""
        return (
            f"RaftLog({self.node_id}, length={self.length()}, "
            f"last_index={self.get_last_index()}, last_term={self.get_last_term()})"
        )
