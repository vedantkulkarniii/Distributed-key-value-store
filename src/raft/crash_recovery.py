"""
Crash recovery mechanism for Raft state machine.

Implements:
- Recovery from snapshots
- WAL replay after crash
- State machine consistency verification
- Idempotent recovery operations
- Recovery progress tracking
"""

import logging
import json
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class RecoveryPhase(Enum):
    """Phases of crash recovery."""
    INITIALIZING = "initializing"
    LOADING_SNAPSHOT = "loading_snapshot"
    REPLAYING_LOG = "replaying_log"
    VERIFYING_STATE = "verifying_state"
    COMPLETE = "complete"


@dataclass
class RecoveryCheckpoint:
    """Checkpoint during recovery."""
    
    phase: RecoveryPhase
    timestamp: str
    entries_replayed: int = 0
    entries_skipped: int = 0
    errors_encountered: int = 0
    last_applied_index: int = 0
    state_hash: Optional[str] = None


class CrashRecoveryManager:
    """
    Manages crash recovery for Raft state machine.
    
    Ensures:
    - Complete state restoration after crash
    - Consistency between snapshots and logs
    - Idempotent recovery
    - Recovery durability
    """
    
    def __init__(self, node_id: str, snapshot_manager, wal_manager):
        """
        Initialize crash recovery manager.
        
        Args:
            node_id: Node identifier
            snapshot_manager: SnapshotPersistence instance
            wal_manager: WAL manager instance
        """
        self.node_id = node_id
        self.snapshot_manager = snapshot_manager
        self.wal_manager = wal_manager
        
        # Recovery tracking
        self.recovery_in_progress = False
        self.last_recovery_time: Optional[datetime] = None
        self.recovery_phase = RecoveryPhase.INITIALIZING
        self.recovery_checkpoints: List[RecoveryCheckpoint] = []
        
        # Statistics
        self.total_recoveries = 0
        self.successful_recoveries = 0
        self.failed_recoveries = 0
        self.total_entries_replayed = 0
        self.total_entries_skipped = 0
        self.total_errors = 0
        
        logger.info(f"Crash recovery manager initialized for {node_id}")
    
    def begin_recovery(self) -> Tuple[bool, Optional[str]]:
        """
        Begin crash recovery process.
        
        Returns:
            Tuple of (success, error_message)
        """
        if self.recovery_in_progress:
            return False, "Recovery already in progress"
        
        self.recovery_in_progress = True
        self.recovery_phase = RecoveryPhase.INITIALIZING
        self.recovery_checkpoints = []
        
        logger.info(f"Beginning crash recovery for {self.node_id}")
        
        return True, None
    
    def recover_from_snapshot(
        self,
        state_machine_data: Dict[str, Any],
    ) -> Tuple[bool, Optional[str], int, int]:
        """
        Recover state machine from latest snapshot.
        
        Args:
            state_machine_data: State machine data dict to populate
            
        Returns:
            Tuple of (success, error_message, last_index, last_term)
        """
        if not self.recovery_in_progress:
            return False, "Recovery not started", 0, 0
        
        self.recovery_phase = RecoveryPhase.LOADING_SNAPSHOT
        
        try:
            # Get latest snapshot
            success, snapshot_data, last_index, last_term = \
                self.snapshot_manager.get_latest_snapshot_data()
            
            if not success:
                logger.info("No snapshot found, starting with empty state")
                return True, None, 0, 0
            
            # Restore state
            state_machine_data.clear()
            state_machine_data.update(snapshot_data)
            
            # Record checkpoint
            checkpoint = RecoveryCheckpoint(
                phase=RecoveryPhase.LOADING_SNAPSHOT,
                timestamp=datetime.now().isoformat(),
                last_applied_index=last_index,
            )
            self.recovery_checkpoints.append(checkpoint)
            
            logger.info(
                f"Restored snapshot: index={last_index}, term={last_term}, "
                f"keys={len(snapshot_data)}"
            )
            
            return True, None, last_index, last_term
            
        except Exception as e:
            logger.error(f"Snapshot recovery failed: {e}")
            self.total_errors += 1
            return False, f"Snapshot recovery failed: {str(e)}", 0, 0
    
    def replay_wal_entries(
        self,
        state_machine_data: Dict[str, Any],
        from_index: int,
        state_machine: Any,
    ) -> Tuple[bool, Optional[str], int]:
        """
        Replay WAL entries after snapshot recovery.
        
        Args:
            state_machine_data: State machine data dict
            from_index: Start replaying from this index
            state_machine: StateMachineEngine instance
            
        Returns:
            Tuple of (success, error_message, entries_applied)
        """
        if not self.recovery_in_progress:
            return False, "Recovery not started", 0
        
        self.recovery_phase = RecoveryPhase.REPLAYING_LOG
        entries_applied = 0
        entries_skipped = 0
        errors = 0
        
        try:
            # Get all WAL entries
            wal_entries = self.wal_manager.get_all_entries()
            
            for index, entry in enumerate(wal_entries):
                try:
                    entry_index = entry.get("index")
                    
                    # Skip entries before recovery point
                    if entry_index <= from_index:
                        entries_skipped += 1
                        continue
                    
                    # Apply entry
                    term = entry.get("term")
                    command = entry.get("command")
                    
                    if command:
                        # Apply using state machine
                        state_machine.apply_command(entry_index, term, command)
                        entries_applied += 1
                    
                except Exception as e:
                    logger.warning(f"Failed to replay entry {index}: {e}")
                    errors += 1
                    self.total_errors += 1
            
            # Record checkpoint
            checkpoint = RecoveryCheckpoint(
                phase=RecoveryPhase.REPLAYING_LOG,
                timestamp=datetime.now().isoformat(),
                entries_replayed=entries_applied,
                entries_skipped=entries_skipped,
                errors_encountered=errors,
                last_applied_index=from_index + entries_applied,
            )
            self.recovery_checkpoints.append(checkpoint)
            
            self.total_entries_replayed += entries_applied
            self.total_entries_skipped += entries_skipped
            
            logger.info(
                f"WAL replay complete: applied={entries_applied}, "
                f"skipped={entries_skipped}, errors={errors}"
            )
            
            return True, None, entries_applied
            
        except Exception as e:
            logger.error(f"WAL replay failed: {e}")
            self.total_errors += 1
            return False, f"WAL replay failed: {str(e)}", entries_applied
    
    def verify_state_consistency(
        self,
        state_machine_data: Dict[str, Any],
        expected_keys: Optional[set] = None,
    ) -> Tuple[bool, Optional[str], Dict]:
        """
        Verify state machine consistency after recovery.
        
        Args:
            state_machine_data: Recovered state machine data
            expected_keys: Optional set of keys that should exist
            
        Returns:
            Tuple of (success, error_message, verification_results)
        """
        if not self.recovery_in_progress:
            return False, "Recovery not started", {}
        
        self.recovery_phase = RecoveryPhase.VERIFYING_STATE
        
        verification_results = {
            "total_keys": len(state_machine_data),
            "has_null_values": False,
            "null_value_count": 0,
            "missing_expected_keys": [],
            "extra_keys": [],
            "data_size_bytes": 0,
        }
        
        try:
            # Check for null values
            null_count = 0
            for key, value in state_machine_data.items():
                if value is None:
                    null_count += 1
            
            verification_results["null_value_count"] = null_count
            verification_results["has_null_values"] = null_count > 0
            
            # Check expected keys
            if expected_keys:
                actual_keys = set(state_machine_data.keys())
                missing = expected_keys - actual_keys
                extra = actual_keys - expected_keys
                
                verification_results["missing_expected_keys"] = list(missing)
                verification_results["extra_keys"] = list(extra)
                
                if missing:
                    logger.warning(f"Missing expected keys: {missing}")
            
            # Estimate data size
            data_json = json.dumps(state_machine_data)
            verification_results["data_size_bytes"] = len(data_json.encode('utf-8'))
            
            # Record checkpoint
            checkpoint = RecoveryCheckpoint(
                phase=RecoveryPhase.VERIFYING_STATE,
                timestamp=datetime.now().isoformat(),
            )
            self.recovery_checkpoints.append(checkpoint)
            
            logger.info(
                f"State verification complete: keys={verification_results['total_keys']}, "
                f"size={verification_results['data_size_bytes']} bytes"
            )
            
            return True, None, verification_results
            
        except Exception as e:
            logger.error(f"State verification failed: {e}")
            self.total_errors += 1
            return False, f"Verification failed: {str(e)}", verification_results
    
    def complete_recovery(self) -> Tuple[bool, Optional[str], Dict]:
        """
        Complete recovery process.
        
        Returns:
            Tuple of (success, error_message, recovery_stats)
        """
        if not self.recovery_in_progress:
            return False, "Recovery not in progress", {}
        
        self.recovery_phase = RecoveryPhase.COMPLETE
        self.recovery_in_progress = False
        self.last_recovery_time = datetime.now()
        self.total_recoveries += 1
        self.successful_recoveries += 1
        
        # Compile recovery statistics
        recovery_stats = {
            "total_recoveries": self.total_recoveries,
            "successful_recoveries": self.successful_recoveries,
            "failed_recoveries": self.failed_recoveries,
            "total_entries_replayed": self.total_entries_replayed,
            "total_entries_skipped": self.total_entries_skipped,
            "total_errors": self.total_errors,
            "last_recovery_time": self.last_recovery_time.isoformat(),
            "checkpoint_count": len(self.recovery_checkpoints),
        }
        
        logger.info(f"Crash recovery complete for {self.node_id}")
        
        return True, None, recovery_stats
    
    def abort_recovery(self, reason: str) -> Tuple[bool, Optional[str]]:
        """
        Abort recovery process.
        
        Args:
            reason: Reason for abort
            
        Returns:
            Tuple of (success, error_message)
        """
        if not self.recovery_in_progress:
            return False, "Recovery not in progress"
        
        self.recovery_in_progress = False
        self.total_recoveries += 1
        self.failed_recoveries += 1
        
        logger.warning(f"Recovery aborted: {reason}")
        
        return True, None
    
    def get_recovery_progress(self) -> Dict:
        """
        Get current recovery progress.
        
        Returns:
            Dictionary with recovery progress
        """
        return {
            "in_progress": self.recovery_in_progress,
            "phase": self.recovery_phase.value,
            "checkpoint_count": len(self.recovery_checkpoints),
            "total_recoveries": self.total_recoveries,
            "successful_recoveries": self.successful_recoveries,
            "failed_recoveries": self.failed_recoveries,
            "entries_replayed": self.total_entries_replayed,
            "last_recovery_time": (
                self.last_recovery_time.isoformat()
                if self.last_recovery_time else None
            ),
        }
    
    def get_recovery_checkpoints(self) -> List[Dict]:
        """Get all recovery checkpoints."""
        return [
            {
                "phase": cp.phase.value,
                "timestamp": cp.timestamp,
                "entries_replayed": cp.entries_replayed,
                "entries_skipped": cp.entries_skipped,
                "errors": cp.errors_encountered,
                "last_applied_index": cp.last_applied_index,
            }
            for cp in self.recovery_checkpoints
        ]
    
    def perform_full_recovery(
        self,
        state_machine_data: Dict[str, Any],
        state_machine: Any,
    ) -> Tuple[bool, Optional[str], Dict]:
        """
        Perform complete crash recovery in one call.
        
        Args:
            state_machine_data: State machine data dict
            state_machine: StateMachineEngine instance
            
        Returns:
            Tuple of (success, error_message, recovery_results)
        """
        # Begin recovery
        begin_ok, begin_err = self.begin_recovery()
        if not begin_ok:
            return False, begin_err, {}
        
        results = {}
        
        try:
            # Step 1: Recover from snapshot
            snap_ok, snap_err, last_index, last_term = self.recover_from_snapshot(
                state_machine_data
            )
            
            if not snap_ok:
                self.abort_recovery(snap_err or "Snapshot recovery failed")
                return False, snap_err, {}
            
            results["snapshot_recovery"] = {
                "success": snap_ok,
                "last_index": last_index,
                "last_term": last_term,
            }
            
            # Step 2: Replay WAL entries
            wal_ok, wal_err, entries_applied = self.replay_wal_entries(
                state_machine_data, last_index, state_machine
            )
            
            if not wal_ok:
                self.abort_recovery(wal_err or "WAL replay failed")
                return False, wal_err, results
            
            results["wal_replay"] = {
                "success": wal_ok,
                "entries_applied": entries_applied,
            }
            
            # Step 3: Verify consistency
            verify_ok, verify_err, verify_results = self.verify_state_consistency(
                state_machine_data
            )
            
            if not verify_ok:
                self.abort_recovery(verify_err or "Verification failed")
                return False, verify_err, results
            
            results["verification"] = verify_results
            
            # Step 4: Complete recovery
            complete_ok, complete_err, recovery_stats = self.complete_recovery()
            
            if not complete_ok:
                return False, complete_err, results
            
            results["recovery_stats"] = recovery_stats
            
            return True, None, results
            
        except Exception as e:
            self.abort_recovery(str(e))
            logger.error(f"Full recovery failed: {e}")
            return False, f"Recovery failed: {str(e)}", results
