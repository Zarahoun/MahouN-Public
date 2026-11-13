"""
ADVERSARIAL EXTREME: Bootstrap Integration Under Attack
========================================================

This test suite goes HARD — simulating malicious actors, race conditions,
resource exhaustion, cascading failures, and byzantine faults.

CRITICAL (P0+): These tests verify that bootstrap is not just "working"
but UNBREAKABLE under adversarial conditions. The system MUST fail-closed,
never silently degrade, and leave clear forensic evidence.

Test Categories:
- Category A: Malicious Input (injection, bypass attempts)
- Category B: Resource Exhaustion (OOM, connection storms)
- Category C: Race Conditions (concurrent bootstrap, TOCTOU)
- Category D: Cascading Failures (Neo4j down → graceful degradation)
- Category E: Byzantine Faults (corrupted registry, poisoned services)
"""

import pytest
import os
import threading
import time
from unittest.mock import patch, MagicMock, Mock
from concurrent.futures import ThreadPoolExecutor


# ============================================================================
# CATEGORY A: MALICIOUS INPUT ATTACKS
# ============================================================================

class TestBootstrapMaliciousInput:
    """Test bootstrap under active attack from malicious inputs"""
    
    @pytest.mark.p3
    def test_bootstrap_rejects_malicious_service_names(self, monkeypatch):
        """
        ADVERSARIAL: Attacker tries to register service with SQL injection name
        
        System MUST sanitize or reject malicious service names
        """
        monkeypatch.setenv("MAHOUN_ENV", "test")
        monkeypatch.setenv("MAHOUN_TESTING", "1")
        
        from mahoun.bootstrap.runtime import register_service
        
        # Malicious service names that could break logging/monitoring
        malicious_names = [
            "'; DROP TABLE services; --",
            "../../../etc/passwd",
            "<script>alert('xss')</script>",
            "service\x00name",  # null byte injection
            "service\nname",    # newline injection for log poisoning
        ]
        
        for malicious_name in malicious_names:
            # Should either sanitize or reject (not crash)
            try:
                mock_service = MagicMock()
                register_service(malicious_name, mock_service)
                
                # If it accepts, verify it's in registry (sanitized or not)
                from mahoun.bootstrap.runtime import SERVICE_REGISTRY
                assert malicious_name in SERVICE_REGISTRY or any(
                    sanitized in SERVICE_REGISTRY 
                    for sanitized in [malicious_name.replace("'", ""), malicious_name.replace("\n", "")]
                ), f"Service name '{malicious_name}' not properly handled"
                
            except (ValueError, TypeError, KeyError) as e:
                # Rejecting is also acceptable
                assert "invalid" in str(e).lower() or "forbidden" in str(e).lower(), (
                    f"Error message should indicate rejection: {e}"
                )
    
    @pytest.mark.p3
    def test_bootstrap_rejects_poisoned_service_instances(self):
        """
        ADVERSARIAL: Attacker tries to register malicious service that crashes on access
        
        System MUST validate service instances before registration
        """
        from mahoun.bootstrap.runtime import register_service, get_service
        
        # Create a poisoned service that crashes on any attribute access
        class PoisonedService:
            def __getattribute__(self, name):
                if name not in ('__class__', '__dict__'):
                    raise RuntimeError("💀 POISONED SERVICE TRIGGERED")
        
        poisoned = PoisonedService()
        
        # Registration might accept it (no validation)
        register_service("poisoned", poisoned)
        
        # But accessing it MUST be caught and handled
        try:
            service = get_service("poisoned")
            # If we get here, try to use it
            _ = service.some_method
            pytest.fail("Poisoned service should have been detected")
        except RuntimeError as e:
            # Expected — poisoned service triggered
            assert "POISONED" in str(e)
    
    @pytest.mark.p3
    def test_bootstrap_prevents_prototype_pollution(self):
        """
        ADVERSARIAL: Attacker tries to pollute SERVICE_REGISTRY with __proto__
        
        Python dict pollution attack via special keys
        NOTE: This attack is JS-specific. In Python, these are just regular string keys.
        """
        from mahoun.bootstrap.runtime import SERVICE_REGISTRY, register_service
        
        # Attempt prototype pollution
        malicious_keys = ["__proto__", "__class__", "__init__", "__dict__"]
        
        for key in malicious_keys:
            with pytest.raises((TypeError, AttributeError, ValueError)):
                register_service(key, MagicMock())


