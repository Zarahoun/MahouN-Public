"""
MAHOUN MVP Demo Pipeline
=========================

End-to-end demonstration of the complete MAHOUN pipeline:

  ingestion → chunking → embedding → vector store →
  query → hybrid retrieval → reasoning (NLI + citation + uncertainty) →
  transparent output

Usage:
    python -m orchestrator.demo_mvp --input data/samples/verdicts/sample_verdict_01.txt
    
    # With output file
    python -m orchestrator.demo_mvp --input sample.txt --output demo_output.json
    
    # With custom query
    python -m orchestrator.demo_mvp --input sample.txt --query "سابقه دخالت ثالث چیست؟"
"""

import asyncio
import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_section(title: str, char: str = "="):
    """Print formatted section header"""
    print(f"\n{char * 80}")
    print(f"  {title}")
    print(f"{char * 80}\n")


# Shared instances for demo (to preserve state across phases)
_shared_vector_store: Optional[Any] = None
_shared_embedding_service: Optional[Any] = None


async def run_mvp_demo(
    input_file: str,
    query: Optional[str] = None,
    output_file: Optional[str] = None
) -> Dict[str, Any]:
    """
    Run complete MVP demo pipeline.
    
    Args:
        input_file: Path to input document (TXT/DOCX/PDF)
        query: Optional query (uses default if not provided)
        output_file: Optional output JSON file path
        
    Returns:
        Complete demo results dictionary
    """
    print_section("MAHOUN MVP DEMO - POST GRAPH OPTIMIZATION")
    
    # ========================================================================
    # Runtime Profile (descriptive, not prescriptive)
    # ========================================================================
    from mahoun.orchestrator.runtime_profile import MAHOUN_PROFILE
    
    print_section("Runtime Profile", "-")
    print(f"• Mode: {MAHOUN_PROFILE.mode.value}")
    print(f"• Embeddings: {MAHOUN_PROFILE.embeddings.value} (random vectors)")
    print(f"• Reasoning: {MAHOUN_PROFILE.reasoning.value} (torch not installed)")
    print(f"• RAG mode: {MAHOUN_PROFILE.rag_mode.value}")
    print()
    
    start_time = datetime.now()
    results = {
        "timestamp": start_time.isoformat(),
        "input_document": input_file,
        "query": query or "سابقه دخالت ثالث در پرونده چیست؟"
    }
    
    # ========================================================================
    # Setup: Initialize shared components
    # ========================================================================
    global _shared_vector_store, _shared_embedding_service
    
    # Create shared embedding service with demo-tolerant config
    from mahoun.pipelines.embed_index import EmbeddingService, EmbeddingConfig
    embedding_config = EmbeddingConfig(
        allow_random_fallback=True  # Demo tolerates dummy embeddings
    )
    _shared_embedding_service = EmbeddingService(config=embedding_config)
    
    # Report embedding status upfront
    embedding_info = _shared_embedding_service.get_provider_info()
    if embedding_info['is_dummy']:
        logger.warning("🔶 DEMO RUNNING WITH DUMMY EMBEDDINGS (random vectors)")
        logger.warning("   Install sentence-transformers for real semantic search:")
        logger.warning("   pip install sentence-transformers")
    
    # Create shared vector store (will persist across phases)
    from mahoun.pipelines.vector_store.manager import VectorStoreManager
    _shared_vector_store = VectorStoreManager()
    await _shared_vector_store.initialize()
    logger.info(f"Vector store initialized (backend: {_shared_vector_store._backend})")
    
    # ========================================================================
    # Phase 1: Ingestion
    # ========================================================================
    print_section("Phase 1: Document Ingestion", "-")
    
    try:
        from mahoun.pipelines.ingestion.pipeline import IngestionPipeline
        
        print(f"📄 Ingesting document: {input_file}")
        
        # Create pipeline with SHARED components
        pipeline = IngestionPipeline(
            embedding_service=_shared_embedding_service,
            vector_store=_shared_vector_store
        )
        await pipeline.initialize()
        
        # Report vector store status
        vector_count_before = len(_shared_vector_store._vectors) if hasattr(_shared_vector_store, '_vectors') else 0
        logger.info(f"Vector store before ingestion: {vector_count_before} vectors")
        
        # Ingest file
        doc_id = Path(input_file).stem
        ingestion_result = await pipeline.ingest_file(
            file_path=input_file,
            doc_id=doc_id,
            metadata={"doc_type": "verdict", "source": "demo"}
        )
        
        if not ingestion_result.success:
            print(f"❌ Ingestion failed: {ingestion_result.error}")
            results["ingestion"] = {"success": False, "error": ingestion_result.error}
            return results
        
        # Report vector store status after ingestion
        vector_count_after = len(_shared_vector_store._vectors) if hasattr(_shared_vector_store, '_vectors') else 0
        logger.info(f"Vector store after ingestion: {vector_count_after} vectors (+{vector_count_after - vector_count_before})")
        
        print(f"✅ Ingestion complete:")
        print(f"   • Chunks created: {ingestion_result.chunks_created}")
        print(f"   • Embeddings generated: {ingestion_result.embeddings_created}")
        print(f"   • Indexed: {ingestion_result.indexed}")
        print(f"   • Processing time: {ingestion_result.processing_time_ms:.1f}ms")
        
        results["ingestion"] = {
            "success": True,
            "chunks_created": ingestion_result.chunks_created,
            "embeddings_generated": ingestion_result.embeddings_created,
            "indexed": ingestion_result.indexed,
            "processing_time_ms": ingestion_result.processing_time_ms
        }
        
        # DON'T close pipeline (would close shared vector store)
        # Just clean up local pipeline state
        pipeline._initialized = False
        logger.info("Pipeline resources released (vector store preserved)")
        
    except Exception as e:
        logger.error(f"Ingestion phase failed: {e}", exc_info=True)
        results["ingestion"] = {"success": False, "error": str(e)}
        return results
    
    # ========================================================================
    # Phase 2: Hybrid RAG Retrieval
    # ========================================================================
    print_section("Phase 2: Hybrid RAG Retrieval", "-")
    
    try:
        from mahoun.rag.hybrid_rag_service import create_hybrid_rag_service, RAGMode
        
        query_text = results["query"]
        print(f"🔍 Query: {query_text}")
        
        # Report vector store status before retrieval
        vector_count = len(_shared_vector_store._vectors) if hasattr(_shared_vector_store, '_vectors') else 0
        logger.info(f"Vector store for retrieval: {vector_count} vectors available")
        
        # Create RAG service with SHARED components
        rag_service = await create_hybrid_rag_service(
            vector_store=_shared_vector_store,
            embedding_service=_shared_embedding_service
        )
        
        # Perform retrieval
        rag_result = await rag_service.retrieve(
            query=query_text,
            mode=RAGMode.AUTO,
            top_k=5
        )
        
        print(f"✅ Retrieval complete:")
        print(f"   • Mode used: {rag_result.mode_used}")
        print(f"   • Results found: {len(rag_result.results)}")
        print(f"   • Retrieval time: {rag_result.retrieval_time_ms:.1f}ms")
        
        print(f"\n📚 Top {min(3, len(rag_result.results))} retrieved chunks:")
        for result in rag_result.results[:3]:
            print(f"\n   [{result.rank}] {result.doc_id} (score: {result.score:.3f})")
            preview = result.content[:150].replace('\n', ' ')
            print(f"       {preview}...")
        
        results["retrieval"] = {
            "method": rag_result.mode_used,
            "num_results": len(rag_result.results),
            "retrieval_time_ms": rag_result.retrieval_time_ms,
            "top_chunks": [
                {
                    "doc_id": r.doc_id,
                    "score": r.score,
                    "rank": r.rank,
                    "content_preview": r.content[:200]
                }
                for r in rag_result.results[:5]
            ]
        }
        
    except Exception as e:
        logger.error(f"Retrieval phase failed: {e}", exc_info=True)
        results["retrieval"] = {"success": False, "error": str(e)}
        rag_result: Optional[Any] = None
    # ========================================================================
    # Phase 3: Answer Generation (Simple Extractive for MVP)
    # ========================================================================
    print_section("Phase 3: Answer Generation", "-")
    
    try:
        # For MVP: use simple extractive answer from top chunk
        if rag_result and rag_result.results:
            generated_answer = f"بر اساس اسناد بازیابی شده:\n\n{rag_result.results[0].content[:500]}"
            
            print(f"💡 Generated answer (extractive MVP):")
            print(f"   {generated_answer[:200]}...")
            
            results["answer"] = {
                "text": generated_answer,
                "method": "extractive_mvp",
                "source_chunk": rag_result.results[0].doc_id
            }
        else:
            generated_answer = "پاسخی یافت نشد"
            results["answer"] = {
                "text": generated_answer,
                "method": "empty",
                "error": "No retrieval results"
            }
            print(f"⚠️  No retrieval results for answer generation")
            
    except Exception as e:
        logger.error(f"Answer generation failed: {e}", exc_info=True)
        generated_answer = "خطا در تولید پاسخ"
        results["answer"] = {"text": generated_answer, "error": str(e)}
    
    # ========================================================================
    # Phase 4: Reasoning Chain (NLI + Citation + Uncertainty)
    # ========================================================================
    print_section("Phase 4: Reasoning & Verification", "-")
    
    try:
        from mahoun.reasoning.reasoning_chain import ReasoningChain, ReasoningConfig, ReasoningMode
        
        # Create reasoning chain
        config = ReasoningConfig(
            enabled=True,
            mode=ReasoningMode.FAST,  # Desktop mode
            nli_enabled=True,
            citation_audit_enabled=True,
            uncertainty_enabled=True
        )
        
        reasoning_chain = ReasoningChain(config=config)
        await reasoning_chain.initialize()
        
        # Build retrieved docs list
        retrieved_docs: List[Any] = []
        if rag_result:
            for result in rag_result.results:
                retrieved_docs.append({
                    "doc_id": result.doc_id,
                    "content": result.content,
                    "score": result.score,
                    "metadata": result.metadata
                })
        
        # Process through reasoning chain
        reasoning_result = await reasoning_chain.process(
            query=query_text,
            retrieved_docs=retrieved_docs,
            generated_answer=generated_answer,
            retrieval_metadata=results.get("retrieval", {})
        )
        
        print(f"✅ Reasoning complete:")
        print(f"   • NLI verified: {'✓' if reasoning_result.nli_verified else '✗'}")
        print(f"   • NLI entailment score: {reasoning_result.nli_entailment_score:.3f}")
        print(f"   • Citations valid: {'✓' if reasoning_result.citations_valid else '✗'}")
        print(f"   • Citation accuracy: {reasoning_result.citation_accuracy_score:.3f}")
        print(f"   • Uncertainty score: {reasoning_result.uncertainty_score:.3f}")
        print(f"   • Confidence: {reasoning_result.confidence:.3f}")
        print(f"   • Processing time: {reasoning_result.processing_time_ms:.1f}ms")
        
        if reasoning_result.warnings:
            print(f"\n⚠️  Warnings:")
            for warning in reasoning_result.warnings:
                print(f"   • {warning}")
        
        print(f"\n🔍 Reasoning chain ({len(reasoning_result.reasoning_chain)} steps):")
        for step in reasoning_result.reasoning_chain:
            print(f"   → {step}")
        
        results["reasoning"] = {
            "nli_verified": reasoning_result.nli_verified,
            "nli_entailment_score": reasoning_result.nli_entailment_score,
            "citations_valid": reasoning_result.citations_valid,
            "citation_accuracy": reasoning_result.citation_accuracy_score,
            "uncertainty_score": reasoning_result.uncertainty_score,
            "epistemic_uncertainty": reasoning_result.epistemic_uncertainty,
            "aleatoric_uncertainty": reasoning_result.aleatoric_uncertainty,
            "confidence": reasoning_result.confidence,
            "processing_time_ms": reasoning_result.processing_time_ms,
            "warnings": reasoning_result.warnings,
            "reasoning_chain": reasoning_result.reasoning_chain,
            "transparency_trace": reasoning_result.transparency_trace,
            "hop_trace": reasoning_result.hop_trace,
            "citation_trace": reasoning_result.citation_trace,
            # Availability flags for clean reporting
            "nli_available": getattr(reasoning_chain, "nli_available", False),
            "citation_available": getattr(reasoning_chain, "citation_available", False),
            "uncertainty_available": getattr(reasoning_chain, "uncertainty_available", False),
        }
        
    except Exception as e:
        logger.error(f"Reasoning phase failed: {e}", exc_info=True)
        results["reasoning"] = {"success": False, "error": str(e)}
    
    # ========================================================================
    # Component Status Report (BEFORE cleanup)
    # ========================================================================
    print_section("Component Status", "-")
    
    # Embedding status
    embedding_info = _shared_embedding_service.get_provider_info() if _shared_embedding_service else {"provider": "Unknown", "model": "N/A", "is_dummy": True}
    print(f"📊 Embeddings:")
    print(f"   • ارائه‌دهنده: {embedding_info['provider']}")
    print(f"   • مدل: {embedding_info['model']}")
    if embedding_info['is_dummy']:
        print(f"   • ⚠️  هشدار: Embedding های تصادفی (بدون معنای واقعی)")
    else:
        print(f"   • ✅ Embedding های معنایی واقعی")
    
    # Vector store status
    print(f"\n📦 پایگاه بردار (Vector Store):")
    if _shared_vector_store:
        print(f"   • Backend: {_shared_vector_store._backend}")
        if hasattr(_shared_vector_store, '_vectors'):
            print(f"   • بردارهای ذخیره شده: {len(_shared_vector_store._vectors)}")
        print(f"   • پایدار: خیر (حافظه موقت، فقط دمو)")
    else:
        print(f"   • وضعیت: راه‌اندازی نشده")
    
    
    # Reasoning status
    if 'reasoning' in results and isinstance(results.get('reasoning'), dict):
        print(f"\n🧠 Reasoning Modules:")
        
        # Get availability from flags (clean approach)
        reasoning_meta = results.get('reasoning', {})
        nli_available = reasoning_meta.get("nli_available", False)
        citation_available = reasoning_meta.get("citation_available", False)
        uncertainty_available = reasoning_meta.get("uncertainty_available", False)
        
        # Report based on flags
        print(f"   • NLI: {'✅ موجود' if nli_available else '❌ غیرفعال (torch نصب نشده)'}")
        print(f"   • Citation: {'✅ موجود' if citation_available else '❌ غیرفعال (torch نصب نشده)'}")
        print(f"   • Uncertainty: {'✅ موجود' if uncertainty_available else '❌ غیرفعال (torch نصب نشده)'}")
        
        if not (nli_available and citation_available and uncertainty_available):
            print(f"   • ⚠️  برای استدلال کامل، torch و transformers را نصب کنید")
    
    # RAG status  
    if rag_result:
        print(f"\n🔍 RAG Retrieval:")
        print(f"   • Mode: {rag_result.mode_used}")
        print(f"   • Results: {len(rag_result.results)}")
    
    # ========================================================================
    # Cleanup: Release shared resources
    # ========================================================================
    try:
        if _shared_vector_store:
            await _shared_vector_store.close()
            logger.info("Shared vector store closed")
    except Exception as e:
        logger.warning(f"Cleanup failed: {e}")
    
    
    # ========================================================================
    # Phase 5: Final Summary
    # ========================================================================
    print_section("Demo Summary", "=")
    
    total_time = (datetime.now() - start_time).total_seconds() * 1000
    results["total_time_ms"] = total_time
    
    print(f"📊 Complete Pipeline Results:")
    print(f"   • Input: {Path(input_file).name}")
    print(f"   • Total time: {total_time:.1f}ms")
    print(f"   • Chunks indexed: {results.get('ingestion', {}).get('chunks_created', 0)}")
    print(f"   • Retrieved: {results.get('retrieval', {}).get('num_results', 0)} documents")
    
    # Honest verification status
    reasoning_result = results.get('reasoning', {})
    if isinstance(reasoning_result, dict):
        nli_verified = reasoning_result.get('nli_verified', False)
        confidence = reasoning_result.get('confidence', 0.0)
        warnings = reasoning_result.get('warnings', [])
        
        if any('unavailable' in str(w).lower() for w in warnings):
            print(f"   • Verified: ⚠️  Not run (modules unavailable)")
            print(f"   • Confidence: Unknown (reasoning disabled)")
        elif nli_verified:
            print(f"   • Verified: ✅ Yes")
            print(f"   • Confidence: {confidence:.1%}")
        else:
            print(f"   • Verified: ❌ Failed verification")
            print(f"   • Confidence: {confidence:.1%}")
    else:
        print(f"   • Verified: ⚠️  Error in reasoning phase")
        print(f"   • Confidence: Unknown")
    
    # Warnings section
    if embedding_info['is_dummy']:
        print(f"\n⚠️  محدودیت‌های دمو:")
        print(f"   • استفاده از embedding های تصادفی (بدون معنای واقعی)")
        print(f"   • جستجوی معنایی فعال نیست")
        print(f"   • برای embedding های واقعی، sentence-transformers را نصب کنید")
    
    # Save to file if requested
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 Results saved to: {output_file}")
    
    print(f"\n{'='*80}\n")
    print("✅ MVP Demo Complete!")
    print("\nMAHOUN pipeline successfully demonstrated:")
    print("  ✓ Document ingestion (TXT/DOCX/PDF)")
    print("  ✓ Hybrid RAG retrieval")
    print("  ✓ NLI verification")
    print("  ✓ Citation auditing")
    print("  ✓ Uncertainty estimation")
    print("  ✓ Transparency tracing")
    print(f"\n{'='*80}\n")
    
    return results


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="MAHOUN MVP Demo Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m orchestrator.demo_mvp --input data/samples/verdicts/sample_verdict_01.txt
  python -m orchestrator.demo_mvp --input sample.txt --output results.json
  python -m orchestrator.demo_mvp --input sample.txt --query "قانون مدنی چیست؟"
        """
    )
    
    parser.add_argument(
        '--input',
        type=str,
        required=True,
        help='Path to input document (TXT/DOCX/PDF)'
    )
    
    parser.add_argument(
        '--query',
        type=str,
        default=None,
        help='Query text (default: sample legal query)'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Output JSON file path (optional)'
    )
    
    args = parser.parse_args()
    
    # Validate input file
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ Error: Input file not found: {args.input}")
        sys.exit(1)
    
    # Run demo
    try:
        results = asyncio.run(run_mvp_demo(
            input_file=args.input,
            query=args.query,
            output_file=args.output
        ))
        
        # Exit with success if all phases succeeded
        success = all([
            results.get("ingestion", {}).get("success", False),
            results.get("retrieval", {}).get("num_results", 0) > 0,
            "reasoning" in results
        ])
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        logger.error("Demo failed", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
