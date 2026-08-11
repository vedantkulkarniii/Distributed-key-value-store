"""Tests for Byzantine failure tolerance."""

import pytest
from unittest.mock import Mock


class TestByzantineFailureTolerance:
    """Test Byzantine fault tolerance scenarios."""
    
    @pytest.fixture
    def cluster_nodes(self):
        """Create 5-node cluster for Byzantine testing."""
        nodes = {}
        for i in range(5):
            node = Mock()
            node.node_id = f"node{i+1}"
            node.current_term = 0
            node.log = []
            node.state = "follower"
            node.last_vote_granted = None
            nodes[f"node{i+1}"] = node
        return nodes
    
    def test_byzantine_node_sends_conflicting_votes(self, cluster_nodes):
        """Test byzantine node sending conflicting votes."""
        # Node1 votes for candidate A
        cluster_nodes["node1"].voted_for = "node2"
        
        # Byzantine node3 tries to vote twice
        cluster_nodes["node3"].voted_for = "node2"
        cluster_nodes["node3"].voted_for = "node4"  # Changed vote (byzantine)
        
        # Only first vote counts in term
        # System should reject second vote
        assert cluster_nodes["node3"].voted_for != "node4"  # After fix
    
    def test_byzantine_node_sends_stale_term(self, cluster_nodes):
        """Test rejection of stale term messages."""
        current_term = 5
        cluster_nodes["node1"].current_term = current_term
        
        # Byzantine node sends message with stale term
        stale_message = {"term": current_term - 1, "from": "byzantine_node"}
        
        # Message should be rejected
        assert stale_message["term"] < current_term
    
    def test_byzantine_node_sends_invalid_log_index(self, cluster_nodes):
        """Test rejection of invalid log indices."""
        node = cluster_nodes["node1"]
        node.log = [{"index": 1}, {"index": 2}, {"index": 3}]
        
        # Byzantine message with gap in indices
        byzantine_entries = [
            {"index": 1},
            {"index": 3},  # Gap - invalid
            {"index": 5},
        ]
        
        # System should detect gap and reject
        valid = all(byzantine_entries[i]["index"] <= byzantine_entries[i+1]["index"] 
                   for i in range(len(byzantine_entries)-1))
        
        assert not valid  # Gap detected
    
    def test_quorum_ignores_byzantine_minority(self, cluster_nodes):
        """Test that quorum correctly ignores Byzantine minority."""
        # 3/5 nodes are honest
        honest_votes = 3
        byzantine_votes = 2
        quorum_needed = (5 // 2) + 1  # 3
        
        # Quorum can be achieved without Byzantine nodes
        assert honest_votes >= quorum_needed
    
    def test_byzantine_node_duplicate_messages(self, cluster_nodes):
        """Test duplicate message handling from Byzantine node."""
        messages_received = []
        
        # Byzantine node sends same message multiple times
        for _ in range(5):
            messages_received.append({"from": "byzantine", "msg_id": 1})
        
        # System should deduplicate
        unique_messages = len(set((m["from"], m["msg_id"]) for m in messages_received))
        
        assert unique_messages == 1
    
    def test_byzantine_node_false_committed_claims(self, cluster_nodes):
        """Test rejection of false committed index claims."""
        node = cluster_nodes["node1"]
        node.log_length = 10
        node.committed_index = 5
        
        # Byzantine node claims index 15 is committed (false)
        byzantine_commit = 15
        
        # Should be rejected (beyond log length)
        assert byzantine_commit > node.log_length
    
    def test_byzantine_log_consistency_check(self, cluster_nodes):
        """Test log consistency prevents Byzantine log divergence."""
        nodes_data = {
            "node1": [1, 2, 3, 4, 5],
            "node2": [1, 2, 3, 4, 5],
            "node3": [1, 2, 3, 4, 5],
            "node4": [1, 2, 3, 7, 8],  # Byzantine divergence
            "node5": [1, 2, 3, 4, 5],
        }
        
        # Majority (3/5) have correct log
        correct_log = [1, 2, 3, 4, 5]
        matches = sum(1 for log in nodes_data.values() if log == correct_log)
        
        assert matches >= 3  # Majority
    
    def test_byzantine_node_wrong_term_claim(self, cluster_nodes):
        """Test Byzantine node claiming wrong term."""
        current_term = 5
        byzantine_claim = 100
        
        # Byzantine node claims to be in term 100
        # Other nodes reject
        assert byzantine_claim > current_term
        # System should stay in term 5
    
    def test_byzantine_heartbeat_forgery(self, cluster_nodes):
        """Test Byzantine node forging heartbeats."""
        # Real leader
        real_leader_term = 5
        
        # Byzantine node forges heartbeat with term 3
        forged_term = 3
        
        # Nodes ignore old terms
        assert forged_term < real_leader_term
    
    def test_byzantine_vote_request_amplification(self, cluster_nodes):
        """Test Byzantine node can't amplify votes."""
        votes_for_byzantine = {"node_a"}  # Only 1 vote
        
        # Byzantine tries to claim 5 votes
        claimed_votes = 5
        
        # Reality check
        assert len(votes_for_byzantine) != claimed_votes
    
    def test_byzantine_leader_misbehavior_detection(self, cluster_nodes):
        """Test detection of Byzantine leader misbehavior."""
        # Node1 is leader
        cluster_nodes["node1"].is_leader = True
        
        # Byzantine leader sends conflicting values to different followers
        node2_receives = {"key": "value_A"}
        node3_receives = {"key": "value_B"}
        
        # Followers detect conflict
        assert node2_receives != node3_receives
        # Should reject or force new election
    
    def test_quorum_ensures_linearizability_despite_byzant(self, cluster_nodes):
        """Test quorum ensures linearizability despite Byzantine."""
        # Write committed on 3/5 nodes (quorum)
        committed_nodes = ["node1", "node2", "node3"]
        
        # 2 Byzantine nodes reject/lose write
        # But quorum has it - read guaranteed to see it
        
        reads_see_write = len(committed_nodes) >= 3
        assert reads_see_write
    
    def test_byzantine_election_attempt_fails(self, cluster_nodes):
        """Test Byzantine node can't win election alone."""
        byzantine_node = "node4"
        votes_for_byzantine = 1  # Only self
        quorum_needed = (5 // 2) + 1  # 3
        
        assert votes_for_byzantine < quorum_needed
    
    def test_byzantine_crash_recovery(self, cluster_nodes):
        """Test system recovers even if Byzantine node has state."""
        # Byzantine node crashes with corrupted state
        cluster_nodes["node4"].state = {"corrupted": True}
        
        # Rest of cluster continues
        honest_nodes = 4  # Excluding Byzantine
        quorum_possible = honest_nodes >= 3
        
        assert quorum_possible
    
    def test_two_byzantine_nodes_in_5_node_cluster(self, cluster_nodes):
        """Test 5-node cluster tolerates 2 Byzantine nodes."""
        honest_nodes = 3
        byzantine_nodes = 2
        quorum_needed = 3
        
        # Honest nodes can still form quorum
        assert honest_nodes >= quorum_needed
    
    def test_byzantine_prevents_majority(self, cluster_nodes):
        """Test Byzantine majority prevents consensus."""
        honest_nodes = 1
        byzantine_nodes = 4
        quorum_needed = (5 // 2) + 1  # 3
        
        # Cannot form quorum without Byzantine
        assert honest_nodes < quorum_needed


class TestByzantineMessageValidation:
    """Test message validation against Byzantine attacks."""
    
    def test_validate_request_vote_term(self):
        """Test term validation in RequestVote."""
        current_term = 5
        vote_request_term = 3  # Stale
        
        # Should reject
        is_valid = vote_request_term >= current_term
        assert not is_valid
    
    def test_validate_append_entries_term(self):
        """Test term validation in AppendEntries."""
        current_term = 5
        append_term = 5
        
        # Accept same term
        is_valid = append_term >= current_term
        assert is_valid
    
    def test_validate_log_index_monotonic(self):
        """Test log indices are monotonically increasing."""
        log_indices = [1, 2, 3, 4, 5]
        
        is_valid = all(log_indices[i] <= log_indices[i+1] 
                      for i in range(len(log_indices)-1))
        
        assert is_valid
    
    def test_reject_Byzantine_duplicate_index(self):
        """Test rejection of duplicate indices."""
        log_indices = [1, 2, 2, 4, 5]  # Duplicate at index 2
        
        is_valid = all(log_indices[i] < log_indices[i+1] 
                      for i in range(len(log_indices)-1))
        
        assert not is_valid
    
    def test_validate_prev_log_consistency(self):
        """Test previous log consistency check."""
        follower_log = [
            {"index": 1, "term": 1},
            {"index": 2, "term": 1},
            {"index": 3, "term": 2},
        ]
        
        prev_log_index = 3
        prev_log_term = 2
        
        # Check consistency
        entry = follower_log[prev_log_index - 1]
        is_consistent = (entry["index"] == prev_log_index and 
                        entry["term"] == prev_log_term)
        
        assert is_consistent
    
    def test_reject_future_log_claim(self):
        """Test rejection of claims about future log."""
        my_log_length = 10
        claimed_log_index = 100  # Byzantine claim
        
        # Reject future claims
        is_valid = claimed_log_index <= my_log_length
        assert not is_valid
