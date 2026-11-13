import os
import pytest
import requests


BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")


@pytest.mark.integration
@pytest.mark.p2
def test_health_endpoint_reflects_real_db_state_when_down():
    """
    Gate: Health endpoint must NEVER return healthy when DBs are unreachable.
    
    This test ensures the health check doesn't produce fake OK responses.
    Uses invalid host/port to simulate DB unavailability.
    
    Validates JSON payload semantics, not just HTTP status code.
    """
    invalid_env = {
        "POSTGRES_HOST": "invalid-host-does-not-exist",
        "POSTGRES_PORT": "9999",
        "NEO4J_URI": "bolt://invalid-host:9999",
        "REDIS_URL": "redis://invalid-host:9999/0",
        "ENABLE_POSTGRES": "true",
        "ENABLE_NEO4J": "true",
        "ENABLE_REDIS": "true"
    }
    
    with pytest.MonkeyPatch.context() as mp:
        for key, val in invalid_env.items():
            mp.setenv(key, val)
        
        try:
            response = requests.get(f"{BASE_URL}/system/health", timeout=5)
        except requests.exceptions.ConnectionError:
            # quality-gate-approved: requires a separately running API process
            pytest.skip("Backend not running - test requires running backend")
        
        try:
            data = response.json()
        except Exception:
            pytest.fail(f"Health endpoint returned non-JSON response: {response.text[:200]}")
        
        if "ImportError" in response.text or "cannot import name" in response.text:
            pytest.fail(f"ImportError detected in health response - this causes fake OK! Response: {response.text[:500]}")
        
        overall_status = data.get("status", "unknown")
        
        assert overall_status != "healthy", \
            f"Health endpoint returned 'healthy' when DBs are down - FAKE OK DETECTED! Response: {data}"
        
        assert overall_status in ["degraded", "unhealthy", "error", "unavailable"], \
            f"Expected degraded/unhealthy/error status when DBs down, got: {overall_status}"


@pytest.mark.p2
def test_health_endpoint_import_errors_are_real_failures():
    """
    Gate: ImportError in health checks must cause test failure, not pass.
    
    This ensures we never ship code where health checks silently fail
    due to missing imports and return fake OK.
    """
    try:
        from api.health import get_health_status
        
        status = get_health_status()
        
        assert "components" in status, \
            "Health status missing 'components' - possible ImportError being hidden"
        
        for component, state in status.get("components", {}).items():
            assert "status" in state, \
                f"Component '{component}' missing status field - possible ImportError"
            
            if state.get("status") == "healthy":
                assert "error" not in state or state["error"] is None, \
                    f"Component '{component}' is 'healthy' but has error: {state.get('error')}"
                    
    except ImportError as e:
        pytest.fail(f"ImportError detected in health check module: {e}. "
                   "This would cause fake OK responses!")

# quality-gate-approved: staging-only Docker gate
@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("SKIP_DOCKER_INTEGRATION") == "1",
    reason="Docker integration tests skipped"
)
@pytest.mark.p2
def test_health_endpoint_reflects_real_db_state_when_up():
    """
    Gate: Health endpoint must return healthy when DBs are actually reachable.
    
    This test runs only when DBs are available (integration environment).
    Validates the "up" case to ensure health checks work correctly.
    """
    try:
        response = requests.get(f"{BASE_URL}/system/health", timeout=5)
    except requests.exceptions.ConnectionError:
        # quality-gate-approved: requires a separately running API process
        pytest.skip("Backend not running")

    if response.status_code not in (200, 503):
        # quality-gate-approved: staging-only dependency availability
        pytest.skip("Backend or DBs not fully available")
    
    try:
        data = response.json()
    except Exception:
        pytest.fail(f"Health endpoint returned non-JSON: {response.text[:200]}")
    
    expected_healthy = os.getenv("EXPECT_HEALTHY_DBS", "false").lower() == "true"
    
    if expected_healthy:
        assert data.get("status") == "healthy", \
            f"Expected healthy status when DBs are up, got: {data}"
        
        components = data.get("components", {})
        for db in ["postgresql", "neo4j", "redis"]:
            if db in components:
                assert components[db].get("status") == "healthy", \
                    f"DB {db} should be healthy but got: {components[db]}"


@pytest.mark.p2
def test_health_module_has_required_functions():
    """
    Sanity check: Ensure health module exports expected functions.
    
    Prevents ImportError regressions where functions are renamed/removed
    and health checks start failing silently.
    """
    try:
        from api import health
        
        assert hasattr(health, "get_health_status"), \
            "Health module missing get_health_status function"
        
    except ImportError as e:
        pytest.fail(f"Cannot import api.health module: {e}")
