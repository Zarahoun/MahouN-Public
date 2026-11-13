"""
Complete Data Ingestion Pipeline
=================================

End-to-end pipeline for ingesting legal documents:
1. Discovery - Find files
2. Loading - Load files
3. Parsing - Parse content
4. Validation - Validate data
5. Transformation - Transform to standard format
6. Storage - Store in database
"""


from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import json

from mahoun.pipelines.data_loader import DataLoader, LoadResult, LoadStatus
from mahoun.pipelines.ingestion.parsers import ParserFactory, ParseResult

@dataclass
class IngestionResult:
    """Result of complete ingestion pipeline"""
    total_files: int
    successful: int
    failed: int
    skipped: int
    documents: List[Dict[str, Any]]
    errors: List[Dict[str, str]]
    metadata: Dict[str, Any]
    
    @property
    def success_rate(self) -> float:
        return self.successful / self.total_files if self.total_files > 0 else 0


class DataIngestionPipeline:
    """
    Complete data ingestion pipeline
    
    Handles the entire process from file discovery to database storage
    """
    
    def __init__(
        self,
        batch_size: int = 100,
        max_workers: int = 4,
        skip_on_error: bool = True,
        validate_data: bool = True,
    ):
        """
        Initialize ingestion pipeline
        
        Args:
            batch_size: Batch size for loading
            max_workers: Maximum parallel workers
            skip_on_error: Skip failed files
            validate_data: Enable data validation
        """
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.skip_on_error = skip_on_error
        self.validate_data = validate_data
        
        # Initialize components
        self.loader = DataLoader(
            batch_size=batch_size,
            max_workers=max_workers,
            skip_on_error=skip_on_error,
        )
        self.parser_factory = ParserFactory()
    
    def ingest_directory(
        self,
        directory: Path,
        file_pattern: str = "*.pdf",
        recursive: bool = True,
    ) -> IngestionResult:
        """
        Ingest all files from a directory
        
        Args:
            directory: Directory to ingest from
            file_pattern: File pattern to match
            recursive: Search recursively
            
        Returns:
            IngestionResult with statistics
        """
        print(f"🔍 Discovering files in {directory}...")
        
        # Step 1: Discover files
        files = self._discover_files(directory, file_pattern, recursive)
        print(f"✓ Found {len(files)} files")
        
        if not files:
            return IngestionResult(
                total_files=0,
                successful=0,
                failed=0,
                skipped=0,
                documents=[],
                errors=[],
                metadata={}
            )
        
        # Step 2: Load and parse files
        print(f"\n📥 Loading and parsing files...")
        documents, errors = self._load_and_parse(files)
        
        # Step 3: Validate (if enabled)
        if self.validate_data:
            print(f"\n✅ Validating documents...")
            documents, validation_errors = self._validate_documents(documents)
            errors.extend(validation_errors)
        
        # Step 4: Transform to standard format
        print(f"\n🔄 Transforming documents...")
        documents = self._transform_documents(documents)
        
        # Create result
        result = IngestionResult(
            total_files=len(files),
            successful=len(documents),
            failed=len(errors),
            skipped=0,
            documents=documents,
            errors=errors,
            metadata={
                'directory': str(directory),
                'file_pattern': file_pattern,
                'timestamp': datetime.now().isoformat(),
            }
        )
        
        # Print summary
        self._print_summary(result)
        
        return result
    
    def _discover_files(
        self,
        directory: Path,
        pattern: str,
        recursive: bool,
    ) -> List[Path]:
        """Discover files matching pattern"""
        if recursive:
            files = list(directory.rglob(pattern))
        else:
            files = list(directory.glob(pattern))
        
        return sorted(files)
    
    def _load_and_parse(
        self,
        files: List[Path],
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
        """Load and parse files"""
        documents = []
        errors = []
        
        def parse_file(file_path: Path) -> Dict[str, Any]:
            """Parse a single file"""
            # Get appropriate parser
            parser = self.parser_factory.get_parser(file_path)
            
            # Parse file
            result = parser.parse(file_path)
            
            if not result.success:
                raise ValueError(f"Parse failed: {result.errors}")
            
            return {
                'file_path': str(file_path),
                'content': result.data,
                'metadata': result.metadata,
                'parse_result': result,
            }
        
        # Load files
        load_results = self.loader.load_files(files, parse_file)
        
        # Separate successful and failed
        for load_result in load_results:
            if load_result.status == LoadStatus.SUCCESS:
                documents.append(load_result.data)
            else:
                errors.append({
                    'file': str(load_result.file_path),
                    'error': load_result.error or "Unknown error",
                })
        
        return documents, errors
    
    def _validate_documents(
        self,
        documents: List[Dict[str, Any]],
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
        """Validate documents"""
        valid_documents = []
        errors = []
        
        for doc in documents:
            # Basic validation
            if not doc.get('content'):
                errors.append({
                    'file': doc.get('file_path', 'unknown'),
                    'error': 'Empty content',
                })
                continue
            
            if not doc.get('metadata'):
                errors.append({
                    'file': doc.get('file_path', 'unknown'),
                    'error': 'Missing metadata',
                })
                continue
            
            valid_documents.append(doc)
        
        return valid_documents, errors
    
    def _transform_documents(
        self,
        documents: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Transform documents to standard format"""
        transformed = []
        
        for doc in documents:
            # Extract parse result
            parse_result: ParseResult = doc.get('parse_result')
            
            # Create standard document
            standard_doc = {
                'id': self._generate_doc_id(doc['file_path']),
                'source_file': doc['file_path'],
                'content': doc['content'],
                'metadata': {
                    **doc['metadata'],
                    'ingestion_timestamp': datetime.now().isoformat(),
                },
                'status': 'ingested',
            }
            
            transformed.append(standard_doc)
        
        return transformed
    
    def _generate_doc_id(self, file_path: str) -> str:
        """Generate unique document ID"""
        import hashlib
        return hashlib.md5(file_path.encode()).hexdigest()
    
    def _print_summary(self, result: IngestionResult):
        """Print ingestion summary"""
        print("\n" + "=" * 70)
        print("Ingestion Summary")
        print("=" * 70)
        print(f"Total files: {result.total_files}")
        print(f"Successful: {result.successful}")
        print(f"Failed: {result.failed}")
        print(f"Success rate: {result.success_rate:.2%}")
        
        if result.errors:
            print(f"\n⚠️  Errors ({len(result.errors)}):")
            for error in result.errors[:5]:  # Show first 5
                print(f"  - {error['file']}: {error['error']}")
            if len(result.errors) > 5:
                print(f"  ... and {len(result.errors) - 5} more")
        
        print("=" * 70)
    
    def save_results(
        self,
        result: IngestionResult,
        output_file: Path,
    ):
        """Save ingestion results to file"""
        output_data = {
            'summary': {
                'total_files': result.total_files,
                'successful': result.successful,
                'failed': result.failed,
                'success_rate': result.success_rate,
            },
            'documents': result.documents,
            'errors': result.errors,
            'metadata': result.metadata,
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✓ Results saved to {output_file}")


def main():
    """Test ingestion pipeline"""
    print("=" * 70)
    print("Testing Data Ingestion Pipeline")
    print("=" * 70)
    
    # Create test directory
    test_dir = Path("test_ingestion")
    test_dir.mkdir(exist_ok=True)
    
    # Create test files
    for i in range(5):
        file_path = test_dir / f"document_{i}.txt"
        file_path.write_text(f"Legal document content {i}\nThis is a test document.")
    
    # Initialize pipeline
    pipeline = DataIngestionPipeline(
        batch_size=2,
        max_workers=2,
    )
    
    # Ingest directory
    result = pipeline.ingest_directory(
        directory=test_dir,
        file_pattern="*.txt",
        recursive=False,
    )
    
    # Save results
    output_file = test_dir / "ingestion_results.json"
    pipeline.save_results(result, output_file)
    
    # Cleanup
    import shutil
    shutil.rmtree(test_dir)
    
    print("\n✓ Test completed")


if __name__ == "__main__":
    main()
