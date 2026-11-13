"""
Integration Test: Bootstrap Runtime Integration
================================================

Tests that bootstrap_runtime() is properly called during app startup
and that SERVICE_REGISTRY is correctly populated.

CRITICAL (P0): These tests verify the fix for B1+B8 where bootstrap
was NEVER called in api/main.py, resulting in empty SERVICE_REGISTRY
and silent failure of graph-enhanced retrieval.
"""

import pytest
import os
import sys
from unittest.mock import patch, MagicMock


@pytest.mark.integration
class TestBootstrapIntegration:
    """Test bootstrap runtime integration with FastAPI app"""
    
    @pytest.mark.p2
    def test_bootstrap_called_on_startup(self, monkeypatch):
        """
        CRITICAL: Verify bootstrap_runtime() is called during app startup
        
        Test verifies fix for B1: bootstrap was NEVER called in api/main.py
        """
        # Set test environment to avoid database connection attempts
        monkeypatch.setenv("MAHOUN_ENV", "test")
        monkeypatch.setenv("MAHOUN_TESTING", "1")
        monkeypatch.setenv("ENABLE_POSTGRES", "false")
        monkeypatch.setenv("ENABLE_NEO4J", "false")
        monkeypatch.setenv("ENABLE_REDIS", "false")
        monkeypatch.setenv("MAHOUN_GRAPH_BACKEND", "disabled_fallback")  # Valid value per config_validator
        
        # Mock bootstrap_runtime to track if it's called
        bootstrap_called = {"called": False, "registry": {}}
        
        def mock_bootstrap():
            bootstrap_called["called"] = True
            bootstrap_called["registry"] = {
                "query": MagicMock(),
                "gnn": MagicMock(),
                "graph_retriever": MagicMock(),
                "graph_vector_sync": MagicMock(),
                "legal_query_executor": MagicMock(),
            }
            return bootstrap_called["registry"]
        
        # CRITICAL: Patch BEFORE importing app
        with patch("mahoun.bootstrap.runtime.bootstrap_runtime", side_effect=mock_bootstrap):
            # Clear any cached imports AND runtime config cache
            if "api.main" in sys.modules:
                del sys.modules["api.main"]
            if "mahoun.core.runtime_config" in sys.modules:
                # Clear lru_cache to pick up new environment variables
                from mahoun.core import runtime_config
                runtime_config.get_runtime_settings.cache_clear()
            
            # Import app (this triggers lifespan startup)
            from api.main import app
            from fastapi.testclient import TestClient
            
            # Create test client (triggers lifespan)
            with TestClient(app) as client:
                # Verify bootstrap was called
                assert bootstrap_called["called"], (
                    "❌ CRITICAL: bootstrap_runtime() was NOT called during app startup. "
                    "This is the root cause of B1+B8 where SERVICE_REGISTRY stays empty."
                )
                
                # Verify registry is stored in app.state
                assert hasattr(app.state, "service_registry"), (
                    "app.state.service_registry not set. "
                    "Bootstrap registry should be stored for health checks."
                )
    
    @pytest.mark.integration
    @pytest.mark.p2
    def test_bootstrap_populates_service_registry(self, monkeypatch):
        """
        Verify SERVICE_REGISTRY contains required services after bootstrap
        
        Test verifies fix for B8: SERVICE_REGISTRY was empty → graph_retriever=None
        """
        monkeypatch.setenv("MAHOUN_ENV", "test")
        monkeypatch.setenv("MAHOUN_TESTING", "1")
        monkeypatch.setenv("ENABLE_POSTGRES", "false")
        monkeypatch.setenv("ENABLE_NEO4J", "false")
        monkeypatch.setenv("ENABLE_REDIS", "false")
        monkeypatch.setenv("MAHOUN_GRAPH_BACKEND", "disabled_fallback")
        
        # Mock all services to avoid real Neo4j connection
        mock_services = {
            "query": MagicMock(),
            "gnn": MagicMock(),
            "graph_retriever": MagicMock(),
            "graph_vector_sync": MagicMock(),
            "legal_query_executor": MagicMock(),
        }
        
        with patch("mahoun.bootstrap.runtime.bootstrap_runtime", return_value=mock_services):
            # Clear cached imports AND runtime config cache
            if "api.main" in sys.modules:
                del sys.modules["api.main"]
            if "mahoun.core.runtime_config" in sys.modules:
                # Clear lru_cache to pick up new environment variables
                from mahoun.core import runtime_config
                runtime_config.get_runtime_settings.cache_clear()
                
            from api.main import app
            from fastapi.testclient import TestClient
            
            with TestClient(app) as client:
                # Verify critical services are registered
                registry = app.state.service_registry
                
                assert "graph_retriever" in registry, (
                    "❌ CRITICAL: graph_retriever not in SERVICE_REGISTRY. "
                    "This causes silent failure of graph-enhanced RAG."
                )
                
                assert "query" in registry, "query service not registered"
                assert "gnn" in registry, "gnn service not registered"
                
                # Verify graph_retriever is not None
                assert registry["graph_retriever"] is not None, (
                    "graph_retriever is None — wiring error in bootstrap"
                )
    
    @pytest.mark.integration
    @pytest.mark.p2
    def test_app_fails_on_bootstrap_error(self, monkeypatch):
        """
        CRITICAL: App startup MUST fail if bootstrap fails
        
        Fail-fast behavior prevents silent degradation
        """
        monkeypatch.setenv("MAHOUN_ENV", "test")
        monkeypatch.setenv("MAHOUN_TESTING", "1")
        monkeypatch.setenv("ENABLE_POSTGRES", "false")
        monkeypatch.setenv("ENABLE_NEO4J", "false")
        monkeypatch.setenv("ENABLE_REDIS", "false")
        monkeypatch.setenv("MAHOUN_GRAPH_BACKEND", "disabled_fallback")
        
        # Mock bootstrap to raise error
        def mock_bootstrap_fail():
            raise RuntimeError("Simulated bootstrap failure")
        
        with patch("mahoun.bootstrap.runtime.bootstrap_runtime", side_effect=mock_bootstrap_fail):
            # Clear cached imports AND runtime config cache
            if "api.main" in sys.modules:
                del sys.modules["api.main"]
            if "mahoun.core.runtime_config" in sys.modules:
                # Clear lru_cache to pick up new environment variables
                from mahoun.core import runtime_config
                runtime_config.get_runtime_settings.cache_clear()
            
            from api.main import app
            from fastapi.testclient import TestClient
            
            # App startup should fail (RuntimeError should propagate)
            with pytest.raises(RuntimeError, match="Simulated bootstrap failure|MAHOUN bootstrap failed"):
                with TestClient(app):
                    pass
    
    @pytest.mark.integration
    @pytest.mark.p2
    def test_app_fails_on_missing_critical_services(self, monkeypatch):
        """
        CRITICAL: App startup MUST fail if critical services are missing
        
        Verifies fail-fast on incomplete bootstrap
        """
        monkeypatch.setenv("MAHOUN_ENV", "test")
        monkeypatch.setenv("MAHOUN_TESTING", "1")
        monkeypatch.setenv("ENABLE_POSTGRES", "false")
        monkeypatch.setenv("ENABLE_NEO4J", "false")
        monkeypatch.setenv("ENABLE_REDIS", "false")
        monkeypatch.setenv("MAHOUN_GRAPH_BACKEND", "disabled_fallback")
        
        # Mock bootstrap with incomplete registry (missing graph_retriever)
        incomplete_registry = {
            "query": MagicMock(),
            "gnn": MagicMock(),
            # graph_retriever intentionally missing
        }
        
        with patch("mahoun.bootstrap.runtime.bootstrap_runtime", return_value=incomplete_registry):
            # Clear cached imports AND runtime config cache
            if "api.main" in sys.modules:
                del sys.modules["api.main"]
            if "mahoun.core.runtime_config" in sys.modules:
                # Clear lru_cache to pick up new environment variables
                from mahoun.core import runtime_config
                runtime_config.get_runtime_settings.cache_clear()
            
            from api.main import app
            from fastapi.testclient import TestClient
            
            # App startup should fail
            with pytest.raises(RuntimeError, match="Critical services not registered|Missing critical service|failed to register required services"):
                with TestClient(app):
                    pass


