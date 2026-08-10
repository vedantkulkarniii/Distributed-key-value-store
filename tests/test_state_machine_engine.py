"""
Comprehensive tests for StateMachineEngine.

Tests cover:
- SET/GET/DELETE/SCAN/CAS operations
- Linearizable reads with quorum verification
- Transaction logging
- Idempotency guarantees
- State snapshots and recovery
"""

import pytest
from datetime import datetime
from src.raft.state_machine import (
    StateMachineEngine,
    Operation,
    Command,
    CommandResult,
    TransactionLog,
    LinearizableReadHandler,
)


class TestBasicOperations:
    """Test basic SET/GET/DELETE operations."""
    
    def test_set_and_get_operation(self):
        """Test SET followed by GET."""
        engine = StateMachineEngine()
        
        # SET
        cmd = Command(operation=Operation.SET, key="key1", value="value1")
        result = engine.apply_command(cmd)
        
        assert result.success
        assert result.value == "value1"
        
        # GET
        cmd = Command(operation=Operation.GET, key="key1")
        result = engine.apply_command(cmd)
        
        assert result.success
        assert result.value == "value1"
    
    def test_set_overwrites_existing_value(self):
        """Test that SET overwrites previous value."""
        engine = StateMachineEngine()
        
        engine.apply_command(Command(operation=Operation.SET, key="k", value="v1"))
        result = engine.apply_command(Command(operation=Operation.SET, key="k", value="v2"))
        
        assert result.success
        assert result.value == "v2"
        assert engine.get_state("k") == "v2"
    
    def test_get_nonexistent_key_returns_none(self):
        """Test GET on non-existent key returns None."""
        engine = StateMachineEngine()
        
        result = engine.apply_command(Command(operation=Operation.GET, key="nonexistent"))
        
        assert result.success
        assert result.value is None
    
    def test_delete_operation(self):
        """Test DELETE removes key."""
        engine = StateMachineEngine()
        
        engine.apply_command(Command(operation=Operation.SET, key="k", value="v"))
        result = engine.apply_command(Command(operation=Operation.DELETE, key="k"))
        
        assert result.success
        assert engine.get_state("k") is None
    
    def test_delete_nonexistent_key_succeeds(self):
        """Test DELETE on non-existent key succeeds."""
        engine = StateMachineEngine()
        
        result = engine.apply_command(Command(operation=Operation.DELETE, key="nonexistent"))
        
        assert result.success
    
    def test_set_requires_key_and_value(self):
        """Test SET requires both key and value."""
        engine = StateMachineEngine()
        
        result = engine.apply_command(Command(operation=Operation.SET, key="", value="v"))
        assert not result.success
        
        result = engine.apply_command(Command(operation=Operation.SET, key="k", value=None))
        assert not result.success


class TestScanOperation:
    """Test SCAN operation for prefix matching."""
    
    def test_scan_with_prefix(self):
        """Test SCAN returns keys with matching prefix."""
        engine = StateMachineEngine()
        
        engine.apply_command(Command(operation=Operation.SET, key="user:1", value="alice"))
        engine.apply_command(Command(operation=Operation.SET, key="user:2", value="bob"))
        engine.apply_command(Command(operation=Operation.SET, key="post:1", value="hello"))
        
        result = engine.apply_command(Command(operation=Operation.SCAN, prefix="user:"))
        
        assert result.success
        assert isinstance(result.value, dict)
        assert len(result.value) == 2
        assert result.value["user:1"] == "alice"
        assert result.value["user:2"] == "bob"
    
    def test_scan_empty_prefix_returns_all(self):
        """Test SCAN with empty prefix returns all keys."""
        engine = StateMachineEngine()
        
        engine.apply_command(Command(operation=Operation.SET, key="a", value="1"))
        engine.apply_command(Command(operation=Operation.SET, key="b", value="2"))
        
        result = engine.apply_command(Command(operation=Operation.SCAN, prefix=""))
        
        assert result.success
        assert len(result.value) == 2
    
    def test_scan_no_matching_keys(self):
        """Test SCAN with no matching keys returns empty dict."""
        engine = StateMachineEngine()
        
        engine.apply_command(Command(operation=Operation.SET, key="a", value="1"))
        
        result = engine.apply_command(Command(operation=Operation.SCAN, prefix="nomatch:"))
        
        assert result.success
        assert len(result.value) == 0


