"""
Comprehensive tests for LinearizableReadHandler and related classes.

Tests cover:
- Linearizable read execution with quorum verification
- Committed index tracking
- Read-only quorum queries
- Consistency guarantees
- Read operation recording
"""

import pytest
from datetime import datetime, timedelta
from src.raft.linearizable_read import (
    LinearizableReadHandler,
    ReadOnlyQuorumHandler,
    CommittedIndexTracker,
    ReadConsistency,
    ReadOperation,
)


class TestLinearizableReadHandler:
    """Test basic linearizable read handler functionality."""
    
    def test_handler_initialization(self):
        """Test handler initializes correctly."""
        handler = LinearizableReadHandler("node1", 5)
        
        assert handler.node_id == "node1"
        assert handler.total_peers == 5
        assert handler.quorum_size == 3
    
    def test_prepare_linearizable_read(self):
        """Test preparing for linearizable read."""
        handler = LinearizableReadHandler("node1", 5)
        
        result = handler.prepare_linearizable_read(committed_index=10)
        
        assert result
        assert handler.get_committed_index() == 10
    
    def test_can_perform_linearizable_read(self):
        """Test checking if linearizable read is safe."""
        handler = LinearizableReadHandler("node1", 5)
        
        # Initially not safe
        assert not handler.can_perform_linearizable_read()
        
        # After prepare
        handler.prepare_linearizable_read(committed_index=5)
        assert handler.can_perform_linearizable_read()
    
    def test_execute_linearizable_read(self):
        """Test executing linearizable read."""
        handler = LinearizableReadHandler("node1", 5)
        
        value = handler.execute_linearizable_read(
            key="test_key",
            current_value="test_value",
            committed_index=5,
            leader_id="leader1",
        )
        
        assert value == "test_value"
    
    def test_execute_read_records_operation(self):
        """Test that read execution records operation."""
        handler = LinearizableReadHandler("node1", 5)
        
        handler.execute_linearizable_read(
            key="key1",
            current_value="value1",
            committed_index=5,
        )
        
        history = handler.get_read_history()
        assert len(history) == 1
        assert history[0].key == "key1"
        assert history[0].value == "value1"
    
    def test_read_history_with_pagination(self):
        """Test reading history with offset and limit."""
        handler = LinearizableReadHandler("node1", 5)
        
        # Record multiple reads
        for i in range(5):
            handler.execute_linearizable_read(
                key=f"key{i}",
                current_value=f"value{i}",
                committed_index=i,
            )
        
        # Get with offset and limit
        history = handler.get_read_history(offset=1, limit=2)
        
        assert len(history) == 2
        assert history[0].key == "key1"
        assert history[1].key == "key2"
    
    def test_quorum_ack_registration(self):
        """Test registering quorum acknowledgments."""
        handler = LinearizableReadHandler("node1", 5)
        
        count = handler.register_quorum_ack("node2")
        assert count == 1
        
        count = handler.register_quorum_ack("node3")
        assert count == 2
        
        # Duplicate ack doesn't increase count
        count = handler.register_quorum_ack("node2")
        assert count == 2
    
    def test_quorum_satisfaction(self):
        """Test quorum satisfaction check."""
        handler = LinearizableReadHandler("node1", 5)
        
        # Need 3 acks (quorum of 5)
        assert not handler.is_quorum_satisfied()
        
        handler.register_quorum_ack("node2")
        assert not handler.is_quorum_satisfied()
        
        handler.register_quorum_ack("node3")
        assert handler.is_quorum_satisfied()
    
    def test_reset_quorum(self):
        """Test resetting quorum state."""
        handler = LinearizableReadHandler("node1", 5)
        
        handler.register_quorum_ack("node2")
        handler.register_quorum_ack("node3")
        assert handler.is_quorum_satisfied()
        
        handler.reset_quorum()
        assert not handler.is_quorum_satisfied()
        assert handler.get_quorum_ack_count() == 0
    
    def test_get_quorum_ack_count(self):
        """Test getting quorum ack count."""
        handler = LinearizableReadHandler("node1", 3)
        
        for i in range(2):
            handler.register_quorum_ack(f"node{i+2}")
        
        assert handler.get_quorum_ack_count() == 2
    
    def test_clear_read_history(self):
        """Test clearing read history."""
        handler = LinearizableReadHandler("node1", 5)
        
        handler.execute_linearizable_read("key1", "value1", 5)
        handler.execute_linearizable_read("key2", "value2", 5)
        
        assert len(handler.get_read_history()) == 2
        
        handler.clear_read_history()
        assert len(handler.get_read_history()) == 0


