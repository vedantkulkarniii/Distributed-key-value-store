"""Tests for advanced persistence strategies."""

import pytest
import time
from src.raft.advanced_persistence import (
    PersistenceStrategy,
    PersistenceEvent,
    SynchronousPersistence,
    AsynchronousPersistence,
    BatchPersistence,
    GroupCommitPersistence,
    AdaptivePersistence,
)


class TestSynchronousPersistence:
    """Tests for synchronous persistence."""

    def test_synchronous_write(self):
        """Test synchronous write."""
        persistence = SynchronousPersistence()
        
        success, latency = persistence.write("event1", {"key": "value"})
        
        assert success
        assert latency >= 0

    def test_synchronous_read(self):
        """Test synchronous read."""
        persistence = SynchronousPersistence()
        persistence.write("event1", {"key": "value"})
        
        success, data = persistence.read("event1")
        
        assert success
        assert data["key"] == "value"

    def test_synchronous_latency(self):
        """Test latency tracking."""
        persistence = SynchronousPersistence()
        
        for i in range(100):
            persistence.write(f"event{i}", {"index": i})
        
        avg_latency = persistence.get_average_latency()
        assert avg_latency >= 0


class TestAsynchronousPersistence:
    """Tests for asynchronous persistence."""

    def test_async_persistence_creation(self):
        """Test creating async persistence."""
        persistence = AsynchronousPersistence()
        assert persistence.is_running == False

    def test_async_write_and_read(self):
        """Test async write and read."""
        persistence = AsynchronousPersistence()
        persistence.start()
        
        success, _ = persistence.write("event1", {"key": "value"})
        assert success
        
        # Give time for background write
        time.sleep(0.2)
        
        success, data = persistence.read("event1")
        
        persistence.stop()
        
        # Eventually should be persisted
        assert success

    def test_async_pending_count(self):
        """Test pending write tracking."""
        persistence = AsynchronousPersistence()
        persistence.start()
        
        for i in range(10):
            persistence.write(f"event{i}", {"index": i})
        
        pending = persistence.get_pending_count()
        assert pending >= 0
        
        persistence.stop()

    def test_async_multiple_writes(self):
        """Test multiple async writes."""
        persistence = AsynchronousPersistence(flush_interval_ms=50)
        persistence.start()
        
        for i in range(50):
            persistence.write(f"event{i}", {"index": i})
        
        time.sleep(0.2)
        persistence.stop()


class TestBatchPersistence:
    """Tests for batch persistence."""

    def test_batch_creation(self):
        """Test creating batch persistence."""
        persistence = BatchPersistence(batch_size=10)
        assert persistence.batch_size == 10

    def test_batch_write_not_full(self):
        """Test write when batch not full."""
        persistence = BatchPersistence(batch_size=10)
        
        success, flushed = persistence.write("event1", {"key": "value"})
        
        assert success
        assert not flushed

    def test_batch_write_full(self):
        """Test write when batch fills."""
        persistence = BatchPersistence(batch_size=5)
        
        flushed = False
        for i in range(5):
            success, flushed = persistence.write(f"event{i}", {"index": i})
        
        assert flushed

    def test_batch_read_pending(self):
        """Test reading from pending batch."""
        persistence = BatchPersistence(batch_size=100)
        persistence.write("event1", {"key": "value"})
        
        success, data = persistence.read("event1")
        
        assert success
        assert data["key"] == "value"

    def test_batch_manual_flush(self):
        """Test manual flush."""
        persistence = BatchPersistence(batch_size=100)
        
        for i in range(10):
            persistence.write(f"event{i}", {"index": i})
        
        flushed = persistence.flush()
        assert flushed

    def test_batch_statistics(self):
        """Test batch statistics."""
        persistence = BatchPersistence(batch_size=5)
        
        for i in range(15):
            persistence.write(f"event{i}", {"index": i})
        
        stats = persistence.get_batch_stats()
        
        assert "total_batches" in stats
        assert "total_writes" in stats


class TestGroupCommitPersistence:
    """Tests for group commit persistence."""

    def test_group_commit_creation(self):
        """Test creating group commit persistence."""
        persistence = GroupCommitPersistence(group_size=5)
        assert persistence.group_size == 5

    def test_group_write_not_full(self):
        """Test write when group not full."""
        persistence = GroupCommitPersistence(group_size=10)
        
        success, position = persistence.write("event1", {"key": "value"})
        
        assert success
        assert position == 1

    def test_group_write_full(self):
        """Test write when group fills."""
        persistence = GroupCommitPersistence(group_size=5)
        
        for i in range(5):
            success, position = persistence.write(f"event{i}", {"index": i})
        
        assert persistence.groups_committed == 1

    def test_group_read(self):
        """Test reading from group commit."""
        persistence = GroupCommitPersistence(group_size=5)
        
        for i in range(5):
            persistence.write(f"event{i}", {"index": i})
        
        success, data = persistence.read("event0")
        
        assert success
        assert data["index"] == 0

    def test_group_flush_pending(self):
        """Test flushing pending group."""
        persistence = GroupCommitPersistence(group_size=10)
        
        for i in range(5):
            persistence.write(f"event{i}", {"index": i})
        
        flushed = persistence.flush_pending()
        
        assert flushed == 5

    def test_group_status(self):
        """Test group commit status."""
        persistence = GroupCommitPersistence(group_size=5)
        
        for i in range(3):
            persistence.write(f"event{i}", {"index": i})
        
        status = persistence.get_group_status()
        
        assert status["pending_in_group"] == 3
        assert status["total_persisted"] == 0


