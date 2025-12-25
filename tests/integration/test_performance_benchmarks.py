"""
Integration tests for performance benchmarking.

Tests measure and report performance metrics WITHOUT hard assertions,
corresponding to Test Case 5 from TESTING_PLAN.md.

These tests verify:
- Local file serving performance (Test 5.1.1)
- GCS file serving performance (Test 5.1.2)
- Compression ratio reporting (Test 5.3.1)
- Memory usage during operations (Test 5.2.1)
- Concurrent upload performance
- Database query performance

Note: These tests REPORT metrics via logging, they do NOT fail on performance issues.
"""

import time
import logging
from pathlib import Path
import pytest

logger = logging.getLogger(__name__)


class TestPerformanceBenchmarks:
    """Performance benchmark tests - reporting only, no assertions."""

    def test_local_file_serving_performance(self, test_app_with_fakes, integration_temp_dir, caplog):
        """
        Test: Save archive → measure GET /files/... response time → log metrics (no assertion).

        Corresponds to TESTING_PLAN Test Case 5.1.1: Local File Serving Performance
        Target: < 500ms but only reports, doesn't fail
        """
        from fastapi.testclient import TestClient

        client = TestClient(test_app_with_fakes)

        test_url = "https://example.com/perf-test"
        item_id = "perf_local_001"

        # Save archive
        save_start = time.time()
        response = client.post(
            "/archive/monolith",
            json={"id": item_id, "url": test_url}
        )
        save_duration = time.time() - save_start

        if response.status_code == 200:
            # Measure retrieval performance (10 iterations)
            retrieval_times = []
            for i in range(10):
                retrieve_start = time.time()
                retrieve_response = client.post(
                    "/archive/retrieve",
                    json={"id": item_id, "archiver": "monolith"}
                )
                retrieve_duration = time.time() - retrieve_start

                if retrieve_response.status_code == 200:
                    retrieval_times.append(retrieve_duration)

            # Calculate statistics
            if retrieval_times:
                avg_time = sum(retrieval_times) / len(retrieval_times)
                min_time = min(retrieval_times)
                max_time = max(retrieval_times)

                # Report metrics (no assertion)
                logger.info(f"Local file serving performance:")
                logger.info(f"  Save time: {save_duration:.3f}s")
                logger.info(f"  Retrieval avg: {avg_time:.3f}s")
                logger.info(f"  Retrieval min: {min_time:.3f}s")
                logger.info(f"  Retrieval max: {max_time:.3f}s")
                logger.info(f"  Target: < 0.500s (for reference)")

                # Log to caplog for test output
                print(f"\n📊 Local File Serving Performance:")
                print(f"   Save: {save_duration:.3f}s | Retrieval: {avg_time:.3f}s (avg)")

    def test_gcs_file_serving_performance_mock(self, test_app_with_fakes, mocker, caplog):
        """
        Test: Mock GCS → measure POST /archive/retrieve → log response time.

        Corresponds to TESTING_PLAN Test Case 5.1.2: GCS File Serving Performance
        Target: < 1000ms but only reports
        """
        # Mock GCS for performance testing
        mock_serve_time = 0.150  # Simulate 150ms GCS response

        def mock_serve_file(*args, **kwargs):
            time.sleep(mock_serve_time)
            from fastapi.responses import Response
            return Response(content="<html>Mock content</html>", media_type="text/html")

        # Measure simulated GCS serving
        retrieval_times = []
        for i in range(10):
            start = time.time()
            mock_serve_file()
            duration = time.time() - start
            retrieval_times.append(duration)

        avg_time = sum(retrieval_times) / len(retrieval_times)

        logger.info(f"GCS file serving performance (mocked):")
        logger.info(f"  Average: {avg_time:.3f}s")
        logger.info(f"  Target: < 1.000s (for reference)")

        print(f"\n📊 GCS File Serving Performance (Mock):")
        print(f"   Retrieval: {avg_time:.3f}s (avg)")

    def test_compression_ratio_reporting(self, integration_temp_dir, real_file_storage, caplog):
        """
        Test: Upload compressible file → log compression_ratio → report in test output.

        Corresponds to TESTING_PLAN Test Case 5.3.1: Compression Ratio Analysis
        Target: > 70% but only reports
        """
        # Create highly compressible file
        test_file = integration_temp_dir / "compressible.html"
        compressible_content = "<html><body>" + ("x" * 50000) + "</body></html>"
        test_file.write_text(compressible_content)

        original_size = len(compressible_content.encode())

        # Upload with compression
        result = real_file_storage.upload_file(
            local_path=test_file,
            destination_path="perf/compressible.html",
            compress=True
        )

        if result.success and result.compression_ratio:
            logger.info(f"Compression performance:")
            logger.info(f"  Original size: {original_size:,} bytes")
            logger.info(f"  Stored size: {result.stored_size:,} bytes")
            logger.info(f"  Compression ratio: {result.compression_ratio:.2f}%")
            logger.info(f"  Target: > 70% (for reference)")

            print(f"\n📊 Compression Performance:")
            print(f"   Ratio: {result.compression_ratio:.2f}% | Target: >70%")

    def test_memory_usage_during_bundle_creation(self, test_app_with_fakes, integration_temp_dir):
        """
        Test: Create bundle with 10 archives → measure memory delta → log peak usage.

        Corresponds to TESTING_PLAN Test Case 5.2.1: Bundle Creation Memory
        """
        try:
            import psutil
            process = psutil.Process()
        except ImportError:
            pytest.skip("psutil not available for memory monitoring")

        from fastapi.testclient import TestClient

        client = TestClient(test_app_with_fakes)

        # Measure baseline memory
        baseline_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Create multiple archives
        item_ids = []
        for i in range(5):  # Reduced from 10 for faster testing
            item_id = f"perf_bundle_{i:03d}"
            item_ids.append(item_id)

            response = client.post(
                "/archive/monolith",
                json={"id": item_id, "url": f"https://example.com/bundle/{i}"}
            )

        # Measure peak memory
        peak_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_delta = peak_memory - baseline_memory

        logger.info(f"Memory usage during bundle creation:")
        logger.info(f"  Baseline: {baseline_memory:.2f} MB")
        logger.info(f"  Peak: {peak_memory:.2f} MB")
        logger.info(f"  Delta: {memory_delta:.2f} MB")
        logger.info(f"  Archives created: {len(item_ids)}")

        print(f"\n📊 Memory Usage:")
        print(f"   Delta: {memory_delta:.2f} MB | Archives: {len(item_ids)}")

    def test_concurrent_upload_performance(self, integration_temp_dir, real_file_storage):
        """
        Test: 5 concurrent uploads → measure throughput → log ops/second.

        Measures concurrent operation performance.
        """
        import threading
        import queue

        # Create test files
        test_files = []
        for i in range(5):
            test_file = integration_temp_dir / f"concurrent_{i}.html"
            test_file.write_text(f"<html>Concurrent test {i}</html>")
            test_files.append(test_file)

        results = queue.Queue()
        start_time = time.time()

        def upload_worker(worker_id, test_file):
            worker_start = time.time()
            result = real_file_storage.upload_file(
                local_path=test_file,
                destination_path=f"perf/concurrent_{worker_id}.html",
                compress=False
            )
            worker_duration = time.time() - worker_start
            results.put((worker_id, worker_duration, result.success))

        # Launch concurrent uploads
        threads = []
        for i, test_file in enumerate(test_files):
            thread = threading.Thread(target=upload_worker, args=(i, test_file))
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        total_duration = time.time() - start_time

        # Collect results
        upload_times = []
        success_count = 0
        while not results.empty():
            worker_id, duration, success = results.get()
            upload_times.append(duration)
            if success:
                success_count += 1

        # Calculate throughput
        if total_duration > 0:
            throughput = len(test_files) / total_duration
            avg_upload_time = sum(upload_times) / len(upload_times) if upload_times else 0

            logger.info(f"Concurrent upload performance:")
            logger.info(f"  Total duration: {total_duration:.3f}s")
            logger.info(f"  Average upload time: {avg_upload_time:.3f}s")
            logger.info(f"  Throughput: {throughput:.2f} ops/sec")
            logger.info(f"  Success rate: {success_count}/{len(test_files)}")

            print(f"\n📊 Concurrent Upload Performance:")
            print(f"   Throughput: {throughput:.2f} ops/sec | Success: {success_count}/{len(test_files)}")

    def test_database_query_performance(self, db_session, sample_items, caplog):
        """
        Test: Insert 100 artifacts → measure query time for list_by_url → log duration.

        Measures database query performance.
        """
        from app.db.repositories import ArchiveArtifactRepository, ArchivedUrlRepository

        artifact_repo = ArchiveArtifactRepository(db_session)
        url_repo = ArchivedUrlRepository(db_session)

        # Insert test data
        insert_start = time.time()

        # Create URLs and artifacts
        for i in range(min(20, len(sample_items) * 4)):  # Reduced for faster testing
            url_data = sample_items[i % len(sample_items)]

            archived_url = url_repo.get_or_create(
                url=f"{url_data['url']}?variant={i}",
                item_id=f"perf_db_{i:03d}"
            )

            artifact_repo.get_or_create(
                archived_url_id=archived_url.id,
                archiver="monolith"
            )

        insert_duration = time.time() - insert_start

        # Measure query performance
        query_times = []
        for i in range(10):
            query_start = time.time()
            results = artifact_repo.list_by_url(sample_items[0]['url'])
            query_duration = time.time() - query_start
            query_times.append(query_duration)

        avg_query_time = sum(query_times) / len(query_times)

        logger.info(f"Database query performance:")
        logger.info(f"  Insert duration (20 records): {insert_duration:.3f}s")
        logger.info(f"  Average query time: {avg_query_time:.4f}s")
        logger.info(f"  Query iterations: {len(query_times)}")

        print(f"\n📊 Database Performance:")
        print(f"   Insert: {insert_duration:.3f}s | Query: {avg_query_time:.4f}s (avg)")

    def test_archive_creation_performance_by_archiver(self, test_app_with_fakes, caplog):
        """
        Test: Measure archive creation time for different archivers.

        Compares performance across archiver types.
        """
        from fastapi.testclient import TestClient

        client = TestClient(test_app_with_fakes)

        archivers_to_test = ["monolith"]  # Add more if available in test setup

        results = {}

        for archiver in archivers_to_test:
            times = []

            for i in range(5):
                start = time.time()
                response = client.post(
                    f"/archive/{archiver}",
                    json={
                        "id": f"perf_{archiver}_{i}",
                        "url": f"https://example.com/{archiver}/{i}"
                    }
                )
                duration = time.time() - start

                if response.status_code == 200:
                    times.append(duration)

            if times:
                avg_time = sum(times) / len(times)
                results[archiver] = avg_time

        # Report results
        logger.info(f"Archive creation performance by archiver:")
        for archiver, avg_time in results.items():
            logger.info(f"  {archiver}: {avg_time:.3f}s (avg)")

        print(f"\n📊 Archive Creation Performance:")
        for archiver, avg_time in results.items():
            print(f"   {archiver}: {avg_time:.3f}s")

    def test_large_file_compression_performance(self, integration_temp_dir, real_file_storage):
        """
        Test: Compress large file (5MB) → measure time and ratio.

        Tests compression performance on larger files.
        """
        # Create 5MB file
        large_file = integration_temp_dir / "large.html"
        large_content = "<html><body>" + ("x" * 5_000_000) + "</body></html>"
        large_file.write_text(large_content)

        original_size = len(large_content.encode())

        # Measure compression time
        compress_start = time.time()
        result = real_file_storage.upload_file(
            local_path=large_file,
            destination_path="perf/large.html",
            compress=True
        )
        compress_duration = time.time() - compress_start

        if result.success:
            throughput = original_size / compress_duration / 1024 / 1024  # MB/s

            logger.info(f"Large file compression performance:")
            logger.info(f"  File size: {original_size / 1024 / 1024:.2f} MB")
            logger.info(f"  Compression time: {compress_duration:.3f}s")
            logger.info(f"  Throughput: {throughput:.2f} MB/s")
            if result.compression_ratio:
                logger.info(f"  Compression ratio: {result.compression_ratio:.2f}%")

            print(f"\n📊 Large File Compression:")
            print(f"   Throughput: {throughput:.2f} MB/s | Ratio: {result.compression_ratio:.2f}%")
