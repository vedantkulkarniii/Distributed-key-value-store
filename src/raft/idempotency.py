"""
Idempotency and request deduplication for Raft state machine.

Implements:
- Client-side request deduplication
- Exactly-once semantics
- Idempotent operation handling
- Session state tracking
- Duplicate detection and suppression
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import OrderedDict
from uuid import uuid4

logger = logging.getLogger(__name__)


class RequestResult:
    """Cached result of a deduplicated request."""
    
    def __init__(self, request_id: str, result: Any, timestamp: Optional[datetime] = None):
        self.request_id = request_id
        self.result = result
        self.timestamp = timestamp or datetime.now()
        self.retrieval_count = 0  # How many times this result was retrieved
    
    def is_expired(self, ttl_seconds: int = 3600) -> bool:
        """Check if cached result has expired."""
        age = (datetime.now() - self.timestamp).total_seconds()
        return age > ttl_seconds
    
    def increment_retrieval(self) -> None:
        """Increment retrieval counter."""
        self.retrieval_count += 1


class ClientSession:
    """Session state for a client."""
    
    def __init__(self, client_id: str, session_id: str):
        self.client_id = client_id
        self.session_id = session_id
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        
        # Request deduplication cache
        self.request_cache: Dict[str, RequestResult] = OrderedDict()
        self.max_cache_size = 1000
        
        # Sequence tracking for ordering
        self.sequence_number = 0
        self.acknowledged_sequence = 0
        
        # Statistics
        self.total_requests = 0
        self.duplicate_count = 0
    
    def add_request(self, request_id: str, result: Any) -> None:
        """Add request result to cache."""
        self.request_cache[request_id] = RequestResult(request_id, result)
        self.total_requests += 1
        
        # Evict oldest if cache is full
        if len(self.request_cache) > self.max_cache_size:
            oldest_id = next(iter(self.request_cache))
            del self.request_cache[oldest_id]
    
    def get_request_result(self, request_id: str) -> Optional[Any]:
        """Get cached result for request."""
        if request_id in self.request_cache:
            result_obj = self.request_cache[request_id]
            result_obj.increment_retrieval()
            self.last_activity = datetime.now()
            return result_obj.result
        return None
    
    def is_duplicate(self, request_id: str) -> bool:
        """Check if request is a duplicate."""
        is_dup = request_id in self.request_cache
        if is_dup:
            self.duplicate_count += 1
        return is_dup
    
    def is_expired(self, ttl_seconds: int = 3600) -> bool:
        """Check if session has expired."""
        age = (datetime.now() - self.last_activity).total_seconds()
        return age > ttl_seconds
    
    def clean_expired_entries(self, ttl_seconds: int = 3600) -> int:
        """Remove expired entries from cache."""
        expired_count = 0
        keys_to_delete = [
            req_id for req_id, result_obj in self.request_cache.items()
            if result_obj.is_expired(ttl_seconds)
        ]
        
        for req_id in keys_to_delete:
            del self.request_cache[req_id]
            expired_count += 1
        
        return expired_count


class IdempotencyManager:
    """
    Manages idempotent request handling and deduplication.
    
    Ensures:
    - Exactly-once semantics for client requests
    - Duplicate detection and suppression
    - Session state tracking
    - Automatic cleanup of stale data
    """
    
    def __init__(self, node_id: str):
        """Initialize idempotency manager."""
        self.node_id = node_id
        
        # Session management
        self.sessions: Dict[str, ClientSession] = {}
        self.client_to_session: Dict[str, str] = {}  # client_id -> session_id
        
        # Global statistics
        self.total_requests = 0
        self.duplicate_requests = 0
        self.processed_requests = 0
        
        # Configuration
        self.session_ttl_seconds = 3600  # 1 hour
        self.request_cache_ttl_seconds = 3600
        self.max_sessions = 10000
        
        logger.info(f"Idempotency manager initialized for {node_id}")
    
    def create_session(self, client_id: str) -> Tuple[bool, str, Optional[str]]:
        """
        Create new client session.
        
        Args:
            client_id: Client identifier
            
        Returns:
            Tuple of (success, session_id, error_message)
        """
        # Check if client already has session
        if client_id in self.client_to_session:
            session_id = self.client_to_session[client_id]
            return True, session_id, None
        
        # Check session limit
        if len(self.sessions) >= self.max_sessions:
            return False, "", "Max sessions reached"
        
        # Create new session
        session_id = str(uuid4())
        session = ClientSession(client_id, session_id)
        
        self.sessions[session_id] = session
        self.client_to_session[client_id] = session_id
        
        logger.debug(f"Created session {session_id} for client {client_id}")
        
        return True, session_id, None
    
    def process_request(
        self,
        client_id: str,
        request_id: str,
        operation: Any,
    ) -> Tuple[bool, Optional[Any], Optional[str]]:
        """
        Process request with deduplication.
        
        Args:
            client_id: Client identifier
            request_id: Unique request identifier
            operation: Operation to execute
            
        Returns:
            Tuple of (is_duplicate, cached_result, error_message)
        """
        self.total_requests += 1
        
        # Get or create session
        if client_id not in self.client_to_session:
            success, session_id, error = self.create_session(client_id)
            if not success:
                return False, None, error
        
        session_id = self.client_to_session[client_id]
        session = self.sessions[session_id]
        
        # Check for duplicate
        if session.is_duplicate(request_id):
            self.duplicate_requests += 1
            cached_result = session.get_request_result(request_id)
            logger.debug(f"Duplicate request {request_id} from {client_id}")
            return True, cached_result, None
        
        # Not a duplicate - process normally
        self.processed_requests += 1
        logger.debug(f"Processing new request {request_id} from {client_id}")
        
        return False, None, None
    
    def cache_result(
        self,
        client_id: str,
        request_id: str,
        result: Any,
    ) -> Tuple[bool, Optional[str]]:
        """
        Cache result of processed request.
        
        Args:
            client_id: Client identifier
            request_id: Unique request identifier
            result: Result of operation
            
        Returns:
            Tuple of (success, error_message)
        """
        if client_id not in self.client_to_session:
            return False, f"No session for client {client_id}"
        
        session_id = self.client_to_session[client_id]
        if session_id not in self.sessions:
            return False, f"Session {session_id} not found"
        
        session = self.sessions[session_id]
        session.add_request(request_id, result)
        
        logger.debug(f"Cached result for request {request_id}")
        
        return True, None
    
    def get_cached_result(self, client_id: str, request_id: str) -> Optional[Any]:
        """
        Get cached result for request.
        
        Args:
            client_id: Client identifier
            request_id: Unique request identifier
            
        Returns:
            Cached result or None
        """
        if client_id not in self.client_to_session:
            return None
        
        session_id = self.client_to_session[client_id]
        if session_id not in self.sessions:
            return None
        
        session = self.sessions[session_id]
        return session.get_request_result(request_id)
    
    def acknowledge_request(self, client_id: str, sequence_number: int) -> Tuple[bool, Optional[str]]:
        """
        Acknowledge receipt of request sequence.
        
        Args:
            client_id: Client identifier
            sequence_number: Sequence number being acknowledged
            
        Returns:
            Tuple of (success, error_message)
        """
        if client_id not in self.client_to_session:
            return False, f"No session for client {client_id}"
        
        session_id = self.client_to_session[client_id]
        session = self.sessions[session_id]
        
        if sequence_number > session.acknowledged_sequence:
            session.acknowledged_sequence = sequence_number
        
        return True, None
    
    def cleanup_expired_sessions(self) -> int:
        """
        Remove expired sessions.
        
        Returns:
            Number of sessions removed
        """
        expired_sessions = [
            session_id for session_id, session in self.sessions.items()
            if session.is_expired(self.session_ttl_seconds)
        ]
        
        for session_id in expired_sessions:
            session = self.sessions.pop(session_id)
            # Remove client mapping
            for client_id, sid in list(self.client_to_session.items()):
                if sid == session_id:
                    del self.client_to_session[client_id]
            
            logger.debug(f"Expired session {session_id}")
        
        return len(expired_sessions)
    
    def cleanup_expired_requests(self) -> int:
        """
        Remove expired request entries from all sessions.
        
        Returns:
            Total number of entries removed
        """
        total_removed = 0
        
        for session in self.sessions.values():
            removed = session.clean_expired_entries(self.request_cache_ttl_seconds)
            total_removed += removed
        
        return total_removed
    
    def get_session_status(self, client_id: str) -> Optional[Dict]:
        """
        Get status of client session.
        
        Args:
            client_id: Client identifier
            
        Returns:
            Session status or None
        """
        if client_id not in self.client_to_session:
            return None
        
        session_id = self.client_to_session[client_id]
        if session_id not in self.sessions:
            return None
        
        session = self.sessions[session_id]
        
        return {
            "session_id": session_id,
            "client_id": client_id,
            "created_at": session.created_at.isoformat(),
            "last_activity": session.last_activity.isoformat(),
            "cached_requests": len(session.request_cache),
            "total_requests": session.total_requests,
            "duplicates": session.duplicate_count,
            "sequence_number": session.sequence_number,
            "acknowledged": session.acknowledged_sequence,
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get idempotency manager statistics.
        
        Returns:
            Dictionary with statistics
        """
        duplicate_rate = (
            self.duplicate_requests / self.total_requests
            if self.total_requests > 0
            else 0
        )
        
        total_cached_requests = sum(
            len(session.request_cache) for session in self.sessions.values()
        )
        
        return {
            "total_requests": self.total_requests,
            "processed_requests": self.processed_requests,
            "duplicate_requests": self.duplicate_requests,
            "duplicate_rate": duplicate_rate,
            "active_sessions": len(self.sessions),
            "total_cached_requests": total_cached_requests,
            "avg_cache_per_session": (
                total_cached_requests / len(self.sessions)
                if self.sessions else 0
            ),
        }
