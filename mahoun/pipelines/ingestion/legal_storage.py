"""
Legal Storage Service - PostgreSQL Wiring for legal.* Tables
=============================================================
Stores parsed verdict data in PostgreSQL legal schema tables.

This module connects the ingestion pipeline to the advanced SQL schema:
- legal.verdicts: Structured verdict metadata
- legal.citations: Law article references
- legal.chunks: Document chunks with embeddings
- legal.entities: NER extracted entities

Usage:
    from mahoun.pipelines.ingestion.legal_storage import LegalStorageService
    
    storage = LegalStorageService()
    await storage.initialize()
    
    # Store a parsed verdict
    result = await storage.store_verdict(
        doc_id="verdict_001",
        verdict_struct=parsed_verdict,
        chunks=chunk_list,
        embeddings=embedding_list
    )
"""

import asyncio
import logging
import uuid
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Thread-safe singleton for storage service
from mahoun.core.singleton import ThreadSafeSingleton

_storage_singleton = ThreadSafeSingleton["LegalStorageService"]("LegalStorageService")


@dataclass
class StorageResult:
    """Result of storage operation"""
    success: bool
    verdict_id: Optional[str] = None
    chunks_stored: int = 0
    entities_stored: int = 0
    citations_stored: int = 0
    error: Optional[str] = None


