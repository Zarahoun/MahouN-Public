#!/bin/bash
# Test runner for enhanced graph wiring verification

cd /home/haji/Desktop/KingMahouN

echo "=================================================="
echo "Enhanced Graph Wiring Verification Tests"
echo "=================================================="
echo ""

echo "1. Running import verification tests..."
python3 -m pytest tests/graph/test_wiring_verify.py -v

echo ""
echo "2. Testing semantic extractor..."
python3 -c "
from mahoun.graph.extraction.semantic_extractor import SemanticExtractor
extractor = SemanticExtractor()
result = extractor.extract_concepts('قرارداد خرید املاک')
print(f'✅ Semantic extraction works: {type(result)}')
"

echo ""
echo "3. Testing entity linker..."
python3 -c "
from mahoun.graph.builders.entity_linker import EntityLinker
from mahoun.core.models import LegalEntity
linker = EntityLinker()
entities = [LegalEntity(name='احمد', entity_type='شخص')]
result = linker.link_entities(entities)
print(f'✅ Entity linking works: {type(result)}')
"

echo ""
echo "4. Testing concurrent builder initialization..."
python3 -c "
from mahoun.graph.concurrent_graph_builder import ConcurrentGraphBuilder
builder = ConcurrentGraphBuilder(
    enable_validation=True,
    enable_semantic_extraction=True,
    enable_entity_linking=True
)
print(f'✅ Builder initialized with enhancements')
print(f'   - Validation: {builder._enable_validation}')
print(f'   - Semantic: {builder._enable_semantic_extraction}')
print(f'   - Linking: {builder._enable_entity_linking}')
"

echo ""
echo "5. Testing ingestion runtime initialization..."
python3 -c "
from unittest.mock import MagicMock
from mahoun.core.governance.ingestion_runtime import GovernedIngestionRuntime
runtime = GovernedIngestionRuntime(
    session=MagicMock(),
    enable_semantic_extraction=True,
    enable_entity_linking=True
)
print(f'✅ Runtime initialized with enhancements')
print(f'   - Semantic: {runtime._enable_semantic_extraction}')
print(f'   - Linking: {runtime._enable_entity_linking}')
"

echo ""
echo "=================================================="
echo "All wiring tests completed!"
echo "=================================================="
