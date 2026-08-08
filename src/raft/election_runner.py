"""
Election runner orchestration (Phase 3).

Coordinates complete election campaigns across multi-node clusters.
Handles RequestVote RPC broadcasting and vote collection.
"""

import logging
import asyncio
from typing import Dict, List, Optional, Set
from src.raft.state import NodeRole
from src.raft.election import VoteCounter


logger = logging.getLogger(__name__)


class ElectionRunner:
    """
    Orchestrates a complete election campaign.
    
    Coordinates:
    - Broadcasting RequestVote to peers
    - Collecting votes and rejections
    - Determining election winner
    - Handling timeouts and failures
    """
    
    def __init__(self, node_id: str, peers: List[str]):
        """
        Initialize election runner.
        
        Args:
            node_id: This node's ID
            peers: List of peer node IDs
        """
        self.node_id = node_id
        self.peers = peers
        self.cluster_size = len(peers) + 1  # Include self
        
        self.vote_counter: Optional[VoteCounter] = None
        self.election_term: int = 0
        self.election_in_progress = False
        
        logger.debug(
            f"Node {node_id}: Initialized election runner "
            f"(cluster_size={self.cluster_size})"
        )
    
    async def start_election(self, term: int, timeout: float = 0.5) -> bool:
        """
        Start a new election campaign.
        
        Args:
            term: Term for this election
            timeout: Timeout for election in seconds
            
        Returns:
            True if won election, False if lost or timed out
        """
        logger.info(
            f"Node {self.node_id}: Starting election (term={term})"
        )
        
        self.election_term = term
        self.election_in_progress = True
        self.vote_counter = VoteCounter(self.node_id, total_nodes=self.cluster_size)
        
        try:
            # Broadcast RequestVote to all peers
            await self._broadcast_request_vote(term)
            
            # Wait for votes or timeout
            result = await asyncio.wait_for(
                self._wait_for_election(),
                timeout=timeout
            )
            
            logger.info(
                f"Node {self.node_id}: Election completed "
                f"(term={term}, won={result})"
            )
            
            return result
            
        except asyncio.TimeoutError:
            logger.warning(
                f"Node {self.node_id}: Election timed out (term={term})"
            )
            return False
        
        finally:
            self.election_in_progress = False
    
    async def _broadcast_request_vote(self, term: int) -> None:
        """
        Broadcast RequestVote RPC to all peers.
        
        In real implementation, would send actual RPC.
        Here we just prepare the request.
        
        Args:
            term: Election term
        """
        logger.debug(
            f"Node {self.node_id}: Broadcasting RequestVote "
            f"to {len(self.peers)} peers (term={term})"
        )
        
        # In real system:
        # - Create RequestVote message
        # - Send to all peers asynchronously
        # - Collect responses
        
        # For now, just log
        for peer_id in self.peers:
            logger.debug(
                f"Node {self.node_id}: Sending RequestVote to {peer_id}"
            )
    
    async def _wait_for_election(self) -> bool:
        """
        Wait for election results.
        
        Returns:
            True if won, False otherwise
        """
        assert self.vote_counter is not None
        
        # In real system, would wait for actual RPC responses
        # Here we simulate waiting
        while self.election_in_progress:
            # Check if we have quorum
            if self.vote_counter.has_quorum():
                logger.info(
                    f"Node {self.node_id}: Won election "
                    f"({len(self.vote_counter.votes_received)} votes)"
                )
                return True
            
            # Check if we can still win
            if not self.vote_counter.can_still_win():
                logger.warning(
                    f"Node {self.node_id}: Lost election "
                    f"({len(self.vote_counter.votes_rejected)} rejections)"
                )
                return False
            
            # Wait a bit before checking again
            await asyncio.sleep(0.001)
            
            # In real system: wait for RPC response
            break
        
        return False
    
    def receive_vote(self, peer_id: str) -> None:
        """
        Record vote from peer.
        
        Args:
            peer_id: Peer that voted for us
        """
        if self.vote_counter is None:
            logger.warning(
                f"Node {self.node_id}: Received vote but no election in progress"
            )
            return
        
        logger.debug(
            f"Node {self.node_id}: Received vote from {peer_id}"
        )
        
        self.vote_counter.record_vote(peer_id)
    
    def receive_rejection(self, peer_id: str) -> None:
        """
        Record vote rejection from peer.
        
        Args:
            peer_id: Peer that rejected our vote request
        """
        if self.vote_counter is None:
            logger.warning(
                f"Node {self.node_id}: Received rejection but no election in progress"
            )
            return
        
        logger.debug(
            f"Node {self.node_id}: Received rejection from {peer_id}"
        )
        
        self.vote_counter.record_rejection(peer_id)
    
    def get_election_status(self) -> Dict:
        """
        Get current election status.
        
        Returns:
            Dict with election status
        """
        if self.vote_counter is None:
            return {
                "node_id": self.node_id,
                "in_progress": False,
                "term": self.election_term,
            }
        
        return {
            "node_id": self.node_id,
            "in_progress": self.election_in_progress,
            "term": self.election_term,
            "votes_received": len(self.vote_counter.votes_received),
            "votes_rejected": len(self.vote_counter.votes_rejected),
            "quorum": self.vote_counter.quorum,
            "has_quorum": self.vote_counter.has_quorum(),
            "can_still_win": self.vote_counter.can_still_win(),
        }


class MultiNodeElectionOrchestrator:
    """
    Orchestrates elections across multiple nodes.
    
    Coordinates:
    - Individual node elections
    - Peer communication
    - Leader determination
    """
    
    def __init__(self, node_ids: List[str]):
        """
        Initialize orchestrator.
        
        Args:
            node_ids: List of all node IDs in cluster
        """
        self.node_ids = node_ids
        self.runners: Dict[str, ElectionRunner] = {}
        self.leaders: Dict[int, str] = {}  # term -> leader_id
        
        for node_id in node_ids:
            peers = [n for n in node_ids if n != node_id]
            self.runners[node_id] = ElectionRunner(node_id, peers)
        
        logger.info(
            f"Orchestrator: Initialized for {len(node_ids)} nodes"
        )
    
    async def run_election(self, term: int, timeout: float = 0.5) -> Optional[str]:
        """
        Run election for all nodes simultaneously.
        
        Args:
            term: Election term
            timeout: Timeout for election
            
        Returns:
            ID of elected leader, or None if no leader
        """
        logger.info(
            f"Orchestrator: Running election for term {term}"
        )
        
        # Start elections on all nodes
        tasks = [
            self._run_node_election(node_id, term, timeout)
            for node_id in self.node_ids
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Find winner
        for node_id, won in zip(self.node_ids, results):
            if isinstance(won, bool) and won:
                logger.info(
                    f"Orchestrator: {node_id} won election (term={term})"
                )
                self.leaders[term] = node_id
                return node_id
        
        logger.warning(
            f"Orchestrator: No leader elected for term {term}"
        )
        return None
    
    async def _run_node_election(
        self, node_id: str, term: int, timeout: float
    ) -> bool:
        """
        Run election for a single node.
        
        Args:
            node_id: Node to run election for
            term: Election term
            timeout: Election timeout
            
        Returns:
            True if node won, False otherwise
        """
        runner = self.runners[node_id]
        return await runner.start_election(term, timeout)
    
    def get_cluster_status(self) -> Dict:
        """
        Get status of all nodes.
        
        Returns:
            Dict with status of each node
        """
        return {
            node_id: runner.get_election_status()
            for node_id, runner in self.runners.items()
        }
