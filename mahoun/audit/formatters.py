"""
Audit Export Format Converters
===============================

Enterprise-grade formatters for SIEM/audit system integration.

Supported Formats:
- CEF (Common Event Format) - ArcSight, Splunk
- LEEF (Log Event Extended Format) - IBM QRadar
- JSON-LD (JSON Linked Data) - Semantic web
- JSONL (JSON Lines) - Streaming/bulk
- CSV (Comma Separated Values) - Excel, analysis

Design:
- Deterministic output (same input → same output)
- RFC-compliant formatting
- Escaping for injection protection
- UTF-8 safe
"""

import csv
import json
import hashlib
from abc import ABC, abstractmethod
from datetime import datetime
from io import StringIO
from typing import List, Dict, Any
from urllib.parse import quote


# ============================================================================
# BASE FORMATTER
# ============================================================================

class AuditFormatter(ABC):
    """Base class for audit formatters"""
    
    @abstractmethod
    def format(self, records: List[Dict[str, Any]]) -> str:
        """
        Format records.
        
        Args:
            records: List of audit records
        
        Returns:
            Formatted string ready for export
        """
        pass
    
    @staticmethod
    def _escape_cef(value: str) -> str:
        """Escape value for CEF format"""
        if not isinstance(value, str):
            value = str(value)
        # CEF escaping: backslash escape pipe and backslash
        return value.replace('\\', '\\\\').replace('|', '\\|')
    
    @staticmethod
    def _escape_leef(value: str) -> str:
        """Escape value for LEEF format"""
        if not isinstance(value, str):
            value = str(value)
        # LEEF escaping: backslash escape tab, newline, carriage return
        return (value
                .replace('\\', '\\\\')
                .replace('\t', '\\t')
                .replace('\n', '\\n')
                .replace('\r', '\\r'))
    
    @staticmethod
    def _truncate(value: str, max_length: int = 1024) -> str:
        """Truncate long values"""
        if len(value) <= max_length:
            return value
        return value[:max_length - 3] + "..."
    
    @staticmethod
    def _normalize_timestamp(timestamp: Any) -> str:
        """Normalize timestamp to ISO 8601"""
        if isinstance(timestamp, datetime):
            return timestamp.isoformat()
        if isinstance(timestamp, str):
            return timestamp
        return datetime.now().isoformat()


# ============================================================================
# CEF FORMATTER
# ============================================================================

