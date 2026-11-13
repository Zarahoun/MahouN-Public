#!/bin/bash
# Wrapper script for judgment ingestion

cd /home/haji/Desktop/KingMahouN
source venv/bin/activate

echo "🚀 Starting judgment ingestion..."
echo "Data: data/ara_top_333/judgments_top_333.json"
echo "Batch size: 50"
echo ""

python scripts/build_judgment_kg.py \
    --file data/ara_top_333/judgments_top_333.json \
    --batch-size 50

echo ""
echo "✅ Ingestion complete!"
