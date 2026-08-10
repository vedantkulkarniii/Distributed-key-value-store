"""Tests for idempotency and request deduplication."""

import pytest
from datetime import datetime, timedelta
from src.raft.idempotency import (
    IdempotencyManager,
    ClientSession,
    RequestResult,
)


class TestRequestResult:
    """Test suite for RequestResult."""
    
    def test_request_result_creation(self):
        """Test creating request result."""
        result = RequestResult("req1", {"status": "ok"})
        
        assert result.request_id == "req1"
        assert result.result == {"status": "ok"}
        assert result.retrieval_count == 0
    
    def test_request_result_not_expired(self):
        """Test request result not expired."""
        result = RequestResult("req1", {"status": "ok"})
        
        assert not result.is_expired(ttl_seconds=3600)
    
    def test_request_result_expired(self):
        """Test request result expired."""
        result = RequestResult("req1", {"status": "ok"})
        result.timestamp = datetime.now() - timedelta(hours=2)
        
        assert result.is_expired(ttl_seconds=3600)
    
    def test_increment_retrieval(self):
        """Test incrementing retrieval counter."""
        result = RequestResult("req1", {"status": "ok"})
        
        result.increment_retrieval()
        assert result.retrieval_count == 1
        
        result.increment_retrieval()
        assert result.retrieval_count == 2


class TestClientSession:
    """Test suite for ClientSession."""
    
    @pytest.fixture
    def session(self):
        """Fixture for client session."""
        return ClientSession("client1", "session1")
    
    def test_session_creation(self, session):
        """Test creating client session."""
        assert session.client_id == "client1"
        assert session.session_id == "session1"
        assert len(session.request_cache) == 0
    
    def test_add_request(self, session):
        """Test adding request to cache."""
        session.add_request("req1", {"result": "data"})
        
        assert "req1" in session.request_cache
        assert session.total_requests == 1
    
    def test_get_request_result(self, session):
        """Test retrieving request result."""
        session.add_request("req1", {"result": "data"})
        
        result = session.get_request_result("req1")
        assert result == {"result": "data"}
    
    def test_get_nonexistent_request(self, session):
        """Test getting nonexistent request."""
        result = session.get_request_result("nonexistent")
        assert result is None
    
    def test_is_duplicate(self, session):
        """Test duplicate detection."""
        session.add_request("req1", {"result": "data"})
        
        assert session.is_duplicate("req1")
        assert not session.is_duplicate("req2")
        assert session.duplicate_count == 1
    
    def test_session_expiration(self, session):
        """Test session expiration."""
        session.last_activity = datetime.now() - timedelta(hours=2)
        
        assert session.is_expired(ttl_seconds=3600)
    
    def test_session_not_expired(self, session):
        """Test session not expired."""
        assert not session.is_expired(ttl_seconds=3600)
    
    def test_clean_expired_entries(self, session):
        """Test cleaning expired entries."""
        result1 = RequestResult("req1", {"data": 1})
        result1.timestamp = datetime.now() - timedelta(hours=2)
        
        result2 = RequestResult("req2", {"data": 2})
        
        session.request_cache["req1"] = result1
        session.request_cache["req2"] = result2
        
        expired_count = session.clean_expired_entries(ttl_seconds=3600)
        
        assert expired_count == 1
        assert "req1" not in session.request_cache
        assert "req2" in session.request_cache


