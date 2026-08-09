"""
Tests for AppendEntries RPC handler implementation.

Tests cover:
- AppendEntries RPC handling
- Log consistency checking
- Entry appending and conflicts
- Commit index advancement
- State machine application
- Heartbeat handling
"""

import pytest
import asyncio
from datetime import datetime
from src.raft.append_entries import AppendEntriesHandler, LeaderHeartbeat
from src.raft.log import RaftLog, LogEntry


class TestAppendEntriesHandler:
    """Test AppendEntries RPC handler."""
    
    def setup_method(self):
        """Setup for each test."""
        self.handler = AppendEntriesHandler("node-1")
        self.log = RaftLog("node-1")
        self.handler.log = self.log
    
    @pytest.mark.asyncio
    async def test_handle_append_entries_heartbeat(self):
        """Test heartbeat (empty entries)."""
        success, last_index = await self.handler.handle_append_entries(
            term=1,
            leader_id="leader",
            prev_log_index=0,
            prev_log_term=0,
            entries=[],
            leader_commit=0
        )
        
        assert success is True
        assert last_index == 0
        assert self.handler.last_heartbeat is not None
    
    @pytest.mark.asyncio
    async def test_handle_append_entries_single_entry(self):
        """Test appending single entry."""
        entry_dict = {
            'term': 1,
            'command': {'op': 'set', 'key': 'key1', 'value': 'value1'},
            'timestamp': datetime.now().isoformat()
        }
        
        success, last_index = await self.handler.handle_append_entries(
            term=1,
            leader_id="leader",
            prev_log_index=0,
            prev_log_term=0,
            entries=[entry_dict],
            leader_commit=0
        )
        
        assert success is True
        assert last_index == 1
        assert self.log.length() == 1
    
    @pytest.mark.asyncio
    async def test_handle_append_entries_multiple_entries(self):
        """Test appending multiple entries."""
        entries = [
            {
                'term': 1,
                'command': {'op': 'set', 'key': f'key{i}', 'value': f'value{i}'},
                'timestamp': datetime.now().isoformat()
            }
            for i in range(5)
        ]
        
        success, last_index = await self.handler.handle_append_entries(
            term=1,
            leader_id="leader",
            prev_log_index=0,
            prev_log_term=0,
            entries=entries,
            leader_commit=0
        )
        
        assert success is True
        assert last_index == 5
        assert self.log.length() == 5
    
    @pytest.mark.asyncio
    async def test_handle_append_entries_consistency_check_fail(self):
        """Test rejection on consistency check failure."""
        success, last_index = await self.handler.handle_append_entries(
            term=1,
            leader_id="leader",
            prev_log_index=99,  # Non-existent
            prev_log_term=1,
            entries=[],
            leader_commit=0
        )
        
        assert success is False
        assert last_index == 0
    
    @pytest.mark.asyncio
    async def test_handle_append_entries_term_mismatch(self):
        """Test rejection on term mismatch."""
        # First, append an entry with term 1
        entry_dict = {
            'term': 1,
            'command': {'op': 'set', 'key': 'key1', 'value': 'value1'},
            'timestamp': datetime.now().isoformat()
        }
        
        await self.handler.handle_append_entries(
            term=1,
            leader_id="leader",
            prev_log_index=0,
            prev_log_term=0,
            entries=[entry_dict],
            leader_commit=0
        )
        
        # Try to append with mismatched term
        entry_dict2 = {
            'term': 2,
            'command': {'op': 'set', 'key': 'key2', 'value': 'value2'},
            'timestamp': datetime.now().isoformat()
        }
        
        success, last_index = await self.handler.handle_append_entries(
            term=2,
            leader_id="leader",
            prev_log_index=1,
            prev_log_term=2,  # Wrong term
            entries=[entry_dict2],
            leader_commit=0
        )
        
        assert success is False
    
    @pytest.mark.asyncio
    async def test_handle_append_entries_conflict_detection(self):
        """Test conflict detection and resolution."""
        # Append initial entries
        entries1 = [
            {
                'term': 1,
                'command': {'op': 'set', 'key': f'key{i}', 'value': f'value{i}'},
                'timestamp': datetime.now().isoformat()
            }
            for i in range(3)
        ]
        
        await self.handler.handle_append_entries(
            term=1,
            leader_id="leader",
            prev_log_index=0,
            prev_log_term=0,
            entries=entries1,
            leader_commit=0
        )
        
        # Send conflicting entries at index 2 (term 2 vs term 1)
        entries2 = [
            {
                'term': 2,
                'command': {'op': 'set', 'key': 'new_key', 'value': 'new_value'},
                'timestamp': datetime.now().isoformat()
            }
        ]
        
        success, last_index = await self.handler.handle_append_entries(
            term=2,
            leader_id="leader",
            prev_log_index=1,
            prev_log_term=1,
            entries=entries2,
            leader_commit=0
        )
        
        assert success is True
        # Conflict resolved, log truncated at index 2
        assert self.log.length() == 2
    
    @pytest.mark.asyncio
    async def test_commit_index_advancement(self):
        """Test commit index advancement."""
        # Append entries
        entries = [
            {
                'term': 1,
                'command': {'op': 'set', 'key': f'key{i}', 'value': f'value{i}'},
                'timestamp': datetime.now().isoformat()
            }
            for i in range(5)
        ]
        
        success, _ = await self.handler.handle_append_entries(
            term=1,
            leader_id="leader",
            prev_log_index=0,
            prev_log_term=0,
            entries=entries,
            leader_commit=0
        )
        
        assert self.handler.commit_index == 0
        
        # Advance commit index
        success, _ = await self.handler.handle_append_entries(
            term=1,
            leader_id="leader",
            prev_log_index=5,
            prev_log_term=1,
            entries=[],
            leader_commit=3
        )
        
        assert self.handler.commit_index == 3
    
    @pytest.mark.asyncio
    async def test_apply_committed_entries(self):
        """Test applying committed entries to state machine."""
        # Append entries
        entries = [
            {
                'term': 1,
                'command': {'op': 'set', 'key': 'key1', 'value': 'value1'},
                'timestamp': datetime.now().isoformat()
            },
            {
                'term': 1,
                'command': {'op': 'set', 'key': 'key2', 'value': 'value2'},
                'timestamp': datetime.now().isoformat()
            }
        ]
        
        # First append the entries to the log
        success, _ = await self.handler.handle_append_entries(
            term=1,
            leader_id='leader',
            prev_log_index=0,
            prev_log_term=0,
            entries=entries,
            leader_commit=0
        )
        
        assert success is True
        
        # Now set commit index to 2 and apply
        self.handler.commit_index = 2
        applied = await self.handler.apply_committed_entries()
        
        assert applied == 2
        assert self.handler.last_applied == 2
        assert self.handler.state_machine['key1'] == 'value1'
        assert self.handler.state_machine['key2'] == 'value2'
    
    @pytest.mark.asyncio
    async def test_apply_entries_delete_operation(self):
        """Test applying delete operations."""
        # Set initial state
        self.handler.state_machine['key1'] = 'value1'
        
        # Create delete entry
        self.log.append(1, {'op': 'delete', 'key': 'key1'})
        
        self.handler.commit_index = 1
        applied = await self.handler.apply_committed_entries()
        
        assert applied == 1
        assert 'key1' not in self.handler.state_machine
    
    @pytest.mark.asyncio
    async def test_apply_entries_skip_on_missing_entry(self):
        """Test skipping application on missing entry."""
        # Set commit index higher than log
        self.handler.commit_index = 10
        
        # This should not crash
        applied = await self.handler.apply_committed_entries()
        
        assert applied == 0
        assert self.handler.last_applied == 0
    
    def test_get_status(self):
        """Test getting handler status."""
        status = self.handler.get_status()
        
        assert status['node_id'] == 'node-1'
        assert status['last_applied'] == 0
        assert status['commit_index'] == 0
        assert status['state_machine_size'] == 0
        assert 'last_heartbeat' in status


