# MAHOUN Distributed Tracing — Span/Trace System
"""
Distributed tracing implementation for MAHOUN.
"""

import json
import logging
import threading
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from enum import Enum

from ..config import get_observability_config

logger = logging.getLogger(__name__)

# Context variables for trace/span tracking
_current_trace: ContextVar[Optional['Trace']] = ContextVar('current_trace', default=None)
_current_span: ContextVar[Optional['Span']] = ContextVar('current_span', default=None)


class SpanStatus(str, Enum):
    """Span status."""
    OK = "ok"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class Span:
    """
    A single span in a trace.
    
    Represents one operation (e.g., agent call, database query).
    """
    span_id: str
    trace_id: str
    name: str
    parent_span_id: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    status: SpanStatus = SpanStatus.OK
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def finish(self, status: Optional[SpanStatus] = None, error: Optional[str] = None) -> None:
        """
        Finish the span.
        
        Args:
            status: Final status (default: OK)
            error: Error message if failed
        """
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        
        if status is not None:
            self.status = status
        
        if error is not None:
            self.error = error
            self.status = SpanStatus.ERROR
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "name": self.name,
            "parent_span_id": self.parent_span_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "status": self.status.value,
            "error": self.error,
            "metadata": self.metadata
        }


@dataclass
class Trace:
    """
    A complete trace (request lifecycle).
    
    Contains multiple spans representing operations.
    """
    trace_id: str
    name: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    spans: List[Span] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_span(self, span: Span) -> None:
        """Add a span to the trace."""
        self.spans.append(span)
    
    def finish(self) -> None:
        """Finish the trace."""
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "trace_id": self.trace_id,
            "name": self.name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "spans": [span.to_dict() for span in self.spans],
            "metadata": self.metadata
        }
    
    def to_ndjson(self) -> str:
        """Export as NDJSON (one line per span + trace)."""
        lines: List[Any] = []
        # Trace line
        trace_line = {
            "type": "trace",
            "trace_id": self.trace_id,
            "name": self.name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata
        }
        lines.append(json.dumps(trace_line))
        
        # Span lines
        for span in self.spans:
            span_line = {
                "type": "span",
                **span.to_dict()
            }
            lines.append(json.dumps(span_line))
        
        return "\n".join(lines)