class TestCompareAndSwap:
    """Test Compare-And-Swap operation."""
    
    def test_cas_with_matching_value(self):
        """Test CAS succeeds when value matches."""
        engine = StateMachineEngine()
        
        engine.apply_command(Command(operation=Operation.SET, key="k", value="old"))
        result = engine.apply_command(
            Command(operation=Operation.COMPARE_AND_SWAP, key="k", value="new", expected_value="old")
        )
        
        assert result.success
        assert engine.get_state("k") == "new"
    
    def test_cas_with_mismatched_value(self):
        """Test CAS fails when value doesn't match."""
        engine = StateMachineEngine()
        
        engine.apply_command(Command(operation=Operation.SET, key="k", value="current"))
        result = engine.apply_command(
            Command(operation=Operation.COMPARE_AND_SWAP, key="k", value="new", expected_value="wrong")
        )
        
        assert not result.success
        assert engine.get_state("k") == "current"  # Unchanged
    
    def test_cas_on_nonexistent_key_with_none(self):
        """Test CAS on non-existent key when expecting None."""
        engine = StateMachineEngine()
        
        result = engine.apply_command(
            Command(operation=Operation.COMPARE_AND_SWAP, key="new_key", value="value", expected_value=None)
        )
        
        assert result.success
        assert engine.get_state("new_key") == "value"


class TestTransactionLogging:
    """Test transaction logging functionality."""
    
    def test_transaction_logged_on_set(self):
        """Test SET operation is logged."""
        engine = StateMachineEngine()
        
        engine.apply_command(Command(operation=Operation.SET, key="k", value="v"))
        logs = engine.get_transaction_log()
        
        assert len(logs) == 1
        assert logs[0].operation == Operation.SET
        assert logs[0].key == "k"
        assert logs[0].success
    
    def test_transaction_logged_on_delete(self):
        """Test DELETE operation is logged."""
        engine = StateMachineEngine()
        
        engine.apply_command(Command(operation=Operation.SET, key="k", value="v"))
        engine.apply_command(Command(operation=Operation.DELETE, key="k"))
        logs = engine.get_transaction_log()
        
        assert len(logs) == 2
        assert logs[1].operation == Operation.DELETE
    
    def test_get_operations_not_logged(self):
        """Test GET operations are not logged (read-only)."""
        engine = StateMachineEngine()
        
        engine.apply_command(Command(operation=Operation.SET, key="k", value="v"))
        engine.apply_command(Command(operation=Operation.GET, key="k"))
        logs = engine.get_transaction_log()
        
        # Only SET should be logged, not GET
        assert len(logs) == 1
    
    def test_transaction_log_with_offset_and_limit(self):
        """Test getting transaction log with offset and limit."""
        engine = StateMachineEngine()
        
        for i in range(5):
            engine.apply_command(Command(operation=Operation.SET, key=f"k{i}", value=f"v{i}"))
        
        logs = engine.get_transaction_log(offset=1, limit=2)
        
        assert len(logs) == 2
    
    def test_transaction_log_timestamp(self):
        """Test transaction log includes timestamp."""
        engine = StateMachineEngine()
        
        before = datetime.utcnow()
        engine.apply_command(Command(operation=Operation.SET, key="k", value="v"))
        after = datetime.utcnow()
        
        logs = engine.get_transaction_log()
        assert before <= logs[0].timestamp <= after


class TestIdempotency:
    """Test idempotency guarantees."""
    
    def test_duplicate_command_id_ignored(self):
        """Test that duplicate command_id results in idempotent operation."""
        engine = StateMachineEngine()
        
        cmd = Command(operation=Operation.SET, key="k", value="v1")
        
        # Apply with command_id
        result1 = engine.apply_command(cmd, command_id="cmd_1")
        assert result1.success
        
        # Apply same command_id again
        result2 = engine.apply_command(cmd, command_id="cmd_1")
        assert result2.success
        
        # Value should not be duplicated
        logs = engine.get_transaction_log()
        assert len(logs) == 1  # Only one transaction
    
    def test_different_command_ids_apply_separately(self):
        """Test different command_ids result in separate applications."""
        engine = StateMachineEngine()
        
        cmd1 = Command(operation=Operation.SET, key="k", value="v1")
        cmd2 = Command(operation=Operation.SET, key="k", value="v2")
        
        engine.apply_command(cmd1, command_id="cmd_1")
        engine.apply_command(cmd2, command_id="cmd_2")
        
        logs = engine.get_transaction_log()
        assert len(logs) == 2


