"""
Node configuration schema for Raft cluster.

Defines the configuration for each node including its identity,
network address, and list of peers.
"""

from dataclasses import dataclass, field
from typing import List
from pydantic import BaseModel, Field, validator


@dataclass
class NodeConfig:
    """
    Configuration for a single Raft node.
    
    Attributes:
        node_id: Unique identifier for this node (e.g., "node-1")
        host: IP address or hostname for this node's RPC server
        port: Port number for this node's RPC server
        peers: List of peer node configurations
    """
    node_id: str
    host: str
    port: int
    peers: List['NodeConfig'] = field(default_factory=list)
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        if not self.node_id or not self.node_id.strip():
            raise ValueError("node_id cannot be empty")
        if not self.host or not self.host.strip():
            raise ValueError("host cannot be empty")
        if self.port < 1 or self.port > 65535:
            raise ValueError(f"port must be between 1 and 65535, got {self.port}")
    
    @property
    def address(self) -> str:
        """Get the full address (host:port) for this node."""
        return f"{self.host}:{self.port}"
    
    @property
    def peer_ids(self) -> List[str]:
        """Get list of peer node IDs."""
        return [peer.node_id for peer in self.peers]
    
    @property
    def all_node_ids(self) -> List[str]:
        """Get list of all node IDs including self."""
        return [self.node_id] + self.peer_ids
    
    @property
    def is_cluster(self) -> bool:
        """Check if this node is part of a multi-node cluster."""
        return len(self.peers) > 0
    
    def get_peer(self, node_id: str) -> 'NodeConfig':
        """
        Get a peer configuration by node ID.
        
        Args:
            node_id: The ID of the peer to retrieve
            
        Returns:
            The NodeConfig for the peer
            
        Raises:
            ValueError: If peer not found
        """
        for peer in self.peers:
            if peer.node_id == node_id:
                return peer
        raise ValueError(f"Peer '{node_id}' not found in configuration")
    
    def __repr__(self) -> str:
        """String representation."""
        return f"NodeConfig(node_id={self.node_id}, address={self.address}, peers={len(self.peers)})"


class PeerInfo(BaseModel):
    """Pydantic model for peer information (for API serialization)."""
    node_id: str = Field(..., description="Unique node identifier")
    host: str = Field(..., description="IP address or hostname")
    port: int = Field(..., description="RPC port number", ge=1, le=65535)
    
    class Config:
        json_schema_extra = {
            "example": {
                "node_id": "node-1",
                "host": "127.0.0.1",
                "port": 9000
            }
        }


class ClusterConfig(BaseModel):
    """
    Pydantic model for complete cluster configuration.
    
    Used for parsing cluster configuration from JSON/YAML.
    """
    nodes: List[PeerInfo] = Field(..., description="List of all nodes in cluster")
    
    class Config:
        json_schema_extra = {
            "example": {
                "nodes": [
                    {"node_id": "node-1", "host": "127.0.0.1", "port": 9000},
                    {"node_id": "node-2", "host": "127.0.0.1", "port": 9001},
                    {"node_id": "node-3", "host": "127.0.0.1", "port": 9002}
                ]
            }
        }
    
    @validator('nodes')
    def validate_node_count(cls, nodes):
        """Ensure at least 1 node is configured."""
        if not nodes:
            raise ValueError("At least 1 node must be configured")
        return nodes
    
    @validator('nodes')
    def validate_unique_ids(cls, nodes):
        """Ensure all node IDs are unique."""
        ids = [n.node_id for n in nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("Node IDs must be unique")
        return nodes
    
    @validator('nodes')
    def validate_unique_addresses(cls, nodes):
        """Ensure all nodes have unique addresses."""
        addresses = {(n.host, n.port) for n in nodes}
        if len(addresses) != len(nodes):
            raise ValueError("Node addresses (host:port) must be unique")
        return nodes
    
    def build_node_config(self, node_id: str) -> NodeConfig:
        """
        Build a NodeConfig for a specific node with its peers.
        
        Args:
            node_id: The ID of the node to build config for
            
        Returns:
            NodeConfig with this node and its peers
            
        Raises:
            ValueError: If node_id not found
        """
        # Find the node
        node_peer = None
        for peer in self.nodes:
            if peer.node_id == node_id:
                node_peer = peer
                break
        
        if not node_peer:
            raise ValueError(f"Node '{node_id}' not found in cluster config")
        
        # Build peer list (all nodes except self)
        peers = []
        for peer in self.nodes:
            if peer.node_id != node_id:
                peers.append(NodeConfig(
                    node_id=peer.node_id,
                    host=peer.host,
                    port=peer.port
                ))
        
        # Create config for this node
        return NodeConfig(
            node_id=node_peer.node_id,
            host=node_peer.host,
            port=node_peer.port,
            peers=peers
        )
    
    def get_all_addresses(self) -> dict:
        """
        Get mapping of all node IDs to their addresses.
        
        Returns:
            Dict mapping node_id -> (host, port)
        """
        return {
            node.node_id: (node.host, node.port)
            for node in self.nodes
        }


def create_local_cluster_config(num_nodes: int = 3, base_port: int = 9000) -> ClusterConfig:
    """
    Create a local test cluster configuration.
    
    Useful for testing and development with all nodes on localhost.
    
    Args:
        num_nodes: Number of nodes in cluster
        base_port: Starting port number (incremented for each node)
        
    Returns:
        ClusterConfig for a local cluster
        
    Raises:
        ValueError: If num_nodes < 1 or ports would exceed 65535
    """
    if num_nodes < 1:
        raise ValueError("num_nodes must be at least 1")
    if base_port + num_nodes > 65535:
        raise ValueError(f"Port range would exceed 65535")
    
    nodes = []
    for i in range(num_nodes):
        nodes.append(PeerInfo(
            node_id=f"node-{i+1}",
            host="127.0.0.1",
            port=base_port + i
        ))
    
    return ClusterConfig(nodes=nodes)
