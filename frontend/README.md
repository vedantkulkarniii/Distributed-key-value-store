# 🎨 Frontend Dashboard for Distributed KV Store

A beautiful, interactive web dashboard to manage your Distributed Key-Value Store with Raft Consensus.

## 📸 What It Looks Like

```
┌─────────────────────────────────────────────────────────────┐
│         📦 Distributed Key-Value Store                      │
│    Real-time data management dashboard                      │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ 📊 Dashboard  |  ➕ Add Data  |  📈 Stats  |  ℹ️ About      │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ 📊 All Stored Data           🔄 Refresh   🔍 Search...    │
├─────────────────────────────────────────────────────────────┤
│ 🔑 user:1                                                   │
│ 📝 "Alice"                             [📋 Copy] [🗑️ Delete]│
│                                                             │
│ 🔑 settings:theme                                           │
│ 📝 "dark"                              [📋 Copy] [🗑️ Delete]│
│                                                             │
│ 🔑 product:123                                              │
│ 📝 {"name":"Laptop","price":999}       [📋 Copy] [🗑️ Delete]│
└─────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites
- Your backend running on `http://localhost:8000`
- A modern web browser (Chrome, Firefox, Safari, Edge)

### Method 1: Open HTML File Directly (Easiest)
```bash
# On Windows
start frontend\index.html

# On Mac
open frontend/index.html

# On Linux
xdg-open frontend/index.html
```

### Method 2: Use Python's Built-in Server
```bash
cd frontend
python -m http.server 8001
```
Then visit: `http://localhost:8001`

### Method 3: Use Node.js (if installed)
```bash
cd frontend
npx serve
```

## 📚 Loading Sample Data

The project includes sample databases for demonstration purposes. You can load example data into your store to test the dashboard.

### Option 1: Load Sample Data Using Python Script (Recommended)

```bash
# Load both sample databases (User Profile + E-Commerce)
python load_sample_databases.py

# Load only User Profile database
python load_sample_databases.py --database user

# Load only E-Commerce database
python load_sample_databases.py --database ecommerce

# Load with custom API URL
python load_sample_databases.py --api-url http://localhost:8000

# Verify data was loaded
python load_sample_databases.py --verify-only
```

### Option 2: Load Individual Keys via cURL

**User Profile Store:**
```bash
curl -X POST http://localhost:8000/kv/user:1001 \
  -H "Content-Type: application/json" \
  -d '{"value": {"id": 1001, "name": "Alice Johnson", "email": "alice@example.com", "role": "admin", "status": "active"}}'
```

**E-Commerce Store:**
```bash
curl -X POST http://localhost:8000/kv/product:SKU-001 \
  -H "Content-Type: application/json" \
  -d '{"value": {"sku": "SKU-001", "name": "Laptop Pro 15\"", "category": "Electronics", "price": 1299.99, "stock": 25}}'
```

### Option 3: Manually Add Data via Dashboard

1. Open the dashboard (index.html)
2. Go to the **Add Data** tab
3. Enter a key and value
4. Click **Save to Database**

### Sample Databases Overview

**Database 1: User Profile Store**
- Contains user profiles, settings, and notifications
- 5 keys total
- Use case: User management systems

**Database 2: E-Commerce Store**
- Contains products, orders, and inventory
- 6 keys total
- Use case: E-commerce platforms

For detailed documentation, see [`SAMPLE_DATABASES.md`](../SAMPLE_DATABASES.md)

## 📋 Features

### ✨ Dashboard Tab
- **View all stored data** in real-time
- **Search functionality** (searches both keys and values)
- **Refresh button** to fetch latest data
- **Copy button** to copy keys to clipboard
- **Delete button** to remove keys

### ➕ Add Data Tab
- **Add new key-value pairs**
- **Supports multiple data types**:
  - Strings: `"Alice"`
  - Numbers: `42` or `3.14`
  - JSON objects: `{"name": "Alice", "age": 30}`
  - JSON arrays: `[1, 2, 3]`
  - Booleans: `true` or `false`
- **Optional TTL (Time-To-Live)** for automatic expiration

### 📈 Statistics Tab
- **Total keys count**
- **Storage size used**
- **API health status**
- **Response time measurement**
- **Top keys listing**
- **Data types distribution**

