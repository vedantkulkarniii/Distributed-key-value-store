# Phase 3: Leader Election

**Timeline**: Days 5-7 (3 days)  
**Goal**: Implement Raft leader election with state transitions, timeouts, voting, and multi-node election

## Architecture Overview

The election system comprises 5 coordinated modules:

1. **RaftState** - State machine (Follower ↔ Candidate ↔ Leader)
2. **ElectionTimeout** - Randomized timeouts to prevent split votes
3. **RaftPersistentState** - Atomic persistence of term and vote
4. **RequestVoteProcessor** - Vote counting and election logic
5. **ElectionRunner** - Campaign orchestration

## Module: RaftState (src/raft/state.py)

### State Transitions

```
┌─────────────────────────────────────────┐
│                                         │
│                                    Wins election
│    Higher term                    with quorum ▼
└─ Follower ◄───────────────────────── Leader
    │                                    ▲ │
    │ Timeout                           │ │
    │ (increment term, vote for self)   │ │
    └──────────────────────► Candidate ─┘ │
                               ▲          │
                               │ Stale term detected
                               └──────────┘
```

### Key Properties

- **Follower**: Default state. Responds to RPCs from leader or candidate.
- **Candidate**: Seeking votes. Increments term, votes for self, broadcasts RequestVote.
- **Leader**: Won election. Sends heartbeats to maintain authority.

### State Machine Rules

The state machine enforces strict Raft invariants:

1. **Term Ordering**: Current term must be ≥ known term
2. **Vote Once Per Term**: Can only vote once per term (for any candidate)
3. **Vote for Self**: When becoming candidate, must vote for self
4. **Follower Demotion**: Higher term always demotes to follower
5. **State Validity**: Cannot transition Candidate → Candidate without becoming follower first

### NodeRole API

```python
# State transitions
await role.become_follower(term=5, leader_id="node-2")
await role.become_candidate()  # Increments term, votes for self
await role.become_leader()

# Voting
success = role.set_voted_for("candidate-id")  # Allowed once per term

# Term management
role.advance_term(10)  # Updates term, demotes to follower

# Queries
status = role.get_status()  # Returns {"node_id", "state", "term", "voted_for"}
```

## Module: ElectionTimeout (src/raft/timeout.py)

### Timeout Strategy

Split votes are prevented via randomized election timeouts:

- **Range**: 150ms - 300ms (default)
- **Randomization**: Uniformly random within range per election
- **Reset**: On heartbeat from leader or state change

### Timeout Profiles

| Profile | Min | Max | Use Case |
|---------|-----|-----|----------|
| Standard | 150ms | 300ms | Normal operation |
| Conservative | 300ms | 600ms | High-latency networks |
| Aggressive | 50ms | 100ms | Testing, low-latency |
| Test | 10ms | 20ms | Unit tests |

### Timeout Behavior

```python
timeout = ElectionTimeoutManager("node-1")
timeout.reset()  # Randomize timeout
remaining = timeout.remaining_time()  # Seconds until expiration
if timeout.is_expired():
    # Trigger election
```

### Correctness Properties

- **No Split Votes**: Different random timeouts prevent simultaneous candidates
- **Liveness**: Eventually some node times out and wins election
- **Fairness**: Higher-term candidates win (term-based tie-breaking)

## Module: RaftPersistentState (src/raft/persistence.py)

### Invariant: State Must Survive Crashes

The Raft paper requires:
- **currentTerm**: Persisted before any RPC response using that term
- **votedFor**: Persisted before voting in that term

This prevents:
- Node voting for multiple candidates in same term
- Node reverting to lower term after crash

### Persistence Implementation

```python
persistent_state = RaftPersistentState("node-1", state_file="raft_state.json")
await persistent_state.load()  # Load from disk on startup

await persistent_state.set_term(5)  # Atomic write with fsync
await persistent_state.set_voted_for("candidate-1")

term = await persistent_state.get_term()
voted_for = await persistent_state.get_voted_for()
```

### Atomic Write Guarantees

- **Write + fsync()**: Ensures data on disk
- **Atomic rename**: File not readable until fully written
- **Recovery**: File is always consistent

## Module: RequestVoteProcessor (src/raft/election.py)

### Vote Counting

The VoteCounter tracks election progress:

```python
counter = VoteCounter("node-1", total_nodes=5)
assert counter.quorum == 3  # Majority of 5

counter.record_vote("node-2")
counter.record_vote("node-3")
assert counter.has_quorum()  # 3 votes ≥ 3 quorum
```

### RequestVote Logic

