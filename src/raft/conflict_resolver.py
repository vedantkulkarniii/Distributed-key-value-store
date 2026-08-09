"""Conflict Detection and Resolution Utilities for Raft Log Replication.

This module provides utilities for detecting and resolving conflicts in the Raft log,
including automatic conflict recovery mechanisms and optimistic log synchronization.
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class ConflictInfo:
    """Information about a detected conflict in the log."""
    
    follower_id: str
    """The follower that has the conflict."""
    
    conflict_index: int
    """The index where the conflict was detected."""
    
    leader_term: int
    """The term at the conflict index according to the leader."""
    
    follower_term: Optional[int] = None
    """The term at the conflict index according to the follower."""
    
    conflict_type: str = "term_mismatch"
    """Type of conflict: 'term_mismatch', 'missing_entry', or 'partial_divergence'."""
    
    recovery_strategy: str = "backtrack"
    """Recovery strategy to use: 'backtrack', 'snapshot', or 'full_sync'."""


class ConflictResolver:
    """Detects and resolves conflicts in Raft log replication.
    
    The ConflictResolver uses the AppendEntries RPC response to detect when
    a follower's log diverges from the leader's log, and employs various
    strategies to recover from these conflicts.
    """
    
    def __init__(self):
        """Initialize the conflict resolver."""
        self.conflicts: Dict[str, List[ConflictInfo]] = {}
        """Track conflicts per follower."""
        
        self.recovery_attempts: Dict[str, int] = {}
        """Track recovery attempts per follower."""
        
        self.backtrack_history: Dict[str, List[int]] = {}
        """Track backtrack indices for optimization."""
    
    def detect_conflict(
        self,
        follower_id: str,
        append_entries_response: Dict,
        leader_log_term: int,
        conflict_index: int,
    ) -> Optional[ConflictInfo]:
        """Detect if a conflict exists based on AppendEntries response.
        
        Args:
            follower_id: The ID of the follower.
            append_entries_response: The AppendEntries RPC response from the follower.
            leader_log_term: The term at the conflict index in the leader's log.
            conflict_index: The index where we suspect a conflict.
        
        Returns:
            ConflictInfo if a conflict is detected, None otherwise.
        """
        if append_entries_response.get("success"):
            return None
        
        # Follower rejected the AppendEntries, indicating a conflict
        follower_term = append_entries_response.get("term")
        
        conflict = ConflictInfo(
            follower_id=follower_id,
            conflict_index=conflict_index,
            leader_term=leader_log_term,
            follower_term=follower_term,
            conflict_type=self._classify_conflict(
                leader_log_term, follower_term, append_entries_response
            ),
        )
        
        # Determine recovery strategy
        conflict.recovery_strategy = self._select_recovery_strategy(conflict)
        
        # Track the conflict
        if follower_id not in self.conflicts:
            self.conflicts[follower_id] = []
        self.conflicts[follower_id].append(conflict)
        
        return conflict
    
    def _classify_conflict(
        self,
        leader_term: int,
        follower_term: Optional[int],
        response: Dict,
    ) -> str:
        """Classify the type of conflict detected.
        
        Args:
            leader_term: The leader's term at the conflict index.
            follower_term: The follower's term (from response).
            response: The full AppendEntries response.
        
        Returns:
            The conflict type as a string.
        """
        if follower_term is not None and follower_term > leader_term:
            return "term_mismatch"
        
        if response.get("last_index", 0) == 0:
            return "missing_entry"
        
        return "partial_divergence"
    
    def _select_recovery_strategy(self, conflict: ConflictInfo) -> str:
        """Select the best recovery strategy for a conflict.
        
        Args:
            conflict: The conflict information.
        
        Returns:
            The recovery strategy to use.
        """
        attempts = self.recovery_attempts.get(conflict.follower_id, 0)
        
        # Use full sync after multiple failed backtracks
        if attempts >= 3 and conflict.conflict_type == "partial_divergence":
            return "full_sync"
        
        # Use snapshot for term mismatches on higher terms
        if conflict.conflict_type == "term_mismatch" and (
            conflict.follower_term or 0
        ) > conflict.leader_term:
            return "snapshot"
        
        return "backtrack"
    
    def optimistic_log_sync(
        self,
        follower_id: str,
        leader_log: List[Dict],
        follower_last_index: int,
    ) -> Tuple[int, List[Dict]]:
        """Perform optimistic log synchronization to a follower.
        
        Uses exponential backoff combined with conflict history to quickly
        find the point of divergence and sync the log efficiently.
        
        Args:
            follower_id: The ID of the follower.
            leader_log: The leader's log entries.
            follower_last_index: The last known index of the follower.
        
        Returns:
            A tuple of (sync_from_index, entries_to_send).
        """
        # Check if we have history for this follower
        if follower_id in self.backtrack_history:
            history = self.backtrack_history[follower_id]
            if history:
                # Use the last successful backtrack as a starting point
                last_known_good = history[-1]
                sync_from = max(0, last_known_good + 1)
            else:
                sync_from = max(0, follower_last_index - 1)
        else:
            # Start with exponential backoff
            sync_from = max(0, follower_last_index // 2)
            self.backtrack_history[follower_id] = []
        
        # Get entries to send
        entries_to_send = [
            entry for entry in leader_log
            if entry.get("index", 0) >= sync_from
        ]
        
        return sync_from, entries_to_send
    
    def record_successful_sync(
        self,
        follower_id: str,
        sync_index: int,
    ) -> None:
        """Record a successful log synchronization point.
        
        Args:
            follower_id: The ID of the follower.
            sync_index: The index up to which the sync was successful.
        """
        if follower_id not in self.backtrack_history:
            self.backtrack_history[follower_id] = []
        
        # Only record if it's a new high watermark
        current_history = self.backtrack_history[follower_id]
        if not current_history or sync_index > current_history[-1]:
            current_history.append(sync_index)
            # Keep only recent history (last 5 entries)
            if len(current_history) > 5:
                current_history.pop(0)
    
    def should_use_fast_backtrack(self, follower_id: str) -> bool:
        """Determine if fast backtracking should be used.
        
        Args:
            follower_id: The ID of the follower.
        
        Returns:
            True if fast backtracking is applicable, False otherwise.
        """
        if follower_id not in self.backtrack_history:
            return False
        
        history = self.backtrack_history[follower_id]
        return len(history) >= 2
    
    def get_conflict_summary(self, follower_id: str) -> Dict:
        """Get a summary of all conflicts for a follower.
        
        Args:
            follower_id: The ID of the follower.
        
        Returns:
            A dictionary with conflict summary information.
        """
        conflicts = self.conflicts.get(follower_id, [])
        
        if not conflicts:
            return {
                "follower_id": follower_id,
                "total_conflicts": 0,
                "latest_conflict": None,
            }
        
        latest = conflicts[-1]
        
        return {
            "follower_id": follower_id,
            "total_conflicts": len(conflicts),
            "latest_conflict": {
                "index": latest.conflict_index,
                "type": latest.conflict_type,
                "leader_term": latest.leader_term,
                "follower_term": latest.follower_term,
                "recovery_strategy": latest.recovery_strategy,
            },
            "recovery_attempts": self.recovery_attempts.get(follower_id, 0),
            "sync_history_length": len(self.backtrack_history.get(follower_id, [])),
        }
    
    def clear_resolved_conflicts(self, follower_id: str) -> None:
        """Clear conflict records for a follower after successful sync.
        
        Args:
            follower_id: The ID of the follower.
        """
        if follower_id in self.conflicts:
            del self.conflicts[follower_id]
        
        if follower_id in self.recovery_attempts:
            self.recovery_attempts[follower_id] = 0
    
    def increment_recovery_attempt(self, follower_id: str) -> int:
        """Increment and return the recovery attempt count for a follower.
        
        Args:
            follower_id: The ID of the follower.
        
        Returns:
            The updated recovery attempt count.
        """
        current = self.recovery_attempts.get(follower_id, 0)
        current += 1
        self.recovery_attempts[follower_id] = current
        return current
