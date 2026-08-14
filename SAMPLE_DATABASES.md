# 📚 Sample Databases - Example Data

This document describes two example databases that can be loaded into the Distributed Key-Value Store for demonstration purposes.

---

## Database 1: User Profile Store

A production-like database for storing user profiles and related data.

### Sample Data

```json
{
  "user:1001": {
    "id": 1001,
    "name": "Alice Johnson",
    "email": "alice@example.com",
    "role": "admin",
    "status": "active",
    "created_at": "2026-01-15T10:30:00Z",
    "last_login": "2026-08-14T09:45:00Z"
  },
  "user:1002": {
    "id": 1002,
    "name": "Bob Smith",
    "email": "bob@example.com",
    "role": "user",
    "status": "active",
    "created_at": "2026-02-20T14:15:00Z",
    "last_login": "2026-08-13T16:20:00Z"
  },
  "user:1003": {
    "id": 1003,
    "name": "Carol Williams",
    "email": "carol@example.com",
    "role": "user",
    "status": "inactive",
    "created_at": "2026-03-10T11:00:00Z",
    "last_login": "2026-07-01T08:30:00Z"
  },
  "settings:theme": {
    "mode": "dark",
    "accent_color": "indigo",
    "language": "en"
  },
  "settings:notifications": {
    "email": true,
    "push": true,
    "sms": false
  }
}
```

### Key Statistics

| Metric | Value |
|--------|-------|
| Total Keys | 5 |
| Data Types | Object, String |
| Approximate Size | ~1.2 KB |
| Use Case | User management |

---

## Database 2: E-Commerce Store

A realistic e-commerce database with products, orders, and inventory.

### Sample Data

```json
{
  "product:SKU-001": {
    "sku": "SKU-001",
    "name": "Laptop Pro 15\"",
    "category": "Electronics",
    "price": 1299.99,
    "currency": "USD",
    "stock": 25,
    "rating": 4.8,
    "reviews": 342,
    "description": "High-performance laptop with 16GB RAM and 512GB SSD"
  },
  "product:SKU-002": {
    "sku": "SKU-002",
    "name": "Wireless Headphones",
    "category": "Audio",
    "price": 149.99,
    "currency": "USD",
    "stock": 87,
    "rating": 4.5,
    "reviews": 156,
    "description": "Noise-cancelling Bluetooth headphones with 30-hour battery"
  },
  "product:SKU-003": {
    "sku": "SKU-003",
    "name": "USB-C Hub",
    "category": "Accessories",
    "price": 49.99,
    "currency": "USD",
    "stock": 156,
    "rating": 4.3,
    "reviews": 89,
    "description": "7-in-1 USB-C hub with HDMI, USB 3.0, and SD card reader"
  },
  "order:ORD-2026-001": {
    "order_id": "ORD-2026-001",
    "customer_id": 1001,
    "items": [
      {"sku": "SKU-001", "quantity": 1, "price": 1299.99},
      {"sku": "SKU-003", "quantity": 2, "price": 49.99}
    ],
    "total": 1399.97,
    "status": "shipped",
    "created_at": "2026-08-10T10:15:00Z",
    "shipped_at": "2026-08-12T14:30:00Z"
  },
  "order:ORD-2026-002": {
    "order_id": "ORD-2026-002",
    "customer_id": 1002,
    "items": [
      {"sku": "SKU-002", "quantity": 1, "price": 149.99}
    ],
    "total": 149.99,
    "status": "pending",
    "created_at": "2026-08-14T08:00:00Z"
  },
  "inventory:summary": {
    "total_products": 3,
    "total_items": 268,
    "low_stock_threshold": 20,
    "low_stock_items": 0,
    "last_updated": "2026-08-14T09:00:00Z"
  }
}
```

### Key Statistics

| Metric | Value |
|--------|-------|
| Total Keys | 6 |
| Data Types | Object, Array, Number, String |
| Approximate Size | ~2.8 KB |
| Use Case | E-commerce |

---

## How to Load Sample Databases

### Option 1: Manually via Frontend

1. Go to the **Add Data** tab
2. For each key-value pair, enter:
   - **Key**: (from the sample data)
   - **Value**: (JSON content)
3. Click **Save to Database**

### Option 2: Using cURL (from command line)

**User Profile Store:**
```bash
curl -X POST http://localhost:8000/kv/user:1001 \
  -H "Content-Type: application/json" \
  -d '{"value": {"id": 1001, "name": "Alice Johnson", "email": "alice@example.com", "role": "admin", "status": "active", "created_at": "2026-01-15T10:30:00Z", "last_login": "2026-08-14T09:45:00Z"}}'

curl -X POST http://localhost:8000/kv/settings:theme \
  -H "Content-Type: application/json" \
  -d '{"value": {"mode": "dark", "accent_color": "indigo", "language": "en"}}'
```