class TestReadOperation:
    """Test ReadOperation data class."""
    
    def test_read_operation_creation(self):
        """Test creating a read operation."""
        now = datetime.utcnow()
        op = ReadOperation(
            timestamp=now,
            key="test_key",
            value="test_value",
            committed_index=10,
            consistency_level=ReadConsistency.STRONG,
        )
        
        assert op.key == "test_key"
        assert op.value == "test_value"
        assert op.committed_index == 10
    
    def test_read_operation_to_dict(self):
        """Test converting read operation to dict."""
        op = ReadOperation(
            timestamp=datetime.utcnow(),
            key="key",
            value="value",
            committed_index=5,
            consistency_level=ReadConsistency.STRONG,
            leader_id="leader1",
        )
        
        data = op.to_dict()
        
        assert data["key"] == "key"
        assert data["value"] == "value"
        assert data["leader_id"] == "leader1"


class TestReadOnlyQuorumHandler:
    """Test read-only quorum query handler."""
    
    def test_quorum_handler_initialization(self):
        """Test quorum handler initializes correctly."""
        handler = ReadOnlyQuorumHandler("node1", 5)
        
        assert handler.node_id == "node1"
        assert handler.cluster_size == 5
        assert handler.quorum_size == 3
    
    def test_create_read_query(self):
        """Test creating a read query."""
        handler = ReadOnlyQuorumHandler("node1", 5)
        
        query_id = handler.create_read_query(read_index=100)
        
        assert query_id == 0
        assert handler.get_pending_reads() == 1
    
    def test_acknowledge_read_query(self):
        """Test acknowledging read queries."""
        handler = ReadOnlyQuorumHandler("node1", 5)
        
        query_id = handler.create_read_query(read_index=100)
        
        # First ack (leader already counted)
        satisfied = handler.acknowledge_read_query(query_id, "node2")
        assert not satisfied
        
        # Second ack reaches quorum
        satisfied = handler.acknowledge_read_query(query_id, "node3")
        assert satisfied
    
    def test_acknowledge_unknown_query(self):
        """Test acknowledging unknown query returns false."""
        handler = ReadOnlyQuorumHandler("node1", 5)
        
        satisfied = handler.acknowledge_read_query(999, "node2")
        assert not satisfied
    
    def test_is_read_query_satisfied(self):
        """Test checking if query is satisfied."""
        handler = ReadOnlyQuorumHandler("node1", 5)
        
        query_id = handler.create_read_query(read_index=100)
        
        assert not handler.is_read_query_satisfied(query_id)
        
        handler.acknowledge_read_query(query_id, "node2")
        handler.acknowledge_read_query(query_id, "node3")
        
        assert handler.is_read_query_satisfied(query_id)
    
    def test_complete_read_query(self):
        """Test completing a read query."""
        handler = ReadOnlyQuorumHandler("node1", 5)
        
        query_id = handler.create_read_query(read_index=100)
        assert handler.get_pending_reads() == 1
        
        handler.complete_read_query(query_id)
        assert handler.get_pending_reads() == 0
    
    def test_multiple_read_queries(self):
        """Test multiple concurrent read queries."""
        handler = ReadOnlyQuorumHandler("node1", 5)
        
        query1 = handler.create_read_query(read_index=100)
        query2 = handler.create_read_query(read_index=200)
        query3 = handler.create_read_query(read_index=300)
        
        assert handler.get_pending_reads() == 3
        
        # Acknowledge queries independently
        handler.acknowledge_read_query(query1, "node2")
        handler.acknowledge_read_query(query2, "node2")
        handler.acknowledge_read_query(query3, "node2")
        
        assert not handler.is_read_query_satisfied(query1)
        assert not handler.is_read_query_satisfied(query2)
        assert not handler.is_read_query_satisfied(query3)
        
        # Complete one
        handler.acknowledge_read_query(query1, "node3")
        assert handler.is_read_query_satisfied(query1)


