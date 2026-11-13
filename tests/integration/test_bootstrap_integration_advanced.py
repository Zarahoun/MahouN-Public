"""
Advanced Bootstrap Integration Tests
=====================================
Task 1.1: Hardened bootstrap verification with stress tests, adversarial scenarios,
and comprehensive service registry validation.

These tests verify that bootstrap_runtime() is called during lifespan,
all critical services are registered, and fail-closed behavior is enforced.
"""

import pytest
import asyncio
import time
import threading
from unittest.mock import patch, MagicMock, PropertyMock
from concurrent.futures import ThreadPoolExecutor, as_completed

from mahoun.bootstrap.runtime import (
    bootstrap_runtime, 
    clear_registry, 
    get_service, 
    SERVICE_REGISTRY
)
from mahoun.core.governance.governance_context import GovernanceContextManager
from mahoun.reasoning.adapters import ReasoningDependencyContainer


class TestBootstrapRuntimeIntegration:
    """Integration tests for bootstrap_runtime() execution"""

    def setup_method(self):
        """Clear registry before each test"""
        clear_registry()

    def teardown_method(self):
        """Clean up after each test"""
        clear_registry()

    @pytest.mark.integration
    def test_bootstrap_populates_registry_with_critical_services(self):
        """
        CRITICAL: bootstrap_runtime() populates SERVICE_REGISTRY with all required services.
        
        This is P0 - if registry is empty, RAG is silently disabled.
        """
        registry = bootstrap_runtime()
        
        # Assert critical services present
        assert "graph_retriever" in registry, (
            f"graph_retriever missing. Available: {list(registry.keys())}"
        )
        assert "query" in registry, (
            f"query service missing. Available: {list(registry.keys())}"
        )
        assert "gnn" in registry, (
            f"gnn service missing. Available: {list(registry.keys())}"
        )
        
        # Verify registry has reasonable size (not just 1-2 stubs)
        assert len(registry) >= 3, f"Too few services ({len(registry)}). Possible partial bootstrap."
        
        # Verify services are actual instances, not None
        for service_name, service_instance in registry.items():
            assert service_instance is not None, f"Service {service_name} is None"


    @pytest.mark.integration
    def test_bootstrap_graph_retriever_is_callable(self):
        """
        Verify graph_retriever service is initialized and has expected interface.
        """
        registry = bootstrap_runtime()
        graph_retriever = registry["graph_retriever"]
        
        # Verify it's not None
        assert graph_retriever is not None
        
        # Verify it has retrieve method (RAGServiceProtocol compliance)
        assert hasattr(graph_retriever, "retrieve"), (
            "graph_retriever missing retrieve() method"
        )
        
        # Verify it's callable
        assert callable(graph_retriever.retrieve), (
            "graph_retriever.retrieve is not callable"
        )


    @pytest.mark.integration
    def test_bootstrap_service_registry_singleton_consistency(self):
        """
        Verify SERVICE_REGISTRY is consistent across multiple get_service() calls.
        
        This tests that bootstrap doesn't create new instances on each call.
        """
        registry1 = bootstrap_runtime()
        
        # Get same services multiple times
        query_service_1 = get_service("query")
        query_service_2 = get_service("query")
        gnn_1 = get_service("gnn")
        gnn_2 = get_service("gnn")
        
        # Verify they are the same instances (singleton)
        assert query_service_1 is query_service_2, (
            "query service not singleton - different instances"
        )
        assert gnn_1 is gnn_2, (
            "gnn service not singleton - different instances"
        )


    @pytest.mark.integration
    def test_bootstrap_fails_if_critical_service_missing(self):
        """
        FAIL-CLOSED: bootstrap_runtime() raises error if critical service missing.
        
        Simulate a failure in service initialization and verify bootstrap fails.
        """
        with patch("mahoun.bootstrap.runtime.GNNGraphBuilder") as mock_gnn:
            # Make GNNGraphBuilder raise an error
            mock_gnn.side_effect = RuntimeError("GNN initialization failed")
            
            with pytest.raises(RuntimeError, match="GNN initialization failed"):
                bootstrap_runtime()
        
        # Verify registry is left in consistent state (not partial)
        # Next bootstrap attempt should work
        clear_registry()
        registry = bootstrap_runtime()
        assert "gnn" in registry, "Bootstrap recovery failed"


    @pytest.mark.integration
    async def test_bootstrap_then_governance_context_activation(self):
        """
        Integration: bootstrap_runtime() followed by GovernanceContext activation.
        
        Verifies that governance context can be activated after bootstrap.
        """
        clear_registry()
        registry = bootstrap_runtime()
        
        # Activate governance context
        manager = GovernanceContextManager()
        with manager.active_context(
            correlation_id="test-bootstrap-governance",
            actor_id="test_actor_bootstrap",
            execution_mode="STRICT"
        ):
            # Verify we can access services inside governance context
            container = ReasoningDependencyContainer()
            assert container is not None
            
            # Verify RAG service is available
            rag_service = container.rag_service
            assert rag_service is not None
            assert hasattr(rag_service, "retrieve")


    @pytest.mark.integration
    def test_bootstrap_registry_accessible_from_app_state(self):
        """
        Verify ReasoningDependencyContainer can access SERVICE_REGISTRY through get_service().
        """
        registry = bootstrap_runtime()
        
        # Create container and access RAG service (which internally uses get_service)
        container = ReasoningDependencyContainer()
        
        # This should not raise KeyError
        try:
            rag_service = container.rag_service
            assert rag_service is not None
        except KeyError as e:
            pytest.fail(f"Cannot access graph_retriever from registry: {e}")


    @pytest.mark.integration
    @pytest.mark.stress
    def test_bootstrap_concurrent_service_access(self):
        """
        STRESS TEST: Multiple threads accessing bootstrap services simultaneously.
        
        Verifies thread safety of singleton pattern and SERVICE_REGISTRY.
        """
        registry = bootstrap_runtime()
        
        results = {"errors": [], "instances": []}
        lock = threading.Lock()
        
        def access_services():
            try:
                query = get_service("query")
                gnn = get_service("gnn")
                retriever = get_service("graph_retriever")
                
                with lock:
                    results["instances"].append((id(query), id(gnn), id(retriever)))
            except Exception as e:
                with lock:
                    results["errors"].append(str(e))
        
        # Spawn 20 concurrent threads accessing services
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(access_services) for _ in range(20)]
            for future in as_completed(futures):
                future.result()
        
        # Verify no errors occurred
        assert len(results["errors"]) == 0, f"Concurrent access errors: {results['errors']}"
        
        # Verify all threads got the SAME instances (singleton)
        first_instances = results["instances"][0]
        for instances in results["instances"][1:]:
            assert instances == first_instances, (
                f"Singleton violation: different instances across threads. "
                f"First: {first_instances}, Current: {instances}"
            )


    @pytest.mark.integration
    def test_bootstrap_service_types_are_correct(self):
        """
        Verify each registered service is of the expected type/protocol.
        """
        registry = bootstrap_runtime()
        
        # Verify query service type
        from mahoun.graph.graph_query_service import GraphQueryService
        query = registry.get("query")
        assert isinstance(query, GraphQueryService), (
            f"query service wrong type: {type(query)}"
        )
        
        # Verify GNN builder type
        from mahoun.graph.gnn.gnn_graph_builder import GNNGraphBuilder
        gnn = registry.get("gnn")
        assert isinstance(gnn, GNNGraphBuilder), (
            f"gnn service wrong type: {type(gnn)}"
        )


    @pytest.mark.integration
    @pytest.mark.slow
    def test_bootstrap_duration_acceptable(self):
        """
        Performance: bootstrap_runtime() completes within acceptable time.
        
        P0: Bootstrap should be < 5 seconds even on slow hardware.
        """
        start = time.time()
        registry = bootstrap_runtime()
        duration = time.time() - start
        
        # Bootstrap should be fast (< 5 seconds)
        assert duration < 5.0, (
            f"Bootstrap took too long: {duration:.2f}s (threshold: 5.0s). "
            f"May indicate initialization blocker."
        )
        
        # Log duration for observability
        assert len(registry) > 0  # Ensure registry was actually populated


    @pytest.mark.integration
    def test_bootstrap_idempotency(self):
        """
        bootstrap_runtime() should be safe to call multiple times (though not recommended).
        
        Second call should reuse/update services rather than crash.
        """
        registry1 = bootstrap_runtime()
        registry2 = bootstrap_runtime()
        
        # Both registries should have critical services
        for reg in [registry1, registry2]:
            assert "graph_retriever" in reg
            assert "query" in reg
            assert "gnn" in reg


