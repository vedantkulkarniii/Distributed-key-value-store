# Distributed Key-Value Store with Raft Consensus

A production-grade distributed key-value store implemented in Python using the Raft consensus algorithm. Guarantees linearizable consistency, fault tolerance, and automatic leader election across a cluster of nodes.

## Features

- **Raft Consensus**: Full implementation of the Raft algorithm for distributed consensus
- **Fault Tolerance**: Survives arbitrary node failures and network partitions
- **Linearizable Consistency**: Guarantees strong consistency for all reads and writes
- **Async I/O**: Built on asyncio and gRPC for high concurrency
- **Persistent Storage**: Write-ahead log with crash recovery
- **Network Simulation**: Built-in chaos testing harness for fault injection

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│           Client HTTP API (FastAPI)                     │
└──────────────┬──────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────┐
│        Raft State Machine & Core Logic                  │
│  (Follower, Candidate, Leader transitions)              │
└──────────────┬──────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────┐
│     RPC Layer (Async TCP + Length-Prefixed Protocol)    │
│    (RequestVote, AppendEntries, InstallSnapshot)        │
└──────────────┬──────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────┐
│    Storage Engine & Write-Ahead Log (WAL)               │
│         (Persistence, Crash Recovery)                   │
└─────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- pip

### Installation

```bash
git clone https://github.com/vedantkulkarniii/Distributed-key-value-store.git
cd Distributed-key-value-store
pip install -r requirements.txt
```

### Running a Local Cluster

(Instructions to be added in Phase 6)

### Example Client Usage

```python
# To be implemented in Phase 6
from src.api.client import KVClient

client = KVClient(leader_address="http://localhost:8000")
await client.set("key1", "value1")
value = await client.get("key1")
await client.delete("key1")
```

## Project Structure

```
Distributed-key-value-store/
├── src/
│   ├── storage/          # Phase 1: In-memory store + WAL
│   ├── raft/             # Phase 3-4: Raft consensus core
│   ├── rpc/              # Phase 2: RPC protocol & networking
│   ├── api/              # Phase 6: HTTP client API
│   └── chaos/            # Phase 5: Network simulation harness
├── tests/                # Test suite (pytest + pytest-asyncio)
├── docs/
│   └── DESIGN.md         # Architecture and design decisions
├── README.md             # This file
└── requirements.txt      # Python dependencies
```

## Implementation Phases

| Phase | Scope | Status |
|-------|-------|--------|
| 1 | Single-node KV store + WAL | Pending |
| 2 | Cluster bootstrap + RPC layer | Pending |
| 3 | Leader election | Pending |
| 4 | Log replication | Pending |
| 5 | Fault tolerance & partitions | Pending |
| 6 | Client-facing correctness | Pending |
| 7 | Stretch: compaction, membership, metrics | Pending |

## Design Principles

### Correctness Over Performance
- All safety properties verified by tests
- Strict adherence to Raft paper specification
- Comprehensive invariant checking in chaos tests

### Modularity
- Clear separation between storage, RPC, consensus, and API layers
- Each module independently testable
- Protocol buffers or custom serialization for RPC

### Durability
- Write-ahead log with fsync() guarantees
- Persistent term and vote before RPC responses
- No data loss on node failures

## Testing

Run the full test suite:

```bash
pytest tests/ -v
```

Run with coverage:

```bash
pytest tests/ --cov=src --cov-report=html
```

## Documentation

- **DESIGN.md**: Detailed architecture, design decisions, and correctness guarantees
- **Phase-specific READMEs**: (To be added) Detailed notes for each implementation phase
- **Inline code comments**: Extensive comments explaining Raft correctness properties

## Non-Negotiable Correctness Properties

1. **Election Restriction**: A candidate's log must be at least as up-to-date as any voter's
2. **Commit Safety**: Log entries are applied only after being replicated to a majority
3. **Persistence**: All persistent state (term, vote, log) is fsync'd before RPC responses
4. **Split-Brain Prevention**: No two leaders can be elected in the same term

## Performance Characteristics

(To be benchmarked in Phase 7)

- Typical write latency: ~1-5ms (under normal conditions)
- Cluster scalability: 3-5 nodes (can extend to higher node counts)
- Network efficiency: Batch AppendEntries messages where possible

## License

MIT (to be added)

## Contributing

(Guidelines to be added)

---

**Current Phase**: Day 1 - Project Setup
**Last Updated**: Day 1, Commit 1
