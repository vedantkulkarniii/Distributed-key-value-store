"""
Tests for RPC protocol and message serialization.

Tests cover message encoding/decoding, protocol correctness,
and RPC handler logic.
"""

import pytest
import json
import struct

from src.rpc.protocol import (
    MessageEncoder, MessageDecoder, RPCMessage, RPCResponse,
    RequestVoteRPC, AppendEntriesRPC,
    ProtocolError, MessageTooLargeError, InvalidMessageError
)
from src.rpc.config import NodeConfig, ClusterConfig, PeerInfo, create_local_cluster_config


class TestMessageEncoding:
    """Test message encoding and decoding."""
    
    def test_encode_decode_roundtrip(self):
        """Test that messages survive encode-decode roundtrip."""
        original = RPCMessage(
            rpc_type="TestRPC",
            data={"key": "value", "number": 42},
            source_node_id="node-1"
        )
        
        # Encode
        encoded = MessageEncoder.encode(original)
        assert isinstance(encoded, bytes)
        assert len(encoded) >= 4
        
        # Decode
        bytes_consumed, decoded = MessageEncoder.decode(encoded)
        assert bytes_consumed == len(encoded)
        assert decoded.rpc_type == original.rpc_type
        assert decoded.data == original.data
        assert decoded.source_node_id == original.source_node_id
    
    def test_encode_includes_length_prefix(self):
        """Test that encoded messages have correct length prefix."""
        message = RPCMessage(rpc_type="Test", data={})
        encoded = MessageEncoder.encode(message)
        
        # Extract length
        length = struct.unpack('>I', encoded[:4])[0]
        
        # Verify: total length = 4 + length value
        assert len(encoded) == 4 + length
    
    def test_decode_incomplete_message_fails(self):
        """Test that incomplete messages raise error."""
        # Just a partial length header
        with pytest.raises(InvalidMessageError):
            MessageEncoder.decode(b'\x00\x00')
    
    def test_decode_message_too_large(self):
        """Test that oversized length causes error."""
        # Create fake length header with huge size
        huge_size = 20_000_000  # > 10MB limit
        encoded = struct.pack('>I', huge_size)
        
        with pytest.raises(MessageTooLargeError):
            MessageEncoder.decode(encoded)
    
    def test_encode_message_too_large(self):
        """Test that encoding oversized message fails."""
        # Create message with huge data
        huge_data = {"big": "x" * 20_000_000}
        message = RPCMessage(rpc_type="Test", data=huge_data)
        
        with pytest.raises(MessageTooLargeError):
            MessageEncoder.encode(message)
    
    def test_complex_data_serialization(self):
        """Test encoding/decoding complex nested data."""
        complex_data = {
            "nested": {"deep": {"very_deep": [1, 2, 3]}},
            "string": "hello",
            "number": 42,
            "float": 3.14,
            "bool": True,
            "null": None,
            "array": [1, "two", 3.0, True, None]
        }
        
        message = RPCMessage(rpc_type="Complex", data=complex_data)
        encoded = MessageEncoder.encode(message)
        _, decoded = MessageEncoder.decode(encoded)
        
        assert decoded.data == complex_data


class TestRequestVoteMessage:
    """Test RequestVote RPC messages."""
    
    def test_request_vote_creation(self):
        """Test creating RequestVote message."""
        msg = RequestVoteRPC(
            term=5,
            candidate_id="node-1",
            last_log_index=10,
            last_log_term=4
        )
        
        assert msg.rpc_type == "RequestVote"
        assert msg.data["term"] == 5
        assert msg.data["candidate_id"] == "node-1"
        assert msg.data["last_log_index"] == 10
        assert msg.data["last_log_term"] == 4
    
    def test_request_vote_serialization(self):
        """Test RequestVote message roundtrip."""
        msg = RequestVoteRPC(
            term=3,
            candidate_id="node-2",
            last_log_index=5,
            last_log_term=2,
            source_node_id="node-2",
            request_id="req-123"
        )
        
        encoded = MessageEncoder.encode(msg)
        _, decoded = MessageEncoder.decode(encoded)
        
        assert decoded.rpc_type == "RequestVote"
        assert decoded.data["term"] == 3
        assert decoded.source_node_id == "node-2"