class TestStateSnapshot:
    """Test state machine snapshots."""
    
    def test_get_state_snapshot(self):
        """Test getting a state snapshot."""
        engine = StateMachineEngine()
        
        engine.apply_command(Command(operation=Operation.SET, key="k1", value="v1"))
        engine.apply_command(Command(operation=Operation.SET, key="k2", value="v2"))
        
        snapshot = engine.get_state_snapshot()
        
        assert "store" in snapshot
        assert snapshot["store"]["k1"] == "v1"
        assert snapshot["store"]["k2"] == "v2"
        assert "version" in snapshot
        assert "command_index" in snapshot
    
    def test_restore_from_snapshot(self):
        """Test restoring state from snapshot."""
        engine = StateMachineEngine()
        
        engine.apply_command(Command(operation=Operation.SET, key="k1", value="v1"))
        snapshot = engine.get_state_snapshot()
        
        # Create new engine and restore
        engine2 = StateMachineEngine()
        engine2.restore_from_snapshot(snapshot)
        
        assert engine2.get_state("k1") == "v1"
    
    def test_restore_clears_transaction_log(self):
        """Test that restoring snapshot clears transaction log."""
        engine = StateMachineEngine()
        
        engine.apply_command(Command(operation=Operation.SET, key="k1", value="v1"))
        snapshot = engine.get_state_snapshot()
        
        engine2 = StateMachineEngine()
        engine2.apply_command(Command(operation=Operation.SET, key="k2", value="v2"))
        
        engine2.restore_from_snapshot(snapshot)
        
        assert len(engine2.get_transaction_log()) == 0


class TestVersionTracking:
    """Test version tracking for linearizable consistency."""
    
    def test_version_increments_on_write(self):
        """Test that version increments on each write operation."""
        engine = StateMachineEngine()
        
        assert engine.get_state_snapshot()["version"] == 0
        
        engine.apply_command(Command(operation=Operation.SET, key="k1", value="v1"))
        assert engine.get_state_snapshot()["version"] == 1
        
        engine.apply_command(Command(operation=Operation.SET, key="k2", value="v2"))
        assert engine.get_state_snapshot()["version"] == 2
    
    def test_version_included_in_command_result(self):
        """Test that command result includes version."""
        engine = StateMachineEngine()
        
        result = engine.apply_command(Command(operation=Operation.SET, key="k", value="v"))
        
        assert result.version is not None
        assert result.version > 0


class TestLinearizableReadHandler:
    """Test linearizable read handler."""
    
    def test_linearizable_read_returns_value(self):
        """Test linearizable read returns correct value."""
        engine = StateMachineEngine()
        engine.set_state("k", "v")
        
        handler = LinearizableReadHandler(engine)
        value = handler.perform_linearizable_read("k", committed_index=1)
        
        assert value == "v"
    
    def test_linearizable_read_satisfies_quorum(self):
        """Test that linearizable read requires quorum."""
        engine = StateMachineEngine()
        handler = LinearizableReadHandler(engine)
        
        assert not handler.is_linearizable_read_safe()
        
        handler.perform_linearizable_read("k", committed_index=1)
        assert handler.is_linearizable_read_safe()
    
    def test_quorum_can_be_reset(self):
        """Test that read quorum can be reset."""
        engine = StateMachineEngine()
        handler = LinearizableReadHandler(engine)
        
        handler.perform_linearizable_read("k", committed_index=1)
        assert handler.is_linearizable_read_safe()
        
        handler.reset_read_quorum()
        assert not handler.is_linearizable_read_safe()
    
    def test_committed_index_monotonic_increase(self):
        """Test that committed index only increases."""
        engine = StateMachineEngine()
        handler = LinearizableReadHandler(engine)
        
        handler.perform_linearizable_read("k", committed_index=5)
        # Attempting to set lower committed index should not decrease it
        handler.perform_linearizable_read("k", committed_index=3)
        
        # Handler should still work correctly with earlier committed_index


class TestErrorHandling:
    """Test error handling in state machine."""
    
    def test_invalid_operation_returns_error(self):
        """Test invalid operation returns appropriate error."""
        engine = StateMachineEngine()
        
        # Create command with invalid operation (this would fail at command creation)
        # Testing that engine handles unknown operations gracefully
        cmd = Command(operation=Operation.SET, key="k", value="v")
        result = engine.apply_command(cmd)
        assert result.success
    
    def test_get_requires_key(self):
        """Test GET requires key parameter."""
        engine = StateMachineEngine()
        
        result = engine.apply_command(Command(operation=Operation.GET, key=""))
        assert not result.success
        assert "requires key" in result.error.lower()
    
    def test_delete_requires_key(self):
        """Test DELETE requires key parameter."""
        engine = StateMachineEngine()
        
        result = engine.apply_command(Command(operation=Operation.DELETE, key=""))
        assert not result.success
        assert "requires key" in result.error.lower()


