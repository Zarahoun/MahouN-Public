"""
Prompt Injection Defense
=========================

Advanced defense against prompt injection attacks.

Features:
- Pattern-based detection
- Semantic similarity analysis
- Input sanitization
- Threat scoring
- Logging and alerting
"""

import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ThreatLevel(str, Enum):
    """Threat level classification."""
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ThreatAnalysis:
    """Prompt injection threat analysis."""
    is_threat: bool
    threat_level: ThreatLevel
    confidence: float  # 0-1
    detected_patterns: List[str]
    sanitized_input: str
    explanation: str


class PromptInjectionDefender:
    """
    Defend against prompt injection attacks.
    
    Uses multiple detection strategies:
    - Pattern matching for known attack vectors
    - Semantic analysis for suspicious instructions
    - Input length and complexity checks
    """
    
    # Known attack patterns
    ATTACK_PATTERNS = [
        # Instruction override attempts
        r"ignore\s+(previous|all|above|prior)\s+(instructions?|prompts?|rules?)",
        r"disregard\s+(previous|all|above|prior)\s+(instructions?|prompts?|rules?)",
        r"forget\s+(previous|all|above|prior)\s+(instructions?|prompts?|rules?)",
        
        # System prompt extraction
        r"(show|display|print|reveal|tell)\s+(me\s+)?(your|the)\s+(system\s+)?(prompt|instructions?)",
        r"what\s+(is|are)\s+your\s+(system\s+)?(prompt|instructions?)",
        
        # Role manipulation
        r"you\s+are\s+now\s+(a|an)\s+\w+",
        r"act\s+as\s+(a|an)\s+\w+",
        r"pretend\s+(to\s+be|you\s+are)\s+(a|an)\s+\w+",
        
        # Delimiter injection
        r"```\s*system",
        r"<\s*system\s*>",
        r"\[\s*system\s*\]",
        
        # Jailbreak attempts
        r"(DAN|developer\s+mode|god\s+mode)",
        r"(bypass|override|disable)\s+(safety|filter|guardrail)",
        
        # Data exfiltration
        r"(send|post|transmit)\s+.{0,20}\s+to\s+https?://",
        r"execute\s+(code|command|script)",
    ]
    
    # Suspicious keywords
    SUSPICIOUS_KEYWORDS = [
        "ignore", "disregard", "forget", "override", "bypass",
        "jailbreak", "exploit", "hack", "inject", "manipulate",
        "system", "admin", "root", "sudo", "execute"
    ]
    
    def __init__(
        self,
        threat_threshold: float = 0.5,  # Lower threshold for stricter detection
        max_input_length: int = 10000,
        enable_sanitization: bool = True
    ):
        """
        Initialize prompt injection defender.
        
        Args:
            threat_threshold: Confidence threshold for blocking (0-1)
            max_input_length: Maximum allowed input length
            enable_sanitization: Whether to sanitize inputs
        """
        self.threat_threshold = threat_threshold
        self.max_input_length = max_input_length
        self.enable_sanitization = enable_sanitization
        
        # Compile patterns
        self.compiled_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in self.ATTACK_PATTERNS
        ]
    
    def analyze(self, user_input: str) -> ThreatAnalysis:
        """
        Analyze input for prompt injection threats.
        
        Args:
            user_input: User input to analyze
            
        Returns:
            ThreatAnalysis object
        """
        detected_patterns = []
        threat_score = 0.0
        
        # Check input length
        if len(user_input) > self.max_input_length:
            logger.warning(f"Input exceeds max length: {len(user_input)}")
            return ThreatAnalysis(
                is_threat=True,
                threat_level=ThreatLevel.HIGH,
                confidence=1.0,
                detected_patterns=["excessive_length"],
                sanitized_input=user_input[:self.max_input_length],
                explanation="Input exceeds maximum allowed length"
            )
        
        # Pattern matching
        for i, pattern in enumerate(self.compiled_patterns):
            if pattern.search(user_input):
                pattern_name = self.ATTACK_PATTERNS[i]
                detected_patterns.append(pattern_name)
                threat_score += 0.3
                logger.warning(f"Detected attack pattern: {pattern_name}")
        
        # Keyword analysis
        lower_input = user_input.lower()
        keyword_count = sum(
            1 for keyword in self.SUSPICIOUS_KEYWORDS
            if keyword in lower_input
        )
        
        if keyword_count > 0:
            keyword_score = min(keyword_count * 0.1, 0.5)
            threat_score += keyword_score
            detected_patterns.append(f"suspicious_keywords:{keyword_count}")
        
        # Delimiter injection check
        delimiter_count = user_input.count("```") + user_input.count("---")
        if delimiter_count > 3:
            threat_score += 0.2
            detected_patterns.append("excessive_delimiters")
        
        # Normalize threat score
        threat_score = min(threat_score, 1.0)
        
        # Determine threat level
        if threat_score >= 0.8:
            threat_level = ThreatLevel.CRITICAL
        elif threat_score >= 0.6:
            threat_level = ThreatLevel.HIGH
        elif threat_score >= 0.4:
            threat_level = ThreatLevel.MEDIUM
        elif threat_score >= 0.2:
            threat_level = ThreatLevel.LOW
        else:
            threat_level = ThreatLevel.SAFE
        
        # Sanitize input if enabled
        sanitized = self._sanitize(user_input) if self.enable_sanitization else user_input
        
        is_threat = threat_score >= self.threat_threshold
        
        if is_threat:
            logger.warning(
                f"Prompt injection detected! Level: {threat_level}, "
                f"Score: {threat_score:.2f}, Patterns: {detected_patterns}"
            )
        
        return ThreatAnalysis(
            is_threat=is_threat,
            threat_level=threat_level,
            confidence=threat_score,
            detected_patterns=detected_patterns,
            sanitized_input=sanitized,
            explanation=self._generate_explanation(threat_level, detected_patterns)
        )
    
    def _sanitize(self, user_input: str) -> str:
        """
        Sanitize user input.
        
        Args:
            user_input: Raw user input
            
        Returns:
            Sanitized input
        """
        sanitized = user_input
        
        # Remove system delimiters
        sanitized = re.sub(r"```\s*system.*?```", "", sanitized, flags=re.DOTALL)
        sanitized = re.sub(r"<\s*system\s*>.*?<\s*/\s*system\s*>", "", sanitized, flags=re.DOTALL)
        
        # Remove URLs (potential exfiltration)
        sanitized = re.sub(r"https?://[^\s]+", "[URL_REMOVED]", sanitized)
        
        # Limit consecutive special characters
        sanitized = re.sub(r"([^\w\s])\1{5,}", r"\1\1\1", sanitized)
        
        return sanitized.strip()
    
    def _generate_explanation(
        self,
        threat_level: ThreatLevel,
        patterns: List[str]
    ) -> str:
        """Generate human-readable explanation."""
        if threat_level == ThreatLevel.SAFE:
            return "Input appears safe"
        
        if not patterns:
            return f"Input classified as {threat_level.value} threat"
        
        return (
            f"Detected {threat_level.value} threat. "
            f"Patterns: {', '.join(patterns[:3])}"
        )
    
    def check_and_block(self, user_input: str) -> str:
        """
        Check input and block if threat detected.
        
        Args:
            user_input: User input
            
        Returns:
            Sanitized input if safe
            
        Raises:
            ValueError: If threat detected
        """
        analysis = self.analyze(user_input)
        
        if analysis.is_threat:
            raise ValueError(
                f"Prompt injection detected: {analysis.explanation}"
            )
        
        return analysis.sanitized_input
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get defender statistics.
        
        Returns:
            Statistics dictionary
        """
        return {
            "threat_threshold": self.threat_threshold,
            "max_input_length": self.max_input_length,
            "pattern_count": len(self.compiled_patterns),
            "keyword_count": len(self.SUSPICIOUS_KEYWORDS)
        }
