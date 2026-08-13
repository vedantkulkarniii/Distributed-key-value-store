// ============================================
// DISTRIBUTED KV STORE DASHBOARD
// Frontend JavaScript Application
// ============================================

// API Configuration
const API_BASE = 'http://localhost:8000';

// DOM Elements
const navBtns = document.querySelectorAll('.nav-btn');
const tabContents = document.querySelectorAll('.tab-content');
const addForm = document.getElementById('addForm');
const keyInput = document.getElementById('keyInput');
const valueInput = document.getElementById('valueInput');
const ttlInput = document.getElementById('ttlInput');
const dataDisplay = document.getElementById('dataDisplay');
const refreshBtn = document.getElementById('refreshBtn');
const searchInput = document.getElementById('searchInput');
const statusMessage = document.getElementById('statusMessage');

// State
let allData = {};

// ============================================
// EVENT LISTENERS
// ============================================

// Tab Navigation
navBtns.forEach(btn => {
    btn.addEventListener('click', () => handleTabSwitch(btn));
});

// Form Submission
addForm.addEventListener('submit', handleAddKey);

// Data Management
refreshBtn.addEventListener('click', loadAllData);
searchInput.addEventListener('input', handleSearch);

// Load data on page load
document.addEventListener('DOMContentLoaded', () => {
    loadAllData();
    loadStatistics();
});

// Refresh statistics every 5 seconds
setInterval(loadStatistics, 5000);

// ============================================
// TAB NAVIGATION
// ============================================

function handleTabSwitch(btn) {
    // Remove active class from all buttons and tabs
    navBtns.forEach(b => b.classList.remove('active'));
    tabContents.forEach(tab => tab.classList.remove('active'));

    // Add active class to clicked button
    btn.classList.add('active');

    // Show corresponding tab
    const tabName = btn.dataset.tab;
    const tabElement = document.getElementById(`${tabName}-tab`);
    if (tabElement) {
        tabElement.classList.add('active');

        // Load data for specific tabs
        if (tabName === 'stats') {
            loadStatistics();
        }
    }
}

// ============================================
// MAIN FUNCTIONS
// ============================================

/**
 * Add or update a key in the database
 */
