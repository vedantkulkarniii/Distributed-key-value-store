# 📚 Complete API Guide - Distributed Key-Value Store

**Date**: August 15, 2026  
**Version**: 1.0  
**Status**: ✅ Complete API Documentation

---

## 🎯 API Overview

The Distributed Key-Value Store provides a REST API for all operations. The API is built with FastAPI and includes automatic documentation.

**Base URL**: `http://localhost:8000`  
**API Docs**: `http://localhost:8000/docs` (Interactive Swagger UI)  
**API Schema**: `http://localhost:8000/openapi.json` (OpenAPI 3.0)

---

## 📋 Quick Reference

| Operation | Method | Endpoint | Purpose |
|-----------|--------|----------|---------|
| **Get All** | GET | `/kv` | Fetch all key-value pairs |
| **Get One** | GET | `/kv/{key}` | Fetch a specific value |
| **Create/Update** | POST | `/kv/{key}` | Save a key-value pair |
| **Delete** | DELETE | `/kv/{key}` | Remove a key |
| **Delete All** | DELETE | `/kv` | Clear all data |
| **Health Check** | GET | `/health` | Check API status |
| **Store Info** | GET | `/info` | Get store metadata |

---

## 🔍 Detailed Endpoints

### 1. Get All Data

**Endpoint**: `GET /kv`

**Description**: Retrieve all stored key-value pairs

**Response**: 
```bash
curl -X GET http://localhost:8000/kv
```

**Success Response (200 OK)**:
```json
{
  "data": {
    "user:1": {
      "id": 1,
      "name": "Alice",
      "email": "alice@example.com"
    },
    "user:2": {
      "id": 2,
      "name": "Bob",
      "email": "bob@example.com"
    },
    "settings:theme": "dark"
  },
  "count": 3
}
```

**Query Parameters**:
- None

**Use Cases**:
- Dashboard display
- Data export
- Backup/synchronization
- Analytics

---

### 2. Get Specific Key

**Endpoint**: `GET /kv/{key}`

**Description**: Retrieve value for a specific key

**Parameters**:
- `key` (path parameter, required): The key name

**Example**:
```bash
curl -X GET http://localhost:8000/kv/user:1
```

**Success Response (200 OK)**:
```json
{
  "key": "user:1",
  "value": {
    "id": 1,
    "name": "Alice",
    "email": "alice@example.com"
  },
  "exists": true
}
```

**Error Response (404 Not Found)**:
```json
{
  "error": "Not Found",
  "detail": "Key 'nonexistent' not found"
}
```

**Use Cases**:
- Single record retrieval
- User profile lookup
- Configuration fetch
- Cache checking

---

### 3. Create or Update Data

**Endpoint**: `POST /kv/{key}`

**Description**: Create a new key or update existing one

**Parameters**:
- `key` (path parameter, required): The key name
- `value` (body parameter, required): The value to store

**Request Body**:
```json
{
  "value": "any JSON-serializable value"
}
```

**Examples**:

**String value**:
```bash
curl -X POST http://localhost:8000/kv/greeting \
  -H "Content-Type: application/json" \
  -d '{"value": "Hello World"}'
```

**Number value**:
```bash
curl -X POST http://localhost:8000/kv/count \
  -H "Content-Type: application/json" \
  -d '{"value": 42}'
```

**JSON Object**:
```bash
curl -X POST http://localhost:8000/kv/user:1 \
  -H "Content-Type: application/json" \
  -d '{
    "value": {
      "id": 1,
      "name": "Alice",
      "email": "alice@example.com",
      "age": 30
    }
  }'
```

**JSON Array**:
```bash
curl -X POST http://localhost:8000/kv/tags \
  -H "Content-Type: application/json" \
  -d '{"value": ["python", "distributed-systems", "raft"]}'
```

**Complex Nested Structure**:
```bash
curl -X POST http://localhost:8000/kv/order:001 \
  -H "Content-Type: application/json" \
  -d '{
    "value": {
      "order_id": "001",
      "customer": {
        "id": 1,
        "name": "Alice",
        "email": "alice@example.com"
      },
      "items": [
        {"sku": "PROD-001", "name": "Laptop", "price": 999.99, "qty": 1},
        {"sku": "PROD-002", "name": "Mouse", "price": 29.99, "qty": 2}
      ],
      "total": 1059.97,
      "status": "shipped",
      "created_at": "2026-08-15T10:00:00Z"
    }
  }'
```

**Success Response (201 Created)**:
```json
{
  "status": "success",
  "key": "user:1",
  "message": "Value set successfully"
}
```

**Error Responses**:

**Invalid JSON (422 Unprocessable Entity)**:
```json
{
  "error": "Validation Error",
  "detail": "Invalid request body"
}
```

**Empty Key (400 Bad Request)**:
```json
{
  "error": "Bad Request",
  "detail": "Key cannot be empty"
}
```

**Use Cases**:
- Create new records
- Update existing values
- Store configuration
- Add to cache

---

### 4. Delete a Key

**Endpoint**: `DELETE /kv/{key}`

**Description**: Remove a key from the store

