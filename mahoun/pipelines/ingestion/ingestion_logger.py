"""
Ingestion Logger
================
Structured JSON logging for the ingestion pipeline.

This module provides a standardized way to log parsing events, quality metrics,
and errors, enabling observability and automated monitoring of the ingestion process.
"""

import logging
import json
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class IngestionLogger:
    """
    Structured logger for ingestion events.
    """
    
    @staticmethod
    def log_parsing_event(
        doc_id: str,
        status: str,
        metrics: Optional[Dict[str, Any]] = None,
        errors: Optional[List[str]] = None,
        duration_ms: Optional[float] = None
    ):
        """
        Log a parsing event in structured JSON format.
        
        Args:
            doc_id: Document identifier
            status: 'SUCCESS', 'PARTIAL', 'FAILED'
            metrics: Quality metrics (confidence, fields_found, etc.)
            errors: List of error messages or warnings
            duration_ms: Processing time in milliseconds
        """
        log_entry = {
            "event": "parsing_completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "doc_id": doc_id,
            "status": status,
            "metrics": metrics or {},
            "errors": errors or [],
            "duration_ms": duration_ms
        }
        
        # Log at appropriate level
        if status == 'FAILED':
            logger.error(json.dumps(log_entry, ensure_ascii=False))
        elif status == 'PARTIAL':
            logger.warning(json.dumps(log_entry, ensure_ascii=False))
        else:
            logger.info(json.dumps(log_entry, ensure_ascii=False))

    @staticmethod
    def log_quality_report(
        doc_id: str,
        quality_score: float,
        missing_fields: List[str]
    ):
        """
        Log a specific quality report for a document.
        """
        log_entry = {
            "event": "quality_check",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "doc_id": doc_id,
            "quality_score": quality_score,
            "missing_fields": missing_fields,
            "is_high_quality": quality_score > 0.8
        }
        
        logger.info(json.dumps(log_entry, ensure_ascii=False))
