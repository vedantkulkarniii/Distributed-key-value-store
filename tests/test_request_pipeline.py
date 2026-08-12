"""Tests for client request pipeline and batching."""

import pytest
from datetime import datetime, timedelta
from src.raft.request_pipeline import (
    RequestPipeline,
    RequestPriority,
    BatchRequest,
)


class TestBatchRequest:
    """Test suite for BatchRequest."""
    
    def test_batch_creation(self):
        """Test creating batch request."""
        batch = BatchRequest("batch1", max_size=100, max_wait_ms=100)
        
        assert batch.batch_id == "batch1"
        assert batch.max_size == 100
        assert batch.get_size() == 0
    
    def test_add_request_to_batch(self):
        """Test adding requests to batch."""
        batch = BatchRequest("batch1", max_size=100)
        
        success = batch.add_request({"op": "SET", "key": "k1"})
        
        assert success
        assert batch.get_size() == 1
    
    def test_batch_full_detection(self):
        """Test batch full detection."""
        batch = BatchRequest("batch1", max_size=2)
        
        batch.add_request({"op": "SET"})
        batch.add_request({"op": "SET"})
        success = batch.add_request({"op": "SET"})
        
        assert not success
        assert batch.is_full
    
    def test_batch_ready_by_time(self):
        """Test batch ready by timeout."""
        batch = BatchRequest("batch1", max_wait_ms=10)
        batch.created_at = datetime.now() - timedelta(milliseconds=50)
        
        assert batch.is_ready()
    
    def test_batch_ready_by_size(self):
        """Test batch ready by size."""
        batch = BatchRequest("batch1", max_size=2)
        batch.add_request({"op": "SET"})
        batch.add_request({"op": "SET"})
        
        assert batch.is_ready()


