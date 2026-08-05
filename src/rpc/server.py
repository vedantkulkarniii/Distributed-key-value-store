"""
Async TCP RPC server for Raft inter-node communication.

Handles incoming RPC requests from peer nodes using async TCP sockets
with a length-prefixed message protocol.
"""

import asyncio
import logging
from typing import Callable, Dict, Optional

from .config import NodeConfig


logger = logging.getLogger(__name__)


class RPCServer:
    """
    Async TCP RPC server for receiving RPC calls from peers.
    
    Uses a length-prefixed protocol:
      [4 bytes: message length][N bytes: message data]
    
    Message format:
      {
        "rpc_type": "RequestVote" | "AppendEntries",
        "data": {...}
      }
    """
    
    def __init__(self, config: NodeConfig):
        """
        Initialize the RPC server.
        
        Args:
            config: NodeConfig for this node
        """
        self.config = config
        self.host = config.host
        self.port = config.port
        self.node_id = config.node_id
        
        # RPC handlers mapping
        self.handlers: Dict[str, Callable] = {}
        
        # Server state
        self.server: Optional[asyncio.Server] = None
        self.running = False
        self._tasks: set = set()
    
    def register_handler(self, rpc_type: str, handler: Callable) -> None:
        """
        Register a handler for a specific RPC type.
        
        Args:
            rpc_type: Type of RPC (e.g., "RequestVote", "AppendEntries")
            handler: Async callable that handles the RPC
        """
        self.handlers[rpc_type] = handler
        logger.debug(f"Registered handler for RPC type: {rpc_type}")
    
    async def start(self) -> None:
        """
        Start the RPC server.
        
        Listens on the configured host and port.
        """
        if self.running:
            logger.warning("RPC server already running")
            return
        
        try:
            self.server = await asyncio.start_server(
                self._handle_client,
                self.host,
                self.port
            )
            self.running = True
            
            # Get the actual server addresses
            addr = self.server.sockets[0].getsockname()
            logger.info(f"RPC server started on {addr[0]}:{addr[1]}")
            
        except Exception as e:
            logger.error(f"Failed to start RPC server: {e}")
            raise
    
    async def stop(self) -> None:
        """
        Stop the RPC server.
        
        Closes all connections and stops accepting new ones.
        """
        if not self.running:
            logger.warning("RPC server not running")
            return
        
        self.running = False
        
        if self.server:
            self.server.close()
            try:
                await asyncio.wait_for(self.server.wait_closed(), timeout=5.0)
                logger.info("RPC server stopped")
            except asyncio.TimeoutError:
                logger.warning("RPC server stop timed out")
        
        # Cancel all pending tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()
        
        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
    
    async def _handle_client(self, reader: asyncio.StreamReader, 
                            writer: asyncio.StreamWriter) -> None:
        """
        Handle a single client connection.
        
        Args:
            reader: StreamReader for receiving data
            writer: StreamWriter for sending responses
        """
        addr = writer.get_extra_info('peername')
        logger.debug(f"New RPC connection from {addr}")
        
        try:
            while self.running:
                # Read message length (4 bytes, big-endian)
                length_bytes = await reader.readexactly(4)
                if not length_bytes:
                    break
                
                message_length = int.from_bytes(length_bytes, byteorder='big')
                
                # Validate message length
                if message_length <= 0 or message_length > 10_000_000:  # Max 10MB
                    logger.warning(f"Invalid message length from {addr}: {message_length}")
                    break
                
                # Read message data
                message_data = await reader.readexactly(message_length)
                
                # Handle the RPC request
                response = await self._handle_rpc_request(message_data)
                
                # Send response
                if response:
                    response_bytes = response.encode('utf-8')
                    response_length = len(response_bytes).to_bytes(4, byteorder='big')
                    writer.write(response_length + response_bytes)
                    await writer.drain()
                
        except asyncio.IncompleteReadError:
            logger.debug(f"Client {addr} disconnected (incomplete read)")
        except asyncio.CancelledError:
            logger.debug(f"Client {addr} handler cancelled")
        except Exception as e:
            logger.error(f"Error handling RPC from {addr}: {e}")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception as e:
                logger.debug(f"Error closing connection to {addr}: {e}")
    
    async def _handle_rpc_request(self, message_data: bytes) -> Optional[str]:
        """
        Parse and handle an RPC request.
        
        Args:
            message_data: Raw message bytes
            
        Returns:
            Response string or None
        """
        import json
        
        try:
            message = json.loads(message_data.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(f"Failed to parse RPC message: {e}")
            return json.dumps({"error": "Invalid JSON"})
        
        rpc_type = message.get('rpc_type')
        rpc_data = message.get('data', {})
        
        if not rpc_type:
            logger.warning("RPC message missing rpc_type")
            return json.dumps({"error": "Missing rpc_type"})
        
        # Look up handler
        handler = self.handlers.get(rpc_type)
        if not handler:
            logger.warning(f"No handler for RPC type: {rpc_type}")
            return json.dumps({"error": f"Unknown RPC type: {rpc_type}"})
        
        try:
            # Call handler
            result = await handler(rpc_data)
            return json.dumps({"success": True, "result": result})
        except Exception as e:
            logger.error(f"Error handling RPC {rpc_type}: {e}")
            return json.dumps({"error": str(e)})
    
    async def serve_forever(self) -> None:
        """
        Run the RPC server until stopped.
        
        This is a convenience method that waits forever.
        Call stop() to halt the server.
        """
        if not self.running:
            await self.start()
        
        try:
            if self.server:
                async with self.server:
                    await self.server.serve_forever()
        except Exception as e:
            logger.error(f"Server error: {e}")
            self.running = False


async def create_rpc_server(config: NodeConfig) -> RPCServer:
    """
    Factory function to create and start an RPC server.
    
    Args:
        config: NodeConfig for the server
        
    Returns:
        Started RPCServer instance
    """
    server = RPCServer(config)
    await server.start()
    return server
