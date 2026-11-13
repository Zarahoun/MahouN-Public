"""
Phase 5 Simple Integration Tests
=================================

Simple, fast tests - function-based for better pytest discovery.
NO NEW CLASSES - only imports and tests existing code.

Part of: Phase 5 - Architecture Integration Mission
"""

import os
import pytest
from unittest.mock import Mock, patch

# Import existing classes - NO duplicates created
from api.middleware.governance_context import GovernanceContextMiddleware, get_governance_context
from mahoun.reasoning.adapters import ReasoningDependencyContainer
from mahoun.core.governance.governance_context import GovernanceContext


# ==== SIMPLE TESTS ====

def test_extract_correlation_id_from_x_correlation_header():
    """SIMPLE: Test X-Correlation-ID extraction."""
    middleware = GovernanceContextMiddleware(None)
    request = Mock()
    request.headers = {"X-Correlation-ID": "test-corr-123"}
    
    result = middleware._extract_correlation_id(request)
    assert result == "test-corr-123"


def test_extract_actor_id_from_user_header():
    """SIMPLE: Test X-User-ID extraction."""
    middleware = GovernanceContextMiddleware(None)
    request = Mock()
    request.headers = {"X-User-ID": "user-789"}
    
    result = middleware._extract_actor_id(request)
    assert result == "user-789"


def test_feature_flag_default_is_false():
    """SIMPLE: Test default feature flag value."""
    flag_value = os.getenv("MAHOUN_USE_POLICY_AWARE_RAG", "false")
    assert flag_value == "false"


def test_di_container_creation_succeeds():
    """SIMPLE: Test DI container can be created."""
    container = ReasoningDependencyContainer()
    assert container is not None
    assert hasattr(container, 'rag_service')


def test_middleware_has_no_service_creation_methods():
    """SIMPLE: Verify middleware doesn't create services."""
    middleware = GovernanceContextMiddleware(None)
    
    # Should NOT have service creation
    assert not hasattr(middleware, 'create_rag_service')
    assert not hasattr(middleware, '_create_rag_service')
    
    # SHOULD have context helpers only
    assert hasattr(middleware, '_extract_correlation_id')


def test_policy_aware_rag_uses_composition_pattern():
    """SIMPLE: Verify PolicyAwareRAGService takes base_service param."""
    from mahoun.rag.policy_aware_rag_service import PolicyAwareRAGService
    import inspect
    
    sig = inspect.signature(PolicyAwareRAGService.__init__)
    assert 'base_service' in sig.parameters