**Parameters**:
- `key` (path parameter, required): The key to delete

**Example**:
```bash
curl -X DELETE http://localhost:8000/kv/user:1
```

**Success Response (200 OK)**:
```json
{
  "status": "success",
  "key": "user:1",
  "message": "Key 'user:1' deleted successfully"
}
```

**Error Response (404 Not Found)**:
```json
{
  "error": "Not Found",
  "detail": "Key 'nonexistent' not found"
}
```

**Use Cases**:
- Remove user records
- Delete expired sessions
- Cleanup cache
- Data removal

---

### 5. Delete All Data

**Endpoint**: `DELETE /kv`

**Description**: Clear entire store (WARNING: irreversible)

**Example**:
```bash
curl -X DELETE http://localhost:8000/kv
```

**Success Response (200 OK)**:
```json
{
  "status": "success",
  "message": "Store cleared successfully"
}
```

**Use Cases**:
- Development/testing cleanup
- Start fresh
- Reset system

**⚠️ Warning**: This operation deletes ALL data permanently!

---

### 6. Health Check

**Endpoint**: `GET /health`

**Description**: Check if API is running

**Example**:
```bash
curl -X GET http://localhost:8000/health
```

**Success Response (200 OK)**:
```json
{
  "status": "healthy",
  "service": "kv-store-api"
}
```

**Use Cases**:
- Monitoring
- Load balancer health checks
- Service discovery
- Availability verification

---

### 7. Store Information

**Endpoint**: `GET /info`

**Description**: Get metadata about the store

**Example**:
```bash
curl -X GET http://localhost:8000/info
```

**Success Response (200 OK)**:
```json
{
  "size": 5,
  "wal_size_bytes": 2048,
  "was_recovered": false
}
```

**Fields**:
- `size`: Number of keys in store
- `wal_size_bytes`: Write-ahead log size in bytes
- `was_recovered`: Whether recovered from crash

**Use Cases**:
- Monitoring store size
- Storage usage tracking
- Recovery status checking
- Statistics gathering

---

## 💡 Common Patterns

### Pattern 1: Namespacing Keys

Use colons to organize data:

```bash
# User data
curl -X POST http://localhost:8000/kv/user:1 -H "Content-Type: application/json" -d '{"value": {"name": "Alice"}}'
curl -X POST http://localhost:8000/kv/user:2 -H "Content-Type: application/json" -d '{"value": {"name": "Bob"}}'

# Settings
curl -X POST http://localhost:8000/kv/settings:theme -H "Content-Type: application/json" -d '{"value": "dark"}'
curl -X POST http://localhost:8000/kv/settings:language -H "Content-Type: application/json" -d '{"value": "en"}'

# Products
curl -X POST http://localhost:8000/kv/product:SKU-001 -H "Content-Type: application/json" -d '{"value": {"name": "Laptop", "price": 999.99}}'
```

---

### Pattern 2: Hierarchical Data

Store complex relationships:

```bash
curl -X POST http://localhost:8000/kv/company:acme:departments:sales \
  -H "Content-Type: application/json" \
  -d '{
    "value": {
      "name": "Sales",
      "manager": "John Doe",
      "employees": 15,
      "budget": 500000
    }
  }'
```

---

### Pattern 3: Bulk Operations

Create multiple records:

```bash
# Script to load multiple items
for i in {1..10}; do
  curl -X POST http://localhost:8000/kv/record:$i \
    -H "Content-Type: application/json" \
    -d "{\"value\": {\"id\": $i, \"name\": \"Record $i\"}}"
done
```

---

### Pattern 4: Conditional Updates

Check before updating:

```bash
# Get current value
curl -X GET http://localhost:8000/kv/counter

# Update if needed
curl -X POST http://localhost:8000/kv/counter \
  -H "Content-Type: application/json" \
  -d '{"value": 42}'
```

---

## 🔧 Programming Examples

### Python Example

```python
import requests
import json

API_BASE = 'http://localhost:8000'

# Get all data
response = requests.get(f"{API_BASE}/kv")
all_data = response.json()
print(f"Total keys: {all_data['count']}")

# Get specific key
response = requests.get(f"{API_BASE}/kv/user:1")
user = response.json()
print(f"User: {user['value']}")

# Create/Update
response = requests.post(
    f"{API_BASE}/kv/user:1",
    headers={"Content-Type": "application/json"},
    json={"value": {"name": "Alice", "age": 30}}
)
print(f"Status: {response.status_code}")

# Delete
response = requests.delete(f"{API_BASE}/kv/user:1")
print(f"Deleted: {response.status_code}")

# Health check
response = requests.get(f"{API_BASE}/health")
print(f"API Status: {response.json()['status']}")
```

### JavaScript Example

```javascript
const API_BASE = 'http://localhost:8000';

// Get all data
async function getAllData() {
    const response = await fetch(`${API_BASE}/kv`);
    const data = await response.json();
    console.log(`Total keys: ${data.count}`);
    return data.data;
}

// Get specific key
async function getKey(key) {
    const response = await fetch(`${API_BASE}/kv/${key}`);
    const data = await response.json();
    return data.value;
}

// Create/Update
async function setKey(key, value) {
    const response = await fetch(`${API_BASE}/kv/${key}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({value})
    });
    return response.status === 201;
}