class CEFFormatter(AuditFormatter):
    """
    Common Event Format (CEF) formatter.
    
    Format:
    CEF:Version|Device Vendor|Device Product|Device Version|Signature ID|Name|Severity|Extension
    
    Used by:
    - ArcSight
    - Splunk
    - LogRhythm
    - Many enterprise SIEMs
    
    Spec: https://www.microfocus.com/documentation/arcsight/arcsight-smartconnectors/
    """
    
    VERSION = "0"
    VENDOR = "MAHOUN"
    PRODUCT = "Legal AI Platform"
    DEVICE_VERSION = "1.1.0"
    
    def format(self, records: List[Dict[str, Any]]) -> str:
        """Format records as CEF"""
        lines = []
        
        for record in records:
            cef_line = self._format_record(record)
            lines.append(cef_line)
        
        return "\n".join(lines) + "\n"
    
    def _format_record(self, record: Dict[str, Any]) -> str:
        """Format single record as CEF"""
        # Extract core fields
        signature_id = record.get('operation', 'unknown_operation')
        name = record.get('event_name', f"MAHOUN {signature_id}")
        severity = self._map_severity(record.get('severity', 'INFO'))
        
        # Build header
        header = "|".join([
            f"CEF:{self.VERSION}",
            self._escape_cef(self.VENDOR),
            self._escape_cef(self.PRODUCT),
            self._escape_cef(self.DEVICE_VERSION),
            self._escape_cef(signature_id),
            self._escape_cef(name),
            str(severity),
        ])
        
        # Build extension (key=value pairs)
        extensions = self._build_extensions(record)
        extension_str = " ".join([f"{k}={v}" for k, v in extensions.items()])
        
        return f"{header}|{extension_str}"
    
    def _build_extensions(self, record: Dict[str, Any]) -> Dict[str, str]:
        """Build CEF extension fields"""
        extensions = {}
        
        # Standard CEF fields
        if 'timestamp' in record:
            extensions['rt'] = self._normalize_timestamp(record['timestamp'])
        
        if 'actor_id' in record:
            extensions['suser'] = self._escape_cef(record['actor_id'])
        
        if 'correlation_id' in record:
            extensions['externalId'] = self._escape_cef(record['correlation_id'])
        
        if 'source_ip' in record:
            extensions['src'] = record['source_ip']
        
        if 'verdict_id' in record:
            extensions['cn1'] = self._escape_cef(record['verdict_id'])
            extensions['cn1Label'] = "VerdictID"
        
        if 'confidence' in record:
            extensions['cn2'] = str(record.get('confidence', 0.0))
            extensions['cn2Label'] = "Confidence"
        
        if 'operation' in record:
            extensions['act'] = self._escape_cef(record['operation'])
        
        if 'outcome' in record:
            extensions['outcome'] = self._escape_cef(record['outcome'])
        
        # Custom fields (cs1-cs6 for custom strings)
        custom_idx = 1
        for key in ['case_id', 'proof_hash', 'merkle_root']:
            if key in record and custom_idx <= 6:
                extensions[f'cs{custom_idx}'] = self._escape_cef(str(record[key]))
                extensions[f'cs{custom_idx}Label'] = key.title().replace('_', '')
                custom_idx += 1
        
        return extensions
    
    @staticmethod
    def _map_severity(severity: str) -> int:
        """Map severity to CEF numeric (0-10)"""
        severity_map = {
            'DEBUG': 1,
            'INFO': 3,
            'NOTICE': 4,
            'WARNING': 6,
            'ERROR': 8,
            'CRITICAL': 9,
            'FATAL': 10,
        }
        return severity_map.get(severity.upper(), 5)


# ============================================================================
# LEEF FORMATTER
# ============================================================================

class LEEFFormatter(AuditFormatter):
    """
    Log Event Extended Format (LEEF) formatter.
    
    Format:
    LEEF:Version|Vendor|Product|Version|EventID|Key=Value\tKey=Value...
    
    Used by:
    - IBM QRadar
    - IBM Security products
    
    Spec: https://www.ibm.com/docs/en/dsm?topic=leef-overview
    """
    
    VERSION = "2.0"
    VENDOR = "MAHOUN"
    PRODUCT = "Legal AI Platform"
    PRODUCT_VERSION = "1.1.0"
    
    def format(self, records: List[Dict[str, Any]]) -> str:
        """Format records as LEEF"""
        lines = []
        
        for record in records:
            leef_line = self._format_record(record)
            lines.append(leef_line)
        
        return "\n".join(lines) + "\n"
    
    def _format_record(self, record: Dict[str, Any]) -> str:
        """Format single record as LEEF"""
        # Extract core fields
        event_id = record.get('operation', 'unknown_operation')
        
        # Build header
        header = "|".join([
            f"LEEF:{self.VERSION}",
            self.VENDOR,
            self.PRODUCT,
            self.PRODUCT_VERSION,
            event_id,
        ])
        
        # Build attributes (tab-separated key=value)
        attributes = self._build_attributes(record)
        attribute_str = "\t".join([f"{k}={v}" for k, v in attributes.items()])
        
        return f"{header}|{attribute_str}"
    
    def _build_attributes(self, record: Dict[str, Any]) -> Dict[str, str]:
        """Build LEEF attribute fields"""
        attributes = {}
        
        # Standard LEEF fields
        if 'timestamp' in record:
            attributes['devTime'] = self._normalize_timestamp(record['timestamp'])
        
        if 'actor_id' in record:
            attributes['usrName'] = self._escape_leef(record['actor_id'])
        
        if 'correlation_id' in record:
            attributes['identSrc'] = self._escape_leef(record['correlation_id'])
        
        if 'source_ip' in record:
            attributes['src'] = record['source_ip']
        
        if 'verdict_id' in record:
            attributes['verdictID'] = self._escape_leef(record['verdict_id'])
        
        if 'confidence' in record:
            attributes['confidence'] = str(record['confidence'])
        
        if 'operation' in record:
            attributes['cat'] = self._escape_leef(record['operation'])
        
        if 'severity' in record:
            attributes['sev'] = str(self._map_severity(record['severity']))
        
        # Custom attributes
        for key in ['case_id', 'proof_hash', 'merkle_root', 'outcome']:
            if key in record:
                attributes[key] = self._escape_leef(str(record[key]))
        
        return attributes
    
    @staticmethod
    def _map_severity(severity: str) -> int:
        """Map severity to LEEF numeric (1-10)"""
        severity_map = {
            'DEBUG': 1,
            'INFO': 3,
            'NOTICE': 4,
            'WARNING': 6,
            'ERROR': 8,
            'CRITICAL': 9,
            'FATAL': 10,
        }
        return severity_map.get(severity.upper(), 5)


