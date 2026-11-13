"""
Advanced Data Loader
===================

Enterprise-grade data loading system with:
- Batch processing
- Progress tracking
- Error recovery
- Streaming support
- Parallel loading
- Data validation
"""


import asyncio
from typing import List, Dict, Any, Optional, Iterator, Callable
from dataclasses import dataclass, field
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False


class LoadStatus(str, Enum):
    """Loading status"""
    PENDING = "pending"
    LOADING = "loading"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class LoadResult:
    """Result of loading operation"""
    file_path: Path
    status: LoadStatus
    data: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    load_time_ms: float = 0.0
    
    @property
    def is_success(self) -> bool:
        return self.status == LoadStatus.SUCCESS


@dataclass
class LoadProgress:
    """Loading progress tracker"""
    total: int
    loaded: int = 0
    failed: int = 0
    skipped: int = 0
    start_time: float = field(default_factory=time.time)
    
    @property
    def completed(self) -> int:
        return self.loaded + self.failed + self.skipped
    
    @property
    def progress_pct(self) -> float:
        return (self.completed / self.total * 100) if self.total > 0 else 0
    
    @property
    def elapsed_time(self) -> float:
        return time.time() - self.start_time
    
    @property
    def eta_seconds(self) -> Optional[float]:
        if self.completed == 0:
            return None
        rate = self.completed / self.elapsed_time
        remaining = self.total - self.completed
        return remaining / rate if rate > 0 else None


