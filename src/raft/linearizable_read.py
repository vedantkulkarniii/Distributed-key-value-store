"""
Linearizable read implementation for Raft consensus.

Implements:
- Linearizable read consistency (reads see all committed writes)
- Read-index method for lease-based reads
- Heartbeat confirmation for read safety
- Quorum-based commit tracking
"""

import logging
from typing import Dict, Any, List, Optional, Set, Tuple
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class ReadPhase(Enum):
    """Phases of linearizable read protocol."""
    INITIATED = "initiated"
    READ_INDEX_ACQUIRED = "read_index_acquired"
    HEARTBEAT_SENT = "heartbeat_sent"
    HEARTBEAT_ACK_RECEIVED = "heartbeat_ack_received"
    APPLIED = "applied"
    COMPLETED = "completed"


class LinearizableReadRequest:
    """Represents a linearizable read request."""
    
    def __init__(self, request_id: str, read_index: int, timeout_ms: int = 1000):
        self.request_id = request_id
        self.read_index = read_index
        self.timeout_ms = timeout_ms
        self.created_at = datetime.now()
        self.phase = ReadPhase.INITIATED
        self.replicas_acked: Set[str] = set()
        self.result = None
        self.error = None
    
    def is_timed_out(self) -> bool:
        """Check if request has timed out."""
        elapsed = (datetime.now() - self.created_at).total_seconds() * 1000
        return elapsed > self.timeout_ms
    
    def __repr__(self) -> str:
        return (
            f"LinearizableReadRequest(id={self.request_id}, "
            f"read_index={self.read_index}, phase={self.phase.value})"
        )


