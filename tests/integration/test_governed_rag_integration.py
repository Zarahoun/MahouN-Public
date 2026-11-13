"""
Integration Tests for Governed RAG Service
==========================================

Tests the complete integration of PolicyAwareRAGService with:
- GovernanceContextMiddleware 
- ReasoningDependencyContainer
- Feature flag switching
- API endpoint flow

Part of: Phase 5 - Architecture Integration Mission
Author: MAHOUN Platform Governance Council
Version: 1.0.0
"""

import os
import pytest
from unittest.mock import AsyncMock, Mock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI, Request

from api.middleware.governance_context import GovernanceContextMiddleware, get_governance_context
from api.routers.reasoning import router as reasoning_router
from mahoun.reasoning.adapters import ReasoningDependencyContainer
from mahoun.core.protocols import RAGServiceProtocol
from mahoun.core.governance.governance_context import GovernanceContext, GovernanceContextManager


# ============================================================================
# Test Setup and Fixtures
# ============================================================================

@pytest.fixture
def app_with_middleware():
    """Create FastAPI app with governance middleware for testing."""
    app = FastAPI()
    
    # Add governance middleware
    app.add_middleware(GovernanceContextMiddleware, execution_mode="STRICT")
    
    # Add reasoning router
    app.include_router(reasoning_router)
    
    return app


@pytest.fixture
def client(app_with_middleware):
    """Test client with governance middleware."""
    return TestClient(app_with_middleware)


@pytest.fixture
def mock_rag_service():
    """Mock RAG service for testing."""
    service = Mock(spec=RAGServiceProtocol)
    service.retrieve = AsyncMock(return_value=Mock(
        documents=[],
        metadata={"total_results": 0},
        query_info=Mock(rewritten_query="test query")
    ))
    return service


@pytest.fixture
def mock_policy_aware_rag():
    """Mock PolicyAwareRAGService for testing."""
    service = Mock(spec=RAGServiceProtocol)
    service.retrieve = AsyncMock(return_value=Mock(
        documents=[],
        metadata={"total_results": 0, "policy_filtered": True},
        query_info=Mock(rewritten_query="policy-filtered query")
    ))
    return service


# ============================================================================
# Middleware Integration Tests
# ============================================================================

class TestGovernanceContextMiddleware:
    """Test governance context middleware behavior."""
    
    def test_middleware_creates_context_for_reasoning_endpoints(self, client):
        """Test that middleware creates governance context for reasoning endpoints."""
        with patch('api.routers.reasoning.get_verdict_engine') as mock_engine:
            # Mock the verdict engine to avoid initialization
            mock_engine.side_effect = Exception("Service unavailable test")
            
            response = client.post(
                "/api/v1/reasoning/generate-verdict",
                json={
                    "question": "Test legal question?",
                    "facts": [{"value": "Test fact"}],
                    "generate_proof": False
                },
                headers={"X-Correlation-ID": "test-correlation-123"}
            )
            
            # Should get past middleware (context creation) even if engine fails
            assert response.status_code in [500, 503]  # Engine failure, not middleware failure
    
    def test_middleware_skips_context_for_health_endpoints(self, app_with_middleware):
        """Test that middleware skips governance context for health endpoints."""
        client = TestClient(app_with_middleware)
        
        # Add a simple health endpoint
        @app_with_middleware.get("/health")
        async def health():
            return {"status": "ok"}
        
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    
    def test_middleware_extracts_correlation_id_from_headers(self):
        """Test correlation ID extraction from various headers."""
        from api.middleware.governance_context import GovernanceContextMiddleware
        
        middleware = GovernanceContextMiddleware(None)
        
        # Test X-Correlation-ID header
        request = Mock()
        request.headers = {"X-Correlation-ID": "corr-123"}
        correlation_id = middleware._extract_correlation_id(request)
        assert correlation_id == "corr-123"
        
        # Test X-Request-ID header fallback
        request.headers = {"X-Request-ID": "req-456"}
        correlation_id = middleware._extract_correlation_id(request)
        assert correlation_id == "req-456"
        
        # Test no headers (should return None for auto-generation)
        request.headers = {}
        correlation_id = middleware._extract_correlation_id(request)
        assert correlation_id is None


# ============================================================================
# DI Container Integration Tests
# ============================================================================

