"""
Test suite for state machine engine.

Tests:
- Command application (SET, GET, DELETE, SCAN, CAS)
- Idempotency and duplicate detection
- Transaction support
- Read-only operations
- Snapshot and restore
- Status reporting
"""

import pytest
import asyncio
from src.raft.state_machine import StateMachineEngine, StateSnapshot


class TestStateMachineBasicOperations:
    """Test basic KV operations."""
    
    @pytest.fixture
    def engine(self):
        return StateMachineEngine("node-1")
    
    @pytest.mark.asyncio
    async def test_set_operation(self, engine):
        """Test SET operation."""
        result = await engine.apply_command(1, 1, {"op": "set", "key": "x", "value": 10})
        assert result["ok"] is True
        assert result["key"] == "x"
        assert engine.data["x"] == 10
        assert engine.applied_index == 1
    
    @pytest.mark.asyncio
    async def test_get_operation(self, engine):
        """Test GET operation."""
        await engine.apply_command(1, 1, {"op": "set", "key": "x", "value": 10})
        result = await engine.apply_command(2, 1, {"op": "get", "key": "x"})
        assert result["ok"] is True
        assert result["value"] == 10
    
    @pytest.mark.asyncio
    async def test_get_missing_key(self, engine):
        """Test GET on missing key."""
        result = await engine.apply_command(1, 1, {"op": "get", "key": "missing"})
        assert "error" in result
    
    @pytest.mark.asyncio
    async def test_delete_operation(self, engine):
        """Test DELETE operation."""
        await engine.apply_command(1, 1, {"op": "set", "key": "x", "value": 10})
        result = await engine.apply_command(2, 1, {"op": "delete", "key": "x"})
        assert result["ok"] is True
        assert result["deleted"] is True
        assert "x" not in engine.data
    
    @pytest.mark.asyncio
    async def test_delete_missing_key(self, engine):
        """Test DELETE on missing key."""
        result = await engine.apply_command(1, 1, {"op": "delete", "key": "missing"})
        assert result["ok"] is True
        assert result["deleted"] is False
    
    @pytest.mark.asyncio
    async def test_scan_operation(self, engine):
        """Test SCAN operation."""
        await engine.apply_command(1, 1, {"op": "set", "key": "a", "value": 1})
        await engine.apply_command(2, 1, {"op": "set", "key": "b", "value": 2})
        await engine.apply_command(3, 1, {"op": "set", "key": "c", "value": 3})
        
        result = await engine.apply_command(4, 1, {"op": "scan", "pattern": "", "limit": 100})
        assert result["ok"] is True
        assert result["count"] == 3
        assert len(result["results"]) == 3
    
    @pytest.mark.asyncio
    async def test_scan_with_pattern(self, engine):
        """Test SCAN with pattern matching."""
        await engine.apply_command(1, 1, {"op": "set", "key": "user:1", "value": "alice"})
        await engine.apply_command(2, 1, {"op": "set", "key": "user:2", "value": "bob"})
        await engine.apply_command(3, 1, {"op": "set", "key": "post:1", "value": "hello"})
        
        result = await engine.apply_command(4, 1, {"op": "scan", "pattern": "user", "limit": 100})
        assert result["count"] == 2
    
    @pytest.mark.asyncio
    async def test_cas_success(self, engine):
        """Test CAS (Compare-And-Swap) success."""
        await engine.apply_command(1, 1, {"op": "set", "key": "x", "value": 10})
        result = await engine.apply_command(2, 1, {"op": "cas", "key": "x", "expected": 10, "new_value": 20})
        assert result["ok"] is True
        assert result["swapped"] is True
        assert engine.data["x"] == 20
    
    @pytest.mark.asyncio
    async def test_cas_failure(self, engine):
        """Test CAS (Compare-And-Swap) failure."""
        await engine.apply_command(1, 1, {"op": "set", "key": "x", "value": 10})
        result = await engine.apply_command(2, 1, {"op": "cas", "key": "x", "expected": 5, "new_value": 20})
        assert result["ok"] is False
        assert result["swapped"] is False
        assert engine.data["x"] == 10