class LinearizableReadHandler:
    """
    Manages linearizable read consistency.
    
    Ensures:
    - All reads see committed state
    - Strong consistency across cluster
    - Quorum-based safety
    - Lease-based optimization
    """
    
    def __init__(self, node_id: str, cluster_size: int):
        """Initialize read handler."""
        self.node_id = node_id
        self.cluster_size = cluster_size
        self.quorum_size = (cluster_size // 2) + 1
        
        # Read request tracking
        self.pending_reads: Dict[str, LinearizableReadRequest] = {}
        self.completed_reads: List[LinearizableReadRequest] = []
        
        # State tracking
        self.committed_index = 0
        self.applied_index = 0
        self.current_term = 0
        self.leader_id: Optional[str] = None
        
        # Replica tracking for heartbeat ACKs
        self.replica_ack_set: Dict[str, Set[str]] = {}  # request_id -> set of replica ids
        
        logger.info(f"LinearizableReadHandler initialized for {node_id} (quorum={self.quorum_size})")
    
    def initiate_read(self, read_index: int, timeout_ms: int = 1000) -> LinearizableReadRequest:
        """
        Initiate a linearizable read request.
        
        Args:
            read_index: The log index to read from (usually committed_index)
            timeout_ms: Request timeout in milliseconds
            
        Returns:
            LinearizableReadRequest object
        """
        request_id = f"read-{len(self.pending_reads)}-{int(datetime.now().timestamp() * 1000)}"
        request = LinearizableReadRequest(request_id, read_index, timeout_ms)
        
        self.pending_reads[request_id] = request
        self.replica_ack_set[request_id] = {self.node_id}  # Leader always acks itself
        
        logger.debug(f"Initiated linearizable read: {request}")
        return request
    
    def process_read_index(self, request_id: str, read_index: int, term: int) -> bool:
        """
        Process read index acquisition.
        
        Called when leader determines it can serve the read.
        
        Args:
            request_id: Request identifier
            read_index: Index that must be applied before read
            term: Current term
            
        Returns:
            True if processing succeeded
        """
        if request_id not in self.pending_reads:
            logger.warning(f"Read request not found: {request_id}")
            return False
        
        request = self.pending_reads[request_id]
        
        if request.is_timed_out():
            logger.warning(f"Read request timed out: {request_id}")
            self.pending_reads.pop(request_id)
            return False
        
        request.read_index = read_index
        request.phase = ReadPhase.READ_INDEX_ACQUIRED
        request.current_term = term
        
        logger.debug(f"Read index acquired: {request_id} -> index {read_index}")
        return True
    
    def send_heartbeat_for_read(self, request_id: str) -> bool:
        """
        Prepare to send heartbeat to confirm read safety.
        
        Leader sends heartbeat before serving read to ensure:
        1. It's still the leader
        2. All previous entries are committed
        
        Args:
            request_id: Request identifier
            
        Returns:
            True if heartbeat should be sent
        """
        if request_id not in self.pending_reads:
            logger.warning(f"Read request not found: {request_id}")
            return False
        
        request = self.pending_reads[request_id]
        
        if request.is_timed_out():
            logger.warning(f"Read request timed out: {request_id}")
            self.pending_reads.pop(request_id)
            return False
        
        request.phase = ReadPhase.HEARTBEAT_SENT
        logger.debug(f"Heartbeat phase started for read: {request_id}")
        return True
    
    def record_heartbeat_ack(self, request_id: str, replica_id: str) -> bool:
        """
        Record heartbeat ACK from a replica.
        
        Args:
            request_id: Request identifier
            replica_id: ID of replying replica
            
        Returns:
            True if quorum is now satisfied
        """
        if request_id not in self.pending_reads:
            logger.debug(f"Read request not found: {request_id}")
            return False
        
        request = self.pending_reads[request_id]
        
        if request.is_timed_out():
            logger.warning(f"Read request timed out: {request_id}")
            self.pending_reads.pop(request_id)
            return False
        
        ack_set = self.replica_ack_set.get(request_id, set())
        ack_set.add(replica_id)
        self.replica_ack_set[request_id] = ack_set
        
        logger.debug(
            f"Heartbeat ACK recorded: {request_id} from {replica_id} "
            f"({len(ack_set)}/{self.quorum_size})"
        )
        
        # Check if quorum is satisfied
        if len(ack_set) >= self.quorum_size:
            request.phase = ReadPhase.HEARTBEAT_ACK_RECEIVED
            request.replicas_acked = ack_set.copy()
            logger.debug(f"Quorum satisfied for read: {request_id}")
            return True
        
        return False
    
    def wait_for_applied(self, request_id: str, applied_index: int) -> bool:
        """
        Check if read can be applied.
        
        Read can proceed once all entries up to read_index are applied.
        
        Args:
            request_id: Request identifier
            applied_index: Current applied index in state machine
            
        Returns:
            True if read can proceed
        """
        if request_id not in self.pending_reads:
            return False
        
        request = self.pending_reads[request_id]
        
        if request.is_timed_out():
            logger.warning(f"Read request timed out: {request_id}")
            self.pending_reads.pop(request_id)
            return False
        
        if applied_index >= request.read_index:
            request.phase = ReadPhase.APPLIED
            logger.debug(
                f"Read entries applied: {request_id} "
                f"(read_index={request.read_index}, applied={applied_index})"
            )
            return True
        
        logger.debug(
            f"Waiting for read entries: {request_id} "
            f"(need={request.read_index}, current={applied_index})"
        )
        return False
    
    def complete_read(self, request_id: str, result: Any) -> bool:
        """
        Complete a read request with result.
        
        Args:
            request_id: Request identifier
            result: Read result
            
        Returns:
            True if completion succeeded
        """
        if request_id not in self.pending_reads:
            logger.warning(f"Read request not found: {request_id}")
            return False
        
        request = self.pending_reads.pop(request_id)
        request.phase = ReadPhase.COMPLETED
        request.result = result
        
        self.completed_reads.append(request)
        self.replica_ack_set.pop(request_id, None)
        
        logger.debug(f"Read completed: {request_id}")
        return True
    
    def fail_read(self, request_id: str, error: str) -> bool:
        """
        Fail a read request with error.
        
        Args:
            request_id: Request identifier
            error: Error message
            
        Returns:
            True if failure was recorded
        """
        if request_id not in self.pending_reads:
            logger.warning(f"Read request not found: {request_id}")
            return False
        
        request = self.pending_reads.pop(request_id)
        request.error = error
        
        self.completed_reads.append(request)
        self.replica_ack_set.pop(request_id, None)
        
        logger.warning(f"Read failed: {request_id} - {error}")
        return True
    
    def update_commit_index(self, new_index: int, term: int) -> None:
        """
        Update committed index.
        
        Args:
            new_index: New committed index
            term: Current term
        """
        if new_index > self.committed_index:
            self.committed_index = new_index
            self.current_term = term
            logger.debug(f"Commit index updated: {new_index}")
    
    def update_applied_index(self, new_index: int) -> None:
        """
        Update applied index.
        
        Args:
            new_index: New applied index
        """
        if new_index > self.applied_index:
            self.applied_index = new_index
            logger.debug(f"Applied index updated: {new_index}")
    
    def get_pending_reads(self) -> List[LinearizableReadRequest]:
        """Get list of pending read requests."""
        return list(self.pending_reads.values())
    
    def get_timed_out_reads(self) -> List[LinearizableReadRequest]:
        """Get list of timed out reads."""
        timed_out = []
        for request_id, request in list(self.pending_reads.items()):
            if request.is_timed_out():
                timed_out.append(request)
        return timed_out
    
    def cleanup_timed_out_reads(self) -> int:
        """
        Clean up timed out read requests.
        
        Returns:
            Number of cleaned up requests
        """
        timed_out = self.get_timed_out_reads()
        count = 0
        
        for request in timed_out:
            self.fail_read(request.request_id, "Timeout")
            count += 1
        
        return count
    
    def get_status(self) -> Dict[str, Any]:
        """Get handler status."""
        return {
            "node_id": self.node_id,
            "cluster_size": self.cluster_size,
            "quorum_size": self.quorum_size,
            "committed_index": self.committed_index,
            "applied_index": self.applied_index,
            "current_term": self.current_term,
            "pending_reads": len(self.pending_reads),
            "completed_reads": len(self.completed_reads)
        }
    
    def __repr__(self) -> str:
        return (
            f"LinearizableReadHandler({self.node_id}, "
            f"pending={len(self.pending_reads)}, "
            f"completed={len(self.completed_reads)})"
        )
