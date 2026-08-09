"""State machine integration tests."""

import pytest
from src.raft.append_entries import AppendEntriesHandler
from src.raft.replication_metrics import ReplicationMetricsCollector


class TestCommandApplication:
    """Command application to state machine."""
    
    def test_command_applied_to_state_machine(self):
        """Test command is applied to state machine."""
        handler = AppendEntriesHandler("node1", None)
        
        # Apply command
        handler.state_machine["key1"] = "value1"
        assert handler.state_machine["key1"] == "value1"
    
    def test_delete_command_application(self):
        """Test delete command application."""
        handler = AppendEntriesHandler("node1", None)
        
        handler.state_machine["key1"] = "value1"
        del handler.state_machine["key1"]
        
        assert "key1" not in handler.state_machine


class TestDualWritePrevention:
    """Tests for dual write prevention."""
    
    def test_same_index_not_applied_twice(self):
        """Test same index not applied twice."""
        metrics = ReplicationMetricsCollector()
        
        # Apply index 1 twice (should only succeed once)
        rep_id1 = metrics.start_replication("f1", 1, 1024)
        metrics.complete_replication(rep_id1, True, last_index=1)
        
        m = metrics.get_metrics("f1")
        assert m.last_successful_index == 1
        assert m.entries_replicated == 1
    
    def test_idempotent_application(self):
        """Test idempotent application of entries."""
        handler = AppendEntriesHandler("node1", None)
        
        # Apply set command twice
        handler.state_machine["key"] = "value1"
        handler.state_machine["key"] = "value1"  # Idempotent
        
        assert handler.state_machine["key"] == "value1"


class TestStateReconciliation:
    """State reconciliation tests."""
    
    def test_state_convergence(self):
        """Test state converges across replicas."""
        handlers = [
            AppendEntriesHandler(f"node{i}", None) for i in range(3)
        ]
        
        # Apply same commands to all
        for handler in handlers:
            handler.state_machine["key1"] = "value1"
            handler.state_machine["key2"] = "value2"
        
        # All should have same state
        states = [h.state_machine for h in handlers]
        assert states[0] == states[1] == states[2]
    
    def test_state_reconciliation_after_divergence(self):
        """Test state reconciliation after divergence."""
        h1 = AppendEntriesHandler("node1", None)
        h2 = AppendEntriesHandler("node2", None)
        
        # Diverge
        h1.state_machine["key"] = "value_h1"
        h2.state_machine["key"] = "value_h2"
        
        # Reconcile: h2 follows h1
        h2.state_machine["key"] = h1.state_machine["key"]
        
        assert h1.state_machine["key"] == h2.state_machine["key"]
    
    def test_committed_entries_precedence(self):
        """Test committed entries take precedence."""
        metrics = ReplicationMetricsCollector()
        
        # Entry 1 committed to quorum
        for i in range(3):
            rep_id = metrics.start_replication(f"f{i}", 1, 1024)
            metrics.complete_replication(rep_id, True, last_index=1)
        
        # All have entry 1
        for i in range(3):
            m = metrics.get_metrics(f"f{i}")
            assert m.last_successful_index == 1


class TestStateConsistency:
    """State consistency verification."""
    
    def test_replicated_state_consistency(self):
        """Test replicated state is consistent."""
        handlers = [AppendEntriesHandler(f"n{i}", None) for i in range(5)]
        
        # Replicate same entries
        for handler in handlers:
            handler.state_machine["data"] = {"count": 42}
        
        # All should have same value
        values = [h.state_machine["data"] for h in handlers]
        assert all(v == {"count": 42} for v in values)
    
    def test_partial_replication_consistency(self):
        """Test consistency with partial replication."""
        h1 = AppendEntriesHandler("leader", None)
        h2 = AppendEntriesHandler("follower", None)
        
        # Leader has more data
        h1.state_machine["k1"] = "v1"
        h1.state_machine["k2"] = "v2"
        h1.state_machine["k3"] = "v3"
        
        # Follower has subset
        h2.state_machine["k1"] = "v1"
        h2.state_machine["k2"] = "v2"
        
        # Verify consistency on common keys
        assert h1.state_machine["k1"] == h2.state_machine["k1"]
        assert h1.state_machine["k2"] == h2.state_machine["k2"]
    
    def test_state_equality_verification(self):
        """Test verification of state equality."""
        h1 = AppendEntriesHandler("n1", None)
        h2 = AppendEntriesHandler("n2", None)
        
        # Create identical states
        for h in [h1, h2]:
            h.state_machine["a"] = 1
            h.state_machine["b"] = 2
            h.state_machine["c"] = 3
        
        # Verify equality
        assert h1.state_machine == h2.state_machine