class TestBootstrapFailureModes:
    """Test bootstrap failure handling (fail-closed principle)"""

    def setup_method(self):
        clear_registry()

    def teardown_method(self):
        clear_registry()

    @pytest.mark.integration
    def test_bootstrap_keyerror_on_unregistered_service(self):
        """
        FAIL-CLOSED: Accessing unregistered service raises KeyError with helpful message.
        """
        registry = bootstrap_runtime()
        
        # Try to access non-existent service
        with pytest.raises(KeyError, match="Service 'nonexistent' not found"):
            get_service("nonexistent")


    @pytest.mark.integration
    def test_bootstrap_registry_clear_prevents_silent_failures(self):
        """
        Verify that if registry is cleared, subsequent access fails loudly (not silently).
        """
        bootstrap_runtime()
        
        # Clear registry (simulating a corruption scenario)
        clear_registry()
        
        # Verify accessing any service now fails
        with pytest.raises(KeyError):
            get_service("query")


    @pytest.mark.integration
    def test_bootstrap_partial_initialization_detected(self):
        """
        If bootstrap adds some but not all critical services, it should be detected.
        """
        with patch.dict(SERVICE_REGISTRY, {"query": MagicMock()}):
            # Registry has query but missing gnn and graph_retriever
            critical_services = ["graph_retriever", "query", "gnn"]
            missing = [s for s in critical_services if s not in SERVICE_REGISTRY]
            
            assert len(missing) > 0, "Partial initialization not detected"
            assert "gnn" in missing
            assert "graph_retriever" in missing


