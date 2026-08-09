"""Snapshot Support and Fast State Transfer for Raft.

This module provides the foundation for snapshot management in Raft,
enabling fast state transfer to lagging followers without sending
the entire log.
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
import time


class SnapshotStatus(Enum):
    """Status of a snapshot."""
    
    PENDING = "pending"
    """Snapshot creation in progress."""
    
    COMPLETE = "complete"
    """Snapshot is ready for use."""
    
    INSTALLING = "installing"
    """Snapshot is being installed on a follower."""
    
    FAILED = "failed"
    """Snapshot creation or installation failed."""


@dataclass
class SnapshotMetadata:
    """Metadata for a snapshot."""
    
    last_included_index: int
    """The index of the last entry included in the snapshot."""
    
    last_included_term: int
    """The term of the last entry included in the snapshot."""
    
    creation_timestamp: float
    """When the snapshot was created."""
    
    size_bytes: int = 0
    """Size of the snapshot in bytes."""
    
    status: SnapshotStatus = SnapshotStatus.PENDING
    """Current status of the snapshot."""
    
    checksum: Optional[str] = None
    """Checksum of the snapshot for verification."""
    
    metadata_dict: Dict[str, Any] = field(default_factory=dict)
    """Additional metadata as a dictionary."""


class SnapshotManager:
    """Manages snapshots for fast state transfer in Raft.
    
    The SnapshotManager handles:
    - Creating snapshots of the current state machine
    - Tracking snapshot metadata
    - Coordinating InstallSnapshot RPC
    - Managing snapshot chunks for large snapshots
    """
    
    def __init__(self, max_snapshot_size: int = 100 * 1024 * 1024):
        """Initialize the snapshot manager.
        
        Args:
            max_snapshot_size: Maximum size of a snapshot in bytes (default 100MB).
        """
        self.max_snapshot_size = max_snapshot_size
        self.snapshots: Dict[int, SnapshotMetadata] = {}
        """Snapshots indexed by last_included_index."""
        
        self.current_snapshot: Optional[SnapshotMetadata] = None
        """The most recent snapshot."""
        
        self.snapshot_in_progress: bool = False
        """Whether a snapshot is currently being created."""
        
        self.chunk_size = 64 * 1024
        """Size of chunks for InstallSnapshot RPC (64KB)."""
    
    def create_snapshot(
        self,
        last_included_index: int,
        last_included_term: int,
        state_data: Dict[str, Any],
    ) -> Optional[SnapshotMetadata]:
        """Create a snapshot of the current state machine.
        
        Args:
            last_included_index: The index of the last entry in the snapshot.
            last_included_term: The term of the last entry in the snapshot.
            state_data: The state machine data to snapshot.
        
        Returns:
            SnapshotMetadata if creation succeeded, None if it failed.
        """
        if self.snapshot_in_progress:
            return None
        
        self.snapshot_in_progress = True
        
        try:
            # Calculate snapshot size (simplified - actual would serialize state_data)
            snapshot_size = len(str(state_data).encode())
            
            if snapshot_size > self.max_snapshot_size:
                return None
            
            # Create metadata
            metadata = SnapshotMetadata(
                last_included_index=last_included_index,
                last_included_term=last_included_term,
                creation_timestamp=time.time(),
                size_bytes=snapshot_size,
                status=SnapshotStatus.COMPLETE,
            )
            
            # Calculate checksum (simplified)
            metadata.checksum = self._calculate_checksum(state_data)
            
            # Store snapshot
            self.snapshots[last_included_index] = metadata
            self.current_snapshot = metadata
            
            return metadata
            
        finally:
            self.snapshot_in_progress = False
    
    def _calculate_checksum(self, data: Dict[str, Any]) -> str:
        """Calculate a checksum for snapshot data.
        
        Args:
            data: The data to checksum.
        
        Returns:
            A checksum string.
        """
        import hashlib
        data_str = str(sorted(data.items()))
        return hashlib.md5(data_str.encode()).hexdigest()
    
    def get_current_snapshot(self) -> Optional[SnapshotMetadata]:
        """Get the most recent snapshot.
        
        Returns:
            The most recent SnapshotMetadata or None if no snapshot exists.
        """
        return self.current_snapshot
    
    def get_snapshot_by_index(
        self,
        last_included_index: int,
    ) -> Optional[SnapshotMetadata]:
        """Get a specific snapshot by its last_included_index.
        
        Args:
            last_included_index: The index to retrieve.
        
        Returns:
            The SnapshotMetadata or None if not found.
        """
        return self.snapshots.get(last_included_index)
    
    def should_take_snapshot(
        self,
        log_size: int,
        log_entries: int,
    ) -> bool:
        """Determine if a snapshot should be taken.
        
        Args:
            log_size: Current size of the log in bytes.
            log_entries: Number of entries in the log.
        
        Returns:
            True if a snapshot should be taken, False otherwise.
        """
        # Take snapshot if log grows beyond threshold
        if log_size > 10 * 1024 * 1024:  # 10MB
            return True
        
        # Take snapshot if log has many entries
        if log_entries > 100000:
            return True
        
        return False
    
    def split_snapshot_into_chunks(
        self,
        snapshot_data: bytes,
    ) -> List[bytes]:
        """Split a snapshot into chunks for InstallSnapshot RPC.
        
        Args:
            snapshot_data: The snapshot data to split.
        
        Returns:
            A list of chunks.
        """
        chunks = []
        for i in range(0, len(snapshot_data), self.chunk_size):
            chunk = snapshot_data[i:i + self.chunk_size]
            chunks.append(chunk)
        
        return chunks
    
    def reassemble_snapshot(
        self,
        chunks: List[bytes],
    ) -> bytes:
        """Reassemble a snapshot from chunks.
        
        Args:
            chunks: The chunks to reassemble.
        
        Returns:
            The complete snapshot data.
        """
        return b"".join(chunks)
    
    def verify_snapshot_integrity(
        self,
        snapshot_data: bytes,
        expected_checksum: str,
    ) -> bool:
        """Verify the integrity of snapshot data.
        
        Args:
            snapshot_data: The snapshot data to verify.
            expected_checksum: The expected checksum.
        
        Returns:
            True if integrity is verified, False otherwise.
        """
        import hashlib
        actual_checksum = hashlib.md5(snapshot_data).hexdigest()
        return actual_checksum == expected_checksum
    
    def get_snapshot_statistics(self) -> Dict[str, Any]:
        """Get statistics about snapshots.
        
        Returns:
            A dictionary with snapshot statistics.
        """
        return {
            "total_snapshots": len(self.snapshots),
            "current_snapshot_index": (
                self.current_snapshot.last_included_index
                if self.current_snapshot
                else None
            ),
            "current_snapshot_size": (
                self.current_snapshot.size_bytes
                if self.current_snapshot
                else 0
            ),
            "snapshot_in_progress": self.snapshot_in_progress,
            "chunk_size": self.chunk_size,
        }


class InstallSnapshotHandler:
    """Interface for handling InstallSnapshot RPC.
    
    This class provides the contract for handling snapshot installation
    on followers during fast state transfer.
    """
    
    def handle_install_snapshot(
        self,
        term: int,
        leader_id: str,
        last_included_index: int,
        last_included_term: int,
        offset: int,
        data: bytes,
        done: bool,
    ) -> Dict[str, Any]:
        """Handle an InstallSnapshot RPC request.
        
        Args:
            term: The current term of the leader.
            leader_id: The ID of the leader sending the snapshot.
            last_included_index: The index of the last included entry.
            last_included_term: The term of the last included entry.
            offset: The byte offset of this chunk in the snapshot.
            data: The snapshot data chunk.
            done: Whether this is the last chunk.
        
        Returns:
            A dictionary with the RPC response (must include 'term').
        """
        raise NotImplementedError("Subclasses must implement handle_install_snapshot")
    
    def snapshot_received(self) -> None:
        """Called when a complete snapshot has been received.
        
        This is invoked after the last chunk is processed and verified.
        """
        raise NotImplementedError("Subclasses must implement snapshot_received")
    
    def can_accept_snapshot(self) -> bool:
        """Check if the follower can accept a snapshot.
        
        Returns:
            True if the follower is ready to accept a snapshot, False otherwise.
        """
        raise NotImplementedError("Subclasses must implement can_accept_snapshot")
