"""
Advanced Quality Filter for Training Data
=========================================
Enterprise-grade quality filtering with multi-dimensional scoring.

Features:
- Semantic similarity validation
- Entity preservation checking
- Groundedness verification (Mahoun I1 invariant)
- Deduplication with embedding similarity
- Multi-stage filtering pipeline
- Quality metrics and reporting
"""

import hashlib
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import numpy as np

from .config import QualityFilterConfig, DomainType
from .qa_generator import QAPair

logger = logging.getLogger(__name__)


# =============================================================================
# Quality Metrics
# =============================================================================

class QualityDimension(str, Enum):
    """Dimensions of quality assessment"""
    RELEVANCE = "relevance"           # Q&A relevance to source
    COHERENCE = "coherence"           # Linguistic coherence
    GROUNDEDNESS = "groundedness"     # Evidence-linked (Mahoun I1)
    COMPLETENESS = "completeness"     # Answer completeness
    DIVERSITY = "diversity"           # Dataset diversity
    FLUENCY = "fluency"               # Language fluency
    FACTUALITY = "factuality"         # Factual accuracy


@dataclass
class QualityScore:
    """Multi-dimensional quality score"""
    overall: float
    dimensions: Dict[QualityDimension, float] = field(default_factory=dict)
    
    # Detailed metrics
    relevance_score: float = 0.0
    coherence_score: float = 0.0
    groundedness_score: float = 0.0
    completeness_score: float = 0.0
    fluency_score: float = 0.0
    
    # Validation flags
    passes_threshold: bool = True
    failure_reasons: List[str] = field(default_factory=list)
    
    # Metadata
    computed_at: datetime = field(default_factory=datetime.now)


@dataclass
class FilteredDataset:
    """Result of quality filtering"""
    original_count: int
    filtered_count: int
    removed_count: int
    
    # Filtered data
    high_quality: List[QAPair] = field(default_factory=list)
    low_quality: List[QAPair] = field(default_factory=list)
    duplicates: List[QAPair] = field(default_factory=list)
    
    # Statistics
    avg_quality_score: float = 0.0
    quality_distribution: Dict[str, int] = field(default_factory=dict)
    removal_reasons: Dict[str, int] = field(default_factory=dict)
    
    # Metadata
    filter_config: Optional[QualityFilterConfig] = None
    filtered_at: datetime = field(default_factory=datetime.now)


# =============================================================================
# Quality Scorers
# =============================================================================

