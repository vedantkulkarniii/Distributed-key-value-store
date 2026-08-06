# Phase 2 Part 2: Cluster Bootstrap & Peer Communication

## Overview

This document describes cluster bootstrap, peer discovery, and heartbeat mechanisms implemented in Phase 2 Part 2 (Days 3-4).

## Cluster Bootstrap Process

### Initialization Sequence

```
1. Create LocalConfig for this node
   ├─ node_id: unique identifier
   ├─ host: listen address
   ├─ port: RPC port
   └─ peers: list of peer NodeConfigs

2. Create ClusterBootstrap instance
   └─ Orchestrates bootstrap steps

3. Call bootstrap.bootstrap()
   ├─ Step 1: Start RPC server
   │  └─ Listen for incoming RPC connections
   ├─ Step 2: Discover peers
   │  ├─ Create RPC client pool
   │  └─ Attempt connections to all peers
   └─ Step 3: Start heartbeat monitoring
      └─ Track leader and peer health
```

### Code Example

```python
from src.rpc.config import create_local_cluster_config
from src.rpc.discovery import ClusterBootstrap

# Create cluster configuration
cluster_config = create_local_cluster_config(num_nodes=3, base_port=9000)
node_config = cluster_config.build_node_config("node-1")

# Bootstrap the cluster
bootstrap = ClusterBootstrap(node_config)
success = await bootstrap.bootstrap()

if success:
    print("Node ready for operation")
    status = bootstrap.get_cluster_status()
    print(f"Connected peers: {status['peers_connected']}")
```

## Peer Discovery

### Discovery Process

**Goal**: Establish connectivity to all known peers

**Steps**:
1. Create RPC client for each peer
2. Attempt connection with retry logic
3. Track discovered vs failed peers
4. Periodically retry failed peers

### Retry Logic

- **Attempts per peer**: 5 total attempts
- **Backoff**: Linear: 1s, 2s, 3s, 4s, 5s
- **Connection timeout**: 5 seconds per attempt
- **Auto-rediscovery**: Every 10 seconds for failed peers

### Example

```python
from src.rpc.discovery import PeerDiscovery

discovery = PeerDiscovery(node_config)

# Discover peers
success = await discovery.discover_peers()

# Check status
connected = discovery.get_connected_peers()
failed = discovery.get_failed_peers()
ready = discovery.is_cluster_ready()
```

## Heartbeat Mechanism

### Purpose

Heartbeats serve multiple functions:

1. **Election timeout reset** (Phase 3+)
   - Followers reset election timeout on valid heartbeat
   - Prevents unnecessary elections

2. **Leader detection**
   - Followers identify the current leader
   - Helps with request routing

3. **Commit index propagation** (Phase 4+)
   - Leader sends commit index
   - Followers apply committed entries

4. **Replication** (Phase 4+)
   - Sends log entries to replicate

### Heartbeat Interval

- **Leader sends**: Every 150ms (0.15s)
- **Election timeout**: 150-300ms (randomized)
- **Ratio**: Heartbeat ~10x smaller than election timeout
- **Rationale**: Ensures followers rarely timeout with active leader

### Timing Manager

Unified management of heartbeat and election timing:

```python
from src.rpc.heartbeat import create_timing_manager

timing = create_timing_manager("node-1")

# Callbacks for state transitions
await timing.become_leader()  # Start heartbeats
await timing.become_follower()  # Start election timeout

# Callbacks on heartbeat/timeout
timing.heartbeat.set_callbacks(send_heartbeat_callback)
timing.election_timeout.set_callback(on_election_timeout)

# Reset timeout on valid heartbeat
timing.reset_election_timeout()

# Shutdown
await timing.shutdown()
```

## Heartbeat Monitoring

### Health Metrics per Peer

Tracked metrics:
- `heartbeat_count`: Number of valid heartbeats received
- `error_count`: Number of invalid heartbeats
- `error_rate`: Percentage of errors
- `is_healthy`: True if heartbeat received within 1 second
- `uptime_seconds`: Time since first seen
- `last_error`: Most recent error message

### Cluster Health Status

- `current_leader`: Identified leader node ID
- `healthy_peers`: Number of nodes with recent heartbeats
- `cluster_health_percent`: Health as percentage
- `total_heartbeats`: Total valid heartbeats received
- `total_errors`: Total invalid heartbeats

### Example

```python
from src.rpc.heartbeat_monitor import HeartbeatMonitor

monitor = HeartbeatMonitor("node-1", peer_ids=["node-2", "node-3"])

# Record incoming heartbeat
monitor.record_heartbeat(
    source_node_id="node-2",
    term=5,
    commit_index=10,
    is_valid=True
)

# Check cluster health
status = monitor.get_cluster_status()
print(f"Leader: {status['current_leader']}")
print(f"Cluster health: {status['cluster_health_percent']}%")

# Get recent heartbeats
recent = monitor.get_recent_heartbeats(limit=10)
```

## Connection Management

### Connection Pooling

Features:
- Reuse TCP connections across multiple RPC calls
- Automatic cleanup of idle connections
- Health monitoring per connection
- Graceful error handling

### Connection Monitor

Tracks per-peer:
- Successful connections
- Failed connections
- Connection latency statistics
- Success rate

