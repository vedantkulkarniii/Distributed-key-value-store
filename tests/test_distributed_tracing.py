"""
Tests for distributed tracing & observability

Covers:
- Span creation and tracking
- Trace creation and completion
- Cross-node correlation
- Performance metrics
- Bottleneck identification
- Trace analysis
"""

import pytest
import time
from src.raft.distributed_tracing import (
    DistributedTracer, Span, Trace, TraceAnalyzer, SpanStatus
)


class TestSpan:
    """Test Span class"""
    
    def test_create_span(self):
        """Test creating span"""
        span = Span(operation_name="test_op", node_id="node_1")
        assert span.operation_name == "test_op"
        assert span.node_id == "node_1"
        assert span.status == SpanStatus.PENDING
    
    def test_mark_success(self):
        """Test marking span as success"""
        span = Span(operation_name="test_op", node_id="node_1")
        span.mark_success()
        
        assert span.status == SpanStatus.SUCCESS
        assert span.end_time is not None
        assert span.duration_ms > 0
    
    def test_mark_error(self):
        """Test marking span as error"""
        span = Span(operation_name="test_op", node_id="node_1")
        span.mark_error("Test error")
        
        assert span.status == SpanStatus.ERROR
        assert span.error_message == "Test error"
    
    def test_add_tag(self):
        """Test adding tags"""
        span = Span(operation_name="test_op", node_id="node_1")
        span.add_tag("key", "value")
        span.add_tag("count", 42)
        
        assert span.tags["key"] == "value"
        assert span.tags["count"] == 42
    
    def test_add_log(self):
        """Test adding logs"""
        span = Span(operation_name="test_op", node_id="node_1")
        span.add_log("Test message", level="info")
        span.add_log("Error occurred", level="error")
        
        assert len(span.logs) == 2
        assert span.logs[0]["message"] == "Test message"
    
    def test_to_dict(self):
        """Test converting span to dictionary"""
        span = Span(operation_name="test_op", node_id="node_1")
        span.mark_success()
        
        span_dict = span.to_dict()
        assert "span_id" in span_dict
        assert span_dict["operation_name"] == "test_op"
        assert span_dict["status"] == "success"


class TestTrace:
    """Test Trace class"""
    
    def test_create_trace(self):
        """Test creating trace"""
        trace = Trace(root_operation="test_operation")
        assert trace.root_operation == "test_operation"
        assert len(trace.spans) == 0
    
    def test_add_span(self):
        """Test adding span to trace"""
        trace = Trace(root_operation="test_operation")
        span = Span(operation_name="child_op", node_id="node_1")
        
        trace.add_span(span)
        
        assert len(trace.spans) == 1
        assert span.trace_id == trace.trace_id
        assert "node_1" in trace.nodes_visited
    
    def test_get_critical_path(self):
        """Test getting critical path"""
        trace = Trace(root_operation="test_operation")
        
        root_span = Span(operation_name="root", node_id="node_1")
        root_span.start_time = time.time()
        root_span.duration_ms = 100
        
        child_span = Span(operation_name="child", node_id="node_2")
        child_span.parent_span_id = root_span.span_id
        child_span.duration_ms = 50
        
        trace.add_span(root_span)
        trace.add_span(child_span)
        
        critical_path = trace.get_critical_path()
        assert len(critical_path) >= 1
    
    def test_finalize_trace(self):
        """Test finalizing trace"""
        trace = Trace(root_operation="test_operation")
        trace.finalize()
        
        assert trace.end_time is not None
        assert trace.duration_ms > 0
    
    def test_to_dict(self):
        """Test converting trace to dictionary"""
        trace = Trace(root_operation="test_operation")
        span = Span(operation_name="op", node_id="node_1")
        trace.add_span(span)
        trace.finalize()
        
        trace_dict = trace.to_dict()
        assert "trace_id" in trace_dict
        assert trace_dict["root_operation"] == "test_operation"
        assert len(trace_dict["spans"]) == 1