class TestAppendEntriesMessage:
    """Test AppendEntries RPC messages."""
    
    def test_append_entries_heartbeat(self):
        """Test AppendEntries with no entries (heartbeat)."""
        msg = AppendEntriesRPC(
            term=5,
            leader_id="node-1",
            prev_log_index=10,
            prev_log_term=4,
            leader_commit=8
        )
        
        assert msg.rpc_type == "AppendEntries"
        assert msg.data["term"] == 5
        assert msg.data["entries"] == []
        assert msg.data["leader_commit"] == 8
    
    def test_append_entries_with_entries(self):
        """Test AppendEntries with log entries."""
        entries = [
            {"index": 11, "term": 5, "data": "command1"},
            {"index": 12, "term": 5, "data": "command2"}
        ]
        
        msg = AppendEntriesRPC(
            term=5,
            leader_id="node-1",
            prev_log_index=10,
            prev_log_term=4,
            entries=entries,
            leader_commit=8
        )
        
        assert len(msg.data["entries"]) == 2
        assert msg.data["entries"] == entries
    
    def test_append_entries_serialization(self):
        """Test AppendEntries message roundtrip."""
        entries = [{"data": "cmd"}]
        msg = AppendEntriesRPC(
            term=3,
            leader_id="leader",
            prev_log_index=2,
            prev_log_term=2,
            entries=entries,
            leader_commit=2
        )
        
        encoded = MessageEncoder.encode(msg)
        _, decoded = MessageEncoder.decode(encoded)
        
        assert decoded.rpc_type == "AppendEntries"
        assert len(decoded.data["entries"]) == 1


class TestMessageDecoder:
    """Test stateful message decoder."""
    
    def test_decoder_accumulates_data(self):
        """Test that decoder accumulates incomplete messages."""
        msg = RPCMessage(rpc_type="Test", data={"key": "value"})
        encoded = MessageEncoder.encode(msg)
        
        decoder = MessageDecoder()
        
        # Feed data in parts
        messages1 = decoder.feed(encoded[:5])
        assert len(messages1) == 0  # Incomplete
        
        messages2 = decoder.feed(encoded[5:])
        assert len(messages2) == 1  # Complete
        assert messages2[0].rpc_type == "Test"
    
    def test_decoder_multiple_messages(self):
        """Test decoding multiple messages from buffer."""
        msg1 = RPCMessage(rpc_type="First", data={})
        msg2 = RPCMessage(rpc_type="Second", data={"n": 2})
        
        encoded1 = MessageEncoder.encode(msg1)
        encoded2 = MessageEncoder.encode(msg2)
        
        decoder = MessageDecoder()
        messages = decoder.feed(encoded1 + encoded2)
        
        assert len(messages) == 2
        assert messages[0].rpc_type == "First"
        assert messages[1].rpc_type == "Second"
    
    def test_decoder_clear(self):
        """Test clearing decoder buffer."""
        decoder = MessageDecoder()
        msg = RPCMessage(rpc_type="Test", data={})
        encoded = MessageEncoder.encode(msg)
        
        # Feed partial data
        decoder.feed(encoded[:5])
        assert decoder.has_incomplete_message()
        
        # Clear
        decoder.clear()
        assert not decoder.has_incomplete_message()


class TestNodeConfig:
    """Test node configuration."""
    
    def test_node_config_creation(self):
        """Test creating NodeConfig."""
        config = NodeConfig(
            node_id="node-1",
            host="127.0.0.1",
            port=9000
        )
        
        assert config.node_id == "node-1"
        assert config.address == "127.0.0.1:9000"
        assert config.is_cluster is False
    
    def test_node_config_with_peers(self):
        """Test NodeConfig with peer nodes."""
        peer1 = NodeConfig("node-2", "127.0.0.1", 9001)
        peer2 = NodeConfig("node-3", "127.0.0.1", 9002)
        
        config = NodeConfig(
            node_id="node-1",
            host="127.0.0.1",
            port=9000,
            peers=[peer1, peer2]
        )
        
        assert config.is_cluster is True
        assert len(config.peer_ids) == 2
        assert "node-2" in config.peer_ids
    
    def test_node_config_invalid_port(self):
        """Test that invalid ports raise error."""
        with pytest.raises(ValueError):
            NodeConfig("node-1", "localhost", 0)
        
        with pytest.raises(ValueError):
            NodeConfig("node-1", "localhost", 70000)
    
    def test_get_peer(self):
        """Test retrieving peer configuration."""
        peer = NodeConfig("peer-1", "127.0.0.1", 9001)
        config = NodeConfig(
            node_id="node-1",
            host="127.0.0.1",
            port=9000,
            peers=[peer]
        )
        
        retrieved = config.get_peer("peer-1")
        assert retrieved.node_id == "peer-1"
    
    def test_get_peer_not_found(self):
        """Test that getting non-existent peer raises error."""
        config = NodeConfig("node-1", "127.0.0.1", 9000)
        
        with pytest.raises(ValueError):
            config.get_peer("nonexistent")


