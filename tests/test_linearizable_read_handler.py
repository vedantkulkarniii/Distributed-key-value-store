"""
Test suite for linearizable read handler.

Tests:
- Read request initiation and lifecycle
- Heartbeat ACK tracking and quorum validation
- Index advancement and consistency
- Timeout handling
- Status reporting
"""

import pytest
from datetime import datetime, timedelta
from src.raft.linearizable_read import (
    LinearizableReadHandler,
    LinearizableReadRequest,
    ReadPhase
)


class TestLinearizableReadBasics:
    """Test basic read request operations."""
    
    @pytest.fixture
    def handler(self):
        return LinearizableReadHandler("node-1", 3)
    
    def test_initialization(self, handler):
        """Test handler initialization."""
        assert handler.node_id == "node-1"
        assert handler.cluster_size == 3
        assert handler.quorum_size == 2
        assert handler.committed_index == 0
        assert handler.applied_index == 0
    
    def test_initiate_read(self, handler):
        """Test initiating a read request."""
        request = handler.initiate_read(5, timeout_ms=1000)
        
        assert request.read_index == 5
        assert request.phase == ReadPhase.INITIATED
        assert request.is_timed_out() is False
        assert request.request_id in handler.pending_reads
    
    def test_initiate_multiple_reads(self, handler):
        """Test initiating multiple read requests."""
        req1 = handler.initiate_read(5)
        req2 = handler.initiate_read(10)
        req3 = handler.initiate_read(15)
        
        assert len(handler.pending_reads) == 3
        assert req1.request_id != req2.request_id
        assert req2.request_id != req3.request_id


class TestReadIndexLifecycle:
    """Test read index acquisition lifecycle."""
    
    @pytest.fixture
    def handler(self):
        return LinearizableReadHandler("node-1", 3)
    
    def test_process_read_index(self, handler):
        """Test processing read index."""
        request = handler.initiate_read(5)
        result = handler.process_read_index(request.request_id, 5, 1)
        
        assert result is True
        request = handler.pending_reads[request.request_id]
        assert request.phase == ReadPhase.READ_INDEX_ACQUIRED
    
    def test_send_heartbeat_for_read(self, handler):
        """Test sending heartbeat for read."""
        request = handler.initiate_read(5)
        handler.process_read_index(request.request_id, 5, 1)
        
        result = handler.send_heartbeat_for_read(request.request_id)
        assert result is True
        
        request = handler.pending_reads[request.request_id]
        assert request.phase == ReadPhase.HEARTBEAT_SENT


class TestHeartbeatACK:
    """Test heartbeat ACK tracking."""
    
    @pytest.fixture
    def handler(self):
        return LinearizableReadHandler("node-1", 3)
    
    def test_single_ack(self, handler):
        """Test recording a single heartbeat ACK."""
        request = handler.initiate_read(5)
        handler.send_heartbeat_for_read(request.request_id)
        
        # Leader already has itself
        result = handler.record_heartbeat_ack(request.request_id, "node-1")
        assert result is False  # Not quorum yet (only leader)
    
    def test_quorum_ack(self, handler):
        """Test ACK reaching quorum."""
        request = handler.initiate_read(5)
        handler.send_heartbeat_for_read(request.request_id)
        
        # Get ack from one more node (quorum = 2)
        result = handler.record_heartbeat_ack(request.request_id, "node-2")
        assert result is True
        
        request = handler.pending_reads[request.request_id]
        assert request.phase == ReadPhase.HEARTBEAT_ACK_RECEIVED
        assert len(request.replicas_acked) == 2
    
    def test_ack_from_multiple_replicas(self, handler):
        """Test ACKs from multiple replicas."""
        request = handler.initiate_read(5)
        handler.send_heartbeat_for_read(request.request_id)
        
        result1 = handler.record_heartbeat_ack(request.request_id, "node-2")
        assert result1 is True  # Quorum reached (2/2)
        
        # Additional ack still returns True in 3-node cluster (quorum=2, have 3 acks)
        result2 = handler.record_heartbeat_ack(request.request_id, "node-3")
        assert result2 is True  # Still >= quorum


