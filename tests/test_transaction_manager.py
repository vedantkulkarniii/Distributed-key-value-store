"""Tests for distributed transaction manager."""

import pytest
from src.raft.transaction_manager import (
    TransactionManager,
    TransactionState,
    IsolationLevel,
    TransactionRecord,
)


class TestTransactionManager:
    """Test suite for TransactionManager."""
    
    @pytest.fixture
    def state_data(self):
        """Fixture for state machine data."""
        return {"key1": "value1", "key2": "value2"}
    
    @pytest.fixture
    def manager(self, state_data):
        """Fixture for transaction manager."""
        return TransactionManager("node1", state_data)
    
    # Basic Transaction Lifecycle Tests
    
    def test_begin_transaction(self, manager):
        """Test beginning a transaction."""
        success, tx_id, error = manager.begin_transaction("client1")
        
        assert success
        assert tx_id is not None
        assert error is None
        assert tx_id in manager.active_transactions
    
    def test_begin_multiple_transactions(self, manager):
        """Test beginning multiple transactions."""
        success1, tx_id1, _ = manager.begin_transaction("client1")
        success2, tx_id2, _ = manager.begin_transaction("client2")
        
        assert success1 and success2
        assert tx_id1 != tx_id2
        assert len(manager.active_transactions) == 2
    
    def test_commit_empty_transaction(self, manager):
        """Test committing empty transaction."""
        _, tx_id, _ = manager.begin_transaction("client1")
        success, error = manager.commit_transaction(tx_id)
        
        assert success
        assert error is None
        assert tx_id not in manager.active_transactions
        assert tx_id in manager.completed_transactions
    
    def test_abort_transaction(self, manager):
        """Test aborting a transaction."""
        _, tx_id, _ = manager.begin_transaction("client1")
        success, error = manager.abort_transaction(tx_id)
        
        assert success
        assert error is None
        assert manager.completed_transactions[tx_id].state == TransactionState.ABORTED
    
    # Single-Key Operations Tests
    
    def test_read_in_transaction(self, manager, state_data):
        """Test reading a key in transaction."""
        _, tx_id, _ = manager.begin_transaction("client1")
        success, value, error = manager.read_in_transaction(tx_id, "key1")
        
        assert success
        assert value == "value1"
        assert error is None
    
    def test_read_nonexistent_key(self, manager):
        """Test reading nonexistent key."""
        _, tx_id, _ = manager.begin_transaction("client1")
        success, value, error = manager.read_in_transaction(tx_id, "nonexistent")
        
        assert success
        assert value is None
        assert error is None
    
    def test_write_in_transaction(self, manager):
        """Test writing a key in transaction."""
        _, tx_id, _ = manager.begin_transaction("client1")
        success, error = manager.write_in_transaction(tx_id, "key3", "value3")
        
        assert success
        assert error is None
    
    def test_write_and_commit(self, manager, state_data):
        """Test writing and committing."""
        _, tx_id, _ = manager.begin_transaction("client1")
        manager.write_in_transaction(tx_id, "key3", "value3")
        success, error = manager.commit_transaction(tx_id)
        
        assert success
        assert state_data["key3"] == "value3"
    
    # Multi-Key Transactions Tests
    
    def test_multi_key_read(self, manager):
        """Test reading multiple keys in transaction."""
        _, tx_id, _ = manager.begin_transaction("client1")
        
        success1, v1, _ = manager.read_in_transaction(tx_id, "key1")
        success2, v2, _ = manager.read_in_transaction(tx_id, "key2")
        
        assert success1 and success2
        assert v1 == "value1"
        assert v2 == "value2"
    
    def test_multi_key_write(self, manager, state_data):
        """Test writing multiple keys in transaction."""
        _, tx_id, _ = manager.begin_transaction("client1")
        
        manager.write_in_transaction(tx_id, "key3", "value3")
        manager.write_in_transaction(tx_id, "key4", "value4")
        success, error = manager.commit_transaction(tx_id)
        
        assert success
        assert state_data["key3"] == "value3"
        assert state_data["key4"] == "value4"
    
    def test_read_modify_write(self, manager, state_data):
        """Test read-modify-write transaction."""
        _, tx_id, _ = manager.begin_transaction("client1")
        
        # Read
        success, old_value, _ = manager.read_in_transaction(tx_id, "key1")
        assert success
        
        # Write new value
        success, _ = manager.write_in_transaction(tx_id, "key1", old_value + "_modified")
        assert success
        
        # Commit
        success, _ = manager.commit_transaction(tx_id)
        assert success
        assert state_data["key1"] == "value1_modified"
    
    # Lock Management Tests
    
    def test_lock_acquisition(self, manager):
        """Test lock acquisition during write."""
        _, tx_id, _ = manager.begin_transaction("client1")
        manager.write_in_transaction(tx_id, "key1", "new_value")
        
        assert "key1" in manager.lock_table
        assert manager.lock_table["key1"] == tx_id
    
    def test_lock_release_on_commit(self, manager):
        """Test lock release after commit."""
        _, tx_id, _ = manager.begin_transaction("client1")
        manager.write_in_transaction(tx_id, "key1", "new_value")
        manager.commit_transaction(tx_id)
        
        assert "key1" not in manager.lock_table
    
    def test_lock_release_on_abort(self, manager):
        """Test lock release after abort."""
        _, tx_id, _ = manager.begin_transaction("client1")
        manager.write_in_transaction(tx_id, "key1", "new_value")
        manager.abort_transaction(tx_id)
        
        assert "key1" not in manager.lock_table
    
    def test_lock_conflict_detection(self, manager):
        """Test detection of lock conflicts."""
        _, tx_id1, _ = manager.begin_transaction("client1")
        _, tx_id2, _ = manager.begin_transaction("client2")
        
        # First transaction acquires lock
        manager.write_in_transaction(tx_id1, "key1", "value1")
        
        # Second transaction tries to write same key
        success, error = manager.write_in_transaction(tx_id2, "key1", "value2")
        
        assert not success
        assert error is not None
    
    # Isolation Level Tests
    
    def test_read_uncommitted_isolation(self, manager, state_data):
        """Test READ_UNCOMMITTED isolation level."""
        _, tx_id, _ = manager.begin_transaction(
            "client1", IsolationLevel.READ_UNCOMMITTED
        )
        success, value, _ = manager.read_in_transaction(tx_id, "key1")
        
        assert success
        assert value == "value1"
    
    def test_read_committed_isolation(self, manager):
        """Test READ_COMMITTED isolation level."""
        _, tx_id, _ = manager.begin_transaction(
            "client1", IsolationLevel.READ_COMMITTED
        )
        manager.write_in_transaction(tx_id, "key1", "new_value")
        success, _ = manager.commit_transaction(tx_id)
        
        assert success
    
    def test_repeatable_read_isolation(self, manager, state_data):
        """Test REPEATABLE_READ isolation level."""
        _, tx_id, _ = manager.begin_transaction(
            "client1", IsolationLevel.REPEATABLE_READ
        )
        
        # Should read from snapshot
        success1, v1, _ = manager.read_in_transaction(tx_id, "key1")
        
        # Modify state externally
        state_data["key1"] = "modified"
        
        # Should still read from snapshot
        success2, v2, _ = manager.read_in_transaction(tx_id, "key1")
        
        assert success1 and success2
        assert v1 == v2 == "value1"
    
    def test_serializable_isolation(self, manager, state_data):
        """Test SERIALIZABLE isolation level."""
        _, tx_id, _ = manager.begin_transaction(
            "client1", IsolationLevel.SERIALIZABLE
        )
        
        # Should take snapshot
        tx_record = manager.active_transactions[tx_id]
        assert len(tx_record.read_snapshot) > 0
    
    # Conflict Detection Tests
    
    def test_write_write_conflict(self, manager, state_data):
        """Test write-write conflict detection."""
        _, tx_id1, _ = manager.begin_transaction("client1")
        _, tx_id2, _ = manager.begin_transaction("client2")
        
        # Both write to same key
        manager.write_in_transaction(tx_id1, "key1", "value_a")
        manager.write_in_transaction(tx_id2, "key1", "value_b")
        
        # First commit should succeed
        success1, _ = manager.commit_transaction(tx_id1)
        assert success1
        
        # Second commit should detect conflict
        success2, _ = manager.commit_transaction(tx_id2)
        assert not success2
    
    def test_no_conflict_different_keys(self, manager, state_data):
        """Test no conflict when writing different keys."""
        _, tx_id1, _ = manager.begin_transaction("client1")
        _, tx_id2, _ = manager.begin_transaction("client2")
        
        # Write to different keys
        manager.write_in_transaction(tx_id1, "key1", "value_a")
        manager.write_in_transaction(tx_id2, "key2", "value_b")
        
        # Both should commit
        success1, _ = manager.commit_transaction(tx_id1)
        success2, _ = manager.commit_transaction(tx_id2)
        
        assert success1 and success2
    
    # Error Handling Tests
    
    def test_read_from_invalid_transaction(self, manager):
        """Test reading from nonexistent transaction."""
        success, value, error = manager.read_in_transaction("invalid_tx", "key1")
        
        assert not success
        assert value is None
        assert error is not None
    
    def test_write_to_invalid_transaction(self, manager):
        """Test writing to nonexistent transaction."""
        success, error = manager.write_in_transaction("invalid_tx", "key1", "value")
        
        assert not success
        assert error is not None
    
    def test_commit_invalid_transaction(self, manager):
        """Test committing nonexistent transaction."""
        success, error = manager.commit_transaction("invalid_tx")
        
        assert not success
        assert error is not None
    
    def test_abort_invalid_transaction(self, manager):
        """Test aborting nonexistent transaction."""
        success, error = manager.abort_transaction("invalid_tx")
        
        assert not success
        assert error is not None
    
    # Status and Statistics Tests
    
    def test_get_transaction_status_active(self, manager):
        """Test getting status of active transaction."""
        _, tx_id, _ = manager.begin_transaction("client1")
        manager.read_in_transaction(tx_id, "key1")
        manager.write_in_transaction(tx_id, "key2", "value")
        
        status = manager.get_transaction_status(tx_id)
        
        assert status is not None
        assert status["state"] == "pending"
        assert status["read_count"] == 1
        assert status["write_count"] == 1
    
    def test_get_transaction_status_completed(self, manager):
        """Test getting status of completed transaction."""
        _, tx_id, _ = manager.begin_transaction("client1")
        manager.commit_transaction(tx_id)
        
        status = manager.get_transaction_status(tx_id)
        
        assert status is not None
        assert status["state"] == "committed"
    
    def test_get_statistics(self, manager):
        """Test getting manager statistics."""
        for i in range(3):
            _, tx_id, _ = manager.begin_transaction(f"client{i}")
            if i < 2:
                manager.commit_transaction(tx_id)
            else:
                manager.abort_transaction(tx_id)
        
        stats = manager.get_statistics()
        
        assert stats["total_transactions"] == 3
        assert stats["committed"] == 2
        assert stats["aborted"] == 1
        assert 0 <= stats["commit_rate"] <= 1
    
    # Idempotency Tests
    
    def test_transaction_idempotency(self, manager, state_data):
        """Test that same transaction doesn't double-apply."""
        _, tx_id, _ = manager.begin_transaction("client1")
        manager.write_in_transaction(tx_id, "counter", 1)
        manager.commit_transaction(tx_id)
        
        initial_value = state_data.get("counter")
        
        # Committing same transaction again should not apply again
        success, _ = manager.commit_transaction(tx_id)
        
        # Should fail since transaction no longer active
        assert not success
        assert state_data.get("counter") == initial_value
    
    # Atomicity Tests
    
    def test_transaction_all_or_nothing(self, manager, state_data):
        """Test atomicity of transaction."""
        _, tx_id, _ = manager.begin_transaction("client1")
        manager.write_in_transaction(tx_id, "key_a", "value_a")
        manager.write_in_transaction(tx_id, "key_b", "value_b")
        
        success, _ = manager.commit_transaction(tx_id)
        
        assert success
        assert state_data.get("key_a") == "value_a"
        assert state_data.get("key_b") == "value_b"
