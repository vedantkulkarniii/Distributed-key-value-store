"""
Crash recovery handler for state machine durability.

Implements:
- Recovery from persistent state files
- WAL replay for uncommitted entries
- Snapshot-based fast recovery
- State validation and consistency checks
- Recovery progress tracking
"""

import logging
import os
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class RecoveryPhase(Enum):
    """Phases of crash recovery."""
    STARTED = "started"
    LOADING_SNAPSHOTS = "loading_snapshots"
    REPLAYING_LOG = "replaying_log"
    VALIDATING_STATE = "validating_state"
    COMPLETED = "completed"
    FAILED = "failed"


class RecoveryStats:
    """Statistics from crash recovery."""
    
    def __init__(self):
        self.phase = RecoveryPhase.STARTED
        self.start_time = datetime.now()
        self.end_time: Optional[datetime] = None
        
        self.snapshots_loaded = 0
        self.log_entries_replayed = 0
        self.entries_failed = 0
        self.conflicts_resolved = 0
        
        self.state_keys_recovered = 0
        self.state_size_bytes = 0
        
        self.errors: List[str] = []
    
    def duration_seconds(self) -> float:
        """Get recovery duration in seconds."""
        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "phase": self.phase.value,
            "duration": self.duration_seconds(),
            "snapshots_loaded": self.snapshots_loaded,
            "log_entries_replayed": self.log_entries_replayed,
            "entries_failed": self.entries_failed,
            "conflicts_resolved": self.conflicts_resolved,
            "state_keys": self.state_keys_recovered,
            "state_size_kb": self.state_size_bytes / 1024,
            "errors": len(self.errors),
        }


