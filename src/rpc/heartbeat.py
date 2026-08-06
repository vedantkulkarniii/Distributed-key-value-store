"""
Heartbeat mechanism for Raft leaders and followers.

Leaders send periodic heartbeats to reset follower election timeouts.
Followers reset their election timer on valid heartbeats.
"""

import asyncio
import logging
from typing import Optional, Callable
from datetime import datetime


logger = logging.getLogger(__name__)


class HeartbeatManager:
    """
    Manages heartbeat sending for leaders.
    
    Sends periodic heartbeats to all followers to:
    1. Prevent follower timeouts (keep them from starting elections)
    2. Replicate log entries
    3. Communicate commit index
    """
    
    def __init__(self, node_id: str, interval: float = 0.15):
        """
        Initialize heartbeat manager.
        
        Args:
            node_id: ID of the leader node
            interval: Heartbeat interval in seconds (default: 150ms)
        """
        self.node_id = node_id
        self.interval = interval
        
        # Heartbeat state
        self.running = False
        self.task: Optional[asyncio.Task] = None
        
        # Current state for heartbeats
        self.current_term: int = 0
        self.commit_index: int = 0
        self.last_log_index: int = 0
        self.last_log_term: int = 0
        
        # Callback for sending heartbeats
        self.send_heartbeat_callback: Optional[Callable] = None
    
    def set_callbacks(self, send_callback: Callable) -> None:
        """
        Set the callback for sending heartbeats.
        
        Args:
            send_callback: Async function to call for each heartbeat
        """
        self.send_heartbeat_callback = send_callback
    
    def update_state(self, term: int, last_log_index: int, 
                    last_log_term: int, commit_index: int) -> None:
        """
        Update state for heartbeats.
        
        Called when leader state changes.
        
        Args:
            term: Current term
            last_log_index: Index of last log entry
            last_log_term: Term of last log entry
            commit_index: Current commit index
        """
        self.current_term = term
        self.last_log_index = last_log_index
        self.last_log_term = last_log_term
        self.commit_index = commit_index
        
        logger.debug(
            f"Node {self.node_id}: Updated heartbeat state "
            f"(term={term}, commit={commit_index})"
        )
    
    async def start(self) -> None:
        """Start sending heartbeats."""
        if self.running:
            logger.warning(f"Node {self.node_id}: Heartbeats already running")
            return
        
        if not self.send_heartbeat_callback:
            logger.error(f"Node {self.node_id}: No heartbeat callback set")
            return
        
        self.running = True
        logger.info(
            f"Node {self.node_id}: Starting heartbeat (interval={self.interval}s)"
        )
        
        # Create heartbeat task
        self.task = asyncio.create_task(self._send_heartbeats_loop())
    
    async def stop(self) -> None:
        """Stop sending heartbeats."""
        if not self.running:
            return
        
        self.running = False
        
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        logger.info(f"Node {self.node_id}: Stopped heartbeat")
    
    async def _send_heartbeats_loop(self) -> None:
        """Main heartbeat loop."""
        try:
            while self.running:
                try:
                    # Send heartbeat
                    await self.send_heartbeat_callback(
                        term=self.current_term,
                        last_log_index=self.last_log_index,
                        last_log_term=self.last_log_term,
                        commit_index=self.commit_index
                    )
                    
                    logger.debug(
                        f"Node {self.node_id}: Sent heartbeat (term={self.current_term})"
                    )
                    
                except Exception as e:
                    logger.error(f"Node {self.node_id}: Error sending heartbeat: {e}")
                
                # Wait for next heartbeat interval
                await asyncio.sleep(self.interval)
        
        except asyncio.CancelledError:
            logger.debug(f"Node {self.node_id}: Heartbeat task cancelled")
        except Exception as e:
            logger.error(f"Node {self.node_id}: Heartbeat loop error: {e}")
            self.running = False


