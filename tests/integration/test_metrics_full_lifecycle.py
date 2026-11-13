"""
Integration Tests - Full Lifecycle
===================================

تست کامل lifecycle از ابتدا تا انتها با سختگیری بالا.
"""

import pytest
import time
import threading
from mahoun.metrics import MetricsCollector, get_metrics_collector, reset_global_collector
from mahoun.metrics.snapshot import MetricsSnapshot


class TestMetricsFullLifecycle:
    """تست lifecycle کامل metrics system"""
    
    def setup_method(self):
        """Setup before each test"""
        reset_global_collector()
    
    def teardown_method(self):
        """Cleanup after each test"""
        reset_global_collector()
    
    @pytest.mark.p2
    def test_complete_lifecycle_single_thread(self):
        """
        تست lifecycle کامل در single thread:
        1. Initialize
        2. Register metrics
        3. Record values
        4. Create snapshot
        5. Export Prometheus
        6. Reset
        7. Verify clean state
        """
        # 1. Initialize
        collector = MetricsCollector()
        assert collector is not None
        
        # 2. Register metrics
        counter = collector.register_counter("requests_total")
        gauge = collector.register_gauge("active_connections")
        histogram = collector.register_histogram("request_duration_ms")
        
        # 3. Record values
        counter.inc(100)
        gauge.set(42)
        for i in range(10):
            histogram.observe(i * 10)
        
        # 4. Verify values
        snapshot = collector.snapshot()
        assert snapshot["counters"]["requests_total"]["value"] == 100
        assert snapshot["gauges"]["active_connections"]["value"] == 42
        assert snapshot["histograms"]["request_duration_ms"]["count"] == 10
        
        # 5. Create immutable snapshot
        immutable_snapshot = collector.create_immutable_snapshot()
        assert immutable_snapshot.content_hash is not None
        assert immutable_snapshot.timestamp is not None
        
        # 6. Export Prometheus
        prom_output = collector.to_prometheus()
        assert "requests_total" in prom_output
        assert "active_connections" in prom_output
        assert "request_duration_ms" in prom_output
        
        # 7. Reset
        collector.reset()
        
        # 8. Verify clean state
        snapshot_after = collector.snapshot()
        assert len(snapshot_after["counters"]) == 0
        assert len(snapshot_after["gauges"]) == 0
        assert len(snapshot_after["histograms"]) == 0
    
    @pytest.mark.p2
    def test_lifecycle_with_system_metrics(self):
        """تست lifecycle با system metrics"""
        collector = MetricsCollector()
        
        # Collect system metrics
        collector.collect_system_metrics()
        
        # Verify system metrics exist
        snapshot = collector.snapshot()
        # System metrics should be present
        assert len(snapshot["gauges"]) > 0
        
        # Add custom metrics
        counter = collector.register_counter("custom_counter")
        counter.inc(10)
        
        # Verify both exist
        snapshot = collector.snapshot()
        assert "custom_counter" in snapshot["counters"]
        
        # Reset should clear everything
        collector.reset()
        snapshot = collector.snapshot()
        assert len(snapshot["counters"]) == 0
        assert len(snapshot["gauges"]) == 0
    
    @pytest.mark.p2
    def test_lifecycle_multi_threaded(self):
        """
        تست lifecycle در محیط multi-threaded:
        - 10 threads همزمان metrics می‌سازند
        - هر thread 100 operation انجام می‌دهد
        - در پایان همه مقادیر باید صحیح باشد
        """
        collector = MetricsCollector()
        counter = collector.register_counter("concurrent_counter")
        
        num_threads = 10
        ops_per_thread = 100
        
        def worker():
            for _ in range(ops_per_thread):
                counter.inc(1)
        
        threads = []
        for _ in range(num_threads):
            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # Verify total
        snapshot = collector.snapshot()
        expected = num_threads * ops_per_thread
        actual = snapshot["counters"]["concurrent_counter"]["value"]
        assert actual == expected, f"Expected {expected}, got {actual}"
    
    @pytest.mark.p2
    def test_snapshot_immutability(self):
        """تست immutability snapshot"""
        collector = MetricsCollector()
        counter = collector.register_counter("test")
        counter.inc(10)
        
        # Create snapshot
        snapshot = collector.create_immutable_snapshot()
        original_hash = snapshot.content_hash
        
        # Try to modify (should fail or have no effect)
        try:
            snapshot.counters["test"]["value"] = 999
            pytest.fail("Snapshot should be immutable!")
        except (TypeError, AttributeError):
            pass  # Expected
        
        # Verify hash unchanged
        assert snapshot.content_hash == original_hash
        
        # Modify original
        counter.inc(20)
        
        # Snapshot should still have old value
        assert snapshot.counters["test"]["value"] == 10
    
    @pytest.mark.p2
    def test_prometheus_export_format(self):
        """تست format صحیح Prometheus export"""
        collector = MetricsCollector()
        
        # Create various metrics
        counter = collector.register_counter("http_requests_total", 
                                             labels={"method": "GET", "status": "200"})
        counter.inc(42)
        
        gauge = collector.register_gauge("temperature_celsius",
                                        labels={"location": "server1"})
        gauge.set(75.5)
        
        histogram = collector.register_histogram("response_time_ms")
        histogram.observe(100)
        histogram.observe(200)
        
        # Export
        output = collector.to_prometheus()
        
        # Verify format
        assert 'http_requests_total{method="GET",status="200"} 42' in output
        assert 'temperature_celsius{location="server1"} 75.5' in output
        assert 'response_time_ms_count' in output
    
    @pytest.mark.p2
    def test_error_recovery(self):
        """تست recovery از خطاها"""
        collector = MetricsCollector()
        
        # Register valid metric
        counter = collector.register_counter("valid")
        counter.inc(10)
        
        # Try invalid operations (should not crash)
        try:
            counter.inc(-5)  # Negative increment
        except ValueError:
            pass  # Expected
        
        # System should still work
        counter.inc(5)
        snapshot = collector.snapshot()
        assert snapshot["counters"]["valid"]["value"] == 15
    
    @pytest.mark.p2
    def test_singleton_behavior(self):
        """تست singleton pattern"""
        collector1 = get_metrics_collector()
        collector2 = get_metrics_collector()
        
        assert collector1 is collector2
        
        # Modify through one
        counter = collector1.register_counter("shared")
        counter.inc(10)
        
        # Verify through other
        snapshot = collector2.snapshot()
        assert snapshot["counters"]["shared"]["value"] == 10
    
    @pytest.mark.p2
    def test_reset_and_reuse(self):
        """تست reset و استفاده مجدد"""
        collector = MetricsCollector()
        
        # First use
        counter = collector.register_counter("test")
        counter.inc(100)
        assert collector.snapshot()["counters"]["test"]["value"] == 100
        
        # Reset
        collector.reset()
        assert len(collector.snapshot()["counters"]) == 0
        
        # Reuse
        counter2 = collector.register_counter("test")
        counter2.inc(50)
        assert collector.snapshot()["counters"]["test"]["value"] == 50
    
    @pytest.mark.p2
    def test_large_scale_metrics(self):
        """
        تست با تعداد زیاد metrics:
        - 1000 counters
        - 1000 gauges
        - 100 histograms
        """
        collector = MetricsCollector()
        
        # Create many metrics
        for i in range(1000):
            counter = collector.register_counter(f"counter_{i}")
            counter.inc(i)
            
            gauge = collector.register_gauge(f"gauge_{i}")
            gauge.set(float(i))
        
        for i in range(100):
            histogram = collector.register_histogram(f"histogram_{i}")
            histogram.observe(float(i))
        
        # Verify all exist
        snapshot = collector.snapshot()
        assert len(snapshot["counters"]) == 1000
        assert len(snapshot["gauges"]) == 1000
        assert len(snapshot["histograms"]) == 100
        
        # Verify values
        assert snapshot["counters"]["counter_500"]["value"] == 500
        assert snapshot["gauges"]["gauge_500"]["value"] == 500.0
        assert snapshot["histograms"]["histogram_50"]["count"] == 1


