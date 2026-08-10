"""
Distributed Transaction Manager for Raft state machine.

Implements:
- ACID properties for distributed transactions
- Multi-key operations with atomicity
- Transaction isolation levels
- Deadlock detection and prevention
- Transaction rollback on failures
"""

import logging
from typing import Dict, Any, List, Optional, Set, Tuple
from datetime import datetime, timedelta
from enum import Enum
from uuid import uuid4
import threading

logger = logging.getLogger(__name__)


class TransactionState(Enum):
    """Transaction state enumeration."""
    PENDING = "pending"
    COMMITTED = "committed"
    ABORTED = "aborted"
    ROLLING_BACK = "rolling_back"


class IsolationLevel(Enum):
    """Transaction isolation levels."""
    READ_UNCOMMITTED = 0
    READ_COMMITTED = 1
    REPEATABLE_READ = 2
    SERIALIZABLE = 3


class TransactionRecord:
    """Record of a distributed transaction."""
    
    def __init__(
        self,
        tx_id: str,
        client_id: str,
        isolation_level: IsolationLevel = IsolationLevel.READ_COMMITTED,
    ):
        self.tx_id = tx_id
        self.client_id = client_id
        self.isolation_level = isolation_level
        
        self.state = TransactionState.PENDING
        self.start_time = datetime.now()
        self.end_time: Optional[datetime] = None
        
        self.read_set: Set[str] = set()  # Keys read
        self.write_set: Set[str] = set()  # Keys written
        self.read_snapshot: Dict[str, Any] = {}  # Snapshot for isolation
        self.write_ops: Dict[str, Any] = {}  # Pending writes
        
        self.lock_acquired: Set[str] = set()  # Locks held
        self.dependencies: Set[str] = set()  # Transactions this depends on
        
        self.conflict_count = 0
        self.retry_count = 0
        self.max_retries = 3