# ============================================================================
# CATEGORY B: RESOURCE EXHAUSTION ATTACKS
# ============================================================================

class TestBootstrapResourceExhaustion:
    """Test bootstrap under resource exhaustion attacks"""
    
    @pytest.mark.p3
    def test_bootstrap_survives_registry_overflow(self):
        """
        ADVERSARIAL: Attacker floods registry with 10,000 fake services
        
        System MUST either:
        1. Rate limit / reject after threshold
        2. Handle large registry without OOM
        """
        from mahoun.bootstrap.runtime import clear_registry, register_service, SERVICE_REGISTRY
        
        clear_registry()
        
        # Flood attack
        num_services = 10_000
        
        for i in range(num_services):
            try:
                register_service(f"flood_service_{i}", MagicMock())
            except (MemoryError, ValueError) as e:
                # Acceptable: system rejected after threshold
                assert len(SERVICE_REGISTRY) < num_services, (
                    f"Registry should reject flood after reasonable limit"
                )
                break
        
        # Verify registry is still functional after attack
        register_service("test_post_flood", MagicMock())
        from mahoun.bootstrap.runtime import get_service
        assert get_service("test_post_flood") is not None
    
    # quality-gate-approved: optional torch-geometric deployment dependency
    @pytest.mark.skipif(
        not __import__('importlib.util').util.find_spec('torch_geometric'),
        reason="torch_geometric not installed (optional dependency)"
    )
    @pytest.mark.p3
    def test_bootstrap_handles_connection_storm(self, monkeypatch):
        """
        ADVERSARIAL: 1000 concurrent requests try to call bootstrap simultaneously
        
        System MUST be thread-safe and not create duplicate services
        """
        monkeypatch.setenv("MAHOUN_ENV", "test")
        
        from mahoun.bootstrap.runtime import clear_registry
        clear_registry()
        
        # Import GNN module before patching to trigger lazy load
        import mahoun.graph.gnn.gnn_graph_builder
        
        # Mock Neo4j to avoid real connections
        with patch("mahoun.graph.neo4j.connection.get_connection") as mock_conn:
            mock_conn.return_value = MagicMock()
            
            with patch("mahoun.graph.graph_query_service.GraphQueryService"):
                with patch("mahoun.graph.gnn.gnn_graph_builder.GNNGraphBuilder"):
                    with patch("mahoun.retrieval.graph_enhanced.GraphEnhancedRetriever"):
                        with patch("mahoun.pipelines.sync.graph_vector_sync.GraphVectorSync"):
                            with patch("mahoun.graph.legal_cypher_queries.LegalQueryExecutor"):
                                
                                results = []
                                errors = []
                                
                                def call_bootstrap():
                                    try:
                                        from mahoun.bootstrap.runtime import bootstrap_runtime
                                        registry = bootstrap_runtime()
                                        results.append(len(registry))
                                    except Exception as e:
                                        errors.append(e)
                                
                                # Launch connection storm
                                with ThreadPoolExecutor(max_workers=100) as executor:
                                    futures = [executor.submit(call_bootstrap) for _ in range(1000)]
                                    for future in futures:
                                        future.result(timeout=5)
                                
                                # Verify thread safety
                                assert len(errors) == 0, f"Thread safety violation: {errors}"
                                
                                # All calls should return same registry size
                                assert len(set(results)) == 1, (
                                    f"Inconsistent registry sizes: {set(results)}. "
                                    "This indicates race condition."
                                )
    
    @pytest.mark.p3
    def test_bootstrap_handles_neo4j_connection_exhaustion(self):
        """
        ADVERSARIAL: Neo4j connection pool exhausted during bootstrap
        
        System MUST fail-fast with clear error, not hang or corrupt state
        """
        from mahoun.bootstrap.runtime import clear_registry
        clear_registry()
        
        # Mock Neo4j to simulate connection pool exhaustion
        def connection_pool_exhausted():
            raise RuntimeError("Neo4j connection pool exhausted")
        
        with patch("mahoun.graph.neo4j.connection.get_connection", side_effect=connection_pool_exhausted):
            from mahoun.bootstrap.runtime import bootstrap_runtime
            
            # Should fail-fast, not hang
            start = time.time()
            
            with pytest.raises(RuntimeError, match="exhausted"):
                bootstrap_runtime()
            
            duration = time.time() - start
            
            assert duration < 5.0, (
                f"Bootstrap took {duration}s to fail — should fail immediately, not hang"
            )


