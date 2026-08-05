# Phase 2: RPC Layer & Cluster Bootstrap

## Overview

Phase 2 implements the network communication layer for Raft consensus. Nodes communicate using async TCP with a length-prefixed message protocol.

## RPC Protocol Specification

### Message Format

All RPC messages use a length-prefixed binary protocol:

```
┌─────────────────────────────────────┐
│  [4 bytes] Message Length (big-endian)
├─────────────────────────────────────┤
│  [N bytes] JSON-encoded Message     │
└─────────────────────────────────────┘
```

**Constraints:**
- Message length: 4-byte unsigned integer (big-endian)
- Max message size: 10MB
- Message body: UTF-8 encoded JSON

### RPC Message Structure

```json
{
  "rpc_type": "RequestVote" | "AppendEntries",
  "data": {
    // RPC-specific fields
  },
  "source_node_id": "node-1",
  "request_id": "uuid-string"
}
```

**Fields:**
- `rpc_type` (string, required): Type of RPC
- `data` (object, required): RPC-specific data
- `source_node_id` (string, optional): Sender's node ID
- `request_id` (string, optional): Request ID for tracking

### RPC Response Structure

```json
{
  "success": true | false,
  "result": { /* response data */ },
  "error": "error message if failed",
  "request_id": "uuid-string"
}
```

---

## RequestVote RPC

**Purpose**: Request a vote from a peer during leader election (Phase 3)

### Request

```json
{
  "rpc_type": "RequestVote",
  "data": {
    "term": 5,
    "candidate_id": "node-1",
    "last_log_index": 10,
    "last_log_term": 4
  }
}
```

**Request Fields:**
- `term` (integer): Candidate's current term
- `candidate_id` (string): ID of candidate requesting vote
- `last_log_index` (integer): Index of candidate's last log entry
- `last_log_term` (integer): Term of candidate's last log entry

### Response

```json
{
  "success": true,
  "result": {
    "term": 5,
    "vote_granted": true
  }
}
```

**Response Fields:**
- `term` (integer): Current term (for candidate to update itself)
- `vote_granted` (boolean): Whether the vote was granted

### Receiver Rules (Raft Paper)

1. **Rule 1**: Reply `vote_granted=false` if `term < currentTerm`
2. **Rule 2**: Grant vote if `votedFor` is null or equals candidateId, AND candidate's log is at least as up-to-date as receiver's log
3. **Rule 3**: Reply `vote_granted=false` otherwise

### Log Up-to-Date Comparison

Candidate log is up-to-date if:
- Candidate's `lastLogTerm` > receiver's `lastLogTerm`, OR
- `lastLogTerm` values equal AND candidate's `lastLogIndex` >= receiver's `lastLogIndex`

---

## AppendEntries RPC

**Purpose**: 
- Replicate log entries to followers (Phase 4)
- Send periodic heartbeats (empty entries)

### Request

```json
{
  "rpc_type": "AppendEntries",
  "data": {
    "term": 5,
    "leader_id": "node-1",
    "prev_log_index": 10,
    "prev_log_term": 4,
    "entries": [
      {"index": 11, "term": 5, "data": "command1"},
      {"index": 12, "term": 5, "data": "command2"}
    ],
    "leader_commit": 8
  }
}
```

**Request Fields:**
- `term` (integer): Leader's current term
- `leader_id` (string): ID of leader (helps followers find leader)
- `prev_log_index` (integer): Index of entry preceding new ones
- `prev_log_term` (integer): Term of `prev_log_index` entry
- `entries` (array): Log entries to replicate (empty for heartbeat)
- `leader_commit` (integer): Leader's commit index

### Response

```json
{
  "success": true,
  "result": {
    "term": 5,
    "success": true
  }
}
```

**Response Fields:**
- `term` (integer): Current term
- `success` (boolean): Whether entries were replicated

### Receiver Rules (Raft Paper)

