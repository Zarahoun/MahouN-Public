"""
Model Registry
==============
Lightweight registry for tracking fine-tuned models with metadata.

Features:
- Model versioning and metadata tracking
- GGUF path management
- JSON-based persistence
- Query by domain, metrics, or job_id
- Thread-safe operations
- Integration with TrainingManager
"""

import json
import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class ModelMetadata:
    """
    Metadata for a registered fine-tuned model.
    
    Attributes:
        job_id: Unique training job identifier
        base_model: Base model name (e.g., "unsloth/llama-3-8b-bnb-4bit")
        dataset_path: Path to training dataset
        output_dir: Directory containing model files
        gguf_paths: Dictionary of quantization method -> GGUF file path
        metrics: Training metrics (loss, perplexity, etc.)
        config: Training configuration used
        domain: Domain/category (legal, medical, etc.)
        created_at: Timestamp of model creation
        status: Model status (training, completed, failed)
        tags: Custom tags for filtering
    """
    job_id: str
    base_model: str
    dataset_path: str
    output_dir: str
    gguf_paths: Dict[str, str] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)
    domain: str = "general"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: str = "training"
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelMetadata":
        """Create from dictionary"""
        return cls(**data)


class ModelRegistry:
    """
    Registry for tracking fine-tuned models.
    
    This is a lightweight, production-ready registry that:
    - Stores model metadata in JSON
    - Provides fast queries by job_id, domain, or metrics
    - Thread-safe for concurrent access
    - Integrates seamlessly with TrainingManager
    
    Usage:
        registry = ModelRegistry()
        
        # Register a model
        metadata = ModelMetadata(
            job_id="job_20250213_120000",
            base_model="unsloth/llama-3-8b-bnb-4bit",
            dataset_path="./datasets/legal_qa",
            output_dir="./models/finetuned/job_20250213_120000",
            gguf_paths={
                "q4_k_m": "./models/.../gguf_q4_k_m/model.gguf",
                "q5_k_m": "./models/.../gguf_q5_k_m/model.gguf",
            },
            metrics={"loss": 0.23, "perplexity": 1.26},
            domain="legal"
        )
        registry.register(metadata)
        
        # Query models
        best_legal = registry.get_best_model(domain="legal", metric="loss")
        all_models = registry.list_models()
        model_info = registry.get_model(job_id="job_20250213_120000")
    """
    
    def __init__(self, registry_path: str = "./models/registry.json"):
        """
        Initialize model registry.
        
        Args:
            registry_path: Path to JSON file for persistence
        """
        self.registry_path = Path(registry_path)
        self._models: Dict[str, ModelMetadata] = {}
        self._lock = threading.RLock()
        
        # Create directory if needed
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing registry
        self._load()
        
        logger.info(f"ModelRegistry initialized: {len(self._models)} models loaded")
    
    def register(self, metadata: ModelMetadata) -> None:
        """
        Register a new model.
        
        Args:
            metadata: Model metadata to register
            
        Raises:
            ValueError: If job_id already exists
        """
        with self._lock:
            if metadata.job_id in self._models:
                logger.warning(f"Model {metadata.job_id} already registered, updating...")
            
            self._models[metadata.job_id] = metadata
            self._save()
            
            logger.info(f"✅ Model registered: {metadata.job_id} ({metadata.domain})")
    
    def update_status(self, job_id: str, status: str) -> None:
        """
        Update model status.
        
        Args:
            job_id: Job identifier
            status: New status (training, completed, failed)
        """
        with self._lock:
            if job_id not in self._models:
                raise ValueError(f"Model {job_id} not found")
            
            self._models[job_id].status = status
            self._save()
            
            logger.info(f"Model {job_id} status updated: {status}")
    
    def update_metrics(self, job_id: str, metrics: Dict[str, float]) -> None:
        """
        Update model metrics.
        
        Args:
            job_id: Job identifier
            metrics: Metrics to update/add
        """
        with self._lock:
            if job_id not in self._models:
                raise ValueError(f"Model {job_id} not found")
            
            self._models[job_id].metrics.update(metrics)
            self._save()
            
            logger.info(f"Model {job_id} metrics updated")
    
    def add_gguf_path(self, job_id: str, quantization: str, path: str) -> None:
        """
        Add GGUF export path.
        
        Args:
            job_id: Job identifier
            quantization: Quantization method (q4_k_m, q5_k_m, f16)
            path: Path to GGUF file
        """
        with self._lock:
            if job_id not in self._models:
                raise ValueError(f"Model {job_id} not found")
            
            self._models[job_id].gguf_paths[quantization] = path
            self._save()
            
            logger.info(f"GGUF path added for {job_id}: {quantization}")
    
    def get_model(self, job_id: str) -> Optional[ModelMetadata]:
        """
        Get model metadata by job_id.
        
        Args:
            job_id: Job identifier
            
        Returns:
            Model metadata or None if not found
        """
        with self._lock:
            return self._models.get(job_id)
    
    def list_models(
        self,
        domain: Optional[str] = None,
        status: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> List[ModelMetadata]:
        """
        List all models with optional filtering.
        
        Args:
            domain: Filter by domain
            status: Filter by status
            tags: Filter by tags (model must have all tags)
            
        Returns:
            List of model metadata
        """
        with self._lock:
            models = list(self._models.values())
            
            # Apply filters
            if domain:
                models = [m for m in models if m.domain == domain]
            
            if status:
                models = [m for m in models if m.status == status]
            
            if tags:
                models = [
                    m for m in models
                    if all(tag in m.tags for tag in tags)
                ]
            
            # Sort by creation time (newest first)
            models.sort(key=lambda m: m.created_at, reverse=True)
            
            return models
    
    def get_best_model(
        self,
        metric: str = "loss",
        domain: Optional[str] = None,
        minimize: bool = True
    ) -> Optional[ModelMetadata]:
        """
        Get best model based on a metric.
        
        Args:
            metric: Metric name to optimize (loss, perplexity, accuracy, etc.)
            domain: Filter by domain
            minimize: If True, lower is better; if False, higher is better
            
        Returns:
            Best model metadata or None if no models found
        """
        models = self.list_models(domain=domain, status="completed")
        
        # Filter models that have the metric
        models_with_metric = [m for m in models if metric in m.metrics]
        
        if not models_with_metric:
            return None
        
        # Find best
        if minimize:
            best = min(models_with_metric, key=lambda m: m.metrics[metric])
        else:
            best = max(models_with_metric, key=lambda m: m.metrics[metric])
        
        return best
    
    def delete_model(self, job_id: str) -> bool:
        """
        Delete model from registry.
        
        Note: This only removes from registry, not from disk.
        
        Args:
            job_id: Job identifier
            
        Returns:
            True if deleted, False if not found
        """
        with self._lock:
            if job_id in self._models:
                del self._models[job_id]
                self._save()
                logger.info(f"Model {job_id} deleted from registry")
                return True
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get registry statistics.
        
        Returns:
            Dictionary with statistics
        """
        with self._lock:
            models = list(self._models.values())
            
            # Count by domain
            domains = {}
            for model in models:
                domains[model.domain] = domains.get(model.domain, 0) + 1
            
            # Count by status
            statuses = {}
            for model in models:
                statuses[model.status] = statuses.get(model.status, 0) + 1
            
            return {
                "total_models": len(models),
                "by_domain": domains,
                "by_status": statuses,
                "registry_path": str(self.registry_path),
            }
    
    def _load(self) -> None:
        """Load registry from disk"""
        if not self.registry_path.exists():
            logger.info("No existing registry found, starting fresh")
            return
        
        try:
            with open(self.registry_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self._models = {
                job_id: ModelMetadata.from_dict(model_data)
                for job_id, model_data in data.items()
            }
            
            logger.info(f"Loaded {len(self._models)} models from registry")
            
        except Exception as e:
            logger.error(f"Failed to load registry: {e}")
            self._models = {}
    
    def _save(self) -> None:
        """Save registry to disk"""
        try:
            data = {
                job_id: metadata.to_dict()
                for job_id, metadata in self._models.items()
            }
            
            # Write atomically
            temp_path = self.registry_path.with_suffix('.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            temp_path.replace(self.registry_path)
            
        except Exception as e:
            logger.error(f"Failed to save registry: {e}")
    
    def export_summary(self, output_path: str) -> None:
        """
        Export human-readable summary.
        
        Args:
            output_path: Path to output file
        """
        with self._lock:
            models = self.list_models()
            
            lines = [
                "# Fine-Tuned Models Registry",
                f"Generated: {datetime.now().isoformat()}",
                f"Total Models: {len(models)}",
                "",
            ]
            
            # Group by domain
            by_domain: Dict[str, List[ModelMetadata]] = {}
            for model in models:
                if model.domain not in by_domain:
                    by_domain[model.domain] = []
                by_domain[model.domain].append(model)
            
            for domain, domain_models in sorted(by_domain.items()):
                lines.append(f"## Domain: {domain}")
                lines.append(f"Models: {len(domain_models)}")
                lines.append("")
                
                for model in domain_models:
                    lines.append(f"### {model.job_id}")
                    lines.append(f"- Base Model: {model.base_model}")
                    lines.append(f"- Status: {model.status}")
                    lines.append(f"- Created: {model.created_at}")
                    
                    if model.metrics:
                        lines.append(f"- Metrics: {model.metrics}")
                    
                    if model.gguf_paths:
                        lines.append(f"- GGUF Exports: {list(model.gguf_paths.keys())}")
                    
                    lines.append("")
            
            Path(output_path).write_text("\n".join(lines), encoding='utf-8')
            logger.info(f"Registry summary exported to {output_path}")


# Singleton instance for global access
_global_registry: Optional[ModelRegistry] = None


def get_registry(registry_path: str = "./models/registry.json") -> ModelRegistry:
    """
    Get global registry instance (singleton pattern).
    
    Args:
        registry_path: Path to registry file
        
    Returns:
        ModelRegistry instance
    """
    global _global_registry
    
    if _global_registry is None:
        _global_registry = ModelRegistry(registry_path)
    
    return _global_registry