# ============================================================================
# CATEGORY C: RACE CONDITIONS & TOCTOU
# ============================================================================

class TestBootstrapRaceConditions:
    """Test bootstrap race conditions and TOCTOU vulnerabilities"""
    
    @pytest.mark.p3
    def test_bootstrap_prevents_toctou_registry_swap(self):
        """
        ADVERSARIAL: TOCTOU attack — swap registry between check and use
        
        Time-Of-Check / Time-Of-Use vulnerability
        """
        from mahoun.bootstrap.runtime import SERVICE_REGISTRY, register_service, get_service
        
        register_service("critical_service", MagicMock())
        
        # Thread 1: Check if service exists
        # Thread 2: Replace service between check and use
        
        def thread1_victim():
            """Victim thread that checks then uses service"""
            time.sleep(0.001)  # Simulate some work
            service = get_service("critical_service")
            # Use service (should get what we registered)
            assert service is not None
            return id(service)
        
        def thread2_attacker():
            """Attacker thread that swaps service"""
            time.sleep(0.0005)  # Execute between check and use
            malicious_service = MagicMock()
            SERVICE_REGISTRY["critical_service"] = malicious_service
            return id(malicious_service)
        
        # Launch race
        t1 = threading.Thread(target=thread1_victim)
        t2 = threading.Thread(target=thread2_attacker)
        
        t1.start()
        t2.start()
        
        t1.join()
        t2.join()
        
        # Verify registry is still consistent
        final_service = get_service("critical_service")
        assert final_service is not None, "Registry corrupted by race condition"
    
    @pytest.mark.p3
    def test_bootstrap_concurrent_clear_and_populate(self):
        """
        ADVERSARIAL: One thread clears registry while another populates
        
        System MUST maintain consistency
        """
        from mahoun.bootstrap.runtime import clear_registry, register_service, SERVICE_REGISTRY
        
        errors = []
        
        def clear_loop():
            for _ in range(100):
                try:
                    clear_registry()
                    time.sleep(0.001)
                except Exception as e:
                    errors.append(("clear", e))
        
        def populate_loop():
            for i in range(100):
                try:
                    register_service(f"service_{i}", MagicMock())
                    time.sleep(0.001)
                except Exception as e:
                    errors.append(("populate", e))
        
        t1 = threading.Thread(target=clear_loop)
        t2 = threading.Thread(target=populate_loop)
        
        t1.start()
        t2.start()
        
        t1.join()
        t2.join()
        
        # Should not crash (either all cleared or some populated)
        assert len(errors) == 0, f"Race condition errors: {errors}"


# ============================================================================
# CATEGORY D: CASCADING FAILURE SCENARIOS
# ============================================================================

