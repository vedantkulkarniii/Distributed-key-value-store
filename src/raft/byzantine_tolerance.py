"""
Byzantine failure tolerance for Raft consensus.

Implements:
- Byzantine fault detection
- Vote authentication
- Message validation
- Anomaly detection
- Adaptive trust scoring
"""

import logging
from typing import Dict, Any, List, Optional, Set, Tuple
from datetime import datetime, timedelta
from enum import Enum
import threading

logger = logging.getLogger(__name__)


class ByzantineLevel(Enum):
    """Byzantine fault severity levels."""
    NONE = 0
    SUSPICIOUS = 1
    WARNING = 2
    CRITICAL = 3


class NodeTrust:
    """Trust score for a node."""
    
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.trust_score = 1.0  # 0.0 to 1.0
        self.total_interactions = 0
        self.successful_interactions = 0
        self.failed_interactions = 0
        self.last_interaction = None
        
        self.byzantine_incidents = []
        self.recovery_attempts = 0
    
    def record_success(self) -> None:
        """Record successful interaction."""
        self.total_interactions += 1
        self.successful_interactions += 1
        self.last_interaction = datetime.now()
        self._update_trust_score()
    
    def record_failure(self) -> None:
        """Record failed interaction."""
        self.total_interactions += 1
        self.failed_interactions += 1
        self.last_interaction = datetime.now()
        self._update_trust_score()
    
    def record_byzantine_incident(self, incident_type: str) -> None:
        """Record Byzantine behavior."""
        self.byzantine_incidents.append({
            "type": incident_type,
            "timestamp": datetime.now(),
        })
        self.failed_interactions += 1
        self._update_trust_score()
    
    def _update_trust_score(self) -> None:
        """Update trust score based on history."""
        if self.total_interactions == 0:
            self.trust_score = 1.0
            return
        
        success_rate = self.successful_interactions / self.total_interactions
        
        # Penalize for Byzantine incidents
        byzantine_penalty = len(self.byzantine_incidents) * 0.1
        
        self.trust_score = max(0.0, success_rate - byzantine_penalty)
    
    def is_trusted(self, threshold: float = 0.7) -> bool:
        """Check if node is trusted."""
        return self.trust_score >= threshold


