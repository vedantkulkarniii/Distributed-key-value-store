"""
Tests for Raft replicated log implementation.
"""

import pytest
from src.raft.log import RaftLog, LogEntry
from datetime import datetime


class TestLogEntry:
    """Test LogEntry data structure."""
    
    def test_log_entry_creation(self):
        """Test creating log entry."""
        entry = LogEntry(term=1, index=1, command={"op": "set", "key": "x", "value": 10}, timestamp=datetime.now())
        
        assert entry.term == 1
        assert entry.index == 1
        assert entry.command["key"] == "x"
    
    def test_log_entry_equality(self):
        """Test log entry equality."""
        now = datetime.now()
        entry1 = LogEntry(term=1, index=1, command={"op": "set"}, timestamp=now)
        entry2 = LogEntry(term=1, index=1, command={"op": "set"}, timestamp=now)
        
        assert entry1 == entry2
    
    def test_log_entry_inequality_term(self):
        """Test inequality with different term."""
        now = datetime.now()
        entry1 = LogEntry(term=1, index=1, command={"op": "set"}, timestamp=now)
        entry2 = LogEntry(term=2, index=1, command={"op": "set"}, timestamp=now)
        
        assert entry1 != entry2
    
    def test_log_entry_to_dict(self):
        """Test converting entry to dict."""
        entry = LogEntry(term=1, index=5, command={"op": "get", "key": "x"}, timestamp=datetime.now())
        
        data = entry.to_dict()
        
        assert data["term"] == 1
        assert data["index"] == 5
        assert data["command"]["op"] == "get"


