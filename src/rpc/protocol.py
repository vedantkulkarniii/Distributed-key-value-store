"""
Length-prefixed message protocol for RPC communication.

Protocol format:
  [4 bytes: message length in big-endian][N bytes: JSON message]

This ensures reliable message framing over TCP stream.
"""

import json
import struct
import logging
from typing import Any, Dict, Optional
from dataclasses import dataclass, asdict


logger = logging.getLogger(__name__)


# Constants
MESSAGE_LENGTH_SIZE = 4  # 4 bytes for length field
MAX_MESSAGE_SIZE = 10_000_000  # 10MB max message size


class ProtocolError(Exception):
    """Base exception for protocol errors."""
    pass


class MessageTooLargeError(ProtocolError):
    """Message exceeds maximum allowed size."""
    pass


class InvalidMessageError(ProtocolError):
    """Invalid message format."""
    pass


@dataclass
class RPCMessage:
    """
    RPC message structure.
    
    Attributes:
        rpc_type: Type of RPC (e.g., "RequestVote", "AppendEntries")
        data: RPC-specific data
        source_node_id: Node ID sending this message (optional)
        request_id: Unique request ID for tracking (optional)
    """
    rpc_type: str
    data: Dict[str, Any]
    source_node_id: Optional[str] = None
    request_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RPCMessage':
        """Create from dictionary."""
        return cls(
            rpc_type=data['rpc_type'],
            data=data['data'],
            source_node_id=data.get('source_node_id'),
            request_id=data.get('request_id')
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> 'RPCMessage':
        """Create from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)


@dataclass
class RPCResponse:
    """
    RPC response structure.
    
    Attributes:
        success: Whether the RPC succeeded
        result: Result data (if successful)
        error: Error message (if failed)
        request_id: Echo of the request ID
    """
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    request_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RPCResponse':
        """Create from dictionary."""
        return cls(
            success=data['success'],
            result=data.get('result'),
            error=data.get('error'),
            request_id=data.get('request_id')
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> 'RPCResponse':
        """Create from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)


class MessageEncoder:
    """Encodes messages using length-prefixed protocol."""
    
    @staticmethod
    def encode(message: RPCMessage) -> bytes:
        """
        Encode an RPC message.
        
        Args:
            message: RPCMessage to encode
            
        Returns:
            Encoded bytes ready to send
            
        Raises:
            MessageTooLargeError: If message exceeds max size
        """
        # Serialize to JSON
        json_str = message.to_json()
        message_bytes = json_str.encode('utf-8')
        
        # Check size
        if len(message_bytes) > MAX_MESSAGE_SIZE:
            raise MessageTooLargeError(
                f"Message size {len(message_bytes)} exceeds max {MAX_MESSAGE_SIZE}"
            )
        
        # Prepend length
        length = len(message_bytes)
        length_bytes = struct.pack('>I', length)  # Big-endian 4-byte unsigned int
        
        return length_bytes + message_bytes
    
    @staticmethod
    def decode(data: bytes) -> tuple[int, RPCMessage]:
        """
        Decode an RPC message.
        
        Args:
            data: Encoded message bytes
            
        Returns:
            Tuple of (bytes_consumed, RPCMessage)
            
        Raises:
            InvalidMessageError: If message format is invalid
        """
        if len(data) < MESSAGE_LENGTH_SIZE:
            raise InvalidMessageError("Incomplete message length header")
        
        # Read length
        length = struct.unpack('>I', data[:MESSAGE_LENGTH_SIZE])[0]
        
        # Validate length
        if length <= 0:
            raise InvalidMessageError(f"Invalid message length: {length}")
        if length > MAX_MESSAGE_SIZE:
            raise MessageTooLargeError(f"Message size {length} exceeds max {MAX_MESSAGE_SIZE}")
        
        # Check if we have complete message
        total_size = MESSAGE_LENGTH_SIZE + length
        if len(data) < total_size:
            raise InvalidMessageError(f"Incomplete message (have {len(data)}, need {total_size})")
        
        # Extract and parse message
        try:
            message_bytes = data[MESSAGE_LENGTH_SIZE:total_size]
            json_str = message_bytes.decode('utf-8')
            message = RPCMessage.from_json(json_str)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise InvalidMessageError(f"Failed to parse message: {e}")
        
        return total_size, message