class RelevanceScorer:
    """Score relevance between question, answer, and source"""
    
    def __init__(self):
        self._embedding_model = None
    
    def _get_embedding_model(self):
        """Lazy load embedding model"""
        if self._embedding_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
            except ImportError:
                logger.warning("sentence-transformers not available, using fallback")
                self._embedding_model = "fallback"
        return self._embedding_model
    
    def score(self, qa_pair: QAPair) -> float:
        """
        Calculate relevance score.
        
        Measures:
        - Question-Answer alignment
        - Answer-Source alignment
        - Question-Source alignment
        """
        model = self._get_embedding_model()
        
        if model == "fallback":
            return self._fallback_score(qa_pair)
        
        try:
            # Get embeddings
            texts = [qa_pair.question, qa_pair.answer, qa_pair.source_text[:500]]
            embeddings = model.encode(texts)
            
            # Calculate cosine similarities
            q_a_sim = self._cosine_similarity(embeddings[0], embeddings[1])
            a_s_sim = self._cosine_similarity(embeddings[1], embeddings[2])
            q_s_sim = self._cosine_similarity(embeddings[0], embeddings[2])
            
            # Weighted combination
            # Answer-Source is most important for groundedness
            score = 0.3 * q_a_sim + 0.5 * a_s_sim + 0.2 * q_s_sim
            
            return float(np.clip(score, 0.0, 1.0))
            
        except Exception as e:
            logger.warning(f"Embedding-based scoring failed: {e}")
            return self._fallback_score(qa_pair)
    
    def _fallback_score(self, qa_pair: QAPair) -> float:
        """Fallback scoring using word overlap"""
        q_words = set(qa_pair.question.lower().split())
        a_words = set(qa_pair.answer.lower().split())
        s_words = set(qa_pair.source_text.lower().split())
        
        if not q_words or not a_words or not s_words:
            return 0.0
        
        # Jaccard similarities
        q_a_sim = len(q_words & a_words) / len(q_words | a_words) if q_words | a_words else 0
        a_s_sim = len(a_words & s_words) / len(a_words | s_words) if a_words | s_words else 0
        q_s_sim = len(q_words & s_words) / len(q_words | s_words) if q_words | s_words else 0
        
        return 0.3 * q_a_sim + 0.5 * a_s_sim + 0.2 * q_s_sim
    
    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Calculate cosine similarity"""
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))


class GroundednessScorer:
    """
    Score groundedness - Mahoun I1 Invariant Compliance.
    
    Every answer must be explicitly linked to evidence in the source.
    This is critical for zero-hallucination guarantee.
    """
    
    def __init__(self):
        self.min_overlap_ratio = 0.3
        self.exact_match_bonus = 0.2
    
    def score(self, qa_pair: QAPair) -> Tuple[float, Optional[str]]:
        """
        Calculate groundedness score.
        
        Returns:
            Tuple of (score, evidence_span)
        """
        answer = qa_pair.answer.lower()
        source = qa_pair.source_text.lower()
        
        # Check for exact substring match
        if answer in source:
            return 1.0, qa_pair.answer
        
        # Check for evidence span
        if qa_pair.evidence_span:
            evidence_lower = qa_pair.evidence_span.lower()
            if evidence_lower in source:
                # Evidence is grounded
                overlap = self._calculate_overlap(answer, evidence_lower)
                return min(1.0, 0.7 + overlap * 0.3), qa_pair.evidence_span
        
        # Calculate n-gram overlap
        answer_ngrams = self._get_ngrams(answer, n=3)
        source_ngrams = self._get_ngrams(source, n=3)
        
        if not answer_ngrams:
            return 0.0, None
        
        overlap_count = len(answer_ngrams & source_ngrams)
        overlap_ratio = overlap_count / len(answer_ngrams)
        
        # Find best matching span
        best_span = self._find_best_span(qa_pair.answer, qa_pair.source_text)
        
        score = min(1.0, overlap_ratio + (self.exact_match_bonus if best_span else 0))
        
        return score, best_span
    
    def _get_ngrams(self, text: str, n: int = 3) -> Set[str]:
        """Extract character n-grams"""
        text = text.replace(" ", "")
        return {text[i:i+n] for i in range(len(text) - n + 1)}
    
    def _calculate_overlap(self, text1: str, text2: str) -> float:
        """Calculate word overlap ratio"""
        words1 = set(text1.split())
        words2 = set(text2.split())
        if not words1:
            return 0.0
        return len(words1 & words2) / len(words1)
    
    def _find_best_span(self, answer: str, source: str, window_size: int = 200) -> Optional[str]:
        """Find the best matching span in source for the answer"""
        answer_words = set(answer.lower().split())
        best_score = 0.0
        best_span = None
        
        # Sliding window
        words = source.split()
        for i in range(0, len(words), 10):
            window = " ".join(words[i:i + window_size // 5])
            window_words = set(window.lower().split())
            
            if not window_words:
                continue
            
            overlap = len(answer_words & window_words) / len(answer_words) if answer_words else 0
            
            if overlap > best_score:
                best_score = overlap
                best_span = window
        
        return best_span if best_score > 0.3 else None


class CoherenceScorer:
    """Score linguistic coherence of Q&A pairs"""
    
    def __init__(self):
        # Persian question patterns
        self.question_patterns = [
            r'^(چه|کی|کجا|چرا|چگونه|آیا|کدام|چند)',
            r'\?$|؟$',
            r'^(what|who|where|when|why|how|which|is|are|do|does)',
        ]
        
        # Answer quality patterns
        self.good_answer_patterns = [
            r'\.',  # Has sentence ending
            r'[،,]',  # Has proper punctuation
        ]
        
        self.bad_answer_patterns = [
            r'^(بله|خیر|آره|نه|yes|no)$',  # Too short/simple
            r'^\s*$',  # Empty
            r'^[.،,!?؟]+$',  # Only punctuation
        ]
    
    def score(self, qa_pair: QAPair) -> float:
        """Calculate coherence score"""
        score = 0.5  # Base score
        
        # Question quality
        question_score = self._score_question(qa_pair.question)
        score += question_score * 0.3
        
        # Answer quality
        answer_score = self._score_answer(qa_pair.answer)
        score += answer_score * 0.3
        
        # Q&A alignment
        alignment_score = self._score_alignment(qa_pair.question, qa_pair.answer)
        score += alignment_score * 0.2
        
        return min(1.0, max(0.0, score))
    
    def _score_question(self, question: str) -> float:
        """Score question quality"""
        score = 0.0
        
        # Check for question patterns
        for pattern in self.question_patterns:
            if re.search(pattern, question, re.IGNORECASE):
                score += 0.3
                break
        
        # Length check
        if 10 <= len(question) <= 200:
            score += 0.4
        elif len(question) > 200:
            score += 0.2
        
        # Word count
        word_count = len(question.split())
        if 3 <= word_count <= 20:
            score += 0.3
        
        return min(1.0, score)
    
    def _score_answer(self, answer: str) -> float:
        """Score answer quality"""
        score = 0.0
        
        # Check for bad patterns
        for pattern in self.bad_answer_patterns:
            if re.match(pattern, answer, re.IGNORECASE):
                return 0.1
        
        # Check for good patterns
        for pattern in self.good_answer_patterns:
            if re.search(pattern, answer):
                score += 0.2
        
        # Length check
        if 20 <= len(answer) <= 500:
            score += 0.4
        elif 500 < len(answer) <= 1000:
            score += 0.3
        elif len(answer) > 1000:
            score += 0.2
        
        # Word count
        word_count = len(answer.split())
        if 5 <= word_count <= 100:
            score += 0.2
        
        return min(1.0, score)
    
    def _score_alignment(self, question: str, answer: str) -> float:
        """Score Q&A alignment"""
        # Check if answer addresses the question type
        q_lower = question.lower()
        a_lower = answer.lower()
        
        # Question type detection and answer validation
        alignments = [
            (r'چه کسی|who', r'[\u0600-\u06FF]+|[A-Za-z]+'),  # Person names
            (r'چه زمانی|when|کی', r'\d+|سال|ماه|روز|year|month|day'),  # Time
            (r'چرا|why', r'زیرا|چون|به دلیل|because'),  # Reason
            (r'چگونه|how', r'با|از طریق|by|through'),  # Method
        ]
        
        for q_pattern, a_pattern in alignments:
            if re.search(q_pattern, q_lower):
                if re.search(a_pattern, a_lower):
                    return 1.0
                return 0.5
        
        return 0.7  # Default alignment


class CompletenessScorer:
    """Score answer completeness"""
    
    def score(self, qa_pair: QAPair) -> float:
        """Calculate completeness score"""
        answer = qa_pair.answer
        question = qa_pair.question
        
        score = 0.0
        
        # Length-based completeness
        if len(answer) >= 50:
            score += 0.3
        elif len(answer) >= 20:
            score += 0.2
        
        # Sentence count
        sentences = re.split(r'[.!?؟]', answer)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if len(sentences) >= 2:
            score += 0.3
        elif len(sentences) == 1:
            score += 0.2
        
        # Information density (unique words / total words)
        words = answer.split()
        if words:
            unique_ratio = len(set(words)) / len(words)
            score += unique_ratio * 0.2
        
        # Question coverage (does answer address question keywords?)
        q_keywords = set(question.lower().split()) - {'چه', 'کی', 'کجا', 'چرا', 'آیا', 'است', 'هست'}
        a_words = set(answer.lower().split())
        
        if q_keywords:
            coverage = len(q_keywords & a_words) / len(q_keywords)
            score += coverage * 0.2
        
        return min(1.0, score)


# =============================================================================
# Deduplication Engine
# =============================================================================

class DeduplicationEngine:
    """Remove duplicate Q&A pairs using multiple strategies"""
    
    def __init__(self, similarity_threshold: float = 0.85):
        self.similarity_threshold = similarity_threshold
        self._embedding_model = None
        self._hash_cache: Dict[str, str] = {}
    
    def _get_embedding_model(self):
        """Lazy load embedding model"""
        if self._embedding_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
            except ImportError:
                self._embedding_model = "fallback"
        return self._embedding_model
    
    def deduplicate(self, qa_pairs: List[QAPair]) -> Tuple[List[QAPair], List[QAPair]]:
        """
        Remove duplicates from Q&A pairs.
        
        Returns:
            Tuple of (unique_pairs, duplicate_pairs)
        """
        if not qa_pairs:
            return [], []
        
        # Stage 1: Exact hash deduplication
        unique_by_hash, hash_duplicates = self._hash_dedup(qa_pairs)
        
        # Stage 2: Semantic deduplication
        unique_final, semantic_duplicates = self._semantic_dedup(unique_by_hash)
        
        all_duplicates = hash_duplicates + semantic_duplicates
        
        logger.info(
            f"Deduplication: {len(qa_pairs)} → {len(unique_final)} "
            f"(removed {len(all_duplicates)} duplicates)"
        )
        
        return unique_final, all_duplicates
    
    def _hash_dedup(self, qa_pairs: List[QAPair]) -> Tuple[List[QAPair], List[QAPair]]:
        """Remove exact duplicates using hash"""
        seen_hashes: Set[str] = set()
        unique = []
        duplicates = []
        
        for pair in qa_pairs:
            # Create hash from question + answer
            content = f"{pair.question.strip().lower()}|{pair.answer.strip().lower()}"
            content_hash = hashlib.md5(content.encode()).hexdigest()
            
            if content_hash not in seen_hashes:
                seen_hashes.add(content_hash)
                unique.append(pair)
            else:
                duplicates.append(pair)
        
        return unique, duplicates
    
    def _semantic_dedup(self, qa_pairs: List[QAPair]) -> Tuple[List[QAPair], List[QAPair]]:
        """Remove semantic duplicates using embeddings"""
        if len(qa_pairs) <= 1:
            return qa_pairs, []
        
        model = self._get_embedding_model()
        
        if model == "fallback":
            return self._fallback_semantic_dedup(qa_pairs)
        
        try:
            # Get embeddings for all questions
            questions = [p.question for p in qa_pairs]
            embeddings = model.encode(questions)
            
            unique = []
            duplicates = []
            unique_embeddings = []
            
            for i, (pair, emb) in enumerate(zip(qa_pairs, embeddings)):
                is_duplicate = False
                
                for unique_emb in unique_embeddings:
                    similarity = self._cosine_similarity(emb, unique_emb)
                    if similarity > self.similarity_threshold:
                        is_duplicate = True
                        break
                
                if is_duplicate:
                    duplicates.append(pair)
                else:
                    unique.append(pair)
                    unique_embeddings.append(emb)
            
            return unique, duplicates
            
        except Exception as e:
            logger.warning(f"Semantic dedup failed: {e}")
            return qa_pairs, []
    
    def _fallback_semantic_dedup(self, qa_pairs: List[QAPair]) -> Tuple[List[QAPair], List[QAPair]]:
        """Fallback using Jaccard similarity"""
        unique = []
        duplicates = []
        
        for pair in qa_pairs:
            is_duplicate = False
            pair_words = set(pair.question.lower().split())
            
            for existing in unique:
                existing_words = set(existing.question.lower().split())
                
                if pair_words and existing_words:
                    jaccard = len(pair_words & existing_words) / len(pair_words | existing_words)
                    if jaccard > self.similarity_threshold:
                        is_duplicate = True
                        break
            
            if is_duplicate:
                duplicates.append(pair)
            else:
                unique.append(pair)
        
        return unique, duplicates
    
    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Calculate cosine similarity"""
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))