class TestMetricsEdgeCases:
    """تست edge cases"""
    
    def setup_method(self):
        reset_global_collector()
    
    def teardown_method(self):
        reset_global_collector()
    
    @pytest.mark.p2
    def test_empty_collector(self):
        """تست collector خالی"""
        collector = MetricsCollector()
        
        snapshot = collector.snapshot()
        assert snapshot["counters"] == {}
        assert snapshot["gauges"] == {}
        assert snapshot["histograms"] == {}
        
        prom = collector.to_prometheus()
        assert prom == "# Metrics disabled" or prom == ""
    
    @pytest.mark.p2
    def test_duplicate_registration(self):
        """تست registration تکراری"""
        collector = MetricsCollector()
        
        counter1 = collector.register_counter("test")
        counter2 = collector.register_counter("test")
        
        # Should return same instance
        assert counter1 is counter2
        
        # Modifications should affect both
        counter1.inc(10)
        assert counter2.value == 10
    
    @pytest.mark.p2
    def test_concurrent_snapshot_creation(self):
        """تست ایجاد همزمان snapshot"""
        collector = MetricsCollector()
        counter = collector.register_counter("test")
        
        snapshots = []
        
        def create_snapshot():
            for _ in range(10):
                counter.inc(1)
                snap = collector.create_immutable_snapshot()
                snapshots.append(snap)
        
        threads = [threading.Thread(target=create_snapshot) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # All snapshots should be valid
        assert len(snapshots) == 50
        for snap in snapshots:
            assert snap.content_hash is not None
            assert snap.timestamp is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
