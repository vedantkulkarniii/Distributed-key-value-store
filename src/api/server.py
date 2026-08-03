"""
HTTP API server for the distributed key-value store.

Built on FastAPI for async request handling and automatic OpenAPI documentation.
Provides REST endpoints for GET, SET, and DELETE operations on the KV store.
"""

import logging
from typing import Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.storage.recovery import StorageEngine


logger = logging.getLogger(__name__)


# Request/Response Models

class SetRequest(BaseModel):
    """Request model for SET operations."""
    value: Any
    ttl_seconds: Optional[float] = None


class SetResponse(BaseModel):
    """Response model for SET operations."""
    status: str = "success"
    key: str
    message: str = "Value set successfully"


class GetResponse(BaseModel):
    """Response model for GET operations."""
    key: str
    value: Any
    exists: bool


class DeleteResponse(BaseModel):
    """Response model for DELETE operations."""
    status: str
    key: str
    message: str


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    detail: str


class StoreInfoResponse(BaseModel):
    """Response model for store info."""
    size: int
    wal_size_bytes: int
    was_recovered: bool


# API Server

class KVStoreAPI:
    """HTTP API wrapper around the storage engine."""
    
    def __init__(self, storage_engine: StorageEngine, host: str = "127.0.0.1", port: int = 8000):
        """
        Initialize the API server.
        
        Args:
            storage_engine: The StorageEngine instance to wrap
            host: Server host address
            port: Server port
        """
        self.storage = storage_engine
        self.host = host
        self.port = port
        self.app: Optional[FastAPI] = None
    
    def create_app(self) -> FastAPI:
        """
        Create and configure the FastAPI application.
        
        Returns:
            Configured FastAPI instance
        """
        
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # Startup
            logger.info("Starting KV Store API server")
            await self.storage.start()
            logger.info(f"Storage engine started. Was recovered: {self.storage.was_recovered}")
            yield
            # Shutdown
            logger.info("Shutting down KV Store API server")
        
        self.app = FastAPI(
            title="Distributed KV Store API",
            description="HTTP API for the distributed key-value store with Raft consensus",
            version="1.0.0",
            lifespan=lifespan
        )
        
        # Routes
        
        @self.app.get(
            "/health",
            summary="Health check",
            tags=["System"]
        )
        async def health():
            """Server health check endpoint."""
            return {
                "status": "healthy",
                "service": "kv-store-api"
            }
        
        @self.app.get(
            "/info",
            summary="Store information",
            response_model=StoreInfoResponse,
            tags=["System"]
        )
        async def info():
            """Get information about the store."""
            return StoreInfoResponse(
                size=await self.storage.size(),
                wal_size_bytes=await self.storage.get_wal_size(),
                was_recovered=self.storage.was_recovered
            )
        
        @self.app.post(
            "/kv/{key}",
            summary="Set a key-value pair",
            response_model=SetResponse,
            status_code=status.HTTP_201_CREATED,
            tags=["Key-Value Operations"]
        )
        async def set_key(key: str, request: SetRequest):
            """
            Set a key-value pair.
            
            Args:
                key: The key to set
                request: SetRequest body with value and optional ttl_seconds
                
            Returns:
                SetResponse with status confirmation
            """
            try:
                await self.storage.set(key, request.value)
                return SetResponse(key=key)
            except Exception as e:
                logger.error(f"Error setting key {key}: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to set key: {str(e)}"
                )
        
        @self.app.get(
            "/kv/{key}",
            summary="Get a value by key",
            response_model=GetResponse,
            tags=["Key-Value Operations"]
        )
        async def get_key(key: str):
            """
            Get a value by key.
            
            Args:
                key: The key to retrieve
                
            Returns:
                GetResponse with value and existence status
            """
            try:
                value = await self.storage.get(key)
                exists = await self.storage.exists(key)
                return GetResponse(key=key, value=value, exists=exists)
            except Exception as e:
                logger.error(f"Error getting key {key}: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to get key: {str(e)}"
                )
        
        @self.app.delete(
            "/kv/{key}",
            summary="Delete a key-value pair",
            response_model=DeleteResponse,
            tags=["Key-Value Operations"]
        )
        async def delete_key(key: str):
            """
            Delete a key-value pair.
            
            Args:
                key: The key to delete
                
            Returns:
                DeleteResponse with status
                
            Raises:
                404: If key doesn't exist
            """
            try:
                deleted = await self.storage.delete(key)
                if not deleted:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Key '{key}' not found"
                    )
                return DeleteResponse(
                    status="success",
                    key=key,
                    message=f"Key '{key}' deleted successfully"
                )
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error deleting key {key}: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to delete key: {str(e)}"
                )
        
        @self.app.get(
            "/kv",
            summary="Get all key-value pairs",
            tags=["Key-Value Operations"]
        )
        async def get_all():
            """
            Retrieve all key-value pairs in the store.
            
            Returns:
                Dictionary of all key-value pairs
            """
            try:
                all_data = await self.storage.get_all()
                return {"data": all_data, "count": len(all_data)}
            except Exception as e:
                logger.error(f"Error retrieving all keys: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to retrieve data: {str(e)}"
                )
        
        @self.app.delete(
            "/kv",
            summary="Clear all key-value pairs",
            tags=["Key-Value Operations"]
        )
        async def clear_all():
            """
            Clear all key-value pairs from the store.
            
            Returns:
                Confirmation message
            """
            try:
                await self.storage.clear()
                return {"status": "success", "message": "Store cleared successfully"}
            except Exception as e:
                logger.error(f"Error clearing store: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to clear store: {str(e)}"
                )
        
        return self.app
    
    async def run(self):
        """
        Run the API server (typically called via uvicorn).
        
        Use: uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload
        """
        if not self.app:
            self.create_app()
        
        import uvicorn
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()


# Create a global app instance for uvicorn
_storage = StorageEngine()
api = KVStoreAPI(_storage)
app = api.create_app()