class TestRequestPipeline:
    """Test suite for RequestPipeline."""
    
    @pytest.fixture
    def pipeline(self):
        """Fixture for request pipeline."""
        return RequestPipeline("node1", batch_size=10, batch_timeout_ms=100)
    
    # Request Submission Tests
    
    def test_submit_request(self, pipeline):
        """Test submitting request."""
        request = {"op": "SET", "key": "k1", "value": "v1"}
        
        success, error = pipeline.submit_request(request)
        
        assert success
        assert error is None
        assert pipeline.total_requests == 1
    
    def test_submit_multiple_requests(self, pipeline):
        """Test submitting multiple requests."""
        for i in range(5):
            pipeline.submit_request({"op": "SET", "key": f"k{i}"})
        
        assert pipeline.total_requests == 5
    
    def test_submit_with_priority(self, pipeline):
        """Test submitting with priority."""
        pipeline.submit_request({"op": "GET"}, priority=RequestPriority.NORMAL)
        pipeline.submit_request({"op": "SET"}, priority=RequestPriority.HIGH)
        pipeline.submit_request({"op": "DELETE"}, priority=RequestPriority.LOW)
        
        assert pipeline.total_requests == 3
    
    # Batch Creation Tests
    
    def test_create_batch(self, pipeline):
        """Test creating batch."""
        for i in range(5):
            pipeline.submit_request({"op": "SET", "key": f"k{i}"})
        
        batch = pipeline.create_batch()
        
        assert batch is not None
        assert batch.get_size() == 5
    
    def test_create_empty_batch(self, pipeline):
        """Test creating batch with no requests."""
        batch = pipeline.create_batch()
        
        assert batch is None
    
    def test_batch_respects_max_size(self, pipeline):
        """Test batch respects size limit."""
        pipeline.batch_size = 5
        
        for i in range(10):
            pipeline.submit_request({"op": "SET"})
        
        batch = pipeline.create_batch()
        
        assert batch.get_size() <= 5
    
    # Batch Ready Detection Tests
    
    def test_get_batch_full(self, pipeline):
        """Test getting full batch."""
        pipeline.batch_size = 5
        
        for i in range(5):
            pipeline.submit_request({"op": "SET"})
        
        batch = pipeline.get_batch_for_sending()
        
        assert batch is not None
    
    def test_get_batch_by_timeout(self, pipeline):
        """Test getting batch by timeout."""
        pipeline.batch_timeout_ms = 50
        
        pipeline.submit_request({"op": "SET"})
        
        # Wait for timeout
        import time
        time.sleep(0.1)
        
        batch = pipeline.get_batch_for_sending()
        
        assert batch is not None
    
    # Batch Sending Tests
    
    def test_send_batch(self, pipeline):
        """Test sending batch."""
        for i in range(3):
            pipeline.submit_request({"op": "SET"})
        
        batch = pipeline.create_batch()
        success, error = pipeline.send_batch(batch)
        
        assert success
        assert pipeline.batches_sent == 1
    
    # Priority Handling Tests
    
    def test_priority_order(self, pipeline):
        """Test requests batched in priority order."""
        # Submit in mixed order
        pipeline.submit_request({"op": "LOW"}, priority=RequestPriority.LOW)
        pipeline.submit_request({"op": "CRITICAL"}, priority=RequestPriority.CRITICAL)
        pipeline.submit_request({"op": "NORMAL"}, priority=RequestPriority.NORMAL)
        
        batch = pipeline.create_batch()
        
        # Critical should be first
        assert batch.requests[0]["op"] == "CRITICAL"
    
    # Queue Management Tests
    
    def test_get_pending_count(self, pipeline):
        """Test getting pending request count."""
        for i in range(5):
            pipeline.submit_request({"op": "SET"})
        
        count = pipeline.get_pending_count()
        
        assert count == 5
    
    def test_get_queue_depth(self, pipeline):
        """Test getting queue depth."""
        pipeline.submit_request({"op": "SET"}, priority=RequestPriority.HIGH)
        pipeline.submit_request({"op": "SET"}, priority=RequestPriority.NORMAL)
        pipeline.submit_request({"op": "SET"}, priority=RequestPriority.LOW)
        
        depths = pipeline.get_queue_depth()
        
        assert depths["HIGH"] == 1
        assert depths["NORMAL"] == 1
        assert depths["LOW"] == 1
    
    # Statistics Tests
    
    def test_get_throughput(self, pipeline):
        """Test getting throughput statistics."""
        for i in range(10):
            pipeline.submit_request({"op": "SET"})
        
        batch = pipeline.create_batch()
        pipeline.send_batch(batch)
        
        stats = pipeline.get_throughput()
        
        assert stats["total_requests"] == 10
        assert stats["total_batches"] == 1
        assert stats["batches_sent"] == 1
    
    def test_avg_batch_size(self, pipeline):
        """Test average batch size calculation."""
        # First batch: 5 requests
        for i in range(5):
            pipeline.submit_request({"op": "SET"})
        batch1 = pipeline.create_batch()
        pipeline.send_batch(batch1)
        
        # Second batch: 3 requests
        for i in range(3):
            pipeline.submit_request({"op": "SET"})
        batch2 = pipeline.create_batch()
        pipeline.send_batch(batch2)
        
        stats = pipeline.get_throughput()
        
        assert stats["avg_batch_size"] == 4.0
    
    # Flush Tests
    
    def test_flush_pipeline(self, pipeline):
        """Test flushing pipeline."""
        for i in range(7):
            pipeline.submit_request({"op": "SET", "index": i})
        
        all_requests = pipeline.flush_pipeline()
        
        assert len(all_requests) == 7
        assert pipeline.get_pending_count() == 0
    
    def test_flush_includes_current_batch(self, pipeline):
        """Test flush includes current batch."""
        for i in range(3):
            pipeline.submit_request({"op": "SET"})
        
        # Create current batch
        pipeline.create_batch()
        
        all_requests = pipeline.flush_pipeline()
        
        assert len(all_requests) == 3
    
    # Status Tests
    
    def test_get_status(self, pipeline):
        """Test getting pipeline status."""
        for i in range(5):
            pipeline.submit_request({"op": "SET"})
        
        status = pipeline.get_status()
        
        assert status["node_id"] == "node1"
        assert status["pending_requests"] == 5
        assert "statistics" in status
    
    # Edge Cases
    
    def test_single_request_batching(self, pipeline):
        """Test batching single request."""
        pipeline.batch_size = 1
        
        pipeline.submit_request({"op": "SET"})
        batch = pipeline.get_batch_for_sending()
        
        assert batch is not None
        assert batch.get_size() == 1
    
    def test_large_batch_size(self, pipeline):
        """Test with large batch size."""
        pipeline.batch_size = 1000
        
        for i in range(100):
            pipeline.submit_request({"op": "SET"})
        
        assert pipeline.get_pending_count() == 100
    
    def test_rapid_request_submission(self, pipeline):
        """Test rapid request submission."""
        for i in range(100):
            pipeline.submit_request({"op": "SET", "id": i})
        
        assert pipeline.total_requests == 100
    
    def test_batch_reuse_prevention(self, pipeline):
        """Test that batches are not reused."""
        for i in range(5):
            pipeline.submit_request({"op": "SET"})
        
        batch1 = pipeline.create_batch()
        pipeline.send_batch(batch1)
        
        # Submit more requests
        for i in range(3):
            pipeline.submit_request({"op": "GET"})
        
        batch2 = pipeline.create_batch()
        
        assert batch1.batch_id != batch2.batch_id
    
    def test_all_priority_levels(self, pipeline):
        """Test all priority levels."""
        for priority in RequestPriority:
            pipeline.submit_request({"op": "SET"}, priority=priority)
        
        assert pipeline.total_requests == 4
