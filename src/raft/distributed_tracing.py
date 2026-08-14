"""
Distributed Tracing & Observability

Comprehensive distributed tracing for request flows across cluster nodes,
enabling deep insights into system behavior.

Features:
- Request tracing with unique trace IDs
- Span creation and tracking
- Cross-node correlation
- Performance metrics collection
- Bottleneck identification
- Request path visualization
- Trace aggregation and analysis
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any
from enum import Enum
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


class SpanStatus(Enum):
    """Span execution status"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class Span:
    """Tracing span representing single operation"""
    span_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    trace_id: str = ""
    parent_span_id: Optional[str] = None
    operation_name: str = ""
    node_id: str = ""
    status: SpanStatus = SpanStatus.PENDING
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    duration_ms: float = 0.0
    tags: Dict[str, Any] = field(default_factory=dict)
    logs: List[Dict[str, Any]] = field(default_factory=list)
    error_message: Optional[str] = None
    
    def mark_success(self):
        """Mark span as successful"""
        self.status = SpanStatus.SUCCESS
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
    
    def mark_error(self, error_msg: str):
        """Mark span as failed
        
        Args:
            error_msg: Error message
        """
        self.status = SpanStatus.ERROR
        self.error_message = error_msg
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
    
    def add_tag(self, key: str, value: Any):
        """Add tag to span
        
        Args:
            key: Tag key
            value: Tag value
        """
        self.tags[key] = value
    
    def add_log(self, message: str, level: str = "info", **kwargs):
        """Add log entry to span
        
        Args:
            message: Log message
            level: Log level
            **kwargs: Additional log fields
        """
        self.logs.append({
            "timestamp": time.time(),
            "level": level,
            "message": message,
            **kwargs
        })
    
    def to_dict(self) -> Dict:
        """Convert span to dictionary
        
        Returns:
            Dictionary representation
        """
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "operation_name": self.operation_name,
            "node_id": self.node_id,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "tags": self.tags,
            "logs": self.logs,
            "error": self.error_message
        }


@dataclass
class Trace:
    """Complete trace for a request across cluster"""
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4())[:16])
    root_operation: str = ""
    spans: Dict[str, Span] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    duration_ms: float = 0.0
    nodes_visited: Set[str] = field(default_factory=set)
    
    def add_span(self, span: Span):
        """Add span to trace
        
        Args:
            span: Span to add
        """
        span.trace_id = self.trace_id
        self.spans[span.span_id] = span
        self.nodes_visited.add(span.node_id)
    
    def get_critical_path(self) -> List[Span]:
        """Get critical path (longest execution chain)
        
        Returns:
            List of spans in critical path
        """
        if not self.spans:
            return []
        
        # Build parent-child relationships
        children = defaultdict(list)
        roots = []
        
        for span in self.spans.values():
            if span.parent_span_id is None:
                roots.append(span)
            else:
                children[span.parent_span_id].append(span)
        
        # DFS to find longest path
        def find_longest_path(span):
            if span.span_id not in children:
                return [span], span.duration_ms
            
            max_path = [span]
            max_duration = span.duration_ms
            
            for child in children[span.span_id]:
                child_path, child_duration = find_longest_path(child)
                total_duration = span.duration_ms + child_duration
                
                if total_duration > max_duration:
                    max_path = [span] + child_path
                    max_duration = total_duration
            
            return max_path, max_duration
        
        if not roots:
            return list(self.spans.values())
        
        longest_path = []
        max_duration = 0
        
        for root in roots:
            path, duration = find_longest_path(root)
            if duration > max_duration:
                longest_path = path
                max_duration = duration
        
        return longest_path
    
    def finalize(self):
        """Finalize trace"""
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
    
    def to_dict(self) -> Dict:
        """Convert trace to dictionary
        
        Returns:
            Dictionary representation
        """
        return {
            "trace_id": self.trace_id,
            "root_operation": self.root_operation,
            "duration_ms": self.duration_ms,
            "nodes_visited": list(self.nodes_visited),
            "span_count": len(self.spans),
            "spans": [s.to_dict() for s in self.spans.values()]
        }