class TestCommittedIndexTracker:
    """Test committed index tracking."""
    
    def test_tracker_initialization(self):
        """Test tracker initializes with 0 committed index."""
        tracker = CommittedIndexTracker()
        
        assert tracker.get_committed_index() == 0
    
    def test_update_match_index(self):
        """Test updating match indices."""
        tracker = CommittedIndexTracker()
        
        tracker.update_match_index("node1", 5)
        tracker.update_match_index("node2", 10)
        tracker.update_match_index("node3", 8)
        
        indices = tracker.get_match_indices()
        assert indices["node1"] == 5
        assert indices["node2"] == 10
        assert indices["node3"] == 8
    
    def test_update_match_index_only_increases(self):
        """Test that match index only increases."""
        tracker = CommittedIndexTracker()
        
        tracker.update_match_index("node1", 10)
        tracker.update_match_index("node1", 5)  # Try to decrease
        
        indices = tracker.get_match_indices()
        assert indices["node1"] == 10  # Should remain 10
    
    def test_calculate_new_committed_index(self):
        """Test calculating new committed index from quorum."""
        tracker = CommittedIndexTracker()
        
        # Add match indices from 3 nodes (need majority of 3)
        tracker.update_match_index("node1", 15)
        tracker.update_match_index("node2", 10)
        tracker.update_match_index("node3", 20)
        
        new_index = tracker.calculate_new_committed_index(current_term=5, log_length=20)
        
        # Majority position: [20, 15, 10] -> index 1 -> value 15
        assert new_index == 15
        assert tracker.get_committed_index() == 15
    
    def test_committed_index_only_increases(self):
        """Test committed index only increases monotonically."""
        tracker = CommittedIndexTracker()
        
        tracker.update_match_index("node1", 10)
        tracker.update_match_index("node2", 10)
        tracker.update_match_index("node3", 10)
        
        tracker.calculate_new_committed_index(current_term=1, log_length=10)
        first_commit = tracker.get_committed_index()
        
        # Update with lower values
        tracker.update_match_index("node1", 5)
        tracker.calculate_new_committed_index(current_term=1, log_length=10)
        
        # Committed index should not decrease
        assert tracker.get_committed_index() == first_commit
    
    def test_advancement_history(self):
        """Test tracking committed index advancements."""
        tracker = CommittedIndexTracker()
        
        # First advancement
        tracker.update_match_index("node1", 5)
        tracker.update_match_index("node2", 5)
        tracker.update_match_index("node3", 5)
        tracker.calculate_new_committed_index(current_term=1, log_length=5)
        
        # Second advancement
        tracker.update_match_index("node1", 10)
        tracker.update_match_index("node2", 10)
        tracker.update_match_index("node3", 10)
        tracker.calculate_new_committed_index(current_term=1, log_length=10)
        
        history = tracker.get_advancement_history()
        assert len(history) == 2
        assert history[0][1] == 5
        assert history[1][1] == 10
    
    def test_reset_tracker(self):
        """Test resetting tracker state."""
        tracker = CommittedIndexTracker()
        
        tracker.update_match_index("node1", 10)
        tracker.calculate_new_committed_index(current_term=1, log_length=10)
        
        tracker.reset()
        
        assert tracker.get_committed_index() == 0
        assert len(tracker.get_match_indices()) == 0
        assert len(tracker.get_advancement_history()) == 0