class TestIdempotency:
    """Test idempotent operation handling."""
    
    @pytest.fixture
    def engine(self):
        return StateMachineEngine("node-1")
    
    @pytest.mark.asyncio
    async def test_duplicate_command_ignored(self, engine):
        """Test duplicate commands are ignored."""
        cmd = {"op": "set", "key": "x", "value": 10}
        result1 = await engine.apply_command(1, 1, cmd)
        result2 = await engine.apply_command(1, 1, cmd)
        
        # Second call should return None (already applied)
        assert result2 is None
        assert engine.applied_index == 1
    
    @pytest.mark.asyncio
    async def test_later_command_not_reapplied(self, engine):
        """Test that later commands aren't reapplied."""
        await engine.apply_command(1, 1, {"op": "set", "key": "x", "value": 10})
        await engine.apply_command(2, 1, {"op": "set", "key": "y", "value": 20})
        
        # Trying to apply command at earlier index
        result = await engine.apply_command(1, 1, {"op": "set", "key": "z", "value": 30})
        assert result is None
        assert "z" not in engine.data


class TestTransactionSupport:
    """Test transaction functionality."""
    
    @pytest.fixture
    def engine(self):
        return StateMachineEngine("node-1")
    
    def test_begin_transaction(self, engine):
        """Test beginning a transaction."""
        result = engine.begin_transaction("tx-1")
        assert result["ok"] is True
        assert "tx-1" in engine.pending_transactions
    
    def test_begin_duplicate_transaction(self, engine):
        """Test starting duplicate transaction."""
        engine.begin_transaction("tx-1")
        result = engine.begin_transaction("tx-1")
        assert "error" in result
    
    def test_commit_transaction(self, engine):
        """Test committing a transaction."""
        engine.begin_transaction("tx-1")
        result = engine.commit_transaction("tx-1")
        assert result["ok"] is True
        assert "tx-1" not in engine.pending_transactions
    
    def test_commit_nonexistent_transaction(self, engine):
        """Test committing non-existent transaction."""
        result = engine.commit_transaction("tx-1")
        assert "error" in result
    
    @pytest.mark.asyncio
    async def test_transaction_with_multiple_operations(self, engine):
        """Test transaction with multiple operations."""
        engine.begin_transaction("tx-1")
        
        await engine.apply_command(1, 1, {"op": "set", "key": "a", "value": 1, "tx_id": "tx-1"})
        await engine.apply_command(2, 1, {"op": "set", "key": "b", "value": 2, "tx_id": "tx-1"})
        
        result = engine.commit_transaction("tx-1")
        assert result["ok"] is True
        assert engine.data["a"] == 1
        assert engine.data["b"] == 2


class TestDuplicateTransactionDetection:
    """Test client-level duplicate detection."""
    
    @pytest.fixture
    def engine(self):
        return StateMachineEngine("node-1")
    
    @pytest.mark.asyncio
    async def test_duplicate_transaction_cached(self, engine):
        """Test duplicate transactions return cached result."""
        cmd1 = {"op": "set", "key": "x", "value": 10, "client_id": "c1", "tx_id": "tx-1"}
        result1 = await engine.apply_command(1, 1, cmd1)
        
        # Same tx_id from same client with different index should return cached result
        result2 = await engine.apply_command(2, 1, cmd1)
        
        assert result2 == result1
        # applied_index stays at 1 because duplicate is detected and not reapplied
        assert engine.applied_index == 1
    
    @pytest.mark.asyncio
    async def test_different_clients_different_cache(self, engine):
        """Test different clients have separate transaction caches."""
        cmd1 = {"op": "set", "key": "x", "value": 10, "client_id": "c1", "tx_id": "tx-1"}
        cmd2 = {"op": "set", "key": "x", "value": 20, "client_id": "c2", "tx_id": "tx-1"}
        
        await engine.apply_command(1, 1, cmd1)
        result2 = await engine.apply_command(2, 1, cmd2)
        
        # Different client should apply the command, not return cached result
        assert result2["ok"] is True
        assert engine.data["x"] == 20