class TestIndexAdvancement:
    """Test index advancement and consistency."""
    
    @pytest.fixture
    def handler(self):
        return LinearizableReadHandler("node-1", 3)
    
    def test_update_commit_index(self, handler):
        """Test updating committed index."""
        handler.update_commit_index(5, 1)
        assert handler.committed_index == 5
        assert handler.current_term == 1
    
    def test_update_applied_index(self, handler):
        """Test updating applied index."""
        handler.update_applied_index(5)
        assert handler.applied_index == 5
    
    def test_wait_for_applied_ready(self, handler):
        """Test waiting for applied index when ready."""
        request = handler.initiate_read(5)
        handler.send_heartbeat_for_read(request.request_id)
        handler.record_heartbeat_ack(request.request_id, "node-2")
        
        # Applied index >= read_index
        result = handler.wait_for_applied(request.request_id, 5)
        assert result is True
        
        request = handler.pending_reads[request.request_id]
        assert request.phase == ReadPhase.APPLIED
    
    def test_wait_for_applied_not_ready(self, handler):
        """Test waiting for applied index when not ready."""
        request = handler.initiate_read(10)
        handler.send_heartbeat_for_read(request.request_id)
        handler.record_heartbeat_ack(request.request_id, "node-2")
        
        # Applied index < read_index
        result = handler.wait_for_applied(request.request_id, 5)
        assert result is False
        
        request = handler.pending_reads[request.request_id]
        assert request.phase == ReadPhase.HEARTBEAT_ACK_RECEIVED


class TestReadCompletion:
    """Test read request completion."""
    
    @pytest.fixture
    def handler(self):
        return LinearizableReadHandler("node-1", 3)
    
    def test_complete_read_success(self, handler):
        """Test completing a read successfully."""
        request = handler.initiate_read(5)
        
        result = handler.complete_read(request.request_id, {"key": "value"})
        assert result is True
        
        assert request.request_id not in handler.pending_reads
        assert len(handler.completed_reads) == 1
        assert handler.completed_reads[0].phase == ReadPhase.COMPLETED
        assert handler.completed_reads[0].result == {"key": "value"}
    
    def test_fail_read(self, handler):
        """Test failing a read."""
        request = handler.initiate_read(5)
        
        result = handler.fail_read(request.request_id, "Node not leader")
        assert result is True
        
        assert request.request_id not in handler.pending_reads
        assert len(handler.completed_reads) == 1
        assert handler.completed_reads[0].error == "Node not leader"


class TestTimeoutHandling:
    """Test timeout handling for read requests."""
    
    @pytest.fixture
    def handler(self):
        return LinearizableReadHandler("node-1", 3)
    
    def test_read_timeout_check(self, handler):
        """Test checking if read has timed out."""
        request = LinearizableReadRequest("test-id", 5, timeout_ms=1)
        
        assert request.is_timed_out() is False
        
        # Wait past timeout
        import time
        time.sleep(0.05)
        assert request.is_timed_out() is True
    
    def test_get_timed_out_reads(self, handler):
        """Test getting timed out reads."""
        req1 = handler.initiate_read(5, timeout_ms=1000)
        req2 = handler.initiate_read(10, timeout_ms=1)
        
        import time
        time.sleep(0.05)
        
        timed_out = handler.get_timed_out_reads()
        assert len(timed_out) == 1
        assert timed_out[0].request_id == req2.request_id
    
    def test_cleanup_timed_out_reads(self, handler):
        """Test cleaning up timed out reads."""
        req1 = handler.initiate_read(5, timeout_ms=1000)
        req2 = handler.initiate_read(10, timeout_ms=1)
        
        import time
        time.sleep(0.05)
        
        count = handler.cleanup_timed_out_reads()
        assert count == 1
        assert len(handler.pending_reads) == 1
        assert len(handler.completed_reads) == 1


class TestQuorumSizes:
    """Test quorum calculation for different cluster sizes."""
    
    def test_single_node_quorum(self):
        """Test quorum for single node."""
        handler = LinearizableReadHandler("node-1", 1)
        assert handler.quorum_size == 1
    
    def test_two_node_quorum(self):
        """Test quorum for two nodes."""
        handler = LinearizableReadHandler("node-1", 2)
        assert handler.quorum_size == 2
    
    def test_three_node_quorum(self):
        """Test quorum for three nodes."""
        handler = LinearizableReadHandler("node-1", 3)
        assert handler.quorum_size == 2
    
    def test_five_node_quorum(self):
        """Test quorum for five nodes."""
        handler = LinearizableReadHandler("node-1", 5)
        assert handler.quorum_size == 3
    
    def test_seven_node_quorum(self):
        """Test quorum for seven nodes."""
        handler = LinearizableReadHandler("node-1", 7)
        assert handler.quorum_size == 4