class ElectionTimeout:
    """
    Manages election timeout for followers and candidates.
    
    Followers start election if no heartbeat received within timeout period.
    """
    
    def __init__(self, node_id: str, min_timeout: float = 0.15, 
                 max_timeout: float = 0.3):
        """
        Initialize election timeout.
        
        Args:
            node_id: Node ID
            min_timeout: Minimum timeout in seconds (default: 150ms)
            max_timeout: Maximum timeout in seconds (default: 300ms)
        """
        self.node_id = node_id
        self.min_timeout = min_timeout
        self.max_timeout = max_timeout
        
        # Randomized timeout value
        import random
        self.timeout = random.uniform(min_timeout, max_timeout)
        
        # Timeout state
        self.running = False
        self.task: Optional[asyncio.Task] = None
        self.last_reset: datetime = datetime.now()
        
        # Callback when timeout expires
        self.on_timeout_callback: Optional[Callable] = None
    
    def set_callback(self, callback: Callable) -> None:
        """
        Set callback for when timeout expires.
        
        Args:
            callback: Async function to call on timeout
        """
        self.on_timeout_callback = callback
    
    def reset(self) -> None:
        """Reset the election timeout."""
        import random
        self.timeout = random.uniform(self.min_timeout, self.max_timeout)
        self.last_reset = datetime.now()
        
        logger.debug(
            f"Node {self.node_id}: Reset election timeout (will expire in {self.timeout:.2f}s)"
        )
    
    async def start(self) -> None:
        """Start the election timeout."""
        if self.running:
            logger.warning(f"Node {self.node_id}: Election timeout already running")
            return
        
        if not self.on_timeout_callback:
            logger.error(f"Node {self.node_id}: No timeout callback set")
            return
        
        self.running = True
        self.reset()
        
        logger.info(
            f"Node {self.node_id}: Starting election timeout "
            f"(range {self.min_timeout:.2f}s - {self.max_timeout:.2f}s)"
        )
        
        self.task = asyncio.create_task(self._timeout_loop())
    
    async def stop(self) -> None:
        """Stop the election timeout."""
        if not self.running:
            return
        
        self.running = False
        
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        logger.info(f"Node {self.node_id}: Stopped election timeout")
    
    async def _timeout_loop(self) -> None:
        """Main timeout loop."""
        try:
            while self.running:
                await asyncio.sleep(self.timeout)
                
                if self.running:
                    logger.warning(
                        f"Node {self.node_id}: Election timeout expired! "
                        f"Starting election..."
                    )
                    
                    try:
                        await self.on_timeout_callback()
                    except Exception as e:
                        logger.error(
                            f"Node {self.node_id}: Error in timeout callback: {e}"
                        )
                    
                    # Reschedule next timeout
                    self.reset()
        
        except asyncio.CancelledError:
            logger.debug(f"Node {self.node_id}: Timeout task cancelled")
        except Exception as e:
            logger.error(f"Node {self.node_id}: Timeout loop error: {e}")
            self.running = False


class TimingManager:
    """
    Centralized management of heartbeat and election timing.
    
    Coordinates between:
    - Leader's heartbeat sending
    - Follower's election timeout
    - State transitions
    """
    
    def __init__(self, node_id: str, heartbeat_interval: float = 0.15,
                 election_timeout_min: float = 0.15,
                 election_timeout_max: float = 0.3):
        """
        Initialize timing manager.
        
        Args:
            node_id: Node ID
            heartbeat_interval: Leader heartbeat interval
            election_timeout_min: Min election timeout
            election_timeout_max: Max election timeout
        """
        self.node_id = node_id
        
        # Components
        self.heartbeat = HeartbeatManager(node_id, interval=heartbeat_interval)
        self.election_timeout = ElectionTimeout(
            node_id,
            min_timeout=election_timeout_min,
            max_timeout=election_timeout_max
        )
    
    async def become_leader(self) -> None:
        """
        Transition to leader role.
        
        Stops election timeout and starts sending heartbeats.
        """
        logger.info(f"Node {self.node_id}: Becoming leader")
        
        await self.election_timeout.stop()
        await self.heartbeat.start()
    
    async def become_follower(self) -> None:
        """
        Transition to follower role.
        
        Stops sending heartbeats and starts election timeout.
        """
        logger.info(f"Node {self.node_id}: Becoming follower")
        
        await self.heartbeat.stop()
        await self.election_timeout.start()
    
    def reset_election_timeout(self) -> None:
        """
        Reset election timeout (e.g., on valid heartbeat).
        
        Prevents follower from starting election.
        """
        if self.election_timeout.running:
            self.election_timeout.reset()
    
    async def shutdown(self) -> None:
        """Shutdown timing manager."""
        await self.heartbeat.stop()
        await self.election_timeout.stop()
        logger.info(f"Node {self.node_id}: Timing manager shutdown")


def create_timing_manager(node_id: str) -> TimingManager:
    """
    Factory function to create a timing manager.
    
    Args:
        node_id: Node ID
        
    Returns:
        Configured TimingManager
    """
    return TimingManager(
        node_id,
        heartbeat_interval=0.15,  # 150ms
        election_timeout_min=0.15,  # 150ms
        election_timeout_max=0.3   # 300ms
    )
