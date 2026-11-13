# Tracing Middleware for FastAPI
"""
FastAPI middleware for distributed tracing.
"""

import time
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

import logging

from .tracing import get_tracer, start_trace, finish_trace, start_span, finish_span, SpanStatus
from ..config import get_observability_config

logger = logging.getLogger(__name__)


class TracingMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for automatic request tracing.
    
    Automatically creates traces for all HTTP requests.
    """
    
    def __init__(self, app: ASGIApp):
        """
        Initialize tracing middleware.
        
        Args:
            app: ASGI application
        """
        super().__init__(app)
        self.config = get_observability_config()
        self.tracer = get_tracer()
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request with tracing.
        
        Args:
            request: HTTP request
            call_next: Next middleware/handler
            
        Returns:
            HTTP response
        """
        if not self.config.tracing_enabled:
            return await call_next(request)
        
        # Start trace for request
        trace_name = f"{request.method} {request.url.path}"
        trace = self.tracer.start_trace(
            name=trace_name,
            metadata={
                "method": request.method,
                "path": str(request.url.path),
                "query_params": dict(request.query_params),
                "client_host": request.client.host if request.client else None
            }
        )
        
        # Add trace ID to request headers for propagation
        request.state.trace_id = trace.trace_id
        
        # Start span for request handling
        span = self.tracer.start_span(
            name="request_handler",
            metadata={
                "route": request.url.path,
                "method": request.method
            }
        )
        
        try:
            # Process request
            response = await call_next(request)
            
            # Finish span with success
            self.tracer.finish_span(
                span,
                status=SpanStatus.OK,
                error=None
            )
            
            # Add trace ID to response headers
            response.headers["X-Trace-ID"] = trace.trace_id
            
            return response
            
        except Exception as e:
            # Finish span with error
            self.tracer.finish_span(
                span,
                status=SpanStatus.ERROR,
                error=str(e)
            )
            raise
        
        finally:
            # Finish trace
            self.tracer.finish_trace(trace)

