"""
Client request pipeline and batching for optimized throughput.

Implements:
- Request batching for network efficiency
- Pipelining for parallelism
- Backpressure handling
- Request prioritization
- Batch aggregation
"""

import logging
from typing import Dict, Any, List, Optional, Tuple, Callable
from datetime import datetime, timedelta
from enum import Enum
from collections import deque
import threading

logger = logging.getLogger(__name__)


class RequestPriority(Enum):
    """Request priority levels."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class BatchRequest:
    """Represents a batch of requests."""
    
    def __init__(self, batch_id: str, max_size: int = 100, max_wait_ms: int = 100):
        self.batch_id = batch_id
        self.max_size = max_size
        self.max_wait_ms = max_wait_ms
        
        self.requests: List[Dict[str, Any]] = []
        self.created_at = datetime.now()
        self.is_full = False
        self.is_sent = False
    
    def add_request(self, request: Dict[str, Any]) -> bool:
        """Add request to batch."""
        if len(self.requests) >= self.max_size:
            self.is_full = True
            return False
        
        self.requests.append(request)
        return True
    
    def is_ready(self) -> bool:
        """Check if batch is ready to send."""
        if self.is_full:
            return True
        
        age = (datetime.now() - self.created_at).total_seconds() * 1000
        return age >= self.max_wait_ms
    
    def get_size(self) -> int:
        """Get batch size."""
        return len(self.requests)


class RequestPipeline:
    """
    Manages request pipelining and batching.
    
    Ensures:
    - Efficient batching of requests
    - Network optimization
    - Throughput maximization
    - Request ordering preservation
    """
    
    def __init__(self, node_id: str, batch_size: int = 100, batch_timeout_ms: int = 100):
        """Initialize request pipeline."""
        self.node_id = node_id
        self.batch_size = batch_size
        self.batch_timeout_ms = batch_timeout_ms
        
        # Request queues by priority
        self.request_queues: Dict[RequestPriority, deque] = {
            priority: deque() for priority in RequestPriority
        }
        
        # Current batch
        self.current_batch: Optional[BatchRequest] = None
        self.batch_counter = 0
        
        # Statistics
        self.total_requests = 0
        self.total_batches = 0
        self.total_throughput = 0
        self.avg_batch_size = 0
        self.batches_sent = 0
        
        # Callbacks
        self.on_batch_ready: Optional[Callable] = None
        
        # Thread safety
        self.lock = threading.RLock()
        
        logger.info(
            f"Request pipeline initialized for {node_id} "
            f"(batch_size={batch_size}, timeout={batch_timeout_ms}ms)"
        )
    
    def submit_request(
        self,
        request: Dict[str, Any],
        priority: RequestPriority = RequestPriority.NORMAL,
    ) -> Tuple[bool, Optional[str]]:
        """
        Submit a request to pipeline.
        
        Args:
            request: Request dictionary
            priority: Request priority
            
        Returns:
            Tuple of (success, error_message)
        """
        with self.lock:
            try:
                # Add to priority queue
                self.request_queues[priority].append(request)
                self.total_requests += 1
                
                # Try to form batch
                should_batch = len(self.request_queues[priority]) >= self.batch_size
                
                return True, None
                
            except Exception as e:
                logger.error(f"Error submitting request: {e}")
                return False, f"Failed to submit request: {str(e)}"
    
    def create_batch(self) -> Optional[BatchRequest]:
        """
        Create batch from pending requests.
        
        Returns:
            BatchRequest or None
        """
        with self.lock:
            try:
                batch_id = f"batch-{self.batch_counter}-{int(datetime.now().timestamp() * 1000)}"
                self.batch_counter += 1
                
                batch = BatchRequest(
                    batch_id,
                    max_size=self.batch_size,
                    max_wait_ms=self.batch_timeout_ms
                )
                
                # Fill batch with requests in priority order
                for priority in [RequestPriority.CRITICAL, RequestPriority.HIGH, 
                                RequestPriority.NORMAL, RequestPriority.LOW]:
                    queue = self.request_queues[priority]
                    
                    while queue and batch.get_size() < self.batch_size:
                        request = queue.popleft()
                        batch.add_request(request)
                
                if batch.get_size() == 0:
                    return None
                
                self.current_batch = batch
                return batch
                
            except Exception as e:
                logger.error(f"Error creating batch: {e}")
                return None
    
    def get_batch_for_sending(self) -> Optional[BatchRequest]:
        """
        Get batch ready for sending.
        
        Returns:
            BatchRequest or None
        """
        with self.lock:
            # Create batch if needed
            if not self.current_batch:
                self.create_batch()
            
            if not self.current_batch:
                return None
            
            # Check if ready to send
            if self.current_batch.is_ready():
                batch = self.current_batch
                self.current_batch = None
                return batch
            
            return None
    
    def send_batch(self, batch: BatchRequest) -> Tuple[bool, Optional[str]]:
        """
        Send batch (mark as sent).
        
        Args:
            batch: Batch to send
            
        Returns:
            Tuple of (success, error_message)
        """
        with self.lock:
            try:
                batch.is_sent = True
                self.batches_sent += 1
                self.total_batches += 1
                
                # Update statistics
                if self.total_batches > 0:
                    self.avg_batch_size = (
                        (self.avg_batch_size * (self.total_batches - 1) + batch.get_size()) /
                        self.total_batches
                    )
                
                logger.debug(f"Sent batch {batch.batch_id} with {batch.get_size()} requests")
                
                return True, None
                
            except Exception as e:
                logger.error(f"Error sending batch: {e}")
                return False, f"Failed to send batch: {str(e)}"
    
    def get_pending_count(self) -> int:
        """Get count of pending requests."""
        with self.lock:
            total = sum(len(q) for q in self.request_queues.values())
            if self.current_batch:
                total += self.current_batch.get_size()
            return total
    
    def get_queue_depth(self, priority: Optional[RequestPriority] = None) -> Dict[str, int]:
        """
        Get queue depth information.
        
        Args:
            priority: Specific priority or None for all
            
        Returns:
            Dictionary with queue depths
        """
        with self.lock:
            if priority:
                return {priority.name: len(self.request_queues[priority])}
            
            return {
                p.name: len(q) for p, q in self.request_queues.items()
            }
    
    def get_throughput(self) -> Dict[str, Any]:
        """Get throughput statistics."""
        with self.lock:
            if self.total_batches == 0:
                throughput = 0
            else:
                throughput = self.total_requests / self.total_batches
            
            return {
                "total_requests": self.total_requests,
                "total_batches": self.total_batches,
                "batches_sent": self.batches_sent,
                "avg_batch_size": self.avg_batch_size,
                "throughput": throughput,
                "pending_requests": self.get_pending_count(),
            }
    
    def flush_pipeline(self) -> List[Dict[str, Any]]:
        """
        Flush all pending requests.
        
        Returns:
            List of all pending requests
        """
        with self.lock:
            all_requests = []
            
            # Collect from all queues
            for queue in self.request_queues.values():
                all_requests.extend(queue)
                queue.clear()
            
            # Collect from current batch
            if self.current_batch:
                all_requests.extend(self.current_batch.requests)
                self.current_batch = None
            
            logger.info(f"Flushed {len(all_requests)} pending requests")
            
            return all_requests
    
    def get_status(self) -> Dict[str, Any]:
        """Get pipeline status."""
        with self.lock:
            return {
                "node_id": self.node_id,
                "pending_requests": self.get_pending_count(),
                "queue_depths": self.get_queue_depth(),
                "current_batch_size": (
                    self.current_batch.get_size() if self.current_batch else 0
                ),
                "statistics": self.get_throughput(),
            }