The RequestVoteProcessor implements Raft voting rules:

1. **Term Check**: Reject if term < currentTerm
2. **Vote Already Cast**: Reject if voted for different candidate
3. **Log Check**: Reject if candidate log is less up-to-date

### Up-To-Date Check

A log is up-to-date if:
- Candidate's last term > receiver's last term, OR
- Terms equal AND candidate's last index ≥ receiver's last index

```python
# Candidate has term 5, index 20
# Receiver has term 4, index 25
is_uptodate = (5, 20) > (4, 25)  # True (term comparison wins)

# Candidate has term 4, index 20
# Receiver has term 4, index 25
is_uptodate = (4, 20) > (4, 25)  # False (index too low)
```

### ElectionRunner

Orchestrates the election campaign:

```python
runner = ElectionRunner("node-1", peers=["node-2", "node-3"])

# Send RequestVote to all peers, collect responses
votes = await runner.run_election(term=5, candidate_id="node-1")
if votes >= quorum:
    # Won election
```

## Module: RaftLog (src/raft/log.py)

### Phase 3 Implementation

Minimal in-memory log supporting election logic:

```python
log = RaftLog()
index = log.append(term=5, data=b"command")  # Returns index
last_index = log.get_last_index()
last_term = log.get_last_term()
```

### Phase 4 Extension

Full log will add:
- Persistent storage (log file)
- Batch appends
- Compaction
- Snapshots

## Integration: Multi-Node Election (Days 6-7)

### Election Flow

```
Node A (Follower)          Node B (Follower)          Node C (Follower)
│                          │                          │
│ Timeout expires          │                          │
│ ──────────────►          │                          │
│ Term++ (term=2)          │                          │
│ Vote for self            │                          │
│ Become candidate         │                          │
│                          │                          │
│ RequestVote(term=2)      │                          │
├─────────────────────────►│                          │
│                          │ Check: term 2 > 1 ✓      │
│                          │ Log up-to-date ✓        │
│                          │ Haven't voted ✓          │
│                          │ Save vote for A          │
│                          │ Send vote ack            │
│                          │                          │
│ RequestVote(term=2)      │                          │
└──────────────────────────────────────────────────► │
│                          │                          │ Check & vote
│                          │                          │ Send ack
│ Received 2/3 votes       │                          │
│ Become leader ◄──────────┴──────────────────────────┘
│ Start heartbeats         │                          │
```

### Testing Strategy (Days 6-7)

- **2-node cluster**: Basic leader election
- **3-node cluster**: Majority quorum voting
- **5-node cluster**: Realistic multi-node election
- **Stale candidate**: Higher-term candidate wins
- **Network delays**: Timeout handling and retries
- **Concurrent elections**: Multiple candidates, eventual winner

## Correctness Invariants

1. **Safety**: Only one leader per term
   - Implementation: Quorum voting prevents multiple candidates from winning same term

2. **Liveness**: Election eventually succeeds
   - Implementation: Randomized timeouts ensure not all nodes timeout simultaneously

3. **Transparency**: New leader has all committed entries
   - Implementation: Up-to-date checking prevents less-informed nodes from winning

4. **Durability**: Persistent state survives crashes
   - Implementation: Atomic fsync() writes before RPC responses

## Files

- `src/raft/state.py` (363L) - State machine and transitions
- `src/raft/timeout.py` (343L) - Election timeout management
- `src/raft/persistence.py` (308L) - Persistent term/vote
- `src/raft/election.py` (309L) - Vote counting and RequestVote logic
- `src/raft/log.py` (77L) - Minimal log for Phase 3
- `tests/test_raft_election.py` (312L+) - Comprehensive election tests

## Day 5 Deliverables

- ✅ RaftState state machine with correct transitions
- ✅ ElectionTimeout with randomization and profiles
- ✅ RaftPersistentState with atomic writes
- ✅ RequestVoteProcessor with up-to-date checking
- ✅ Single-node election tests (trivial case)
- ✅ RaftLog minimal implementation
- ✅ This design documentation
- TBD: State transitions module (refactor)

## Day 6-7 Deliverables

- Multi-node election tests (2, 3, 5-node clusters)
- Stale term handling and candidate rejection
- Concurrent election handling
- Network failure resilience
- Performance benchmarks
- Integration with bootstrap from Phase 2

## Next Phase: Phase 4 (Log Replication)

Once leader is elected, it must:
1. Replicate entries to followers via AppendEntries RPC
2. Commit entries when majority has replicated
3. Apply committed entries to state machine
4. Support log persistence and recovery
5. Handle follower failures and network partitions
