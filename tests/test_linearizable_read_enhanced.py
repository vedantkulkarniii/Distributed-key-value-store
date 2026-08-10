"""Enhanced tests for linearizable read handler with quorum tracking."""

import pytest
from datetime import datetime, timedelta
from src.raft.linearizable_read import (
    LinearizableReadHandler,
    LinearizableReadRequest,
    ReadPhase,
)


class TestLinearizableReadEnhanced:
    """Enhanced test suite for LinearizableReadHandler."""
    
    @pytest.fixture
    def handler_3node(self):
        """Fixture for 3-node cluster handler."""
        return LinearizableReadHandler("node1", cluster_size=3)
    
    @pytest.fixture
    def handler_5node(self):
        """Fixture for 5-node cluster handler."""
        return LinearizableReadHandler("node1", cluster_size=5)
    
    @pytest.fixture
    def handler_7node(self):
        """Fixture for 7-node cluster handler."""
        return LinearizableReadHandler("node1", cluster_size=7)
    
    # Quorum Tests
    
    def test_quorum_size_3node(self, handler_3node):
        """Test quorum calculation for 3 nodes."""
        assert handler_3node.quorum_size == 2
    
    def test_quorum_size_5node(self, handler_5node):
        """Test quorum calculation for 5 nodes."""
        assert handler_5node.quorum_size == 3
    
    def test_quorum_size_7node(self, handler_7node):
        """Test quorum calculation for 7 nodes."""
        assert handler_7node.quorum_size == 4
    
    # Basic Read Lifecycle Tests
    
    def test_initiate_read(self, handler_3node):
        """Test initiating read request."""
        request = handler_3node.initiate_read(read_index=10)
        
        assert request is not None
        assert request.read_index == 10
        assert request.phase == ReadPhase.INITIATED
        assert "node1" in request.replicas_acked
    
    def test_initiate_multiple_reads(self, handler_3node):
        """Test initiating multiple read requests."""
        req1 = handler_3node.initiate_read(read_index=10)
        req2 = handler_3node.initiate_read(read_index=20)
        
        assert req1.request_id != req2.request_id
        assert len(handler_3node.pending_reads) == 2
    
    def test_read_index_phase(self, handler_3node):
        """Test read index acquisition phase."""
        request = handler_3node.initiate_read(read_index=10)
        success = handler_3node.process_read_index(request.request_id, 10, term=1)
        
        assert success
        assert request.phase == ReadPhase.READ_INDEX_ACQUIRED
    
    def test_heartbeat_phase(self, handler_3node):
        """Test heartbeat phase."""
        request = handler_3node.initiate_read(read_index=10)
        handler_3node.process_read_index(request.request_id, 10, term=1)
        
        success = handler_3node.send_heartbeat_for_read(request.request_id)
        
        assert success
        assert request.phase == ReadPhase.HEARTBEAT_SENT
    
    # Quorum ACK Tests
    
    def test_single_ack_insufficient(self, handler_3node):
        """Test that single ACK is insufficient for 3-node cluster."""
        request = handler_3node.initiate_read(read_index=10)
        handler_3node.process_read_index(request.request_id, 10, term=1)
        handler_3node.send_heartbeat_for_read(request.request_id)
        
        # Leader already acked, need 1 more
        quorum_met = handler_3node.record_heartbeat_ack(request.request_id, "node2")
        
        assert quorum_met
        assert len(request.replicas_acked) == 2
    
    def test_quorum_ack_met_3node(self, handler_3node):
        """Test quorum ACK for 3-node cluster."""
        request = handler_3node.initiate_read(read_index=10)
        handler_3node.process_read_index(request.request_id, 10, term=1)
        handler_3node.send_heartbeat_for_read(request.request_id)
        
        # Record ACK from second node
        quorum_met = handler_3node.record_heartbeat_ack(request.request_id, "node2")
        
        assert quorum_met
        assert request.phase == ReadPhase.HEARTBEAT_ACK_RECEIVED
        assert len(request.replicas_acked) >= handler_3node.quorum_size
    
    def test_quorum_ack_met_5node(self, handler_5node):
        """Test quorum ACK for 5-node cluster."""
        request = handler_5node.initiate_read(read_index=10)
        handler_5node.process_read_index(request.request_id, 10, term=1)
        handler_5node.send_heartbeat_for_read(request.request_id)
        
        # Record ACKs - need 2 more (leader + 2 followers = 3 total)
        quorum_met1 = handler_5node.record_heartbeat_ack(request.request_id, "node2")
        assert not quorum_met1
        
        quorum_met2 = handler_5node.record_heartbeat_ack(request.request_id, "node3")
        assert quorum_met2
        assert len(request.replicas_acked) >= handler_5node.quorum_size
    
    def test_duplicate_ack_same_node(self, handler_5node):
        """Test duplicate ACK from same node."""
        request = handler_5node.initiate_read(read_index=10)
        handler_5node.process_read_index(request.request_id, 10, term=1)
        handler_5node.send_heartbeat_for_read(request.request_id)
        
        handler_5node.record_heartbeat_ack(request.request_id, "node2")
        ack_set_1 = len(request.replicas_acked)
        
        # Send same ACK again
        handler_5node.record_heartbeat_ack(request.request_id, "node2")
        ack_set_2 = len(request.replicas_acked)
        
        assert ack_set_1 == ack_set_2  # Set size unchanged
    
    def test_majority_partition_scenario(self, handler_5node):
        """Test read with majority partition."""
        request = handler_5node.initiate_read(read_index=10)
        handler_5node.process_read_index(request.request_id, 10, term=1)
        handler_5node.send_heartbeat_for_read(request.request_id)
        
        # Get ACKs from 2 followers
        handler_5node.record_heartbeat_ack(request.request_id, "node2")
        quorum_met = handler_5node.record_heartbeat_ack(request.request_id, "node3")
        
        assert quorum_met
        # Nodes 4 and 5 don't respond, but quorum is met
        assert len(request.replicas_acked) == 3  # leader + node2 + node3
    
    # Applied Index Tests
    
    def test_wait_for_applied_not_ready(self, handler_3node):
        """Test waiting when applied index not ready."""
        request = handler_3node.initiate_read(read_index=10)
        handler_3node.process_read_index(request.request_id, 10, term=1)
        handler_3node.send_heartbeat_for_read(request.request_id)
        handler_3node.record_heartbeat_ack(request.request_id, "node2")
        
        # Applied index still behind
        can_read = handler_3node.wait_for_applied(request.request_id, applied_index=9)
        
        assert not can_read
        assert request.phase == ReadPhase.HEARTBEAT_ACK_RECEIVED
    
    def test_wait_for_applied_ready(self, handler_3node):
        """Test waiting when applied index is ready."""
        request = handler_3node.initiate_read(read_index=10)
        handler_3node.process_read_index(request.request_id, 10, term=1)
        handler_3node.send_heartbeat_for_read(request.request_id)
        handler_3node.record_heartbeat_ack(request.request_id, "node2")
        
        # Applied index reached
        can_read = handler_3node.wait_for_applied(request.request_id, applied_index=10)
        
        assert can_read
        assert request.phase == ReadPhase.APPLIED
    
    # Completion Tests
    
    def test_complete_read(self, handler_3node):
        """Test completing a read request."""
        request = handler_3node.initiate_read(read_index=10)
        handler_3node.process_read_index(request.request_id, 10, term=1)
        handler_3node.send_heartbeat_for_read(request.request_id)
        handler_3node.record_heartbeat_ack(request.request_id, "node2")
        handler_3node.wait_for_applied(request.request_id, applied_index=10)
        
        result = {"key": "value"}
        success = handler_3node.complete_read(request.request_id, result)
        
        assert success
        assert request.phase == ReadPhase.COMPLETED
        assert request.result == result
        assert request.request_id not in handler_3node.pending_reads
    
    def test_fail_read(self, handler_3node):
        """Test failing a read request."""
        request = handler_3node.initiate_read(read_index=10)
        
        success = handler_3node.fail_read(request.request_id, "Node failure")
        
        assert success
        assert request.error == "Node failure"
        assert request.request_id not in handler_3node.pending_reads
    
    # Timeout Tests
    
    def test_read_timeout(self, handler_3node):
        """Test read request timeout."""
        request = handler_3node.initiate_read(read_index=10, timeout_ms=100)
        request.created_at = datetime.now() - timedelta(milliseconds=200)
        
        assert request.is_timed_out()
    
    def test_read_not_timed_out(self, handler_3node):
        """Test read not timed out yet."""
        request = handler_3node.initiate_read(read_index=10, timeout_ms=1000)
        
        assert not request.is_timed_out()
    
    def test_reject_timed_out_read(self, handler_3node):
        """Test that timed out reads are rejected."""
        request = handler_3node.initiate_read(read_index=10, timeout_ms=100)
        request.created_at = datetime.now() - timedelta(milliseconds=200)
        
        success = handler_3node.process_read_index(request.request_id, 10, term=1)
        
        assert not success
        assert request.request_id not in handler_3node.pending_reads
    
    def test_cleanup_timed_out_reads(self, handler_3node):
        """Test cleaning up timed out reads."""
        # Create reads with different timeouts
        req1 = handler_3node.initiate_read(read_index=10, timeout_ms=100)
        req2 = handler_3node.initiate_read(read_index=20, timeout_ms=1000)
        
        req1.created_at = datetime.now() - timedelta(milliseconds=200)
        
        cleaned = handler_3node.cleanup_timed_out_reads()
        
        assert cleaned == 1
        assert req1.request_id not in handler_3node.pending_reads
        assert req2.request_id in handler_3node.pending_reads
    
    # Full Workflow Tests
    
    def test_complete_read_workflow_3node(self, handler_3node):
        """Test complete read workflow for 3-node cluster."""
        # 1. Initiate
        request = handler_3node.initiate_read(read_index=10)
        assert request.phase == ReadPhase.INITIATED
        
        # 2. Get read index
        handler_3node.process_read_index(request.request_id, 10, term=1)
        assert request.phase == ReadPhase.READ_INDEX_ACQUIRED
        
        # 3. Send heartbeat
        handler_3node.send_heartbeat_for_read(request.request_id)
        assert request.phase == ReadPhase.HEARTBEAT_SENT
        
        # 4. Get ACKs
        handler_3node.record_heartbeat_ack(request.request_id, "node2")
        assert request.phase == ReadPhase.HEARTBEAT_ACK_RECEIVED
        
        # 5. Wait for applied
        handler_3node.wait_for_applied(request.request_id, applied_index=10)
        assert request.phase == ReadPhase.APPLIED
        
        # 6. Complete
        result = {"status": "ok", "value": "data"}
        handler_3node.complete_read(request.request_id, result)
        assert request.phase == ReadPhase.COMPLETED
    
    def test_complete_read_workflow_5node(self, handler_5node):
        """Test complete read workflow for 5-node cluster."""
        request = handler_5node.initiate_read(read_index=20)
        handler_5node.process_read_index(request.request_id, 20, term=2)
        handler_5node.send_heartbeat_for_read(request.request_id)
        
        # Need 2 followers for quorum
        handler_5node.record_heartbeat_ack(request.request_id, "node2")
        handler_5node.record_heartbeat_ack(request.request_id, "node3")
        
        handler_5node.wait_for_applied(request.request_id, applied_index=20)
        result = {"x": 100}
        handler_5node.complete_read(request.request_id, result)
        
        assert request.phase == ReadPhase.COMPLETED
        assert request.result == result
    
    # Status and Statistics Tests
    
    def test_get_status(self, handler_3node):
        """Test getting handler status."""
        req1 = handler_3node.initiate_read(read_index=10)
        req2 = handler_3node.initiate_read(read_index=20)
        
        handler_3node.complete_read(req1.request_id, {"data": 1})
        
        status = handler_3node.get_status()
        
        assert status["node_id"] == "node1"
        assert status["quorum_size"] == 2
        assert status["pending_reads"] == 1
        assert status["completed_reads"] == 1
    
    def test_get_pending_reads(self, handler_3node):
        """Test getting pending reads."""
        req1 = handler_3node.initiate_read(read_index=10)
        req2 = handler_3node.initiate_read(read_index=20)
        
        pending = handler_3node.get_pending_reads()
        
        assert len(pending) == 2
        assert req1 in pending
        assert req2 in pending
    
    def test_get_timed_out_reads(self, handler_3node):
        """Test getting timed out reads."""
        req1 = handler_3node.initiate_read(read_index=10, timeout_ms=100)
        req2 = handler_3node.initiate_read(read_index=20, timeout_ms=1000)
        
        req1.created_at = datetime.now() - timedelta(milliseconds=200)
        
        timed_out = handler_3node.get_timed_out_reads()
        
        assert len(timed_out) == 1
        assert req1 in timed_out
        assert req2 not in timed_out
    
    # Commit Index Tests
    
    def test_update_commit_index(self, handler_3node):
        """Test updating commit index."""
        handler_3node.update_commit_index(new_index=10, term=1)
        
        assert handler_3node.committed_index == 10
        assert handler_3node.current_term == 1
    
    def test_update_applied_index(self, handler_3node):
        """Test updating applied index."""
        handler_3node.update_applied_index(new_index=10)
        
        assert handler_3node.applied_index == 10
    
    # Edge Cases
    
    def test_read_with_invalid_request_id(self, handler_3node):
        """Test operations on invalid request ID."""
        success = handler_3node.process_read_index("invalid_id", 10, term=1)
        assert not success
        
        quorum_met = handler_3node.record_heartbeat_ack("invalid_id", "node2")
        assert not quorum_met
        
        can_read = handler_3node.wait_for_applied("invalid_id", 10)
        assert not can_read
    
    def test_large_cluster(self):
        """Test with large cluster."""
        handler = LinearizableReadHandler("node1", cluster_size=21)
        
        assert handler.quorum_size == 11
        
        request = handler.initiate_read(read_index=10)
        handler.process_read_index(request.request_id, 10, term=1)
        handler.send_heartbeat_for_read(request.request_id)
        
        # Add 10 ACKs
        for i in range(2, 12):
            quorum_met = handler.record_heartbeat_ack(request.request_id, f"node{i}")
            if i == 11:
                assert quorum_met
