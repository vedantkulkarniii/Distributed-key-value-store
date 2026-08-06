"""
Async RPC client for sending requests to peer nodes.

Uses the length-prefixed protocol to communicate with remote nodes.
"""

import asyncio
import logging
import uuid
from typing import Optional, Dict, Any, Tuple

from .protocol import (
    MessageEncoder, MessageDecoder, RPCMessage, RPCResponse,
    RequestVoteRPC, AppendEntriesRPC, InvalidMessageError, MessageTooLargeError
)
from .config import NodeConfig


logger = logging.getLogger(__name__)

# Constants
DEFAULT_TIMEOUT = 5.0  # seconds
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_DELAY = 0.5  # seconds


class RPCClient:
    """
    Client for sending RPC requests to peer nodes.
    
    Uses async TCP sockets with the length-prefixed message protocol.
    Includes automatic retry logic and timeout handling.
    """
    
    def __init__(self, peer_config: NodeConfig, timeout: float = DEFAULT_TIMEOUT):
        """
        Initialize RPC client for a peer node.
        
        Args:
            peer_config: NodeConfig for the peer
            timeout: Request timeout in seconds
        """
        self.peer_config = peer_config
        self.peer_id = peer_config.node_id
        self.host = peer_config.host
        self.port = peer_config.port
        self.timeout = timeout
        
        # Connection state
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._connected = False
        self._lock = asyncio.Lock()
    
    async def connect(self) -> bool:
        """
        Establish connection to peer with retry logic.
        
        Returns:
            True if connected, False if connection failed
        """
        if self._connected:
            # Validate existing connection is still good
            try:
                if self._writer and not self._writer.is_closing():
                    return True
            except Exception:
                pass
            
            # Connection was closed, reset state
            self._connected = False
            self._reader = None
            self._writer = None
        
        async with self._lock:
            # Double-check connection after acquiring lock
            if self._connected:
                try:
                    if self._writer and not self._writer.is_closing():
                        return True
                except Exception:
                    pass
                
                self._connected = False
                self._reader = None
                self._writer = None
            
            # Attempt connection with exponential backoff
            for attempt in range(1, 4):  # 3 attempts
                try:
                    logger.debug(
                        f"RPC client {self.peer_id}: Connection attempt {attempt}/3"
                    )
                    
                    self._reader, self._writer = await asyncio.wait_for(
                        asyncio.open_connection(self.host, self.port),
                        timeout=self.timeout
                    )
                    
                    self._connected = True
                    logger.info(
                        f"Connected to peer {self.peer_id} at {self.host}:{self.port}"
                    )
                    return True
                
                except asyncio.TimeoutError:
                    logger.warning(
                        f"Connection timeout to {self.peer_id} (attempt {attempt}/3)"
                    )
                    if attempt < 3:
                        # Exponential backoff: 0.1s, 0.2s
                        await asyncio.sleep(0.1 * attempt)
                    continue
                
                except ConnectionRefusedError:
                    logger.debug(
                        f"Connection refused by {self.peer_id} (attempt {attempt}/3)"
                    )
                    if attempt < 3:
                        await asyncio.sleep(0.1 * attempt)
                    continue
                
                except OSError as e:
                    logger.warning(
                        f"OS error connecting to {self.peer_id}: {e} "
                        f"(attempt {attempt}/3)"
                    )
                    if attempt < 3:
                        await asyncio.sleep(0.1 * attempt)
                    continue
                
                except Exception as e:
                    logger.error(
                        f"Unexpected error connecting to {self.peer_id}: {e}"
                    )
                    return False
            
            logger.warning(
                f"Failed to connect to {self.peer_id} after 3 attempts"
            )
            return False
    
    async def disconnect(self) -> None:
        """Close connection to peer."""
        async with self._lock:
            if self._writer:
                try:
                    self._writer.close()
                    await self._writer.wait_closed()
                except Exception as e:
                    logger.debug(f"Error closing connection to {self.peer_id}: {e}")
            
            self._reader = None
            self._writer = None
            self._connected = False
    
    async def _send_request(self, message: RPCMessage) -> Optional[str]:
        """
        Send a request and receive response.
        
        Args:
            message: RPCMessage to send
            
        Returns:
            Response JSON string or None if failed
        """
        if not self._connected:
            if not await self.connect():
                return None
        
        try:
            # Encode and send message
            encoded = MessageEncoder.encode(message)
            self._writer.write(encoded)
            await self._writer.drain()
            
            # Read response length
            length_bytes = await asyncio.wait_for(
                self._reader.readexactly(4),
                timeout=self.timeout
            )
            
            if not length_bytes:
                logger.warning(f"Empty response from {self.peer_id}")
                await self.disconnect()
                return None
            
            # Read response data
            import struct
            response_length = struct.unpack('>I', length_bytes)[0]
            
            if response_length <= 0 or response_length > 10_000_000:
                logger.warning(f"Invalid response length from {self.peer_id}: {response_length}")
                await self.disconnect()
                return None
            
            response_data = await asyncio.wait_for(
                self._reader.readexactly(response_length),
                timeout=self.timeout
            )
            
            return response_data.decode('utf-8')
        
        except asyncio.TimeoutError:
            logger.warning(f"RPC timeout with {self.peer_id}")
            await self.disconnect()
            return None
        except Exception as e:
            logger.error(f"Error in RPC with {self.peer_id}: {e}")
            await self.disconnect()
            return None
    
    async def request_vote(self, term: int, candidate_id: str,
                          last_log_index: int, last_log_term: int,
                          retry_count: int = 0) -> Optional[Dict[str, Any]]:
        """
        Send RequestVote RPC to peer.
        
        Args:
            term: Candidate's term
            candidate_id: Candidate's node ID
            last_log_index: Index of candidate's last log entry
            last_log_term: Term of candidate's last log entry
            retry_count: Internal retry counter
            
        Returns:
            Response dict or None if failed
        """
        try:
            # Create request
            message = RequestVoteRPC(
                term=term,
                candidate_id=candidate_id,
                last_log_index=last_log_index,
                last_log_term=last_log_term,
                source_node_id=candidate_id,
                request_id=str(uuid.uuid4())
            )
            
            # Send and receive
            response_json = await self._send_request(message)
            
            if not response_json:
                # Retry on failure
                if retry_count < DEFAULT_RETRY_ATTEMPTS:
                    await asyncio.sleep(DEFAULT_RETRY_DELAY * (2 ** retry_count))
                    return await self.request_vote(
                        term, candidate_id, last_log_index, last_log_term,
                        retry_count + 1
                    )
                return None
            
            # Parse response
            response = RPCResponse.from_json(response_json)
            if response.success:
                return response.result
            else:
                logger.warning(f"RequestVote failed: {response.error}")
                return None
        
        except Exception as e:
            logger.error(f"Error in request_vote: {e}")
            return None
    
    async def append_entries(self, term: int, leader_id: str,
                            prev_log_index: int, prev_log_term: int,
                            entries: list = None, leader_commit: int = 0,
                            retry_count: int = 0) -> Optional[Dict[str, Any]]:
        """
        Send AppendEntries RPC to peer.
        
        Args:
            term: Leader's term
            leader_id: Leader's node ID
            prev_log_index: Index of previous log entry
            prev_log_term: Term of previous log entry
            entries: Log entries to append (None for heartbeat)
            leader_commit: Leader's commit index
            retry_count: Internal retry counter
            
        Returns:
            Response dict or None if failed
        """
        try:
            # Create request
            message = AppendEntriesRPC(
                term=term,
                leader_id=leader_id,
                prev_log_index=prev_log_index,
                prev_log_term=prev_log_term,
                entries=entries or [],
                leader_commit=leader_commit,
                source_node_id=leader_id,
                request_id=str(uuid.uuid4())
            )
            
            # Send and receive
            response_json = await self._send_request(message)
            
            if not response_json:
                # Retry on failure
                if retry_count < DEFAULT_RETRY_ATTEMPTS:
                    await asyncio.sleep(DEFAULT_RETRY_DELAY * (2 ** retry_count))
                    return await self.append_entries(
                        term, leader_id, prev_log_index, prev_log_term,
                        entries, leader_commit, retry_count + 1
                    )
                return None
            
            # Parse response
            response = RPCResponse.from_json(response_json)
            if response.success:
                return response.result
            else:
                logger.warning(f"AppendEntries failed: {response.error}")
                return None
        
        except Exception as e:
            logger.error(f"Error in append_entries: {e}")
            return None