# ============================================================================
# JSON-LD FORMATTER
# ============================================================================

class JSONLDFormatter(AuditFormatter):
    """
    JSON Linked Data formatter.
    
    Semantic web format with schema.org vocabulary.
    
    Used for:
    - Semantic integration
    - Knowledge graph import
    - Research/academic use
    
    Spec: https://json-ld.org/
    """
    
    CONTEXT = {
        "@vocab": "https://schema.org/",
        "mahoun": "https://mahoun.ai/schema/",
        "auditRecord": "mahoun:AuditRecord",
        "verdictID": "mahoun:verdictID",
        "proofHash": "mahoun:proofHash",
        "merkleRoot": "mahoun:merkleRoot",
        "confidence": "mahoun:confidenceScore",
    }
    
    def format(self, records: List[Dict[str, Any]]) -> str:
        """Format records as JSON-LD"""
        # Build JSON-LD document
        document = {
            "@context": self.CONTEXT,
            "@type": "Collection",
            "@id": f"urn:mahoun:audit:export:{datetime.now().isoformat()}",
            "name": "MAHOUN Audit Trail Export",
            "description": "Cryptographically verified audit trail from MAHOUN Legal AI Platform",
            "numberOfItems": len(records),
            "member": [self._format_record(record) for record in records],
        }
        
        return json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    
    def _format_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Format single record as JSON-LD"""
        json_ld = {
            "@type": "auditRecord",
            "@id": f"urn:mahoun:audit:{record.get('id', 'unknown')}",
        }
        
        # Map fields to schema.org vocabulary
        if 'timestamp' in record:
            json_ld['dateCreated'] = self._normalize_timestamp(record['timestamp'])
        
        if 'actor_id' in record:
            json_ld['agent'] = {
                "@type": "Person",
                "identifier": record['actor_id'],
            }
        
        if 'operation' in record:
            json_ld['actionType'] = record['operation']
        
        if 'verdict_id' in record:
            json_ld['verdictID'] = record['verdict_id']
        
        if 'confidence' in record:
            json_ld['confidence'] = record['confidence']
        
        if 'correlation_id' in record:
            json_ld['identifier'] = record['correlation_id']
        
        # Add custom mahoun fields
        for key in ['proof_hash', 'merkle_root', 'case_id']:
            if key in record:
                json_ld[key] = record[key]
        
        return json_ld


# ============================================================================
# JSONL FORMATTER
# ============================================================================

class JSONLFormatter(AuditFormatter):
    """
    JSON Lines formatter (newline-delimited JSON).
    
    One JSON object per line - efficient for streaming and bulk processing.
    
    Used by:
    - Elasticsearch
    - BigQuery
    - Many data pipelines
    
    Spec: https://jsonlines.org/
    """
    
    def format(self, records: List[Dict[str, Any]]) -> str:
        """Format records as JSONL"""
        lines = []
        
        for record in records:
            # Ensure deterministic ordering
            sorted_record = dict(sorted(record.items()))
            line = json.dumps(sorted_record, ensure_ascii=False, separators=(',', ':'))
            lines.append(line)
        
        return "\n".join(lines) + "\n"


# ============================================================================
# CSV FORMATTER
# ============================================================================

class CSVFormatter(AuditFormatter):
    """
    CSV (Comma-Separated Values) formatter.
    
    Excel-compatible format for analysis and reporting.
    
    Used for:
    - Excel import
    - Data analysis
    - Reporting
    """
    
    # Standard columns (deterministic order)
    COLUMNS = [
        'id',
        'timestamp',
        'correlation_id',
        'actor_id',
        'operation',
        'verdict_id',
        'confidence',
        'case_id',
        'outcome',
        'severity',
        'source_ip',
        'proof_hash',
        'merkle_root',
    ]
    
    def format(self, records: List[Dict[str, Any]]) -> str:
        """Format records as CSV"""
        output = StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=self.COLUMNS,
            extrasaction='ignore',
            quoting=csv.QUOTE_MINIMAL,
        )
        
        # Write header
        writer.writeheader()
        
        # Write records
        for record in records:
            # Flatten nested structures
            flat_record = self._flatten_record(record)
            writer.writerow(flat_record)
        
        return output.getvalue()
    
    def _flatten_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Flatten nested structures for CSV"""
        flat = {}
        
        for col in self.COLUMNS:
            value = record.get(col, '')
            
            # Convert to string
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            elif value is None:
                value = ''
            else:
                value = str(value)
            
            flat[col] = value
        
        return flat