class LegalStorageService:
    """
    Service for storing legal documents in PostgreSQL legal.* tables.
    
    Connects parsed verdict data to the advanced SQL schema defined in
    schemas/sql/master_schema.sql (legal.verdicts, legal.citations, etc.)
    
    Features:
    - Stores structured verdict metadata
    - Stores document chunks with embeddings
    - Stores NER entities
    - Stores law article citations
    - Transaction support for consistency
    - Graceful fallback if PostgreSQL unavailable
    """
    
    def __init__(self):
        self._pool = None
        self._initialized = False
        self._available = False
        
    async def initialize(self) -> bool:
        """
        Initialize PostgreSQL connection pool.
        
        Returns:
            True if PostgreSQL is available, False otherwise
        """
        if self._initialized:
            return self._available
            
        try:
            # Try to get PostgreSQL pool from API database module
            from api.database import postgres_pool, init_postgres
            
            if postgres_pool is None:
                await init_postgres()
                from api.database import postgres_pool
            
            self._pool = postgres_pool
            
            if self._pool:
                # Test connection and check if legal schema exists
                async with self._pool.acquire() as conn:
                    # Check if legal.verdicts table exists
                    exists = await conn.fetchval("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_schema = 'legal' 
                            AND table_name = 'verdicts'
                        )
                    """)
                    
                    if exists:
                        self._available = True
                        logger.info("✅ LegalStorageService initialized - legal schema available")
                    else:
                        logger.warning("⚠️ legal.verdicts table not found - using fallback mode")
                        self._available = False
            else:
                logger.warning("⚠️ PostgreSQL pool not available - using fallback mode")
                self._available = False
                
        except ImportError:
            logger.warning("⚠️ api.database not available - using fallback mode")
            self._available = False
        except Exception as e:
            logger.warning(f"⚠️ PostgreSQL initialization failed: {e} - using fallback mode")
            self._available = False
            
        self._initialized = True
        return self._available
    
    async def store_verdict(
        self,
        doc_id: str,
        verdict_struct: Dict[str, Any],
        chunks: Optional[List[Dict[str, Any]]] = None,
        embeddings: Optional[List[List[float]]] = None,
        source_file: Optional[str] = None
    ) -> StorageResult:
        """
        Store a parsed verdict in legal.* tables.
        
        Args:
            doc_id: Unique document identifier
            verdict_struct: Parsed verdict structure from minimal_verdict_parser
            chunks: Optional list of text chunks
            embeddings: Optional list of embeddings (must match chunks length)
            source_file: Optional source file path
            
        Returns:
            StorageResult with operation details
        """
        if not self._initialized:
            await self.initialize()
            
        if not self._available:
            logger.debug(f"PostgreSQL not available, skipping legal storage for {doc_id}")
            return StorageResult(
                success=True,  # Not a failure, just skipped
                verdict_id=doc_id,
                error="PostgreSQL legal schema not available - data stored in ChromaDB only"
            )
        
        try:
            async with self._pool.acquire() as conn:
                # Start transaction
                async with conn.transaction():
                    # 1. Store verdict metadata
                    verdict_id = await self._store_verdict_record(conn, doc_id, verdict_struct, source_file)
                    
                    # 2. Store chunks and embeddings
                    chunks_stored = 0
                    if chunks:
                        chunks_stored = await self._store_chunks(
                            conn, verdict_id, chunks, embeddings
                        )
                    
                    # 3. Store entities
                    entities_stored = 0
                    entities = verdict_struct.get("entities", {})
                    hardened_entities = verdict_struct.get("hardened_entities")
                    if entities or hardened_entities:
                        entities_stored = await self._store_entities(
                            conn, verdict_id, entities, hardened_entities
                        )
                    
                    # 4. Store citations (law references)
                    citations_stored = 0
                    legal_refs = verdict_struct.get("legal_references", {})
                    if legal_refs:
                        citations_stored = await self._store_citations(conn, verdict_id, legal_refs)
                    
                    logger.info(
                        f"✅ Stored verdict {doc_id} in legal schema: "
                        f"{chunks_stored} chunks, {entities_stored} entities, {citations_stored} citations"
                    )
                    
                    return StorageResult(
                        success=True,
                        verdict_id=str(verdict_id),
                        chunks_stored=chunks_stored,
                        entities_stored=entities_stored,
                        citations_stored=citations_stored
                    )
                    
        except Exception as e:
            logger.error(f"Failed to store verdict {doc_id} in legal schema: {e}")
            return StorageResult(
                success=False,
                error=str(e)
            )
    
    async def _store_verdict_record(
        self,
        conn,
        doc_id: str,
        verdict_struct: Dict[str, Any],
        source_file: Optional[str]
    ) -> uuid.UUID:
        """Store verdict metadata in legal.verdicts table."""
        
        case_meta = verdict_struct.get("case_meta", {})
        sections = verdict_struct.get("sections", {})
        parties = verdict_struct.get("parties", {})
        
        # Extract fields
        verdict_number = case_meta.get("case_number") or doc_id
        case_number = case_meta.get("case_number") or doc_id
        court_name = case_meta.get("court_level") or "نامشخص"
        
        # Map court type
        court_type_map = {
            "دیوان عالی کشور": "supreme",
            "تجدیدنظر": "appeal",
            "عمومی": "general",
            "انقلاب": "revolutionary",
            "اداری": "administrative",
        }
        court_type = "general"  # default
        for key, value in court_type_map.items():
            if key in court_name:
                court_type = value
                break
        
        # Parse date
        verdict_date: Optional[Any] = None
        date_str = case_meta.get("decision_date")
        if date_str:
            try:
                # Try to parse Persian date (simplified)
                # TODO: Implement proper Jalali date parsing
                verdict_date = datetime.now().date()  # Fallback to today
            except (ValueError, TypeError) as e:
                logger.debug(f"Date parsing failed for {date_str}: {e}")
                verdict_date = datetime.now().date()
        else:
            verdict_date = datetime.now().date()
        
        # Case type and result
        case_type = case_meta.get("case_type")
        
        # Map result
        result_map = {
            "رد": "rejected",
            "تأیید": "accepted",
            "نقض": "rejected",
            "وارد": "accepted",
        }
        result: Optional[Any] = None
        appeal_info = verdict_struct.get("appeal_court_reasoning", {})
        appeal_result = appeal_info.get("result", "")
        for key, value in result_map.items():
            if key in str(appeal_result):
                result = value
                break
        
        # Build parties JSON
        parties_json = {
            "plaintiff": parties.get("third_party_objector"),
            "defendant": parties.get("respondents", []),
            "attorneys": parties.get("respondents_attorneys", [])
        }
        
        # Build metadata JSON
        metadata = {
            "source_file": source_file,
            "doc_id": doc_id,
            "branch": case_meta.get("branch_number"),
            "city": case_meta.get("city"),
            "province": case_meta.get("province"),
            "is_final": case_meta.get("is_final", False),
            "finality_basis": case_meta.get("finality_basis"),
            "system_tags": verdict_struct.get("system_tags", []),
            "parsing_quality": verdict_struct.get("_parsing_quality", {})
        }
        
        # Get summary and full text
        summary = sections.get("summary", "")[:5000] if sections.get("summary") else None
        full_text = sections.get("verdict", "")[:50000] if sections.get("verdict") else None
        
        # Generate UUID
        verdict_id = uuid.uuid4()
        
        # Insert into legal.verdicts
        await conn.execute("""
            INSERT INTO legal.verdicts (
                id, verdict_number, case_number, court_name, court_type,
                branch_number, verdict_date, case_type, subject, summary,
                full_text, result, parties, metadata, is_deleted, created_at
            ) VALUES (
                $1, $2, $3, $4, $5::legal.court_type,
                $6, $7, $8, $9, $10,
                $11, $12::legal.case_result, $13, $14, false, NOW()
            )
            ON CONFLICT (verdict_number) DO UPDATE SET
                case_number = EXCLUDED.case_number,
                court_name = EXCLUDED.court_name,
                summary = EXCLUDED.summary,
                full_text = EXCLUDED.full_text,
                result = EXCLUDED.result,
                parties = EXCLUDED.parties,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
        """,
            verdict_id,
            verdict_number[:100],
            case_number[:100] if case_number else None,
            court_name[:200],
            court_type,
            case_meta.get("branch_number"),
            verdict_date,
            case_type[:100] if case_type else None,
            case_type[:500] if case_type else None,  # subject = case_type for now
            summary,
            full_text,
            result,
            parties_json,
            metadata
        )
        
        return verdict_id
    
    async def _store_chunks(
        self,
        conn,
        verdict_id: uuid.UUID,
        chunks: List[Dict[str, Any]],
        embeddings: Optional[List[List[float]]]
    ) -> int:
        """Store document chunks in legal.chunks table."""
        
        stored = 0
        
        for i, chunk in enumerate(chunks):
            chunk_id = uuid.uuid4()
            text = chunk.get("text", "")
            metadata = chunk.get("metadata", {})
            
            # Get embedding if available
            embedding: Optional[Any] = None
            if embeddings and i < len(embeddings):
                embedding = embeddings[i]
            
            try:
                await conn.execute("""
                    INSERT INTO legal.chunks (
                        id, document_id, parent_type, parent_id, chunk_index,
                        text, embedding, coherence_score, metadata, created_at
                    ) VALUES (
                        $1, $2, 'verdict', $3, $4,
                        $5, $6, $7, $8, NOW()
                    )
                    ON CONFLICT (parent_type, parent_id, chunk_index) DO UPDATE SET
                        text = EXCLUDED.text,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                """,
                    chunk_id,
                    verdict_id,
                    verdict_id,
                    i,
                    text[:10000],  # Limit text size
                    embedding,
                    metadata.get("coherence_score"),
                    metadata
                )
                stored += 1
            except Exception as e:
                logger.warning(f"Failed to store chunk {i}: {e}")
                
        return stored
    
    async def _store_entities(
        self,
        conn,
        verdict_id: uuid.UUID,
        entities: Dict[str, List[Dict[str, Any]]],
        hardened_entities: Optional[List[Dict[str, Any]]] = None
    ) -> int:
        """Store NER entities in legal.entities table."""
        
        stored = 0
        
        # 1. Process hardened entities first (highest fidelity)
        if hardened_entities:
            for entity in hardened_entities:
                entity_id = uuid.uuid4()
                text = entity.get("text", "")
                label = entity.get("category", "ENTITY")
                confidence = entity.get("confidence", 1.0)
                prov = entity.get("provenance", {})
                
                # Try to map chunk_id to UUID
                chunk_uuid: Optional[uuid.UUID] = None
                if "chunk_id" in prov:
                    try:
                        # This assumes chunk_id in prov matches what was stored in legal.chunks
                        # In this system, we often use the doc_id_chunk_idx format for Chroma
                        # but PostgreSQL uses UUIDs. We might need a mapping.
                        # For now, we'll store NULL if it's not a UUID.
                        chunk_uuid = uuid.UUID(prov["chunk_id"])
                    except (ValueError, TypeError):
                        pass

                try:
                    await conn.execute("""
                        INSERT INTO legal.entities (
                            id, chunk_id, text, label, start_pos, end_pos,
                            confidence, metadata, created_at
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6,
                            $7, $8, NOW()
                        )
                    """,
                        entity_id,
                        chunk_uuid,
                        text[:500],
                        label[:50],
                        prov.get("chunk_relative_start", 0),
                        prov.get("chunk_relative_end", len(text)),
                        confidence,
                        entity
                    )
                    stored += 1
                except Exception as e:
                    logger.debug(f"Failed to store hardened entity: {e}")
            
            return stored

        # 2. Fallback to raw entities if no hardened ones available
        # Map entity types
        entity_type_map = {
            "persons": "PERSON",
            "organizations": "ORGANIZATION",
            "courts": "COURT",
            "laws": "LAW",
            "topics": "TOPIC",
            "dates": "DATE",
            "amounts": "AMOUNT"
        }
        
        for entity_type, entity_list in entities.items():
            label = entity_type_map.get(entity_type, entity_type.upper())
            
            for entity in entity_list:
                entity_id = uuid.uuid4()
                
                # Get entity text
                text = entity.get("name") or entity.get("text") or entity.get("normalized_ref") or str(entity)
                if isinstance(text, dict):
                    text = str(text)
                
                confidence = entity.get("confidence", 1.0)
                
                try:
                    # Note: We store entities linked to verdict, not chunk
                    # In a more complete implementation, we'd link to specific chunks
                    await conn.execute("""
                        INSERT INTO legal.entities (
                            id, chunk_id, text, label, start_pos, end_pos,
                            confidence, metadata, created_at
                        ) VALUES (
                            $1, NULL, $2, $3, 0, $4,
                            $5, $6, NOW()
                        )
                    """,
                        entity_id,
                        text[:500],
                        label[:50],
                        len(text),
                        confidence,
                        entity
                    )
                    stored += 1
                except Exception as e:
                    logger.debug(f"Failed to store entity: {e}")
                    
        return stored
    
    async def _store_citations(
        self,
        conn,
        verdict_id: uuid.UUID,
        legal_refs: Dict[str, List[str]]
    ) -> int:
        """Store law citations in legal.citations table (simplified)."""
        
        # Note: Full implementation would link to legal.articles table
        # For now, we store citation info in verdict metadata
        
        stored = 0
        all_refs: List[Any] = []
        for ref_type, refs in legal_refs.items():
            for ref in refs:
                all_refs.append({
                    "type": ref_type,
                    "reference": ref
                })
                stored += 1
        
        # Update verdict metadata with citations
        if all_refs:
            try:
                await conn.execute("""
                    UPDATE legal.verdicts
                    SET metadata = metadata || jsonb_build_object('citations', $1::jsonb)
                    WHERE id = $2
                """,
                    all_refs,
                    verdict_id
                )
            except Exception as e:
                logger.debug(f"Failed to update citations metadata: {e}")
                
        return stored
    
    async def get_verdict(self, verdict_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a verdict from legal.verdicts table."""
        
        if not self._available:
            return None
            
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT * FROM legal.verdicts WHERE id = $1 OR verdict_number = $1
                """, verdict_id)
                
                if row:
                    return dict(row)
                return None
        except Exception as e:
            logger.error(f"Failed to get verdict {verdict_id}: {e}")
            return None
    
    async def search_verdicts(
        self,
        query: str,
        limit: int = 10,
        case_type: Optional[str] = None,
        court_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search verdicts using full-text search."""
        
        if not self._available:
            return []
            
        try:
            async with self._pool.acquire() as conn:
                # Build query with filters
                sql = """
                    SELECT id, verdict_number, case_number, court_name, 
                           case_type, summary, result, verdict_date,
                           ts_rank(full_text_tsv, plainto_tsquery('persian', $1)) as rank
                    FROM legal.verdicts
                    WHERE full_text_tsv @@ plainto_tsquery('persian', $1)
                """
                params = [query]
                param_idx = 2
                
                if case_type:
                    sql += f" AND case_type ILIKE ${param_idx}"
                    params.append(f"%{case_type}%")
                    param_idx += 1
                    
                if court_type:
                    sql += f" AND court_type = ${param_idx}::legal.court_type"
                    params.append(court_type)
                    param_idx += 1
                
                sql += f" ORDER BY rank DESC LIMIT ${param_idx}"
                params.append(limit)
                
                rows = await conn.fetch(sql, *params)
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Failed to search verdicts: {e}")
            return []
    
    async def close(self):
        """Close connections."""
        # Pool is managed by api.database, don't close it here
        self._initialized = False
        self._available = False


# ============================================================================
# Convenience Functions
# ============================================================================

async def get_legal_storage() -> LegalStorageService:
    """
    Get or create the legal storage service singleton (thread-safe).
    
    Returns:
        LegalStorageService instance
    """
    service = _storage_singleton.get_instance(
        factory=lambda: LegalStorageService()
    )
    
    # Initialize if not already initialized
    if not _storage_singleton.is_initialized() or not hasattr(service, '_initialized'):
        await service.initialize()
        
    return service


async def store_verdict_to_legal_schema(
    doc_id: str,
    verdict_struct: Dict[str, Any],
    chunks: Optional[List[Dict[str, Any]]] = None,
    embeddings: Optional[List[List[float]]] = None,
    source_file: Optional[str] = None
) -> StorageResult:
    """
    Convenience function to store a verdict in legal schema.
    
    This is the main entry point for the ingestion pipeline.
    """
    storage = await get_legal_storage()
    return await storage.store_verdict(
        doc_id=doc_id,
        verdict_struct=verdict_struct,
        chunks=chunks,
        embeddings=embeddings,
        source_file=source_file
    )