1. **Rule 1**: Reply `success=false` if `term < currentTerm`

2. **Rule 2**: Reply `success=false` if log doesn't contain entry at `prevLogIndex` with term matching `prevLogTerm`

3. **Rule 3**: If conflicting entry found:
   - Delete existing entry and all following entries
   - Append new entries

4. **Rule 4**: Append any new entries not already in log

5. **Rule 5**: If `leaderCommit > commitIndex`:
   - Set `commitIndex = min(leaderCommit, index of last new entry)`

### Heartbeat

Heartbeat is an AppendEntries RPC with empty `entries`:

```json
{
  "rpc_type": "AppendEntries",
  "data": {
    "term": 5,
    "leader_id": "node-1",
    "prev_log_index": 10,
    "prev_log_term": 4,
    "entries": [],
    "leader_commit": 8
  }
}
```

---

## Node Configuration

### NodeConfig Structure

```python
@dataclass
class NodeConfig:
    node_id: str              # Unique node identifier
    host: str                 # IP address or hostname
    port: int                 # RPC port (1-65535)
    peers: List[NodeConfig]   # List of peer nodes
```

**Properties:**
- `address`: Full address as "host:port"
- `peer_ids`: List of peer node IDs
- `all_node_ids`: All node IDs including self
- `is_cluster`: Whether part of multi-node cluster

### Example Configuration

```python
# Create a 3-node local cluster
cluster = create_local_cluster_config(num_nodes=3, base_port=9000)

# Build config for node-2
node_config = cluster.build_node_config("node-2")
# node_config.node_id = "node-2"
# node_config.host = "127.0.0.1"
# node_config.port = 9001
# node_config.peers = [node-1, node-3]
```

### Cluster Configuration Format

```json
{
  "nodes": [
    {
      "node_id": "node-1",
      "host": "127.0.0.1",
      "port": 9000
    },
    {
      "node_id": "node-2",
      "host": "127.0.0.1",
      "port": 9001
    },
    {
      "node_id": "node-3",
      "host": "127.0.0.1",
      "port": 9002
    }
  ]
}
```

---

## RPC Server

### Server Lifecycle

```
create_rpc_server()
    ↓
await server.start()     # Listen on configured port
    ↓
register_handler()       # Register RPC handlers
    ↓
await server.serve_forever()  # Accept connections
    ↓
await server.stop()      # Shutdown gracefully
```

### Registering Handlers

```python
server = RPCServer(config)
await server.start()

# Register RequestVote handler
server.register_handler("RequestVote", handle_request_vote)

# Register AppendEntries handler
server.register_handler("AppendEntries", handle_append_entries)

await server.serve_forever()
```

### Handler Interface

Each handler is an async function:

```python
async def handle_request_vote(data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle RequestVote RPC."""
    term = data['term']
    candidate_id = data['candidate_id']
    # ... implement logic ...
    return {
        "term": current_term,
        "vote_granted": True
    }
```

---

## RPC Client

### Client Lifecycle

```
RPCClient(peer_config)
    ↓
await client.connect()    # Connect to peer
    ↓
await client.request_vote(...)
await client.append_entries(...)
    ↓
await client.disconnect() # Close connection
```

### Sending RPCs

```python
client = RPCClient(peer_config, timeout=5.0)

# Send RequestVote
response = await client.request_vote(
    term=5,
    candidate_id="node-1",
    last_log_index=10,
    last_log_term=4
)

# Send AppendEntries
response = await client.append_entries(
    term=5,
    leader_id="node-1",
    prev_log_index=10,
    prev_log_term=4,
    entries=[...],
    leader_commit=8
)
```

### Connection Management

- Auto-connect on first RPC
- Automatic retry with exponential backoff (3 attempts max)
- Connection pooling via `RPCClientPool`
- Graceful disconnect

### Error Handling

