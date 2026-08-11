"""
Multi-node state synchronization for cluster consistency.

Implements:
- State sync between leader and followers
- Incremental sync protocol
- Consistency verification
- Sync progress tracking
- Conflict resolution
"""

import logging
from typing import Dict, Any, List, Optional, Tuple, Set
from datetime import datetime
from enum import Enum
import threading

logger = logging.getLogger(__name__)


class SyncPhase(Enum):
    """Phases of state synchronization."""
    INITIATED = "initiated"
    METADATA_EXCHANGE = "metadata_exchange"
    SNAPSHOT_TRANSFER = "snapshot_transfer"
    LOG_SYNC = "log_sync"
    VERIFICATION = "verification"
    COMPLETED = "completed"
    FAILED = "failed"


class SyncProgress:
    """Tracks progress of a sync operation."""
    
    def __init__(self, node_id: str, peer_id: str):
        self.node_id = node_id
        self.peer_id = peer_id
        self.phase = SyncPhase.INITIATED
        self.start_time = datetime.now()
        self.end_time: Optional[datetime] = None
        
        # Progress metrics
        self.entries_synced = 0
        self.entries_total = 0
        self.bytes_transferred = 0
        self.conflicts_detected = 0
        self.conflicts_resolved = 0
        
        # Status
        self.is_complete = False
        self.is_successful = False
        self.error: Optional[str] = None
    
    def duration_seconds(self) -> float:
        """Get sync duration."""
        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds()
    
    def progress_percent(self) -> float:
        """Get sync progress percentage."""
        if self.entries_total == 0:
            return 0.0
        return (self.entries_synced / self.entries_total) * 100
    
    def throughput_entries_per_sec(self) -> float:
        """Get throughput in entries per second."""
        duration = self.duration_seconds()
        if duration == 0:
            return 0.0
        return self.entries_synced / duration


