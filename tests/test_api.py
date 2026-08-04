"""
Integration tests for the HTTP API.

Tests cover all endpoints (GET, SET, DELETE, health, info, etc.)
and error handling scenarios.
"""

import asyncio
import pytest
from fastapi.testclient import TestClient

from src.api.server import KVStoreAPI
from src.storage.recovery import StorageEngine


@pytest.fixture
async def storage():
    """Fixture providing a fresh StorageEngine instance."""
    store = StorageEngine(wal_path=":memory:")  # Use in-memory for testing
    await store.start()
    yield store
    await store.clear()


@pytest.fixture
def api(storage):
    """Fixture providing a KVStoreAPI instance with test storage."""
    # Create API and replace storage with test instance
    api_instance = KVStoreAPI(storage)
    return api_instance


@pytest.fixture
def client(api):
    """Fixture providing a TestClient for the API."""
    app = api.create_app()
    return TestClient(app)


class TestHealthAndInfo:
    """Test system endpoints."""
    
    def test_health_check(self, client):
        """Test the health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    def test_info_endpoint(self, client):
        """Test the info endpoint returns store metadata."""
        response = client.get("/info")
        assert response.status_code == 200
        data = response.json()
        assert "size" in data
        assert "wal_size_bytes" in data
        assert "was_recovered" in data


class TestSetOperations:
    """Test SET endpoint."""
    
    def test_set_simple_string(self, client):
        """Test setting a simple string value."""
        response = client.post(
            "/kv/test_key",
            json={"value": "test_value"}
        )
        assert response.status_code == 201
        assert response.json()["status"] == "success"
        assert response.json()["key"] == "test_key"
    
    def test_set_integer(self, client):
        """Test setting an integer value."""
        response = client.post(
            "/kv/counter",
            json={"value": 42}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "success"
    
    def test_set_object(self, client):
        """Test setting a complex object."""
        obj = {"name": "Alice", "age": 30, "email": "alice@example.com"}
        response = client.post(
            "/kv/user:1",
            json={"value": obj}
        )
        assert response.status_code == 201
        assert response.json()["status"] == "success"
    
    def test_set_list(self, client):
        """Test setting a list value."""
        lst = [1, 2, 3, 4, 5]
        response = client.post(
            "/kv/numbers",
            json={"value": lst}
        )
        assert response.status_code == 201
        assert response.json()["status"] == "success"
    
    def test_set_null_value(self, client):
        """Test setting None/null value."""
        response = client.post(
            "/kv/nullable",
            json={"value": None}
        )
        assert response.status_code == 201
        assert response.json()["status"] == "success"
    
    def test_set_empty_key_fails(self, client):
        """Test that setting an empty key fails."""
        response = client.post(
            "/kv/",
            json={"value": "something"}
        )
        # FastAPI will return 405 for path not found
        assert response.status_code in [404, 405]
    
    def test_set_overwrites_previous_value(self, client):
        """Test that setting a key overwrites the previous value."""
        # Set initial value
        client.post("/kv/key", json={"value": "value1"})
        
        # Overwrite
        response = client.post("/kv/key", json={"value": "value2"})
        assert response.status_code == 201
        
        # Verify new value
        get_response = client.get("/kv/key")
        assert get_response.json()["value"] == "value2"


class TestGetOperations:
    """Test GET endpoint."""
    
    def test_get_existing_key(self, client):
        """Test getting an existing key."""
        # Set a value
        client.post("/kv/test_key", json={"value": "test_value"})
        
        # Get it
        response = client.get("/kv/test_key")
        assert response.status_code == 200
        data = response.json()
        assert data["key"] == "test_key"
        assert data["value"] == "test_value"
        assert data["exists"] is True
    
    def test_get_nonexistent_key(self, client):
        """Test getting a non-existent key."""
        response = client.get("/kv/nonexistent")
        assert response.status_code == 200
        data = response.json()
        assert data["key"] == "nonexistent"
        assert data["value"] is None
        assert data["exists"] is False
    
    def test_get_integer_value(self, client):
        """Test getting an integer value."""
        client.post("/kv/count", json={"value": 42})
        
        response = client.get("/kv/count")
        assert response.status_code == 200
        assert response.json()["value"] == 42
    
    def test_get_object_value(self, client):
        """Test getting a complex object."""
        obj = {"name": "Bob", "status": "active"}
        client.post("/kv/user", json={"value": obj})
        
        response = client.get("/kv/user")
        assert response.status_code == 200
        assert response.json()["value"] == obj
    
    def test_get_after_overwrite(self, client):
        """Test that GET returns the latest value after overwrite."""
        client.post("/kv/key", json={"value": "v1"})
        client.post("/kv/key", json={"value": "v2"})
        client.post("/kv/key", json={"value": "v3"})
        
        response = client.get("/kv/key")
        assert response.json()["value"] == "v3"


class TestDeleteOperations:
    """Test DELETE endpoint."""
    
    def test_delete_existing_key(self, client):
        """Test deleting an existing key."""
        # Set a value
        client.post("/kv/test_key", json={"value": "test_value"})
        
        # Delete it
        response = client.delete("/kv/test_key")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["key"] == "test_key"
        
        # Verify it's gone
        get_response = client.get("/kv/test_key")
        assert get_response.json()["exists"] is False
    
    def test_delete_nonexistent_key_returns_404(self, client):
        """Test that deleting a non-existent key returns 404."""
        response = client.delete("/kv/nonexistent")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    
    def test_delete_after_overwrite(self, client):
        """Test deleting after multiple overwrites."""
        client.post("/kv/key", json={"value": "v1"})
        client.post("/kv/key", json={"value": "v2"})
        
        response = client.delete("/kv/key")
        assert response.status_code == 200
        
        get_response = client.get("/kv/key")
        assert get_response.json()["exists"] is False


class TestBulkOperations:
    """Test bulk operations (get all, clear)."""
    
    def test_get_all(self, client):
        """Test retrieving all key-value pairs."""
        # Set multiple values
        client.post("/kv/key1", json={"value": "value1"})
        client.post("/kv/key2", json={"value": "value2"})
        client.post("/kv/key3", json={"value": "value3"})
        
        response = client.get("/kv")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 3
        assert "key1" in data["data"]
        assert "key2" in data["data"]
        assert "key3" in data["data"]
    
    def test_get_all_empty_store(self, client):
        """Test getting all from an empty store."""
        response = client.get("/kv")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["data"] == {}
    
    def test_clear_all(self, client):
        """Test clearing all key-value pairs."""
        # Set multiple values
        client.post("/kv/key1", json={"value": "value1"})
        client.post("/kv/key2", json={"value": "value2"})
        
        # Clear
        response = client.delete("/kv")
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        
        # Verify all are gone
        get_all_response = client.get("/kv")
        assert get_all_response.json()["count"] == 0


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    def test_set_with_missing_value_field(self, client):
        """Test that SET without value field returns 400."""
        response = client.post(
            "/kv/test_key",
            json={}  # Missing "value" field
        )
        assert response.status_code == 422  # Validation error
    
    def test_special_characters_in_key(self, client):
        """Test keys with special characters."""
        special_key = "user:profile:123:settings"
        response = client.post(
            f"/kv/{special_key}",
            json={"value": "special_data"}
        )
        assert response.status_code == 201
        
        get_response = client.get(f"/kv/{special_key}")
        assert get_response.status_code == 200
        assert get_response.json()["value"] == "special_data"
    
    def test_very_long_key(self, client):
        """Test very long key."""
        long_key = "k" * 1000
        response = client.post(
            f"/kv/{long_key}",
            json={"value": "data"}
        )
        assert response.status_code == 201
    
    def test_very_large_value(self, client):
        """Test setting a very large value."""
        large_value = "x" * 1000000  # 1MB string
        response = client.post(
            "/kv/large",
            json={"value": large_value}
        )
        assert response.status_code == 201
        
        # Retrieve and verify
        get_response = client.get("/kv/large")
        assert get_response.status_code == 200
        assert len(get_response.json()["value"]) == 1000000


class TestSequentialOperations:
    """Test sequences of operations."""
    
    def test_set_get_delete_cycle(self, client):
        """Test a complete SET -> GET -> DELETE cycle."""
        key = "test_key"
        value = {"data": "test"}
        
        # Set
        set_response = client.post(f"/kv/{key}", json={"value": value})
        assert set_response.status_code == 201
        
        # Get
        get_response = client.get(f"/kv/{key}")
        assert get_response.status_code == 200
        assert get_response.json()["value"] == value
        
        # Delete
        del_response = client.delete(f"/kv/{key}")
        assert del_response.status_code == 200
        
        # Verify deleted
        final_get = client.get(f"/kv/{key}")
        assert final_get.json()["exists"] is False
    
    def test_multiple_operations_sequence(self, client):
        """Test a sequence of mixed operations."""
        # Set multiple keys
        for i in range(5):
            client.post(f"/kv/key{i}", json={"value": f"value{i}"})
        
        # Delete some
        client.delete("/kv/key1")
        client.delete("/kv/key3")
        
        # Get all
        response = client.get("/kv")
        assert response.json()["count"] == 3
        assert "key0" in response.json()["data"]
        assert "key1" not in response.json()["data"]
        assert "key2" in response.json()["data"]
        assert "key3" not in response.json()["data"]
        assert "key4" in response.json()["data"]


class TestConcurrentRequests:
    """Test concurrent API requests."""
    
    def test_concurrent_sets(self, client):
        """Test concurrent SET requests."""
        # Since TestClient is synchronous, we test sequential rapid requests
        for i in range(10):
            response = client.post(
                f"/kv/concurrent_key_{i}",
                json={"value": f"value_{i}"}
            )
            assert response.status_code == 201
        
        # Verify all are set
        get_response = client.get("/kv")
        assert get_response.json()["count"] == 10
    
    def test_interleaved_operations(self, client):
        """Test interleaved GET, SET, DELETE operations."""
        # Set
        client.post("/kv/key1", json={"value": "v1"})
        
        # Get
        assert client.get("/kv/key1").json()["exists"] is True
        
        # Set another
        client.post("/kv/key2", json={"value": "v2"})
        
        # Delete first
        client.delete("/kv/key1")
        
        # Get all
        response = client.get("/kv")
        assert response.json()["count"] == 1
        assert "key2" in response.json()["data"]