### ℹ️ About Tab
- **Project description**
- **Key features explained**
- **Architecture diagram**
- **Use cases**
- **Project statistics**
- **Links to API docs**

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+R` (Windows/Linux) or `Cmd+R` (Mac) | Refresh data |
| `Ctrl+K` or `Cmd+K` | Focus search box |
| `Escape` | Clear search |

## 🎨 UI Features

### Responsive Design
- ✅ Works on desktop, tablet, and mobile
- ✅ Auto-adjusting layout
- ✅ Touch-friendly buttons

### Beautiful Animations
- ✅ Smooth page transitions
- ✅ Hover effects on buttons and cards
- ✅ Slide-in animations

### Real-time Updates
- ✅ Auto-refresh statistics every 5 seconds
- ✅ Instant feedback on actions
- ✅ Status messages

### Dark Gradient Theme
- ✅ Modern purple gradient design
- ✅ Professional appearance
- ✅ Easy on the eyes

## 📝 Data Types Supported

### Strings
```
Input: "Alice"
Stored as: "Alice"
```

### Numbers
```
Input: 42
Stored as: 42
```

### JSON Objects
```
Input: {"name": "Alice", "age": 30}
Stored as: {name: "Alice", age: 30}
```

### JSON Arrays
```
Input: [1, 2, 3, 4, 5]
Stored as: [1, 2, 3, 4, 5]
```

### Complex Nested Data
```
Input: {"user": {"name": "Alice", "tags": ["admin", "user"]}}
Stored as: {user: {name: "Alice", tags: ["admin", "user"]}}
```

## 🔧 How It Works

### Frontend-Backend Communication

```
┌─────────────────────────────┐
│   FRONTEND (This Dashboard) │
│   (HTML, CSS, JavaScript)   │
└──────────────┬──────────────┘
               │
        HTTP/REST API Calls
               │
               ▼
┌──────────────────────────────┐
│  BACKEND (Your KV Store)    │
│  (Raft Consensus API)        │
│  http://localhost:8000       │
└──────────────────────────────┘
```

### API Endpoints Used

| Operation | Method | URL | Purpose |
|-----------|--------|-----|---------|
| Get all data | GET | `/kv` | Fetch all key-value pairs |
| Get specific | GET | `/kv/{key}` | Fetch one value |
| Create/Update | POST | `/kv/{key}` | Save a key-value pair |
| Delete | DELETE | `/kv/{key}` | Remove a key |
| Health check | GET | `/health` | Check API status |
| Info | GET | `/info` | Get store metadata |

## 🐛 Troubleshooting

### Dashboard shows "API is offline"
**Problem**: Backend not running or wrong URL
**Solution**: 
```bash
# Start your backend
cd your-project
python -m uvicorn src.api.server:app --host 0.0.0.0 --port 8000
```

### Search not working
**Problem**: Browser cache issue
**Solution**: Clear cache or refresh the page (Ctrl+Shift+Delete)

### CORS errors in browser console
**Problem**: Frontend and backend on different origins
**Solution**: Your backend already has CORS enabled, just make sure it's running

### Changes not appearing
**Problem**: Data not saved or need refresh
**Solution**: Click the 🔄 Refresh button

## 🎓 File Structure

```
frontend/
├── index.html          # Main HTML structure
├── style.css           # All styling and responsive design
├── app.js              # All JavaScript functionality
└── README.md           # This file
```

## 💡 Tips & Tricks

### Namespacing Keys
Use colons for organization:
```
user:1              → Alice's data
user:2              → Bob's data
settings:theme      → Theme preference
settings:language   → Language preference
product:123         → Product 123 details
```

### Bulk Operations
Add multiple related keys:
```
user:10 -> {"name": "User 10"}
user:11 -> {"name": "User 11"}
user:12 -> {"name": "User 12"}
```

### Complex Data Storage
Store entire objects:
```
key: app:config
value: {"theme":"dark","language":"en","notifications":true}
```

## 🚀 Extending the Dashboard

### Add Login Page
```javascript
// Check authentication on load
if (!isLoggedIn()) {
    showLoginPage();
}
```

### Add Real-time Updates
```javascript
// Connect WebSocket for live updates
const ws = new WebSocket('ws://localhost:8000/ws');
ws.onmessage = () => loadAllData();
```

### Add Charts
```javascript
// Use Chart.js for visualizations
import Chart from 'chart.js';
// Create graphs of your data
```

### Add Export
```javascript
// Export data as JSON
function exportData() {
    const json = JSON.stringify(allData, null, 2);
    downloadFile(json, 'data.json');
}
```

## 🔐 Security Notes

### Current State
- ✅ No authentication required (local/trusted network)
- ✅ CORS enabled for development

### For Production
- ⚠️ Add authentication/authorization
- ⚠️ Use HTTPS instead of HTTP
- ⚠️ Implement rate limiting
- ⚠️ Add input validation
- ⚠️ Use environment variables for API URL

## 📚 Learn More

- [Backend API Documentation](http://localhost:8000/docs)
- [Project README](../README.md)
- [Architecture Guide](../ARCHITECTURE.md)
- [Frontend Guide](../FRONTEND_EXTENSION_GUIDE.md)

## 🎉 You Now Have

✅ **Full-Stack Application**
- Frontend: Beautiful dashboard
- Backend: Production-grade database
- Communication: REST API

✅ **Features**
- Real-time data management
- Beautiful UI
- Responsive design
- Statistics and monitoring
- Search and filtering

✅ **Ready to Show**
- Non-technical people can use it
- Professional appearance
- Works on all devices

## 🚀 Next Steps

1. ✅ Run the frontend
2. ✅ Add data through the dashboard
3. ✅ Verify it syncs across cluster
4. ✅ Customize the styling
5. ✅ Add more features
6. ✅ Deploy to production

## 📞 Support

For issues:
1. Check browser console (F12)
2. Verify backend is running
3. Check API URL is correct
4. Clear browser cache

---

**Enjoy your new dashboard! 🎨🚀**
