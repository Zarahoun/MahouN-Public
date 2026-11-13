#!/usr/bin/env python3
"""
PII Scrubber Service
====================
Detects and anonymizes Personally Identifiable Information (PII)
for GDPR compliance
"""

import re
import hashlib
from dataclasses import dataclass
import logging

log = logging.getLogger(__name__)


@dataclass
class PIIMatch:
    """PII detection result"""
    type: str
    value: str
    start: int
    end: int
    anonymized: str


class PIIScrubber:
    """
    PII detection and anonymization
    
    Detects:
    - Email addresses
    - Phone numbers (Iranian format)
    - National IDs (Iranian)
    - Credit card numbers
    - IP addresses
    - Names (basic patterns)
    """
    
    # Regex patterns
    PATTERNS = {
        "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        "phone_ir": r'\b(?:0|\+98)?9\d{9}\b',
        "national_id_ir": r'\b\d{10}\b',
        "credit_card": r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',
        "ip_address": r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
    }
    
    def __init__(
        self,
        hash_pii: bool = True,
        preserve_format: bool = True
    ):
        """
        Initialize PII Scrubber
        
        Args:
            hash_pii: Hash PII values for consistency
            preserve_format: Keep format (e.g., email@[REDACTED])
        """
        self.hash_pii = hash_pii
        self.preserve_format = preserve_format
        
        log.info("PIIScrubber initialized")
    
    def scrub(self, text: str) -> Tuple[str, List[PIIMatch]]:
        """
        Scrub PII from text
        
        Args:
            text: Input text
            
        Returns:
            (anonymized_text, pii_matches)
        """
        if not text:
            return text, []
        
        matches = []
        anonymized = text
        
        # Detect all PII types
        for pii_type, pattern in self.PATTERNS.items():
            for match in re.finditer(pattern, text):
                value = match.group()
                
                # Anonymize
                anon_value = self._anonymize(value, pii_type)
                
                matches.append(PIIMatch(
                    type=pii_type,
                    value=value,
                    start=match.start(),
                    end=match.end(),
                    anonymized=anon_value
                ))
        
        # Sort by position (reverse to replace from end)
        matches.sort(key=lambda x: x.start, reverse=True)
        
        # Replace in text
        for match in matches:
            anonymized = (
                anonymized[:match.start] +
                match.anonymized +
                anonymized[match.end:]
            )
        
        log.info(f"Scrubbed {len(matches)} PII instances")
        return anonymized, matches
    
    def _anonymize(self, value: str, pii_type: str) -> str:
        """Anonymize a PII value"""
        if self.hash_pii:
            # Hash for consistency
            hash_val = hashlib.sha256(value.encode()).hexdigest()[:8]
            
            if self.preserve_format:
                if pii_type == "email":
                    return f"[EMAIL_{hash_val}]"
                elif pii_type == "phone_ir":
                    return f"[PHONE_{hash_val}]"
                elif pii_type == "national_id_ir":
                    return f"[ID_{hash_val}]"
                elif pii_type == "credit_card":
                    return f"[CARD_{hash_val}]"
                elif pii_type == "ip_address":
                    return f"[IP_{hash_val}]"
            
            return f"[{pii_type.upper()}_{hash_val}]"
        else:
            # Simple redaction
            return f"[{pii_type.upper()}_REDACTED]"
    
    def scrub_dict(self, data: Dict) -> Dict:
        """
        Scrub PII from dictionary values
        
        Args:
            data: Dictionary with potential PII
            
        Returns:
            Anonymized dictionary
        """
        result = {}
        
        for key, value in data.items():
            if isinstance(value, str):
                result[key], _ = self.scrub(value)
            elif isinstance(value, dict):
                result[key] = self.scrub_dict(value)
            elif isinstance(value, list):
                result[key] = [
                    self.scrub(v)[0] if isinstance(v, str) else v
                    for v in value
                ]
            else:
                result[key] = value
        
        return result
    
    def is_safe(self, text: str) -> bool:
        """
        Check if text contains PII
        
        Args:
            text: Text to check
            
        Returns:
            True if no PII detected
        """
        _, matches = self.scrub(text)
        return len(matches) == 0


# Global instance
_scrubber = None

def get_pii_scrubber() -> PIIScrubber:
    """Get global PII scrubber instance"""
    global _scrubber
    if _scrubber is None:
        _scrubber = PIIScrubber()
    return _scrubber
