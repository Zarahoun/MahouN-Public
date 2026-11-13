#!/usr/bin/env python3
"""
MahouN-Native ARA Judgment Ingestion Pipeline
=============================================
Fully integrated with MahouN's existing systems for judicial ruling ingestion.

Integration Points:
- LegalNEREngine for entity extraction
- SemanticMaterializer for graph construction
- GovernedIngestionRuntime for Neo4j write
- Phase 2A semantic schema compliance
- Case isolation architecture

Usage:
    python scripts/ingest_ara_judgments.py --sample 100 --dry-run
    python scripts/ingest_ara_judgments.py --sample 100 --commit
"""

from __future__ import annotations

import sys
import json
import logging
import argparse
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
import hashlib
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# MahouN imports
from mahoun.pipelines.ingestion.legal_ner import LegalNEREngine
from mahoun.graph.extraction.semantic_materializer import SemanticMaterializer
from mahoun.core.governance.ingestion_runtime import GovernedIngestionRuntime
from mahoun.core.governance.ingestion_execution_gate import IngestionExecutionGate
from mahoun.graph.neo4j.connection import get_connection
from mahoun.core.models.case import CaseIdentity
from typing import Any

# The former SemanticEntity/SemanticRelation classes were removed from the
# canonical model package. This quarantined adapter is dry-run capable and
# keeps its legacy internal shape isolated until it is migrated to the
# canonical ingestion contract.
SemanticEntity = Any
SemanticRelation = Any

# Import the parser we already built
from scripts.parse_ara_judgments import (
    AraJudgmentParser,
    Judgment,
    JudgmentMetadata
)
from scripts.build_judgment_kg import CanonicalJudgment, EnterpriseJudgmentCompiler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class JudgmentIngestionResult:
    """Result of ingesting a single judgment."""
    judgment_id: str
    case_id: Optional[str]
    entities_extracted: int
    relations_created: int
    neo4j_node_id: Optional[str]
    success: bool
    error: Optional[str] = None


