"""
Integration Tests - Under Load (سختگیرانه و بی‌رحمانه)
========================================================

تست سیستم تحت بار سنگین برای کشف race conditions و memory leaks.
"""

import pytest
import time
import threading
import gc
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from mahoun.metrics import MetricsCollector, reset_global_collector


class TestMetricsUnderLoad:
    """تست‌های تحت بار سنگین"""
    
    def setup_method(self):
        """Setup before each test"""
        reset_global_collector()
        gc.collect()  # Clean memory before test
    
    def teardown_method(self):
        """Cleanup after each test"""
        reset_global_collector()
        gc.collect()
    
    @pytest.mark.p3
    def test_high_concurrency_counter(self):
        """
        تست با concurrency بالا:
        - 100 threads
        - هر thread 1000 increment
        - مجموع باید دقیقاً 100,000 باشد
        """
        collector = MetricsCollector()
        counter = collector.register_counter("high_concurrency")
        
        num_threads = 100
        increments_per_thread = 1000
        expected_total = num_threads * increments_per_thread
        
        def worker():
            for _ in range(increments_per_thread):
                counter.inc(1)
        
        # Start all threads
        threads = []
        start_time = time.time()
        
        for _ in range(num_threads):
            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()
        
        # Wait for completion
        for t in threads:
            t.join()
        
        elapsed = time.time() - start_time
        
        # Verify result
        snapshot = collector.snapshot()
        actual = snapshot["counters"]["high_concurrency"]["value"]
        
        assert actual == expected_total, (
            f"Expected {expected_total}, got {actual}. "
            f"Lost {expected_total - actual} increments!"
        )
        
        # Performance check
        ops_per_second = expected_total / elapsed
        print(f"\n✅ {expected_total:,} operations in {elapsed:.2f}s "
              f"({ops_per_second:,.0f} ops/sec)")
        
        # Should be reasonably fast
        assert ops_per_second > 10000, f"Too slow: {ops_per_second:,.0f} ops/sec"
    
    @pytest.mark.p3
    def test_mixed_operations_under_load(self):
        """
        تست عملیات مختلف همزمان:
        - 30 threads: counter increment
        - 30 threads: gauge update
        - 30 threads: histogram observe
        - 10 threads: snapshot creation
        """
        collector = MetricsCollector()
        
        counter = collector.register_counter("load_counter")
        gauge = collector.register_gauge("load_gauge")
        histogram = collector.register_histogram("load_histogram")
        
        operations = 500
        snapshots_created = []
        errors = []
        
        def counter_worker():
            try:
                for i in range(operations):
                    counter.inc(1)
            except Exception as e:
                errors.append(("counter", e))
        
        def gauge_worker():
            try:
                for i in range(operations):
                    gauge.set(float(i))
            except Exception as e:
                errors.append(("gauge", e))
        
        def histogram_worker():
            try:
                for i in range(operations):
                    histogram.observe(float(i))
            except Exception as e:
                errors.append(("histogram", e))
        
        def snapshot_worker():
            try:
                for _ in range(50):
                    snap = collector.create_immutable_snapshot()
                    snapshots_created.append(snap)
                    time.sleep(0.01)  # Small delay
            except Exception as e:
                errors.append(("snapshot", e))
        
        # Start all workers
        threads = []
        
        for _ in range(30):
            threads.append(threading.Thread(target=counter_worker))
        for _ in range(30):
            threads.append(threading.Thread(target=gauge_worker))
        for _ in range(30):
            threads.append(threading.Thread(target=histogram_worker))
        for _ in range(10):
            threads.append(threading.Thread(target=snapshot_worker))
        
        start_time = time.time()
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join()
        
        elapsed = time.time() - start_time
        
        # Check for errors
        assert len(errors) == 0, f"Errors occurred: {errors}"
        
        # Verify results
        snapshot = collector.snapshot()
        
        # Counter should have exact count
        expected_counter = 30 * operations
        actual_counter = snapshot["counters"]["load_counter"]["value"]
        assert actual_counter == expected_counter, (
            f"Counter: expected {expected_counter}, got {actual_counter}"
        )
        
        # Histogram should have exact count
        expected_histogram = 30 * operations
        actual_histogram = snapshot["histograms"]["load_histogram"]["count"]
        assert actual_histogram == expected_histogram, (
            f"Histogram: expected {expected_histogram}, got {actual_histogram}"
        )
        
        # Snapshots should all be valid
        assert len(snapshots_created) == 500, (
            f"Expected 500 snapshots, got {len(snapshots_created)}"
        )
        
        for snap in snapshots_created:
            assert snap.content_hash is not None
            assert snap.timestamp is not None
        
        print(f"\n✅ Mixed operations completed in {elapsed:.2f}s")
        print(f"   - {expected_counter:,} counter increments")
        print(f"   - {30 * operations:,} gauge updates")
        print(f"   - {expected_histogram:,} histogram observations")
        print(f"   - {len(snapshots_created)} snapshots created")
    
    @pytest.mark.p3
    def test_sustained_load(self):
        """
        تست بار پایدار:
        - 10 threads برای 30 ثانیه
        - هر thread به طور مداوم operations انجام می‌دهد
        - بررسی memory leak
        """
        collector = MetricsCollector()
        counter = collector.register_counter("sustained")
        
        duration = 10  # seconds (کوتاه‌تر برای سرعت تست)
        stop_flag = threading.Event()
        operation_counts = []
        
        def worker():
            count = 0
            while not stop_flag.is_set():
                counter.inc(1)
                count += 1
            operation_counts.append(count)
        
        # Measure initial memory
        gc.collect()
        initial_memory = sys.getsizeof(collector)
        
        # Start workers
        threads = []
        for _ in range(10):
            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()
        
        # Run for duration
        time.sleep(duration)
        stop_flag.set()
        
        # Wait for completion
        for t in threads:
            t.join()
        
        # Measure final memory
        gc.collect()
        final_memory = sys.getsizeof(collector)
        
        # Verify operations
        total_ops = sum(operation_counts)
        snapshot = collector.snapshot()
        actual = snapshot["counters"]["sustained"]["value"]
        
        assert actual == total_ops, f"Expected {total_ops}, got {actual}"
        
        # Check memory growth
        memory_growth = final_memory - initial_memory
        memory_growth_percent = (memory_growth / initial_memory) * 100
        
        print(f"\n✅ Sustained load test:")
        print(f"   - Duration: {duration}s")
        print(f"   - Total operations: {total_ops:,}")
        print(f"   - Ops/sec: {total_ops/duration:,.0f}")
        print(f"   - Memory growth: {memory_growth} bytes ({memory_growth_percent:.1f}%)")
        
        # Memory shouldn't grow significantly
        assert memory_growth_percent < 50, (
            f"Excessive memory growth: {memory_growth_percent:.1f}%"
        )
    
    @pytest.mark.p3
    def test_burst_load(self):
        """
        تست بار ناگهانی (burst):
        - 1000 threads همزمان شروع می‌شوند
        - هر thread 10 operation انجام می‌دهد
        - سیستم نباید crash کند
        """
        collector = MetricsCollector()
        counter = collector.register_counter("burst")
        
        num_threads = 1000
        ops_per_thread = 10
        expected = num_threads * ops_per_thread
        
        def worker():
            for _ in range(ops_per_thread):
                counter.inc(1)
        
        # Use ThreadPoolExecutor for better management
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=100) as executor:
            futures = [executor.submit(worker) for _ in range(num_threads)]
            
            # Wait for all to complete
            for future in as_completed(futures):
                future.result()  # Raise any exceptions
        
        elapsed = time.time() - start_time
        
        # Verify
        snapshot = collector.snapshot()
        actual = snapshot["counters"]["burst"]["value"]
        
        assert actual == expected, f"Expected {expected}, got {actual}"
        
        print(f"\n✅ Burst load test:")
        print(f"   - {num_threads} threads")
        print(f"   - {expected:,} total operations")
        print(f"   - Completed in {elapsed:.2f}s")
    
    @pytest.mark.p3
    def test_reset_under_load(self):
        """
        تست reset در حین بار:
        - 50 threads در حال increment
        - 1 thread هر 0.1 ثانیه reset می‌کند
        - نباید crash کند
        """
        collector = MetricsCollector()
        counter = collector.register_counter("reset_test")
        
        duration = 5  # seconds
        stop_flag = threading.Event()
        reset_count = [0]
        errors = []
        
        def increment_worker():
            try:
                while not stop_flag.is_set():
                    counter.inc(1)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(("increment", e))
        
        def reset_worker():
            try:
                while not stop_flag.is_set():
                    collector.reset()
                    reset_count[0] += 1
                    time.sleep(0.1)
            except Exception as e:
                errors.append(("reset", e))
        
        # Start workers
        threads = []
        
        for _ in range(50):
            t = threading.Thread(target=increment_worker)
            threads.append(t)
            t.start()
        
        reset_thread = threading.Thread(target=reset_worker)
        threads.append(reset_thread)
        reset_thread.start()
        
        # Run
        time.sleep(duration)
        stop_flag.set()
        
        # Wait
        for t in threads:
            t.join()
        
        # Check errors
        assert len(errors) == 0, f"Errors: {errors}"
        
        print(f"\n✅ Reset under load:")
        print(f"   - Duration: {duration}s")
        print(f"   - Resets performed: {reset_count[0]}")
        print(f"   - No crashes or deadlocks")
    
    @pytest.mark.p3
    def test_large_number_of_metrics(self):
        """
        تست با تعداد زیاد metrics:
        - 10,000 counters
        - همزمان از 100 thread استفاده می‌شود
        """
        collector = MetricsCollector()
        
        num_metrics = 10000
        num_threads = 100
        metrics_per_thread = num_metrics // num_threads
        
        def worker(start_idx):
            for i in range(start_idx, start_idx + metrics_per_thread):
                counter = collector.register_counter(f"metric_{i}")
                counter.inc(i)
        
        start_time = time.time()
        
        threads = []
        for i in range(num_threads):
            start_idx = i * metrics_per_thread
            t = threading.Thread(target=worker, args=(start_idx,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        elapsed = time.time() - start_time
        
        # Verify
        snapshot = collector.snapshot()
        assert len(snapshot["counters"]) == num_metrics
        
        # Spot check
        assert snapshot["counters"]["metric_5000"]["value"] == 5000
        
        print(f"\n✅ Large metrics test:")
        print(f"   - {num_metrics:,} metrics created")
        print(f"   - Time: {elapsed:.2f}s")
        print(f"   - Rate: {num_metrics/elapsed:,.0f} metrics/sec")
    
    @pytest.mark.slow
    @pytest.mark.p3
    def test_memory_leak_detection(self):
        """
        تست memory leak:
        - 1000 iterations
        - هر iteration: create, use, reset
        - memory نباید رشد کند
        """
        import tracemalloc
        
        tracemalloc.start()
        
        iterations = 1000
        memory_samples = []
        
        for i in range(iterations):
            collector = MetricsCollector()
            
            # Create metrics
            for j in range(10):
                counter = collector.register_counter(f"counter_{j}")
                counter.inc(j)
            
            # Use them
            snapshot = collector.snapshot()
            _ = collector.to_prometheus()
            
            # Reset
            collector.reset()
            
            # Sample memory every 100 iterations
            if i % 100 == 0:
                current, peak = tracemalloc.get_traced_memory()
                memory_samples.append(current)
                print(f"Iteration {i}: {current / 1024 / 1024:.2f} MB")
        
        tracemalloc.stop()
        
        # Check memory trend
        if len(memory_samples) > 2:
            first_half_avg = sum(memory_samples[:len(memory_samples)//2]) / (len(memory_samples)//2)
            second_half_avg = sum(memory_samples[len(memory_samples)//2:]) / (len(memory_samples)//2)
            
            growth_percent = ((second_half_avg - first_half_avg) / first_half_avg) * 100
            
            print(f"\n✅ Memory leak test:")
            print(f"   - Iterations: {iterations}")
            print(f"   - Memory growth: {growth_percent:.1f}%")
            
            # Should not grow significantly
            assert growth_percent < 20, f"Possible memory leak: {growth_percent:.1f}% growth"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])