class DistributedTracer:
    """Manages distributed tracing across cluster"""
    
    def __init__(self, max_traces: int = 1000):
        """Initialize tracer
        
        Args:
            max_traces: Maximum traces to keep in memory
        """
        self.current_trace: Optional[Trace] = None
        self.current_span: Optional[Span] = None
        self.traces: Dict[str, Trace] = {}
        self.max_traces = max_traces
        self.trace_stats: Dict[str, int] = defaultdict(int)
    
    def start_trace(self, operation_name: str, node_id: str = "local") -> str:
        """Start new trace
        
        Args:
            operation_name: Name of operation
            node_id: Node ID
            
        Returns:
            Trace ID
        """
        trace = Trace(root_operation=operation_name)
        self.current_trace = trace
        self.traces[trace.trace_id] = trace
        
        # Create root span
        span = Span(operation_name=operation_name, node_id=node_id)
        span.status = SpanStatus.RUNNING
        self.start_span(span)
        
        return trace.trace_id
    
    def start_span(self, span: Span) -> str:
        """Start new span
        
        Args:
            span: Span to start
            
        Returns:
            Span ID
        """
        if self.current_span:
            span.parent_span_id = self.current_span.span_id
        
        span.status = SpanStatus.RUNNING
        parent_span = self.current_span
        self.current_span = span
        
        if self.current_trace:
            self.current_trace.add_span(span)
        
        self.current_span = parent_span
        
        return span.span_id
    
    def end_span(self, span_id: str, success: bool = True, error_msg: Optional[str] = None):
        """End span
        
        Args:
            span_id: Span ID
            success: Whether span succeeded
            error_msg: Optional error message
        """
        if not self.current_trace or span_id not in self.current_trace.spans:
            return
        
        span = self.current_trace.spans[span_id]
        if success:
            span.mark_success()
        else:
            span.mark_error(error_msg or "Unknown error")
    
    def end_trace(self, trace_id: str):
        """End trace
        
        Args:
            trace_id: Trace ID
        """
        if trace_id not in self.traces:
            return
        
        trace = self.traces[trace_id]
        trace.finalize()
        self.current_trace = None
        
        # Cleanup old traces
        if len(self.traces) > self.max_traces:
            oldest = min(self.traces.values(), key=lambda t: t.start_time)
            del self.traces[oldest.trace_id]
    
    def get_trace(self, trace_id: str) -> Optional[Trace]:
        """Get trace by ID
        
        Args:
            trace_id: Trace ID
            
        Returns:
            Trace or None
        """
        return self.traces.get(trace_id)
    
    def get_traces_for_operation(self, operation_name: str) -> List[Trace]:
        """Get traces for specific operation
        
        Args:
            operation_name: Operation name
            
        Returns:
            List of traces
        """
        return [t for t in self.traces.values() 
                if t.root_operation == operation_name]
    
    def get_slow_traces(self, threshold_ms: float = 1000) -> List[Trace]:
        """Get traces slower than threshold
        
        Args:
            threshold_ms: Time threshold in milliseconds
            
        Returns:
            List of slow traces
        """
        return [t for t in self.traces.values() 
                if t.duration_ms > threshold_ms]
    
    def get_failed_traces(self) -> List[Trace]:
        """Get traces with errors
        
        Returns:
            List of failed traces
        """
        failed = []
        for trace in self.traces.values():
            for span in trace.spans.values():
                if span.status == SpanStatus.ERROR:
                    failed.append(trace)
                    break
        return failed
    
    def get_tracing_stats(self) -> Dict:
        """Get tracing statistics
        
        Returns:
            Statistics dictionary
        """
        total_duration = sum(t.duration_ms for t in self.traces.values())
        avg_duration = total_duration / max(len(self.traces), 1)
        
        operation_stats = {}
        for op_name in self.trace_stats:
            op_traces = self.get_traces_for_operation(op_name)
            if op_traces:
                avg_op_duration = sum(t.duration_ms for t in op_traces) / len(op_traces)
                operation_stats[op_name] = {
                    "count": len(op_traces),
                    "avg_duration_ms": avg_op_duration,
                    "min_duration_ms": min(t.duration_ms for t in op_traces),
                    "max_duration_ms": max(t.duration_ms for t in op_traces)
                }
        
        return {
            "total_traces": len(self.traces),
            "total_spans": sum(len(t.spans) for t in self.traces.values()),
            "average_duration_ms": avg_duration,
            "slow_traces": len(self.get_slow_traces()),
            "failed_traces": len(self.get_failed_traces()),
            "operations": operation_stats
        }


class TraceAnalyzer:
    """Analyzes traces for insights"""
    
    def __init__(self, tracer: DistributedTracer):
        """Initialize analyzer
        
        Args:
            tracer: DistributedTracer instance
        """
        self.tracer = tracer
        self.bottlenecks: List[Dict] = []
        self.insights: List[str] = []
    
    def analyze_trace(self, trace_id: str) -> Dict:
        """Analyze single trace
        
        Args:
            trace_id: Trace ID
            
        Returns:
            Analysis results
        """
        trace = self.tracer.get_trace(trace_id)
        if not trace:
            return {}
        
        analysis = {
            "trace_id": trace_id,
            "total_duration_ms": trace.duration_ms,
            "span_count": len(trace.spans),
            "nodes_visited": list(trace.nodes_visited),
            "critical_path": [s.to_dict() for s in trace.get_critical_path()]
        }
        
        # Find slowest span
        if trace.spans:
            slowest = max(trace.spans.values(), key=lambda s: s.duration_ms)
            analysis["slowest_span"] = slowest.to_dict()
        
        return analysis
    
    def identify_bottlenecks(self) -> List[Dict]:
        """Identify performance bottlenecks
        
        Returns:
            List of bottleneck information
        """
        bottlenecks = []
        
        # Find slowest operations
        operation_stats = self.tracer.get_tracing_stats()["operations"]
        
        for op_name, stats in operation_stats.items():
            if stats["max_duration_ms"] > 5000:  # Arbitrary threshold
                bottlenecks.append({
                    "operation": op_name,
                    "max_duration_ms": stats["max_duration_ms"],
                    "type": "slow_operation"
                })
        
        # Find error patterns
        failed_traces = self.tracer.get_failed_traces()
        if len(failed_traces) > 5:
            bottlenecks.append({
                "type": "high_error_rate",
                "error_count": len(failed_traces)
            })
        
        self.bottlenecks = bottlenecks
        return bottlenecks
    
    def generate_insights(self) -> List[str]:
        """Generate insights from trace data
        
        Returns:
            List of insight strings
        """
        insights = []
        stats = self.tracer.get_tracing_stats()
        
        if stats["average_duration_ms"] > 500:
            insights.append(f"High average latency: {stats['average_duration_ms']:.0f}ms")
        
        if stats["slow_traces"] > len(stats["total_traces"]) * 0.1:
            insights.append(f"{stats['slow_traces']} slow traces detected (>1000ms)")
        
        if stats["failed_traces"] > 0:
            insights.append(f"{stats['failed_traces']} failed traces detected")
        
        self.insights = insights
        return insights
    
    def get_analysis_report(self) -> Dict:
        """Get comprehensive analysis report
        
        Returns:
            Analysis report dictionary
        """
        return {
            "stats": self.tracer.get_tracing_stats(),
            "bottlenecks": self.identify_bottlenecks(),
            "insights": self.generate_insights()
        }