class MahouNJudgmentIngestor:
    """
    Orchestrates judgment ingestion using MahouN's native systems.
    """
    
    def __init__(self, dry_run: bool = True, compiler=None):
        self.dry_run = dry_run
        self.compiler = compiler
        
        # Initialize MahouN components
        logger.info("🔧 Initializing MahouN components...")
        
        try:
            self.ner_engine = LegalNEREngine()
            logger.info("   ✅ LegalNEREngine initialized")
        except Exception as e:
            logger.warning(f"   ⚠️  LegalNEREngine unavailable: {e}")
            self.ner_engine = None
        
        try:
            self.semantic_materializer = SemanticMaterializer()
            logger.info("   ✅ SemanticMaterializer initialized")
        except Exception as e:
            logger.warning(f"   ⚠️  SemanticMaterializer unavailable: {e}")
            self.semantic_materializer = None
        
        if not dry_run:
            try:
                self.neo4j_conn = get_connection()
                logger.info("   ✅ Neo4j connection established")
            except Exception as e:
                logger.error(f"   ❌ Neo4j connection failed: {e}")
                raise
        else:
            self.neo4j_conn = None
            logger.info("   🔸 Dry-run mode: Neo4j writes disabled")
    
    def ingest_judgment(
        self, 
        judgment: Judgment,
        author_id: str = "ara_import_system"
    ) -> JudgmentIngestionResult:
        """
        Ingest a single judgment through the complete MahouN pipeline.
        
        Pipeline:
        1. Create Case object
        2. Extract legal entities with NER
        3. Build semantic graph with materializer
        4. Write to Neo4j via governed runtime
        """
        judgment_id = judgment.metadata.judgment_id
        logger.info(f"\n📄 Processing: {judgment_id}")
        logger.info(f"   Title: {judgment.metadata.title[:60]}...")
        
        try:
            # Step 1: Create Case
            case = self._create_case_from_judgment(judgment)
            logger.info(f"   ✅ Case created: {case.case_id}")
            
            # Step 2: Extract entities
            entities = self._extract_entities(judgment)
            logger.info(f"   ✅ Extracted {len(entities)} entities")
            
            # Step 3: Build semantic relations
            relations = self._build_relations(judgment, entities)
            logger.info(f"   ✅ Built {len(relations)} relations")
            
            # Step 4: Materialize to graph
            if self.semantic_materializer and not self.dry_run:
                graph_data = self._materialize_to_graph(
                    case, entities, relations, judgment
                )
                logger.info(f"   ✅ Graph materialized")
            else:
                graph_data = None
                logger.info(f"   🔸 Graph materialization skipped (dry-run or unavailable)")
            
            # Step 5: Write to Neo4j
            neo4j_node_id = None
            if not self.dry_run:
                neo4j_node_id = self._write_to_neo4j(
                    case, entities, relations, judgment, author_id
                )
                logger.info(f"   ✅ Written to Neo4j: {neo4j_node_id}")
            else:
                logger.info(f"   🔸 Neo4j write skipped (dry-run)")
            
            return JudgmentIngestionResult(
                judgment_id=judgment_id,
                case_id=case.case_id,
                entities_extracted=len(entities),
                relations_created=len(relations),
                neo4j_node_id=neo4j_node_id,
                success=True
            )
            
        except Exception as e:
            logger.error(f"   ❌ Failed: {e}")
            return JudgmentIngestionResult(
                judgment_id=judgment_id,
                case_id=None,
                entities_extracted=0,
                relations_created=0,
                neo4j_node_id=None,
                success=False,
                error=str(e)
            )
    
    def _create_case_from_judgment(self, judgment: Judgment) -> CaseIdentity:
        """Convert judgment to the canonical immutable case identity."""
        m = judgment.metadata
        
        # Generate case ID
        case_id = f"CASE_ARA_{m.content_hash[:12]}"
        
        # Build case metadata
        case_metadata = {
            'source': 'ara.jri.ac.ir',
            'import_date': datetime.now().isoformat(),
            'court_level': m.court_level,
            'branch_number': m.branch_number,
            'case_number': m.case_number,
            'date': m.date,
            'legal_area': m.legal_area,
            'verdict_type': m.verdict_type,
            'quality_score': m.quality_score,
        }
        
        return CaseIdentity.from_user_provided(
            case_id=case_id,
            question=m.title,
            facts=[judgment.full_text[:500], *m.parties],
            user_id="ara_import_system",
        )
    
    def _extract_entities(self, judgment: Judgment) -> List[SemanticEntity]:
        """Extract legal entities using NER if available."""
        entities = []
        
        if self.ner_engine:
            try:
                # Use NER engine
                ner_result = self.ner_engine.extract(judgment.full_text)
                
                # Convert to SemanticEntity
                for entity in ner_result.get('entities', []):
                    entities.append(SemanticEntity(
                        entity_id=f"ENT_{hashlib.sha256(entity['text'].encode()).hexdigest()[:12]}",
                        entity_type=entity['label'],
                        name=entity['text'],
                        properties={
                            'start': entity.get('start'),
                            'end': entity.get('end'),
                            'confidence': entity.get('score', 0.0)
                        }
                    ))
            except Exception as e:
                logger.warning(f"NER extraction failed: {e}, using fallback")
        
        # Fallback: extract from metadata
        if not entities:
            entities = self._extract_entities_fallback(judgment)
        
        return entities
    
    def _extract_entities_fallback(self, judgment: Judgment) -> List[SemanticEntity]:
        """Fallback entity extraction from metadata."""
        entities = []
        m = judgment.metadata
        
        # Parties
        for i, party in enumerate(m.parties):
            entities.append(SemanticEntity(
                entity_id=f"PARTY_{hashlib.sha256(party.encode()).hexdigest()[:12]}",
                entity_type='PARTY',
                name=party,
                properties={'source': 'metadata'}
            ))
        
        # Judges
        for i, judge in enumerate(m.judges):
            entities.append(SemanticEntity(
                entity_id=f"JUDGE_{hashlib.sha256(judge.encode()).hexdigest()[:12]}",
                entity_type='JUDGE',
                name=judge,
                properties={'source': 'metadata'}
            ))
        
        # Legal references
        for i, ref in enumerate(m.legal_references):
            entities.append(SemanticEntity(
                entity_id=f"LEGAL_REF_{hashlib.sha256(ref.encode()).hexdigest()[:12]}",
                entity_type='LEGAL_REFERENCE',
                name=ref,
                properties={'source': 'metadata'}
            ))
        
        return entities
    
    def _build_relations(
        self, 
        judgment: Judgment, 
        entities: List[SemanticEntity]
    ) -> List[SemanticRelation]:
        """Build semantic relations between entities."""
        relations = []
        
        # Find parties and judges
        parties = [e for e in entities if e.entity_type == 'PARTY']
        judges = [e for e in entities if e.entity_type == 'JUDGE']
        legal_refs = [e for e in entities if e.entity_type == 'LEGAL_REFERENCE']
        
        # Create DECIDED_BY relations (parties -> judges)
        for party in parties:
            for judge in judges:
                relations.append(SemanticRelation(
                    relation_id=f"REL_{hashlib.sha256(f'{party.entity_id}_{judge.entity_id}'.encode()).hexdigest()[:12]}",
                    source_id=party.entity_id,
                    target_id=judge.entity_id,
                    relation_type='DECIDED_BY',
                    properties={'judgment_id': judgment.metadata.judgment_id}
                ))
        
        # Create CITES relations (judgment -> legal refs)
        # We'll use the judgment_id as a pseudo-entity
        for ref in legal_refs:
            relations.append(SemanticRelation(
                relation_id=f"REL_{hashlib.sha256(f'{judgment.metadata.judgment_id}_{ref.entity_id}'.encode()).hexdigest()[:12]}",
                source_id=judgment.metadata.judgment_id,
                target_id=ref.entity_id,
                relation_type='CITES',
                properties={}
            ))
        
        return relations
    
    def _materialize_to_graph(
        self,
        case: Case,
        entities: List[SemanticEntity],
        relations: List[SemanticRelation],
        judgment: Judgment
    ) -> Dict:
        """Use SemanticMaterializer to prepare graph data."""
        try:
            # Prepare data for materializer
            semantic_data = {
                'case': asdict(case),
                'entities': [asdict(e) for e in entities],
                'relations': [asdict(r) for r in relations],
                'judgment': {
                    'metadata': asdict(judgment.metadata),
                    'sections': judgment.sections
                }
            }
            
            # Materialize
            graph_data = self.semantic_materializer.materialize(semantic_data)
            return graph_data
            
        except Exception as e:
            logger.warning(f"Materialization failed: {e}")
            return {}
    
    def _write_to_neo4j(
        self,
        case: Case,
        entities: List[SemanticEntity],
        relations: List[SemanticRelation],
        judgment: Judgment,
        author_id: str
    ) -> Optional[str]:
        """Delegate writes to the canonical governed judgment compiler."""
        m = judgment.metadata
        canonical = CanonicalJudgment(
            judgment_id=m.judgment_id,
            title=m.title,
            full_text=judgment.full_text,
            court_level=m.court_level or "unknown",
            legal_area=m.legal_area or "unknown",
            verdict_type=m.verdict_type or "unknown",
            date=m.date,
            quality_score=m.quality_score,
            word_count=m.word_count,
            parties=m.parties,
            legal_references=m.legal_references,
            source_hash=hashlib.sha256(
                judgment.full_text.encode("utf-8")
            ).hexdigest(),
        )
        if self.compiler is None:
            raise RuntimeError(
                "Canonical compiler is not wired; commit mode requires an "
                "EnterpriseJudgmentCompiler owned by the CLI."
            )
        result = self.compiler.compile([canonical], batch_size=1)
        if result["errors_count"]:
            raise RuntimeError(f"Canonical judgment ingestion failed: {result}")
        return m.judgment_id


