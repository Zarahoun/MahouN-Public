"""
MAHOUN Governance Kernel - Standalone Server
============================================

A minimal HTTP server that exposes governance functionality
without requiring grpc or heavy dependencies.

Endpoints:
  POST /v1/governance/enforce     - Enforce governance rules
  POST /v1/governance/validate    - Validate reasoning response
  POST /v1/governance/context     - Create governance context
  GET  /health                    - Health check
  GET  /metrics                   - Prometheus metrics (simple)

Usage:
  python -m mahoun.infrastructure.interfaces.governance_server
  
Environment:
  MAHOUN_GOVERNANCE_PORT=8080
  MAHOUN_METRICS_PORT=9090
"""

import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict

# Import kernel components
from mahoun.core.governance_kernel import (
    QueryType,
    GovernanceError,
    enforce_governance,
    GovernanceContext,
    set_governance_context,
    clear_governance_context,
)
from mahoun.core.governance_lock import GovernanceLock, GovernanceMode


class GovernanceHandler(BaseHTTPRequestHandler):
    """HTTP request handler for governance kernel"""
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == "/health":
            self._handle_health()
        elif self.path == "/metrics":
            self._handle_metrics()
        else:
            self._send_error(404, "Not Found")
    
    def do_POST(self):
        """Handle POST requests"""
        if self.path == "/v1/governance/enforce":
            self._handle_enforce()
        elif self.path == "/v1/governance/validate":
            self._handle_validate()
        elif self.path == "/v1/governance/context":
            self._handle_context()
        else:
            self._send_error(404, "Not Found")
    
    def _handle_health(self):
        """Health check endpoint"""
        try:
            # Verify governance lock is initialized
            lock = GovernanceLock.get_or_initialize()
            mode = lock.get_mode()
            
            response = {
                "status": "healthy",
                "governance_mode": mode.value,
                "governance_enabled": lock.is_enforcement_enabled(),
                "version": "1.0.0",
            }
            self._send_json(200, response)
        except Exception as e:
            self._send_error(503, f"Unhealthy: {str(e)}")
    
    def _handle_metrics(self):
        """Simple Prometheus-style metrics"""
        try:
            lock = GovernanceLock.get_or_initialize()
            metadata = lock.get_audit_metadata()
            
            metrics = f"""# HELP governance_initialized Governance lock initialization status
# TYPE governance_initialized gauge
governance_initialized{{mode="{metadata['mode']}"}} {1 if metadata['initialized'] else 0}

# HELP governance_change_attempts Number of bypass attempts
# TYPE governance_change_attempts counter
governance_change_attempts {metadata['change_attempts']}

# HELP governance_enforcement_enabled Enforcement status
# TYPE governance_enforcement_enabled gauge
governance_enforcement_enabled {1 if lock.is_enforcement_enabled() else 0}
"""
            self._send_response(200, metrics.encode(), content_type="text/plain")
        except Exception as e:
            self._send_error(500, f"Metrics error: {str(e)}")
    
    def _handle_enforce(self):
        """Enforce governance rules"""
        try:
            # Parse request
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            request = json.loads(body)
            
            # Extract parameters
            query_type_str = request.get('query_type', 'UNKNOWN')
            query_type = QueryType[query_type_str]
            correlation_id = request.get('correlation_id')
            actor_id = request.get('actor_id')
            allow_destructive = request.get('allow_destructive', False)
            
            # Enforce
            enforce_governance(
                query_type=query_type,
                correlation_id=correlation_id,
                actor_id=actor_id,
                allow_destructive=allow_destructive,
            )
            
            response = {
                "status": "allowed",
                "query_type": query_type_str,
                "correlation_id": correlation_id,
            }
            self._send_json(200, response)
            
        except GovernanceError as e:
            self._send_json(403, {
                "status": "denied",
                "error": "GovernanceError",
                "message": str(e),
            })
        except Exception as e:
            self._send_error(500, str(e))
    
    def _handle_validate(self):
        """Validate reasoning response (placeholder)"""
        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            request = json.loads(body)
            
            # For now, just return success
            # In full implementation, would use FortressValidator
            response = {
                "status": "validated",
                "passed": True,
                "correlation_id": request.get('correlation_id', 'unknown'),
            }
            self._send_json(200, response)
            
        except Exception as e:
            self._send_error(500, str(e))
    
    def _handle_context(self):
        """Create governance context"""
        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            request = json.loads(body)
            
            # Create context
            ctx = GovernanceContext(
                correlation_id=request['correlation_id'],
                actor_id=request['actor_id'],
                scope_id=request.get('scope_id'),
                query_type=QueryType[request['query_type']] if 'query_type' in request else None,
                origin=request.get('origin'),
            )
            
            # Set in context var
            set_governance_context(ctx)
            
            response = {
                "status": "created",
                "correlation_id": ctx.correlation_id,
                "actor_id": ctx.actor_id,
            }
            self._send_json(200, response)
            
        except Exception as e:
            self._send_error(500, str(e))
    
    def _send_json(self, status: int, data: Dict[str, Any]):
        """Send JSON response"""
        body = json.dumps(data).encode()
        self._send_response(status, body, content_type="application/json")
    
    def _send_response(self, status: int, body: bytes, content_type: str = "application/json"):
        """Send HTTP response"""
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    
    def _send_error(self, status: int, message: str):
        """Send error response"""
        self._send_json(status, {"error": message})
    
    def log_message(self, format, *args):
        """Override to customize logging"""
        sys.stderr.write(f"[{self.date_time_string()}] {format % args}\n")


def run_server():
    """Run the governance kernel server"""
    # Initialize governance lock
    print("[Governance Kernel] Initializing...")
    lock = GovernanceLock.initialize(mode=GovernanceMode.STRICT)
    print(f"[Governance Kernel] Lock initialized: mode={lock.get_mode().value}")
    
    # Get port from environment
    port = int(os.getenv('MAHOUN_GOVERNANCE_PORT', '8080'))
    
    # Create server
    server = HTTPServer(('0.0.0.0', port), GovernanceHandler)
    print(f"[Governance Kernel] Server listening on port {port}")
    print(f"[Governance Kernel] Health: http://localhost:{port}/health")
    print(f"[Governance Kernel] Metrics: http://localhost:{port}/metrics")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Governance Kernel] Shutting down...")
        server.shutdown()
        print("[Governance Kernel] Goodbye!")


if __name__ == "__main__":
    run_server()