class MultiNodeStateSyncManager:
    """
    Manages state synchronization across cluster.
    
    Ensures:
    - All nodes have consistent state
    - Efficient incremental sync
    - Rapid failure recovery
    - Conflict detection and resolution
    """
    
    def __init__(self, node_id: str, cluster_size: int):
        """Initialize state sync manager."""
        self.node_id = node_id
        self.cluster_size = cluster_size
        
        # Sync state tracking
        self.active_syncs: Dict[str, SyncProgress] = {}
        self.completed_syncs: List[SyncProgress] = []
        
        # Node state tracking
        self.peer_states: Dict[str, Dict[str, Any]] = {}
        self.peer_last_sync: Dict[str, datetime] = {}
        self.peer_consistency: Dict[str, float] = {}  # Consistency score 0-1
        
        # Sync statistics
        self.total_syncs = 0
        self.successful_syncs = 0
        self.failed_syncs = 0
        
        # Thread safety
        self.lock = threading.RLock()
        
        logger.info(f"State sync manager initialized for {node_id}")
    
    def initiate_sync(self, peer_id: str) -> SyncProgress:
        """
        Initiate sync with a peer.
        
        Args:
            peer_id: Peer node ID
            
        Returns:
            SyncProgress object
        """
        with self.lock:
            progress = SyncProgress(self.node_id, peer_id)
            self.active_syncs[peer_id] = progress
            self.total_syncs += 1
            
            logger.debug(f"Initiated sync with {peer_id}")
            
            return progress
    
    def update_sync_progress(
        self,
        peer_id: str,
        entries_synced: int,
        entries_total: int,
    ) -> bool:
        """
        Update sync progress.
        
        Args:
            peer_id: Peer node ID
            entries_synced: Number of entries synced
            entries_total: Total entries to sync
            
        Returns:
            True if sync is complete
        """
        with self.lock:
            if peer_id not in self.active_syncs:
                return False
            
            progress = self.active_syncs[peer_id]
            progress.entries_synced = entries_synced
            progress.entries_total = entries_total
            
            if entries_synced >= entries_total and entries_total > 0:
                logger.debug(f"Sync with {peer_id} complete: {entries_synced}/{entries_total}")
                return True
            
            return False
    
    def update_peer_state(
        self,
        peer_id: str,
        state: Dict[str, Any],
    ) -> None:
        """
        Update tracked state of peer.
        
        Args:
            peer_id: Peer node ID
            state: Current state of peer
        """
        with self.lock:
            self.peer_states[peer_id] = state.copy()
            self.peer_last_sync[peer_id] = datetime.now()
    
    def complete_sync(
        self,
        peer_id: str,
        is_successful: bool = True,
        error: Optional[str] = None,
    ) -> bool:
        """
        Mark sync as complete.
        
        Args:
            peer_id: Peer node ID
            is_successful: Whether sync succeeded
            error: Error message if failed
            
        Returns:
            True if sync was active
        """
        with self.lock:
            if peer_id not in self.active_syncs:
                return False
            
            progress = self.active_syncs.pop(peer_id)
            progress.end_time = datetime.now()
            progress.is_complete = True
            progress.is_successful = is_successful
            progress.error = error
            
            self.completed_syncs.append(progress)
            
            if is_successful:
                self.successful_syncs += 1
            else:
                self.failed_syncs += 1
            
            phase_name = "COMPLETED" if is_successful else "FAILED"
            progress.phase = SyncPhase.COMPLETED if is_successful else SyncPhase.FAILED
            
            logger.info(
                f"Sync with {peer_id} {phase_name}: "
                f"{progress.entries_synced} entries in {progress.duration_seconds():.2f}s"
            )
            
            return True
    
    def detect_conflicts(
        self,
        peer_id: str,
        local_state: Dict[str, Any],
        peer_state: Dict[str, Any],
    ) -> List[Tuple[str, Any, Any]]:
        """
        Detect conflicts between local and peer state.
        
        Args:
            peer_id: Peer node ID
            local_state: Local state
            peer_state: Peer state
            
        Returns:
            List of (key, local_value, peer_value) conflicts
        """
        with self.lock:
            conflicts = []
            
            # Check for keys with different values
            all_keys = set(local_state.keys()) | set(peer_state.keys())
            
            for key in all_keys:
                local_value = local_state.get(key)
                peer_value = peer_state.get(key)
                
                if local_value != peer_value:
                    conflicts.append((key, local_value, peer_value))
            
            if peer_id in self.active_syncs:
                self.active_syncs[peer_id].conflicts_detected = len(conflicts)
            
            logger.debug(f"Detected {len(conflicts)} conflicts with {peer_id}")
            
            return conflicts
    
    def resolve_conflicts(
        self,
        peer_id: str,
        conflicts: List[Tuple[str, Any, Any]],
        prefer_local: bool = False,
    ) -> Dict[str, Any]:
        """
        Resolve conflicts between states.
        
        Args:
            peer_id: Peer node ID
            conflicts: List of conflicts
            prefer_local: Whether to prefer local values
            
        Returns:
            Resolved state
        """
        with self.lock:
            resolved = {}
            
            for key, local_value, peer_value in conflicts:
                # Simple resolution: prefer local (leader)
                if prefer_local:
                    resolved[key] = local_value
                else:
                    # Otherwise prefer non-None value
                    resolved[key] = local_value if local_value is not None else peer_value
            
            if peer_id in self.active_syncs:
                self.active_syncs[peer_id].conflicts_resolved = len(resolved)
            
            logger.debug(f"Resolved {len(resolved)} conflicts with {peer_id}")
            
            return resolved
    
    def verify_consistency(
        self,
        peer_id: str,
        local_state: Dict[str, Any],
        peer_state: Dict[str, Any],
    ) -> Tuple[bool, float]:
        """
        Verify state consistency between nodes.
        
        Args:
            peer_id: Peer node ID
            local_state: Local state
            peer_state: Peer state
            
        Returns:
            Tuple of (is_consistent, consistency_score)
        """
        with self.lock:
            if not local_state and not peer_state:
                self.peer_consistency[peer_id] = 1.0
                return True, 1.0
            
            # Count matching keys
            total_keys = max(len(local_state), len(peer_state))
            if total_keys == 0:
                consistency_score = 1.0
            else:
                matching_keys = 0
                for key in local_state:
                    if key in peer_state and local_state[key] == peer_state[key]:
                        matching_keys += 1
                
                consistency_score = matching_keys / total_keys
            
            self.peer_consistency[peer_id] = consistency_score
            
            is_consistent = consistency_score > 0.95  # 95% consistency threshold
            
            logger.debug(
                f"Consistency with {peer_id}: {consistency_score:.2%} "
                f"(matching: {matching_keys}/{total_keys})"
            )
            
            return is_consistent, consistency_score
    
    def get_sync_progress(self, peer_id: str) -> Optional[Dict[str, Any]]:
        """Get current sync progress for peer."""
        with self.lock:
            if peer_id not in self.active_syncs:
                return None
            
            progress = self.active_syncs[peer_id]
            
            return {
                "peer_id": peer_id,
                "phase": progress.phase.value,
                "progress": f"{progress.entries_synced}/{progress.entries_total}",
                "percent": progress.progress_percent(),
                "duration": progress.duration_seconds(),
                "throughput": progress.throughput_entries_per_sec(),
                "conflicts": {
                    "detected": progress.conflicts_detected,
                    "resolved": progress.conflicts_resolved,
                },
            }
    
    def get_cluster_status(self) -> Dict[str, Any]:
        """Get overall cluster sync status."""
        with self.lock:
            return {
                "node_id": self.node_id,
                "active_syncs": len(self.active_syncs),
                "total_syncs": self.total_syncs,
                "successful": self.successful_syncs,
                "failed": self.failed_syncs,
                "success_rate": (
                    self.successful_syncs / self.total_syncs
                    if self.total_syncs > 0 else 0
                ),
                "peer_consistency": self.peer_consistency.copy(),
                "peers_in_sync": len(
                    {p for p, score in self.peer_consistency.items() if score > 0.95}
                ),
            }
    
    def get_peer_consistency(self, peer_id: str) -> Optional[float]:
        """Get consistency score for peer."""
        with self.lock:
            return self.peer_consistency.get(peer_id)
    
    def get_sync_history(self, peer_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get sync history."""
        with self.lock:
            syncs = self.completed_syncs
            
            if peer_id:
                syncs = [s for s in syncs if s.peer_id == peer_id]
            
            return [
                {
                    "peer_id": s.peer_id,
                    "duration": s.duration_seconds(),
                    "entries": s.entries_synced,
                    "successful": s.is_successful,
                    "error": s.error,
                    "timestamp": s.end_time.isoformat() if s.end_time else None,
                }
                for s in syncs
            ]
