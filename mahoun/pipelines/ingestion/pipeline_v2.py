"""
Forwarder for pipeline_v2.
This file is kept for backward compatibility.
The authoritative implementation has been moved to pipelines/ingestion/pipeline.py.
"""

from mahoun.pipelines.ingestion.pipeline import (
    IngestionPipelineV2, 
    IngestionResultV2, 
    ingest_document_v2, 
    ingest_file_v2
)