async function handleAddKey(e) {
    e.preventDefault();

    const key = keyInput.value.trim();
    const value = valueInput.value.trim();

    if (!key || !value) {
        showStatus('❌ Key and value cannot be empty', 'error');
        return;
    }

    // Try to parse value as JSON if it looks like JSON
    let parsedValue = value;
    if ((value.startsWith('{') || value.startsWith('[')) && value.endsWith(']') || value.endsWith('}')) {
        try {
            parsedValue = JSON.parse(value);
        } catch (e) {
            // Keep as string if not valid JSON
        }
    }

    try {
        showStatus('⏳ Saving to database...', '');

        const response = await fetch(`${API_BASE}/kv/${key}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ value: parsedValue })
        });

        if (!response.ok) {
            throw new Error(`Failed to save: ${response.statusText}`);
        }

        showStatus('✅ Data saved successfully!', 'success');
        keyInput.value = '';
        valueInput.value = '';
        ttlInput.value = '';

        // Refresh data display
        await loadAllData();

    } catch (error) {
        showStatus(`❌ Error: ${error.message}`, 'error');
        console.error('Error:', error);
    }
}

/**
 * Load all data from the database
 */
async function loadAllData() {
    try {
        showStatus('⏳ Loading data...', '');

        const startTime = performance.now();
        const response = await fetch(`${API_BASE}/kv`);
        const endTime = performance.now();

        if (!response.ok) {
            throw new Error(`Failed to fetch: ${response.statusText}`);
        }

        const result = await response.json();
        allData = result.data || {};

        // Display data
        displayData(allData);

        const responseTime = (endTime - startTime).toFixed(0);
        showStatus(`✅ Loaded ${Object.keys(allData).length} items from database (${responseTime}ms)`, 'success');

    } catch (error) {
        dataDisplay.innerHTML = `<div class="empty-state">❌ Error loading data: ${error.message}</div>`;
        showStatus(`❌ Error: ${error.message}`, 'error');
        console.error('Error:', error);
    }
}

/**
 * Display data in the dashboard
 */
function displayData(dataToDisplay) {
    if (Object.keys(dataToDisplay).length === 0) {
        dataDisplay.innerHTML = '<div class="empty-state">📭 No data stored yet. Add something!</div>';
        dataDisplay.classList.add('empty');
        return;
    }

    dataDisplay.classList.remove('empty');
    let html = '';

    for (const [key, value] of Object.entries(dataToDisplay)) {
        const valueStr = JSON.stringify(value);
        const truncatedValue = valueStr.length > 100 ? valueStr.substring(0, 100) + '...' : valueStr;

        html += `
            <div class="data-item">
                <div class="data-item-content">
                    <div class="data-item-key">🔑 ${escapeHtml(key)}</div>
                    <div class="data-item-value" title="${escapeHtml(valueStr)}">
                        📝 ${escapeHtml(truncatedValue)}
                    </div>
                </div>
                <div class="data-item-actions">
                    <button class="btn btn-primary" onclick="handleCopyKey('${escapeHtml(key)}')">
                        📋 Copy
                    </button>
                    <button class="btn btn-danger delete-btn" onclick="handleDeleteKey('${escapeHtml(key)}')">
                        🗑️ Delete
                    </button>
                </div>
            </div>
        `;
    }

    dataDisplay.innerHTML = html;
}

/**
 * Search/filter data
 */
function handleSearch() {
    const searchTerm = searchInput.value.toLowerCase();

    if (!searchTerm) {
        displayData(allData);
        return;
    }

    const filtered = {};
    for (const [key, value] of Object.entries(allData)) {
        if (key.toLowerCase().includes(searchTerm) || JSON.stringify(value).toLowerCase().includes(searchTerm)) {
            filtered[key] = value;
        }
    }

    displayData(filtered);
    showStatus(`🔍 Found ${Object.keys(filtered).length} matching items`, 'success');
}

/**
 * Delete a key from the database
 */
async function handleDeleteKey(key) {
    if (!confirm(`🗑️ Are you sure you want to delete "${key}"? This cannot be undone.`)) {
        return;
    }

    try {
        showStatus('⏳ Deleting...', '');

        const response = await fetch(`${API_BASE}/kv/${key}`, {
            method: 'DELETE'
        });

        if (!response.ok && response.status !== 404) {
            throw new Error(`Failed to delete: ${response.statusText}`);
        }

        showStatus(`✅ Key "${key}" deleted successfully!`, 'success');
        await loadAllData();

    } catch (error) {
        showStatus(`❌ Error: ${error.message}`, 'error');
        console.error('Error:', error);
    }
}

/**
 * Copy key to clipboard
 */
async function handleCopyKey(key) {
    try {
        await navigator.clipboard.writeText(key);
        showStatus(`📋 Key "${key}" copied to clipboard!`, 'success');
    } catch (error) {
        showStatus(`❌ Failed to copy: ${error.message}`, 'error');
    }
}

/**
 * Load statistics
 */
async function loadStatistics() {
    try {
        // Get total keys
        const totalKeys = Object.keys(allData).length;
        document.getElementById('totalKeys').textContent = totalKeys;

        // Calculate storage size
        const storageSize = JSON.stringify(allData).length;
        document.getElementById('storageSize').textContent = formatBytes(storageSize);

        // Check API health
        const healthResponse = await fetch(`${API_BASE}/health`);
        const apiStatus = healthResponse.ok ? '✅ Online' : '⚠️ Issues';
        document.getElementById('apiStatus').textContent = apiStatus;

        // Measure response time
        const startTime = performance.now();
        await fetch(`${API_BASE}/info`);
        const endTime = performance.now();
        const responseTime = (endTime - startTime).toFixed(0);
        document.getElementById('responseTime').textContent = `${responseTime} ms`;

        // Top keys by name
        const topKeys = Object.keys(allData).slice(0, 5);
        const topKeysHtml = topKeys.length > 0
            ? topKeys.map(k => `<p>🔑 ${escapeHtml(k)}</p>`).join('')
            : '<p class="empty">No data yet</p>';
        document.getElementById('topKeys').innerHTML = topKeysHtml;

        // Data types distribution
        const typeMap = {};
        for (const value of Object.values(allData)) {
            const type = typeof value === 'object' ? Array.isArray(value) ? 'Array' : 'Object' : typeof value;
            typeMap[type] = (typeMap[type] || 0) + 1;
        }
        const typesHtml = Object.entries(typeMap).length > 0
            ? Object.entries(typeMap).map(([t, c]) => `<p>📊 ${t}: ${c} item(s)</p>`).join('')
            : '<p class="empty">No data yet</p>';
        document.getElementById('dataTypes').innerHTML = typesHtml;

    } catch (error) {
        console.error('Error loading statistics:', error);
    }
}

// ============================================
// UTILITY FUNCTIONS
// ============================================

/**
 * Show status message
 */
function showStatus(message, type) {
    statusMessage.textContent = message;
    statusMessage.className = `status-message ${type}`;

    // Auto-hide success messages after 5 seconds
    if (type === 'success') {
        setTimeout(() => {
            statusMessage.textContent = '✅ Ready to go!';
            statusMessage.className = 'status-message success';
        }, 5000);
    }
}

/**
 * Escape HTML entities to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Format bytes to human-readable size
 */
function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
}

// ============================================
// KEYBOARD SHORTCUTS
// ============================================

document.addEventListener('keydown', (e) => {
    // Ctrl+R to refresh
    if ((e.ctrlKey || e.metaKey) && e.key === 'r') {
        e.preventDefault();
        loadAllData();
    }

    // Ctrl+K to focus search
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        searchInput.focus();
    }

    // Escape to clear search
    if (e.key === 'Escape') {
        searchInput.value = '';
        displayData(allData);
    }
});

// ============================================
// INITIALIZATION
// ============================================

console.log('🚀 Distributed KV Store Dashboard loaded!');
console.log('API Base:', API_BASE);
console.log('Keyboard shortcuts:');
console.log('  Ctrl+R - Refresh data');
console.log('  Ctrl+K - Focus search');
console.log('  Escape - Clear search');
