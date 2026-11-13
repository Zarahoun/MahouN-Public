"""
Fine-Tuning Configuration
=========================
Centralized configuration for the entire fine-tuning pipeline.

Includes settings for:
- Q&A Generation
- Quality Filtering
- Data Augmentation
- Training Parameters
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class QAGenerationStrategy(str, Enum):
    """Strategies for generating Q&A pairs"""
    LLM_BASED = "llm_based"           # Use LLM to generate Q&A
    TEMPLATE_BASED = "template_based"  # Use domain templates
    EXTRACTIVE = "extractive"          # Extract from text structure
    HYBRID = "hybrid"                  # Combine multiple strategies


class AugmentationStrategy(str, Enum):
    """Data augmentation strategies"""
    PARAPHRASE = "paraphrase"
    BACK_TRANSLATION = "back_translation"
    SYNONYM_REPLACEMENT = "synonym_replacement"
    ENTITY_SWAP = "entity_swap"
    NOISE_INJECTION = "noise_injection"


class DomainType(str, Enum):
    """Supported domain types"""
    LEGAL = "legal"
    HEALTHCARE = "healthcare"
    FINANCIAL = "financial"
    GENERAL = "general"


class QAGeneratorConfig(BaseModel):
    """Configuration for Q&A Generator"""
    
    strategy: QAGenerationStrategy = Field(
        default=QAGenerationStrategy.HYBRID,
        description="Q&A generation strategy"
    )
    domain: DomainType = Field(
        default=DomainType.LEGAL,
        description="Domain for specialized templates"
    )
    
    # LLM settings
    llm_model: str = Field(
        default="llama3.2",
        description="LLM model for generation"
    )
    llm_temperature: float = Field(
        default=0.7,
        ge=0.0, le=2.0,
        description="LLM temperature"
    )
    llm_max_tokens: int = Field(
        default=512,
        ge=64, le=4096,
        description="Max tokens for LLM response"
    )
    
    # Generation settings
    min_qa_pairs_per_chunk: int = Field(
        default=2,
        ge=1, le=10,
        description="Minimum Q&A pairs per chunk"
    )
    max_qa_pairs_per_chunk: int = Field(
        default=5,
        ge=1, le=20,
        description="Maximum Q&A pairs per chunk"
    )
    
    # Quality thresholds
    min_question_length: int = Field(
        default=10,
        ge=5,
        description="Minimum question length in chars"
    )
    min_answer_length: int = Field(
        default=20,
        ge=10,
        description="Minimum answer length in chars"
    )
    max_answer_length: int = Field(
        default=1000,
        le=5000,
        description="Maximum answer length in chars"
    )


class QualityFilterConfig(BaseModel):
    """Configuration for Quality Filter"""
    
    # Score thresholds
    min_relevance_score: float = Field(
        default=0.7,
        ge=0.0, le=1.0,
        description="Minimum relevance score"
    )
    min_coherence_score: float = Field(
        default=0.6,
        ge=0.0, le=1.0,
        description="Minimum coherence score"
    )
    min_groundedness_score: float = Field(
        default=0.8,
        ge=0.0, le=1.0,
        description="Minimum groundedness score (evidence-linked)"
    )
    
    # Deduplication
    enable_deduplication: bool = Field(
        default=True,
        description="Enable semantic deduplication"
    )
    similarity_threshold: float = Field(
        default=0.85,
        ge=0.5, le=1.0,
        description="Similarity threshold for deduplication"
    )
    
    # Content filters
    filter_short_answers: bool = Field(default=True)
    filter_repetitive: bool = Field(default=True)
    filter_low_information: bool = Field(default=True)


class AugmentationConfig(BaseModel):
    """Configuration for Data Augmentation"""
    
    enabled: bool = Field(
        default=True,
        description="Enable data augmentation"
    )
    strategies: List[AugmentationStrategy] = Field(
        default_factory=lambda: [
            AugmentationStrategy.PARAPHRASE,
            AugmentationStrategy.SYNONYM_REPLACEMENT
        ],
        description="Augmentation strategies to use"
    )
    
    # Augmentation ratio
    augmentation_factor: float = Field(
        default=2.0,
        ge=1.0, le=10.0,
        description="Factor to multiply dataset size"
    )
    
    # Per-strategy settings
    paraphrase_variations: int = Field(
        default=2,
        ge=1, le=5,
        description="Number of paraphrase variations"
    )
    synonym_replacement_ratio: float = Field(
        default=0.15,
        ge=0.0, le=0.5,
        description="Ratio of words to replace with synonyms"
    )


class TrainingConfig(BaseModel):
    """Configuration for Model Training (Unsloth/HuggingFace)"""
    
    base_model: str = Field(
        default="unsloth/llama-3-8b-bnb-4bit",
        description="Base model to fine-tune"
    )
    max_seq_length: int = Field(default=2048, description="Max sequence length")
    load_in_4bit: bool = Field(default=True, description="Use 4-bit quantization")
    
    # LoRA parameters
    lora_r: int = Field(default=16, description="LoRA rank")
    lora_alpha: int = Field(default=16, description="LoRA alpha")
    lora_dropout: float = Field(default=0, description="LoRA dropout")
    
    # Training Loop parameters
    batch_size: int = Field(default=2, description="Batch size per device")
    gradient_accumulation_steps: int = Field(default=4, description="Gradient accumulation steps")
    learning_rate: float = Field(default=2e-4, description="Learning rate")
    num_train_epochs: int = Field(default=1, description="Number of training epochs")
    max_steps: int = Field(default=-1, description="Max steps (overrides epochs if > 0)")
    warmup_steps: int = Field(default=5, description="Warmup steps")
    logging_steps: int = Field(default=1, description="Logging steps")
    optimizer: str = Field(default="adamw_8bit", description="Optimizer name")
    seed: int = Field(default=3407, description="Random seed")


class DocumentToTrainingConfig(BaseModel):
    """Master configuration for Document-to-Training Pipeline"""
    
    # Sub-configs
    qa_generator: QAGeneratorConfig = Field(
        default_factory=QAGeneratorConfig
    )
    quality_filter: QualityFilterConfig = Field(
        default_factory=QualityFilterConfig
    )
    augmentation: AugmentationConfig = Field(
        default_factory=AugmentationConfig
    )
    training: TrainingConfig = Field(
        default_factory=TrainingConfig
    )
    
    # Pipeline settings
    chunk_size: int = Field(
        default=512,
        ge=128, le=2048,
        description="Chunk size for document splitting"
    )
    chunk_overlap: int = Field(
        default=50,
        ge=0, le=256,
        description="Overlap between chunks"
    )
    
    # Output settings
    output_format: str = Field(
        default="jsonl",
        pattern="^(jsonl|json|csv)$",
        description="Output format for training data"
    )
    train_split: float = Field(
        default=0.8,
        ge=0.5, le=0.95,
        description="Training split ratio"
    )
    eval_split: float = Field(
        default=0.1,
        ge=0.05, le=0.3,
        description="Evaluation split ratio"
    )
    test_split: float = Field(
        default=0.1,
        ge=0.0, le=0.2,
        description="Test split ratio"
    )
    
    # Processing settings
    batch_size: int = Field(
        default=10,
        ge=1, le=100,
        description="Batch size for processing"
    )
    max_workers: int = Field(
        default=4,
        ge=1, le=16,
        description="Max parallel workers"
    )
    
    # Caching
    enable_cache: bool = Field(
        default=True,
        description="Enable caching of intermediate results"
    )
    cache_dir: str = Field(
        default="./cache/finetuning",
        description="Cache directory"
    )


# Default configurations for different domains
DOMAIN_CONFIGS: Dict[DomainType, Dict[str, Any]] = {
    DomainType.LEGAL: {
        "qa_generator": {
            "domain": "legal",
            "min_qa_pairs_per_chunk": 3,
            "max_qa_pairs_per_chunk": 6,
        },
        "quality_filter": {
            "min_groundedness_score": 0.85,  # Higher for legal
        }
    },
    DomainType.HEALTHCARE: {
        "qa_generator": {
            "domain": "healthcare",
            "min_qa_pairs_per_chunk": 2,
            "max_qa_pairs_per_chunk": 4,
        },
        "quality_filter": {
            "min_groundedness_score": 0.9,  # Highest for healthcare
        }
    },
    DomainType.FINANCIAL: {
        "qa_generator": {
            "domain": "financial",
            "min_qa_pairs_per_chunk": 2,
            "max_qa_pairs_per_chunk": 5,
        },
        "quality_filter": {
            "min_groundedness_score": 0.85,
        }
    },
    DomainType.GENERAL: {
        "qa_generator": {
            "domain": "general",
            "min_qa_pairs_per_chunk": 2,
            "max_qa_pairs_per_chunk": 4,
        },
        "quality_filter": {
            "min_groundedness_score": 0.7,
        }
    },
}


def get_domain_config(domain: DomainType) -> DocumentToTrainingConfig:
    """Get pre-configured settings for a specific domain"""
    base_config = DocumentToTrainingConfig()
    domain_overrides = DOMAIN_CONFIGS.get(domain, {})
    
    # Apply overrides
    if "qa_generator" in domain_overrides:
        for key, value in domain_overrides["qa_generator"].items():
            setattr(base_config.qa_generator, key, value)
    
    if "quality_filter" in domain_overrides:
        for key, value in domain_overrides["quality_filter"].items():
            setattr(base_config.quality_filter, key, value)
    
    return base_config
