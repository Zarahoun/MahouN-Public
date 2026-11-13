"""
Advanced Orphan Node Classification System
==========================================
Intelligent classification of orphaned graph nodes for automated cleanup.

This module provides sophisticated logic to determine whether orphaned nodes
are safe for automated deletion or require manual review, based on multiple
risk factors and business rules.

Classification Categories:
- SAFE: Low-risk nodes eligible for automated cleanup
- RISKY: High-risk nodes requiring human review
- CRITICAL: Never delete (protected entity types)
- SUSPICIOUS: Potentially malicious or corrupted nodes
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Set, Any
from mahoun.graph.validation.ultra_integrity_validator import AdvancedViolation

logger = logging.getLogger(__name__)


class OrphanRiskLevel(Enum):
    """Risk levels for orphaned node classification"""
    SAFE = "safe"
    RISKY = "risky"
    CRITICAL = "critical"
    SUSPICIOUS = "suspicious"


class CleanupAction(Enum):
    """Recommended actions for orphaned nodes"""
    DELETE = "delete"
    REVIEW = "review" 
    PRESERVE = "preserve"
    QUARANTINE = "quarantine"


@dataclass
class OrphanClassification:
    """Result of orphan node classification"""
    node_id: str
    label: str
    risk_level: OrphanRiskLevel
    action: CleanupAction
    confidence_score: float  # 0.0 - 1.0
    age_days: int
    reasons: List[str]
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "label": self.label,
            "classification": self.risk_level.value,
            "action": self.action.value,
            "confidence_score": round(self.confidence_score, 3),
            "age_days": self.age_days,
            "reason": "; ".join(self.reasons),
            "metadata": self.metadata
        }


class AdvancedOrphanClassifier:
    """
    Enterprise-grade orphan node classifier with ML-inspired scoring
    
    Features:
    - Multi-factor risk assessment
    - Configurable safety thresholds
    - Business rule engine
    - Anomaly detection
    - Audit trail generation
    """
    
    def __init__(
        self,
        age_threshold_days: int = 30,
        confidence_threshold: float = 0.8,
        enable_anomaly_detection: bool = True
    ):
        self.age_threshold_days = age_threshold_days
        self.confidence_threshold = confidence_threshold
        self.enable_anomaly_detection = enable_anomaly_detection
        
        # Protected entity types (never auto-delete)
        self.critical_labels = {
            'Evidence', 'Precedent', 'Constitutional', 'LegalRule', 
            'CaseOutcome', 'Statute', 'Regulation', 'Contract',
            'Judge', 'Court', 'Jurisdiction', 'Client'
        }
        
        # Safe entity types (likely to be cleanup candidates)
        self.safe_labels = {
            'TempNode', 'DraftDocument', 'WorkingNotes', 'SessionData',
            'CacheEntry', 'LogEntry', 'TemporaryReference'
        }
        
        # Suspicious patterns (potential security issues)
        self.suspicious_patterns = {
            'rapid_creation': 'Multiple similar nodes created within minutes',
            'unusual_properties': 'Non-standard or potentially malicious properties',
            'broken_references': 'References to deleted or non-existent entities',
            'encoding_anomalies': 'Unusual character encoding or data format'
        }
    
    def classify_orphan(self, violation: AdvancedViolation) -> OrphanClassification:
        """
        Perform comprehensive classification of an orphaned node
        
        Args:
            violation: AdvancedViolation from UltraIntegrityValidator
            
        Returns:
            OrphanClassification with risk assessment and recommended action
        """
        # Extract basic information
        node_id = getattr(violation, 'entity_id', 'unknown')
        label = getattr(violation, 'entity_label', 'Unknown')
        metadata = getattr(violation, 'metadata', {})
        age_days = metadata.get('age_days', 0)
        
        # Initialize scoring
        risk_factors = []
        safety_factors = []
        confidence_modifiers = []
        
        # Factor 1: Entity Type Assessment
        type_assessment = self._assess_entity_type(label)
        if type_assessment['is_critical']:
            return OrphanClassification(
                node_id=node_id,
                label=label,
                risk_level=OrphanRiskLevel.CRITICAL,
                action=CleanupAction.PRESERVE,
                confidence_score=1.0,
                age_days=age_days,
                reasons=[f"Protected entity type: {label}"],
                metadata=metadata
            )
        
        risk_factors.extend(type_assessment['risk_factors'])
        safety_factors.extend(type_assessment['safety_factors'])
        
        # Factor 2: Age Assessment
        age_assessment = self._assess_node_age(age_days)
        risk_factors.extend(age_assessment['risk_factors'])
        safety_factors.extend(age_assessment['safety_factors'])
        
        # Factor 3: Relationship Analysis
        relationship_assessment = self._assess_relationships(metadata)
        risk_factors.extend(relationship_assessment['risk_factors'])
        safety_factors.extend(relationship_assessment['safety_factors'])
        
        # Factor 4: Activity Pattern Analysis
        activity_assessment = self._assess_activity_patterns(metadata)
        risk_factors.extend(activity_assessment['risk_factors'])
        safety_factors.extend(activity_assessment['safety_factors'])
        
        # Factor 5: Anomaly Detection
        if self.enable_anomaly_detection:
            anomaly_assessment = self._detect_anomalies(node_id, label, metadata)
            if anomaly_assessment['is_suspicious']:
                return OrphanClassification(
                    node_id=node_id,
                    label=label,
                    risk_level=OrphanRiskLevel.SUSPICIOUS,
                    action=CleanupAction.QUARANTINE,
                    confidence_score=anomaly_assessment['confidence'],
                    age_days=age_days,
                    reasons=anomaly_assessment['reasons'],
                    metadata=metadata
                )
            confidence_modifiers.extend(anomaly_assessment['confidence_modifiers'])
        
        # Calculate final risk score
        risk_score = self._calculate_risk_score(risk_factors, safety_factors)
        confidence_score = self._calculate_confidence(risk_factors, safety_factors, confidence_modifiers)
        
        # Determine final classification
        if risk_score <= 0.3 and confidence_score >= self.confidence_threshold:
            risk_level = OrphanRiskLevel.SAFE
            action = CleanupAction.DELETE
        elif risk_score <= 0.6:
            risk_level = OrphanRiskLevel.RISKY
            action = CleanupAction.REVIEW
        else:
            risk_level = OrphanRiskLevel.CRITICAL
            action = CleanupAction.PRESERVE
        
        # Compile reasons
        all_reasons = risk_factors + [f"Confidence: {confidence_score:.2f}"]
        
        return OrphanClassification(
            node_id=node_id,
            label=label,
            risk_level=risk_level,
            action=action,
            confidence_score=confidence_score,
            age_days=age_days,
            reasons=all_reasons,
            metadata=metadata
        )
    
    def classify_batch(self, violations: List[AdvancedViolation]) -> List[OrphanClassification]:
        """Classify multiple orphaned nodes efficiently"""
        classifications = []
        
        for violation in violations:
            try:
                classification = self.classify_orphan(violation)
                classifications.append(classification)
            except Exception as e:
                logger.error(f"Failed to classify orphan {getattr(violation, 'entity_id', 'unknown')}: {e}")
                # Create safe fallback classification
                classifications.append(OrphanClassification(
                    node_id=getattr(violation, 'entity_id', 'unknown'),
                    label=getattr(violation, 'entity_label', 'Unknown'),
                    risk_level=OrphanRiskLevel.RISKY,
                    action=CleanupAction.REVIEW,
                    confidence_score=0.0,
                    age_days=0,
                    reasons=[f"Classification failed: {str(e)}"],
                    metadata={}
                ))
        
        return classifications
    
    def _assess_entity_type(self, label: str) -> Dict[str, Any]:
        """Assess risk based on entity type"""
        assessment = {
            'is_critical': False,
            'risk_factors': [],
            'safety_factors': []
        }
        
        if label in self.critical_labels:
            assessment['is_critical'] = True
            return assessment
        
        if label in self.safe_labels:
            assessment['safety_factors'].append(f"Safe entity type: {label}")
        elif label.startswith(('Temp', 'Draft', 'Cache', 'Session')):
            assessment['safety_factors'].append(f"Temporary entity pattern: {label}")
        else:
            assessment['risk_factors'].append(f"Unknown entity type: {label}")
        
        return assessment
    
    def _assess_node_age(self, age_days: int) -> Dict[str, Any]:
        """Assess risk based on node age"""
        assessment = {'risk_factors': [], 'safety_factors': []}
        
        if age_days >= self.age_threshold_days * 2:  # Very old
            assessment['safety_factors'].append(f"Very old node ({age_days} days)")
        elif age_days >= self.age_threshold_days:  # Old enough
            assessment['safety_factors'].append(f"Old enough for cleanup ({age_days} days)")
        elif age_days >= 7:  # Recent but not too recent
            assessment['risk_factors'].append(f"Relatively recent ({age_days} days)")
        else:  # Too recent
            assessment['risk_factors'].append(f"Too recent ({age_days} days)")
        
        return assessment
    
    def _assess_relationships(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Assess risk based on relationship patterns"""
        assessment = {'risk_factors': [], 'safety_factors': []}
        
        relationship_count = metadata.get('relationship_count', 0)
        incoming_count = metadata.get('incoming_relationships', 0)
        outgoing_count = metadata.get('outgoing_relationships', 0)
        
        if relationship_count == 0:
            assessment['safety_factors'].append("No relationships found")
        elif relationship_count <= 2:
            assessment['risk_factors'].append(f"Few relationships ({relationship_count})")
        else:
            assessment['risk_factors'].append(f"Many relationships ({relationship_count})")
        
        if incoming_count > outgoing_count * 2:
            assessment['risk_factors'].append("High incoming/outgoing relationship ratio")
        
        return assessment
    
    def _assess_activity_patterns(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Assess risk based on activity patterns"""
        assessment = {'risk_factors': [], 'safety_factors': []}
        
        last_updated = metadata.get('last_updated')
        creation_date = metadata.get('creation_date')
        access_count = metadata.get('access_count', 0)
        
        if last_updated:
            try:
                # Calculate days since last update
                last_update_date = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
                now_tz = datetime.now(last_update_date.tzinfo or timezone.utc)
                days_since_update = (now_tz - last_update_date).days
                
                if days_since_update >= 90:
                    assessment['safety_factors'].append(f"No activity for {days_since_update} days")
                elif days_since_update >= 30:
                    assessment['safety_factors'].append(f"Low activity ({days_since_update} days)")
                else:
                    assessment['risk_factors'].append(f"Recent activity ({days_since_update} days ago)")
            except Exception:
                assessment['risk_factors'].append("Invalid last_updated timestamp")
        
        if access_count == 0:
            assessment['safety_factors'].append("Never accessed")
        elif access_count <= 5:
            assessment['safety_factors'].append(f"Low access count ({access_count})")
        else:
            assessment['risk_factors'].append(f"High access count ({access_count})")
        
        return assessment
    
    def _detect_anomalies(self, node_id: str, label: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Detect suspicious patterns that might indicate security issues"""
        assessment = {
            'is_suspicious': False,
            'confidence': 1.0,
            'reasons': [],
            'confidence_modifiers': []
        }
        
        # Check for rapid creation patterns
        creation_date = metadata.get('creation_date')
        if creation_date and 'batch_created' in metadata:
            assessment['reasons'].append("Part of rapid batch creation")
            assessment['confidence_modifiers'].append(-0.1)
        
        # Check for unusual properties
        if metadata.get('has_binary_data', False):
            assessment['reasons'].append("Contains binary data")
            assessment['confidence_modifiers'].append(-0.2)
        
        # Check for encoding issues
        try:
            node_id.encode('utf-8')
            label.encode('utf-8')
        except UnicodeEncodeError:
            assessment['is_suspicious'] = True
            assessment['confidence'] = 0.9
            assessment['reasons'].append("Character encoding anomalies detected")
        
        # Check for size anomalies
        node_size = metadata.get('estimated_size_bytes', 0)
        if node_size > 1024 * 1024:  # > 1MB
            assessment['reasons'].append(f"Unusually large node ({node_size} bytes)")
            assessment['confidence_modifiers'].append(-0.3)
        
        return assessment
    
    def _calculate_risk_score(self, risk_factors: List[str], safety_factors: List[str]) -> float:
        """Calculate normalized risk score (0.0 = safe, 1.0 = risky)"""
        risk_weight = len(risk_factors) * 0.2
        safety_weight = len(safety_factors) * -0.15
        
        base_score = 0.5  # Neutral starting point
        final_score = base_score + risk_weight + safety_weight
        
        # Normalize to 0.0-1.0 range
        return max(0.0, min(1.0, final_score))
    
    def _calculate_confidence(
        self, 
        risk_factors: List[str], 
        safety_factors: List[str], 
        modifiers: List[float]
    ) -> float:
        """Calculate confidence score for the classification"""
        base_confidence = 0.7  # Default confidence
        
        # More factors = higher confidence
        factor_boost = min(0.2, (len(risk_factors) + len(safety_factors)) * 0.05)
        
        # Apply modifiers
        modifier_impact = sum(modifiers)
        
        final_confidence = base_confidence + factor_boost + modifier_impact
        return max(0.0, min(1.0, final_confidence))


# Factory function
def create_orphan_classifier(**kwargs) -> AdvancedOrphanClassifier:
    """Factory function to create classifier instance"""
    return AdvancedOrphanClassifier(**kwargs)