class TestReadOnlyOperations:
    """Test linearizable read consistency."""
    
    @pytest.fixture
    def engine(self):
        return StateMachineEngine("node-1")
    
    @pytest.mark.asyncio
    async def test_read_only_get(self, engine):
        """Test read-only GET."""
        await engine.apply_command(1, 1, {"op": "set", "key": "x", "value": 10})
        result = await engine.apply_read_only({"op": "get", "key": "x"}, 1)
        assert result["ok"] is True
        assert result["value"] == 10
    
    @pytest.mark.asyncio
    async def test_read_only_scan(self, engine):
        """Test read-only SCAN."""
        await engine.apply_command(1, 1, {"op": "set", "key": "a", "value": 1})
        await engine.apply_command(2, 1, {"op": "set", "key": "b", "value": 2})
        
        result = await engine.apply_read_only({"op": "scan", "pattern": "", "limit": 100}, 2)
        assert result["ok"] is True
        assert result["count"] == 2
    
    @pytest.mark.asyncio
    async def test_read_only_rejects_writes(self, engine):
        """Test read-only operations reject write commands."""
        result = await engine.apply_read_only({"op": "set", "key": "x", "value": 10}, 0)
        assert "error" in result


class TestSnapshotAndRestore:
    """Test snapshot functionality."""
    
    @pytest.fixture
    def engine(self):
        return StateMachineEngine("node-1")
    
    @pytest.mark.asyncio
    async def test_take_snapshot(self, engine):
        """Test taking a snapshot."""
        await engine.apply_command(1, 1, {"op": "set", "key": "x", "value": 10})
        await engine.apply_command(2, 1, {"op": "set", "key": "y", "value": 20})
        
        snapshot = engine.take_snapshot(2, 1)
        assert snapshot.applied_index == 2
        assert snapshot.term == 1
        assert snapshot.data == {"x": 10, "y": 20}
    
    @pytest.mark.asyncio
    async def test_restore_snapshot(self, engine):
        """Test restoring from snapshot."""
        # Create initial state
        await engine.apply_command(1, 1, {"op": "set", "key": "x", "value": 10})
        await engine.apply_command(2, 1, {"op": "set", "key": "y", "value": 20})
        snapshot = engine.take_snapshot(2, 1)
        
        # Create new engine and restore
        engine2 = StateMachineEngine("node-1")
        engine2.restore_snapshot(snapshot)
        
        assert engine2.applied_index == 2
        assert engine2.last_applied_term == 1
        assert engine2.data == {"x": 10, "y": 20}
    
    @pytest.mark.asyncio
    async def test_snapshot_independence(self, engine):
        """Test snapshots are independent copies."""
        await engine.apply_command(1, 1, {"op": "set", "key": "x", "value": 10})
        snapshot = engine.take_snapshot(1, 1)
        
        # Modify engine
        await engine.apply_command(2, 1, {"op": "set", "key": "y", "value": 20})
        
        # Snapshot shouldn't change
        assert len(snapshot.data) == 1
        assert len(engine.data) == 2


class TestStatus:
    """Test status reporting."""
    
    @pytest.fixture
    def engine(self):
        return StateMachineEngine("node-1")
    
    @pytest.mark.asyncio
    async def test_initial_status(self, engine):
        """Test initial status."""
        status = engine.get_status()
        assert status["node_id"] == "node-1"
        assert status["applied_index"] == 0
        assert status["data_size"] == 0
    
    @pytest.mark.asyncio
    async def test_status_after_operations(self, engine):
        """Test status after operations."""
        await engine.apply_command(1, 1, {"op": "set", "key": "x", "value": 10})
        await engine.apply_command(2, 1, {"op": "set", "key": "y", "value": 20})
        
        status = engine.get_status()
        assert status["applied_index"] == 2
        assert status["data_size"] == 2
        assert status["total_keys"] == 2
    
    def test_string_representation(self, engine):
        """Test string representation."""
        s = str(engine)
        assert "node-1" in s
        assert "applied=" in s


