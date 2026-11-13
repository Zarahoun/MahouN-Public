"""
Vector Store Manager - MVP Implementation
==========================================
Simplified vector store manager that wraps ultra_systems.vector_store.

This provides a clean interface for:
- Inserting embeddings with metadata
- Querying vectors
- Managing collections

For MVP, this delegates to UltraChromaDBBackend.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def _run_async(coro):
    """
    Run an async coroutine from a sync context, handling the case where
    an event loop may already be running.
    
    This is necessary because `asyncio.run()` cannot be called from within
    an already-running event loop (e.g., when called from an async API endpoint).
    
    Args:
        coro: The coroutine to run
    
    Returns:
        The result of the coroutine
    """
    try:
        # Check if there's already a running event loop
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop, safe to use asyncio.run()
        return asyncio.run(coro)
    
    # There's a running loop - we need to handle this differently
    # Create a new task in the existing loop
    import concurrent.futures
    import threading
    
    # Use a thread to run the async code if we're in an async context
    result: Optional[Any] = None
    exception: Optional[Any] = None
    def run_in_thread():
        nonlocal result, exception
        try:
            # Create a new event loop for this thread
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                result = new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
        except Exception as e:
            exception = e
    
    thread = threading.Thread(target=run_in_thread)
    thread.start()
    thread.join()
    
    if exception:
        raise exception
    return result


@dataclass
class VectorStoreConfig:
    """Vector store configuration"""
    backend: str = "chromadb"  # chromadb, faiss, memory
    persist_directory: str = "./vector_store_data"
    collection_name: str = "mahoun_documents"
    dimension: int = 1024
    distance_metric: str = "cosine"


class VectorStoreManager:
    """
    Vector Store Manager for MAHOUN MVP.
    
    This class provides a simplified interface to vector storage,
    delegating to ultra_systems.vector_store for the actual implementation.
    
    Usage:
        manager = VectorStoreManager()
        await manager.initialize()
        
        # Insert embeddings
        await manager.insert(
            ids=["doc1_chunk0", "doc1_chunk1"],
            embeddings=[[0.1, 0.2, ...], [0.3, 0.4, ...]],
            metadatas=[{"doc_id": "doc1", "text": "..."}, ...]
        )
        
        # Query
        results = await manager.query(
            query_embedding=[0.5, 0.6, ...],
            top_k=10
        )
    """
    
    def __init__(self, config: Optional[VectorStoreConfig] = None):
        """
        Initialize Vector Store Manager.
        
        Args:
            config: Optional configuration. Uses defaults if not provided.
        """
        self.config = config or VectorStoreConfig()
        self._backend = None
        self._initialized = False
        
        # Statistics
        self.stats = {
            "inserts": 0,
            "queries": 0,
            "total_vectors": 0
        }
        
        logger.info(f"VectorStoreManager initialized (backend: {self.config.backend})")
    
    async def initialize(self):
        """
        Initialize the vector store backend.
        
        Priority order:
        1. ChromaDB (if installed) - production backend with persistence
        2. Pickle-based persistence - fallback with disk persistence
        3. In-memory dict - last resort (no persistence)
        """
        if self._initialized:
            return
        
        # Try 1: ChromaDB (production-grade)
        try:
            import chromadb
            from chromadb.config import Settings
            
            # Initialize ChromaDB with persistence (using new PersistentClient API)
            chroma_client = chromadb.PersistentClient(
                path=self.config.persist_directory,
                settings=Settings(anonymized_telemetry=False)
            )
            
            # Get or create collection
            # Note: ChromaDB auto-detects dimension from first embedding
            # We only set dimension in metadata for reference
            try:
                # Try to get existing collection first
                existing_collection = chroma_client.get_collection(
                    name=self.config.collection_name
                )
                self._backend = existing_collection
                logger.info(f"Using existing collection: {self.config.collection_name} ({existing_collection.count()} docs)")
            except Exception:
                # Create new collection if it doesn't exist
                self._backend = chroma_client.create_collection(
                    name=self.config.collection_name,
                    metadata={"dimension": self.config.dimension}
                )
                logger.info(f"Created new collection: {self.config.collection_name}")
            
            self._backend_type = "chromadb"
            self._initialized = True
            logger.info(f"✅ ChromaDB initialized (persisted to {self.config.persist_directory})")
            return
            
        except ImportError:
            logger.debug("ChromaDB not available, trying JSON backend...")
        except Exception as e:
            logger.warning(f"ChromaDB initialization failed: {e}, falling back...")
        
        # Try 2: JSON-based persistence (SECURE - no pickle)
        try:
            from pathlib import Path
            from mahoun.core.serialization import SafeSerializer, SerializationError
            
            self._json_path = Path(self.config.persist_directory) / "vectors.json"
            self._json_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Check for legacy pickle file and migrate
            legacy_pickle = Path(self.config.persist_directory) / "vectors.pkl"
            if legacy_pickle.exists() and not self._json_path.exists():
                logger.warning(f"⚠️ Found legacy pickle file, migrating to JSON...")
                from mahoun.core.serialization import migrate_pickle_to_json
                if migrate_pickle_to_json(legacy_pickle, self._json_path):
                    legacy_pickle.rename(legacy_pickle.with_suffix('.pkl.backup'))
                    logger.info("✅ Migration complete, pickle file backed up")
            
            # Load existing data if available
            if self._json_path.exists():
                data = SafeSerializer.load(self._json_path)
                self._vectors = data.get('vectors', {})
                self._metadatas = data.get('metadatas', {})
                logger.info(f"✅ Loaded {len(self._vectors)} vectors from {self._json_path}")
            else:
                self._vectors = {}
                self._metadatas = {}
                logger.info("✅ JSON backend initialized (new)")
            
            self._backend_type = "json"
            self._initialized = True
            return
            
        except Exception as e:
            logger.warning(f"JSON backend failed: {e}, falling back to memory-only...")
        
        # Try 3: In-memory fallback (no persistence)
        try:
            self._vectors = {}
            self._metadatas = {}
            self._backend_type = "memory"
            self._initialized = True
            logger.warning("⚠️  Using in-memory vector store (NO PERSISTENCE)")
            logger.warning("   Install chromadb for production: pip install chromadb")
            return
            
        except Exception as e:
            logger.error(f"Failed to initialize any vector store backend: {e}")
            raise
    
    async def insert(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        texts: Optional[List[str]] = None
    ) -> bool:
        """
        Insert embeddings into the vector store.
        
        Args:
            ids: List of unique IDs for each embedding
            embeddings: List of embedding vectors
            metadatas: Optional list of metadata dicts
            texts: Optional list of text content
        
        Returns:
            True if successful, False otherwise
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # ChromaDB backend
            if self._backend_type == "chromadb":
                # Prepare documents (texts)
                documents = texts if texts else [f"Document {id}" for id in ids]
                
                # Prepare metadatas (add text if not in metadata)
                prepared_metas: List[Any] = []
                for i, id in enumerate(ids):
                    meta = metadatas[i].copy() if (metadatas and i < len(metadatas)) else {}
                    if texts and i < len(texts):
                        meta["text"] = texts[i]
                    # Ensure all values are JSON-serializable
                    meta = {k: v for k, v in meta.items() if isinstance(v, (str, int, float, bool))}
                    prepared_metas.append(meta)
                
                self._backend.add(
                    ids=ids,
                    embeddings=embeddings,
                    documents=documents,
                    metadatas=prepared_metas
                )
                
                # Update stats
                self.stats["inserts"] += 1
                self.stats["total_vectors"] += len(ids)
                
                logger.debug(f"Inserted {len(ids)} vectors into ChromaDB")
                return True
            
            # Pickle or Memory backend
            elif self._backend_type in ["pickle", "memory"]:
                for i, id in enumerate(ids):
                    self._vectors[id] = embeddings[i]
                    if metadatas and i < len(metadatas):
                        meta = metadatas[i].copy() if metadatas[i] else {}
                        if texts and i < len(texts):
                            meta["text"] = texts[i]
                        self._metadatas[id] = meta
                
                # Persist to disk if pickle backend
                if self._backend_type == "pickle":
                    await self._persist_pickle()
                
                # Update stats
                self.stats["inserts"] += 1
                self.stats["total_vectors"] += len(ids)
                
                logger.debug(f"Inserted {len(ids)} vectors into {self._backend_type} store")
                return True
            
            else:
                logger.warning("No vector store backend available")
                return False
            
        except Exception as e:
            logger.error(f"Failed to insert vectors: {e}")
            return False
    
    async def query(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Query the vector store.
        
        Args:
            query_embedding: Query vector
            top_k: Number of results to return
            filter_metadata: Optional metadata filters
        
        Returns:
            List of results with id, score, metadata
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # ChromaDB backend
            if self._backend_type == "chromadb":
                query_result = self._backend.query(
                    query_embeddings=[query_embedding],
                    n_results=top_k,
                    where=filter_metadata
                )
                
                # Format results
                results: List[Any] = []
                if query_result['ids'] and len(query_result['ids']) > 0:
                    for i, id in enumerate(query_result['ids'][0]):
                        # ChromaDB returns distances, convert to similarity (1 - distance for cosine)
                        distance = query_result['distances'][0][i] if query_result.get('distances') else 0
                        score = 1.0 - distance  # Convert distance to similarity
                        
                        metadata = query_result['metadatas'][0][i] if query_result.get('metadatas') else {}
                        
                        results.append({
                            'id': id,
                            'score': score,
                            'metadata': metadata
                        })
                
                # Update stats
                self.stats["queries"] += 1
                
                logger.debug(f"Queried ChromaDB, got {len(results)} results")
                return results
            
            # Pickle or Memory backend
            elif self._backend_type in ["pickle", "memory"]:
                if not hasattr(self, '_vectors') or not self._vectors:
                    logger.warning("No vectors in store, returning empty results")
                    return []
                
                import numpy as np
                
                # Calculate cosine similarity for all vectors
                query_vec = np.array(query_embedding)
                query_norm = np.linalg.norm(query_vec)
                
                similarities: List[Any] = []
                for vec_id, vec in self._vectors.items():
                    vec_array = np.array(vec)
                    vec_norm = np.linalg.norm(vec_array)
                    
                    if query_norm > 0 and vec_norm > 0:
                        similarity = np.dot(query_vec, vec_array) / (query_norm * vec_norm)
                    else:
                        similarity = 0.0
                    
                    similarities.append((vec_id, float(similarity)))
                
                # Sort by similarity (descending)
                similarities.sort(key=lambda x: x[1], reverse=True)
                
                # Format results
                results: List[Any] = []
                for vec_id, score in similarities[:top_k]:
                    results.append({
                        'id': vec_id,
                        'score': score,
                        'metadata': self._metadatas.get(vec_id, {})
                    })
                
                # Update stats
                self.stats["queries"] += 1
                
                logger.debug(f"Queried {self._backend_type} store, got {len(results)} results")
                return results
            
            else:
                logger.warning("No vector store backend available")
                return []
            
        except Exception as e:
            logger.error(f"Failed to query vectors: {e}")
            return []
    
    async def delete(self, ids: List[str]) -> bool:
        """
        Delete vectors by IDs.
        
        Args:
            ids: List of IDs to delete
        
        Returns:
            True if successful
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # ChromaDB backend
            if self._backend_type == "chromadb":
                self._backend.delete(ids=ids)
                self.stats["total_vectors"] -= len(ids)
                logger.debug(f"Deleted {len(ids)} vectors from ChromaDB")
                return True
            
            # Pickle or Memory backend
            elif self._backend_type in ["pickle", "memory"]:
                deleted = 0
                for id in ids:
                    if id in self._vectors:
                        del self._vectors[id]
                        deleted += 1
                    if id in self._metadatas:
                        del self._metadatas[id]
                
                # Persist if pickle
                if self._backend_type == "pickle" and deleted > 0:
                    await self._persist_pickle()
                
                self.stats["total_vectors"] -= deleted
                logger.debug(f"Deleted {deleted} vectors from {self._backend_type} store")
                return True
            
            else:
                logger.warning("No vector store backend available")
                return False
                
        except Exception as e:
            logger.error(f"Failed to delete vectors: {e}")
            return False
    
    async def _persist_json(self):
        """Persist JSON backend to disk (SECURE - no pickle)"""
        try:
            from mahoun.core.serialization import SafeSerializer
            
            data = {
                'vectors': self._vectors,
                'metadatas': self._metadatas
            }
            
            # Write to temp file first, then rename (atomic operation)
            temp_path = self._json_path.with_suffix('.json.tmp')
            SafeSerializer.save(data, temp_path, pretty=False)
            
            temp_path.replace(self._json_path)
            logger.debug(f"Persisted {len(self._vectors)} vectors to {self._json_path}")
            
        except Exception as e:
            logger.error(f"Failed to persist JSON: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics"""
        return self.stats.copy()
    
    async def close(self):
        """Close the vector store connection"""
        try:
            # Persist JSON before closing
            if self._backend_type == "json" and hasattr(self, '_vectors'):
                await self._persist_json()
            
            # ChromaDB persist (if using chromadb)
            if self._backend_type == "chromadb" and self._backend:
                # ChromaDB auto-persists, but we can explicitly persist
                try:
                    if hasattr(self._backend, '_client'):
                        self._backend._client.persist()
                except Exception:
                    pass  # Some ChromaDB versions don't have persist
            
            self._initialized = False
            logger.info(f"Vector store closed ({self._backend_type})")
            
        except Exception as e:
            logger.error(f"Error closing vector store: {e}")


# ============================================================================
# Bootstrap Verdict Ingestion Support
# ============================================================================

def build_verdict_chunks(verdict_struct: Dict[str, Any], source_id: str) -> List[Dict[str, Any]]:
    """
    Build searchable chunks from a parsed verdict structure.
    
    This function is designed for the Bootstrap Verdict Ingestion pipeline (Scenario B).
    It takes a verdict_struct (produced by minimal_verdict_parser) and creates
    a list of text chunks suitable for vector indexing.
    
    Chunking Strategy (Rule-based, NO LLM):
    - Chunk 1: High-level case overview (meta + claims + tags)
    - Chunk 2: First instance summary (if present)
    - Chunk 3: Appeal court reasoning (if present)
    - Chunk 4: Legal references summary
    - Chunk 5: Parties summary
    
    Each chunk includes rich metadata for filtering and retrieval.
    
    Args:
        verdict_struct: Parsed verdict dictionary (from minimal_verdict_parser)
        source_id: Unique identifier (e.g., filename stem)
    
    Returns:
        List of chunk dictionaries, each with:
            - "text": The chunk text (UTF-8 Persian)
            - "metadata": Dict with source_id, section, chunk_index, case_type, etc.
    
    Example:
        >>> chunks = build_verdict_chunks(verdict_struct, "verdict_001")
        >>> for chunk in chunks:
        ...     print(chunk["metadata"]["section"], len(chunk["text"]))
    """
    chunks: List[Any] = []
    chunk_index = 0
    
    # Extract common metadata
    case_meta = verdict_struct.get("case_meta", {})
    case_type = case_meta.get("case_type") or "نامشخص"
    court_level = case_meta.get("court_level") or "نامشخص"
    procedure_stage = case_meta.get("procedure_stage") or "نامشخص"
    is_final = case_meta.get("is_final", False)
    
    # Phase 3 Metadata
    branch = case_meta.get("branch_number")
    city = case_meta.get("city")
    province = case_meta.get("province")
    decision_date = case_meta.get("decision_date")
    
    system_tags = verdict_struct.get("system_tags", [])
    
    # ========================================================================
    # Enterprise NER Entity Metadata (for search filtering)
    # ========================================================================
    entities = verdict_struct.get("entities", {})
    entity_counts = {
        "person_count": len(entities.get("persons", [])),
        "org_count": len(entities.get("organizations", [])),
        "court_count": len(entities.get("courts", [])),
        "law_count": len(entities.get("laws", [])),
        "topic_count": len(entities.get("topics", [])),
    }
    
    # Extract key entity names for filtering (limit to avoid metadata bloat)
    entity_names = {
        "person_names": ",".join([
            p.get("name", "") for p in entities.get("persons", [])[:5]
        ]),
        "org_names": ",".join([
            o.get("name", "") for o in entities.get("organizations", [])[:5]
        ]),
        "law_refs": ",".join([
            l.get("normalized_ref", "") for l in entities.get("laws", [])[:10]
        ]),
    }
    
    # ========================================================================
    # Chunk 1: High-level case overview
    # ========================================================================
    overview_parts: List[Any] = []
    overview_parts.append(f"نوع پرونده: {case_type}")
    overview_parts.append(f"دادگاه: {court_level}")
    overview_parts.append(f"مرحله رسیدگی: {procedure_stage}")
    overview_parts.append(f"قطعیت: {'قطعی' if is_final else 'غیر قطعی'}")
    
    # Add claims (Summary in overview)
    claims = verdict_struct.get("claims", {})
    main_claims = claims.get("main", [])
    if main_claims:
        overview_parts.append("\nخواسته‌ها (خلاصه):")
        for claim in main_claims[:5]:  # Keep summary in overview
            overview_parts.append(f"  • {claim}")
        if len(main_claims) > 5:
            overview_parts.append(f"  • ... و {len(main_claims) - 5} مورد دیگر (در بخش جزئیات)")
    
    # Add execution files
    execution_files = claims.get("execution_files", [])
    if execution_files:
        overview_parts.append("\nپرونده‌های اجرایی:")
        for ef in execution_files[:3]:
            overview_parts.append(f"  • {ef}")
    
    # Add tags
    if system_tags:
        overview_parts.append("\nتگ‌های سیستمی:")
        for tag in system_tags[:10]:
            overview_parts.append(f"  • {tag}")
    
    overview_text = "\n".join(overview_parts)
    
    chunks.append({
        "text": overview_text,
        "metadata": {
            "source_id": source_id,
            "section": "overview",
            "chunk_index": chunk_index,
            "case_type": case_type,
            "court_level": court_level,
            "procedure_stage": procedure_stage,
            "is_final": is_final,
            "branch": branch,
            "city": city,
            "province": province,
            "decision_date": decision_date,
            "tags": system_tags[:20],  # Limit tags in metadata
            # Entity metadata for search filtering
            **entity_counts,
            **entity_names,
        }
    })
    chunk_index += 1
    
    # ========================================================================
    # Chunk 1.5: Detailed Claims (if many)
    # ========================================================================
    if main_claims and len(main_claims) > 0:
        # We chunk ALL claims into dedicated chunks if there are any
        # This ensures full recall even for the first 5 (redundancy is fine/good here)
        # or we can just chunk if > 5.
        # Strategy: If > 5, create dedicated chunks for ALL claims to allow 
        # specific search on "claims" section.
        
        CLAIMS_PER_CHUNK = 20
        for i in range(0, len(main_claims), CLAIMS_PER_CHUNK):
            batch_claims = main_claims[i : i + CLAIMS_PER_CHUNK]
            
            claim_text_parts = [f"لیست کامل خواسته‌ها (بخش {i//CLAIMS_PER_CHUNK + 1}):"]
            for claim in batch_claims:
                claim_text_parts.append(f"  • {claim}")
            
            chunks.append({
                "text": "\n".join(claim_text_parts),
                "metadata": {
                    "source_id": source_id,
                    "section": "claims_list",
                    "chunk_index": chunk_index,
                    "case_type": case_type,
                    "court_level": court_level,
                    "procedure_stage": procedure_stage,
                    "is_final": is_final,
                    "branch": branch,
                    "decision_date": decision_date,
                    "tags": system_tags[:20],
                }
            })
            chunk_index += 1
    
    # ========================================================================
    # Chunk 2: First instance summary
    # ========================================================================
    first_instance = verdict_struct.get("first_instance_summary", {})
    decision = first_instance.get("decision")
    reasoning_keywords = first_instance.get("reasoning_keywords", [])
    
    if decision or reasoning_keywords:
        fi_parts: List[Any] = []
        fi_parts.append("خلاصه رسیدگی دادگاه نخستین:")
        
        if decision:
            fi_parts.append(f"تصمیم: {decision}")
        
        if reasoning_keywords:
            fi_parts.append("\nکلیدواژه‌های استدلال:")
            for kw in reasoning_keywords[:10]:
                fi_parts.append(f"  • {kw}")
        
        fi_text = "\n".join(fi_parts)
        
        chunks.append({
            "text": fi_text,
            "metadata": {
                "source_id": source_id,
                "section": "first_instance_summary",
                "chunk_index": chunk_index,
                "case_type": case_type,
                "court_level": court_level,
                "procedure_stage": procedure_stage,
                "is_final": is_final,
                "branch": branch,
                "decision_date": decision_date,
                "tags": system_tags[:20],
            }
        })
        chunk_index += 1
    
    # ========================================================================
    # Chunk 3: Appeal court reasoning
    # ========================================================================
    appeal = verdict_struct.get("appeal_court_reasoning", {})
    appeal_result = appeal.get("result")
    key_points = appeal.get("key_points", [])
    
    if appeal_result or key_points:
        appeal_parts: List[Any] = []
        appeal_parts.append("استدلال دادگاه تجدیدنظر:")
        
        if appeal_result:
            appeal_parts.append(f"نتیجه: {appeal_result}")
        
        if key_points:
            appeal_parts.append("\nنکات کلیدی:")
            for kp in key_points[:10]:
                appeal_parts.append(f"  • {kp}")
        
        appeal_text = "\n".join(appeal_parts)
        
        chunks.append({
            "text": appeal_text,
            "metadata": {
                "source_id": source_id,
                "section": "appeal_court_reasoning",
                "chunk_index": chunk_index,
                "case_type": case_type,
                "court_level": court_level,
                "procedure_stage": procedure_stage,
                "is_final": is_final,
                "branch": branch,
                "decision_date": decision_date,
                "tags": system_tags[:20],
            }
        })
        chunk_index += 1
    # ========================================================================
    # Chunk 3: Semantic Sections (Phase 3)
    # ========================================================================
    sections = verdict_struct.get("sections", {})
    
    # Summary Section (Ghardeshkar)
    if sections.get("summary"):
        chunks.append({
            "text": f"گردشکار / خلاصه پرونده:\n{sections['summary']}",
            "metadata": {
                "source_id": source_id,
                "section": "summary_text",
                "chunk_index": chunk_index,
                "case_type": case_type,
                "court_level": court_level,
                "is_final": is_final,
                "branch": branch,
                "city": city,
                "decision_date": decision_date,
            }
        })
        chunk_index += 1
        
    # Verdict Section (Raye Dadgah)
    if sections.get("verdict"):
        chunks.append({
            "text": f"متن رأی دادگاه:\n{sections['verdict']}",
            "metadata": {
                "source_id": source_id,
                "section": "verdict_text",
                "chunk_index": chunk_index,
                "case_type": case_type,
                "court_level": court_level,
                "is_final": is_final,
                "branch": branch,
                "city": city,
                "decision_date": decision_date,
            }
        })
        chunk_index += 1

    # ========================================================================
    # Chunk 4: Legal references
    # ========================================================================
    legal_refs = verdict_struct.get("legal_references", {})
    substantive_law = legal_refs.get("substantive_law", [])
    procedural_law = legal_refs.get("procedural_law", [])
    fiqh_principles = legal_refs.get("fiqh_principles", [])
    
    if substantive_law or procedural_law or fiqh_principles:
        legal_parts: List[Any] = []
        legal_parts.append("مراجع قانونی:")
        
        if substantive_law:
            legal_parts.append("\nقوانین موضوعی:")
            for law in substantive_law[:15]:
                legal_parts.append(f"  • {law}")
        
        if procedural_law:
            legal_parts.append("\nقوانین آیین دادرسی:")
            for law in procedural_law[:15]:
                legal_parts.append(f"  • {law}")
        
        if fiqh_principles:
            legal_parts.append("\nاصول فقهی:")
            for principle in fiqh_principles[:10]:
                legal_parts.append(f"  • {principle}")
        
        legal_text = "\n".join(legal_parts)
        
        chunks.append({
            "text": legal_text,
            "metadata": {
                "source_id": source_id,
                "section": "legal_references",
                "chunk_index": chunk_index,
                "case_type": case_type,
                "court_level": court_level,
                "procedure_stage": procedure_stage,
                "is_final": is_final,
                "branch": branch,
                "decision_date": decision_date,
                "tags": system_tags[:20],
            }
        })
        chunk_index += 1
    
    # ========================================================================
    # Chunk 5: Parties summary
    # ========================================================================
    parties = verdict_struct.get("parties", {})
    parties_parts: List[Any] = []
    objector = parties.get("third_party_objector")
    if objector:
        parties_parts.append(f"معترض ثالث: {objector.get('title', '')} {objector.get('name', '')} فرزند {objector.get('father_name', '')}")
    
    objector_attorney = parties.get("third_party_objector_attorney")
    if objector_attorney:
        parties_parts.append(f"وکیل معترض: {objector_attorney.get('title', '')} {objector_attorney.get('name', '')} فرزند {objector_attorney.get('father_name', '')}")
    
    respondents = parties.get("respondents", [])
    if respondents:
        parties_parts.append(f"\nمعترض‌علیهم ({len(respondents)} نفر):")
        for resp in respondents[:5]:
            parties_parts.append(f"  • {resp.get('title', '')} {resp.get('name', '')} فرزند {resp.get('father_name', '')}")
    
    if parties_parts:
        parties_text = "طرفین پرونده:\n" + "\n".join(parties_parts)
        
        chunks.append({
            "text": parties_text,
            "metadata": {
                "source_id": source_id,
                "section": "parties",
                "chunk_index": chunk_index,
                "case_type": case_type,
                "court_level": court_level,
                "procedure_stage": procedure_stage,
                "is_final": is_final,
                "branch": branch,
                "decision_date": decision_date,
                "tags": system_tags[:20],
            }
        })
        chunk_index += 1
    
    logger.debug(f"Built {len(chunks)} chunks for verdict {source_id}")
    return chunks


def index_verdict_struct(verdict_struct: Dict[str, Any], source_id: str) -> None:
    """
    Index a parsed verdict structure into the vector store.
    
    This is the main integration function for Bootstrap Verdict Ingestion (Scenario B).
    It is called by orchestrator.bootstrap_verdict_dataloader when --with-vectorstore is used.
    
    Process:
    1. Build searchable chunks from verdict_struct
    2. Generate embeddings for each chunk
    3. Insert chunks + embeddings + metadata into VectorStore
    4. Handle idempotency (delete old chunks if re-indexing)
    
    Args:
        verdict_struct: Parsed verdict dictionary (from minimal_verdict_parser.parse_verdict_file)
        source_id: Unique identifier for this verdict (e.g., filename stem)
    
    Raises:
        Exception: If vector indexing fails (caller should catch and log)
    
    Example Usage:
        >>> from mahoun.pipelines.vector_store.manager import index_verdict_struct
        >>> verdict_struct = parse_verdict_file("verdict.txt")
        >>> index_verdict_struct(verdict_struct, "verdict_001")
        [INFO] Indexed 5 chunks for verdict verdict_001
    """
    import asyncio
    
    logger.info(f"[VS] Indexing verdict: {source_id}")
    
    # Step 1: Build chunks
    chunks = build_verdict_chunks(verdict_struct, source_id)
    
    if not chunks:
        logger.warning(f"[VS] No chunks generated for {source_id}, skipping indexing")
        return
    
    logger.debug(f"[VS] Generated {len(chunks)} chunks for {source_id}")
    
    # Step 2: Generate embeddings
    try:
        from mahoun.pipelines.embed_index import EmbeddingService
        
        embedding_service = EmbeddingService()
        texts = [chunk["text"] for chunk in chunks]
        
        # Embed all texts
        embeddings = embedding_service.embed_texts(texts)
        
        # Handle both numpy arrays and lists
        if hasattr(embeddings, 'tolist'):
            embeddings = embeddings.tolist()
        elif not isinstance(embeddings, list):
            embeddings = list(embeddings)
        
        if not embeddings or len(embeddings) != len(texts):
            raise ValueError(f"Embedding count mismatch: {len(embeddings)} != {len(texts)}")
        
        logger.debug(f"[VS] Generated {len(embeddings)} embeddings for {source_id}")
        
    except Exception as e:
        logger.error(f"[VS] Failed to generate embeddings for {source_id}: {e}")
        raise
    
    # Step 3: Prepare IDs and metadata for vector store
    ids: List[Any] = []
    metadatas: List[Any] = []
    for i, chunk in enumerate(chunks):
        # Create unique ID: source_id + chunk_index
        chunk_id = f"{source_id}_chunk{i}"
        ids.append(chunk_id)
        
        # Prepare metadata
        metadata = chunk["metadata"].copy()
        # Ensure tags are serializable (convert list to comma-separated string if needed)
        if "tags" in metadata and isinstance(metadata["tags"], list):
            metadata["tags_list"] = ",".join(metadata["tags"][:20])  # Store as string
            metadata["tags_count"] = len(metadata["tags"])
            del metadata["tags"]  # Remove list (not all backends support list metadata)
        
        metadatas.append(metadata)
    
    # Step 4: Index into VectorStore (with idempotency)
    # NOTE: Initialize manager to None before try block to avoid NameError in finally
    manager: Optional[VectorStoreManager] = None
    
    try:
        # Initialize manager
        manager = VectorStoreManager()
        
        # Check if we need to delete old chunks for this source_id
        # (For idempotency: if re-indexing same verdict, remove old chunks first)
        try:
            # Find IDs that match this source_id pattern
            old_ids = [f"{source_id}_chunk{i}" for i in range(100)]  # Check up to 100 chunks
            _run_async(manager.delete(old_ids))
            logger.debug(f"[VS] Deleted old chunks for {source_id} (if any)")
        except Exception as e:
            logger.debug(f"[VS] Could not delete old chunks (may not exist): {e}")
        
        # Insert new chunks
        # Use _run_async to handle both sync and async contexts
        success = _run_async(manager.insert(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            texts=texts
        ))
        
        if success:
            logger.info(f"[VS] ✓ Indexed {len(chunks)} chunks for verdict {source_id}")
        else:
            raise Exception("VectorStore insert returned False")
    
    except Exception as e:
        logger.error(f"[VS] Failed to index verdict {source_id}: {e}")
        raise
    
    finally:
        # Clean up (only if manager was successfully created)
        if manager is not None:
            try:
                _run_async(manager.close())
            except RuntimeError:
                # Event loop issues during cleanup - expected in some contexts
                pass

