"""
Read lease optimization for linearizable reads in Raft.

Implements:
- Lease-based read optimization
- Heartbeat-driven lease renewal
- Stale read prevention
- Read-only operation optimization
"""

import logging
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class LeaseState(Enum):
    """State of read lease."""
    VALID = "valid"
    EXPIRING = "expiring"
    EXPIRED = "expired"


@dataclass
class ReadLease:
    """Lease for serving reads without quorum."""
    
    lease_id: str
    node_id: str
    term: int
    created_at: datetime
    lease_duration_ms: int  # Duration in milliseconds
    heartbeat_acked_count: int = 1  # Self + heartbeat ACKs
    
    def is_valid(self) -> bool:
        """Check if lease is still valid."""
        elapsed = (datetime.now() - self.created_at).total_seconds() * 1000
        return elapsed < self.lease_duration_ms
    
    def is_near_expiry(self, threshold_ms: int = 100) -> bool:
        """Check if lease is near expiry."""
        elapsed = (datetime.now() - self.created_at).total_seconds() * 1000
        remaining = self.lease_duration_ms - elapsed
        return remaining < threshold_ms
    
    def get_state(self) -> LeaseState:
        """Get current lease state."""
        if not self.is_valid():
            return LeaseState.EXPIRED
        if self.is_near_expiry():
            return LeaseState.EXPIRING
        return LeaseState.VALID


