"""Tests for Byzantine failure tolerance."""

import pytest
from datetime import datetime, timedelta
from src.raft.byzantine_tolerance import (
    ByzantineTolerance,
    ByzantineLevel,
    NodeTrust,
)


class TestNodeTrust:
    """Test suite for NodeTrust."""
    
    def test_node_trust_creation(self):
        """Test creating node trust."""
        trust = NodeTrust("node1")
        
        assert trust.node_id == "node1"
        assert trust.trust_score == 1.0
        assert trust.total_interactions == 0
    
    def test_record_success(self):
        """Test recording successful interaction."""
        trust = NodeTrust("node1")
        
        trust.record_success()
        
        assert trust.successful_interactions == 1
        assert trust.total_interactions == 1
    
    def test_record_failure(self):
        """Test recording failed interaction."""
        trust = NodeTrust("node1")
        
        trust.record_failure()
        
        assert trust.failed_interactions == 1
        assert trust.trust_score < 1.0
    
    def test_trust_score_calculation(self):
        """Test trust score calculation."""
        trust = NodeTrust("node1")
        
        # 80% success rate
        for i in range(8):
            trust.record_success()
        for i in range(2):
            trust.record_failure()
        
        assert 0.7 < trust.trust_score < 0.9
    
    def test_is_trusted(self):
        """Test trust threshold check."""
        trust = NodeTrust("node1")
        
        assert trust.is_trusted(threshold=0.5)
        
        trust.record_failure()
        trust.record_failure()
        trust.record_failure()
        
        assert not trust.is_trusted(threshold=0.9)