// Delete
async function deleteKey(key) {
    const response = await fetch(`${API_BASE}/kv/${key}`, {
        method: 'DELETE'
    });
    return response.ok;
}

// Health check
async function checkHealth() {
    const response = await fetch(`${API_BASE}/health`);
    const data = await response.json();
    return data.status === 'healthy';
}

// Usage
getAllData().then(data => console.log(data));
getKey('user:1').then(user => console.log(user));
setKey('user:1', {name: 'Alice', age: 30}).then(ok => console.log(ok));
```

### cURL Examples (Bash)

```bash
#!/bin/bash

API_BASE="http://localhost:8000"

# Get all
curl -X GET "$API_BASE/kv"

# Get one
curl -X GET "$API_BASE/kv/user:1"

# Create/Update multiple
curl -X POST "$API_BASE/kv/user:1" \
  -H "Content-Type: application/json" \
  -d '{"value": {"name": "Alice"}}'

curl -X POST "$API_BASE/kv/user:2" \
  -H "Content-Type: application/json" \
  -d '{"value": {"name": "Bob"}}'

# Delete
curl -X DELETE "$API_BASE/kv/user:1"

# Health
curl -X GET "$API_BASE/health"

# Info
curl -X GET "$API_BASE/info"
```

---

## ⚠️ Error Handling

### Common HTTP Status Codes

| Status | Meaning | Example |
|--------|---------|---------|
| **200 OK** | Request succeeded | GET, DELETE successful |
| **201 Created** | Resource created | POST successful |
| **400 Bad Request** | Invalid request | Empty key, malformed body |
| **404 Not Found** | Key doesn't exist | GET/DELETE nonexistent key |
| **422 Unprocessable** | Invalid JSON | Malformed JSON body |
| **500 Server Error** | Server error | Unexpected server issue |

### Error Response Format

All errors follow this format:

```json
{
  "error": "Error Type",
  "detail": "Detailed error message"
}
```

### Examples

**Empty Key**:
```bash
curl -X GET http://localhost:8000/kv/
```
Response:
```json
{
  "error": "Not Found",
  "detail": "Not Found"
}
```

**Invalid JSON**:
```bash
curl -X POST http://localhost:8000/kv/test \
  -H "Content-Type: application/json" \
  -d 'not valid json'
```
Response:
```json
{
  "error": "Unprocessable Entity",
  "detail": "Invalid JSON"
}
```

---

## 🔐 Security Notes

### Current State
- ✅ No authentication required (intended for local/trusted networks)
- ✅ CORS enabled for local development
- ✅ Input validation implemented

### For Production

Consider adding:
- ✅ API key authentication
- ✅ JWT token support
- ✅ Rate limiting
- ✅ HTTPS/TLS
- ✅ Access control lists (ACLs)
- ✅ Audit logging

---

## 📊 Rate Limiting (Future)

Currently unlimited. Future versions may include:
- Per-IP rate limiting
- Per-key request throttling
- Adaptive backoff

---

## 🚀 Best Practices

1. **Key Naming**
   - Use lowercase with hyphens/colons
   - Use namespaces for organization
   - Keep keys descriptive but concise

2. **Value Storage**
   - Store atomic units (don't split related data)
   - Use JSON objects for complex data
   - Keep values reasonably sized

3. **API Usage**
   - Check `/health` before operations
   - Use appropriate HTTP methods
   - Handle errors gracefully
   - Cache responses when possible

4. **Error Handling**
   - Check HTTP status codes
   - Parse error responses
   - Implement retry logic for failures
   - Log errors for debugging

5. **Performance**
   - Use GET /kv/{key} for single items
   - Use GET /kv for bulk when needed
   - Batch operations when possible
   - Monitor response times

---

## 📖 Additional Resources

- **Interactive Docs**: http://localhost:8000/docs
- **GitHub Repository**: https://github.com/vedantkulkarniii/Distributed-key-value-store
- **Architecture Guide**: ARCHITECTURE.md
- **Sample Data Guide**: SAMPLE_DATABASES.md
- **Frontend Guide**: frontend/README.md

---

## ✅ Testing Your API

### Using the Interactive Docs

1. Go to `http://localhost:8000/docs`
2. Click "Try it out" on any endpoint
3. Enter parameters
4. Click "Execute"
5. See live responses

### Using Postman

1. Import from: `http://localhost:8000/openapi.json`
2. Create requests
3. Set headers and body
4. Send and analyze responses

### Using curl

```bash
# Test all endpoints
curl http://localhost:8000/health
curl http://localhost:8000/info
curl http://localhost:8000/kv
curl -X POST http://localhost:8000/kv/test -H "Content-Type: application/json" -d '{"value": "test"}'
curl http://localhost:8000/kv/test
curl -X DELETE http://localhost:8000/kv/test
```

---

**Version**: 1.0  
**Last Updated**: August 15, 2026  
**Status**: ✅ Complete

