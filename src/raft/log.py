"""
Raft log and log entry management.

Minimal implementation for Phase 3 to support election.
Full implementation comes in Phase 4.
"""

from typing import List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class LogEntry:
    """A single log entry."""
    term: int
    index: int
    data: Optional[bytes] = None


class RaftLog:
    """
    Simple in-memory Raft log for Phase 3.
    
    Phase 4 will add persistent storage.
    """
    
    def __init__(self):
        """Initialize empty log."""
        self.entries: List[LogEntry] = []
    
    def append(self, term: int, data: Optional[bytes] = None) -> int:
        """
        Append entry to log.
        
        Returns:
            Index of appended entry
        """
        index = len(self.entries)
        self.entries.append(LogEntry(term=term, index=index, data=data))
        return index
    
    def get_last_index(self) -> int:
        """Get index of last log entry (or 0 if empty)."""
        return len(self.entries) - 1 if self.entries else 0
    
    def get_last_term(self) -> int:
        """Get term of last log entry (or 0 if empty)."""
        return self.entries[-1].term if self.entries else 0
    
    def get_entry(self, index: int) -> Optional[LogEntry]:
        """Get log entry by index."""
        if 0 <= index < len(self.entries):
            return self.entries[index]
        return None


class LogStateProvider:
    """Provides log state for election logic."""
    
    def __init__(self):
        """Initialize."""
        self.log = RaftLog()
    
    async def get_last_log_index(self) -> int:
        """Get last log index."""
        return self.log.get_last_index()
    
    async def get_last_log_term(self) -> int:
        """Get last log term."""
        return self.log.get_last_term()
    
    async def get_log_entry(self, index: int) -> Optional[Tuple[int, bytes]]:
        """Get log entry."""
        entry = self.log.get_entry(index)
        if entry:
            return (entry.term, entry.data)
        return None