class DataLoader:
    """
    Advanced data loader with batch processing and error recovery
    
    Features:
    - Batch loading with configurable size
    - Progress tracking with ETA
    - Error recovery and retry logic
    - Parallel loading
    - Memory-efficient streaming
    """
    
    def __init__(
        self,
        batch_size: int = 100,
        max_workers: int = 4,
        retry_attempts: int = 3,
        skip_on_error: bool = True,
        show_progress: bool = True,
    ):
        """
        Initialize data loader
        
        Args:
            batch_size: Number of files per batch
            max_workers: Maximum parallel workers
            retry_attempts: Number of retry attempts on failure
            skip_on_error: Skip failed files or raise exception
            show_progress: Show progress bar
        """
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.retry_attempts = retry_attempts
        self.skip_on_error = skip_on_error
        self.show_progress = show_progress and HAS_TQDM
        
        self.progress: Optional[LoadProgress] = None
        self.results: List[LoadResult] = []
    
    def load_files(
        self,
        file_paths: List[Path],
        loader_fn: Callable[[Path], Any],
        validator_fn: Optional[Callable[[Any], bool]] = None,
    ) -> List[LoadResult]:
        """
        Load multiple files with progress tracking
        
        Args:
            file_paths: List of file paths to load
            loader_fn: Function to load a single file
            validator_fn: Optional validation function
            
        Returns:
            List of LoadResult objects
        """
        self.progress = LoadProgress(total=len(file_paths))
        self.results = []
        
        # Create progress bar
        pbar = None
        if self.show_progress:
            pbar = tqdm(total=len(file_paths), desc="Loading files")
        
        # Process in batches
        for batch_start in range(0, len(file_paths), self.batch_size):
            batch_end = min(batch_start + self.batch_size, len(file_paths))
            batch = file_paths[batch_start:batch_end]
            
            # Load batch
            batch_results = self._load_batch(batch, loader_fn, validator_fn)
            self.results.extend(batch_results)
            
            # Update progress
            for result in batch_results:
                if result.status == LoadStatus.SUCCESS:
                    self.progress.loaded += 1
                elif result.status == LoadStatus.FAILED:
                    self.progress.failed += 1
                elif result.status == LoadStatus.SKIPPED:
                    self.progress.skipped += 1
                
                if pbar:
                    pbar.update(1)
                    pbar.set_postfix({
                        'loaded': self.progress.loaded,
                        'failed': self.progress.failed,
                        'eta': f"{self.progress.eta_seconds:.0f}s" if self.progress.eta_seconds else "N/A"
                    })
        
        if pbar:
            pbar.close()
        
        return self.results
    
    def _load_batch(
        self,
        file_paths: List[Path],
        loader_fn: Callable[[Path], Any],
        validator_fn: Optional[Callable[[Any], bool]],
    ) -> List[LoadResult]:
        """Load a batch of files in parallel"""
        results = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_path = {
                executor.submit(self._load_single_file, path, loader_fn, validator_fn): path
                for path in file_paths
            }
            
            # Collect results
            for future in as_completed(future_to_path):
                result = future.result()
                results.append(result)
        
        return results
    
    def _load_single_file(
        self,
        file_path: Path,
        loader_fn: Callable[[Path], Any],
        validator_fn: Optional[Callable[[Any], bool]],
    ) -> LoadResult:
        """Load a single file with retry logic"""
        start_time = time.time()
        
        for attempt in range(self.retry_attempts):
            try:
                # Load file
                data = loader_fn(file_path)
                
                # Validate if validator provided
                if validator_fn and not validator_fn(data):
                    raise ValueError("Validation failed")
                
                # Success
                load_time = (time.time() - start_time) * 1000
                return LoadResult(
                    file_path=file_path,
                    status=LoadStatus.SUCCESS,
                    data=data,
                    load_time_ms=load_time,
                )
                
            except Exception as e:
                if attempt < self.retry_attempts - 1:
                    # Retry
                    time.sleep(0.1 * (attempt + 1))  # Exponential backoff
                    continue
                else:
                    # Final failure
                    load_time = (time.time() - start_time) * 1000
                    
                    if self.skip_on_error:
                        return LoadResult(
                            file_path=file_path,
                            status=LoadStatus.FAILED,
                            error=str(e),
                            load_time_ms=load_time,
                        )
                    else:
                        raise
        
        # Should not reach here
        return LoadResult(
            file_path=file_path,
            status=LoadStatus.FAILED,
            error="Unknown error",
        )
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get loading statistics"""
        if not self.progress:
            return {}
        
        return {
            'total': self.progress.total,
            'loaded': self.progress.loaded,
            'failed': self.progress.failed,
            'skipped': self.progress.skipped,
            'success_rate': self.progress.loaded / self.progress.total if self.progress.total > 0 else 0,
            'elapsed_time': self.progress.elapsed_time,
            'avg_time_per_file': self.progress.elapsed_time / self.progress.completed if self.progress.completed > 0 else 0,
        }


class StreamingDataLoader:
    """
    Memory-efficient streaming data loader for large files
    
    Loads data in chunks to avoid memory issues
    """
    
    def __init__(self, chunk_size: int = 1024 * 1024):  # 1MB chunks
        """
        Initialize streaming loader
        
        Args:
            chunk_size: Size of each chunk in bytes
        """
        self.chunk_size = chunk_size
    
    def stream_file(self, file_path: Path) -> Iterator[bytes]:
        """
        Stream file in chunks
        
        Args:
            file_path: Path to file
            
        Yields:
            Chunks of file data
        """
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(self.chunk_size)
                if not chunk:
                    break
                yield chunk
    
    def stream_lines(self, file_path: Path, encoding: str = 'utf-8') -> Iterator[str]:
        """
        Stream file line by line
        
        Args:
            file_path: Path to file
            encoding: File encoding
            
        Yields:
            Lines from file
        """
        with open(file_path, 'r', encoding=encoding) as f:
            for line in f:
                yield line.strip()


class BatchProcessor:
    """
    Process data in batches with callback support
    """
    
    def __init__(
        self,
        batch_size: int = 100,
        on_batch_complete: Optional[Callable[[List[Any]], None]] = None,
    ):
        """
        Initialize batch processor
        
        Args:
            batch_size: Size of each batch
            on_batch_complete: Callback function called after each batch
        """
        self.batch_size = batch_size
        self.on_batch_complete = on_batch_complete
        self.current_batch: List[Any] = []
        self.total_processed = 0
    
    def add(self, item: Any):
        """Add item to current batch"""
        self.current_batch.append(item)
        
        if len(self.current_batch) >= self.batch_size:
            self.flush()
    
    def flush(self):
        """Process current batch"""
        if not self.current_batch:
            return
        
        if self.on_batch_complete:
            self.on_batch_complete(self.current_batch)
        
        self.total_processed += len(self.current_batch)
        self.current_batch = []
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.flush()


def main():
    """Test data loader"""
    print("=" * 70)
    print("Testing Data Loader")
    print("=" * 70)
    
    # Create test files
    test_dir = Path("test_data")
    test_dir.mkdir(exist_ok=True)
    
    test_files = []
    for i in range(10):
        file_path = test_dir / f"test_{i}.txt"
        file_path.write_text(f"Test content {i}")
        test_files.append(file_path)
    
    print(f"\nCreated {len(test_files)} test files")
    
    # Test loader
    def load_file(path: Path) -> str:
        return path.read_text()
    
    def validate_file(data: str) -> bool:
        return len(data) > 0
    
    loader = DataLoader(
        batch_size=3,
        max_workers=2,
        show_progress=True,
    )
    
    results = loader.load_files(test_files, load_file, validate_file)
    
    # Show results
    print(f"\n✓ Loaded {len(results)} files")
    
    stats = loader.get_statistics()
    print(f"\nStatistics:")
    print(f"  Total: {stats['total']}")
    print(f"  Loaded: {stats['loaded']}")
    print(f"  Failed: {stats['failed']}")
    print(f"  Success rate: {stats['success_rate']:.2%}")
    print(f"  Elapsed time: {stats['elapsed_time']:.2f}s")
    print(f"  Avg time per file: {stats['avg_time_per_file']*1000:.2f}ms")
    
    # Cleanup
    import shutil
    shutil.rmtree(test_dir)
    
    print("\n✓ Test completed")


if __name__ == "__main__":
    main()