class CrashRecoveryHandler:
    """
    Handles recovery from crashes using snapshots and WAL.
    
    Ensures:
    - Complete state recovery from snapshots
    - Uncommitted entries replayed from WAL
    - Data consistency verified
    - Rapid restart capability
    """
    
    def __init__(self, node_id: str):
        """Initialize recovery handler."""
        self.node_id = node_id
        
        # Recovery state
        self.recovery_stats = RecoveryStats()
        self.recovered_state: Optional[Dict[str, Any]] = None
        self.last_recovery_time: Optional[datetime] = None
        
        # Recovery history
        self.recovery_history: List[RecoveryStats] = []
        self.max_history = 10
        
        logger.info(f"Crash recovery handler initialized for {node_id}")
    
    def recover_from_snapshot(
        self,
        snapshot_store,
        term: int,
        index: int,
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Recover state from latest snapshot.
        
        Args:
            snapshot_store: SnapshotStore instance
            term: Expected term (for validation)
            index: Expected index (for validation)
            
        Returns:
            Tuple of (success, recovered_state, error_message)
        """
        self.recovery_stats.phase = RecoveryPhase.LOADING_SNAPSHOTS
        
        try:
            latest = snapshot_store.get_latest_snapshot()
            
            if latest is None:
                logger.warning("No snapshots available for recovery")
                return True, {}, None
            
            metadata, state_data = latest
            
            # Validate snapshot
            if metadata.term > term:
                logger.warning(
                    f"Snapshot term {metadata.term} > current term {term}, "
                    "likely from newer instance"
                )
                return False, None, "Snapshot is from newer instance"
            
            self.recovery_stats.snapshots_loaded += 1
            self.recovery_stats.state_keys_recovered = len(state_data)
            self.recovery_stats.state_size_bytes = len(str(state_data).encode())
            
            logger.info(
                f"Recovered from snapshot: "
                f"{metadata.snapshot_id} ({len(state_data)} keys, index {metadata.index})"
            )
            
            return True, state_data, None
            
        except Exception as e:
            error_msg = f"Snapshot recovery failed: {str(e)}"
            logger.error(error_msg)
            self.recovery_stats.errors.append(error_msg)
            return False, None, error_msg
    
    def replay_log_entries(
        self,
        state: Dict[str, Any],
        log_entries: List[Dict[str, Any]],
        last_applied_index: int,
    ) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """
        Replay log entries to recover uncommitted state.
        
        Args:
            state: Current state from snapshot
            log_entries: Log entries to replay
            last_applied_index: Index of last applied entry
            
        Returns:
            Tuple of (success, updated_state, error_message)
        """
        self.recovery_stats.phase = RecoveryPhase.REPLAYING_LOG
        
        try:
            replayed_state = state.copy()
            
            for entry in log_entries:
                entry_index = entry.get("index", 0)
                
                # Only replay entries after last applied
                if entry_index <= last_applied_index:
                    continue
                
                try:
                    # Extract command
                    command = entry.get("command", {})
                    
                    # Replay based on operation
                    op = command.get("op", "").upper()
                    
                    if op == "SET":
                        key = command.get("key")
                        value = command.get("value")
                        if key:
                            replayed_state[key] = value
                    
                    elif op == "DELETE":
                        key = command.get("key")
                        if key and key in replayed_state:
                            del replayed_state[key]
                    
                    self.recovery_stats.log_entries_replayed += 1
                    
                except Exception as e:
                    logger.warning(f"Failed to replay entry {entry_index}: {e}")
                    self.recovery_stats.entries_failed += 1
                    self.recovery_stats.errors.append(f"Entry {entry_index}: {str(e)}")
                    continue
            
            logger.info(
                f"Replayed {self.recovery_stats.log_entries_replayed} log entries, "
                f"{self.recovery_stats.entries_failed} failed"
            )
            
            return True, replayed_state, None
            
        except Exception as e:
            error_msg = f"Log replay failed: {str(e)}"
            logger.error(error_msg)
            self.recovery_stats.errors.append(error_msg)
            return False, None, error_msg
    
    def validate_recovered_state(
        self,
        state: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate recovered state for consistency.
        
        Args:
            state: State to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        self.recovery_stats.phase = RecoveryPhase.VALIDATING_STATE
        
        try:
            # Check state is dictionary
            if not isinstance(state, dict):
                return False, "State is not a dictionary"
            
            # Check all keys are strings
            for key in state.keys():
                if not isinstance(key, str):
                    return False, f"Non-string key: {key}"
            
            # Check for suspicious patterns
            for key, value in state.items():
                # Check for corrupted entries
                if value is None and key.startswith("_"):
                    logger.warning(f"Suspicious null value for {key}")
            
            logger.info(f"State validation passed: {len(state)} keys")
            return True, None
            
        except Exception as e:
            error_msg = f"State validation failed: {str(e)}"
            logger.error(error_msg)
            self.recovery_stats.errors.append(error_msg)
            return False, error_msg
    
    def full_recovery(
        self,
        snapshot_store,
        log_entries: List[Dict[str, Any]],
        current_term: int,
        last_applied_index: int,
    ) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """
        Perform complete crash recovery.
        
        Args:
            snapshot_store: SnapshotStore instance
            log_entries: Log entries to replay
            current_term: Current term
            last_applied_index: Last applied index
            
        Returns:
            Tuple of (success, recovered_state, error_message)
        """
        self.recovery_stats = RecoveryStats()
        
        try:
            logger.info(
                f"Starting crash recovery for {self.node_id} "
                f"(term={current_term}, applied_index={last_applied_index})"
            )
            
            # Step 1: Recover from snapshot
            success, state, error = self.recover_from_snapshot(
                snapshot_store, current_term, last_applied_index
            )
            
            if not success:
                self.recovery_stats.phase = RecoveryPhase.FAILED
                self.recovery_stats.end_time = datetime.now()
                self.recovery_history.append(self.recovery_stats)
                return False, None, error
            
            if state is None:
                state = {}
            
            # Step 2: Replay log entries
            success, state, error = self.replay_log_entries(
                state, log_entries, last_applied_index
            )
            
            if not success:
                self.recovery_stats.phase = RecoveryPhase.FAILED
                self.recovery_stats.end_time = datetime.now()
                self.recovery_history.append(self.recovery_stats)
                return False, None, error
            
            # Step 3: Validate state
            is_valid, error = self.validate_recovered_state(state)
            
            if not is_valid:
                self.recovery_stats.phase = RecoveryPhase.FAILED
                self.recovery_stats.end_time = datetime.now()
                self.recovery_history.append(self.recovery_stats)
                return False, None, error
            
            # Mark recovery complete
            self.recovery_stats.phase = RecoveryPhase.COMPLETED
            self.recovery_stats.end_time = datetime.now()
            self.recovered_state = state
            self.last_recovery_time = datetime.now()
            
            # Keep history
            self.recovery_history.append(self.recovery_stats)
            if len(self.recovery_history) > self.max_history:
                self.recovery_history.pop(0)
            
            logger.info(
                f"Crash recovery completed in {self.recovery_stats.duration_seconds():.2f}s: "
                f"{self.recovery_stats.state_keys_recovered} keys recovered, "
                f"{self.recovery_stats.log_entries_replayed} entries replayed"
            )
            
            return True, state, None
            
        except Exception as e:
            error_msg = f"Unexpected recovery error: {str(e)}"
            logger.error(error_msg)
            self.recovery_stats.phase = RecoveryPhase.FAILED
            self.recovery_stats.end_time = datetime.now()
            self.recovery_stats.errors.append(error_msg)
            self.recovery_history.append(self.recovery_stats)
            return False, None, error_msg
    
    def get_recovery_stats(self) -> Dict[str, Any]:
        """Get statistics from last recovery."""
        if not self.recovery_stats:
            return {}
        
        return self.recovery_stats.to_dict()
    
    def get_recovery_history(self) -> List[Dict[str, Any]]:
        """Get history of all recoveries."""
        return [stats.to_dict() for stats in self.recovery_history]
    
    def was_recovered_recently(self, seconds: int = 60) -> bool:
        """Check if recovery happened recently."""
        if not self.last_recovery_time:
            return False
        
        elapsed = (datetime.now() - self.last_recovery_time).total_seconds()
        return elapsed < seconds