class TestIdempotencyManager:
    """Test suite for IdempotencyManager."""
    
    @pytest.fixture
    def manager(self):
        """Fixture for idempotency manager."""
        return IdempotencyManager("node1")
    
    # Session Management Tests
    
    def test_create_session(self, manager):
        """Test creating client session."""
        success, session_id, error = manager.create_session("client1")
        
        assert success
        assert session_id is not None
        assert error is None
        assert "client1" in manager.client_to_session
    
    def test_create_multiple_sessions(self, manager):
        """Test creating multiple sessions."""
        success1, sid1, _ = manager.create_session("client1")
        success2, sid2, _ = manager.create_session("client2")
        
        assert success1 and success2
        assert sid1 != sid2
        assert len(manager.sessions) == 2
    
    def test_same_client_gets_same_session(self, manager):
        """Test that same client gets same session."""
        success1, sid1, _ = manager.create_session("client1")
        success2, sid2, _ = manager.create_session("client1")
        
        assert success1 and success2
        assert sid1 == sid2
    
    # Request Processing Tests
    
    def test_process_new_request(self, manager):
        """Test processing new request."""
        manager.create_session("client1")
        is_dup, result, error = manager.process_request(
            "client1", "req1", {"op": "get", "key": "x"}
        )
        
        assert not is_dup
        assert result is None
        assert error is None
        assert manager.processed_requests == 1
    
    def test_process_duplicate_request(self, manager):
        """Test processing duplicate request."""
        manager.create_session("client1")
        
        # First request
        _, _, _ = manager.process_request("client1", "req1", {"op": "get"})
        manager.cache_result("client1", "req1", {"status": "ok"})
        
        # Duplicate request
        is_dup, result, _ = manager.process_request("client1", "req1", {"op": "get"})
        
        assert is_dup
        assert result == {"status": "ok"}
        assert manager.duplicate_requests == 1
    
    def test_process_creates_session_if_needed(self, manager):
        """Test that processing creates session if needed."""
        is_dup, _, _ = manager.process_request("client1", "req1", {"op": "get"})
        
        assert not is_dup
        assert "client1" in manager.client_to_session
    
    # Result Caching Tests
    
    def test_cache_result(self, manager):
        """Test caching request result."""
        manager.create_session("client1")
        success, error = manager.cache_result("client1", "req1", {"status": "ok"})
        
        assert success
        assert error is None
    
    def test_cache_and_retrieve(self, manager):
        """Test caching and retrieving result."""
        manager.create_session("client1")
        manager.cache_result("client1", "req1", {"status": "ok"})
        
        result = manager.get_cached_result("client1", "req1")
        assert result == {"status": "ok"}
    
    def test_get_cached_result_nonexistent(self, manager):
        """Test getting nonexistent cached result."""
        manager.create_session("client1")
        result = manager.get_cached_result("client1", "nonexistent")
        
        assert result is None
    
    # Deduplication Workflow Tests
    
    def test_full_deduplication_workflow(self, manager):
        """Test complete deduplication workflow."""
        # Create session
        manager.create_session("client1")
        
        # First request - new
        is_dup1, _, _ = manager.process_request("client1", "req1", {"op": "set", "key": "x", "value": 1})
        assert not is_dup1
        
        # Cache result
        manager.cache_result("client1", "req1", {"status": "ok"})
        
        # Same request again - should be duplicate
        is_dup2, result, _ = manager.process_request("client1", "req1", {"op": "set", "key": "x", "value": 1})
        assert is_dup2
        assert result == {"status": "ok"}
    
    def test_multiple_clients_separate_deduplication(self, manager):
        """Test that different clients have separate deduplication."""
        manager.create_session("client1")
        manager.create_session("client2")
        
        # Same request ID from different clients
        is_dup1, _, _ = manager.process_request("client1", "req1", {"op": "get"})
        manager.cache_result("client1", "req1", {"result": "A"})
        
        is_dup2, result2, _ = manager.process_request("client2", "req1", {"op": "get"})
        manager.cache_result("client2", "req1", {"result": "B"})
        
        assert not is_dup1
        assert not is_dup2
        assert manager.get_cached_result("client1", "req1") == {"result": "A"}
        assert manager.get_cached_result("client2", "req1") == {"result": "B"}
    
    # Sequence Tracking Tests
    
    def test_acknowledge_request(self, manager):
        """Test acknowledging request sequence."""
        manager.create_session("client1")
        success, error = manager.acknowledge_request("client1", 5)
        
        assert success
        session_id = manager.client_to_session["client1"]
        assert manager.sessions[session_id].acknowledged_sequence == 5
    
    # Cleanup Tests
    
    def test_cleanup_expired_sessions(self, manager):
        """Test cleaning up expired sessions."""
        manager.create_session("client1")
        manager.create_session("client2")
        
        # Expire one session
        session_id_1 = manager.client_to_session["client1"]
        session = manager.sessions[session_id_1]
        session.last_activity = datetime.now() - timedelta(hours=2)
        
        removed = manager.cleanup_expired_sessions()
        
        assert removed == 1
        assert session_id_1 not in manager.sessions
        assert "client1" not in manager.client_to_session
        assert len(manager.sessions) == 1
    
    def test_cleanup_expired_requests(self, manager):
        """Test cleaning up expired request entries."""
        manager.create_session("client1")
        session_id = manager.client_to_session["client1"]
        session = manager.sessions[session_id]
        
        # Add expired and fresh entries
        result_expired = RequestResult("req1", {"data": 1})
        result_expired.timestamp = datetime.now() - timedelta(hours=2)
        
        result_fresh = RequestResult("req2", {"data": 2})
        
        session.request_cache["req1"] = result_expired
        session.request_cache["req2"] = result_fresh
        
        removed = manager.cleanup_expired_requests()
        
        assert removed >= 1
    
    # Status and Statistics Tests
    
    def test_get_session_status(self, manager):
        """Test getting session status."""
        manager.create_session("client1")
        manager.cache_result("client1", "req1", {"status": "ok"})
        
        status = manager.get_session_status("client1")
        
        assert status is not None
        assert status["client_id"] == "client1"
        assert status["cached_requests"] == 1
    
    def test_get_statistics(self, manager):
        """Test getting manager statistics."""
        manager.create_session("client1")
        manager.create_session("client2")
        
        # Process some requests
        _, _, _ = manager.process_request("client1", "req1", {"op": "get"})
        manager.cache_result("client1", "req1", {"result": "ok"})
        
        # Duplicate
        _, _, _ = manager.process_request("client1", "req1", {"op": "get"})
        
        # Another request
        _, _, _ = manager.process_request("client2", "req2", {"op": "set"})
        
        stats = manager.get_statistics()
        
        assert stats["total_requests"] == 3
        assert stats["processed_requests"] == 2
        assert stats["duplicate_requests"] == 1
        assert 0 <= stats["duplicate_rate"] <= 1
        assert stats["active_sessions"] == 2
    
    # Edge Cases
    
    def test_empty_operation(self, manager):
        """Test processing empty operation."""
        manager.create_session("client1")
        is_dup, _, _ = manager.process_request("client1", "req1", {})
        
        assert not is_dup
    
    def test_large_result_caching(self, manager):
        """Test caching large results."""
        manager.create_session("client1")
        large_result = {"data": [i for i in range(10000)]}
        
        manager.cache_result("client1", "req1", large_result)
        retrieved = manager.get_cached_result("client1", "req1")
        
        assert retrieved == large_result
    
    def test_many_requests_per_session(self, manager):
        """Test session with many cached requests."""
        manager.create_session("client1")
        session_id = manager.client_to_session["client1"]
        session = manager.sessions[session_id]
        
        # Cache many requests
        for i in range(100):
            session.add_request(f"req{i}", {"result": i})
        
        assert len(session.request_cache) == 100
        assert session.get_request_result("req50") == {"result": 50}
