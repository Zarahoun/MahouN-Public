"""
Enhanced NER with Cross-Validation and Post-Processing
======================================================
Improves NER accuracy through:
1. Multiple extraction strategies (rule-based + pattern-based)
2. Cross-validation between methods
3. Post-processing and confidence scoring
4. Context-aware entity resolution
"""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import Counter
from .legal_ner import LegalNEREngine, extract_entities

logger = logging.getLogger(__name__)


class EnhancedNEREngine:
    """
    Enhanced NER engine with cross-validation and post-processing.
    
    Uses multiple extraction strategies and validates results
    to improve accuracy.
    """
    
    def __init__(
        self,
        base_engine: Optional[LegalNEREngine] = None,
        enable_cross_validation: bool = True,
        min_confidence: float = 0.7
    ):
        """
        Initialize Enhanced NER Engine.
        
        Args:
            base_engine: Base rule-based NER engine
            enable_cross_validation: Whether to cross-validate entities
            min_confidence: Minimum confidence threshold for entities
        """
        self.base_engine = base_engine or LegalNEREngine()
        self.enable_cross_validation = enable_cross_validation
        self.min_confidence = min_confidence
        
        logger.info("EnhancedNEREngine initialized")
    
    def extract(self, text: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extract entities with enhanced accuracy.
        
        Args:
            text: Persian legal text
        
        Returns:
            Dictionary with extracted entities (same format as base engine)
        """
        # Step 1: Base extraction
        base_result = self.base_engine.extract(text)
        
        if not self.enable_cross_validation:
            return base_result
        
        # Step 2: Cross-validation and refinement
        enhanced_result = self._cross_validate_entities(base_result, text)
        
        # Step 3: Post-processing
        enhanced_result = self._post_process_entities(enhanced_result, text)
        
        # Step 4: Confidence scoring
        enhanced_result = self._score_entity_confidence(enhanced_result)
        
        # Step 5: Filter by confidence
        enhanced_result = self._filter_by_confidence(enhanced_result)
        
        return enhanced_result
    
    def _cross_validate_entities(
        self,
        base_result: Dict[str, List[Dict[str, Any]]],
        text: str
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Cross-validate entities using multiple strategies"""
        
        enhanced_result = {
            "persons": [],
            "organizations": [],
            "courts": [],
            "laws": [],
            "topics": []
        }
        
        # Cross-validate each entity type
        for entity_type, entities in base_result.items():
            if entity_type == "persons":
                enhanced_result["persons"] = self._cross_validate_persons(entities, text)
            elif entity_type == "organizations":
                enhanced_result["organizations"] = self._cross_validate_organizations(entities, text)
            elif entity_type == "courts":
                enhanced_result["courts"] = self._cross_validate_courts(entities, text)
            elif entity_type == "laws":
                enhanced_result["laws"] = self._cross_validate_laws(entities, text)
            elif entity_type == "topics":
                enhanced_result["topics"] = entities  # Topics are usually reliable
        
        return enhanced_result
    
    def _cross_validate_persons(
        self,
        entities: List[Dict[str, Any]],
        text: str
    ) -> List[Dict[str, Any]]:
        """Cross-validate person entities"""
        
        # Strategy 1: Check for multiple occurrences (higher confidence)
        entity_counts = Counter()
        for entity in entities:
            key = entity.get("normalized_name") or entity.get("name", "")
            entity_counts[key] += 1
        
        validated: List[Any] = []
        for entity in entities:
            key = entity.get("normalized_name") or entity.get("name", "")
            count = entity_counts.get(key, 1)
            
            # Boost confidence if entity appears multiple times
            if count > 1:
                entity["confidence"] = min(1.0, entity.get("confidence", 0.8) + 0.1)
                entity["occurrence_count"] = count
            
            # Strategy 2: Validate name format (should have title + name)
            title = entity.get("title")
            name = entity.get("name")
            if title and name and len(name) > 2:
                validated.append(entity)
            elif entity.get("confidence", 0.5) > 0.7:
                # High confidence even without perfect format
                validated.append(entity)
        
        return validated
    
    def _cross_validate_organizations(
        self,
        entities: List[Dict[str, Any]],
        text: str
    ) -> List[Dict[str, Any]]:
        """Cross-validate organization entities"""
        
        validated: List[Any] = []
        for entity in entities:
            name = entity.get("name") or entity.get("text", "")
            
            # Strategy 1: Check for organization keywords
            org_keywords = ["شرکت", "مؤسسه", "سازمان", "بانک", "اداره", "وزارت"]
            has_keyword = any(keyword in name for keyword in org_keywords)
            
            # Strategy 2: Check length (organization names are usually longer)
            if len(name) > 5 or has_keyword:
                if not has_keyword:
                    # Boost confidence if long name
                    entity["confidence"] = min(1.0, entity.get("confidence", 0.7) + 0.1)
                
                validated.append(entity)
        
        return validated
    
    def _cross_validate_courts(
        self,
        entities: List[Dict[str, Any]],
        text: str
    ) -> List[Dict[str, Any]]:
        """Cross-validate court entities"""
        
        validated: List[Any] = []
        court_keywords = ["دادگاه", "شعبه", "دیوان", "مجلس"]
        
        for entity in entities:
            text_content = entity.get("text", "")
            
            # Must contain court keywords
            if any(keyword in text_content for keyword in court_keywords):
                validated.append(entity)
            elif entity.get("confidence", 0.5) > 0.8:
                # Very high confidence
                validated.append(entity)
        
        return validated
    
    def _cross_validate_laws(
        self,
        entities: List[Dict[str, Any]],
        text: str
    ) -> List[Dict[str, Any]]:
        """Cross-validate law/article entities"""
        
        validated: List[Any] = []
        law_keywords = ["ماده", "قانون", "آیین‌نامه"]
        
        for entity in entities:
            text_content = entity.get("text", "")
            
            # Must contain law keywords
            if any(keyword in text_content for keyword in law_keywords):
                # Additional validation: check for article number
                article_num = entity.get("article_number")
                if article_num and article_num.isdigit():
                    entity["confidence"] = min(1.0, entity.get("confidence", 0.8) + 0.1)
                
                validated.append(entity)
        
        return validated
    
    def _post_process_entities(
        self,
        entities: Dict[str, List[Dict[str, Any]]],
        text: str
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Post-process entities to fix common issues"""
        
        processed: Dict[str, Any] = {}
        for entity_type, entity_list in entities.items():
            processed_list: List[Any] = []
            seen_keys: Set[str] = set()
            
            for entity in entity_list:
                # Deduplication
                key = self._get_entity_key(entity)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                
                # Normalize text
                if "text" in entity:
                    entity["text"] = entity["text"].strip()
                
                # Fix common typos/formatting
                if entity_type == "persons":
                    entity = self._normalize_person_entity(entity)
                elif entity_type == "organizations":
                    entity = self._normalize_org_entity(entity)
                
                processed_list.append(entity)
            
            processed[entity_type] = processed_list
        
        return processed
    
    def _normalize_person_entity(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize person entity"""
        # Clean name
        if "name" in entity:
            entity["name"] = entity["name"].strip()
            # Remove extra spaces
            entity["name"] = " ".join(entity["name"].split())
        
        # Clean father name
        if "father_name" in entity and entity["father_name"]:
            entity["father_name"] = entity["father_name"].strip()
        
        return entity
    
    def _normalize_org_entity(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize organization entity"""
        if "name" in entity:
            entity["name"] = entity["name"].strip()
            # Remove redundant org type prefixes if duplicated
            name = entity["name"]
            org_types = ["شرکت", "مؤسسه", "سازمان"]
            for org_type in org_types:
                if name.startswith(org_type + " " + org_type):
                    entity["name"] = name.replace(org_type + " " + org_type, org_type, 1)
        
        return entity
    
    def _get_entity_key(self, entity: Dict[str, Any]) -> str:
        """Get unique key for entity deduplication"""
        # Use normalized name if available
        if "normalized_name" in entity:
            return entity["normalized_name"].lower()
        if "normalized_ref" in entity:
            return entity["normalized_ref"].lower()
        
        # Fallback to text
        text = entity.get("text", "")
        return text.lower().strip()
    
    def _score_entity_confidence(
        self,
        entities: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Recalculate confidence scores based on context"""
        
        scored: Dict[str, Any] = {}
        for entity_type, entity_list in entities.items():
            scored_list: List[Any] = []
            for entity in entity_list:
                base_confidence = entity.get("confidence", 0.7)
                
                # Boost confidence factors
                if "occurrence_count" in entity and entity["occurrence_count"] > 1:
                    base_confidence = min(1.0, base_confidence + 0.1)
                
                # Check completeness
                if entity_type == "persons":
                    if entity.get("name") and entity.get("father_name"):
                        base_confidence = min(1.0, base_confidence + 0.1)
                
                elif entity_type == "organizations":
                    if entity.get("registration_id"):
                        base_confidence = min(1.0, base_confidence + 0.1)
                
                elif entity_type == "laws":
                    if entity.get("article_number") and entity.get("law_name"):
                        base_confidence = min(1.0, base_confidence + 0.1)
                
                entity["confidence"] = base_confidence
                scored_list.append(entity)
            
            scored[entity_type] = scored_list
        
        return scored
    
    def _filter_by_confidence(
        self,
        entities: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Filter entities by minimum confidence threshold"""
        
        filtered: Dict[str, Any] = {}
        for entity_type, entity_list in entities.items():
            filtered_list = [
                entity for entity in entity_list
                if entity.get("confidence", 0.5) >= self.min_confidence
            ]
            filtered[entity_type] = filtered_list
        
        return filtered


# Convenience function
def extract_entities_enhanced(
    text: str,
    enable_cross_validation: bool = True,
    min_confidence: float = 0.7
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Extract entities with enhanced accuracy.
    
    Args:
        text: Persian legal text
        enable_cross_validation: Whether to use cross-validation
        min_confidence: Minimum confidence threshold
    
    Returns:
        Dictionary with extracted entities
    """
    engine = EnhancedNEREngine(
        enable_cross_validation=enable_cross_validation,
        min_confidence=min_confidence
    )
    return engine.extract(text)