class TestErrorHandling:
    """Test error handling."""
    
    @pytest.fixture
    def engine(self):
        return StateMachineEngine("node-1")
    
    @pytest.mark.asyncio
    async def test_missing_key_in_set(self, engine):
        """Test SET with missing key."""
        result = await engine.apply_command(1, 1, {"op": "set", "value": 10})
        assert "error" in result
    
    @pytest.mark.asyncio
    async def test_missing_key_in_get(self, engine):
        """Test GET with missing key."""
        result = await engine.apply_command(1, 1, {"op": "get"})
        assert "error" in result
    
    @pytest.mark.asyncio
    async def test_unknown_operation(self, engine):
        """Test unknown operation."""
        result = await engine.apply_command(1, 1, {"op": "unknown"})
        assert "error" in result
    
    @pytest.mark.asyncio
    async def test_cas_missing_key(self, engine):
        """Test CAS with missing key."""
        result = await engine.apply_command(1, 1, {"op": "cas", "expected": 10, "new_value": 20})
        assert "error" in result


class TestConcurrentOperations:
    """Test concurrent operations."""
    
    @pytest.fixture
    def engine(self):
        return StateMachineEngine("node-1")
    
    @pytest.mark.asyncio
    async def test_concurrent_sets(self, engine):
        """Test concurrent SET operations."""
        tasks = []
        for i in range(10):
            cmd = {"op": "set", "key": f"key{i}", "value": i}
            tasks.append(engine.apply_command(i + 1, 1, cmd))
        
        results = await asyncio.gather(*tasks)
        assert all(r["ok"] is True for r in results)
        assert len(engine.data) == 10
    
    @pytest.mark.asyncio
    async def test_concurrent_mixed_operations(self, engine):
        """Test concurrent mixed operations."""
        # Set initial values
        await engine.apply_command(1, 1, {"op": "set", "key": "a", "value": 1})
        await engine.apply_command(2, 1, {"op": "set", "key": "b", "value": 2})
        
        tasks = [
            engine.apply_command(3, 1, {"op": "get", "key": "a"}),
            engine.apply_command(4, 1, {"op": "get", "key": "b"}),
            engine.apply_command(5, 1, {"op": "set", "key": "c", "value": 3}),
        ]
        
        results = await asyncio.gather(*tasks)
        assert len(results) == 3


class TestEdgeCases:
    """Test edge cases."""
    
    @pytest.fixture
    def engine(self):
        return StateMachineEngine("node-1")
    
    @pytest.mark.asyncio
    async def test_large_value(self, engine):
        """Test storing large values."""
        large_value = "x" * 1000000  # 1MB
        result = await engine.apply_command(1, 1, {"op": "set", "key": "large", "value": large_value})
        assert result["ok"] is True
        assert len(engine.data["large"]) == 1000000
    
    @pytest.mark.asyncio
    async def test_special_characters_in_key(self, engine):
        """Test special characters in keys."""
        key = "user:123:profile:name"
        result = await engine.apply_command(1, 1, {"op": "set", "key": key, "value": "alice"})
        assert result["ok"] is True
        assert engine.data[key] == "alice"
    
    @pytest.mark.asyncio
    async def test_none_and_falsy_values(self, engine):
        """Test storing None and falsy values."""
        await engine.apply_command(1, 1, {"op": "set", "key": "null", "value": None})
        await engine.apply_command(2, 1, {"op": "set", "key": "false", "value": False})
        await engine.apply_command(3, 1, {"op": "set", "key": "zero", "value": 0})
        
        result_null = await engine.apply_command(4, 1, {"op": "get", "key": "null"})
        result_false = await engine.apply_command(5, 1, {"op": "get", "key": "false"})
        result_zero = await engine.apply_command(6, 1, {"op": "get", "key": "zero"})
        
        assert result_null["value"] is None
        assert result_false["value"] is False
        assert result_zero["value"] == 0
    
    @pytest.mark.asyncio
    async def test_scan_with_limit(self, engine):
        """Test SCAN respects limit."""
        for i in range(100):
            await engine.apply_command(i + 1, 1, {"op": "set", "key": f"k{i}", "value": i})
        
        result = await engine.apply_command(101, 1, {"op": "scan", "pattern": "", "limit": 10})
        assert result["count"] == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
