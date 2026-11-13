#!/usr/bin/env python3
"""
Quick test script for judgment ingestion
"""
import sys
from pathlib import Path

# Add repo to path
sys.path.insert(0, str(Path(__file__).parent))

from scripts.build_judgment_kg import (
    EnterpriseJudgmentCompiler,
    parse_judgments_from_json,
    verify_source,
)
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)

def main():
    print("=" * 80)
    print("🚀 Testing Judgment Ingestion (Small Batch)")
    print("=" * 80)
    
    # Load first 10 judgments
    json_file = Path("data/ara_top_333/judgments_top_333.json")
    
    print(f"\n📖 Loading judgments from {json_file}...")
    all_judgments = parse_judgments_from_json(json_file)
    judgments = all_judgments[:10]  # Just first 10
    
    print(f"✅ Loaded {len(judgments)} judgments for testing")
    
    # Compile
    compiler = EnterpriseJudgmentCompiler()
    
    print(f"\n🔧 Starting ingestion...")
    result = compiler.compile(judgments, batch_size=5)
    
    print("\n" + "=" * 80)
    print("✅ INGESTION COMPLETE")
    print("=" * 80)
    print(f"Status         : {result['status']}")
    print(f"Processed      : {result['processed']}/{result['total_judgments']}")
    print(f"Entities       : {result['entities_created']}")
    print(f"Relationships  : {result['relationships_created']}")
    print(f"Duration       : {result['duration_sec']:.1f}s")
    print(f"Throughput     : {result['throughput_jps']:.2f} j/s")
    print(f"Errors         : {result['errors_count']}")
    print("=" * 80)
    
    if result['errors_count'] > 0:
        print("\n❌ Errors encountered:")
        for err in compiler.errors[:3]:
            print(f"  - Batch {err['batch']}: {err['error']}")
    
    return 0 if result['errors_count'] == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