**E-Commerce Store:**
```bash
curl -X POST http://localhost:8000/kv/product:SKU-001 \
  -H "Content-Type: application/json" \
  -d '{"value": {"sku": "SKU-001", "name": "Laptop Pro 15\"", "category": "Electronics", "price": 1299.99, "currency": "USD", "stock": 25, "rating": 4.8, "reviews": 342, "description": "High-performance laptop with 16GB RAM and 512GB SSD"}}'
```

### Option 3: Using Python Script

```python
import requests
import json

API_BASE = 'http://localhost:8000'

# Load User Profile Store
user_db = {
    "user:1001": {
        "id": 1001,
        "name": "Alice Johnson",
        "email": "alice@example.com",
        "role": "admin",
        "status": "active"
    },
    # ... more users
}

for key, value in user_db.items():
    response = requests.post(
        f"{API_BASE}/kv/{key}",
        headers={"Content-Type": "application/json"},
        json={"value": value}
    )
    print(f"Loaded {key}: {response.status_code}")
```

---

## Database Characteristics

### User Profile Store

**Purpose**: Demonstrate user and settings management

**Key Features**:
- Hierarchical naming (user:ID, settings:TYPE)
- Simple object structures
- Text-based keys
- Small-to-medium data size

**Use Cases**:
- User authentication systems
- Configuration management
- Profile storage
- Settings management

---

### E-Commerce Store

**Purpose**: Demonstrate complex transactional data

**Key Features**:
- Product catalog with pricing
- Order management with items
- Inventory tracking
- Complex nested structures
- Financial data

**Use Cases**:
- E-commerce platforms
- Inventory management
- Order processing
- Product catalogs

---

## Querying Sample Data

### View All Data
Dashboard Tab → Shows all stored data

### Search Examples

**User Profile Store:**
- Search: "alice" → Returns user:1001
- Search: "admin" → Returns user:1001
- Search: "theme" → Returns settings:theme

**E-Commerce Store:**
- Search: "laptop" → Returns product:SKU-001
- Search: "SKU-001" → Returns product:SKU-001
- Search: "ORD-2026" → Returns orders
- Search: "shipped" → Returns order:ORD-2026-001

---

## Extending Sample Data

### Add More Users

```json
{
  "user:1004": {
    "id": 1004,
    "name": "David Brown",
    "email": "david@example.com",
    "role": "moderator",
    "status": "active",
    "created_at": "2026-04-05T09:20:00Z"
  }
}
```

### Add More Products

```json
{
  "product:SKU-004": {
    "sku": "SKU-004",
    "name": "Mechanical Keyboard",
    "category": "Peripherals",
    "price": 129.99,
    "stock": 42,
    "rating": 4.7
  }
}
```

### Add More Orders

```json
{
  "order:ORD-2026-003": {
    "order_id": "ORD-2026-003",
    "customer_id": 1003,
    "items": [{"sku": "SKU-004", "quantity": 1, "price": 129.99}],
    "total": 129.99,
    "status": "processing"
  }
}
```

---

## Statistics for Sample Databases

### User Profile Store
- **Total Keys**: 5
- **Data Format**: JSON Objects
- **Typical Size**: ~1.2 KB
- **Access Pattern**: Frequent reads, occasional writes
- **Consistency**: Strong (transactional)

### E-Commerce Store
- **Total Keys**: 6
- **Data Format**: JSON Objects with nested arrays
- **Typical Size**: ~2.8 KB
- **Access Pattern**: Mixed (reads, writes, updates)
- **Consistency**: Strong (transactional)

---

## Performance Characteristics

Both sample databases are small enough to fit entirely in memory, making them ideal for:
- Learning and experimentation
- Performance testing
- Demonstration purposes
- Development and testing

For production systems with millions of records, the Distributed Key-Value Store's distributed architecture ensures:
- Horizontal scalability
- Fault tolerance
- High availability
- Consistent data replication

---

## Tips for Using Sample Data

1. **Start Small**: Load one database first, then add the other
2. **Practice Queries**: Search for different key patterns
3. **Modify Data**: Use the Add Data tab to modify values
4. **Delete Data**: Practice deleting specific keys
5. **Monitor Stats**: Watch the Statistics tab update
6. **Backup**: Note the data before making major changes

---

## Related Documentation

- **Frontend Guide**: `frontend/README.md`
- **API Documentation**: `http://localhost:8000/docs`
- **Architecture**: `ARCHITECTURE.md`
- **Getting Started**: `README.md`

---

*Sample databases created for August 14, 2026 demonstration*