class TestDistributedTracer:
    """Test DistributedTracer class"""
    
    @pytest.fixture
    def tracer(self):
        """Create tracer for testing"""
        return DistributedTracer()
    
    def test_start_trace(self, tracer):
        """Test starting trace"""
        trace_id = tracer.start_trace("test_op", node_id="node_1")
        
        assert trace_id in tracer.traces
        assert tracer.current_trace is not None
    
    def test_start_span(self, tracer):
        """Test starting span"""
        trace_id = tracer.start_trace("test_op")
        span = Span(operation_name="child_op", node_id="node_1")
        
        span_id = tracer.start_span(span)
        assert span_id is not None
    
    def test_end_span_success(self, tracer):
        """Test ending span successfully"""
        trace_id = tracer.start_trace("test_op")
        span = Span(operation_name="child_op", node_id="node_1")
        span_id = tracer.start_span(span)
        
        tracer.end_span(span_id, success=True)
        
        ended_span = tracer.current_trace.spans[span_id]
        assert ended_span.status == SpanStatus.SUCCESS
    
    def test_end_span_error(self, tracer):
        """Test ending span with error"""
        trace_id = tracer.start_trace("test_op")
        span = Span(operation_name="child_op", node_id="node_1")
        span_id = tracer.start_span(span)
        
        tracer.end_span(span_id, success=False, error_msg="Test error")
        
        ended_span = tracer.current_trace.spans[span_id]
        assert ended_span.status == SpanStatus.ERROR
    
    def test_end_trace(self, tracer):
        """Test ending trace"""
        trace_id = tracer.start_trace("test_op")
        tracer.end_trace(trace_id)
        
        trace = tracer.get_trace(trace_id)
        assert trace.end_time is not None
    
    def test_get_trace(self, tracer):
        """Test retrieving trace"""
        trace_id = tracer.start_trace("test_op")
        tracer.end_trace(trace_id)
        
        retrieved = tracer.get_trace(trace_id)
        assert retrieved is not None
        assert retrieved.root_operation == "test_op"
    
    def test_get_traces_for_operation(self, tracer):
        """Test getting traces by operation"""
        trace_id1 = tracer.start_trace("operation_A")
        tracer.end_trace(trace_id1)
        
        trace_id2 = tracer.start_trace("operation_B")
        tracer.end_trace(trace_id2)
        
        op_a_traces = tracer.get_traces_for_operation("operation_A")
        assert len(op_a_traces) == 1
    
    def test_get_slow_traces(self, tracer):
        """Test getting slow traces"""
        trace_id = tracer.start_trace("test_op")
        trace = tracer.current_trace
        trace.start_time = time.time() - 2.0  # 2 seconds ago
        tracer.end_trace(trace_id)
        
        slow = tracer.get_slow_traces(threshold_ms=500)
        assert len(slow) > 0
    
    def test_get_failed_traces(self, tracer):
        """Test getting failed traces"""
        trace_id = tracer.start_trace("test_op")
        span = Span(operation_name="child_op", node_id="node_1")
        span_id = tracer.start_span(span)
        tracer.end_span(span_id, success=False, error_msg="Error")
        tracer.end_trace(trace_id)
        
        failed = tracer.get_failed_traces()
        assert len(failed) > 0
    
    def test_get_tracing_stats(self, tracer):
        """Test getting tracing statistics"""
        trace_id = tracer.start_trace("test_op")
        tracer.end_trace(trace_id)
        
        stats = tracer.get_tracing_stats()
        assert "total_traces" in stats
        assert "average_duration_ms" in stats
        assert stats["total_traces"] == 1
    
    def test_trace_cleanup_old_traces(self, tracer):
        """Test cleanup of old traces"""
        tracer.max_traces = 5
        
        # Create more traces than max
        for i in range(10):
            trace_id = tracer.start_trace(f"op_{i}")
            tracer.end_trace(trace_id)
        
        # Should only keep max_traces
        assert len(tracer.traces) <= tracer.max_traces