class TestLeaderHeartbeat:
    """Test leader heartbeat mechanism."""
    
    def setup_method(self):
        """Setup for each test."""
        self.followers = ['node-2', 'node-3', 'node-4']
        self.heartbeat = LeaderHeartbeat('leader', self.followers)
    
    @pytest.mark.asyncio
    async def test_send_heartbeats_to_followers(self):
        """Test sending heartbeats to all followers."""
        acks = await self.heartbeat.send_heartbeats(term=1)
        
        assert isinstance(acks, dict)
        assert len(acks) == len(self.followers)
        assert all(follower in acks for follower in self.followers)
    
    @pytest.mark.asyncio
    async def test_send_heartbeats_with_log(self):
        """Test sending heartbeats with log info."""
        log = RaftLog('leader')
        
        # Append some entries
        for i in range(3):
            log.append(1, {'key': f'key{i}'})
        
        acks = await self.heartbeat.send_heartbeats(term=1, log=log)
        
        assert len(acks) == len(self.followers)
    
    @pytest.mark.asyncio
    async def test_heartbeat_interval(self):
        """Test heartbeat interval configuration."""
        assert self.heartbeat.heartbeat_interval == 0.15
    
    def test_heartbeat_status(self):
        """Test getting heartbeat status."""
        status = self.heartbeat.get_status()
        
        assert status['leader_id'] == 'leader'
        assert status['followers'] == self.followers
        assert 'heartbeat_acks' in status
        assert 'last_heartbeat_times' in status
    
    def test_heartbeat_initialization(self):
        """Test heartbeat initialization."""
        assert len(self.heartbeat.last_heartbeat_times) == len(self.followers)
        assert len(self.heartbeat.heartbeat_acks) == len(self.followers)
        assert all(not ack for ack in self.heartbeat.heartbeat_acks.values())


