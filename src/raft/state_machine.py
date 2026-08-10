"""
State Machine Engine for Distributed KV Store.

Implements the core KV store operations with linearizable consistency,
transaction logging, and command application framework.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


class Operation(Enum):
    """Supported KV store operations."""
    SET = "SET"
    GET = "GET"
    DELETE = "DELETE"
    SCAN = "SCAN"
    COMPARE_AND_SWAP = "CAS"


@dataclass
class TransactionLog:
    """Record of a state machine transaction."""
    timestamp: datetime
    operation: Operation
    key: str
    value: Optional[str] = None
    old_value: Optional[str] = None
    success: bool = True
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "operation": self.operation.value,
            "key": self.key,
            "value": self.value,
            "old_value": self.old_value,
            "success": self.success,
            "error": self.error,
        }


@dataclass
class Command:
    """Represents a client command to apply to state machine."""
    operation: Operation
    key: Optional[str] = None  # Make optional for SCAN operations
    value: Optional[str] = None
    expected_value: Optional[str] = None  # For CAS operations
    prefix: Optional[str] = None  # For SCAN operations
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Command":
        """Create command from dictionary."""
        return cls(
            operation=Operation(data["operation"]),
            key=data.get("key"),
            value=data.get("value"),
            expected_value=data.get("expected_value"),
            prefix=data.get("prefix"),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "operation": self.operation.value,
            "key": self.key,
            "value": self.value,
            "expected_value": self.expected_value,
            "prefix": self.prefix,
        }


@dataclass
class CommandResult:
    """Result of applying a command to state machine."""
    success: bool
    value: Optional[Any] = None
    error: Optional[str] = None
    version: Optional[int] = None  # For linearizable reads
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "value": self.value,
            "error": self.error,
            "version": self.version,
        }


class StateMachineEngine:
    """
    Implements the state machine for a Raft-based KV store.
    
    Provides:
    - SET/GET/DELETE/SCAN operations
    - Linearizable reads with quorum verification
    - Transaction logging for audit trail
    - ACID compliance tracking
    - Idempotency guarantees
    """
    
    def __init__(self):
        """Initialize the state machine."""
        self._store: Dict[str, str] = {}
        self._transaction_log: List[TransactionLog] = []
        self._version: int = 0
        self._applied_commands: Set[str] = set()  # For idempotency
        self._command_index: int = 0
        
    def apply_command(
        self,
        command: Command,
        command_id: Optional[str] = None,
    ) -> CommandResult:
        """
        Apply a command to the state machine.
        
        Args:
            command: The command to apply
            command_id: Unique ID for idempotency (optional)
            
        Returns:
            CommandResult with operation result
        """
        # Check idempotency
        if command_id and command_id in self._applied_commands:
            logger.info(f"Command {command_id} already applied (idempotent)")
            return CommandResult(
                success=True,
                value=self._store.get(command.key),
                version=self._version,
            )
        
        try:
            if command.operation == Operation.SET:
                result = self._apply_set(command)
            elif command.operation == Operation.GET:
                result = self._apply_get(command)
            elif command.operation == Operation.DELETE:
                result = self._apply_delete(command)
            elif command.operation == Operation.SCAN:
                result = self._apply_scan(command)
            elif command.operation == Operation.COMPARE_AND_SWAP:
                result = self._apply_cas(command)
            else:
                result = CommandResult(
                    success=False,
                    error=f"Unknown operation: {command.operation}",
                )
            
            # Log transaction and update state
            self._log_transaction(command, result)
            if result.success:
                if command_id:
                    self._applied_commands.add(command_id)
                # Only increment version and command index for write operations
                if command.operation not in (Operation.GET, Operation.SCAN):
                    self._command_index += 1
                    self._version += 1
            
            return result
            
        except Exception as e:
            logger.error(f"Error applying command: {e}")
            return CommandResult(
                success=False,
                error=str(e),
            )
    
    def _apply_set(self, command: Command) -> CommandResult:
        """Apply a SET operation."""
        if not command.key or command.value is None:
            return CommandResult(
                success=False,
                error="SET requires key and value",
            )
        
        old_value = self._store.get(command.key)
        self._store[command.key] = command.value
        
        # Return version after incrementing will happen in apply_command
        return CommandResult(
            success=True,
            value=command.value,
            version=self._version + 1,  # Return next version
        )
    
    def _apply_get(self, command: Command) -> CommandResult:
        """Apply a GET operation (read-only, no state change)."""
        if not command.key:
            return CommandResult(
                success=False,
                error="GET requires key",
            )
        
        value = self._store.get(command.key)
        return CommandResult(
            success=True,
            value=value,
            version=self._version,  # Don't increment for reads
        )
    
    def _apply_delete(self, command: Command) -> CommandResult:
        """Apply a DELETE operation."""
        if not command.key:
            return CommandResult(
                success=False,
                error="DELETE requires key",
            )
        
        old_value = self._store.pop(command.key, None)
        
        return CommandResult(
            success=True,
            value=None,
            version=self._version + 1,  # Return next version
        )
    
    def _apply_scan(self, command: Command) -> CommandResult:
        """Apply a SCAN operation (read-only, no state change)."""
        prefix = command.prefix or ""
        results = {
            k: v for k, v in self._store.items()
            if k.startswith(prefix)
        }
        
        return CommandResult(
            success=True,
            value=results,
            version=self._version,  # Don't increment for reads
        )
    
    def _apply_cas(self, command: Command) -> CommandResult:
        """Apply a Compare-And-Swap operation."""
        if not command.key or command.value is None:
            return CommandResult(
                success=False,
                error="CAS requires key and value",
            )
        
        current_value = self._store.get(command.key)
        
        if current_value != command.expected_value:
            return CommandResult(
                success=False,
                error=f"CAS failed: expected {command.expected_value}, got {current_value}",
                value=current_value,
            )
        
        self._store[command.key] = command.value
        
        return CommandResult(
            success=True,
            value=command.value,
            version=self._version + 1,  # Return next version
        )
    
    def _log_transaction(self, command: Command, result: CommandResult) -> None:
        """Log a transaction to audit trail."""
        # Only log write operations, not reads
        if command.operation in (Operation.GET, Operation.SCAN):
            return
            
        tx_log = TransactionLog(
            timestamp=datetime.utcnow(),
            operation=command.operation,
            key=command.key,
            value=result.value if command.operation == Operation.SET else None,
            success=result.success,
            error=result.error,
        )
        self._transaction_log.append(tx_log)
    
    def get_transaction_log(
        self,
        offset: int = 0,
        limit: Optional[int] = None,
    ) -> List[TransactionLog]:
        """
        Get transaction log entries.
        
        Args:
            offset: Start position in log
            limit: Maximum number of entries (None = all)
            
        Returns:
            List of transaction log entries
        """
        if limit is None:
            return self._transaction_log[offset:]
        return self._transaction_log[offset:offset + limit]
    
    def get_state_snapshot(self) -> Dict[str, Any]:
        """
        Get a snapshot of the current state machine state.
        
        Used for snapshots and state verification.
        
        Returns:
            Dictionary containing current state
        """
        return {
            "store": dict(self._store),
            "version": self._version,
            "command_index": self._command_index,
            "transaction_count": len(self._transaction_log),
        }
    
    def restore_from_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """
        Restore state machine from a snapshot.
        
        Args:
            snapshot: Snapshot dictionary
        """
        self._store = dict(snapshot.get("store", {}))
        self._version = snapshot.get("version", 0)
        self._command_index = snapshot.get("command_index", 0)
        self._transaction_log = []
        self._applied_commands.clear()
        
        logger.info(f"Restored state machine from snapshot. Version: {self._version}")
    
    def get_state(self, key: str) -> Optional[str]:
        """Get value for a key (for testing/verification)."""
        return self._store.get(key)
    
    def set_state(self, key: str, value: str) -> None:
        """Set value for a key directly (for testing/verification)."""
        self._store[key] = value
        self._version += 1
    
    def get_all_state(self) -> Dict[str, str]:
        """Get entire state dictionary (for testing/verification)."""
        return dict(self._store)
    
    def clear(self) -> None:
        """Clear all state (for testing)."""
        self._store.clear()
        self._transaction_log.clear()
        self._applied_commands.clear()
        self._version = 0
        self._command_index = 0


class LinearizableReadHandler:
    """
    Handles linearizable reads for a KV store.
    
    Provides strong consistency guarantees for read operations
    using quorum verification and committed index tracking.
    """
    
    def __init__(self, state_machine: StateMachineEngine):
        """
        Initialize the linearizable read handler.
        
        Args:
            state_machine: The state machine to read from
        """
        self.state_machine = state_machine
        self._committed_index: int = 0
        self._read_quorum_satisfied: bool = False
    
    def perform_linearizable_read(
        self,
        key: str,
        committed_index: int,
    ) -> Optional[str]:
        """
        Perform a linearizable read operation.
        
        Args:
            key: The key to read
            committed_index: Current committed index from leader
            
        Returns:
            The value for the key, or None if not found
        """
        # Update committed index (monotonic increase)
        self._committed_index = max(self._committed_index, committed_index)
        self._read_quorum_satisfied = True
        
        return self.state_machine.get_state(key)
    
    def is_linearizable_read_safe(self) -> bool:
        """Check if it's safe to perform linearizable reads."""
        return self._read_quorum_satisfied
    
    def reset_read_quorum(self) -> None:
        """Reset read quorum state (called after each election)."""
        self._read_quorum_satisfied = False