class TestByzantineTolerance:
    """Test suite for ByzantineTolerance."""
    
    @pytest.fixture
    def tolerance_5node(self):
        """Fixture for 5-node Byzantine tolerance."""
        return ByzantineTolerance("node1", cluster_size=5)
    
    @pytest.fixture
    def tolerance_7node(self):
        """Fixture for 7-node Byzantine tolerance."""
        return ByzantineTolerance("node1", cluster_size=7)
    
    # Byzantine Tolerance Calculation Tests
    
    def test_byzantine_tolerance_5node(self, tolerance_5node):
        """Test Byzantine tolerance for 5 nodes."""
        # Can tolerate (5-1)//3 = 1 Byzantine node
        assert tolerance_5node.byzantine_tolerance == 1
    
    def test_byzantine_tolerance_7node(self, tolerance_7node):
        """Test Byzantine tolerance for 7 nodes."""
        # Can tolerate (7-1)//3 = 2 Byzantine nodes
        assert tolerance_7node.byzantine_tolerance == 2
    
    # Vote Validation Tests
    
    def test_validate_valid_vote(self, tolerance_5node):
        """Test validating valid vote."""
        is_valid, reason = tolerance_5node.validate_vote(
            voter_id="node2",
            candidate_id="node3",
            term=1,
            last_log_index=10
        )
        
        assert is_valid
        assert reason is None
    
    def test_validate_vote_invalid_ids(self, tolerance_5node):
        """Test validating vote with invalid IDs."""
        is_valid, reason = tolerance_5node.validate_vote(
            voter_id="",
            candidate_id="node3",
            term=1,
            last_log_index=10
        )
        
        assert not is_valid
        assert reason is not None
    
    def test_validate_vote_invalid_term(self, tolerance_5node):
        """Test validating vote with invalid term."""
        is_valid, reason = tolerance_5node.validate_vote(
            voter_id="node2",
            candidate_id="node3",
            term=-1,
            last_log_index=10
        )
        
        assert not is_valid
    
    # Vote Duplication Detection Tests
    
    def test_detect_duplicate_votes(self, tolerance_5node):
        """Test detecting duplicate votes."""
        votes = [
            {"voter_id": "node2", "candidate_id": "node1", "term": 1},
            {"voter_id": "node2", "candidate_id": "node1", "term": 1},  # Duplicate
            {"voter_id": "node3", "candidate_id": "node1", "term": 1},
        ]
        
        has_duplication, reason = tolerance_5node.detect_vote_duplication(1, votes)
        
        assert has_duplication
        assert "Duplicate" in reason
    
    def test_no_duplicate_votes(self, tolerance_5node):
        """Test when no duplicate votes exist."""
        votes = [
            {"voter_id": "node2", "candidate_id": "node1", "term": 1},
            {"voter_id": "node3", "candidate_id": "node1", "term": 1},
            {"voter_id": "node4", "candidate_id": "node1", "term": 1},
        ]
        
        has_duplication, reason = tolerance_5node.detect_vote_duplication(1, votes)
        
        assert not has_duplication
    
    # Conflicting Vote Detection Tests
    
    def test_detect_conflicting_votes(self, tolerance_5node):
        """Test detecting conflicting votes."""
        votes = [
            {"voter_id": "node2", "candidate_id": "node1", "term": 1},
            {"voter_id": "node2", "candidate_id": "node3", "term": 1},  # Conflict
        ]
        
        has_conflict, reason = tolerance_5node.detect_conflicting_votes(1, votes)
        
        assert has_conflict
        assert "Conflicting" in reason
    
    def test_no_conflicting_votes(self, tolerance_5node):
        """Test when no conflicting votes exist."""
        votes = [
            {"voter_id": "node2", "candidate_id": "node1", "term": 1},
            {"voter_id": "node3", "candidate_id": "node1", "term": 1},
            {"voter_id": "node4", "candidate_id": "node1", "term": 1},
        ]
        
        has_conflict, reason = tolerance_5node.detect_conflicting_votes(1, votes)
        
        assert not has_conflict
    
    # Equivocation Detection Tests
    
    def test_detect_equivocation(self, tolerance_5node):
        """Test detecting equivocation."""
        messages = [
            {"type": "append_entries", "term": 1},
            {"type": "request_vote", "term": 1},  # Same term, contradiction
        ]
        
        is_equivocating, reason = tolerance_5node.detect_equivocation("node2", messages)
        
        assert is_equivocating
    
    def test_no_equivocation(self, tolerance_5node):
        """Test when no equivocation."""
        messages = [
            {"type": "append_entries", "term": 1},
            {"type": "append_entries", "term": 2},
        ]
        
        is_equivocating, reason = tolerance_5node.detect_equivocation("node2", messages)
        
        assert not is_equivocating
    
    # Node Trust Tests
    
    def test_initialize_node_trust(self, tolerance_5node):
        """Test initializing node trust."""
        tolerance_5node.initialize_node_trust("node2")
        
        assert "node2" in tolerance_5node.node_trust
        assert tolerance_5node.node_trust["node2"].trust_score == 1.0
    
    def test_update_node_trust_success(self, tolerance_5node):
        """Test updating trust on success."""
        tolerance_5node.initialize_node_trust("node2")
        
        score = tolerance_5node.update_node_trust("node2", is_successful=True)
        
        assert score == 1.0
    
    def test_update_node_trust_failure(self, tolerance_5node):
        """Test updating trust on failure."""
        tolerance_5node.initialize_node_trust("node2")
        
        score = tolerance_5node.update_node_trust("node2", is_successful=False)
        
        assert score < 1.0
    
    # Quorum Tests
    
    def test_can_reach_quorum_5node(self, tolerance_5node):
        """Test quorum reachability for 5 nodes."""
        # Need 3 for quorum
        can_reach = tolerance_5node.can_reach_quorum({"node1", "node2", "node3"})
        
        assert can_reach
    
    def test_cannot_reach_quorum_5node(self, tolerance_5node):
        """Test when quorum not reachable."""
        # Only 2 nodes
        can_reach = tolerance_5node.can_reach_quorum({"node1", "node2"})
        
        assert not can_reach
    
    def test_can_reach_quorum_with_byzantine(self, tolerance_5node):
        """Test quorum with Byzantine nodes present."""
        # 5 nodes, can tolerate 1 Byzantine
        # Need 3 for quorum, have at least 3 trusted
        trusted = {"node1", "node2", "node3"}
        can_reach = tolerance_5node.can_reach_quorum(trusted)
        
        assert can_reach
    
    # Rate Limiting Tests
    
    def test_rate_limit_untrustworthy_node(self, tolerance_5node):
        """Test rate limiting low-trust node."""
        tolerance_5node.initialize_node_trust("node2")
        
        # Record failures to lower trust
        for i in range(10):
            tolerance_5node.update_node_trust("node2", is_successful=False)
        
        should_rate_limit = tolerance_5node.rate_limit_node("node2")
        
        assert should_rate_limit
    
    def test_no_rate_limit_trustworthy_node(self, tolerance_5node):
        """Test no rate limiting for high-trust node."""
        tolerance_5node.initialize_node_trust("node2")
        
        # Record successes
        for i in range(10):
            tolerance_5node.update_node_trust("node2", is_successful=True)
        
        should_rate_limit = tolerance_5node.rate_limit_node("node2")
        
        assert not should_rate_limit
    
    # Status Queries Tests
    
    def test_get_trusted_nodes(self, tolerance_5node):
        """Test getting trusted nodes."""
        for i in range(2, 5):
            tolerance_5node.initialize_node_trust(f"node{i}")
            tolerance_5node.update_node_trust(f"node{i}", is_successful=True)
        
        trusted = tolerance_5node.get_trusted_nodes(threshold=0.5)
        
        assert len(trusted) >= 3
    
    def test_get_byzantine_status(self, tolerance_5node):
        """Test getting Byzantine status."""
        status = tolerance_5node.get_byzantine_status()
        
        assert status["cluster_size"] == 5
        assert status["byzantine_tolerance"] == 1
    
    def test_get_node_status(self, tolerance_5node):
        """Test getting node status."""
        tolerance_5node.initialize_node_trust("node2")
        tolerance_5node.update_node_trust("node2", is_successful=True)
        
        status = tolerance_5node.get_node_status("node2")
        
        assert status is not None
        assert status["node_id"] == "node2"
        assert status["is_trusted"]
    
    # Edge Cases
    
    def test_byzantine_tolerance_minimal_cluster(self):
        """Test with minimal 3-node cluster."""
        tolerance = ByzantineTolerance("node1", cluster_size=3)
        
        # Can tolerate (3-1)//3 = 0 Byzantine nodes
        assert tolerance.byzantine_tolerance == 0
    
    def test_byzantine_tolerance_large_cluster(self):
        """Test with large 13-node cluster."""
        tolerance = ByzantineTolerance("node1", cluster_size=13)
        
        # Can tolerate (13-1)//3 = 4 Byzantine nodes
        assert tolerance.byzantine_tolerance == 4
    
    def test_multiple_anomalies_counted(self, tolerance_5node):
        """Test that multiple anomalies are counted."""
        # Create votes with issues
        votes1 = [
            {"voter_id": "node2", "candidate_id": "node1", "term": 1},
            {"voter_id": "node2", "candidate_id": "node1", "term": 1},  # Duplicate
        ]
        
        votes2 = [
            {"voter_id": "node3", "candidate_id": "node1", "term": 2},
            {"voter_id": "node3", "candidate_id": "node2", "term": 2},  # Conflict
        ]
        
        tolerance_5node.detect_vote_duplication(1, votes1)
        tolerance_5node.detect_conflicting_votes(2, votes2)
        
        assert tolerance_5node.detected_anomalies >= 2