class TestReadStatus:
    """Test read handler status reporting."""
    
    @pytest.fixture
    def handler(self):
        return LinearizableReadHandler("node-1", 3)
    
    def test_initial_status(self, handler):
        """Test initial status."""
        status = handler.get_status()
        
        assert status["node_id"] == "node-1"
        assert status["cluster_size"] == 3
        assert status["quorum_size"] == 2
        assert status["pending_reads"] == 0
        assert status["completed_reads"] == 0
    
    def test_status_with_pending_reads(self, handler):
        """Test status with pending reads."""
        handler.initiate_read(5)
        handler.initiate_read(10)
        
        status = handler.get_status()
        assert status["pending_reads"] == 2
    
    def test_status_with_completed_reads(self, handler):
        """Test status with completed reads."""
        request = handler.initiate_read(5)
        handler.complete_read(request.request_id, {"key": "value"})
        
        status = handler.get_status()
        assert status["completed_reads"] == 1
        assert status["pending_reads"] == 0


class TestEdgeCases:
    """Test edge cases."""
    
    @pytest.fixture
    def handler(self):
        return LinearizableReadHandler("node-1", 3)
    
    def test_process_nonexistent_request(self, handler):
        """Test processing non-existent request."""
        result = handler.process_read_index("invalid-id", 5, 1)
        assert result is False
    
    def test_ack_nonexistent_request(self, handler):
        """Test ACK for non-existent request."""
        result = handler.record_heartbeat_ack("invalid-id", "node-2")
        assert result is False
    
    def test_complete_nonexistent_request(self, handler):
        """Test completing non-existent request."""
        result = handler.complete_read("invalid-id", {})
        assert result is False
    
    def test_multiple_operations_same_request(self, handler):
        """Test multiple operations on same request."""
        request = handler.initiate_read(5)
        rid = request.request_id
        
        assert handler.process_read_index(rid, 5, 1) is True
        assert handler.send_heartbeat_for_read(rid) is True
        assert handler.record_heartbeat_ack(rid, "node-2") is True
        assert handler.wait_for_applied(rid, 5) is True
        assert handler.complete_read(rid, {"data": "result"}) is True
        
        assert len(handler.pending_reads) == 0
        assert len(handler.completed_reads) == 1


class TestConsistencyScenarios:
    """Test realistic consistency scenarios."""
    
    @pytest.fixture
    def handler(self):
        return LinearizableReadHandler("node-1", 5)
    
    def test_read_after_commit(self, handler):
        """Test read after commit."""
        # Simulate: leader commits entry, then reads
        handler.update_commit_index(10, 1)
        
        request = handler.initiate_read(10)
        handler.process_read_index(request.request_id, 10, 1)
        handler.send_heartbeat_for_read(request.request_id)
        
        # Get quorum ACKs
        for node in ["node-2", "node-3"]:
            if handler.record_heartbeat_ack(request.request_id, node):
                break
        
        # Apply all entries
        handler.update_applied_index(10)
        assert handler.wait_for_applied(request.request_id, 10) is True
    
    def test_concurrent_reads(self, handler):
        """Test concurrent reads."""
        requests = []
        for i in range(5):
            req = handler.initiate_read(10 + i)
            requests.append(req)
        
        assert len(handler.pending_reads) == 5
        
        # Process all reads
        for req in requests:
            handler.process_read_index(req.request_id, req.read_index, 1)
            handler.send_heartbeat_for_read(req.request_id)
            handler.record_heartbeat_ack(req.request_id, "node-2")
            handler.record_heartbeat_ack(req.request_id, "node-3")
            handler.wait_for_applied(req.request_id, req.read_index)
            handler.update_applied_index(req.read_index)
            handler.complete_read(req.request_id, {})
        
        assert len(handler.pending_reads) == 0
        assert len(handler.completed_reads) == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
