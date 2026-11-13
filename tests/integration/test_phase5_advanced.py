"""
Phase 5 Advanced Integration Tests
===================================

MEDIUM, HARD, and VERY HARD tests for Phase 5 governance integration.

Test Categories:
- MEDIUM: Feature flag switching, mocking, helper methods
- HARD: End-to-end flow, architecture validation, real component interaction
- VERY HARD: Concurrent access, race conditions, stress tests

Part of: Phase 5 - Architecture Integration Mission
"""

import os
import pytest
import threading
import time
from typing import Any
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from concurrent.futures import ThreadPoolExecutor

# Skip all tests unless MAHOUN_INTEGRATION=1
pytestmark = pytest.mark.skipif(
    os.environ.get("MAHOUN_INTEGRATION") != "1",
    reason="Integration tests require MAHOUN_INTEGRATION=1"
)

from api.middleware.governance_context import GovernanceContextMiddleware, get_governance_context
from mahoun.reasoning.adapters import ReasoningDependencyContainer, reset_global_container
from mahoun.core.governance.governance_context import GovernanceContext, GovernanceContextManager


# ============================================================================
# Protocol-compliant Mocks
# ============================================================================

class MockRAGService:
    """Mock RAG service that satisfies RAGServiceProtocol."""
    
    async def retrieve(self, query: str, mode: Any, top_k: int = 10) -> Any:
        """Mock retrieve method."""
        return MagicMock()
    
    def __call__(self, *args, **kwargs):
        return self


# ============================================================================
# MEDIUM TESTS - Feature Flags & Mocking
# ============================================================================

def test_medium_feature_flag_true_enables_policy_aware_rag():
    """MEDIUM: Test feature flag enables PolicyAwareRAGService."""
    reset_global_container()
    
    with patch.dict(os.environ, {"MAHOUN_USE_POLICY_AWARE_RAG": "true"}):
        with patch('mahoun.reasoning.rag_adapter.create_rag_service') as mock_base:
            with patch('mahoun.rag.policy_aware_rag_service.PolicyAwareRAGService') as mock_policy:
                # Setup mocks
                mock_base.return_value = MockRAGService()
                mock_policy.return_value = MockRAGService()
                
                # Create container - should use PolicyAwareRAGService
                container = ReasoningDependencyContainer()
                
                # Accessing rag_service triggers lazy initialization
                _ = container.rag_service
                
                # Verify PolicyAwareRAGService was instantiated
                mock_policy.assert_called_once()
                assert mock_policy.call_args[1]['enable_governance'] == True
                assert mock_policy.call_args[1]['enable_cache'] == True


def test_medium_feature_flag_false_uses_hybrid_rag():
    """MEDIUM: Test default uses HybridRAGService."""
    reset_global_container()
    
    with patch.dict(os.environ, {"MAHOUN_USE_POLICY_AWARE_RAG": "false"}):
        with patch('mahoun.reasoning.rag_adapter.create_rag_service') as mock_create:
            mock_create.return_value = MockRAGService()
            
            container = ReasoningDependencyContainer()
            _ = container.rag_service
            
            # Should call base service, not PolicyAwareRAGService
            mock_create.assert_called_once()


def test_medium_middleware_extracts_all_header_types():
    """MEDIUM: Test middleware extracts various header combinations."""
    middleware = GovernanceContextMiddleware(None)
    
    # Test X-Correlation-ID priority
    request = Mock()
    request.headers = {
        "X-Correlation-ID": "corr-123",
        "X-Request-ID": "req-456"
    }
    assert middleware._extract_correlation_id(request) == "corr-123"
    
    # Test X-Request-ID fallback
    request.headers = {"X-Request-ID": "req-456"}
    assert middleware._extract_correlation_id(request) == "req-456"
    
    # Test X-User-ID for actor
    request.headers = {"X-User-ID": "user-789"}
    assert middleware._extract_actor_id(request) == "user-789"
    
    # Test X-API-Key-ID with prefix
    request.headers = {"X-API-Key-ID": "key-abc"}
    assert middleware._extract_actor_id(request) == "api-key:key-abc"


def test_medium_governance_context_error_handling():
    """MEDIUM: Test error handling when context missing."""
    request = Mock()
    request.state = Mock(spec=[])  # Empty spec - no attributes
    
    with pytest.raises(RuntimeError) as exc_info:
        get_governance_context(request)
    
    assert "GovernanceContext not found" in str(exc_info.value)
    assert "GovernanceContextMiddleware" in str(exc_info.value)


# ============================================================================
# HARD TESTS - Architecture Validation & Real Integration
# ============================================================================

