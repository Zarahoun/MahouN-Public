#!/usr/bin/env python3
"""
Create top 333 judgments by quality for graph ingestion
"""
import json
from pathlib import Path

def main():
    # Load all 827
    print("📄 بارگذاری 827 رأی...")
    with open('data/ara_all_827/ara_judgments_sample_100.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    judgments = data['judgments']
    print(f"   ✅ {len(judgments)} رأی بارگذاری شد")
    
    # Sort by quality
    print("\n🔄 مرتب‌سازی بر اساس کیفیت...")
    sorted_judgments = sorted(
        judgments, 
        key=lambda j: j['metadata']['quality_score'], 
        reverse=True
    )
    
    # Take top 333
    top_333 = sorted_judgments[:333]
    
    min_q = top_333[-1]['metadata']['quality_score']
    max_q = top_333[0]['metadata']['quality_score']
    avg_q = sum(j['metadata']['quality_score'] for j in top_333) / len(top_333)
    
    print(f"   ✅ 333 رأی برتر انتخاب شد")
    print(f"   📊 Range: {min_q:.3f} - {max_q:.3f}")
    print(f"   📊 Average: {avg_q:.3f}")
    
    # Calculate distribution
    perfect = sum(1 for j in top_333 if j['metadata']['quality_score'] >= 0.9)
    very_high = sum(1 for j in top_333 if 0.8 <= j['metadata']['quality_score'] < 0.9)
    high = sum(1 for j in top_333 if 0.7 <= j['metadata']['quality_score'] < 0.8)
    good = sum(1 for j in top_333 if 0.5 <= j['metadata']['quality_score'] < 0.7)
    medium = sum(1 for j in top_333 if j['metadata']['quality_score'] < 0.5)
    
    print(f"\n📈 توزیع کیفیت:")
    print(f"   Perfect (≥0.9):      {perfect:3d} رأی")
    print(f"   Very High (0.8-0.9): {very_high:3d} رأی")
    print(f"   High (0.7-0.8):      {high:3d} رأی")
    print(f"   Good (0.5-0.7):      {good:3d} رأی")
    print(f"   Medium (<0.5):       {medium:3d} رأی")
    
    # Create output directory
    output_dir = Path('data/ara_top_333')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Prepare output data
    output_data = {
        'metadata': {
            'source': data['metadata']['source'],
            'extracted_at': data['metadata']['extracted_at'],
            'total_available': data['metadata']['total_judgments'],
            'selection_method': 'top_333_by_quality',
            'selected_count': 333,
            'quality_stats': {
                'min': min_q,
                'max': max_q,
                'avg': avg_q
            },
            'distribution': {
                'perfect': perfect,
                'very_high': very_high,
                'high': high,
                'good': good,
                'medium': medium
            }
        },
        'judgments': top_333
    }
    
    # Save
    output_file = output_dir / 'judgments_top_333.json'
    print(f"\n💾 ذخیره‌سازی...")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    file_size = output_file.stat().st_size / 1024  # KB
    print(f"   ✅ ذخیره شد: {output_file}")
    print(f"   📦 حجم: {file_size:.1f} KB")
    
    # Also save metadata only
    metadata_only = {
        'metadata': output_data['metadata'],
        'judgments': [
            {'metadata': j['metadata']}
            for j in top_333
        ]
    }
    
    metadata_file = output_dir / 'metadata_top_333.json'
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata_only, f, ensure_ascii=False, indent=2)
    
    print(f"   ✅ Metadata: {metadata_file}")
    
    # Create summary
    summary = f"""# Top 333 Judgments - Ready for Graph Ingestion

## Summary Statistics

- **Total Selected**: 333 رأی
- **Quality Range**: {min_q:.3f} - {max_q:.3f}
- **Average Quality**: {avg_q:.3f}

## Quality Distribution

| Category | Count | Percentage |
|----------|-------|------------|
| Perfect (≥0.9) | {perfect} | {perfect*100//333}% |
| Very High (0.8-0.9) | {very_high} | {very_high*100//333}% |
| High (0.7-0.8) | {high} | {high*100//333}% |
| Good (0.5-0.7) | {good} | {good*100//333}% |
| Medium (<0.5) | {medium} | {medium*100//333}% |

## Files

- `judgments_top_333.json` - Full data (333 judgments with full text)
- `metadata_top_333.json` - Metadata only (for quick analysis)

## Ingestion Command

```bash
cd /home/haji/Desktop/KingMahouN
source venv/bin/activate

# Dry run first
python scripts/ingest_ara_judgments.py \\
    --input data/ara_top_333/judgments_top_333.json \\
    --dry-run

# Then commit
python scripts/ingest_ara_judgments.py \\
    --input data/ara_top_333/judgments_top_333.json \\
    --commit
```

## Expected Entities

- **Parties**: ~{333 * 2.9:.0f} نفر
- **Legal References**: ~{333 * 3.9:.0f} مورد
- **Relationships**: ~{333 * 6:.0f} روابط

---
Generated: {output_data['metadata']['extracted_at']}
"""
    
    readme_file = output_dir / 'README.md'
    with open(readme_file, 'w', encoding='utf-8') as f:
        f.write(summary)
    
    print(f"   ✅ README: {readme_file}")
    
    print("\n" + "=" * 70)
    print("✅ آماده برای ingestion به گراف!")
    print("=" * 70)
    print(f"\n📁 دایرکتوری: {output_dir}")
    print(f"📊 تعداد: 333 رأی")
    print(f"⭐ میانگین کیفیت: {avg_q:.3f}")
    print("\n🚀 مرحله بعد:")
    print("   python scripts/ingest_ara_judgments.py --input data/ara_top_333/judgments_top_333.json --dry-run")

if __name__ == '__main__':
    main()