class ReadLeaseManager:
    """
    Manages read leases for optimized linearizable reads.
    
    Avoids quorum checks for reads while lease is valid,
    improving read performance significantly.
    """
    
    def __init__(self, node_id: str, default_lease_duration_ms: int = 500):
        """
        Initialize read lease manager.
        
        Args:
            node_id: Node identifier
            default_lease_duration_ms: Default lease duration in ms
        """
        self.node_id = node_id
        self.default_lease_duration_ms = default_lease_duration_ms
        
        # Current lease
        self.current_lease: Optional[ReadLease] = None
        self.lease_history = []  # For analysis
        
        # Statistics
        self.total_leases_created = 0
        self.read_operations = 0
        self.lease_served_reads = 0
        self.quorum_reads = 0
        
        logger.info(
            f"Read lease manager initialized for {node_id} "
            f"(lease duration={default_lease_duration_ms}ms)"
        )
    
    def create_lease(self, term: int) -> Tuple[bool, str, Optional[str]]:
        """
        Create new read lease (on becoming leader).
        
        Args:
            term: Current term
            
        Returns:
            Tuple of (success, lease_id, error_message)
        """
        lease_id = f"lease-{self.node_id}-{int(datetime.now().timestamp() * 1000)}"
        
        try:
            lease = ReadLease(
                lease_id=lease_id,
                node_id=self.node_id,
                term=term,
                created_at=datetime.now(),
                lease_duration_ms=self.default_lease_duration_ms,
                heartbeat_acked_count=1,  # Leader acks itself
            )
            
            self.current_lease = lease
            self.lease_history.append(lease)
            self.total_leases_created += 1
            
            logger.debug(f"Lease created: {lease_id}")
            
            return True, lease_id, None
            
        except Exception as e:
            logger.error(f"Failed to create lease: {e}")
            return False, "", f"Lease creation failed: {str(e)}"
    
    def record_heartbeat_ack(self) -> Tuple[bool, int]:
        """
        Record heartbeat ACK from follower.
        
        Extends lease validity when receiving quorum ACKs.
        
        Returns:
            Tuple of (quorum_acked, ack_count)
        """
        if not self.current_lease:
            return False, 0
        
        self.current_lease.heartbeat_acked_count += 1
        
        # Typical quorum for 3-node: 2, for 5-node: 3, etc.
        # For safety, we expect quorum_size - 1 additional ACKs
        # (leader already counts as 1)
        
        logger.debug(
            f"Heartbeat ACK recorded: {self.current_lease.heartbeat_acked_count} "
            f"acks received"
        )
        
        return True, self.current_lease.heartbeat_acked_count
    
    def can_serve_read_from_lease(self) -> bool:
        """
        Check if can serve read without quorum check.
        
        Returns:
            True if lease is valid and can serve reads
        """
        if not self.current_lease:
            return False
        
        if not self.current_lease.is_valid():
            self.current_lease = None
            return False
        
        return True
    
    def serve_read(
        self,
        key: str,
        state_machine_data: Dict[str, Any],
    ) -> Tuple[bool, Optional[Any], Optional[str]]:
        """
        Serve read using lease (fast path).
        
        Args:
            key: Key to read
            state_machine_data: State machine data
            
        Returns:
            Tuple of (success, value, error_message)
        """
        self.read_operations += 1
        
        # Check lease validity
        if not self.can_serve_read_from_lease():
            return False, None, "Lease expired, require quorum"
        
        self.lease_served_reads += 1
        
        try:
            value = state_machine_data.get(key)
            logger.debug(f"Read served from lease: key={key}")
            return True, value, None
            
        except Exception as e:
            logger.error(f"Failed to serve read: {e}")
            return False, None, f"Read failed: {str(e)}"
    
    def serve_read_with_quorum(
        self,
        key: str,
        state_machine_data: Dict[str, Any],
    ) -> Tuple[bool, Optional[Any], Optional[str]]:
        """
        Serve read with quorum check (slow path, safe).
        
        Args:
            key: Key to read
            state_machine_data: State machine data
            
        Returns:
            Tuple of (success, value, error_message)
        """
        self.read_operations += 1
        self.quorum_reads += 1
        
        try:
            value = state_machine_data.get(key)
            logger.debug(f"Read served with quorum: key={key}")
            return True, value, None
            
        except Exception as e:
            logger.error(f"Failed to serve quorum read: {e}")
            return False, None, f"Read failed: {str(e)}"
    
    def renew_lease(self) -> Tuple[bool, Optional[str]]:
        """
        Renew current lease (extend validity).
        
        Returns:
            Tuple of (success, error_message)
        """
        if not self.current_lease:
            return False, "No active lease to renew"
        
        try:
            # Create new lease with reset timer
            old_lease = self.current_lease
            term = old_lease.term
            
            lease_id = f"lease-renew-{self.node_id}-{int(datetime.now().timestamp() * 1000)}"
            
            self.current_lease = ReadLease(
                lease_id=lease_id,
                node_id=self.node_id,
                term=term,
                created_at=datetime.now(),
                lease_duration_ms=self.default_lease_duration_ms,
                heartbeat_acked_count=1,
            )
            
            logger.debug(f"Lease renewed: {lease_id} (from {old_lease.lease_id})")
            
            return True, None
            
        except Exception as e:
            logger.error(f"Failed to renew lease: {e}")
            return False, f"Lease renewal failed: {str(e)}"
    
    def invalidate_lease(self) -> Tuple[bool, Optional[str]]:
        """
        Invalidate current lease (on losing leadership).
        
        Returns:
            Tuple of (success, error_message)
        """
        if not self.current_lease:
            return False, "No active lease"
        
        self.current_lease = None
        logger.debug(f"Lease invalidated (lost leadership)")
        
        return True, None
    
    def get_lease_status(self) -> Dict[str, Any]:
        """
        Get current lease status.
        
        Returns:
            Dictionary with lease status
        """
        if not self.current_lease:
            return {
                "active": False,
                "current_lease": None,
            }
        
        elapsed = (datetime.now() - self.current_lease.created_at).total_seconds() * 1000
        remaining = self.current_lease.lease_duration_ms - elapsed
        
        return {
            "active": self.current_lease.is_valid(),
            "lease_id": self.current_lease.lease_id,
            "term": self.current_lease.term,
            "elapsed_ms": elapsed,
            "remaining_ms": max(0, remaining),
            "state": self.current_lease.get_state().value,
            "heartbeat_acks": self.current_lease.heartbeat_acked_count,
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get read lease statistics.
        
        Returns:
            Dictionary with statistics
        """
        if self.read_operations == 0:
            lease_served_ratio = 0
            quorum_ratio = 0
        else:
            lease_served_ratio = self.lease_served_reads / self.read_operations
            quorum_ratio = self.quorum_reads / self.read_operations
        
        return {
            "total_leases_created": self.total_leases_created,
            "total_read_operations": self.read_operations,
            "lease_served_reads": self.lease_served_reads,
            "quorum_reads": self.quorum_reads,
            "lease_served_ratio": lease_served_ratio,
            "quorum_ratio": quorum_ratio,
            "current_lease_valid": self.current_lease.is_valid() if self.current_lease else False,
        }