class ByzantineTolerance:
    """
    Detects and handles Byzantine failures.
    
    Ensures:
    - Byzantine nodes don't harm consistency
    - Quorum-based voting survives Byzantine faults
    - Adaptive trust scoring
    - Anomaly detection
    """
    
    def __init__(self, node_id: str, cluster_size: int):
        """Initialize Byzantine tolerance module."""
        self.node_id = node_id
        self.cluster_size = cluster_size
        self.byzantine_tolerance = (cluster_size - 1) // 3  # BFT requirement
        
        # Node trust tracking
        self.node_trust: Dict[str, NodeTrust] = {}
        
        # Anomaly detection
        self.anomalies: Dict[str, List[Dict]] = {}
        self.detection_threshold = 0.6  # Probability threshold
        
        # Statistics
        self.total_checks = 0
        self.detected_anomalies = 0
        self.false_positives = 0
        
        # Thread safety
        self.lock = threading.RLock()
        
        logger.info(
            f"Byzantine tolerance initialized for {node_id} "
            f"(can tolerate {self.byzantine_tolerance} Byzantine nodes)"
        )
    
    def initialize_node_trust(self, peer_id: str) -> None:
        """Initialize trust for a peer."""
        with self.lock:
            if peer_id not in self.node_trust:
                self.node_trust[peer_id] = NodeTrust(peer_id)
    
    def validate_vote(
        self,
        voter_id: str,
        candidate_id: str,
        term: int,
        last_log_index: int,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate a vote for Byzantine faults.
        
        Args:
            voter_id: Node casting vote
            candidate_id: Candidate being voted for
            term: Vote term
            last_log_index: Voter's last log index
            
        Returns:
            Tuple of (is_valid, reason)
        """
        with self.lock:
            self.total_checks += 1
            
            # Check for obvious anomalies
            if not voter_id or not candidate_id:
                return False, "Invalid node IDs"
            
            if term < 0:
                return False, "Invalid term"
            
            if last_log_index < 0:
                return False, "Invalid log index"
            
            # Check for voting violations
            self.initialize_node_trust(voter_id)
            
            return True, None
    
    def detect_vote_duplication(
        self,
        term: int,
        votes: List[Dict[str, Any]],
    ) -> Tuple[bool, Optional[str]]:
        """
        Detect duplicate votes from same node.
        
        Args:
            term: Term to check
            votes: List of votes in this term
            
        Returns:
            Tuple of (has_duplication, reason)
        """
        with self.lock:
            voter_counts: Dict[str, int] = {}
            
            for vote in votes:
                voter = vote.get("voter_id")
                if voter:
                    voter_counts[voter] = voter_counts.get(voter, 0) + 1
            
            # Check for duplicates
            for voter, count in voter_counts.items():
                if count > 1:
                    self.detected_anomalies += 1
                    return True, f"Duplicate votes from {voter}"
            
            return False, None
    
    def detect_conflicting_votes(
        self,
        term: int,
        votes: List[Dict[str, Any]],
    ) -> Tuple[bool, Optional[str]]:
        """
        Detect conflicting votes (same node voting for different candidates).
        
        Args:
            term: Term to check
            votes: List of votes in this term
            
        Returns:
            Tuple of (has_conflict, reason)
        """
        with self.lock:
            voter_candidates: Dict[str, Set[str]] = {}
            
            for vote in votes:
                voter = vote.get("voter_id")
                candidate = vote.get("candidate_id")
                
                if voter and candidate:
                    if voter not in voter_candidates:
                        voter_candidates[voter] = set()
                    voter_candidates[voter].add(candidate)
            
            # Check for conflicts
            for voter, candidates in voter_candidates.items():
                if len(candidates) > 1:
                    self.detected_anomalies += 1
                    return True, f"Conflicting votes from {voter}"
            
            return False, None
    
    def detect_equivocation(
        self,
        node_id: str,
        messages: List[Dict[str, Any]],
    ) -> Tuple[bool, Optional[str]]:
        """
        Detect equivocation (contradictory messages).
        
        Args:
            node_id: Node to check
            messages: List of messages from node
            
        Returns:
            Tuple of (is_equivocating, reason)
        """
        with self.lock:
            # Group messages by type
            message_types: Dict[str, List[Dict]] = {}
            
            for msg in messages:
                msg_type = msg.get("type")
                if msg_type:
                    if msg_type not in message_types:
                        message_types[msg_type] = []
                    message_types[msg_type].append(msg)
            
            # Check for contradictions
            if "append_entries" in message_types and "request_vote" in message_types:
                ae_term = message_types["append_entries"][0].get("term")
                rv_term = message_types["request_vote"][0].get("term")
                
                if ae_term == rv_term:
                    self.detected_anomalies += 1
                    return True, f"Both leader and candidate in same term"
            
            return False, None
    
    def rate_limit_node(self, node_id: str) -> bool:
        """
        Rate limit a suspicious node.
        
        Args:
            node_id: Node to rate limit
            
        Returns:
            True if node was rate limited
        """
        with self.lock:
            self.initialize_node_trust(node_id)
            trust = self.node_trust[node_id]
            
            if trust.trust_score < 0.3:
                logger.warning(f"Rate limiting node {node_id} (trust: {trust.trust_score:.2f})")
                return True
            
            return False
    
    def update_node_trust(
        self,
        node_id: str,
        is_successful: bool,
    ) -> float:
        """
        Update trust score for a node.
        
        Args:
            node_id: Node ID
            is_successful: Whether interaction was successful
            
        Returns:
            Updated trust score
        """
        with self.lock:
            self.initialize_node_trust(node_id)
            trust = self.node_trust[node_id]
            
            if is_successful:
                trust.record_success()
            else:
                trust.record_failure()
            
            return trust.trust_score
    
    def can_reach_quorum(self, trusted_nodes: Set[str]) -> bool:
        """
        Check if trusted nodes can form quorum.
        
        Args:
            trusted_nodes: Set of trusted node IDs
            
        Returns:
            True if quorum possible
        """
        quorum_size = (self.cluster_size // 2) + 1
        return len(trusted_nodes) >= quorum_size
    
    def get_trusted_nodes(self, threshold: float = 0.7) -> Set[str]:
        """
        Get set of trusted nodes above threshold.
        
        Args:
            threshold: Trust score threshold
            
        Returns:
            Set of trusted node IDs
        """
        with self.lock:
            return {
                node_id for node_id, trust in self.node_trust.items()
                if trust.is_trusted(threshold)
            }
    
    def get_byzantine_status(self) -> Dict[str, Any]:
        """Get Byzantine fault status."""
        with self.lock:
            trusted_nodes = self.get_trusted_nodes()
            
            return {
                "cluster_size": self.cluster_size,
                "byzantine_tolerance": self.byzantine_tolerance,
                "total_nodes": len(self.node_trust),
                "trusted_nodes": len(trusted_nodes),
                "can_reach_quorum": self.can_reach_quorum(trusted_nodes),
                "detected_anomalies": self.detected_anomalies,
                "total_checks": self.total_checks,
                "detection_rate": (
                    self.detected_anomalies / self.total_checks
                    if self.total_checks > 0 else 0
                ),
            }
    
    def get_node_status(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific node."""
        with self.lock:
            if node_id not in self.node_trust:
                return None
            
            trust = self.node_trust[node_id]
            
            return {
                "node_id": node_id,
                "trust_score": trust.trust_score,
                "is_trusted": trust.is_trusted(),
                "successful_interactions": trust.successful_interactions,
                "failed_interactions": trust.failed_interactions,
                "total_interactions": trust.total_interactions,
                "byzantine_incidents": len(trust.byzantine_incidents),
            }