class TestAppendEntriesIntegration:
    """Integration tests for AppendEntries."""
    
    @pytest.mark.asyncio
    async def test_full_replication_scenario(self):
        """Test complete replication scenario."""
        # Setup leader and follower
        leader_log = RaftLog('leader')
        follower_handler = AppendEntriesHandler('follower')
        follower_log = RaftLog('follower')
        follower_handler.log = follower_log
        
        # Leader appends entries
        for i in range(5):
            leader_log.append(1, {'op': 'set', 'key': f'key{i}', 'value': f'value{i}'})
        
        # Follower receives batch replication
        entries_to_replicate = []
        for i in range(1, 6):
            entry = leader_log.get_entry(i)
            entries_to_replicate.append(entry.to_dict())
        
        success, last_index = await follower_handler.handle_append_entries(
            term=1,
            leader_id='leader',
            prev_log_index=0,
            prev_log_term=0,
            entries=entries_to_replicate,
            leader_commit=5
        )
        
        assert success is True
        assert follower_handler.commit_index == 5
        assert follower_handler.last_applied == 5
        assert len(follower_handler.state_machine) == 5
    
    @pytest.mark.asyncio
    async def test_incremental_replication(self):
        """Test incremental replication with multiple RPCs."""
        handler = AppendEntriesHandler('follower')
        log = RaftLog('follower')
        handler.log = log
        
        # First batch: entries 1-3
        entries1 = [
            {
                'term': 1,
                'command': {'op': 'set', 'key': f'key{i}', 'value': f'value{i}'},
                'timestamp': datetime.now().isoformat()
            }
            for i in range(3)
        ]
        
        success1, _ = await handler.handle_append_entries(
            term=1,
            leader_id='leader',
            prev_log_index=0,
            prev_log_term=0,
            entries=entries1,
            leader_commit=0
        )
        
        assert success1 is True
        assert log.length() == 3
        
        # Second batch: entries 4-6
        entries2 = [
            {
                'term': 1,
                'command': {'op': 'set', 'key': f'key{i}', 'value': f'value{i}'},
                'timestamp': datetime.now().isoformat()
            }
            for i in range(3, 6)
        ]
        
        success2, _ = await handler.handle_append_entries(
            term=1,
            leader_id='leader',
            prev_log_index=3,
            prev_log_term=1,
            entries=entries2,
            leader_commit=0
        )
        
        assert success2 is True
        assert log.length() == 6
    
    @pytest.mark.asyncio
    async def test_eventual_consistency(self):
        """Test eventual consistency across replication."""
        handler = AppendEntriesHandler('follower')
        log = RaftLog('follower')
        handler.log = log
        
        # Simulate multiple replication rounds
        entries_count = 0
        for round_num in range(3):
            entries = [
                {
                    'term': 1,
                    'command': {'op': 'set', 'key': f'key_r{round_num}_{i}', 'value': f'v{i}'},
                    'timestamp': datetime.now().isoformat()
                }
                for i in range(2)
            ]
            
            prev_index = log.get_last_index()
            success, _ = await handler.handle_append_entries(
                term=1,
                leader_id='leader',
                prev_log_index=prev_index,
                prev_log_term=1,
                entries=entries,
                leader_commit=prev_index + len(entries)
            )
            
            entries_count += len(entries)
            assert success is True
        
        # All should be applied
        assert handler.last_applied == log.length()
        assert len(handler.state_machine) == 6
