# Architecture Overview: Distributed Key-Value Store with Raft

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CLIENT APPLICATIONS                             │
│                    (HTTP REST Clients, Python SDK, etc.)                  │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                    ┌────────────▼──────────────┐
                    │    HTTP REST API Layer    │ (Phase 1 ✅)
                    │     (FastAPI)             │
                    │                           │
                    │  • GET /kv/{key}          │
                    │  • POST /kv/{key}         │
                    │  • DELETE /kv/{key}       │
                    │  • GET /kv                │
                    │  • DELETE /kv             │
                    │  • GET /health            │
                    │  • GET /info              │
                    └────────────┬──────────────┘
                                 │
                    ┌────────────▼──────────────────────────┐
                    │  Raft State Machine & Core Logic      │ (Phase 3-4)
                    │                                       │
                    │  States:                              │
                    │  ├─ Follower                          │
                    │  ├─ Candidate                         │
                    │  └─ Leader                            │
                    │                                       │
                    │  Mechanisms:                          │
                    │  ├─ Leader election (randomized)      │
                    │  ├─ Log replication                   │
                    │  ├─ Commit index tracking             │
                    │  └─ Majority vote counting            │
                    └────────────┬──────────────────────────┘
                                 │
                ┌────────────────┼────────────────┐
                │                │                │
    ┌───────────▼────────┐ ┌────▼──────────┐ ┌──▼───────────────┐
    │  RPC Protocol      │ │  RPC Client   │ │  Network Layer   │ (Phase 2)
    │  (TCP/gRPC)        │ │  (Async)      │ │  (Heartbeats,    │
    │                    │ │               │ │   Message Queue) │
    │  • RequestVote     │ │ • Send RVote  │ │                  │
    │  • AppendEntries   │ │ • Send AE     │ │                  │
    │  • InstallSnapshot │ │ • Retry Logic │ │                  │
    └────────────────────┘ └───────────────┘ └──────────────────┘
                │
                │ (Peer-to-Peer RPCs)
                │
    ┌───────────▼─────────────────────────────────────────────────┐
    │         Distributed Cluster (3-5 Nodes)                     │
    │                                                              │
    │  ┌──────────┐   ┌──────────┐   ┌──────────┐                │
    │  │ Node 1   │   │ Node 2   │   │ Node 3   │   ...          │
    │  │ (Leader) │◄─►│(Follower)│◄─►│(Follower)│                │
    │  └──────────┘   └──────────┘   └──────────┘                │
    │       ▲              │              │                       │
    └───────┼──────────────┼──────────────┼───────────────────────┘
            │              │              │
            └──────────────┴──────────────┘
                      (Consensus)
                      
            ┌─────────────────────────────┐
            │   Persistence Layer         │ (Phase 1 ✅)
            │   (Write-Ahead Log)         │
            │                             │
            │  ├─ WAL file                │
            │  │  (append-only, fsync)    │
            │  │                          │
            │  ├─ Persistent state        │
            │  │  (term, votedFor)        │
            │  │                          │
            │  └─ Snapshot file (Phase 7) │
            │     (for log compaction)    │
            └─────────────────────────────┘
                      │
            ┌─────────▼──────────┐
            │   Disk Storage     │
            │   (fsync guarantees)       │
            └────────────────────┘
```

---

## Component Details

### Layer 1: HTTP REST API (Phase 1 ✅)

**Files**: `src/api/server.py`

```python
class KVStoreAPI:
    """HTTP interface for distributed KV store"""
    
    async def get(key: str)
    async def set(key: str, value: Any)
    async def delete(key: str)
    async def get_all()
    async def clear()
```

**Endpoints**:
- `GET /health` - Health check
- `GET /info` - Store metadata
- `GET /kv/{key}` - Get value
- `POST /kv/{key}` - Set value
- `DELETE /kv/{key}` - Delete key
- `GET /kv` - Get all
- `DELETE /kv` - Clear all

**Error Handling**:
- Custom exception handlers
- Consistent error response format
- Proper HTTP status codes (200, 201, 400, 404, 422, 500)

---

### Layer 2: Raft State Machine (Phase 3-4)

**Files**: `src/raft/` (to be implemented)

**State Machine**:
```
┌──────────┐  election timeout
│ Follower ├────────────────────┐
└─────▲────┘                    │
      │                         ▼
      │  receive valid term   ┌──────────┐
      │  or AppendEntries     │ Candidate│
      │                       └────┬─────┘
      │                            │
      │                    receives majority votes
      │                            │
      │                            ▼
      │                       ┌────────────┐
      └───────────────────────┤   Leader   │
         higher term or lost  └────────────┘
         quorum (from leader)
