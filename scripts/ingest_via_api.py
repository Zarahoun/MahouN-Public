#!/usr/bin/env python3
"""Simple script to ingest law via API."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from mahoun.ingestion_adapters.iranian_law_adapter import IranianLawAdapter
from mahoun.core.governance.ingestion_execution_gate import IngestionExecutionGate, IngestionExecutionRequest
from mahoun.core.governance.governance_context import GovernanceContextManager
from mahoun.graph.neo4j.connection import get_connection
from mahoun.core.governance.ingestion_runtime import GovernedIngestionRuntime
from mahoun.ingestion_adapters.registry import registered_adapter_object_types
import requests
import uuid

# Configuration
API_URL = "http://localhost:8080"
ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiIsInVzZXJfaWQiOjEsInJvbGUiOiJBRE1JTiIsImV4cCI6MTc5MDEwNDQxNywidHlwZSI6ImFjY2VzcyJ9.K5ZWKyb_xdvWv2Rh_znWFffXUn1oWfTxd_GRUjj5feo"
LAW_FILE = REPO_ROOT / "LAWS/data/all_legal_sentences.txt"
LAW_ID = "law:all_sentences"
LAW_NAME = "All Legal Sentences"

def main():
    # Read file
    text = LAW_FILE.read_text(encoding="utf-8")
    
    # Create adapter
    adapter = IranianLawAdapter(
        law_id=LAW_ID,
        law_name=LAW_NAME,
        source_uri=f"file://{LAW_FILE}",
        correlation_id=str(uuid.uuid4()),
    )
    
    # Parse with governance
    with IngestionExecutionGate.enter(IngestionExecutionRequest(
        adapter_name="IranianLawAdapter",
        source=f"file://{LAW_FILE}",
        author_id="admin",
        correlation_id=str(uuid.uuid4()),
    )):
        batch = adapter.build_batch(text)
    
    print(f"✅ Parsed {len(batch.documents)} documents")
    print(f"✅ Generated {len(batch.facts)} facts")
    print(f"✅ Generated {len(batch.relationships)} relationships")
    
    # Convert to API format
    from api.models import CanonicalBatchRequest
    
    request = CanonicalBatchRequest(
        contract_version="1",
        adapter_name="IranianLawAdapter",
        correlation_id=str(uuid.uuid4()),
        idempotency_key=str(uuid.uuid4()),
        author_id="admin",
        documents=[
            {
                "document_id": doc.document_id,
                "source_uri": doc.source_uri,
                "text": doc.text,
                "metadata": doc.metadata,
                "provenance": doc.provenance,
            }
            for doc in batch.documents
        ],
        facts=[
            {
                "fact_id": fact.fact_id,
                "subject_id": fact.subject_id,
                "predicate": fact.predicate,
                "object_id": fact.object_id,
                "evidence_text": fact.evidence_text,
                "provenance": fact.provenance,
                "source_spans": [
                    {
                        "source_uri": span.source_uri,
                        "start": span.start,
                        "end": span.end,
                        "text_hash": span.text_hash,
                    }
                    for span in fact.source_spans
                ],
                "object_type": fact.object_type,
                "confidence": fact.confidence,
                "metadata": fact.metadata,
            }
            for fact in batch.facts
        ],
        relationships=[
            {
                "relationship_id": rel.relationship_id,
                "source_id": rel.source_id,
                "relationship_type": rel.relationship_type,
                "target_id": rel.target_id,
                "properties": rel.properties,
                "provenance": rel.provenance,
                "source_spans": [
                    {
                        "source_uri": span.source_uri,
                        "start": span.start,
                        "end": span.end,
                        "text_hash": span.text_hash,
                    }
                    for span in rel.source_spans
                ],
            }
            for rel in batch.relationships
        ],
    )
    
    # Send to API
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    
    response = requests.post(
        f"{API_URL}/api/v1/ingest/canonical-batch",
        json=request.model_dump(),
        headers=headers,
    )
    
    if response.status_code == 200:
        print("✅ Ingestion successful!")
        print(response.json())
    else:
        print(f"❌ Ingestion failed: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    main()