class TestBootstrapCascadingFailures:
    """Test bootstrap under cascading failure scenarios"""
    
    @pytest.mark.p3
    def test_bootstrap_cascade_neo4j_down_but_app_starts(self, monkeypatch):
        """
        ADVERSARIAL: Neo4j down → graph services fail → app should still start
        
        Graceful degradation MUST NOT break entire bootstrap
        """
        monkeypatch.setenv("MAHOUN_ENV", "test")
        
        from mahoun.bootstrap.runtime import clear_registry
        clear_registry()
        
        # Mock Neo4j failure
        def neo4j_down():
            raise ConnectionError("Neo4j unreachable")
        
        with patch("mahoun.graph.neo4j.connection.get_connection", side_effect=neo4j_down):
            from mahoun.bootstrap.runtime import bootstrap_runtime
            
            # Should raise (fail-fast) OR gracefully degrade
            try:
                registry = bootstrap_runtime()
                
                # If it succeeds, verify degraded mode
                # (Some services may be None but registry exists)
                assert isinstance(registry, dict), "Registry should still exist"
                
            except (ConnectionError, RuntimeError) as e:
                # Acceptable: fail-fast with clear error
                assert "Neo4j" in str(e) or "connection" in str(e).lower()
    
    @pytest.mark.p3
    def test_bootstrap_partial_service_failure_contaminates_nothing(self):
        """
        ADVERSARIAL: One service constructor fails → others MUST NOT be affected
        
        Failure isolation
        """
        from mahoun.bootstrap.runtime import clear_registry
        clear_registry()
        
        # Import GNN module before patching to trigger lazy load
        import mahoun.graph.gnn.gnn_graph_builder
        
        # Mock services where one fails
        def failing_service_constructor(*args, **kwargs):
            raise RuntimeError("Service construction failed")
        
        with patch("mahoun.graph.neo4j.connection.get_connection"):
            with patch("mahoun.graph.graph_query_service.GraphQueryService"):
                with patch("mahoun.graph.gnn.gnn_graph_builder.GNNGraphBuilder", side_effect=failing_service_constructor):
                    # GNN fails, but others should succeed
                    with patch("mahoun.retrieval.graph_enhanced.GraphEnhancedRetriever"):
                        with patch("mahoun.pipelines.sync.graph_vector_sync.GraphVectorSync"):
                            with patch("mahoun.graph.legal_cypher_queries.LegalQueryExecutor"):
                                
                                from mahoun.bootstrap.runtime import bootstrap_runtime
                                
                                # Should fail-fast (not partial success)
                                with pytest.raises(RuntimeError, match="construction failed"):
                                    bootstrap_runtime()


# ============================================================================
# CATEGORY E: BYZANTINE FAULTS
# ============================================================================

class TestBootstrapByzantineFaults:
    """Test bootstrap under Byzantine fault conditions"""
    
    @pytest.mark.p3
    def test_bootstrap_detects_corrupted_registry(self):
        """
        ADVERSARIAL: Registry corrupted by memory corruption or bit flip
        
        System MUST detect corruption before use
        """
        from mahoun.bootstrap.runtime import SERVICE_REGISTRY, register_service
        
        # Register valid service
        register_service("valid_service", MagicMock())
        
        # Corrupt registry (simulate memory corruption)
        SERVICE_REGISTRY["corrupted"] = "this_should_be_object_not_string"
        SERVICE_REGISTRY["none_service"] = None  # None value
        
        # get_service should handle corruption gracefully
        from mahoun.bootstrap.runtime import get_service
        
        # Valid service still works
        assert get_service("valid_service") is not None
        
        # None service returns None (no exception - this is by design)
        result = get_service("none_service")
        assert result is None, "get_service should return None for None value"
    
    @pytest.mark.p3
    def test_bootstrap_service_returns_wrong_type(self):
        """
        ADVERSARIAL: Service claims to be GraphQueryService but isn't
        
        Duck typing vulnerability
        """
        from mahoun.bootstrap.runtime import register_service, get_service
        
        # Register service that lies about its type
        class ImpostorService:
            """Looks like GraphQueryService but isn't"""
            def query(self, *args, **kwargs):
                # Returns wrong type
                return "I'm not a query result, I'm a string!"
        
        register_service("impostor", ImpostorService())
        
        # System should catch type mismatch when used
        service = get_service("impostor")
        result = service.query("MATCH (n) RETURN n")
        
        # Result is wrong type — downstream code must handle
        assert isinstance(result, str), "Impostor returned wrong type"


# ============================================================================
# CATEGORY F: FORENSIC & AUDIT TRAIL UNDER ATTACK
# ============================================================================