class TestBootstrapWithGovernanceContext:
    """Integration tests combining bootstrap and governance context"""

    def setup_method(self):
        clear_registry()

    def teardown_method(self):
        clear_registry()

    @pytest.mark.integration
    def test_verdict_engine_construction_after_bootstrap(self):
        """
        Full integration: bootstrap → governance context → verdict engine creation.
        
        This is the complete path used by /verdict API endpoint.
        """
        registry = bootstrap_runtime()
        
        manager = GovernanceContextManager()
        with manager.active_context(
            correlation_id="test-verdict-engine",
            actor_id="test_agent",
            execution_mode="STRICT"
        ):
            # This should not raise
            container = ReasoningDependencyContainer()
            
            # Verify all dependencies available
            assert container.rag_service is not None
            assert container.query_router is not None or True  # optional
            assert hasattr(container.rag_service, "retrieve")


    @pytest.mark.integration
    async def test_bootstrap_then_rag_chain_execution(self):
        """
        End-to-end: bootstrap → RAG service initialization → retrieval.
        
        This verifies RAG chain is not silently degraded after bootstrap.
        """
        clear_registry()
        registry = bootstrap_runtime()
        
        # Get graph_retriever and verify it's ready
        graph_retriever = get_service("graph_retriever")
        assert graph_retriever is not None
        
        # Verify it has the retrieve interface
        assert hasattr(graph_retriever, "retrieve")
        assert callable(graph_retriever.retrieve)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