class RPCClientPool:
    """
    Manages RPC clients for all peers.
    
    Provides convenient access to multiple peer clients and handles
    connection pooling and cleanup.
    """
    
    def __init__(self, peers: list, timeout: float = DEFAULT_TIMEOUT):
        """
        Initialize client pool.
        
        Args:
            peers: List of NodeConfig objects for peers
            timeout: Request timeout
        """
        self.clients: Dict[str, RPCClient] = {}
        for peer in peers:
            self.clients[peer.node_id] = RPCClient(peer, timeout=timeout)
    
    def get_client(self, node_id: str) -> Optional[RPCClient]:
        """
        Get client for a specific peer.
        
        Args:
            node_id: ID of peer
            
        Returns:
            RPCClient or None if not found
        """
        return self.clients.get(node_id)
    
    async def broadcast_heartbeat(self, leader_id: str, term: int,
                                  leader_commit: int) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Broadcast heartbeat to all peers.
        
        Args:
            leader_id: Leader's ID
            term: Current term
            leader_commit: Leader's commit index
            
        Returns:
            Dict mapping node_id -> response (or None if failed)
        """
        tasks = []
        node_ids = []
        
        for node_id, client in self.clients.items():
            task = client.append_entries(
                term=term,
                leader_id=leader_id,
                prev_log_index=0,
                prev_log_term=0,
                entries=[],
                leader_commit=leader_commit
            )
            tasks.append(task)
            node_ids.append(node_id)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return {
            node_ids[i]: results[i] if not isinstance(results[i], Exception) else None
            for i in range(len(node_ids))
        }
    
    async def broadcast_vote_request(self, candidate_id: str, term: int,
                                     last_log_index: int, last_log_term: int
                                     ) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Broadcast vote request to all peers.
        
        Args:
            candidate_id: Candidate's ID
            term: Candidate's term
            last_log_index: Candidate's last log index
            last_log_term: Candidate's last log term
            
        Returns:
            Dict mapping node_id -> response (or None if failed)
        """
        tasks = []
        node_ids = []
        
        for node_id, client in self.clients.items():
            task = client.request_vote(
                term=term,
                candidate_id=candidate_id,
                last_log_index=last_log_index,
                last_log_term=last_log_term
            )
            tasks.append(task)
            node_ids.append(node_id)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return {
            node_ids[i]: results[i] if not isinstance(results[i], Exception) else None
            for i in range(len(node_ids))
        }
    
    async def close_all(self) -> None:
        """Close all client connections."""
        tasks = [client.disconnect() for client in self.clients.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