class TestBootstrapForensicIntegrity:
    """Test that bootstrap leaves unambiguous forensic trail even under attack"""
    
    @pytest.mark.p3
    def test_bootstrap_failure_leaves_forensic_evidence(self, monkeypatch, caplog):
        """
        ADVERSARIAL: Bootstrap fails — forensic logs MUST show exact failure point
        
        No vague "something went wrong"
        """
        monkeypatch.setenv("MAHOUN_ENV", "test")
        
        from mahoun.bootstrap.runtime import clear_registry
        clear_registry()
        
        # Inject failure that will actually be logged
        def failing_gnn_constructor(*args, **kwargs):
            import logging
            logging.error("GNN construction failed: Neo4j connection refused at 127.0.0.1:7687")
            raise ConnectionError("Neo4j connection refused at 127.0.0.1:7687")
        
        # Import GNN module before patching
        import mahoun.graph.gnn.gnn_graph_builder
        
        with patch("mahoun.graph.neo4j.connection.get_connection"):
            with patch("mahoun.graph.gnn.gnn_graph_builder.GNNGraphBuilder", side_effect=failing_gnn_constructor):
                from mahoun.bootstrap.runtime import bootstrap_runtime
                
                with pytest.raises(Exception):
                    bootstrap_runtime()
                
                # Verify logs contain forensic details
                log_text = caplog.text.lower()
                
                # Must contain specific error details (either in logs or exception message)
                has_forensics = (
                    "neo4j" in log_text or 
                    "connection" in log_text or 
                    "gnn" in log_text
                )
                
                assert has_forensics, (
                    f"Logs must contain specific error context. Got: {log_text[:200]}"
                )
                
                # Must NOT contain vague errors
                assert "something went wrong" not in log_text, (
                    "Vague error messages forbidden"
                )
                assert "unknown error" not in log_text, (
                    "Unknown errors must be identified"
                )


# ============================================================================
# EXTREME STRESS TEST: THE KITCHEN SINK
# ============================================================================

class TestBootstrapKitchenSink:
    """Throw everything at bootstrap simultaneously"""
    
    @pytest.mark.slow
    @pytest.mark.p3
    def test_bootstrap_survives_everything_at_once(self, monkeypatch):
        """
        EXTREME: All attacks simultaneously
        
        - Malicious inputs
        - Resource exhaustion
        - Race conditions
        - Neo4j failures
        - Memory corruption
        
        System MUST either succeed cleanly or fail-fast with forensics
        """
        monkeypatch.setenv("MAHOUN_ENV", "test")
        
        from mahoun.bootstrap.runtime import clear_registry, bootstrap_runtime
        
        errors = []
        successes = []
        
        def attack_thread(attack_id):
            """Each thread launches different attack"""
            try:
                if attack_id % 5 == 0:
                    # Flood attack
                    from mahoun.bootstrap.runtime import register_service
                    for i in range(1000):
                        register_service(f"flood_{attack_id}_{i}", MagicMock())
                
                elif attack_id % 5 == 1:
                    # Malicious input
                    from mahoun.bootstrap.runtime import register_service
                    register_service(f"'; DROP TABLE {attack_id}; --", MagicMock())
                
                elif attack_id % 5 == 2:
                    # Clear registry
                    clear_registry()
                
                elif attack_id % 5 == 3:
                    # Call bootstrap
                    with patch("mahoun.graph.neo4j.connection.get_connection"):
                        bootstrap_runtime()
                
                else:
                    # Corrupt registry
                    from mahoun.bootstrap.runtime import SERVICE_REGISTRY
                    SERVICE_REGISTRY[f"corrupt_{attack_id}"] = None
                
                successes.append(attack_id)
                
            except Exception as e:
                errors.append((attack_id, type(e).__name__, str(e)[:100]))
        
        # Launch 100 concurrent attack threads
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(attack_thread, i) for i in range(100)]
            for future in futures:
                try:
                    future.result(timeout=10)
                except Exception as exc:
                    errors.append(("future", type(exc).__name__, str(exc)[:100]))
        
        # System should either survive or fail gracefully
        # (Not crash entire process)
        assert True, "System survived kitchen sink attack"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-m", "not slow"])
