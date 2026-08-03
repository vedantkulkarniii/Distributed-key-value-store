# Phase 1: Single-Node Key-Value Store

## Overview

Phase 1 implements a basic but complete single-node key-value store with persistent storage and crash recovery. This provides the foundation for the distributed system built in later phases.

## Design

### Components

1. **In-Memory Store** (`src/storage/store.py`)
   - Simple dictionary-backed KV store
   - Async-safe via `asyncio.Lock`
   - Supports GET, SET, DELETE operations
   - Optional TTL support for key expiration

2. **Write-Ahead Log (WAL)** (`src/storage/wal.py`)
   - Append-only log file stored on disk
   - Each operation is logged as a JSON line
   - fsync() on every write to guarantee durability
   - Enables crash recovery

3. **Recovery Engine** (`src/storage/recovery.py`)
   - Replays WAL on startup
   - Restores in-memory store to pre-crash state
   - Gracefully handles empty logs and malformed entries

4. **Persistent Store Wrapper** (`src/storage/wal.py::PersistentKeyValueStore`)
   - Combines in-memory store with WAL
   - Ensures all operations are logged before being applied
   - Simple "apply after log" pattern

### Persistence Model

**Critical Design**: Write-Ahead Log (WAL)

1. Client issues a write request (SET or DELETE)
2. Operation is appended to WAL and fsync'd to disk
3. Only after successful WAL persist does the in-memory store get updated
4. If the process crashes:
   - In-memory state is lost
   - On restart, all WAL entries are replayed
   - In-memory state is fully restored

This is essential for correctness: **the log is the source of truth, not the in-memory store**.

### TTL (Time-To-Live) Support

Optional feature that allows keys to expire after a specified duration:

```python
await store.set("key", "value", ttl_seconds=3600)  # Expires in 1 hour
```

Expired keys are:
- Lazily removed on access (GET, EXISTS, DELETE)
- Cleaned up via `cleanup_expired()` background task
- Excluded from `get_all()` and `size()` operations

Benefits:
- Low memory overhead (only stores expiry timestamp)
- Automatic cleanup without a separate timer task
- Common pattern in caching systems (Redis, Memcached)

## API

### Basic Operations

```python
store = StorageEngine(wal_path="data/kv.log")
await store.start()  # Perform crash recovery if needed

# Write operations
await store.set("user:1", json.dumps({"name": "Alice", "age": 30}))
await store.delete("user:2")

# Read operations
value = await store.get("user:1")
exists = await store.exists("user:1")

# Metadata
size = await store.size()
all_data = await store.get_all()
wal_size = await store.get_wal_size()
```

### TTL Example

```python
# Set a cache entry that expires in 5 minutes
await store.set("cache:session123", "session_data", ttl_seconds=300)

# Later: entry will be gone
await asyncio.sleep(301)
value = await store.get("cache:session123")  # Returns None
```

## Durability Guarantees

1. **All writes are persisted before returning**: fsync() is called on WAL append
2. **Crash recovery is automatic**: WAL is replayed on startup
3. **No data loss**: Every committed operation is in the log

### Trade-offs

**Pro**: Strong durability, crash recovery
**Con**: fsync() on every write has latency cost (~1ms per operation on typical disk)

For production, consider:
- Batching multiple writes and fsync'ing periodically
- Using async I/O where possible
- Tuning fsync frequency based on consistency vs. performance needs

## Testing

Tests cover:
- Basic operations (GET, SET, DELETE)
- TTL expiration and cleanup
- Concurrent operations (via asyncio locks)
- Edge cases (empty strings, None values, complex types)
- WAL persistence and recovery

Run tests:
```bash
pytest tests/test_storage.py -v
```

## Limitations (by design)

- **Single-node only**: No replication or consensus
- **In-memory only**: All data fits in memory (no paging to disk)
- **No transactions**: Single-key operations only
- **No secondary indexes**: Must iterate through all keys for searches

These limitations are addressed in later phases:
- Phase 2+: Clustering and replication
- Phase 4: Multi-entry commit via Raft
- Phase 7: Snapshotting for larger datasets

## Future Enhancements (Phase 7+)

1. **Log Compaction**: Snapshot + truncate WAL when it grows too large
2. **Persistent Snapshots**: RocksDB or LevelDB for on-disk storage
3. **Transactions**: Multi-key operations with ACID guarantees
4. **Indexes**: B-tree or hash indexes for faster lookups

---

*Phase 1 Complete: Days 1-2*
