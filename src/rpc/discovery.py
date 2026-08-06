"""
Peer discovery and bootstrap for Raft cluster.

Handles initial cluster formation, peer discovery, and connection establishment.
"""

import asyncio
import logging
from typing import List, Dict, Optional, Set
from datetime import datetime, timedelta

from .config import NodeConfig
from .client import RPCClient, RPCClientPool
from .server import RPCServer


logger = logging.getLogger(__name__)


class PeerDiscovery:
    """
    Manages peer discovery and cluster bootstrap.
    
    On startup, attempts to connect to all configured peers and establish
    the cluster topology.
    """
    
    def __init__(self, local_config: NodeConfig, timeout: float = 5.0):
        """
        Initialize peer discovery.
        
        Args:
            local_config: NodeConfig for this node
            timeout: Connection timeout in seconds
        """
        self.local_config = local_config
        self.local_id = local_config.node_id
        self.timeout = timeout
        
        # Track discovery state
        self.discovered_peers: Set[str] = set()
        self.failed_peers: Dict[str, int] = {}  # node_id -> failure count
        self.last_discovery_attempt: Dict[str, datetime] = {}
        
        # RPC client pool for peers
        self.client_pool: Optional[RPCClientPool] = None
        
        # Maximum retries per peer
        self.max_discovery_retries = 5
        self.discovery_retry_delay = 1.0  # seconds
    
    async def discover_peers(self) -> bool:
        """
        Attempt to discover and connect to all configured peers.
        
        Returns:
            True if at least one peer was discovered, False if all failed
        """
        if not self.local_config.peers:
            logger.info(f"Node {self.local_id}: No peers configured (single-node cluster)")
            return True
        
        logger.info(
            f"Node {self.local_id}: Starting peer discovery "
            f"({len(self.local_config.peers)} peers)"
        )
        
        # Create client pool
        self.client_pool = RPCClientPool(
            self.local_config.peers,
            timeout=self.timeout
        )
        
        # Try to connect to each peer
        tasks = []
        for peer in self.local_config.peers:
            task = self._try_connect_peer(peer)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successes
        successes = sum(1 for r in results if r is True)
        failures = sum(1 for r in results if r is False)
        
        logger.info(
            f"Node {self.local_id}: Peer discovery complete "
            f"({successes} connected, {failures} failed)"
        )
        
        return successes > 0
    
    async def _try_connect_peer(self, peer: NodeConfig, attempt: int = 1) -> bool:
        """
        Try to connect to a single peer with retries.
        
        Args:
            peer: NodeConfig for the peer
            attempt: Current attempt number
            
        Returns:
            True if connection successful, False otherwise
        """
        peer_id = peer.node_id
        
        logger.debug(f"Node {self.local_id}: Attempting to discover {peer_id} (attempt {attempt})")
        
        try:
            # Get client from pool
            client = self.client_pool.get_client(peer_id)
            if not client:
                logger.error(f"Node {self.local_id}: No client for {peer_id}")
                return False
            
            # Try to connect
            connected = await asyncio.wait_for(
                client.connect(),
                timeout=self.timeout
            )
            
            if connected:
                self.discovered_peers.add(peer_id)
                self.failed_peers.pop(peer_id, None)
                logger.info(
                    f"Node {self.local_id}: Discovered peer {peer_id} "
                    f"at {peer.address}"
                )
                return True
            else:
                # Connection failed
                if attempt < self.max_discovery_retries:
                    logger.debug(
                        f"Node {self.local_id}: Failed to connect to {peer_id}, "
                        f"retrying... (attempt {attempt + 1}/{self.max_discovery_retries})"
                    )
                    await asyncio.sleep(self.discovery_retry_delay * attempt)
                    return await self._try_connect_peer(peer, attempt + 1)
                else:
                    self.failed_peers[peer_id] = attempt
                    logger.warning(
                        f"Node {self.local_id}: Failed to discover {peer_id} "
                        f"after {attempt} attempts"
                    )
                    return False
        
        except asyncio.TimeoutError:
            logger.debug(
                f"Node {self.local_id}: Connection timeout to {peer_id} "
                f"(attempt {attempt})"
            )
            if attempt < self.max_discovery_retries:
                await asyncio.sleep(self.discovery_retry_delay * attempt)
                return await self._try_connect_peer(peer, attempt + 1)
            else:
                self.failed_peers[peer_id] = attempt
                logger.warning(
                    f"Node {self.local_id}: Peer {peer_id} unreachable "
                    f"after {attempt} timeout attempts"
                )
                return False
        
        except Exception as e:
            logger.error(
                f"Node {self.local_id}: Error discovering {peer_id}: {e}"
            )
            if attempt < self.max_discovery_retries:
                await asyncio.sleep(self.discovery_retry_delay * attempt)
                return await self._try_connect_peer(peer, attempt + 1)
            else:
                self.failed_peers[peer_id] = attempt
                return False
    
    async def rediscover_failed_peers(self) -> None:
        """
        Periodically attempt to rediscover failed peers.
        
        Useful for handling temporary network partitions.
        """
        while True:
            # Wait before attempting rediscovery
            await asyncio.sleep(10.0)
            
            if not self.failed_peers:
                continue
            
            logger.debug(
                f"Node {self.local_id}: Attempting to rediscover "
                f"{len(self.failed_peers)} failed peers"
            )
            
            for peer_id in list(self.failed_peers.keys()):
                try:
                    peer = self.local_config.get_peer(peer_id)
                    success = await self._try_connect_peer(peer, attempt=1)
                    if success:
                        logger.info(
                            f"Node {self.local_id}: Successfully rediscovered {peer_id}"
                        )
                except Exception as e:
                    logger.debug(
                        f"Node {self.local_id}: Error rediscovering {peer_id}: {e}"
                    )
    
    def get_connected_peers(self) -> List[str]:
        """
        Get list of currently discovered peers.
        
        Returns:
            List of connected peer node IDs
        """
        return sorted(list(self.discovered_peers))
    
    def get_failed_peers(self) -> List[str]:
        """
        Get list of currently failed/unreachable peers.
        
        Returns:
            List of failed peer node IDs
        """
        return sorted(list(self.failed_peers.keys()))
    
    def is_cluster_ready(self) -> bool:
        """
        Check if cluster is ready for operation.
        
        Returns:
            True if quorum is available (including this node)
        """
        if not self.local_config.is_cluster:
            return True  # Single node is always ready
        
        # For a cluster, need quorum
        total_nodes = len(self.local_config.all_node_ids)
        connected_nodes = len(self.discovered_peers) + 1  # +1 for self
        quorum = (total_nodes // 2) + 1
        
        return connected_nodes >= quorum
    
    async def close(self) -> None:
        """Close all peer connections."""
        if self.client_pool:
            await self.client_pool.close_all()
            logger.info(f"Node {self.local_id}: Closed all peer connections")


class ClusterBootstrap:
    """
    Orchestrates cluster bootstrap process.
    
    Combines RPC server, peer discovery, and handler setup.
    """
    
    def __init__(self, local_config: NodeConfig):
        """
        Initialize cluster bootstrap.
        
        Args:
            local_config: NodeConfig for this node
        """
        self.local_config = local_config
        self.local_id = local_config.node_id
        
        # Components
        self.rpc_server: Optional[RPCServer] = None
        self.peer_discovery: Optional[PeerDiscovery] = None
        
        # Bootstrap state
        self.started = False
        self.ready = False
    
    async def bootstrap(self) -> bool:
        """
        Perform cluster bootstrap.
        
        Steps:
        1. Start RPC server
        2. Discover peers
        3. Setup handlers
        
        Returns:
            True if bootstrap successful, False otherwise
        """
        try:
            # Step 1: Start RPC server
            logger.info(f"Node {self.local_id}: Starting RPC server...")
            self.rpc_server = await self._create_rpc_server()
            
            if not self.rpc_server:
                logger.error(f"Node {self.local_id}: Failed to start RPC server")
                return False
            
            logger.info(
                f"Node {self.local_id}: RPC server started on "
                f"{self.local_config.address}"
            )
            
            # Step 2: Discover peers
            logger.info(f"Node {self.local_id}: Discovering peers...")
            self.peer_discovery = PeerDiscovery(self.local_config)
            
            discovery_ok = await self.peer_discovery.discover_peers()
            if not discovery_ok and self.local_config.is_cluster:
                logger.warning(
                    f"Node {self.local_id}: Peer discovery failed, "
                    f"will retry periodically"
                )
            
            # Step 3: Check cluster readiness
            if self.peer_discovery.is_cluster_ready():
                logger.info(f"Node {self.local_id}: Cluster is ready")
                self.ready = True
            else:
                logger.warning(f"Node {self.local_id}: Cluster not ready (no quorum)")
            
            # Start periodic rediscovery
            if self.local_config.is_cluster:
                asyncio.create_task(
                    self.peer_discovery.rediscover_failed_peers()
                )
            
            self.started = True
            return True
        
        except Exception as e:
            logger.error(f"Node {self.local_id}: Bootstrap failed: {e}")
            return False
    
    async def _create_rpc_server(self) -> Optional[RPCServer]:
        """
        Create and start RPC server.
        
        Returns:
            Started RPCServer or None if failed
        """
        try:
            from .server import create_rpc_server
            server = await create_rpc_server(self.local_config)
            return server
        except Exception as e:
            logger.error(f"Node {self.local_id}: Failed to create RPC server: {e}")
            return None
    
    async def shutdown(self) -> None:
        """Shutdown the cluster."""
        logger.info(f"Node {self.local_id}: Shutting down cluster...")
        
        if self.rpc_server:
            await self.rpc_server.stop()
        
        if self.peer_discovery:
            await self.peer_discovery.close()
        
        logger.info(f"Node {self.local_id}: Cluster shutdown complete")
    
    def get_cluster_status(self) -> Dict[str, any]:
        """
        Get current cluster status.
        
        Returns:
            Dict with cluster state information
        """
        return {
            "node_id": self.local_id,
            "started": self.started,
            "ready": self.ready,
            "server_address": self.local_config.address if self.rpc_server else None,
            "peers_total": len(self.local_config.peers),
            "peers_connected": (
                len(self.peer_discovery.get_connected_peers())
                if self.peer_discovery else 0
            ),
            "peers_failed": (
                len(self.peer_discovery.get_failed_peers())
                if self.peer_discovery else 0
            ),
            "is_cluster": self.local_config.is_cluster
        }