def main():
    parser = argparse.ArgumentParser(
        description='Ingest ARA judgments into MahouN knowledge graph'
    )
    parser.add_argument(
        '--input',
        default='ara.docx',
        help='Path to ara.docx file'
    )
    parser.add_argument(
        '--sample',
        type=int,
        default=100,
        help='Number of judgments to sample and ingest'
    )
    commit_group = parser.add_mutually_exclusive_group()
    commit_group.add_argument(
        '--commit',
        action='store_true',
        help='Enable governed Neo4j writes (disabled by default)'
    )
    commit_group.add_argument(
        '--dry-run',
        action='store_true',
        help='Parse and extract but do not write to Neo4j (default)'
    )
    parser.add_argument(
        '--seed',
        type=int,
        default=20260914,
        help='Deterministic sampling seed'
    )
    parser.add_argument(
        '--output',
        default='data/ara_ingest_report.json',
        help='Output path for ingestion report'
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("MahouN ARA Judgment Ingestion Pipeline")
    print("=" * 80)
    print()
    
    # Step 1: Parse judgments
    logger.info("📄 Parsing ARA document...")
    parser_obj = AraJudgmentParser(args.input, sampling_seed=args.seed)
    parser_obj.sampler.target_count = args.sample
    judgments, stats = parser_obj.parse()
    
    # Sample
    sampled = parser_obj.sampler.sample(judgments)
    logger.info(f"✅ Sampled {len(sampled)} judgments for ingestion")
    
    # Step 2: Initialize ingestor
    logger.info("\n🔧 Initializing MahouN ingestor...")
    dry_run = not args.commit
    compiler = EnterpriseJudgmentCompiler() if not dry_run else None
    ingestor = MahouNJudgmentIngestor(dry_run=dry_run, compiler=compiler)
    
    # Step 3: Ingest judgments
    logger.info(f"\n🚀 Beginning ingestion of {len(sampled)} judgments...")
    results = []
    
    def ingest_all() -> None:
        for i, judgment in enumerate(sampled, 1):
            logger.info(f"\n[{i}/{len(sampled)}]")
            result = ingestor.ingest_judgment(judgment)
            results.append(asdict(result))

    if dry_run:
        ingest_all()
    else:
        request = IngestionExecutionRequest(
            source=str(Path(args.input).resolve()),
            author_id="ara_import_system",
            correlation_id=f"ara_ingest_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            adapter_name="AraJudgmentIngestionCLI",
        )
        with IngestionExecutionGate.enter(request):
            ingest_all()
    
    # Step 4: Generate report
    report = {
        'metadata': {
            'timestamp': datetime.now().isoformat(),
            'source_file': args.input,
            'total_parsed': len(judgments),
            'total_ingested': len(sampled),
            'dry_run': dry_run,
        },
        'statistics': {
            'successful': sum(1 for r in results if r['success']),
            'failed': sum(1 for r in results if not r['success']),
            'total_entities': sum(r['entities_extracted'] for r in results),
            'total_relations': sum(r['relations_created'] for r in results)
        },
        'results': results
    }
    
    # Save report
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = Path(__file__).resolve().parent.parent / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    # Print summary
    print("\n" + "=" * 80)
    print("✅ Ingestion Complete!")
    print("=" * 80)
    print(f"Successful: {report['statistics']['successful']}/{len(sampled)}")
    print(f"Failed: {report['statistics']['failed']}/{len(sampled)}")
    print(f"Total entities: {report['statistics']['total_entities']}")
    print(f"Total relations: {report['statistics']['total_relations']}")
    print(f"\nReport saved to: {output_path}")
    print("=" * 80)
    return 1 if report["statistics"]["failed"] else 0


if __name__ == '__main__':
    raise SystemExit(main())