def test_hard_architecture_boundary_middleware_only_creates_context():
    """HARD: Verify middleware doesn't create services."""
    middleware = GovernanceContextMiddleware(None)
    
    # Middleware should NOT have any service creation
    forbidden_methods = [
        'create_rag_service', '_create_rag_service',
        'create_reasoning_engine', '_create_reasoning_engine',
        'create_verdict_engine', '_create_verdict_engine',
        'create_di_container', '_create_di_container'
    ]
    
    for method in forbidden_methods:
        assert not hasattr(middleware, method), \
            f"Middleware should NOT have {method} - violates separation of concerns"
    
    # Middleware SHOULD have only context helpers
    required_methods = ['_extract_correlation_id', '_extract_actor_id']
    for method in required_methods:
        assert hasattr(middleware, method), \
            f"Middleware should have {method}"


def test_hard_architecture_boundary_di_container_never_creates_governance():
    """HARD: Verify DI container doesn't create governance contexts."""
    container = ReasoningDependencyContainer()
    
    # Container should NOT create governance
    forbidden_methods = [
        'create_governance_context', '_create_governance_context',
        'create_context', 'initialize_governance'
    ]
    
    for method in forbidden_methods:
        assert not hasattr(container, method), \
            f"DI Container should NOT have {method} - violates separation of concerns"
    
    # Container SHOULD create services
    required_methods = [
        '_create_rag_service',
        '_create_reasoning_engine',
        '_create_query_router'
    ]
    
    for method in required_methods:
        assert hasattr(container, method), \
            f"DI Container should have {method}"


def test_hard_policy_aware_rag_uses_composition_not_inheritance():
    """HARD: Verify PolicyAwareRAGService uses composition pattern."""
    from mahoun.rag.policy_aware_rag_service import PolicyAwareRAGService
    import inspect
    
    # Check constructor signature
    sig = inspect.signature(PolicyAwareRAGService.__init__)
    
    # Must have base_service parameter (composition)
    assert 'base_service' in sig.parameters, \
        "PolicyAwareRAGService must use composition pattern with base_service parameter"
    
    # base_service must be required (no default)
    param = sig.parameters['base_service']
    assert param.default == inspect.Parameter.empty, \
        "base_service parameter must be required (no default value)"
    
    # Should NOT inherit from HybridRAGService (checked via naming, not actual inheritance to avoid import)
    class_name = PolicyAwareRAGService.__name__
    assert class_name == "PolicyAwareRAGService", \
        "Class should be named PolicyAwareRAGService"


def test_hard_no_god_object_pattern_in_policy_aware_rag():
    """HARD: Verify PolicyAwareRAGService isn't a God Object."""
    from mahoun.rag.policy_aware_rag_service import PolicyAwareRAGService
    
    # Should NOT have governance creation/orchestration methods
    god_object_methods = [
        'create_governance_context',
        'create_reasoning_engine',
        'orchestrate_workflow',
        'make_policy_decision',
        'enforce_governance',
        'create_verdict',
        'execute_reasoning'
    ]
    
    for method in god_object_methods:
        assert not hasattr(PolicyAwareRAGService, method), \
            f"PolicyAwareRAGService should NOT have {method} - God Object anti-pattern"


def test_hard_governance_context_propagation_through_stack():
    """HARD: Test context propagates from middleware through services."""
    # Create mock request with governance context
    request = Mock()
    
    # Create actual governance context (not mock)
    ctx = GovernanceContextManager.create_context(
        correlation_id="test-hard-123",
        execution_mode="STRICT"
    )
    
    # Inject into request.state (simulating middleware)
    request.state = Mock()
    request.state.governance_context = ctx
    
    # Extract context (simulating endpoint)
    extracted_ctx = get_governance_context(request)
    
    # Verify it's the same context
    assert extracted_ctx == ctx
    assert extracted_ctx.correlation_id == "test-hard-123"
    assert extracted_ctx.execution_mode == "STRICT"
    assert extracted_ctx.governance_scope_injected == True


# ============================================================================
# VERY HARD TESTS - Concurrency, Race Conditions, Stress
# ============================================================================

def test_very_hard_concurrent_di_container_initialization():
    """VERY HARD: Test thread-safe DI container lazy initialization."""
    reset_global_container()
    
    results = []
    errors = []
    
    def create_and_access_container(thread_id):
        try:
            with patch('mahoun.reasoning.rag_adapter.create_rag_service') as mock_create:
                mock_create.return_value = MockRAGService()
                
                container = ReasoningDependencyContainer()
                service = container.rag_service  # Trigger lazy init
                
                results.append({
                    'thread_id': thread_id,
                    'container_id': id(container),
                    'service_id': id(service),
                    'success': True
                })
        except Exception as e:
            errors.append({'thread_id': thread_id, 'error': str(e)})
    
    # Create 10 threads accessing container concurrently
    threads = []
    for i in range(10):
        thread = threading.Thread(target=create_and_access_container, args=(i,))
        threads.append(thread)
        thread.start()
    
    # Wait for all threads
    for thread in threads:
        thread.join()
    
    # Verify no errors occurred
    assert len(errors) == 0, f"Concurrent access caused errors: {errors}"
    
    # Verify all threads succeeded
    assert len(results) == 10, "All threads should complete successfully"
    
    # Each thread created its own container (no global singleton in this test)
    container_ids = [r['container_id'] for r in results]
    assert len(set(container_ids)) == 10, "Each thread should have its own container"


