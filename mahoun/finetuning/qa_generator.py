"""
Q&A Generator
=============
Advanced Q&A pair generation from document text.

Supports multiple strategies:
- LLM-based generation
- Template-based extraction
- Extractive Q&A
- Hybrid approach

Integrates with Mahoun's LLM infrastructure.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

import numpy as np

from .config import (
    QAGeneratorConfig,
    QAGenerationStrategy,
    DomainType,
)
from .qa_templates import (
    QATemplate,
    template_registry,
    LLM_QA_GENERATION_PROMPT,
    LLM_QA_REFINEMENT_PROMPT,
)

logger = logging.getLogger(__name__)


@dataclass
class QAPair:
    """Generated Q&A pair"""
    question: str
    answer: str
    
    # Metadata
    qa_id: str
    source_chunk_id: str
    source_text: str
    
    # Quality indicators
    question_type: str  # factual, reasoning, comparison
    difficulty: str  # easy, medium, hard
    confidence: float  # 0-1
    
    # Evidence linking (for groundedness)
    evidence_span: Optional[str] = None
    evidence_start: Optional[int] = None
    evidence_end: Optional[int] = None
    
    # Generation metadata
    generation_strategy: str = "unknown"
    template_id: Optional[str] = None
    generated_at: datetime = field(default_factory=datetime.now)
    
    # Validation
    is_valid: bool = True
    validation_errors: List[str] = field(default_factory=list)


class QAGenerator:
    """
    Advanced Q&A Generator with multiple strategies.
    
    Usage:
        generator = QAGenerator(config)
        qa_pairs = await generator.generate(text, chunk_id="chunk_001")
    """
    
    def __init__(self, config: Optional[QAGeneratorConfig] = None):
        self.config = config or QAGeneratorConfig()
        self._llm_client = None
        self._qa_counter = 0
    
    async def _get_llm_client(self):
        """Lazy initialization of LLM client"""
        if self._llm_client is None:
            try:
                from mahoun.pipelines.llm.ollama_llm import OllamaLLMService
                self._llm_client = OllamaLLMService(model=self.config.llm_model)
            except ImportError:
                logger.warning("OllamaLLM not available, using mock")
                self._llm_client = MockLLMClient()
        return self._llm_client
    
    def _generate_qa_id(self) -> str:
        """Generate unique Q&A ID"""
        self._qa_counter += 1
        return f"qa_{datetime.now().strftime('%Y%m%d%H%M%S')}_{self._qa_counter:04d}"
    
    async def generate(
        self,
        text: str,
        chunk_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[QAPair]:
        """
        Generate Q&A pairs from text.
        
        Args:
            text: Source text to generate Q&A from
            chunk_id: ID of the source chunk
            metadata: Optional metadata about the text
        
        Returns:
            List of QAPair objects
        """
        if not text or len(text.strip()) < 50:
            logger.warning(f"Text too short for Q&A generation: {len(text)} chars")
            return []
        
        strategy = self.config.strategy
        
        if strategy == QAGenerationStrategy.LLM_BASED:
            return await self._generate_llm_based(text, chunk_id, metadata)
        elif strategy == QAGenerationStrategy.TEMPLATE_BASED:
            return self._generate_template_based(text, chunk_id, metadata)
        elif strategy == QAGenerationStrategy.EXTRACTIVE:
            return self._generate_extractive(text, chunk_id, metadata)
        elif strategy == QAGenerationStrategy.HYBRID:
            return await self._generate_hybrid(text, chunk_id, metadata)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")
    
    async def _generate_llm_based(
        self,
        text: str,
        chunk_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[QAPair]:
        """Generate Q&A using LLM"""
        llm = await self._get_llm_client()
        
        # Determine language
        language = "Persian" if self._is_persian(text) else "English"
        
        # Build prompt
        num_pairs = min(
            self.config.max_qa_pairs_per_chunk,
            max(self.config.min_qa_pairs_per_chunk, len(text) // 200)
        )
        
        prompt = LLM_QA_GENERATION_PROMPT.format(
            num_pairs=num_pairs,
            domain=self.config.domain.value,
            text=text[:2000],  # Limit text length
            language=language
        )
        
        try:
            response = await llm.generate(
                prompt=prompt,
                temperature=self.config.llm_temperature,
                max_tokens=self.config.llm_max_tokens
            )
            
            # Parse JSON response
            qa_data = self._parse_llm_response(response)
            
            # Convert to QAPair objects
            qa_pairs = []
            for item in qa_data:
                qa_pair = QAPair(
                    question=item.get("question", ""),
                    answer=item.get("answer", ""),
                    qa_id=self._generate_qa_id(),
                    source_chunk_id=chunk_id,
                    source_text=text,
                    question_type=item.get("type", "factual"),
                    difficulty="medium",
                    confidence=0.8,
                    evidence_span=item.get("evidence"),
                    generation_strategy="llm_based"
                )
                
                # Validate
                if self._validate_qa_pair(qa_pair):
                    qa_pairs.append(qa_pair)
            
            logger.info(f"LLM generated {len(qa_pairs)} Q&A pairs for chunk {chunk_id}")
            return qa_pairs
            
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            # Fallback to template-based
            return self._generate_template_based(text, chunk_id, metadata)
    
    def _generate_template_based(
        self,
        text: str,
        chunk_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[QAPair]:
        """Generate Q&A using domain templates"""
        templates = template_registry.get_templates(self.config.domain)
        qa_pairs = []
        
        for template in templates:
            # Try to extract answer using template pattern
            matches = re.findall(template.answer_extraction, text, re.IGNORECASE | re.DOTALL)
            
            if matches:
                # Use first match as answer
                answer = matches[0] if isinstance(matches[0], str) else matches[0][0]
                answer = answer.strip()
                
                if len(answer) >= self.config.min_answer_length:
                    qa_pair = QAPair(
                        question=template.question_pattern,
                        answer=answer,
                        qa_id=self._generate_qa_id(),
                        source_chunk_id=chunk_id,
                        source_text=text,
                        question_type=template.question_type,
                        difficulty=template.difficulty,
                        confidence=0.9,  # High confidence for template matches
                        evidence_span=answer,
                        generation_strategy="template_based",
                        template_id=template.template_id
                    )
                    
                    if self._validate_qa_pair(qa_pair):
                        qa_pairs.append(qa_pair)
        
        logger.info(f"Template generated {len(qa_pairs)} Q&A pairs for chunk {chunk_id}")
        return qa_pairs[:self.config.max_qa_pairs_per_chunk]
    
    def _generate_extractive(
        self,
        text: str,
        chunk_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[QAPair]:
        """Generate Q&A by extracting from text structure"""
        qa_pairs = []
        
        # Split into sentences
        sentences = self._split_sentences(text)
        
        # Look for question-like patterns
        question_patterns = [
            r"^(چه|کی|کجا|چرا|چگونه|آیا|کدام)",  # Persian
            r"^(what|who|where|when|why|how|which|is|are|do|does)",  # English
        ]
        
        for i, sentence in enumerate(sentences):
            for pattern in question_patterns:
                if re.match(pattern, sentence.strip(), re.IGNORECASE):
                    # This sentence is a question, next sentence might be answer
                    if i + 1 < len(sentences):
                        answer = sentences[i + 1].strip()
                        if len(answer) >= self.config.min_answer_length:
                            qa_pair = QAPair(
                                question=sentence.strip(),
                                answer=answer,
                                qa_id=self._generate_qa_id(),
                                source_chunk_id=chunk_id,
                                source_text=text,
                                question_type="factual",
                                difficulty="easy",
                                confidence=0.7,
                                evidence_span=answer,
                                generation_strategy="extractive"
                            )
                            qa_pairs.append(qa_pair)
        
        # Also extract from structured patterns (e.g., "X: Y" format)
        colon_pattern = r"([^:]+):\s*([^:]+?)(?:\n|$)"
        for match in re.finditer(colon_pattern, text):
            key, value = match.groups()
            if len(key) < 100 and len(value) >= self.config.min_answer_length:
                question = f"{key.strip()} چیست؟" if self._is_persian(text) else f"What is {key.strip()}?"
                qa_pair = QAPair(
                    question=question,
                    answer=value.strip(),
                    qa_id=self._generate_qa_id(),
                    source_chunk_id=chunk_id,
                    source_text=text,
                    question_type="factual",
                    difficulty="easy",
                    confidence=0.75,
                    evidence_span=value.strip(),
                    generation_strategy="extractive"
                )
                qa_pairs.append(qa_pair)
        
        logger.info(f"Extractive generated {len(qa_pairs)} Q&A pairs for chunk {chunk_id}")
        return qa_pairs[:self.config.max_qa_pairs_per_chunk]
    
    async def _generate_hybrid(
        self,
        text: str,
        chunk_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[QAPair]:
        """Combine multiple strategies for best results"""
        all_pairs: List[QAPair] = []
        
        # 1. Template-based (fast, high precision)
        template_pairs = self._generate_template_based(text, chunk_id, metadata)
        all_pairs.extend(template_pairs)
        
        # 2. Extractive (fast, medium precision)
        extractive_pairs = self._generate_extractive(text, chunk_id, metadata)
        all_pairs.extend(extractive_pairs)
        
        # 3. LLM-based (slower, fills gaps)
        if len(all_pairs) < self.config.min_qa_pairs_per_chunk:
            llm_pairs = await self._generate_llm_based(text, chunk_id, metadata)
            all_pairs.extend(llm_pairs)
        
        # Deduplicate by question similarity
        unique_pairs = self._deduplicate_pairs(all_pairs)
        
        # Sort by confidence
        unique_pairs.sort(key=lambda x: x.confidence, reverse=True)
        
        logger.info(f"Hybrid generated {len(unique_pairs)} unique Q&A pairs for chunk {chunk_id}")
        return unique_pairs[:self.config.max_qa_pairs_per_chunk]
    
    def _validate_qa_pair(self, qa_pair: QAPair) -> bool:
        """Validate a Q&A pair"""
        errors = []
        
        # Check question length
        if len(qa_pair.question) < self.config.min_question_length:
            errors.append(f"Question too short: {len(qa_pair.question)} chars")
        
        # Check answer length
        if len(qa_pair.answer) < self.config.min_answer_length:
            errors.append(f"Answer too short: {len(qa_pair.answer)} chars")
        
        if len(qa_pair.answer) > self.config.max_answer_length:
            errors.append(f"Answer too long: {len(qa_pair.answer)} chars")
        
        # Check for empty content
        if not qa_pair.question.strip():
            errors.append("Empty question")
        
        if not qa_pair.answer.strip():
            errors.append("Empty answer")
        
        # Check for repetition
        if qa_pair.question.strip() == qa_pair.answer.strip():
            errors.append("Question and answer are identical")
        
        qa_pair.validation_errors = errors
        qa_pair.is_valid = len(errors) == 0
        
        return qa_pair.is_valid
    
    def _deduplicate_pairs(self, pairs: List[QAPair]) -> List[QAPair]:
        """Remove duplicate Q&A pairs based on question similarity"""
        if not pairs:
            return []
        
        unique = [pairs[0]]
        
        for pair in pairs[1:]:
            is_duplicate = False
            for existing in unique:
                # Simple similarity check
                similarity = self._text_similarity(pair.question, existing.question)
                if similarity > 0.8:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique.append(pair)
        
        return unique
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple text similarity (Jaccard)"""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union)
    
    def _is_persian(self, text: str) -> bool:
        """Check if text is primarily Persian"""
        persian_chars = len(re.findall(r'[\u0600-\u06FF]', text))
        return persian_chars > len(text) * 0.3
    
    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences"""
        # Handle both Persian and English
        pattern = r'[.!?؟۔]\s+'
        sentences = re.split(pattern, text)
        return [s.strip() for s in sentences if s.strip()]
    
    def _parse_llm_response(self, response: str) -> List[Dict[str, Any]]:
        """Parse LLM JSON response"""
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            
            # Try parsing entire response as JSON
            return json.loads(response)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM response as JSON")
            return []


class MockLLMClient:
    """Mock LLM client for testing"""
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate mock response"""
        return json.dumps([
            {
                "question": "این متن درباره چیست؟",
                "answer": "این متن یک نمونه آزمایشی است.",
                "type": "factual",
                "evidence": "نمونه آزمایشی"
            }
        ])