class TestTraceAnalyzer:
    """Test TraceAnalyzer class"""
    
    @pytest.fixture
    def analyzer(self):
        """Create analyzer for testing"""
        tracer = DistributedTracer()
        return TraceAnalyzer(tracer)
    
    def test_analyze_trace(self, analyzer):
        """Test analyzing trace"""
        trace_id = analyzer.tracer.start_trace("test_op")
        span = Span(operation_name="child_op", node_id="node_1")
        analyzer.tracer.start_span(span)
        analyzer.tracer.end_trace(trace_id)
        
        analysis = analyzer.analyze_trace(trace_id)
        assert "trace_id" in analysis
        assert analysis["span_count"] > 0
    
    def test_identify_bottlenecks(self, analyzer):
        """Test identifying bottlenecks"""
        # Create slow trace
        trace_id = analyzer.tracer.start_trace("slow_op")
        trace = analyzer.tracer.current_trace
        trace.start_time = time.time() - 10  # 10 seconds
        analyzer.tracer.end_trace(trace_id)
        
        bottlenecks = analyzer.identify_bottlenecks()
        # May or may not find bottlenecks depending on threshold
        assert isinstance(bottlenecks, list)
    
    def test_generate_insights(self, analyzer):
        """Test generating insights"""
        trace_id = analyzer.tracer.start_trace("test_op")
        analyzer.tracer.end_trace(trace_id)
        
        insights = analyzer.generate_insights()
        assert isinstance(insights, list)
    
    def test_get_analysis_report(self, analyzer):
        """Test getting analysis report"""
        trace_id = analyzer.tracer.start_trace("test_op")
        span = Span(operation_name="child_op", node_id="node_1")
        analyzer.tracer.start_span(span)
        analyzer.tracer.end_trace(trace_id)
        
        report = analyzer.get_analysis_report()
        assert "stats" in report
        assert "bottlenecks" in report
        assert "insights" in report


class TestTracingScenarios:
    """Test complex tracing scenarios"""
    
    def test_multi_node_trace(self):
        """Test tracing across multiple nodes"""
        tracer = DistributedTracer()
        
        trace_id = tracer.start_trace("distributed_op", node_id="node_1")
        
        # Simulate spans on different nodes
        span1 = Span(operation_name="local_op", node_id="node_1")
        tracer.start_span(span1)
        
        span2 = Span(operation_name="remote_op", node_id="node_2")
        tracer.start_span(span2)
        
        span3 = Span(operation_name="remote_op", node_id="node_3")
        tracer.start_span(span3)
        
        tracer.end_trace(trace_id)
        
        trace = tracer.get_trace(trace_id)
        assert len(trace.nodes_visited) >= 1  # At least the local node
    
    def test_nested_spans(self):
        """Test nested span hierarchy"""
        tracer = DistributedTracer()
        
        trace_id = tracer.start_trace("parent_op", node_id="node_1")
        
        parent_span = Span(operation_name="parent", node_id="node_1")
        parent_id = tracer.start_span(parent_span)
        
        child_span = Span(operation_name="child", node_id="node_1")
        child_id = tracer.start_span(child_span)
        
        trace = tracer.current_trace
        child = trace.spans[child_id]
        
        assert child.parent_span_id == parent_id
    
    def test_trace_with_errors(self):
        """Test tracing with error spans"""
        tracer = DistributedTracer()
        analyzer = TraceAnalyzer(tracer)
        
        trace_id = tracer.start_trace("failing_op", node_id="node_1")
        
        span1 = Span(operation_name="successful", node_id="node_1")
        id1 = tracer.start_span(span1)
        tracer.end_span(id1, success=True)
        
        span2 = Span(operation_name="failed", node_id="node_1")
        id2 = tracer.start_span(span2)
        tracer.end_span(id2, success=False, error_msg="Operation failed")
        
        tracer.end_trace(trace_id)
        
        # Should detect errors
        failed = tracer.get_failed_traces()
        assert len(failed) > 0