class Tracer:
    """
    Main tracer class for distributed tracing.
    
    Thread-safe and context-aware.
    """
    
    def __init__(self, config: Optional[Any] = None):
        """
        Initialize tracer.
        
        Args:
            config: ObservabilityConfig (default: from get_observability_config)
        """
        from ..config import ObservabilityConfig, get_observability_config
        
        self.config = config or get_observability_config()
        self._traces: List[Trace] = []
        self._lock = threading.RLock()
        self._active_traces: Dict[str, Trace] = {}
    
    def start_trace(self, name: str, metadata: Optional[Dict[str, Any]] = None) -> Trace:
        """
        Start a new trace.
        
        Args:
            name: Trace name (e.g., "api_request", "agent_workflow")
            metadata: Additional metadata
            
        Returns:
            Trace instance
        """
        if not self.config.tracing_enabled:
            # Return dummy trace if disabled
            return Trace(trace_id="", name=name, metadata=metadata or {})
        
        trace_id = str(uuid.uuid4())
        trace = Trace(
            trace_id=trace_id,
            name=name,
            metadata=metadata or {}
        )
        
        with self._lock:
            self._active_traces[trace_id] = trace
        
        # Set in context
        _current_trace.set(trace)
        
        return trace
    
    def start_span(
        self,
        name: str,
        parent_span_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Span:
        """
        Start a new span.
        
        Args:
            name: Span name (e.g., "agent.process", "db.query")
            parent_span_id: Parent span ID (default: current span)
            metadata: Additional metadata
            
        Returns:
            Span instance
        """
        if not self.config.tracing_enabled:
            # Return dummy span if disabled
            return Span(span_id="", trace_id="", name=name, metadata=metadata or {})
        
        trace = _current_trace.get()
        if trace is None:
            # Auto-create trace if none exists
            trace = self.start_trace(name="auto_trace")
        
        span_id = str(uuid.uuid4())
        
        # Get parent from context if not provided
        if parent_span_id is None:
            current_span = _current_span.get()
            if current_span:
                parent_span_id = current_span.span_id
        
        span = Span(
            span_id=span_id,
            trace_id=trace.trace_id,
            name=name,
            parent_span_id=parent_span_id,
            metadata=metadata or {}
        )
        
        trace.add_span(span)
        _current_span.set(span)
        
        return span
    
    def finish_span(
        self,
        span: Span,
        status: Optional[SpanStatus] = None,
        error: Optional[str] = None
    ) -> None:
        """
        Finish a span.
        
        Args:
            span: Span to finish
            status: Final status
            error: Error message if failed
        """
        if not self.config.tracing_enabled:
            return
        
        span.finish(status=status, error=error)
        
        # Clear from context
        if _current_span.get() == span:
            _current_span.set(None)
    
    def finish_trace(self, trace: Trace) -> None:
        """
        Finish a trace and export it.
        
        Args:
            trace: Trace to finish
        """
        if not self.config.tracing_enabled:
            return
        
        trace.finish()
        
        with self._lock:
            if trace.trace_id in self._active_traces:
                del self._active_traces[trace.trace_id]
            
            self._traces.append(trace)
        
        # Export to NDJSON
        self._export_trace(trace)
        
        # Clear from context
        if _current_trace.get() == trace:
            _current_trace.set(None)
    
    def _export_trace(self, trace: Trace) -> None:
        """
        Export trace to NDJSON file.
        
        Args:
            trace: Trace to export
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"trace_{trace.trace_id}_{timestamp}.ndjson"
            filepath = self.config.traces_dir / filename
            
            with open(filepath, 'w') as f:
                f.write(trace.to_ndjson())
            
            logger.debug(f"Trace exported to {filepath}")
        except Exception as e:
            logger.error(f"Failed to export trace: {e}")
    
    def get_recent_traces(self, limit: int = 10) -> List[Trace]:
        """
        Get recent traces.
        
        Args:
            limit: Number of traces to return
            
        Returns:
            List of recent traces
        """
        with self._lock:
            return self._traces[-limit:]
    
    def get_trace(self, trace_id: str) -> Optional[Trace]:
        """
        Get trace by ID.
        
        Args:
            trace_id: Trace ID
            
        Returns:
            Trace or None if not found
        """
        with self._lock:
            # Check active traces
            if trace_id in self._active_traces:
                return self._active_traces[trace_id]
            
            # Check finished traces
            for trace in self._traces:
                if trace.trace_id == trace_id:
                    return trace
        
        return None


# Global tracer instance
_tracer_instance: Optional[Tracer] = None
_tracer_lock = threading.Lock()


def get_tracer() -> Tracer:
    """Get global tracer instance (singleton)."""
    global _tracer_instance
    
    if _tracer_instance is None:
        with _tracer_lock:
            if _tracer_instance is None:
                _tracer_instance = Tracer()
    
    return _tracer_instance


# Convenience functions
def get_current_trace() -> Optional[Trace]:
    """Get current trace from context."""
    return _current_trace.get()


def get_current_span() -> Optional[Span]:
    """Get current span from context."""
    return _current_span.get()


def start_trace(name: str, metadata: Optional[Dict[str, Any]] = None) -> Trace:
    """Start a new trace."""
    return get_tracer().start_trace(name, metadata)


def start_span(
    name: str,
    parent_span_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Span:
    """Start a new span."""
    return get_tracer().start_span(name, parent_span_id, metadata)


def finish_span(
    span: Span,
    status: Optional[SpanStatus] = None,
    error: Optional[str] = None
) -> None:
    """Finish a span."""
    get_tracer().finish_span(span, status, error)


def set_span_metadata(span: Span, key: str, value: Any) -> None:
    """Set metadata on a span."""
    span.metadata[key] = value


def finish_trace(trace: Trace) -> None:
    """Finish a trace."""
    get_tracer().finish_trace(trace)