class MessageDecoder:
    """Stateful decoder for reading messages from a stream."""
    
    def __init__(self):
        """Initialize the decoder."""
        self.buffer = b''
    
    def feed(self, data: bytes) -> list[RPCMessage]:
        """
        Feed data to the decoder and extract complete messages.
        
        Args:
            data: Bytes received from network
            
        Returns:
            List of complete messages extracted
        """
        self.buffer += data
        messages = []
        
        while len(self.buffer) >= MESSAGE_LENGTH_SIZE:
            try:
                bytes_consumed, message = MessageEncoder.decode(self.buffer)
                messages.append(message)
                self.buffer = self.buffer[bytes_consumed:]
            except (InvalidMessageError, MessageTooLargeError):
                # Need more data or corrupted message
                break
            except Exception as e:
                logger.error(f"Unexpected error decoding message: {e}")
                self.buffer = b''  # Clear buffer on fatal error
                break
        
        return messages
    
    def clear(self) -> None:
        """Clear the buffer."""
        self.buffer = b''
    
    def has_incomplete_message(self) -> bool:
        """Check if buffer contains incomplete message."""
        return len(self.buffer) > 0


# RequestVote RPC message format
class RequestVoteRPC(RPCMessage):
    """RequestVote RPC (Raft Phase 3)."""
    
    def __init__(self, term: int, candidate_id: str, last_log_index: int,
                 last_log_term: int, source_node_id: str = None, request_id: str = None):
        """
        Create a RequestVote RPC.
        
        Args:
            term: Current term of candidate
            candidate_id: ID of candidate requesting vote
            last_log_index: Index of candidate's last log entry
            last_log_term: Term of candidate's last log entry
        """
        super().__init__(
            rpc_type="RequestVote",
            data={
                "term": term,
                "candidate_id": candidate_id,
                "last_log_index": last_log_index,
                "last_log_term": last_log_term
            },
            source_node_id=source_node_id,
            request_id=request_id
        )


# AppendEntries RPC message format
class AppendEntriesRPC(RPCMessage):
    """AppendEntries RPC (Raft Phase 4)."""
    
    def __init__(self, term: int, leader_id: str, prev_log_index: int,
                 prev_log_term: int, entries: list = None, leader_commit: int = 0,
                 source_node_id: str = None, request_id: str = None):
        """
        Create an AppendEntries RPC.
        
        Args:
            term: Current term of leader
            leader_id: ID of leader
            prev_log_index: Index of log entry before new entries
            prev_log_term: Term of prev_log_index entry
            entries: Log entries to append (empty for heartbeat)
            leader_commit: Leader's commit index
        """
        super().__init__(
            rpc_type="AppendEntries",
            data={
                "term": term,
                "leader_id": leader_id,
                "prev_log_index": prev_log_index,
                "prev_log_term": prev_log_term,
                "entries": entries or [],
                "leader_commit": leader_commit
            },
            source_node_id=source_node_id,
            request_id=request_id
        )


# Response message formats
class RequestVoteResponse(RPCResponse):
    """Response to RequestVote RPC."""
    
    def __init__(self, term: int, vote_granted: bool, request_id: str = None):
        """
        Create a RequestVote response.
        
        Args:
            term: Current term
            vote_granted: Whether vote was granted
        """
        super().__init__(
            success=True,
            result={"term": term, "vote_granted": vote_granted},
            request_id=request_id
        )


class AppendEntriesResponse(RPCResponse):
    """Response to AppendEntries RPC."""
    
    def __init__(self, term: int, success: bool, request_id: str = None):
        """
        Create an AppendEntries response.
        
        Args:
            term: Current term
            success: Whether entries were appended
        """
        super().__init__(
            success=True,
            result={"term": term, "success": success},
            request_id=request_id
        )