```

**Key Properties**:
1. **Election Restriction**: Candidate's log must be ≥ voter's log
2. **Term Comparison**: All operations check term before proceeding
3. **Persistent State**: Term and votedFor persist before RPC responses
4. **Majority Quorum**: Leader election requires majority votes

---

### Layer 3: RPC Layer (Phase 2)

**Files**: `src/rpc/` (to be implemented)

**Protocol**: Async TCP with length-prefixed messages

```
┌─────────────────────────┐
│ RequestVote RPC         │
├─────────────────────────┤
│ term: int               │
│ candidateId: str        │
│ lastLogIndex: int       │
│ lastLogTerm: int        │
└─────────────────────────┘

┌─────────────────────────┐
│ AppendEntries RPC       │
├─────────────────────────┤
│ term: int               │
│ leaderId: str           │
│ prevLogIndex: int       │
│ prevLogTerm: int        │
│ entries: LogEntry[]     │
│ leaderCommit: int       │
└─────────────────────────┘

┌─────────────────────────┐
│ LogEntry                │
├─────────────────────────┤
│ term: int               │
│ index: int              │
│ data: bytes (command)   │
│ type: SET|DELETE|NOOP   │
└─────────────────────────┘
```

**Features**:
- Async TCP server for receiving RPCs
- Async TCP client for sending RPCs
- Connection pooling and retry logic
- Message serialization/deserialization

---

### Layer 4: Persistence (Phase 1 ✅)

**Files**: `src/storage/`

**Write-Ahead Log Pattern**:

```
Write Operation:
  1. Append to WAL file
  2. Call fsync() on WAL
  3. Update in-memory store
  4. Return to client
  
Crash Recovery:
  1. Read all WAL entries
  2. Replay each entry to in-memory store
  3. Resume normal operation
```

**Persistent State**:
- WAL file: All operations (SET, DELETE, CLEAR)
- Metadata: Current term, voted-for candidate
- Snapshot: Current state machine (Phase 7)

**Durability Guarantees**:
- ✅ All writes fsync'd before return
- ✅ No data loss on crashes
- ✅ Automatic recovery on startup

---

### Layer 5: Storage Engine (Phase 1 ✅)

**Files**: `src/storage/store.py`

```python
class KeyValueStore:
    """In-memory dictionary-backed store"""
    
    async def get(key) -> Optional[Any]
    async def set(key, value, ttl_seconds=None)
    async def delete(key) -> bool
    async def exists(key) -> bool
    async def clear()
    async def get_all() -> dict
    async def size() -> int
```

**Features**:
- Thread-safe via asyncio.Lock
- Optional TTL support with lazy cleanup
- Support for any JSON-serializable type
- No transactions (single-key operations)

---

## Data Flow Diagrams

### Write Operation Flow

```
Client Request: POST /kv/user:1 {"value": "Alice"}
    │
    ▼
┌────────────────┐
│ HTTP API Layer │  Validate request, parse JSON
└────────┬───────┘
         │
         ▼
┌────────────────────┐
│ Raft State Machine │  (Phase 1: Skip - single node)
│ (Leader only)      │  (Phase 3+: Append to log)
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│ WAL Persistence    │  Append to WAL file
│                    │  fsync() to disk
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│ In-Memory Store    │  Update in-memory dict
└────────┬───────────┘
         │
         ▼
Response: 201 Created {"status": "success", "key": "user:1"}
```

### Read Operation Flow

```
Client Request: GET /kv/user:1
    │
    ▼
┌────────────────┐
│ HTTP API Layer │  Parse request
└────────┬───────┘
         │
         ▼
┌────────────────────┐
│ In-Memory Store    │  Get from dict (lock-free read)
│                    │  Return value or null
└────────┬───────────┘
         │
         ▼
Response: 200 OK {"key": "user:1", "value": "Alice", "exists": true}
```

### Replication Flow (Phase 4)

```
Leader:
  1. Client writes key-value
  2. Append to leader's log
  3. Send AppendEntries to followers
  4. Followers append to their logs
  5. Followers send ACK
  6. Leader receives majority ACKs
  7. Leader advances commitIndex
  8. Leader applies to state machine
  9. Send commitIndex update to followers
  10. Followers apply to state machine

Followers:
  1. Receive AppendEntries from leader
  2. Check term (reject if stale)
  3. Check prevLogIndex/prevLogTerm (repair if conflict)
  4. Append entries to log
  5. Send ACK to leader
  6. Wait for commitIndex from leader
  7. Apply committed entries to state machine
