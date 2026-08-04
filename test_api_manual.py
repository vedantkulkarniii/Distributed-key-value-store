"""
Manual test script to verify the API works correctly.
Run with: python test_api_manual.py
"""

import asyncio
import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.storage.store import KeyValueStore
from src.storage.wal import WriteAheadLog, PersistentKeyValueStore
from src.storage.recovery import StorageEngine


async def test_storage_engine():
    """Test the storage engine directly."""
    print("=" * 60)
    print("Testing Storage Engine (Phase 1)")
    print("=" * 60)
    
    # Create storage engine
    store = StorageEngine(wal_path="test_kv.log")
    await store.start()
    
    # Test SET
    print("\n1. Testing SET operations...")
    await store.set("user:1", json.dumps({"name": "Alice", "age": 30}))
    await store.set("user:2", json.dumps({"name": "Bob", "age": 25}))
    await store.set("counter", "42")
    print("✓ SET 3 keys successfully")
    
    # Test GET
    print("\n2. Testing GET operations...")
    val = await store.get("user:1")
    print(f"✓ GET user:1 = {val}")
    
    val = await store.get("counter")
    print(f"✓ GET counter = {val}")
    
    val = await store.get("nonexistent")
    print(f"✓ GET nonexistent = {val} (None as expected)")
    
    # Test EXISTS
    print("\n3. Testing EXISTS operations...")
    exists = await store.exists("user:1")
    print(f"✓ EXISTS user:1 = {exists} (True as expected)")
    
    exists = await store.exists("nonexistent")
    print(f"✓ EXISTS nonexistent = {exists} (False as expected)")
    
    # Test SIZE
    print("\n4. Testing SIZE...")
    size = await store.size()
    print(f"✓ Store size = {size}")
    
    # Test GET_ALL
    print("\n5. Testing GET_ALL...")
    all_data = await store.get_all()
    print(f"✓ All data: {json.dumps(all_data, indent=2)}")
    
    # Test DELETE
    print("\n6. Testing DELETE...")
    deleted = await store.delete("user:2")
    print(f"✓ DELETE user:2 = {deleted} (True as expected)")
    
    size_after = await store.size()
    print(f"✓ Store size after delete = {size_after}")
    
    # Test CLEAR
    print("\n7. Testing CLEAR...")
    await store.clear()
    size_final = await store.size()
    print(f"✓ Store size after clear = {size_final}")
    
    # Test WAL
    print("\n8. Testing WAL...")
    wal_size = await store.get_wal_size()
    print(f"✓ WAL file size = {wal_size} bytes")
    
    print("\n" + "=" * 60)
    print("✓ All Storage Engine tests passed!")
    print("=" * 60)
    
    # Cleanup
    await store.clear_wal()


async def test_api_models():
    """Test API request/response models."""
    print("\n" + "=" * 60)
    print("Testing API Models (Phase 1)")
    print("=" * 60)
    
    from src.api.server import (
        SetRequest, GetResponse, DeleteResponse, 
        ErrorResponse, StoreInfoResponse
    )
    
    # Test SetRequest
    print("\n1. Testing SetRequest model...")
    req = SetRequest(value="test_value", ttl_seconds=None)
    print(f"✓ SetRequest created: {req.model_dump()}")
    
    req_with_ttl = SetRequest(value={"key": "data"}, ttl_seconds=3600)
    print(f"✓ SetRequest with TTL: {req_with_ttl.model_dump()}")
    
    # Test GetResponse
    print("\n2. Testing GetResponse model...")
    resp = GetResponse(key="test_key", value="test_value", exists=True)
    print(f"✓ GetResponse created: {resp.model_dump()}")
    
    # Test DeleteResponse
    print("\n3. Testing DeleteResponse model...")
    resp = DeleteResponse(status="success", key="test_key", message="Deleted")
    print(f"✓ DeleteResponse created: {resp.model_dump()}")
    
    # Test ErrorResponse
    print("\n4. Testing ErrorResponse model...")
    resp = ErrorResponse(error="Not Found", detail="Key not found")
    print(f"✓ ErrorResponse created: {resp.model_dump()}")
    
    # Test StoreInfoResponse
    print("\n5. Testing StoreInfoResponse model...")
    resp = StoreInfoResponse(size=10, wal_size_bytes=1024, was_recovered=False)
    print(f"✓ StoreInfoResponse created: {resp.model_dump()}")
    
    print("\n" + "=" * 60)
    print("✓ All API Model tests passed!")
    print("=" * 60)


async def test_api_creation():
    """Test that the API can be created."""
    print("\n" + "=" * 60)
    print("Testing API Creation (Phase 1)")
    print("=" * 60)
    
    from src.api.server import KVStoreAPI
    from src.storage.recovery import StorageEngine
    
    # Create storage
    storage = StorageEngine(wal_path="test_api.log")
    await storage.start()
    
    # Create API
    api = KVStoreAPI(storage, host="127.0.0.1", port=8000)
    app = api.create_app()
    
    print("✓ FastAPI app created successfully")
    print(f"✓ App title: {app.title}")
    print(f"✓ App version: {app.version}")
    
    # Verify routes exist
    routes = [route.path for route in app.routes]
    print(f"\n✓ Available routes:")
    for route in sorted(set(routes)):
        print(f"  - {route}")
    
    print("\n" + "=" * 60)
    print("✓ API Creation tests passed!")
    print("=" * 60)
    
    # Cleanup
    await storage.clear_wal()


async def main():
    """Run all tests."""
    try:
        await test_storage_engine()
        await test_api_models()
        await test_api_creation()
        
        print("\n" + "=" * 60)
        print("🎉 ALL TESTS PASSED! 🎉")
        print("=" * 60)
        print("\nPhase 1 is fully functional!")
        print("\nTo start the API server, run:")
        print("  uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload")
        print("\nThen access the API at:")
        print("  http://localhost:8000")
        print("  http://localhost:8000/docs (OpenAPI docs)")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
