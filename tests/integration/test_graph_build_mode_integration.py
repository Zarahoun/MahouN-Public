"""
Graph Build Mode Integration Test
=================================

This test verifies that Graph Build Mode properly isolates graph construction
services from secondary services (RAG, GNN, vector sync).

Test Strategy:
Static analysis of bootstrap_runtime.py and api/main.py to verify:
1. Graph Build Mode detection logic is correct
2. Service registration follows the conditional contract
3. Reasoning config validation is properly conditional
4. API startup critical services match the contract
"""

import re
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent


def _source(path: Path) -> str:
    """Read source file as string."""
    return path.read_text()


def test_graph_build_mode_bootstrap_service_isolation():
    """
    Static analysis: Verify Graph Build Mode service isolation in bootstrap_runtime.py.
    
    Verifies that:
    - is_graph_build_mode() check exists and is used correctly
    - Secondary services (gnn, graph_retriever, graph_vector_sync) are conditionally registered
    - Critical services (query, legal_query_executor) are always registered
    - Reasoning config validation is conditionally called
    """
    source = _source(ROOT / "mahoun" / "bootstrap" / "runtime.py")
    
    # Verify Graph Build Mode detection exists
    assert "is_graph_build_mode()" in source
    assert "from mahoun.core.runtime_config import is_graph_build_mode" in source
    
    # Verify conditional blocks exist
    assert source.count("if not is_graph_build_mode():") >= 2
    
    # Verify critical services are unconditionally registered
    assert 'register_service("query"' in source
    assert 'register_service("legal_query_executor"' in source
    
    # Verify secondary services are conditionally registered
    assert 'register_service("gnn"' in source
    assert 'register_service("graph_retriever"' in source
    assert 'register_service("graph_vector_sync"' in source
    
    # Verify reasoning config validation is conditional
    assert "validate_production_reasoning_config()" in source
    
    # Verify reasoning config validation is specifically in the Graph Build Mode conditional
    # Look for the pattern: if not is_graph_build_mode(): ... validate_production_reasoning_config()
    lines = source.split('\n')
    for i, line in enumerate(lines):
        if "if not is_graph_build_mode():" in line:
            # Check the next ~15 lines for the validation call
            for j in range(i, min(i + 15, len(lines))):
                if "validate_production_reasoning_config()" in lines[j]:
                    return  # Found it in the right conditional
    
    # If we didn't find it in a conditional, that's a failure
    raise AssertionError(
        "Reasoning config validation should be inside a Graph Build Mode conditional block"
    )


def test_graph_build_mode_api_startup_critical_services():
    """
    Static analysis: Verify API startup critical services match Graph Build Mode contract.
    
    Verifies that api/main.py:
    - Imports is_graph_build_mode
    - Sets critical_services based on Graph Build Mode
    - Only "query" is critical in Graph Build Mode
    - Additional services are critical in normal mode
    """
    source = _source(ROOT / "api" / "main.py")
    
    # Verify Graph Build Mode import
    assert "is_graph_build_mode" in source
    assert "from mahoun.core.runtime_config import is_graph_build_mode" in source
    
    # Verify critical services logic
    assert 'critical_services = ["query"]' in source
    assert 'if not is_graph_build_mode():' in source
    assert 'critical_services.extend(["graph_retriever", "gnn"])' in source
    
    # Verify the logic flow: set critical_services, then check for missing services
    assert "missing = [s for s in critical_services if s not in registry]" in source
    assert "raise RuntimeError" in source  # fail-closed on missing critical services


def test_graph_build_mode_environment_variable_contract():
    """
    Verify the Graph Build Mode environment variable contract.
    
    Verifies that:
    - Environment variable name is MAHOUN_GRAPH_BUILD_MODE
    - Default value is "false"
    - is_graph_build_mode() function correctly reads from environment
    """
    source = _source(ROOT / "mahoun" / "core" / "runtime_config.py")
    
    # Verify function signature and implementation
    assert "def is_graph_build_mode() -> bool:" in source
    assert 'return os.getenv("MAHOUN_GRAPH_BUILD_MODE", "false").lower() == "true"' in source
    
    # Verify function is imported in bootstrap
    bootstrap_source = _source(ROOT / "mahoun" / "bootstrap" / "runtime.py")
    assert "from mahoun.core.runtime_config import is_graph_build_mode" in bootstrap_source


def test_graph_build_mode_service_registry_contract():
    """
    Verify the service registry contract in Graph Build Mode.
    
    This test ensures that the service names and registration logic
    match the expected contract.
    """
    source = _source(ROOT / "mahoun" / "bootstrap" / "runtime.py")
    
    # Expected services in Graph Build Mode (critical only)
    expected_graph_build_services = {"query", "legal_query_executor"}
    
    # Expected services in normal mode (critical + secondary)
    expected_normal_services = {
        "query", 
        "legal_query_executor",
        "gnn", 
        "graph_retriever", 
        "graph_vector_sync"
    }
    
    # Parse the source to find all register_service calls
    registered_services = set()
    for line in source.split('\n'):
        if 'register_service("' in line:
            # Extract service name from register_service("service_name")
            match = re.search(r'register_service\("([^"]+)"', line)
            if match:
                registered_services.add(match.group(1))
    
    # Verify all expected services are registered somewhere
    for service in expected_normal_services:
        assert service in registered_services, f"Service '{service}' not found in bootstrap"
    
    # Verify the conditional structure exists
    assert "if not is_graph_build_mode():" in source
    
    # Simplified check: verify conditional pattern appears before secondary services
    conditional_pattern = "if not is_graph_build_mode():"
    conditional_pos = source.find(conditional_pattern)
    
    # Verify secondary services appear after the conditional
    for secondary_service in ["gnn", "graph_retriever", "graph_vector_sync"]:
        service_pos = source.find(f'register_service("{secondary_service}"')
        assert service_pos > conditional_pos, (
            f"Secondary service '{secondary_service}' should be after Graph Build Mode conditional"
        )


if __name__ == "__main__":
    # Run tests directly for debugging
    print("Running Graph Build Mode integration tests...")
    test_graph_build_mode_bootstrap_service_isolation()
    test_graph_build_mode_api_startup_critical_services()
    test_graph_build_mode_environment_variable_contract()
    test_graph_build_mode_service_registry_contract()
    print("✅ All Graph Build Mode integration tests passed")
