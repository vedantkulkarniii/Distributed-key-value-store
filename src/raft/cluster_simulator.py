"""
Multi-node cluster simulator for testing (Phase 3).

Simulates complete cluster behavior with elections.
"""

import asyncio
import logging
from typing import Dict, List, Optional
from src.raft.state import NodeRole, RaftState
from src.raft.election import VoteCounter

logger = logging.getLogger(__name__)


class ClusterSimulator:
    """Simulates a complete Raft cluster."""
    
    def __init__(self, node_ids: List[str]):
        """Initialize cluster."""
        self.node_ids = node_ids
        self.nodes: Dict[str, NodeRole] = {}
        self.term = 0
        
        for node_id in node_ids:
            self.nodes[node_id] = NodeRole(node_id)
        
        logger.info(f"Cluster initialized with {len(node_ids)} nodes")
    
    async def initialize(self) -> None:
        """Initialize all nodes as followers."""
        for node in self.nodes.values():
            await node.become_follower(term=0)
        logger.info("Cluster initialized (all followers)")
    
    async def trigger_election(self, term: int) -> Optional[str]:
        """
        Simulate election in cluster.
        
        Returns:
            ID of elected leader or None
        """
        logger.info(f"Cluster: Triggering election (term={term})")
        
        # Reset all nodes to followers first, then start election
        for node in self.nodes.values():
            if not node.is_follower():
                await node.become_follower(term=term)
        
        # Node 1 times out and becomes candidate
        candidate_id = self.node_ids[0]
        candidate = self.nodes[candidate_id]
        
        await candidate.become_candidate()
        new_term = candidate.current_term
        self.term = new_term
        
        # Other nodes see higher term
        for node_id in self.node_ids[1:]:
            self.nodes[node_id].advance_term(new_term)
            self.nodes[node_id].set_voted_for(candidate_id)
        
        # Candidate collects votes
        counter = VoteCounter(candidate_id, total_nodes=len(self.node_ids))
        for node_id in self.node_ids[1:]:
            counter.record_vote(node_id)
        
        if counter.has_quorum():
            await candidate.become_leader()
            logger.info(f"Cluster: {candidate_id} elected leader")
            return candidate_id
        
        return None
    
    def get_status(self) -> Dict:
        """Get cluster status."""
        return {
            "term": self.term,
            "nodes": {
                node_id: node.get_status()
                for node_id, node in self.nodes.items()
            }
        }


class ClusterScenarioRunner:
    """Runs predefined cluster scenarios."""
    
    def __init__(self, cluster_size: int):
        """Initialize runner."""
        self.node_ids = [f"node-{i}" for i in range(1, cluster_size + 1)]
        self.cluster = ClusterSimulator(self.node_ids)
    
    async def run_single_election(self) -> bool:
        """Run single election scenario."""
        await self.cluster.initialize()
        leader = await self.cluster.trigger_election(0)
        return leader is not None
    
    async def run_multiple_elections(self, num_elections: int) -> int:
        """Run multiple elections."""
        await self.cluster.initialize()
        
        successful = 0
        for i in range(num_elections):
            leader = await self.cluster.trigger_election(i)
            if leader:
                successful += 1
        
        return successful
    
    async def run_leader_failure_scenario(self) -> bool:
        """Simulate leader failure and re-election."""
        await self.cluster.initialize()
        
        # First election
        leader1 = await self.cluster.trigger_election(0)
        if not leader1:
            return False
        
        # Verify leader is actually in leader state
        if not self.cluster.nodes[leader1].is_leader():
            return False
        
        # Leader "fails" (becomes follower)
        await self.cluster.nodes[leader1].become_follower(term=self.cluster.term + 1)
        
        # Reinitialize cluster for new election
        await self.cluster.initialize()
        
        # New election
        leader2 = await self.cluster.trigger_election(0)
        
        return leader2 is not None