class TestClusterConfig:
    """Test cluster configuration."""
    
    def test_cluster_config_creation(self):
        """Test creating cluster configuration."""
        config = ClusterConfig(nodes=[
            PeerInfo(node_id="node-1", host="127.0.0.1", port=9000),
            PeerInfo(node_id="node-2", host="127.0.0.1", port=9001)
        ])
        
        assert len(config.nodes) == 2
    
    def test_cluster_config_build_node_config(self):
        """Test building node config from cluster config."""
        cluster = ClusterConfig(nodes=[
            PeerInfo(node_id="node-1", host="127.0.0.1", port=9000),
            PeerInfo(node_id="node-2", host="127.0.0.1", port=9001),
            PeerInfo(node_id="node-3", host="127.0.0.1", port=9002)
        ])
        
        node_config = cluster.build_node_config("node-2")
        
        assert node_config.node_id == "node-2"
        assert len(node_config.peers) == 2
        assert "node-1" in node_config.peer_ids
        assert "node-3" in node_config.peer_ids
    
    def test_cluster_config_unique_ids(self):
        """Test that duplicate node IDs are rejected."""
        with pytest.raises(ValueError):
            ClusterConfig(nodes=[
                PeerInfo(node_id="node-1", host="127.0.0.1", port=9000),
                PeerInfo(node_id="node-1", host="127.0.0.1", port=9001)
            ])
    
    def test_cluster_config_unique_addresses(self):
        """Test that duplicate addresses are rejected."""
        with pytest.raises(ValueError):
            ClusterConfig(nodes=[
                PeerInfo(node_id="node-1", host="127.0.0.1", port=9000),
                PeerInfo(node_id="node-2", host="127.0.0.1", port=9000)
            ])
    
    def test_create_local_cluster(self):
        """Test creating local test cluster."""
        cluster = create_local_cluster_config(num_nodes=3, base_port=9000)
        
        assert len(cluster.nodes) == 3
        assert cluster.nodes[0].port == 9000
        assert cluster.nodes[1].port == 9001
        assert cluster.nodes[2].port == 9002


class TestRPCResponse:
    """Test RPC response messages."""
    
    def test_response_creation_success(self):
        """Test creating successful response."""
        response = RPCResponse(
            success=True,
            result={"term": 5, "granted": True}
        )
        
        assert response.success is True
        assert response.result["term"] == 5
    
    def test_response_creation_error(self):
        """Test creating error response."""
        response = RPCResponse(
            success=False,
            error="Invalid term"
        )
        
        assert response.success is False
        assert response.error == "Invalid term"
    
    def test_response_json_roundtrip(self):
        """Test response JSON serialization."""
        response = RPCResponse(
            success=True,
            result={"data": "value"},
            request_id="req-123"
        )
        
        json_str = response.to_json()
        restored = RPCResponse.from_json(json_str)
        
        assert restored.success == response.success
        assert restored.result == response.result
        assert restored.request_id == response.request_id


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_empty_message_data(self):
        """Test message with empty data dict."""
        msg = RPCMessage(rpc_type="Empty", data={})
        encoded = MessageEncoder.encode(msg)
        _, decoded = MessageEncoder.decode(encoded)
        
        assert decoded.data == {}
    
    def test_null_values_in_data(self):
        """Test message with null values."""
        msg = RPCMessage(rpc_type="Null", data={"key": None, "array": [1, None, 3]})
        encoded = MessageEncoder.encode(msg)
        _, decoded = MessageEncoder.decode(encoded)
        
        assert decoded.data["key"] is None
        assert decoded.data["array"][1] is None
    
    def test_unicode_in_data(self):
        """Test message with unicode characters."""
        msg = RPCMessage(rpc_type="Unicode", data={"text": "Hello 世界 🚀"})
        encoded = MessageEncoder.encode(msg)
        _, decoded = MessageEncoder.decode(encoded)
        
        assert decoded.data["text"] == "Hello 世界 🚀"
