# Design Document: Distributed Key-Value Store with Raft Consensus

## Overview

This document outlines the architecture and design decisions for a distributed key-value store built on the Raft consensus algorithm in Python. The implementation is designed to be production-ready with proper fault tolerance, network partition handling, and linearizable consistency guarantees.

## Architecture Layers

### 1. Storage Engine (Phase 1)
- In-memory dictionary-backed KV store
- Write-ahead log (WAL) for durability
- Log replay on startup
- Per-entry metadata (term, index, type)

### 2. RPC Layer (Phase 2)
- Async TCP server with length-prefixed message protocol
- RequestVote and AppendEntries RPC implementations
- Peer discovery and heartbeat mechanism
- Connection management and retry logic

### 3. Raft Core (Phase 3-4)
- State machine: Follower, Candidate, Leader
- Election timeout with randomization (150-300ms)
- Term-based voting with persistence
- Log replication with majority-based commits
- Log inconsistency detection and repair

### 4. Fault Tolerance (Phase 5)
- Network partition simulation
- Message dropping and delay injection
- Split-brain prevention verification
- Chaos testing harness

### 5. Client API (Phase 6)
- HTTP REST interface
- Leader discovery and redirection
- Linearizable read support
- Idempotent request handling

## Key Design Decisions

### Split-Brain Prevention

Raft prevents split-brain through:
1. **Quorum requirement**: A leader can only be elected with votes from a majority of nodes
2. **Term comparison**: All RPC responses include the current term; higher-term messages invalidate previous leaders
3. **Persistent state**: `currentTerm` and `votedFor` are persisted before RPC responses to ensure correctness

### Consistency Model

- **Writes**: Must be replicated to a majority before being committed and applied to the state machine
- **Reads**: Linearizable via read-index or lease-based reads (to be chosen in Phase 6)
- **Log entries**: Never applied until committed; committed entries are never lost

### Persistence Strategy

- **Write-ahead log**: All state changes logged before in-memory application
- **Atomic persistence**: Use fsync() on relevant updates to guarantee durability
- **Metadata file**: Separate storage for `currentTerm` and `votedFor`

## Phase Breakdown

### Phase 1: Single-node KV Store
- Basic in-memory storage with GET, SET, DELETE
- WAL implementation for crash recovery
- HTTP API for client access

### Phase 2: Cluster Bootstrap + RPC Layer
- Node configuration and peer discovery
- Async TCP RPC protocol (length-prefixed messages)
- Heartbeat exchange mechanism

### Phase 3: Leader Election
- Full state machine implementation
- Randomized timeouts
- Vote counting and majority logic
- Term persistence

### Phase 4: Log Replication
- Client write handling
- Commit index advancement
- Log repair and inconsistency handling
- Majority-based commit logic

### Phase 5: Fault Tolerance
- Network partition simulation
- Chaos test harness
- Invariant verification (no split-brain, no data loss)

### Phase 6: Client-Facing Correctness
- Client library with leader discovery
- Linearizable read implementation
- Graceful retry handling

### Phase 7 (Stretch): Advanced Features
- Log compaction and snapshotting
- Dynamic cluster membership
- Metrics endpoint

## Testing Strategy

- **Unit tests**: Storage, persistence, state machine transitions
- **Integration tests**: Multi-node cluster behavior
- **Chaos tests**: Fault injection, partition healing, node restarts
- **Invariant tests**: No split-brain, no committed data loss

## Correctness Guarantees

1. **Linearizability**: All reads and writes appear to execute in a consistent order
2. **Durability**: Committed entries survive any finite number of node failures
3. **Liveness**: The cluster recovers and makes progress after any partition heals
4. **Safety**: No two leaders elected in the same term; no committed entry is ever lost

---

*Updated: Day 1*