class TestRaftLog:
    """Test Raft log."""
    
    def test_log_initialization(self):
        """Test log initializes empty."""
        log = RaftLog("node-1")
        
        assert log.length() == 0
        assert log.get_last_index() == 0
        assert log.get_last_entry() is None
    
    def test_append_single_entry(self):
        """Test appending single entry."""
        log = RaftLog("node-1")
        
        entry = log.append(term=1, command={"op": "set", "key": "x", "value": 10})
        
        assert entry.term == 1
        assert entry.index == 1
        assert log.length() == 1
    
    def test_append_multiple_entries(self):
        """Test appending multiple entries."""
        log = RaftLog("node-1")
        
        log.append(term=1, command={"op": "set", "key": "x", "value": 1})
        log.append(term=1, command={"op": "set", "key": "y", "value": 2})
        log.append(term=2, command={"op": "set", "key": "z", "value": 3})
        
        assert log.length() == 3
        assert log.get_last_index() == 3
    
    def test_get_entry(self):
        """Test retrieving entry."""
        log = RaftLog("node-1")
        
        log.append(term=1, command={"op": "set", "key": "x", "value": 1})
        log.append(term=1, command={"op": "set", "key": "y", "value": 2})
        
        entry = log.get_entry(1)
        
        assert entry is not None
        assert entry.index == 1
        assert entry.command["key"] == "x"
    
    def test_get_entry_out_of_bounds(self):
        """Test getting non-existent entry."""
        log = RaftLog("node-1")
        log.append(term=1, command={"op": "set"})
        
        assert log.get_entry(0) is None
        assert log.get_entry(2) is None
        assert log.get_entry(100) is None
    
    def test_get_entries_range(self):
        """Test getting range of entries."""
        log = RaftLog("node-1")
        
        for i in range(5):
            log.append(term=1, command={"index": i})
        
        entries = log.get_entries(2, 4)
        
        assert len(entries) == 3
        assert entries[0].index == 2
        assert entries[2].index == 4
    
    def test_get_entries_to_end(self):
        """Test getting entries to end."""
        log = RaftLog("node-1")
        
        for i in range(5):
            log.append(term=1, command={"index": i})
        
        entries = log.get_entries(3)
        
        assert len(entries) == 3
        assert entries[0].index == 3
        assert entries[-1].index == 5
    
    def test_get_last_entry(self):
        """Test getting last entry."""
        log = RaftLog("node-1")
        
        log.append(term=1, command={"index": 1})
        log.append(term=2, command={"index": 2})
        
        last = log.get_last_entry()
        
        assert last.index == 2
        assert last.term == 2
    
    def test_delete_from_index(self):
        """Test deleting entries from index."""
        log = RaftLog("node-1")
        
        for i in range(5):
            log.append(term=1, command={"index": i})
        
        log.delete_from(3)
        
        assert log.length() == 2
        assert log.get_entry(3) is None
    
    def test_is_consistent_with(self):
        """Test consistency check."""
        log = RaftLog("node-1")
        
        log.append(term=1, command={"index": 1})
        log.append(term=1, command={"index": 2})
        log.append(term=2, command={"index": 3})
        
        assert log.is_consistent_with(0, 0)  # No previous entry
        assert log.is_consistent_with(2, 1)  # Consistent
        assert not log.is_consistent_with(2, 2)  # Term mismatch
        assert not log.is_consistent_with(10, 1)  # Index missing
    
    def test_contains_entry_at_term(self):
        """Test checking for specific entry."""
        log = RaftLog("node-1")
        
        log.append(term=1, command={"index": 1})
        log.append(term=1, command={"index": 2})
        log.append(term=2, command={"index": 3})
        
        assert log.contains_entry_at_term(1, 1)
        assert log.contains_entry_at_term(3, 2)
        assert not log.contains_entry_at_term(3, 1)
        assert not log.contains_entry_at_term(10, 1)
    
    def test_apply_entries_success(self):
        """Test applying entries from leader."""
        log = RaftLog("node-1")
        
        # Create new entries to apply
        entries = [
            LogEntry(term=2, index=1, command={"op": "set"}, timestamp=datetime.now()),
            LogEntry(term=2, index=2, command={"op": "set"}, timestamp=datetime.now()),
        ]
        
        result = log.apply_entries(entries, prev_index=0)
        
        assert result is True
        assert log.length() == 2
    
    def test_apply_entries_with_conflict(self):
        """Test applying entries with conflict."""
        log = RaftLog("node-1")
        
        # Add initial entries
        log.append(term=1, command={"index": 1})
        log.append(term=1, command={"index": 2})
        
        # Try to apply conflicting entries
        entries = [
            LogEntry(term=2, index=2, command={"op": "set"}, timestamp=datetime.now()),
        ]
        
        result = log.apply_entries(entries, prev_index=1)
        
        # Should detect conflict (existing term 1 != new term 2)
        assert result is False
    
    def test_get_conflicting_index(self):
        """Test finding conflicting index."""
        log = RaftLog("node-1")
        
        log.append(term=1, command={"index": 1})
        log.append(term=1, command={"index": 2})
        log.append(term=2, command={"index": 3})
        log.append(term=2, command={"index": 4})
        
        # Conflict at index 2 with term 1
        conflict_idx = log.get_conflicting_index(2, 2)
        
        # Should find term difference
        assert conflict_idx <= 2
    
    def test_log_length(self):
        """Test log length calculation."""
        log = RaftLog("node-1")
        
        assert log.length() == 0
        
        log.append(term=1, command={"index": 1})
        assert log.length() == 1
        
        for i in range(10):
            log.append(term=1, command={"index": i})
        
        assert log.length() == 11
    
    def test_get_last_index_and_term(self):
        """Test getting last index and term."""
        log = RaftLog("node-1")
        
        assert log.get_last_index() == 0
        assert log.get_last_term() == 0
        
        log.append(term=1, command={"index": 1})
        assert log.get_last_index() == 1
        assert log.get_last_term() == 1
        
        log.append(term=2, command={"index": 2})
        assert log.get_last_index() == 2
        assert log.get_last_term() == 2
    
    def test_log_validation(self):
        """Test log validation."""
        log = RaftLog("node-1")
        
        assert log.validate() is True
        
        for i in range(5):
            log.append(term=i // 2 + 1, command={"index": i})
        
        assert log.validate() is True
    
    def test_get_status(self):
        """Test getting log status."""
        log = RaftLog("node-1")
        
        for i in range(3):
            log.append(term=1, command={"index": i})
        
        status = log.get_status()
        
        assert status["node_id"] == "node-1"
        assert status["length"] == 3
        assert status["last_index"] == 3
        assert status["last_term"] == 1


class TestLogReplication:
    """Test log replication scenarios."""
    
    def test_leader_log_append(self):
        """Test leader appending entries."""
        leader_log = RaftLog("leader")
        
        # Leader receives client commands
        entry1 = leader_log.append(term=1, command={"op": "set", "key": "x", "value": 10})
        entry2 = leader_log.append(term=1, command={"op": "set", "key": "y", "value": 20})
        
        assert leader_log.length() == 2
        assert entry1.index < entry2.index
    
    def test_follower_log_replication(self):
        """Test follower replicating from leader."""
        follower_log = RaftLog("follower")
        
        # Leader entries to replicate
        leader_entries = [
            LogEntry(term=1, index=1, command={"op": "set", "key": "x", "value": 10}, timestamp=datetime.now()),
            LogEntry(term=1, index=2, command={"op": "set", "key": "y", "value": 20}, timestamp=datetime.now()),
            LogEntry(term=1, index=3, command={"op": "set", "key": "z", "value": 30}, timestamp=datetime.now()),
        ]
        
        # Apply entries
        result = follower_log.apply_entries(leader_entries, prev_index=0)
        
        assert result is True
        assert follower_log.length() == 3
    
    def test_log_consistency_check(self):
        """Test log consistency verification."""
        log1 = RaftLog("node-1")
        log2 = RaftLog("node-2")
        
        # Both start with same entries
        for i in range(3):
            entry = LogEntry(term=1, index=i+1, command={"index": i}, timestamp=datetime.now())
            log1.entries.append(entry)
            log2.entries.append(entry)
        
        # Should be consistent
        assert log1.is_consistent_with(2, 1) == log2.is_consistent_with(2, 1)


class TestLogEdgeCases:
    """Test edge cases."""
    
    def test_empty_entries_apply(self):
        """Test applying empty entries."""
        log = RaftLog("node-1")
        
        result = log.apply_entries([], prev_index=0)
        
        assert result is True
        assert log.length() == 0
    
    def test_large_log(self):
        """Test with large log."""
        log = RaftLog("node-1")
        
        for i in range(1000):
            log.append(term=i // 100 + 1, command={"index": i})
        
        assert log.length() == 1000
        assert log.get_last_index() == 1000
        assert log.validate() is True
    
    def test_delete_entire_log(self):
        """Test deleting entire log."""
        log = RaftLog("node-1")
        
        for i in range(10):
            log.append(term=1, command={"index": i})
        
        log.delete_from(1)
        
        assert log.length() == 0
    
    def test_multiple_terms(self):
        """Test log with multiple terms."""
        log = RaftLog("node-1")
        
        for term in range(1, 6):
            for i in range(3):
                log.append(term=term, command={"term": term, "index": i})
        
        assert log.length() == 15
        assert log.get_last_term() == 5
        assert log.validate() is True
