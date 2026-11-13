"""
Fine-Tuning Module
==================
Complete system for model fine-tuning with feedback integration.

Components:
- feedback_pipeline: Convert user feedback to training data
- training_manager: Manage training jobs
- model_registry: Track and version models
- unsloth_runner: Execute fine-tuning with Unsloth
- qa_generator: Generate Q&A datasets
- quality_filter: Filter and score training examples
- data_augmentation: Augment training data
"""

from mahoun.finetuning.feedback_pipeline import (
    FeedbackPipeline,
    UserFeedback,
    FeedbackType,
    TrainingExample,
    TrainingDataset,
)
from mahoun.finetuning.data_augmentation import DataAugmenter
from mahoun.finetuning.trainer import TrainingManager
from mahoun.finetuning.model_registry import (
    ModelRegistry,
    ModelMetadata,
    get_registry,
)

__all__ = [
    "FeedbackPipeline",
    "UserFeedback",
    "FeedbackType",
    "TrainingExample",
    "TrainingDataset",
    "DataAugmenter",
    "TrainingManager",
    "ModelRegistry",
    "ModelMetadata",
    "get_registry",
]