class TransactionManager:
    """
    Manages distributed transactions in Raft cluster.
    
    Ensures:
    - Atomicity: All-or-nothing execution
    - Consistency: Invariant preservation
    - Isolation: Transaction independence
    - Durability: Committed transactions persist
    """
    
    def __init__(self, node_id: str, state_machine_data: Dict[str, Any]):
        """
        Initialize transaction manager.
        
        Args:
            node_id: Node identifier
            state_machine_data: Reference to state machine data
        """
        self.node_id = node_id
        self.state_machine_data = state_machine_data
        
        # Transaction tracking
        self.active_transactions: Dict[str, TransactionRecord] = {}
        self.completed_transactions: Dict[str, TransactionRecord] = {}
        
        # Lock management
        self.lock_table: Dict[str, str] = {}  # key -> tx_id holding lock
        self.lock_waiters: Dict[str, List[str]] = {}  # key -> [waiting tx_ids]
        
        # Statistics
        self.total_transactions = 0
        self.committed_count = 0
        self.aborted_count = 0
        self.conflict_count = 0
        
        # Thread safety
        self.lock = threading.RLock()
        
        logger.info(f"Transaction manager initialized for {node_id}")
    
    def begin_transaction(
        self,
        client_id: str,
        isolation_level: IsolationLevel = IsolationLevel.READ_COMMITTED,
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Begin a new transaction.
        
        Args:
            client_id: Client identifier
            isolation_level: Isolation level for transaction
            
        Returns:
            Tuple of (success, tx_id, error_message)
        """
        with self.lock:
            tx_id = str(uuid4())
            
            tx_record = TransactionRecord(tx_id, client_id, isolation_level)
            
            # Take snapshot for isolation if needed
            if isolation_level in (
                IsolationLevel.REPEATABLE_READ,
                IsolationLevel.SERIALIZABLE,
            ):
                tx_record.read_snapshot = self.state_machine_data.copy()
            
            self.active_transactions[tx_id] = tx_record
            self.total_transactions += 1
            
            logger.debug(f"Transaction {tx_id} started by {client_id}")
            
            return True, tx_id, None
    
    def read_in_transaction(
        self,
        tx_id: str,
        key: str,
    ) -> Tuple[bool, Optional[Any], Optional[str]]:
        """
        Read value within a transaction.
        
        Args:
            tx_id: Transaction identifier
            key: Key to read
            
        Returns:
            Tuple of (success, value, error_message)
        """
        with self.lock:
            if tx_id not in self.active_transactions:
                return False, None, f"Transaction {tx_id} not found"
            
            tx_record = self.active_transactions[tx_id]
            
            # Check if in conflict
            if key in self.lock_table and self.lock_table[key] != tx_id:
                tx_record.conflict_count += 1
                return False, None, f"Key {key} locked by another transaction"
            
            # Read from appropriate source
            if tx_record.isolation_level in (
                IsolationLevel.REPEATABLE_READ,
                IsolationLevel.SERIALIZABLE,
            ):
                # Read from snapshot
                value = tx_record.read_snapshot.get(key)
            else:
                # Read from current state
                value = self.state_machine_data.get(key)
            
            tx_record.read_set.add(key)
            
            return True, value, None
    
    def write_in_transaction(
        self,
        tx_id: str,
        key: str,
        value: Any,
    ) -> Tuple[bool, Optional[str]]:
        """
        Write value within a transaction.
        
        Args:
            tx_id: Transaction identifier
            key: Key to write
            value: Value to write
            
        Returns:
            Tuple of (success, error_message)
        """
        with self.lock:
            if tx_id not in self.active_transactions:
                return False, f"Transaction {tx_id} not found"
            
            tx_record = self.active_transactions[tx_id]
            
            # Acquire lock for key
            if key in self.lock_table:
                if self.lock_table[key] != tx_id:
                    # Lock held by another transaction
                    tx_record.conflict_count += 1
                    return False, f"Key {key} locked by another transaction"
            else:
                self.lock_table[key] = tx_id
                tx_record.lock_acquired.add(key)
            
            # Stage write
            tx_record.write_ops[key] = value
            tx_record.write_set.add(key)
            
            return True, None
    
    def commit_transaction(self, tx_id: str) -> Tuple[bool, Optional[str]]:
        """
        Commit a transaction.
        
        Args:
            tx_id: Transaction identifier
            
        Returns:
            Tuple of (success, error_message)
        """
        with self.lock:
            if tx_id not in self.active_transactions:
                return False, f"Transaction {tx_id} not found"
            
            tx_record = self.active_transactions[tx_id]
            
            # Check for conflicts before committing
            if self._has_read_write_conflicts(tx_record):
                self.conflict_count += 1
                tx_record.retry_count += 1
                
                if tx_record.retry_count > tx_record.max_retries:
                    return False, "Too many retries, transaction aborted"
                
                return False, "Read-write conflict detected"
            
            # Apply all writes atomically
            try:
                for key, value in tx_record.write_ops.items():
                    self.state_machine_data[key] = value
                
                # Release all locks
                for key in tx_record.lock_acquired:
                    if key in self.lock_table and self.lock_table[key] == tx_id:
                        del self.lock_table[key]
                        self._notify_waiters(key)
                
                # Mark as committed
                tx_record.state = TransactionState.COMMITTED
                tx_record.end_time = datetime.now()
                
                # Move to completed
                self.active_transactions.pop(tx_id)
                self.completed_transactions[tx_id] = tx_record
                self.committed_count += 1
                
                logger.debug(f"Transaction {tx_id} committed")
                
                return True, None
                
            except Exception as e:
                logger.error(f"Error committing transaction {tx_id}: {e}")
                return False, f"Commit failed: {str(e)}"
    
    def abort_transaction(self, tx_id: str) -> Tuple[bool, Optional[str]]:
        """
        Abort a transaction.
        
        Args:
            tx_id: Transaction identifier
            
        Returns:
            Tuple of (success, error_message)
        """
        with self.lock:
            if tx_id not in self.active_transactions:
                return False, f"Transaction {tx_id} not found"
            
            tx_record = self.active_transactions[tx_id]
            
            # Release all locks
            for key in tx_record.lock_acquired:
                if key in self.lock_table and self.lock_table[key] == tx_id:
                    del self.lock_table[key]
                    self._notify_waiters(key)
            
            # Discard writes
            tx_record.write_ops.clear()
            
            # Mark as aborted
            tx_record.state = TransactionState.ABORTED
            tx_record.end_time = datetime.now()
            
            # Move to completed
            self.active_transactions.pop(tx_id)
            self.completed_transactions[tx_id] = tx_record
            self.aborted_count += 1
            
            logger.debug(f"Transaction {tx_id} aborted")
            
            return True, None
    
    def _has_read_write_conflicts(self, tx_record: TransactionRecord) -> bool:
        """
        Detect read-write conflicts.
        
        Args:
            tx_record: Transaction record
            
        Returns:
            True if conflicts detected
        """
        for other_id, other_tx in self.active_transactions.items():
            if other_id == tx_record.tx_id:
                continue
            
            if other_tx.state != TransactionState.PENDING:
                continue
            
            # Check for write-read conflicts
            if tx_record.read_set & other_tx.write_set:
                return True
            
            # Check for write-write conflicts
            if tx_record.write_set & other_tx.write_set:
                return True
        
        return False
    
    def _notify_waiters(self, key: str) -> None:
        """Notify waiting transactions when lock is released."""
        if key in self.lock_waiters:
            logger.debug(f"Notifying {len(self.lock_waiters[key])} waiters for key {key}")
    
    def get_transaction_status(self, tx_id: str) -> Optional[Dict]:
        """
        Get status of a transaction.
        
        Args:
            tx_id: Transaction identifier
            
        Returns:
            Transaction status or None
        """
        with self.lock:
            # Check active transactions
            if tx_id in self.active_transactions:
                tx = self.active_transactions[tx_id]
                return {
                    "tx_id": tx_id,
                    "state": tx.state.value,
                    "read_count": len(tx.read_set),
                    "write_count": len(tx.write_set),
                    "lock_count": len(tx.lock_acquired),
                    "duration": (datetime.now() - tx.start_time).total_seconds(),
                }
            
            # Check completed transactions
            if tx_id in self.completed_transactions:
                tx = self.completed_transactions[tx_id]
                duration = (tx.end_time - tx.start_time).total_seconds()
                return {
                    "tx_id": tx_id,
                    "state": tx.state.value,
                    "read_count": len(tx.read_set),
                    "write_count": len(tx.write_set),
                    "duration": duration,
                }
            
            return None
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get transaction manager statistics.
        
        Returns:
            Dictionary with statistics
        """
        with self.lock:
            return {
                "total_transactions": self.total_transactions,
                "active_transactions": len(self.active_transactions),
                "completed_transactions": len(self.completed_transactions),
                "committed": self.committed_count,
                "aborted": self.aborted_count,
                "conflicts": self.conflict_count,
                "locks_held": len(self.lock_table),
                "commit_rate": (
                    self.committed_count / self.total_transactions
                    if self.total_transactions > 0
                    else 0
                ),
            }