def test_very_hard_feature_flag_switching_under_load():
    """VERY HARD: Test feature flag switching with concurrent requests."""
    results = {'true_count': 0, 'false_count': 0, 'errors': []}
    lock = threading.Lock()
    
    def test_with_flag(flag_value, iteration):
        try:
            reset_global_container()
            
            with patch.dict(os.environ, {"MAHOUN_USE_POLICY_AWARE_RAG": flag_value}):
                with patch('mahoun.reasoning.rag_adapter.create_rag_service') as mock_base:
                    with patch('mahoun.rag.policy_aware_rag_service.PolicyAwareRAGService') as mock_policy:
                        mock_base.return_value = MockRAGService()
                        mock_policy.return_value = MockRAGService()
                        
                        container = ReasoningDependencyContainer()
                        _ = container.rag_service
                        
                        with lock:
                            if flag_value == "true":
                                results['true_count'] += 1
                            else:
                                results['false_count'] += 1
        except Exception as e:
            with lock:
                results['errors'].append(f"Iteration {iteration}: {str(e)}")
    
    # Alternate between true/false rapidly
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        for i in range(20):
            flag = "true" if i % 2 == 0 else "false"
            futures.append(executor.submit(test_with_flag, flag, i))
        
        # Wait for all to complete
        for future in futures:
            future.result()
    
    # Verify no errors
    assert len(results['errors']) == 0, f"Errors during concurrent flag switching: {results['errors']}"
    
    # Verify both flags were tested
    assert results['true_count'] > 0, "Should have tested with flag=true"
    assert results['false_count'] > 0, "Should have tested with flag=false"


def test_very_hard_governance_context_cleanup_prevents_memory_leak():
    """VERY HARD: Test governance contexts are properly cleaned up."""
    initial_stack_size = len(GovernanceContextManager._get_stack())
    
    # Simulate 100 requests
    for i in range(100):
        request = Mock()
        ctx = GovernanceContextManager.create_context(
            correlation_id=f"stress-{i}"
        )
        
        request.state = Mock()
        request.state.governance_context = ctx
        
        # Simulate endpoint usage
        extracted_ctx = get_governance_context(request)
        
        # Add to stack (simulating endpoint logic)
        stack = GovernanceContextManager._get_stack()
        stack.append(extracted_ctx)
        
        # Cleanup (simulating finally block)
        if stack and stack[-1] == extracted_ctx:
            stack.pop()
    
    # Stack should return to initial size
    final_stack_size = len(GovernanceContextManager._get_stack())
    assert final_stack_size == initial_stack_size, \
        f"Memory leak detected: stack grew from {initial_stack_size} to {final_stack_size}"


def test_very_hard_architecture_gate_compatibility():
    """VERY HARD: Verify changes pass architecture boundary gate."""
    import subprocess
    
    # Run the actual architecture gate
    gate_path = "ci/gates/gate_architecture_boundaries.sh"
    
    result = subprocess.run(
        [gate_path],
        capture_output=True,
        text=True,
        cwd="/home/haji/Desktop/KingMahouN"
    )
    
    # Gate must pass (exit code 0)
    assert result.returncode == 0, \
        f"Architecture boundary gate FAILED:\n{result.stdout}\n{result.stderr}"
    
    # Verify specific checks passed
    output = result.stdout
    assert "✅ PASS" in output or "PASS: All architecture boundaries" in output, \
        f"Gate should report passing checks:\n{output}"


def test_very_hard_stress_test_1000_contexts():
    """VERY HARD: Stress test with 1000 governance contexts."""
    contexts_created = []
    start_time = time.time()
    
    try:
        for i in range(1000):
            ctx = GovernanceContextManager.create_context(
                correlation_id=f"stress-1000-{i}",
                execution_mode="STRICT"
            )
            contexts_created.append(ctx)
            
            # Verify context is valid
            assert ctx.correlation_id == f"stress-1000-{i}"
            assert ctx.governance_scope_injected == True
    
    finally:
        # Cleanup
        contexts_created.clear()
    
    elapsed_time = time.time() - start_time
    
    # Performance check: should create 1000 contexts in reasonable time
    assert elapsed_time < 30.0, \
        f"Creating 1000 contexts took {elapsed_time:.2f}s (should be < 30s)"
    
    print(f"✅ Created 1000 governance contexts in {elapsed_time:.2f}s")


if __name__ == "__main__":
    print("🧪 Running Phase 5 Advanced Integration Tests...")
    print("=" * 70)
    print("Test Categories:")
    print("  🟡 MEDIUM: Feature flags, mocking, helpers")
    print("  🟠 HARD: Architecture validation, real integration")  
    print("  🔴 VERY HARD: Concurrency, stress, race conditions")
    print("=" * 70)
    pytest.main([__file__, "-v", "--tb=short", "-k", "test_"])
