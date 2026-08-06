# Local Cluster Setup - Localhost IDs & Ports

## 🚀 Quick Start

Run this command to start a 3-node cluster on your machine:

```powershell
cd "c:\Users\VEDANT\OneDrive\Desktop\DKVS\Distributed-key-value-store"
& "C:\Users\VEDANT\AppData\Local\Programs\Python\Python311\python.exe" run_local_cluster.py
```

---

## 📡 Localhost IDs & Ports

### RPC Layer (Internal Communication)

| Node | Node ID | Address | RPC Port | Purpose |
|------|---------|---------|----------|---------|
| A | `node-a` | `127.0.0.1` | `5000` | Leader Election / Log Replication |
| B | `node-b` | `127.0.0.1` | `5001` | Follower |
| C | `node-c` | `127.0.0.1` | `5002` | Follower |

**Usage**: Nodes communicate with each other via TCP on these ports for Raft consensus.

### HTTP API Layer (Client Access)

| Node | Address | Port | URL | Purpose |
|------|---------|------|-----|---------|
| A | `127.0.0.1` | `8000` | `http://127.0.0.1:8000` | KV Store API |
| B | `127.0.0.1` | `8001` | `http://127.0.0.1:8001` | KV Store API |
| C | `127.0.0.1` | `8002` | `http://127.0.0.1:8002` | KV Store API |

**Usage**: Clients connect to these ports to read/write data.

---

## 🧪 Test Endpoints

### Health Check
```bash
curl http://127.0.0.1:8000/health
```

**Response**:
```json
{
  "status": "healthy",
  "node_id": "node-a"
}
```

### Set a Key-Value
```bash
curl -X POST http://127.0.0.1:8000/set \
  -H "Content-Type: application/json" \
  -d '{"key": "hello", "value": "world"}'
```

**Response**:
```json
{
  "status": "success",
  "message": "Value set successfully"
}
```

### Get a Value
```bash
curl http://127.0.0.1:8000/get/hello
```

**Response**:
```json
{
  "value": "world"
}
```

### Get All Values
```bash
curl http://127.0.0.1:8000/get_all
```

**Response**:
```json
{
  "data": {
    "hello": "world",
    "key1": "value1"
  }
}
```

### Delete a Value
```bash
curl -X DELETE http://127.0.0.1:8000/delete/hello
```

**Response**:
```json
{
  "status": "success",
  "message": "Key deleted successfully"
}
```

---

## 🔗 Inter-Node Communication

### Node A → Node B

```
Node A (127.0.0.1:5000)
    ↓ (Raft RPC)
Node B (127.0.0.1:5001)
```

**Protocol**: TCP with length-prefixed JSON messages

**Message Types**:
- `RequestVote` - For leader election
- `AppendEntries` - For log replication (and heartbeats)

---

## 📊 Cluster Architecture

```
┌─────────────────────────────────────────┐
│         HTTP Clients                    │
│  (Read/Write to KV Store)               │
└─────────────────┬───────────────────────┘
                  │
        ┌─────────┼─────────┐
        │         │         │
   ┌────▼───┐ ┌──▼────┐ ┌──▼────┐
   │ Node A │ │ Node B │ │ Node C │
   │ :8000  │ │ :8001  │ │ :8002  │
   └────┬───┘ └───┬────┘ └───┬────┘
        │         │         │
        │   Raft  │ RPC     │
        │  (TCP)  │         │
        ├─────────┼─────────┤
        │:5000  :5001  :5002│
        │         │         │
        ▼────────(*)────────▼
     Election & Log Replication
```

---

## 🎯 Common Usage Scenarios

### Scenario 1: Write to Node A, Read from Node B

```bash
# Write to Node A
curl -X POST http://127.0.0.1:8000/set \
  -H "Content-Type: application/json" \
  -d '{"key": "test", "value": "data"}'

# Read from Node B (should see the value)
curl http://127.0.0.1:8001/get/test
```

### Scenario 2: Monitor Leader Election

1. Start the cluster
2. Check logs for "Became leader" message
3. Try writing to non-leader node - should forward to leader

### Scenario 3: Check Node Status

```bash
# Get info endpoint
curl http://127.0.0.1:8000/info
```

---

## 🛠️ Development Workflow

### 1. Start Cluster
```powershell
python run_local_cluster.py
```

### 2. In Another Terminal, Run Tests
```powershell
pytest tests/ -v
```

### 3. Test Endpoints with curl
```bash
curl http://127.0.0.1:8000/health
```

### 4. Stop Cluster
Press `Ctrl+C` in the cluster terminal

---

## 📝 WAL Files

Each node creates a WAL file on disk:
- `raft_node-a.wal` - Node A's write-ahead log
- `raft_node-b.wal` - Node B's write-ahead log
- `raft_node-c.wal` - Node C's write-ahead log

These files ensure durability - data survives node crashes!

---

## 🚨 Troubleshooting

### Port Already in Use
```
Error: Address already in use
```
**Fix**: Stop other services or change ports in `run_local_cluster.py`

### Python Not Found
```
Python was not found
```
**Fix**: Use full path: 
```powershell
& "C:\Users\VEDANT\AppData\Local\Programs\Python\Python311\python.exe" run_local_cluster.py
```

### Connection Refused
```
ConnectionRefusedError: [Errno 111]
```
**Fix**: Make sure cluster is running in another terminal

---

## 🎓 What You Can Test

1. **Basic KV Operations**
   - Set, Get, Delete
   - TTL expiration

2. **Consistency**
   - Write to one node
   - Read from another node
   - Verify data is replicated

3. **Cluster Behavior**
   - Watch leader election
   - Monitor heartbeats
   - Check node health

4. **Performance**
   - Concurrent writes
   - Latency measurements
   - Throughput benchmarks

---

## 📚 Additional Resources

- `README.md` - Project overview
- `ARCHITECTURE.md` - System design
- `docs/PHASE_2_BOOTSTRAP.md` - Bootstrap process
- `docs/PHASE_3_ELECTION.md` - Election algorithm
- `TEST_RESULTS.md` - Test coverage

---

## 🎯 Next Steps

After testing the cluster:
1. Check `TEST_RESULTS.md` for test coverage
2. Read `PHASE_3_ELECTION.md` for election details
3. Run tests to verify everything works
4. Experiment with failure scenarios

Enjoy! 🚀
