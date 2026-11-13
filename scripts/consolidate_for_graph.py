#!/usr/bin/env python3
"""
Consolidate filtered judgments for graph ingestion
"""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INPUT_PATH = REPO_ROOT / "data" / "ara_high_quality" / "ara_filtered_high_quality.json"
OUTPUT_DIR = REPO_ROOT / "data" / "ara_consolidated_for_graph"


def main():
    consolidated_dir = OUTPUT_DIR
    consolidated_dir.mkdir(parents=True, exist_ok=True)
    
    # Load filtered data
    with INPUT_PATH.open(encoding='utf-8') as f:
        data = json.load(f)
    
    judgments = data['judgments']
    print(f"📊 تعداد کل: {len(judgments)} رأی")
    
    # Separate by quality
    perfect = [j for j in judgments if j['metadata']['quality_score'] >= 0.9]
    very_high = [j for j in judgments if 0.8 <= j['metadata']['quality_score'] < 0.9]
    high = [j for j in judgments if 0.7 <= j['metadata']['quality_score'] < 0.8]
    
    print(f"\n📈 تفکیک:")
    print(f"   Perfect (≥0.9): {len(perfect)}")
    print(f"   Very High (0.8-0.9): {len(very_high)}")
    print(f"   High (0.7-0.8): {len(high)}")
    
    # Save categories
    categories = [
        ('perfect', perfect),
        ('very_high', very_high),
        ('high', high),
        ('all', judgments)
    ]
    
    for name, cat_data in categories:
        if not cat_data:
            continue
        output = consolidated_dir / f'judgments_{name}.json'
        output_data = {
            'metadata': data['metadata'],
            'judgments': cat_data
        }
        with open(output, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        print(f"✅ {name}: {len(cat_data)} → {output.name}")
    
    print(f"\n✅ همه فایل‌ها در {consolidated_dir} آماده شدند!")

if __name__ == '__main__':
    main()