```

---

## Consistency Model

### Linearizability

Every read and write appears to execute at a single point in time, with all writes before it completing.

**Implementation**:
- **Writes**: Must be replicated to majority (committed) before applying
- **Reads**: Via read-index (get leader's commitIndex, wait for local apply)

### Durability

Every committed entry is guaranteed to survive any finite number of node failures.

**Implementation**:
- Majority replication ensures quorum can always recover
- Write-ahead log prevents data loss
- Fsync guarantees persistence

### Availability

The cluster remains available and makes progress as long as a majority is alive.

**Implementation**:
- Any node can become leader if majority responds
- Followers detect leader failure via timeout
- New elections proceed in parallel

---

## Phase Timeline

| Phase | Scope | Status | Days |
|-------|-------|--------|------|
| 1 | Single-node KV store + WAL | ✅ | 2 |
| 2 | RPC layer + cluster bootstrap | In Progress | 2 |
| 3 | Leader election | Pending | 3 |
| 4 | Log replication | Pending | 3 |
| 5 | Fault tolerance & chaos tests | Pending | 2 |
| 6 | Client correctness | Pending | 1 |
| 7 | Stretch: compaction, membership | Pending | 1 |

**Total**: 15 days

---

## Key Files

### Storage
- `src/storage/store.py` - In-memory KV store (155 lines)
- `src/storage/wal.py` - Write-ahead log (282 lines)
- `src/storage/recovery.py` - Crash recovery (103 lines)

### API
- `src/api/server.py` - FastAPI HTTP server (365 lines)

### Raft (To be implemented)
- `src/raft/state_machine.py` - State machine
- `src/raft/log.py` - Raft log management
- `src/raft/election.py` - Leader election
- `src/raft/replication.py` - Log replication

### RPC (To be implemented)
- `src/rpc/server.py` - RPC server
- `src/rpc/client.py` - RPC client
- `src/rpc/protocol.py` - Message protocol

### Testing
- `tests/test_storage.py` - Storage tests (400+ lines, 37+ tests)
- `tests/test_api.py` - API tests (500+ lines, 50+ tests)
- `tests/test_raft.py` - Raft tests (to be added)
- `tests/test_chaos.py` - Chaos/fault injection tests (to be added)

### Documentation
- `README.md` - Getting started and API reference
- `docs/DESIGN.md` - Architecture and design decisions
- `docs/PHASE_1_STORAGE.md` - Phase 1 details
- `ARCHITECTURE.md` - This file
- `VERIFICATION_PHASE1.md` - Phase 1 verification

---

## Deployment Topology (Planned - Phase 2+)

### Single Node (Phase 1 ✅)
```
┌──────────────┐
│  Node 1      │
│ (Leader)     │
│              │
│ API: 8000    │
│ RPC: 9000    │
└──────────────┘
     │
     ▼
   Disk
```

### 3-Node Cluster (Phase 2+)
```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  Node 1      │  │  Node 2      │  │  Node 3      │
│ (Leader)     │  │ (Follower)   │  │ (Follower)   │
│              │  │              │  │              │
│ API: 8000    │  │ API: 8001    │  │ API: 8002    │
│ RPC: 9000    │  │ RPC: 9001    │  │ RPC: 9002    │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │
       └────────────┬────┴────────┬────────┘
                    │            │
                    ▼            ▼
                  Disk1        Disk2        Disk3
```

---

## Security Considerations

### Current (Phase 1-3)
- No authentication
- No encryption
- Local network assumed trusted

### Future (Phase 7+)
- TLS/SSL for RPC
- Mutual authentication
- Rate limiting
- Access control lists

---

## Performance Targets

| Operation | Target | Achieved |
|-----------|--------|----------|
| Single SET | <10ms | ~1-5ms ✅ |
| Single GET | <1ms | <1ms ✅ |
| Replication latency | <100ms | To be tested |
| Cluster recovery | <500ms | To be tested |
| Failover time | <500ms | To be tested |

---

## Monitoring & Observability

### Metrics Exposed
- Current term
- Leader ID
- Log size
- Commit index
- Last applied index
- Replication lag per follower

### Logging
- Operation logs (GET/SET/DELETE)
- Election logs
- Replication logs
- Error logs

### Health Checks
- `/health` endpoint
- Leader heartbeat detection
- Follower connectivity

---

## Conclusion

This architecture builds a robust, distributed key-value store with Raft consensus. Each phase adds capabilities:

1. **Phase 1** ✅: Durable, single-node KV store
2. **Phase 2**: Network and RPC layer
3. **Phase 3**: Leader election
4. **Phase 4**: Log replication and consistency
5. **Phase 5**: Fault tolerance
6. **Phase 6**: Client guarantees
7. **Phase 7**: Advanced features

The design prioritizes **correctness** over performance, with comprehensive testing at each phase.

---

*Last Updated: Day 2, End of Phase 1*