# ============================================================================
# SQLITE FORMATTER
# ============================================================================

class SQLiteFormatter:
    """
    SQLite database formatter.
    
    Creates a SQLite database file with audit records.
    Efficient for bulk transfer and complex queries on receiving side.
    
    Note: Returns file path, not string content.
    """
    
    def format_to_file(self, records: List[Dict[str, Any]], output_path: str) -> str:
        """
        Format records as SQLite database.
        
        Args:
            records: List of audit records
            output_path: Path to output SQLite file
        
        Returns:
            Path to created SQLite file
        """
        conn = sqlite3.connect(output_path)
        cursor = conn.cursor()
        
        # Create table
        cursor.execute("""
            CREATE TABLE audit_records (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                correlation_id TEXT,
                actor_id TEXT,
                operation TEXT,
                verdict_id TEXT,
                confidence REAL,
                case_id TEXT,
                outcome TEXT,
                severity TEXT,
                source_ip TEXT,
                proof_hash TEXT,
                merkle_root TEXT,
                raw_data TEXT
            )
        """)
        
        # Create indices
        cursor.execute("CREATE INDEX idx_timestamp ON audit_records(timestamp)")
        cursor.execute("CREATE INDEX idx_correlation_id ON audit_records(correlation_id)")
        cursor.execute("CREATE INDEX idx_actor_id ON audit_records(actor_id)")
        cursor.execute("CREATE INDEX idx_verdict_id ON audit_records(verdict_id)")
        
        # Insert records
        for record in records:
            cursor.execute("""
                INSERT INTO audit_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.get('id'),
                record.get('timestamp'),
                record.get('correlation_id'),
                record.get('actor_id'),
                record.get('operation'),
                record.get('verdict_id'),
                record.get('confidence'),
                record.get('case_id'),
                record.get('outcome'),
                record.get('severity'),
                record.get('source_ip'),
                record.get('proof_hash'),
                record.get('merkle_root'),
                json.dumps(record),  # Store full record as JSON
            ))
        
        conn.commit()
        conn.close()
        
        return output_path


# ============================================================================
# FORMATTER REGISTRY
# ============================================================================

FORMATTERS = {
    'cef': CEFFormatter,
    'leef': LEEFFormatter,
    'json-ld': JSONLDFormatter,
    'jsonl': JSONLFormatter,
    'csv': CSVFormatter,
    'sqlite': SQLiteFormatter,
}


def get_formatter(format_name: str) -> AuditFormatter:
    """Get formatter by name"""
    formatter_class = FORMATTERS.get(format_name.lower())
    if not formatter_class:
        raise ValueError(f"Unknown format: {format_name}")
    return formatter_class()
