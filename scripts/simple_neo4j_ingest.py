#!/usr/bin/env python3
"""Compatibility CLI delegating ARA ingestion to the canonical compiler."""
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.build_judgment_kg import (
    EnterpriseJudgmentCompiler,
    parse_judgments_from_json,
)
from mahoun.core.governance.ingestion_execution_gate import (
    IngestionExecutionGate,
    IngestionExecutionRequest,
)

def ingest_judgments(input_file: str, dry_run: bool = True, limit: int = None):
    """
    Simple ingestion to Neo4j
    """
    print("=" * 80)
    print("Simple ARA Judgment Ingestion to Neo4j")
    print("=" * 80)
    print(f"\n📄 Input: {input_file}")
    print(f"🔸 Dry-run: {dry_run}")

    from scripts.graph_script_policy import quarantine_legacy_writer

    quarantine_legacy_writer(
        "simple_neo4j_ingest.py",
        "POST /api/v1/ingest/canonical-batch",
    )

    with IngestionExecutionGate.enter(
        IngestionExecutionRequest(
            source=str(Path(input_file).resolve()),
            author_id="simple_neo4j_ingest",
            correlation_id=f"dry-run:{Path(input_file).name}",
            adapter_name="SimpleAraJudgmentDryRun",
        )
    ):
        judgments = parse_judgments_from_json(Path(input_file))
    if limit:
        judgments = judgments[:limit]
    
    print(f"📊 Judgments to process: {len(judgments)}")
    
    if dry_run:
        print("\n🔸 DRY-RUN MODE - No actual writes")
        print("\n📋 Sample of what would be ingested:")
        for i, j in enumerate(judgments[:3], 1):
            print(f"\n{i}. {j.judgment_id}")
            print(f"   Title: {j.title[:60]}...")
            print(f"   Quality: {j.quality_score}")
            print(f"   Court: {j.court_level}, Area: {j.legal_area}")
            print(f"   Parties: {len(j.parties)}, Refs: {len(j.legal_references)}")
        
        remaining = max(0, len(judgments) - 3)
        print(f"\n... and {remaining} more")
        print("\n✅ Dry-run complete")
        return
    
    print("\n🚀 Delegating to canonical EnterpriseJudgmentCompiler...")
    result = EnterpriseJudgmentCompiler().compile(judgments, batch_size=50)
    print("\n" + "=" * 80)
    print("✅ Ingestion Complete!")
    print("=" * 80)
    print(f"Unique judgments: {result['total_judgments']}")
    print(f"Duplicates      : {result['duplicate_judgments']}")
    print(f"Processed       : {result['processed']}")
    print(f"Errors          : {result['errors_count']}")

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Simple Neo4j ingestion for ARA judgments')
    parser.add_argument('--input', required=True, help='Input JSON file')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode')
    parser.add_argument('--limit', type=int, help='Limit number of judgments')
    
    args = parser.parse_args()
    
    ingest_judgments(args.input, args.dry_run, args.limit)

if __name__ == '__main__':
    main()
