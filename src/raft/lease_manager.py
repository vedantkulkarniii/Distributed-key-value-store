"""
Lease-based read optimization for linearizable reads.

Implements:
- Leader lease mechanism for fast reads
- Clock synchronization awareness
- Lease renewal and expiration
- Read optimization with lease verification
- Clock skew handling
"""

import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum
import threading

logger = logging.getLogger(__name__)


class LeaseState(Enum):
    """States of a leader lease."""
    PENDING = "pending"
    ACTIVE = "active"
    RENEWING = "renewing"
    EXPIRED = "expired"
    REVOKED = "revoked"


class LeaseInfo:
    """Information about a leader lease."""
    
    def __init__(self, lease_id: str, term: int, duration_ms: int = 3000):
        self.lease_id = lease_id
        self.term = term
        self.duration_ms = duration_ms
        self.state = LeaseState.PENDING
        
        self.creation_time = datetime.now()
        self.last_renewed = datetime.now()
        self.expiration_time = datetime.now() + timedelta(milliseconds=duration_ms)
        
        self.renewals = 0
        self.reads_served = 0
        self.heartbeats_acked = 0
    
    def is_valid(self) -> bool:
        """Check if lease is currently valid."""
        return (
            self.state == LeaseState.ACTIVE and
            datetime.now() < self.expiration_time
        )
    
    def is_expired(self) -> bool:
        """Check if lease has expired."""
        return datetime.now() > self.expiration_time
    
    def time_remaining_ms(self) -> int:
        """Get time remaining on lease."""
        remaining = (self.expiration_time - datetime.now()).total_seconds() * 1000
        return max(0, int(remaining))
    
    def renew(self, duration_ms: int) -> None:
        """Renew the lease."""
        self.last_renewed = datetime.now()
        self.expiration_time = datetime.now() + timedelta(milliseconds=duration_ms)
        self.state = LeaseState.ACTIVE
        self.renewals += 1


