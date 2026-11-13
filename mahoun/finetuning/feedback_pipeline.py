"""
Feedback to Fine-Tuning Pipeline
=================================
Complete pipeline for converting user feedback into training data.

Flow:
1. Collect feedback from users
2. Filter and validate quality
3. Convert to training format
4. Create dataset
5. Trigger fine-tuning
6. Evaluate and deploy

This enables continuous improvement through user feedback.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# Data Models
# =============================================================================

class FeedbackType(str, Enum):
    """Types of feedback"""
    RATING = "rating"
    CORRECTION = "correction"
    PREFERENCE = "preference"
    REJECTION = "rejection"


@dataclass
class UserFeedback:
    """User feedback entry"""
    feedback_id: str
    user_id: str
    query: str
    response: str
    feedback_type: FeedbackType
    
    # Rating (1-5)
    rating: Optional[float] = None
    
    # Correction (user provides better response)
    corrected_response: Optional[str] = None
    
    # Preference (A vs B)
    preferred_response: Optional[str] = None
    rejected_response: Optional[str] = None
    
    # Metadata
    timestamp: datetime = field(default_factory=datetime.now)
    context: Dict[str, Any] = field(default_factory=dict)
    
    # Quality metrics
    response_time_ms: Optional[float] = None
    confidence_score: Optional[float] = None


@dataclass
class TrainingExample:
    """Training example for fine-tuning"""
    input_text: str
    target_text: str
    
    # Metadata
    source: str  # feedback, correction, preference
    quality_score: float  # 0-1
    weight: float = 1.0  # Training weight
    
    # Original feedback
    feedback_id: Optional[str] = None
    timestamp: Optional[datetime] = None


@dataclass
class TrainingDataset:
    """Complete training dataset"""
    dataset_id: str
    name: str
    description: str
    
    examples: List[TrainingExample]
    
    # Splits
    train_examples: List[TrainingExample] = field(default_factory=list)
    eval_examples: List[TrainingExample] = field(default_factory=list)
    test_examples: List[TrainingExample] = field(default_factory=list)
    
    # Statistics
    total_examples: int = 0
    avg_quality_score: float = 0.0
    
    created_at: datetime = field(default_factory=datetime.now)


# =============================================================================
# Feedback Pipeline
# =============================================================================

class FeedbackPipeline:
    """
    Pipeline for converting feedback to training data.
    
    Steps:
    1. Collect feedback
    2. Filter by quality
    3. Convert to training format
    4. Create dataset splits
    5. Save dataset
    """
    
    def __init__(
        self,
        storage_dir: str = "./data/feedback",
        min_rating: float = 4.0,
        min_quality_score: float = 0.7,
        train_ratio: float = 0.8,
        eval_ratio: float = 0.1,
        test_ratio: float = 0.1,
    ):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.feedback_file = self.storage_dir / "feedback_log.jsonl"
        
        self.min_rating = min_rating
        self.min_quality_score = min_quality_score
        self.train_ratio = train_ratio
        self.eval_ratio = eval_ratio
        self.test_ratio = test_ratio
        
        self.feedback_store: List[UserFeedback] = self._load_feedback()
    
    def _load_feedback(self) -> List[UserFeedback]:
        """Load feedback from storage"""
        loaded = []
        if self.feedback_file.exists():
            try:
                with open(self.feedback_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            data = json.loads(line)
                            # Handle datetime conversion
                            if 'timestamp' in data and isinstance(data['timestamp'], str):
                                data['timestamp'] = datetime.fromisoformat(data['timestamp'])
                            
                            # Convert string feedback_type back to Enum
                            if 'feedback_type' in data:
                                data['feedback_type'] = FeedbackType(data['feedback_type'])
                                
                            loaded.append(UserFeedback(**data))
            except Exception as e:
                logger.error(f"Error loading feedback: {e}")
        return loaded

    def add_feedback(self, feedback: UserFeedback) -> None:
        """Add feedback to store and persist"""
        self.feedback_store.append(feedback)
        
        # Persist immediately (append)
        try:
            with open(self.feedback_file, 'a', encoding='utf-8') as f:
                # Convert to dict
                data = {
                    k: v.isoformat() if isinstance(v, datetime) else v
                    for k, v in feedback.__dict__.items()
                }
                f.write(json.dumps(data) + '\n')
            logger.info(f"Added and persisted feedback: {feedback.feedback_id}")
        except Exception as e:
            logger.error(f"Error saving feedback: {e}")
    
    def collect_feedback(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        min_rating: Optional[float] = None,
    ) -> List[UserFeedback]:
        """
        Collect feedback from store with filters.
        
        Args:
            start_date: Start date for feedback
            end_date: End date for feedback
            min_rating: Minimum rating threshold
        
        Returns:
            List of filtered feedback
        """
        filtered = self.feedback_store
        
        # Date filter
        if start_date:
            filtered = [f for f in filtered if f.timestamp >= start_date]
        if end_date:
            filtered = [f for f in filtered if f.timestamp <= end_date]
        
        # Rating filter
        min_r = min_rating or self.min_rating
        filtered = [
            f for f in filtered
            if (f.feedback_type != FeedbackType.RATING) or 
               (f.rating is None or f.rating >= min_r)
        ]
        
        logger.info(f"Collected {len(filtered)} feedback entries")
        return filtered
    
    def convert_to_training_examples(
        self,
        feedback_list: List[UserFeedback]
    ) -> List[TrainingExample]:
        """
        Convert feedback to training examples.
        
        Different strategies for different feedback types:
        - Rating: Use high-rated responses as positive examples
        - Correction: Use corrected response as target
        - Preference: Use preferred response as target
        - Rejection: Use as negative example (optional)
        """
        examples = []
        
        for feedback in feedback_list:
            # Calculate quality score
            quality_score = self._calculate_quality_score(feedback)
            
            if quality_score < self.min_quality_score:
                continue
            
            # Convert based on type
            if feedback.feedback_type == FeedbackType.RATING:
                if feedback.rating and feedback.rating >= self.min_rating:
                    example = TrainingExample(
                        input_text=feedback.query,
                        target_text=feedback.response,
                        source="rating",
                        quality_score=quality_score,
                        weight=feedback.rating / 5.0,  # Normalize to 0-1
                        feedback_id=feedback.feedback_id,
                        timestamp=feedback.timestamp
                    )
                    examples.append(example)
            
            elif feedback.feedback_type == FeedbackType.CORRECTION:
                if feedback.corrected_response:
                    example = TrainingExample(
                        input_text=feedback.query,
                        target_text=feedback.corrected_response,
                        source="correction",
                        quality_score=quality_score,
                        weight=1.5,  # Higher weight for corrections
                        feedback_id=feedback.feedback_id,
                        timestamp=feedback.timestamp
                    )
                    examples.append(example)
            
            elif feedback.feedback_type == FeedbackType.PREFERENCE:
                if feedback.preferred_response:
                    example = TrainingExample(
                        input_text=feedback.query,
                        target_text=feedback.preferred_response,
                        source="preference",
                        quality_score=quality_score,
                        weight=1.2,
                        feedback_id=feedback.feedback_id,
                        timestamp=feedback.timestamp
                    )
                    examples.append(example)
        
        logger.info(f"Converted {len(examples)} training examples")
        return examples
    
    def _calculate_quality_score(self, feedback: UserFeedback) -> float:
        """
        Calculate quality score for feedback.
        
        Factors:
        - Rating (if available) - weighted heavily
        - Response time (faster = better)
        - Confidence score
        - Feedback type (corrections are high quality)
        
        Score range: 0.0 to 1.0
        Low-quality feedback (rating < 3, low confidence) should score < 0.5
        High-quality feedback (rating >= 4, high confidence) should score > 0.7
        
        IMPORTANT: Corrections and Preferences are inherently high-quality
        because the user took time to provide better alternatives.
        """
        score = 0.0  # Start from zero for strict scoring
        
        # Rating component (0.0 - 0.4) - most important factor
        if feedback.rating is not None:
            # rating 1 → 0.08, rating 2 → 0.16, rating 3 → 0.24, rating 4 → 0.32, rating 5 → 0.40
            score += (feedback.rating / 5.0) * 0.4
        else:
            # No rating - give neutral base for RATING type, higher for others
            if feedback.feedback_type in [FeedbackType.CORRECTION, FeedbackType.PREFERENCE]:
                # Corrections/Preferences without rating are still valuable
                score += 0.3
            else:
                score += 0.2
        
        # Response time component (0.0 - 0.2)
        if feedback.response_time_ms is not None:
            # Optimal range: 500-2000ms
            if 500 <= feedback.response_time_ms <= 2000:
                score += 0.2  # Perfect response time
            elif feedback.response_time_ms < 500:
                score += 0.15  # Too fast might be cached/simple
            elif feedback.response_time_ms <= 5000:
                # Gradual decrease from 2000 to 5000ms
                score += 0.1 * (1 - (feedback.response_time_ms - 2000) / 3000)
            else:
                # Very slow (> 5000ms) = minimal score
                score += 0.02
        else:
            # No response time = neutral
            score += 0.1
        
        # Confidence component (0.0 - 0.2)
        if feedback.confidence_score is not None:
            score += feedback.confidence_score * 0.2
        else:
            # No confidence = neutral
            score += 0.1
        
        # Type bonus (0.0 - 0.2)
        if feedback.feedback_type == FeedbackType.CORRECTION:
            score += 0.2  # Corrections are high quality - user provided better answer
        elif feedback.feedback_type == FeedbackType.PREFERENCE:
            score += 0.15  # Preferences are good - user compared options
        elif feedback.feedback_type == FeedbackType.RATING:
            score += 0.1  # Ratings are baseline
        # REJECTION gets no bonus
        
        # Special case: Corrections are ground truth (Gold Data)
        # If a user takes time to correct an answer, that text is highly valuable
        # regardless of the original rating (which was likely low).
        if feedback.feedback_type == FeedbackType.CORRECTION:
            if feedback.corrected_response and len(feedback.corrected_response) > 5:
                return 0.95 # Almost perfect score for user corrections
        
        return min(max(score, 0.0), 1.0)  # Clamp to [0, 1]
    
    def create_dataset(
        self,
        examples: List[TrainingExample],
        dataset_name: str,
        description: str = "",
    ) -> TrainingDataset:
        """
        Create training dataset with splits.
        
        Args:
            examples: List of training examples
            dataset_name: Name for the dataset
            description: Description of the dataset
        
        Returns:
            TrainingDataset with train/eval/test splits
        """
        # Shuffle examples
        np.random.shuffle(examples)
        
        # Calculate split indices
        n = len(examples)
        train_end = int(n * self.train_ratio)
        eval_end = train_end + int(n * self.eval_ratio)
        
        # Create splits
        train_examples = examples[:train_end]
        eval_examples = examples[train_end:eval_end]
        test_examples = examples[eval_end:]
        
        # Calculate statistics
        avg_quality = np.mean([e.quality_score for e in examples])
        
        dataset = TrainingDataset(
            dataset_id=f"dataset_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            name=dataset_name,
            description=description,
            examples=examples,
            train_examples=train_examples,
            eval_examples=eval_examples,
            test_examples=test_examples,
            total_examples=len(examples),
            avg_quality_score=float(avg_quality),
        )
        
        logger.info(
            f"Created dataset: {dataset.dataset_id} "
            f"(train={len(train_examples)}, "
            f"eval={len(eval_examples)}, "
            f"test={len(test_examples)})"
        )
        
        return dataset
    
    def save_dataset(
        self,
        dataset: TrainingDataset,
        output_dir: Path,
        format: str = "jsonl"
    ) -> Dict[str, Path]:
        """
        Save dataset to disk.
        
        Args:
            dataset: Dataset to save
            output_dir: Output directory
            format: Format (jsonl, json, csv)
        
        Returns:
            Dict of split names to file paths
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        paths = {}
        
        # Save each split
        for split_name, examples in [
            ("train", dataset.train_examples),
            ("eval", dataset.eval_examples),
            ("test", dataset.test_examples),
        ]:
            if format == "jsonl":
                path = output_dir / f"{split_name}.jsonl"
                with open(path, 'w') as f:
                    for example in examples:
                        data = {
                            "input": example.input_text,
                            "target": example.target_text,
                            "source": example.source,
                            "quality_score": example.quality_score,
                            "weight": example.weight,
                        }
                        f.write(json.dumps(data) + '\n')
            
            elif format == "json":
                path = output_dir / f"{split_name}.json"
                data = [
                    {
                        "input": e.input_text,
                        "target": e.target_text,
                        "source": e.source,
                        "quality_score": e.quality_score,
                        "weight": e.weight,
                    }
                    for e in examples
                ]
                with open(path, 'w') as f:
                    json.dump(data, f, indent=2)
            
            paths[split_name] = path
            logger.info(f"Saved {split_name} split to {path}")
        
        # Save metadata
        metadata_path = output_dir / "metadata.json"
        metadata = {
            "dataset_id": dataset.dataset_id,
            "name": dataset.name,
            "description": dataset.description,
            "total_examples": dataset.total_examples,
            "avg_quality_score": dataset.avg_quality_score,
            "splits": {
                "train": len(dataset.train_examples),
                "eval": len(dataset.eval_examples),
                "test": len(dataset.test_examples),
            },
            "created_at": dataset.created_at.isoformat(),
        }
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        paths["metadata"] = metadata_path
        
        return paths
    
    def run_pipeline(
        self,
        dataset_name: str,
        output_dir: Path,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Tuple[TrainingDataset, Dict[str, Path]]:
        """
        Run complete pipeline: collect → convert → create → save.
        
        Args:
            dataset_name: Name for the dataset
            output_dir: Output directory
            start_date: Start date for feedback
            end_date: End date for feedback
        
        Returns:
            Tuple of (dataset, file_paths)
        """
        logger.info("Starting feedback pipeline")
        
        # Step 1: Collect feedback
        feedback_list = self.collect_feedback(
            start_date=start_date,
            end_date=end_date
        )
        
        if not feedback_list:
            raise ValueError("No feedback collected")
        
        # Step 2: Convert to training examples
        examples = self.convert_to_training_examples(feedback_list)
        
        if not examples:
            raise ValueError("No valid training examples created")
        
        # Step 3: Create dataset
        dataset = self.create_dataset(
            examples=examples,
            dataset_name=dataset_name,
            description=f"Dataset from {len(feedback_list)} feedback entries"
        )
        
        # Step 4: Save dataset
        paths = self.save_dataset(dataset, output_dir)
        
        logger.info(
            f"Pipeline complete: {dataset.total_examples} examples, "
            f"avg quality: {dataset.avg_quality_score:.3f}"
        )
        
        return dataset, paths


# =============================================================================
# Example Usage
# =============================================================================

def example_usage():
    """Example of using the feedback pipeline"""
    
    # Create pipeline
    pipeline = FeedbackPipeline(
        min_rating=4.0,
        min_quality_score=0.7
    )
    
    # Add some example feedback
    feedback1 = UserFeedback(
        feedback_id="fb_001",
        user_id="user_123",
        query="What is the legal definition of force majeure?",
        response="Force majeure is an unforeseeable circumstance...",
        feedback_type=FeedbackType.RATING,
        rating=5.0,
        response_time_ms=1200,
        confidence_score=0.95
    )
    pipeline.add_feedback(feedback1)
    
    feedback2 = UserFeedback(
        feedback_id="fb_002",
        user_id="user_456",
        query="Explain contract breach remedies",
        response="Remedies include damages...",
        feedback_type=FeedbackType.CORRECTION,
        corrected_response="Remedies for contract breach include compensatory damages, specific performance, and rescission...",
        rating=3.0,
        response_time_ms=1500,
        confidence_score=0.85
    )
    pipeline.add_feedback(feedback2)
    
    # Run pipeline
    dataset, paths = pipeline.run_pipeline(
        dataset_name="legal_qa_feedback_jan2024",
        output_dir=Path("./datasets/feedback")
    )
    
    print(f"Created dataset: {dataset.dataset_id}")
    print(f"Total examples: {dataset.total_examples}")
    print(f"Files: {paths}")


if __name__ == "__main__":
    example_usage()