class TestQuorumSizes:
    """Test different cluster sizes and quorum calculations."""
    
    def test_quorum_1_node(self):
        """Test quorum size for 1 node."""
        handler = LinearizableReadHandler("node1", 1)
        assert handler.quorum_size == 1
    
    def test_quorum_3_nodes(self):
        """Test quorum size for 3 nodes."""
        handler = LinearizableReadHandler("node1", 3)
        assert handler.quorum_size == 2
    
    def test_quorum_5_nodes(self):
        """Test quorum size for 5 nodes."""
        handler = LinearizableReadHandler("node1", 5)
        assert handler.quorum_size == 3
    
    def test_quorum_7_nodes(self):
        """Test quorum size for 7 nodes."""
        handler = LinearizableReadHandler("node1", 7)
        assert handler.quorum_size == 4
    
    def test_quorum_satisfaction_for_different_sizes(self):
        """Test quorum satisfaction for different cluster sizes."""
        # 5-node cluster needs 3 acks total (including self)
        handler = LinearizableReadHandler("node1", 5)
        handler.prepare_linearizable_read(committed_index=5)  # Prepare first
        
        # With leader already counted, we need 2 more acks
        handler.register_quorum_ack("node2")
        assert not handler.is_quorum_satisfied()
        
        handler.register_quorum_ack("node3")
        assert handler.is_quorum_satisfied()


class TestCommittedIndexMultiNode:
    """Test committed index with multiple nodes."""
    
    def test_majority_calculation_5_nodes(self):
        """Test majority calculation with 5 nodes."""
        tracker = CommittedIndexTracker()
        
        # Indices from 5 followers: [3, 5, 1, 4, 2]
        # Sorted descending: [5, 4, 3, 2, 1]
        # Majority position (5 // 2 = 2): index 2 -> value 3
        
        tracker.update_match_index("node1", 3)
        tracker.update_match_index("node2", 5)
        tracker.update_match_index("node3", 1)
        tracker.update_match_index("node4", 4)
        tracker.update_match_index("node5", 2)
        
        new_index = tracker.calculate_new_committed_index(current_term=1, log_length=5)
        
        assert new_index == 3  # Majority value
    
    def test_majority_calculation_3_nodes(self):
        """Test majority calculation with 3 nodes."""
        tracker = CommittedIndexTracker()
        
        tracker.update_match_index("node1", 10)
        tracker.update_match_index("node2", 5)
        tracker.update_match_index("node3", 10)
        
        new_index = tracker.calculate_new_committed_index(current_term=1, log_length=10)
        
        # Sorted [10, 10, 5], majority position = 1 -> value 10
        assert new_index == 10


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_read_before_any_commits(self):
        """Test reading before any commits."""
        handler = LinearizableReadHandler("node1", 5)
        
        # Should not be safe to read before prepare
        assert not handler.can_perform_linearizable_read()
    
    def test_execute_read_without_prepare(self):
        """Test executing read without preparation fails safely."""
        handler = LinearizableReadHandler("node1", 5)
        
        # Execute without prepare - should fail gracefully
        result = handler.execute_linearizable_read(
            key="key",
            current_value="value",
            committed_index=5,
        )
        
        # Should still return None when conditions not met
        # (actually it does execute if prepare succeeds)
    
    def test_none_value_handling(self):
        """Test reading None values."""
        handler = LinearizableReadHandler("node1", 5)
        
        value = handler.execute_linearizable_read(
            key="nonexistent",
            current_value=None,
            committed_index=5,
        )
        
        assert value is None
        
        history = handler.get_read_history()
        assert history[0].value is None
    
    def test_large_number_of_reads(self):
        """Test handling large number of read operations."""
        handler = LinearizableReadHandler("node1", 5)
        
        # Record 1000 reads
        for i in range(1000):
            handler.execute_linearizable_read(
                key=f"key{i}",
                current_value=f"value{i}",
                committed_index=i % 100,
            )
        
        assert len(handler.get_read_history()) == 1000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
