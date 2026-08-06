"""
Local cluster runner - Start a 3-node Raft cluster on localhost.

Usage:
    python run_local_cluster.py

This will start 3 nodes:
    - Node A: 127.0.0.1:5000
    - Node B: 127.0.0.1:5001
    - Node C: 127.0.0.1:5002

And HTTP APIs:
    - Node A API: http://127.0.0.1:8000
    - Node B API: http://127.0.0.1:8001
    - Node C API: http://127.0.0.1:8002
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.rpc.config import ClusterConfig, PeerInfo
from src.storage.recovery import StorageEngine
from src.rpc.server import RaftServer
from src.api.server import KVStoreAPI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LocalNode:
    """A single node in the cluster."""
    
    def __init__(self, node_id: str, rpc_port: int, api_port: int, cluster_config: ClusterConfig):
        self.node_id = node_id
        self.rpc_port = rpc_port
        self.api_port = api_port
        self.cluster_config = cluster_config
        self.storage = None
        self.rpc_server = None
        self.api = None
        
    async def start(self):
        """Start this node."""
        logger.info(f"Starting {self.node_id}...")
        
        # Create storage with WAL
        wal_path = f"raft_{self.node_id}.wal"
        self.storage = StorageEngine(wal_path=wal_path)
        await self.storage.start()
        logger.info(f"{self.node_id}: Storage initialized")
        
        # Create RPC server
        node_config = self.cluster_config.build_node_config(self.node_id)
        self.rpc_server = RaftServer(node_config)
        await self.rpc_server.start()
        logger.info(f"{self.node_id}: RPC server started on port {self.rpc_port}")
        
        # Create HTTP API
        self.api = KVStoreAPI(self.storage)
        logger.info(f"{self.node_id}: API ready on port {self.api_port}")
        
        logger.info(f"✅ {self.node_id} started successfully!")
        logger.info(f"   RPC: 127.0.0.1:{self.rpc_port}")
        logger.info(f"   API: http://127.0.0.1:{self.api_port}")
        
    async def stop(self):
        """Stop this node."""
        logger.info(f"Stopping {self.node_id}...")
        if self.rpc_server:
            await self.rpc_server.stop()
        if self.storage:
            await self.storage.clear()
        logger.info(f"{self.node_id} stopped")


async def main():
    """Run a 3-node local cluster."""
    
    # Define cluster configuration
    peers = [
        PeerInfo(node_id="node-a", address="127.0.0.1", port=5000),
        PeerInfo(node_id="node-b", address="127.0.0.1", port=5001),
        PeerInfo(node_id="node-c", address="127.0.0.1", port=5002),
    ]
    
    cluster_config = ClusterConfig(nodes=peers)
    
    logger.info("=" * 80)
    logger.info("🚀 DISTRIBUTED KEY-VALUE STORE - LOCAL CLUSTER")
    logger.info("=" * 80)
    logger.info("")
    logger.info("Starting 3-node Raft cluster on localhost...")
    logger.info("")
    
    # Create nodes
    nodes = [
        LocalNode("node-a", 5000, 8000, cluster_config),
        LocalNode("node-b", 5001, 8001, cluster_config),
        LocalNode("node-c", 5002, 8002, cluster_config),
    ]
    
    try:
        # Start all nodes
        for node in nodes:
            await node.start()
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("✅ CLUSTER STARTED SUCCESSFULLY!")
        logger.info("=" * 80)
        logger.info("")
        logger.info("📡 LOCALHOST IDS & PORTS:")
        logger.info("")
        logger.info("  Node A (Leader candidate):")
        logger.info("    - RPC: 127.0.0.1:5000")
        logger.info("    - HTTP API: http://127.0.0.1:8000")
        logger.info("")
        logger.info("  Node B (Follower):")
        logger.info("    - RPC: 127.0.0.1:5001")
        logger.info("    - HTTP API: http://127.0.0.1:8001")
        logger.info("")
        logger.info("  Node C (Follower):")
        logger.info("    - RPC: 127.0.0.1:5002")
        logger.info("    - HTTP API: http://127.0.0.1:8002")
        logger.info("")
        logger.info("=" * 80)
        logger.info("")
        logger.info("🧪 TEST ENDPOINTS:")
        logger.info("")
        logger.info("  1. Health check:")
        logger.info("     curl http://127.0.0.1:8000/health")
        logger.info("")
        logger.info("  2. Set a value:")
        logger.info('     curl -X POST http://127.0.0.1:8000/set \\')
        logger.info('          -H "Content-Type: application/json" \\')
        logger.info('          -d \'{"key": "hello", "value": "world"}\'')
        logger.info("")
        logger.info("  3. Get a value:")
        logger.info("     curl http://127.0.0.1:8000/get/hello")
        logger.info("")
        logger.info("  4. Get all values:")
        logger.info("     curl http://127.0.0.1:8000/get_all")
        logger.info("")
        logger.info("  5. Delete a value:")
        logger.info("     curl -X DELETE http://127.0.0.1:8000/delete/hello")
        logger.info("")
        logger.info("=" * 80)
        logger.info("")
        logger.info("Press Ctrl+C to stop the cluster...")
        logger.info("")
        
        # Keep running
        await asyncio.sleep(float('inf'))
        
    except KeyboardInterrupt:
        logger.info("")
        logger.info("Shutting down cluster...")
        for node in nodes:
            await node.stop()
        logger.info("✅ Cluster stopped")
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        for node in nodes:
            await node.stop()


if __name__ == "__main__":
    asyncio.run(main())
