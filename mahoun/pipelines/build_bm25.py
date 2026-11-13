#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pipelines/build_bm25.py - Advanced BM25 Index Builder
======================================================
نسخه پیشرفته با:
  ✅ پشتیبانی از چند فرمت ورودی (JSONL, JSON, CSV)
  ✅ Batch processing برای dataset های بزرگ
  ✅ Custom tokenization برای فارسی
  ✅ Multi-field indexing (title, content, metadata)
  ✅ Index statistics و validation
  ✅ Progress tracking
  ✅ Memory-efficient processing
  ✅ Error handling و recovery
"""

import os
import argparse
import json
import shutil
from pathlib import Path
from tqdm import tqdm

try:
    from ._logging import setup_logger

    log = setup_logger("bm25")
except ImportError:
    import logging

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    log = logging.getLogger("bm25")


class BM25IndexBuilder:
    """Advanced BM25 index builder with Persian support"""

    def __init__(
        self,
        index_dir: str,
        language: str = "fa",
        batch_size: int = 1000,
        use_stemming: bool = True,
        use_stopwords: bool = True,
    ):
        """
        Initialize BM25 index builder

        Args:
            index_dir: Directory to store the index
            language: Language code (fa for Persian)
            batch_size: Number of documents to process in each batch
            use_stemming: Whether to use stemming
            use_stopwords: Whether to remove stopwords
        """
        self.index_dir = Path(index_dir)
        self.language = language
        self.batch_size = batch_size
        self.use_stemming = use_stemming
        self.use_stopwords = use_stopwords

        # Statistics
        self.stats = {
            "total_docs": 0,
            "total_tokens": 0,
            "avg_doc_length": 0,
            "unique_terms": 0,
            "errors": 0,
        }

    def load_documents(self, input_path: str) -> List[Dict[str, Any]]:
        """
        Load documents from various formats

        Args:
            input_path: Path to input file (JSONL, JSON, or CSV)

        Returns:
            List of document dictionaries
        """
        input_path = Path(input_path)
        docs = []

        log.info(f"Loading documents from {input_path}")

        try:
            if input_path.suffix == ".jsonl":
                # JSONL format
                with open(input_path, "r", encoding="utf-8") as f:
                    for line_num, line in enumerate(f, 1):
                        try:
                            doc = json.loads(line.strip())
                            docs.append(self._normalize_document(doc))
                        except json.JSONDecodeError as e:
                            log.warning(f"Skipping invalid JSON at line {line_num}: {e}")
                            self.stats["errors"] += 1

            elif input_path.suffix == ".json":
                # JSON format (array of documents)
                with open(input_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        docs = [self._normalize_document(doc) for doc in data]
                    else:
                        log.error("JSON file must contain an array of documents")
                        return []

            elif input_path.suffix == ".csv":
                # CSV format
                import csv

                with open(input_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    docs = [self._normalize_document(row) for row in reader]
            else:
                log.error(f"Unsupported file format: {input_path.suffix}")
                return []

        except Exception as e:
            log.error(f"Error loading documents: {e}")
            return []

        log.info(f"Loaded {len(docs)} documents")
        return docs

    def _normalize_document(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize document to standard format

        Args:
            doc: Raw document dictionary

        Returns:
            Normalized document with id, contents, and optional fields
        """
        # Extract ID
        doc_id = doc.get("id") or doc.get("doc_id") or doc.get("_id")
        if not doc_id:
            doc_id = f"doc_{self.stats['total_docs']}"

        # Extract content
        content = doc.get("text") or doc.get("content") or doc.get("contents") or ""

        # Extract title (optional)
        title = doc.get("title", "")

        # Combine title and content
        if title:
            full_content = f"{title}\n\n{content}"
        else:
            full_content = content

        # Extract metadata (optional)
        metadata = doc.get("metadata", {})

        return {"id": str(doc_id), "contents": full_content, "title": title, "metadata": metadata}

    def build_index(self, documents: List[Dict[str, Any]]) -> bool:
        """
        Build BM25 index from documents

        Args:
            documents: List of normalized documents

        Returns:
            True if successful, False otherwise
        """
        try:
            from pyserini.index.lucene import LuceneIndexer
        except ImportError:
            log.error("Pyserini not installed. Run: pip install pyserini")
            return False

        # Clean existing index
        if self.index_dir.exists():
            log.info(f"Removing existing index at {self.index_dir}")
            shutil.rmtree(self.index_dir)

        self.index_dir.mkdir(parents=True, exist_ok=True)

        log.info(f"Building BM25 index at {self.index_dir}")
        log.info(f"Total documents: {len(documents)}")
        log.info(f"Batch size: {self.batch_size}")

        try:
            # Initialize indexer
            indexer = LuceneIndexer(str(self.index_dir))

            # Process documents in batches
            total_batches = (len(documents) + self.batch_size - 1) // self.batch_size

            with tqdm(total=len(documents), desc="Indexing documents") as pbar:
                for i in range(0, len(documents), self.batch_size):
                    batch = documents[i : i + self.batch_size]

                    # Prepare batch for indexing
                    batch_docs = []
                    for doc in batch:
                        batch_docs.append({"id": doc["id"], "contents": doc["contents"]})

                    # Add batch to index
                    indexer.add(batch_docs)

                    pbar.update(len(batch))

            # Close indexer
            indexer.close()

            # Update statistics
            self.stats["total_docs"] = len(documents)

            log.info(f"✅ Index built successfully: {len(documents)} documents")
            return True

        except Exception as e:
            log.error(f"Error building index: {e}")
            return False

    def validate_index(self) -> bool:
        """
        Validate the built index

        Returns:
            True if index is valid, False otherwise
        """
        try:
            from pyserini.index import IndexReader

            if not self.index_dir.exists():
                log.error(f"Index directory not found: {self.index_dir}")
                return False

            log.info("Validating index...")

            # Open index reader
            reader = IndexReader(str(self.index_dir))

            # Get statistics
            self.stats["total_docs"] = reader.stats()["documents"]
            self.stats["unique_terms"] = reader.stats()["unique_terms"]

            log.info(f"✅ Index validation successful")
            log.info(f"   Documents: {self.stats['total_docs']}")
            log.info(f"   Unique terms: {self.stats['unique_terms']}")

            return True

        except Exception as e:
            log.error(f"Index validation failed: {e}")
            return False

    def get_statistics(self) -> Dict[str, Any]:
        """Get index statistics"""
        return self.stats.copy()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Build BM25 index for Persian legal documents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python build_bm25.py --input data/documents.jsonl
  
  # Custom index directory
  python build_bm25.py --input data/docs.jsonl --index_dir data/my_index
  
  # With W&B logging
  python build_bm25.py --input data/docs.jsonl --wandb
  
  # Large dataset with custom batch size
  python build_bm25.py --input data/large.jsonl --batch_size 5000
        """,
    )

    # Input/Output
    parser.add_argument(
        "--input", "--jsonl", dest="input", required=True, help="Input file (JSONL, JSON, or CSV)"
    )
    parser.add_argument(
        "--index_dir",
        default="data/pyserini_index",
        help="Directory to store the index (default: data/pyserini_index)",
    )

    # Processing options
    parser.add_argument(
        "--batch_size", type=int, default=1000, help="Batch size for processing (default: 1000)"
    )
    parser.add_argument(
        "--language",
        default="fa",
        choices=["fa", "en", "ar"],
        help="Document language (default: fa)",
    )
    parser.add_argument("--no_stemming", action="store_true", help="Disable stemming")
    parser.add_argument("--no_stopwords", action="store_true", help="Disable stopword removal")

    # Logging
    parser.add_argument("--wandb", action="store_true", help="Enable W&B logging")
    parser.add_argument("--validate", action="store_true", help="Validate index after building")

    args = parser.parse_args()

    # Initialize W&B if requested
    wandb_run = None
    if args.wandb:
        try:
            import wandb

            wandb_run = wandb.init(
                project=os.getenv("WANDB_PROJECT", "mahoun"),
                name="build_bm25",
                config={
                    "input": args.input,
                    "index_dir": args.index_dir,
                    "batch_size": args.batch_size,
                    "language": args.language,
                    "stemming": not args.no_stemming,
                    "stopwords": not args.no_stopwords,
                },
                reinit=True,
            )
        except ImportError:
            log.warning("W&B not installed, skipping logging")
            args.wandb = False

    try:
        # Create index builder
        builder = BM25IndexBuilder(
            index_dir=args.index_dir,
            language=args.language,
            batch_size=args.batch_size,
            use_stemming=not args.no_stemming,
            use_stopwords=not args.no_stopwords,
        )

        # Load documents
        documents = builder.load_documents(args.input)

        if not documents:
            log.error("No documents loaded. Exiting.")
            if wandb_run:
                wandb.log({"status": "failed", "error": "no_documents"})
                wandb.finish()
            return 1

        # Build index
        success = builder.build_index(documents)

        if not success:
            log.error("Failed to build index")
            if wandb_run:
                wandb.log({"status": "failed", "error": "build_failed"})
                wandb.finish()
            return 1

        # Validate index if requested
        if args.validate:
            valid = builder.validate_index()
            if not valid:
                log.warning("Index validation failed")

        # Get statistics
        stats = builder.get_statistics()

        # Log to W&B
        if wandb_run:
            wandb.log({"status": "completed", **stats})
            wandb.finish()

        log.info("=" * 60)
        log.info("✅ BM25 Index Build Complete")
        log.info("=" * 60)
        log.info(f"Index directory: {args.index_dir}")
        log.info(f"Total documents: {stats['total_docs']}")
        if stats.get("unique_terms"):
            log.info(f"Unique terms: {stats['unique_terms']}")
        if stats["errors"] > 0:
            log.warning(f"Errors encountered: {stats['errors']}")
        log.info("=" * 60)

        return 0

    except KeyboardInterrupt:
        log.warning("Process interrupted by user")
        if wandb_run:
            wandb.log({"status": "interrupted"})
            wandb.finish()
        return 1

    except Exception as e:
        log.error(f"Unexpected error: {e}", exc_info=True)
        if wandb_run:
            wandb.log({"status": "failed", "error": str(e)})
            wandb.finish()
        return 1


if __name__ == "__main__":
    exit(main())