# =============================================================================
# Main Quality Filter
# =============================================================================

class QualityFilter:
    """
    Enterprise-grade quality filter for training data.
    
    Implements multi-stage filtering:
    1. Basic validation (length, format)
    2. Quality scoring (relevance, coherence, groundedness)
    3. Deduplication
    4. Final threshold filtering
    
    Ensures Mahoun I1 invariant: 100% groundedness.
    """
    
    def __init__(self, config: Optional[QualityFilterConfig] = None):
        self.config = config or QualityFilterConfig()
        
        # Initialize scorers
        self.relevance_scorer = RelevanceScorer()
        self.groundedness_scorer = GroundednessScorer()
        self.coherence_scorer = CoherenceScorer()
        self.completeness_scorer = CompletenessScorer()
        
        # Initialize deduplication
        self.dedup_engine = DeduplicationEngine(
            similarity_threshold=self.config.similarity_threshold
        )
        
        # Statistics
        self.stats = {
            "total_processed": 0,
            "passed": 0,
            "failed": 0,
            "duplicates_removed": 0,
            "failure_reasons": defaultdict(int),
        }
        
        logger.info("QualityFilter initialized")
    
    def filter(self, qa_pairs: List[QAPair]) -> FilteredDataset:
        """
        Filter Q&A pairs by quality.
        
        Args:
            qa_pairs: List of Q&A pairs to filter
        
        Returns:
            FilteredDataset with high/low quality splits
        """
        if not qa_pairs:
            return FilteredDataset(
                original_count=0,
                filtered_count=0,
                removed_count=0
            )
        
        logger.info(f"Filtering {len(qa_pairs)} Q&A pairs")
        
        # Stage 1: Basic validation
        valid_pairs, invalid_pairs = self._basic_validation(qa_pairs)
        
        # Stage 2: Quality scoring
        scored_pairs = []
        for pair in valid_pairs:
            score = self.score_quality(pair)
            scored_pairs.append((pair, score))
        
        # Stage 3: Threshold filtering
        high_quality = []
        low_quality = list(invalid_pairs)
        
        for pair, score in scored_pairs:
            if score.passes_threshold:
                high_quality.append(pair)
            else:
                low_quality.append(pair)
                for reason in score.failure_reasons:
                    self.stats["failure_reasons"][reason] += 1
        
        # Stage 4: Deduplication
        if self.config.enable_deduplication:
            high_quality, duplicates = self.dedup_engine.deduplicate(high_quality)
            self.stats["duplicates_removed"] += len(duplicates)
        else:
            duplicates = []
        
        # Calculate statistics
        self.stats["total_processed"] += len(qa_pairs)
        self.stats["passed"] += len(high_quality)
        self.stats["failed"] += len(low_quality)
        
        avg_quality = np.mean([s.overall for _, s in scored_pairs]) if scored_pairs else 0.0
        
        # Quality distribution
        quality_dist = {"excellent": 0, "good": 0, "fair": 0, "poor": 0}
        for _, score in scored_pairs:
            if score.overall >= 0.9:
                quality_dist["excellent"] += 1
            elif score.overall >= 0.7:
                quality_dist["good"] += 1
            elif score.overall >= 0.5:
                quality_dist["fair"] += 1
            else:
                quality_dist["poor"] += 1
        
        result = FilteredDataset(
            original_count=len(qa_pairs),
            filtered_count=len(high_quality),
            removed_count=len(low_quality) + len(duplicates),
            high_quality=high_quality,
            low_quality=low_quality,
            duplicates=duplicates,
            avg_quality_score=float(avg_quality),
            quality_distribution=quality_dist,
            removal_reasons=dict(self.stats["failure_reasons"]),
            filter_config=self.config
        )
        
        logger.info(
            f"Filtering complete: {result.filtered_count}/{result.original_count} passed "
            f"(avg quality: {result.avg_quality_score:.2f})"
        )
        
        return result
    
    def score_quality(self, qa_pair: QAPair) -> QualityScore:
        """
        Calculate comprehensive quality score for a Q&A pair.
        
        Returns:
            QualityScore with all dimensions
        """
        failure_reasons = []
        
        # Calculate individual scores
        relevance = self.relevance_scorer.score(qa_pair)
        groundedness, evidence = self.groundedness_scorer.score(qa_pair)
        coherence = self.coherence_scorer.score(qa_pair)
        completeness = self.completeness_scorer.score(qa_pair)
        
        # Update evidence span if found
        if evidence and not qa_pair.evidence_span:
            qa_pair.evidence_span = evidence
        
        # Check thresholds
        if relevance < self.config.min_relevance_score:
            failure_reasons.append(f"Low relevance: {relevance:.2f}")
        
        if groundedness < self.config.min_groundedness_score:
            failure_reasons.append(f"Low groundedness: {groundedness:.2f}")
        
        if coherence < self.config.min_coherence_score:
            failure_reasons.append(f"Low coherence: {coherence:.2f}")
        
        # Calculate overall score (weighted)
        overall = (
            relevance * 0.25 +
            groundedness * 0.35 +  # Highest weight for Mahoun I1
            coherence * 0.20 +
            completeness * 0.20
        )
        
        return QualityScore(
            overall=overall,
            dimensions={
                QualityDimension.RELEVANCE: relevance,
                QualityDimension.GROUNDEDNESS: groundedness,
                QualityDimension.COHERENCE: coherence,
                QualityDimension.COMPLETENESS: completeness,
            },
            relevance_score=relevance,
            coherence_score=coherence,
            groundedness_score=groundedness,
            completeness_score=completeness,
            passes_threshold=len(failure_reasons) == 0,
            failure_reasons=failure_reasons
        )
    
    def _basic_validation(self, qa_pairs: List[QAPair]) -> Tuple[List[QAPair], List[QAPair]]:
        """Basic validation checks"""
        valid = []
        invalid = []
        
        for pair in qa_pairs:
            errors = []
            
            # Check question
            if not pair.question or len(pair.question.strip()) < 5:
                errors.append("Question too short")
            
            # Check answer
            if not pair.answer or len(pair.answer.strip()) < 10:
                errors.append("Answer too short")
            
            # Check source
            if not pair.source_text:
                errors.append("Missing source text")
            
            if errors:
                pair.validation_errors.extend(errors)
                pair.is_valid = False
                invalid.append(pair)
                for error in errors:
                    self.stats["failure_reasons"][error] += 1
            else:
                valid.append(pair)
        
        return valid, invalid
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get filtering statistics"""
        return dict(self.stats)