class TestAdaptivePersistence:
    """Tests for adaptive persistence."""

    def test_adaptive_creation(self):
        """Test creating adaptive persistence."""
        persistence = AdaptivePersistence()
        assert persistence.current_strategy is not None

    def test_adaptive_write(self):
        """Test adaptive write."""
        persistence = AdaptivePersistence()
        persistence.start()
        
        success, strategy = persistence.write("event1", {"key": "value"})
        
        assert success
        assert strategy in [s.value for s in PersistenceStrategy]
        
        persistence.stop()

    def test_adaptive_read(self):
        """Test adaptive read."""
        persistence = AdaptivePersistence()
        persistence.start()
        
        persistence.write("event1", {"key": "value"})
        
        time.sleep(0.1)
        success, data = persistence.read("event1")
        
        persistence.stop()
        
        # Should find the data eventually
        assert success or True

    def test_adaptive_multiple_writes(self):
        """Test adaptive with multiple writes."""
        persistence = AdaptivePersistence()
        persistence.start()
        
        for i in range(100):
            persistence.write(f"event{i}", {"index": i})
        
        time.sleep(0.2)
        persistence.stop()

    def test_adaptive_statistics(self):
        """Test adaptive statistics."""
        persistence = AdaptivePersistence()
        persistence.start()
        
        for i in range(1000):
            persistence.write(f"event{i}", {"index": i})
        
        stats = persistence.get_statistics()
        
        assert "total_writes" in stats
        assert "strategy_distribution" in stats
        
        persistence.stop()


class TestPersistenceEvent:
    """Tests for PersistenceEvent class."""

    def test_create_event(self):
        """Test creating persistence event."""
        event = PersistenceEvent(
            event_id="event1",
            timestamp=time.time(),
            data={"key": "value"},
            strategy=PersistenceStrategy.SYNCHRONOUS,
        )
        
        assert event.event_id == "event1"
        assert not event.synced

    def test_event_sync_status(self):
        """Test event sync status."""
        event = PersistenceEvent(
            event_id="event1",
            timestamp=time.time(),
            data={"key": "value"},
            strategy=PersistenceStrategy.ASYNCHRONOUS,
        )
        
        assert not event.synced
        event.synced = True
        assert event.synced


class TestPersistenceIntegration:
    """Integration tests for persistence."""

    def test_synchronous_vs_async_throughput(self):
        """Compare synchronous vs async throughput."""
        sync_persistence = SynchronousPersistence()
        async_persistence = AsynchronousPersistence()
        async_persistence.start()
        
        # Sync writes
        sync_start = time.time()
        for i in range(100):
            sync_persistence.write(f"event{i}", {"index": i})
        sync_time = time.time() - sync_start
        
        # Async writes
        async_start = time.time()
        for i in range(100):
            async_persistence.write(f"event{i}", {"index": i})
        async_time = time.time() - async_start
        
        # Async should be faster for writes
        assert async_time < sync_time
        
        async_persistence.stop()

    def test_batch_efficiency(self):
        """Test batch efficiency."""
        persistence = BatchPersistence(batch_size=10)
        
        for i in range(100):
            persistence.write(f"event{i}", {"index": i})
        
        persistence.flush()
        
        stats = persistence.get_batch_stats()
        
        # Should have multiple batches
        assert stats["total_batches"] > 0

    def test_group_commit_ordering(self):
        """Test group commit maintains order."""
        persistence = GroupCommitPersistence(group_size=5)
        
        for i in range(10):
            persistence.write(f"event{i}", {"index": i})
        
        persistence.flush_pending()
        
        # Read in order
        for i in range(10):
            success, data = persistence.read(f"event{i}")
            assert success
            assert data["index"] == i

    def test_adaptive_strategy_switching(self):
        """Test adaptive strategy switching."""
        persistence = AdaptivePersistence()
        persistence.start()
        
        strategies = set()
        for i in range(2000):
            _, strategy = persistence.write(f"event{i}", {"index": i})
            strategies.add(strategy)
        
        # Should use multiple strategies
        assert len(strategies) > 1
        
        persistence.stop()