### Example

```python
from src.rpc.connection import ConnectionPool

pool = ConnectionPool("default")

# Add connection
await pool.add_connection("peer-1", reader, writer)

# Get connection
reader, writer = await pool.get_connection("peer-1")

# Cleanup
await pool.cleanup_idle()  # Remove unused connections
await pool.close_all()     # Close all
```

## Cluster Readiness

### Definition

Cluster is ready when:
- Local node has RPC server running
- Quorum (majority) of nodes are reachable
- Single-node clusters are always ready

### Quorum Calculation

For N total nodes:
```
quorum = (N / 2) + 1

Examples:
  3 nodes: quorum = 2
  5 nodes: quorum = 3
  7 nodes: quorum = 4
```

### Example

```python
discovery = PeerDiscovery(node_config)
await discovery.discover_peers()

if discovery.is_cluster_ready():
    print("Cluster ready for elections and log replication")
else:
    print("Waiting for quorum...")
```

## Configuration Examples

### 3-Node Local Cluster

```python
from src.rpc.config import create_local_cluster_config

# Create on localhost, ports 9000-9002
cluster = create_local_cluster_config(num_nodes=3, base_port=9000)

# node-1: 127.0.0.1:9000
# node-2: 127.0.0.1:9001
# node-3: 127.0.0.1:9002
```

### Custom Multi-Host Cluster

```python
from src.rpc.config import ClusterConfig, PeerInfo

config = ClusterConfig(nodes=[
    PeerInfo(node_id="node-1", host="192.168.1.10", port=9000),
    PeerInfo(node_id="node-2", host="192.168.1.11", port=9000),
    PeerInfo(node_id="node-3", host="192.168.1.12", port=9000)
])

node2_config = config.build_node_config("node-2")
```

## Failure Scenarios

### Network Partition

**Scenario**: Cluster splits into two groups

**Detection**:
- Partitioned nodes send heartbeats with higher term
- Main partition rejects with "stale term" or waits for timeout
- HeartbeatMonitor tracks errors from partitioned nodes

**Recovery**:
- Partition heals
- Auto-rediscovery reconnects nodes
- Cluster resync happens in Phase 4+

### Node Failure

**Scenario**: A node crashes

**Detection**:
- No heartbeats from failed node
- `is_healthy` becomes False after 1 second timeout
- Error rate increases

**Recovery**:
- Replication catches up when node restarts (Phase 4+)
- Auto-rediscovery attempts to reconnect

### Slow Network

**Scenario**: High latency connections

**Impact**:
- Heartbeats may be delayed
- Possible false "timeout" detection
- But handled by randomized election timeout

**Mitigation**:
- Increase heartbeat interval if needed
- Adjust election timeout ranges
- Monitor latency via ConnectionMonitor

## Testing

### Unit Tests

Located in `tests/test_cluster_bootstrap.py`:

```bash
pytest tests/test_cluster_bootstrap.py -v
```

Covers:
- Cluster configuration validation
- Peer discovery
- Heartbeat monitoring
- Node join/leave scenarios
- Quorum calculations

### Integration Tests (Future)

Phase 5 will add:
- Multi-node cluster startup tests
- Network partition simulation
- Heartbeat under various latencies
- Rolling node restarts

## Performance Characteristics

### Network Overhead

**Per heartbeat** (leader → followers):
- TCP packet: ~40 bytes header
- AppendEntries RPC: ~200-500 bytes (depending on log entries)
- Response: ~100 bytes
- Total per peer: ~300-600 bytes / 150ms = ~2-4 KBps per peer

**For 5-node cluster**:
- Leader sends 4 heartbeats every 150ms
- Total: ~1.6-2.4 KBps

### Latency

**Heartbeat propagation**:
- Generation → Network → Reception: <10ms under normal conditions
- Election timeout reaction: <300ms (max timeout)

### Scalability

- Current design supports 3-5 nodes without issues
- Connection pooling scales to 50+ peers
- Heartbeat loop is O(N) where N = number of peers
- Monitor tracks O(N) state

## Debugging

### Enable Debug Logging

```python
import logging

# RPC module logging
logging.getLogger('src.rpc').setLevel(logging.DEBUG)

# Connection logging
logging.getLogger('src.rpc.client').setLevel(logging.DEBUG)

# Discovery logging
logging.getLogger('src.rpc.discovery').setLevel(logging.DEBUG)
```

### Common Issues

**Issue**: "Failed to discover X after N attempts"
- Peer node not running
- Firewall blocking port
- Wrong IP/port configuration

**Issue**: "Cluster not ready (no quorum)"
- Not enough peers connected
- Network partition isolating this node
- Check `discovery.get_failed_peers()`

**Issue**: "Leader changed from X to Y too frequently"
- Network latency or instability
- Election timeout too aggressive
- Check heartbeat monitor for errors

## Next Phase (Phase 3)

Phase 3 will add:
- Leader election state machine
- Vote counting and term management
- Follower election timeout triggering
- State transitions: Follower ↔ Candidate ↔ Leader

These will use the heartbeat and connection infrastructure built here.

---

*Phase 2 Part 2 Documentation - Days 3-4*