@pytest.mark.integration
class TestBootstrapErrorHandling:
    """Test error handling in bootstrap integration"""
    
    @pytest.mark.p2
    def test_adapters_fail_fast_on_missing_registry(self):
        """
        Verify adapters fail-fast when SERVICE_REGISTRY is empty
        
        Test fix for B2+B7: Silent exception catch allowed degradation
        """
        from mahoun.bootstrap.runtime import clear_registry
        
        # Clear registry to simulate missing bootstrap
        clear_registry()
        
        from mahoun.reasoning.adapters import ReasoningDependencyContainer
        
        container = ReasoningDependencyContainer()
        
        # Accessing rag_service should raise RuntimeError (not silent fallback)
        with pytest.raises(RuntimeError, match="graph_retriever not found in SERVICE_REGISTRY"):
            _ = container.rag_service
    
    @pytest.mark.p2
    def test_adapters_fail_fast_on_none_graph_retriever(self):
        """
        Verify adapters fail-fast when graph_retriever is None
        
        Distinguishes "not registered" from "registered but None"
        """
        from mahoun.bootstrap.runtime import register_service
        
        # Register graph_retriever as None (wiring error)
        register_service("graph_retriever", None)
        
        from mahoun.reasoning.adapters import ReasoningDependencyContainer
        
        container = ReasoningDependencyContainer()
        
        # Should raise RuntimeError with specific message about None value
        with pytest.raises(RuntimeError, match="is registered .* but is None"):
            _ = container.rag_service


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