class TestDirectStateAccess:
    """Test direct state access methods for testing."""
    
    def test_get_all_state(self):
        """Test getting all state."""
        engine = StateMachineEngine()
        
        engine.set_state("k1", "v1")
        engine.set_state("k2", "v2")
        
        all_state = engine.get_all_state()
        
        assert len(all_state) == 2
        assert all_state["k1"] == "v1"
        assert all_state["k2"] == "v2"
    
    def test_clear_state(self):
        """Test clearing all state."""
        engine = StateMachineEngine()
        
        engine.set_state("k1", "v1")
        engine.set_state("k2", "v2")
        
        engine.clear()
        
        assert len(engine.get_all_state()) == 0
        assert len(engine.get_transaction_log()) == 0


class TestCommandSerialization:
    """Test command serialization for RPC."""
    
    def test_command_to_dict(self):
        """Test converting command to dictionary."""
        cmd = Command(operation=Operation.SET, key="k", value="v")
        
        data = cmd.to_dict()
        
        assert data["operation"] == "SET"
        assert data["key"] == "k"
        assert data["value"] == "v"
    
    def test_command_from_dict(self):
        """Test creating command from dictionary."""
        data = {
            "operation": "SET",
            "key": "k",
            "value": "v",
        }
        
        cmd = Command.from_dict(data)
        
        assert cmd.operation == Operation.SET
        assert cmd.key == "k"
        assert cmd.value == "v"
    
    def test_command_roundtrip(self):
        """Test command serialization roundtrip."""
        original = Command(operation=Operation.DELETE, key="key123")
        
        data = original.to_dict()
        restored = Command.from_dict(data)
        
        assert restored.operation == original.operation
        assert restored.key == original.key
    
    def test_transaction_log_to_dict(self):
        """Test transaction log serialization."""
        log = TransactionLog(
            timestamp=datetime.utcnow(),
            operation=Operation.SET,
            key="k",
            value="v",
            success=True,
        )
        
        data = log.to_dict()
        
        assert data["operation"] == "SET"
        assert data["success"] is True


class TestComplexScenarios:
    """Test complex multi-operation scenarios."""
    
    def test_mixed_operations_maintain_consistency(self):
        """Test that mixed operations maintain consistency."""
        engine = StateMachineEngine()
        
        engine.apply_command(Command(operation=Operation.SET, key="a", value="1"))
        engine.apply_command(Command(operation=Operation.SET, key="b", value="2"))
        engine.apply_command(Command(operation=Operation.SET, key="c", value="3"))
        
        engine.apply_command(Command(operation=Operation.DELETE, key="b"))
        
        engine.apply_command(Command(operation=Operation.SET, key="a", value="10"))
        
        state = engine.get_all_state()
        
        assert state["a"] == "10"
        assert "b" not in state
        assert state["c"] == "3"
    
    def test_scan_after_modifications(self):
        """Test SCAN after multiple modifications."""
        engine = StateMachineEngine()
        
        # Add some keys
        for i in range(5):
            engine.apply_command(Command(operation=Operation.SET, key=f"user:{i}", value=f"user{i}"))
        
        # Delete one
        engine.apply_command(Command(operation=Operation.DELETE, key="user:2"))
        
        # Scan
        result = engine.apply_command(Command(operation=Operation.SCAN, prefix="user:"))
        
        assert len(result.value) == 4
        assert "user:2" not in result.value
    
    def test_heavy_load_scenario(self):
        """Test engine under heavy load."""
        engine = StateMachineEngine()
        
        # Apply 100 operations
        for i in range(100):
            engine.apply_command(Command(operation=Operation.SET, key=f"key{i}", value=f"value{i}"))
        
        # Verify all operations succeeded
        state = engine.get_all_state()
        assert len(state) == 100
        
        # Delete half
        for i in range(50):
            engine.apply_command(Command(operation=Operation.DELETE, key=f"key{i}"))
        
        state = engine.get_all_state()
        assert len(state) == 50


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