```python
response = await client.request_vote(...)

if response is None:
    # RPC failed (timeout, connection error, etc.)
    # Client automatically retries
    pass
else:
    # Successful response
    term = response['term']
    vote_granted = response['vote_granted']
```

---

## Error Handling

### Server-Side Validation

The RPC server validates all incoming messages:

1. **Empty messages**: Rejected
2. **Invalid JSON**: Error response returned
3. **Non-string rpc_type**: Validation error
4. **Unknown RPC type**: "Unknown RPC type" error
5. **Malformed data**: Handler receives error

### Protocol Errors

```python
from src.rpc.protocol import (
    ProtocolError,
    MessageTooLargeError,
    InvalidMessageError
)

try:
    encoded = MessageEncoder.encode(message)
except MessageTooLargeError:
    # Message exceeds 10MB limit
    pass
except ProtocolError:
    # Generic protocol error
    pass
```

### Error Response Format

```json
{
  "success": false,
  "error": "Detailed error message",
  "request_id": "original-request-id"
}
```

---

## Implementation Examples

### Creating a Cluster

```python
from src.rpc.config import create_local_cluster_config

# Create 3-node cluster on localhost
cluster = create_local_cluster_config(num_nodes=3, base_port=9000)

# Get config for specific node
node2_config = cluster.build_node_config("node-2")
```

### Starting RPC Server

```python
from src.rpc.server import create_rpc_server

server = await create_rpc_server(node_config)

# Register handlers
from src.rpc.handlers import create_request_vote_handler

handler = create_request_vote_handler(state_provider)
server.register_handler("RequestVote", handler.handle)

# Server is now running and accepting connections
```

### Broadcasting RPCs

```python
from src.rpc.client import RPCClientPool

client_pool = RPCClientPool(node_config.peers)

# Send heartbeat to all peers
responses = await client_pool.broadcast_heartbeat(
    leader_id="node-1",
    term=5,
    leader_commit=8
)

# responses = {"node-2": {...}, "node-3": {...}, ...}
```

---

## Testing

### Unit Tests

Located in `tests/test_rpc.py`:

- Message encoding/decoding
- Protocol compliance
- Configuration validation
- Error handling
- Serialization roundtrips

### Running Tests

```bash
pytest tests/test_rpc.py -v
```

---

## Performance Considerations

### Protocol Efficiency

- **Minimal overhead**: 4-byte length prefix per message
- **Batch support**: Multiple entries per AppendEntries
- **Connection reuse**: Persistent TCP connections
- **Async I/O**: Non-blocking send/receive

### Timeouts

- **RPC timeout**: 5 seconds (configurable)
- **Retry attempts**: 3 with exponential backoff
- **Backoff formula**: 0.5s × 2^attempt

### Scalability

- One TCP connection per peer
- Non-blocking async operations
- Concurrent requests via asyncio
- Connection pooling support

---

## Security Notes (Phase 7+)

Current implementation has no security:
- ⚠️ No authentication
- ⚠️ No encryption (TLS)
- ⚠️ No authorization

Future phases will add:
- [ ] TLS/SSL encryption
- [ ] Mutual authentication
- [ ] Rate limiting
- [ ] Access control

---

## Debugging

### Enable Debug Logging

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('src.rpc')
logger.setLevel(logging.DEBUG)
```

### Common Issues

**Issue**: "Connection refused"
- Check peer is running
- Verify host/port configuration
- Check firewall rules

**Issue**: "Protocol error: Invalid message length"
- Verify peer uses correct protocol
- Check message encoding
- Look for corrupted data

**Issue**: "RPC timeout"
- Check network connectivity
- Verify peer is responsive
- Increase timeout if needed

---

## Next Phase (Phase 3)

Phase 3 will implement:
- Leader election state machine
- Election timeout management
- Vote counting and majority logic
- Term persistence

These will use the RPC layer built in Phase 2.

---

*Phase 2 Documentation - Days 3-4*