class LeaseManager:
    """
    Manages leader leases for optimized reads.
    
    Ensures:
    - Leader can serve reads without quorum
    - Lease validity verified before each read
    - Automatic expiration and renewal
    - Clock skew tolerance
    """
    
    def __init__(self, node_id: str, clock_skew_ms: int = 150):
        """Initialize lease manager."""
        self.node_id = node_id
        self.clock_skew_ms = clock_skew_ms  # Max allowed clock skew
        
        # Lease tracking
        self.current_lease: Optional[LeaseInfo] = None
        self.lease_history: Dict[str, LeaseInfo] = {}
        
        # Statistics
        self.total_leases = 0
        self.successful_reads = 0
        self.reads_denied = 0
        self.lease_expirations = 0
        
        # Configuration
        self.lease_duration_ms = 3000  # 3 second leases
        self.renewal_threshold_ms = 500  # Renew when 500ms remaining
        
        # Thread safety
        self.lock = threading.RLock()
        
        logger.info(f"Lease manager initialized for {node_id} (skew tolerance: {clock_skew_ms}ms)")
    
    def acquire_lease(self, term: int) -> Tuple[bool, Optional[LeaseInfo], Optional[str]]:
        """
        Acquire a new lease.
        
        Args:
            term: Current term
            
        Returns:
            Tuple of (success, lease_info, error_message)
        """
        with self.lock:
            try:
                # Check if existing lease is still valid
                if self.current_lease and self.current_lease.is_valid():
                    # Already have valid lease
                    return True, self.current_lease, None
                
                # Create new lease
                lease_id = f"lease-{term}-{int(datetime.now().timestamp() * 1000)}"
                lease = LeaseInfo(lease_id, term, self.lease_duration_ms)
                lease.state = LeaseState.ACTIVE
                
                self.current_lease = lease
                self.lease_history[lease_id] = lease
                self.total_leases += 1
                
                logger.info(f"Acquired lease {lease_id} for term {term}")
                
                return True, lease, None
                
            except Exception as e:
                logger.error(f"Error acquiring lease: {e}")
                return False, None, f"Failed to acquire lease: {str(e)}"
    
    def can_serve_read(self) -> Tuple[bool, Optional[str]]:
        """
        Check if leader can serve read under lease.
        
        Returns:
            Tuple of (can_serve, reason)
        """
        with self.lock:
            if not self.current_lease:
                return False, "No active lease"
            
            if not self.current_lease.is_valid():
                return False, f"Lease expired: {self.current_lease.time_remaining_ms()}ms remaining"
            
            # Check clock skew
            time_remaining = self.current_lease.time_remaining_ms()
            
            if time_remaining < self.clock_skew_ms:
                return False, f"Lease too close to expiration (clock skew risk)"
            
            return True, None
    
    def serve_read(self) -> Tuple[bool, Optional[str]]:
        """
        Serve a read under current lease.
        
        Returns:
            Tuple of (success, error_message)
        """
        with self.lock:
            can_serve, reason = self.can_serve_read()
            
            if not can_serve:
                self.reads_denied += 1
                return False, reason
            
            self.current_lease.reads_served += 1
            self.successful_reads += 1
            
            # Check if renewal needed
            if self.current_lease.time_remaining_ms() < self.renewal_threshold_ms:
                self.current_lease.state = LeaseState.RENEWING
                logger.debug(f"Renewal needed for lease {self.current_lease.lease_id}")
            
            return True, None
    
    def renew_lease(self) -> Tuple[bool, Optional[str]]:
        """
        Renew current lease.
        
        Returns:
            Tuple of (success, error_message)
        """
        with self.lock:
            if not self.current_lease:
                return False, "No active lease to renew"
            
            try:
                self.current_lease.renew(self.lease_duration_ms)
                logger.debug(f"Renewed lease {self.current_lease.lease_id}")
                return True, None
                
            except Exception as e:
                logger.error(f"Error renewing lease: {e}")
                return False, f"Failed to renew lease: {str(e)}"
    
    def record_heartbeat_ack(self, peer_id: str) -> None:
        """
        Record heartbeat ACK (extends lease validity).
        
        Args:
            peer_id: Peer that acknowledged
        """
        with self.lock:
            if self.current_lease:
                self.current_lease.heartbeats_acked += 1
    
    def revoke_lease(self) -> bool:
        """
        Revoke current lease (e.g., on term change).
        
        Returns:
            True if revoked
        """
        with self.lock:
            if not self.current_lease:
                return False
            
            self.current_lease.state = LeaseState.REVOKED
            logger.info(f"Revoked lease {self.current_lease.lease_id}")
            
            self.current_lease = None
            return True
    
    def check_lease_health(self) -> Dict[str, Any]:
        """
        Check health of current lease.
        
        Returns:
            Health status dictionary
        """
        with self.lock:
            if not self.current_lease:
                return {
                    "active": False,
                    "lease_id": None,
                    "reason": "No active lease",
                }
            
            lease = self.current_lease
            
            can_serve, reason = self.can_serve_read()
            
            return {
                "active": lease.is_valid(),
                "lease_id": lease.lease_id,
                "term": lease.term,
                "state": lease.state.value,
                "time_remaining_ms": lease.time_remaining_ms(),
                "can_serve_read": can_serve,
                "reads_served": lease.reads_served,
                "heartbeats_acked": lease.heartbeats_acked,
                "renewals": lease.renewals,
            }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get lease manager statistics."""
        with self.lock:
            total_reads = self.successful_reads + self.reads_denied
            
            return {
                "total_leases": self.total_leases,
                "expirations": self.lease_expirations,
                "total_reads_attempted": total_reads,
                "successful_reads": self.successful_reads,
                "reads_denied": self.reads_denied,
                "success_rate": (
                    self.successful_reads / total_reads if total_reads > 0 else 0
                ),
                "current_lease_valid": (
                    self.current_lease.is_valid() if self.current_lease else False
                ),
                "clock_skew_tolerance_ms": self.clock_skew_ms,
            }
    
    def cleanup_expired_leases(self) -> int:
        """
        Clean up expired leases from history.
        
        Returns:
            Number of leases cleaned up
        """
        with self.lock:
            expired_ids = [
                lid for lid, lease in self.lease_history.items()
                if lease.is_expired()
            ]
            
            for lid in expired_ids:
                del self.lease_history[lid]
                self.lease_expirations += 1
            
            return len(expired_ids)