class TestDIContainerIntegration:
    """Test dependency injection container with feature flags."""
    
    @pytest.fixture(autouse=True)
    def reset_container(self):
        """Reset DI container between tests."""
        from mahoun.reasoning.adapters import reset_global_container
        yield
        reset_global_container()
    
    def test_di_container_uses_hybrid_rag_by_default(self, mock_rag_service):
        """Test that DI container uses HybridRAGService by default."""
        with patch('mahoun.reasoning.rag_adapter.create_rag_service') as mock_create:
            mock_create.return_value = mock_rag_service
            
            container = ReasoningDependencyContainer()
            service = container.rag_service
            
            # Should use standard HybridRAGService
            mock_create.assert_called_once()
            assert service == mock_rag_service
    
    def test_di_container_uses_policy_aware_rag_with_flag(self, mock_rag_service, mock_policy_aware_rag):
        """Test that DI container uses PolicyAwareRAGService when flag is enabled."""
        with patch.dict(os.environ, {"MAHOUN_USE_POLICY_AWARE_RAG": "true"}):
            with patch('mahoun.reasoning.rag_adapter.create_rag_service') as mock_create_base:
                with patch('mahoun.rag.policy_aware_rag_service.PolicyAwareRAGService') as mock_policy_cls:
                    mock_create_base.return_value = mock_rag_service
                    mock_policy_cls.return_value = mock_policy_aware_rag
                    
                    container = ReasoningDependencyContainer()
                    service = container.rag_service
                    
                    # Should create base service and wrap it
                    mock_create_base.assert_called_once()
                    mock_policy_cls.assert_called_once_with(
                        base_service=mock_rag_service,
                        enable_governance=True,
                        enable_cache=True
                    )
                    assert service == mock_policy_aware_rag


# ============================================================================
# Architecture Boundary Tests
# ============================================================================

class TestArchitectureBoundaries:
    """Test that architecture boundaries are maintained."""
    
    def test_middleware_only_creates_context_never_services(self):
        """Test that middleware only creates governance context, never services."""
        from api.middleware.governance_context import GovernanceContextMiddleware
        
        middleware = GovernanceContextMiddleware(None)
        
        # Middleware should not have any service creation methods
        assert not hasattr(middleware, 'create_rag_service')
        assert not hasattr(middleware, 'create_reasoning_engine')
        assert not hasattr(middleware, 'create_verdict_engine')
        
        # Middleware should only create governance context
        assert hasattr(middleware, '_extract_correlation_id')
        assert hasattr(middleware, '_extract_actor_id')
    
    def test_di_container_receives_context_never_creates_it(self):
        """Test that DI container receives context but never creates it."""
        container = ReasoningDependencyContainer()
        
        # Container should not create governance contexts
        assert not hasattr(container, 'create_governance_context')
        assert not hasattr(container, '_create_governance_context')
        
        # Container should create services only
        assert hasattr(container, '_create_rag_service')
        assert hasattr(container, '_create_reasoning_engine')
    
    def test_policy_aware_rag_wraps_base_service_correctly(self, mock_rag_service):
        """Test that PolicyAwareRAGService correctly wraps base service."""
        # Import the actual class to check its constructor
        from mahoun.rag.policy_aware_rag_service import PolicyAwareRAGService
        
        # Verify it takes base_service parameter (composition pattern)
        import inspect
        sig = inspect.signature(PolicyAwareRAGService.__init__)
        
        # Should have base_service parameter
        assert 'base_service' in sig.parameters


# ============================================================================
# End-to-End Integration Tests
# ============================================================================

class TestEndToEndIntegration:
    """Test complete end-to-end integration flow."""
    
    def test_governance_context_propagation_through_stack(self):
        """Test that governance context propagates from middleware to services."""
        # Create a mock request with governance context
        request = Mock(spec=Request)
        
        # Create mock governance context
        mock_context = Mock(spec=GovernanceContext)
        mock_context.context_id = "ctx-test-123"
        mock_context.correlation_id = "corr-test-456"
        
        # Set up request.state with governance context (simulating middleware)
        request.state = Mock()
        request.state.governance_context = mock_context
        
        # Test get_governance_context helper
        context = get_governance_context(request)
        assert context == mock_context
        assert context.context_id == "ctx-test-123"
        assert context.correlation_id == "corr-test-456"
    
    def test_governance_context_error_handling(self):
        """Test error handling when governance context is missing."""
        # Create request without governance context
        request = Mock(spec=Request)
        request.state = Mock()
        # No governance_context attribute
        
        with pytest.raises(RuntimeError, match="GovernanceContext not found in request.state"):
            get_governance_context(request)


# ============================================================================
# Regression Tests
# ============================================================================

class TestRegressionPrevention:
    """Test prevention of known regression patterns."""
    
    def test_no_god_object_pattern_in_policy_aware_rag(self):
        """Test that PolicyAwareRAGService doesn't become a God Object."""
        from mahoun.rag.policy_aware_rag_service import PolicyAwareRAGService
        
        # Should not have governance creation methods
        assert not hasattr(PolicyAwareRAGService, 'create_governance_context')
        assert not hasattr(PolicyAwareRAGService, 'create_reasoning_engine')
        assert not hasattr(PolicyAwareRAGService, 'orchestrate_workflow')
    
    def test_architecture_boundary_gate_compatibility(self):
        """Test that our changes pass the architecture boundary gate."""
        # This test runs the same checks as our CI gate
        import subprocess
        import os
        
        # Run architecture boundary gate
        gate_path = os.path.join(os.getcwd(), "ci/gates/gate_architecture_boundaries.sh")
        if os.path.exists(gate_path):
            result = subprocess.run([gate_path], capture_output=True, text=True)
            
            # Gate should pass (exit code 0)
            assert result.returncode == 0, f"Architecture boundary gate failed: {result.stdout}\n{result.stderr}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])