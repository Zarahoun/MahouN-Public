"""
Training Manager
================
Orchestrates the fine-tuning training process.

Features:
- Dataset preparation
- Training job management
- Model evaluation interface
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

from .config import DocumentToTrainingConfig
from .feedback_pipeline import FeedbackPipeline
from .data_augmentation import DataAugmenter
from .model_registry import ModelRegistry, ModelMetadata

logger = logging.getLogger(__name__)

class TrainingManager:
    """
    Manages the end-to-end training process.
    """
    
    def __init__(
        self, 
        config: Optional[DocumentToTrainingConfig] = None,
        registry: Optional[ModelRegistry] = None
    ):
        self.config = config or DocumentToTrainingConfig()
        self.feedback_pipeline = FeedbackPipeline() # Initialize with defaults
        self.augmenter = DataAugmenter(config=self.config.augmentation)
        self.registry = registry or ModelRegistry()
        
        # State tracking
        self.current_job_id: Optional[str] = None
        self.job_history: List[Dict[str, Any]] = []
        
        logger.info("TrainingManager initialized")

    def prepare_dataset_from_feedback(
        self, 
        dataset_name: str,
        output_dir: str = "./datasets/training"
    ) -> str:
        """
        Prepare a dataset for training from collected feedback.
        
        1. Collect feedback
        2. Convert to examples
        3. Augment data
        4. Save to disk
        
        Returns:
            Path to the saved dataset directory
        """
        logger.info(f"Preparing dataset: {dataset_name}")
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 1. Collect & Convert (using pipeline)
        # Note: In a real scenario, we might want more control here, but we reuse the pipeline logic
        feedback_list = self.feedback_pipeline.collect_feedback()
        examples = self.feedback_pipeline.convert_to_training_examples(feedback_list)
        
        logger.info(f"Collected {len(examples)} base examples")
        
        # 2. Augment
        augmented_examples = []
        if self.config.augmentation.enabled:
            for ex in examples:
                # Add original
                augmented_examples.append(ex)
                
                # Generate variations for input text
                variations = self.augmenter.augment(ex.input_text)
                for var_text in variations:
                    # Create new example with augmented input, same target
                    # We might want to lower the quality score slightly for augmented data
                    new_ex = type(ex)(
                        input_text=var_text,
                        target_text=ex.target_text,
                        source=f"{ex.source}_aug",
                        quality_score=ex.quality_score * 0.95,
                        weight=ex.weight * 0.8,
                        feedback_id=ex.feedback_id,
                        timestamp=datetime.now()
                    )
                    augmented_examples.append(new_ex)
            
            logger.info(f"Augmentation expanded dataset to {len(augmented_examples)} examples")
        else:
            augmented_examples = examples
            
        # 3. Create & Save
        dataset = self.feedback_pipeline.create_dataset(
            examples=augmented_examples, 
            dataset_name=dataset_name,
            description="Augmented dataset from feedback"
        )
        
        self.feedback_pipeline.save_dataset(dataset, output_path, format=self.config.output_format)
        
        return str(output_path)

    async def start_training_job(
        self, 
        dataset_path: str, 
        base_model_name: Optional[str] = None,
        domain: str = "general",
        tags: Optional[List[str]] = None
    ) -> str:
        """
        Start a fine-tuning job.
        
        Args:
            dataset_path: Path to prepared dataset
            base_model_name: Base model override (optional)
            domain: Domain/category for the model (legal, medical, etc.)
            tags: Custom tags for filtering
            
        Returns:
            Job ID
        """
        job_id = f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.current_job_id = job_id
        
        # Override config if needed
        if base_model_name:
            self.config.training.base_model = base_model_name
            
        logger.info(f"Starting training job {job_id} on {self.config.training.base_model}")
        
        output_dir = f"./models/finetuned/{job_id}"
        
        # Register model in registry (initial state)
        metadata = ModelMetadata(
            job_id=job_id,
            base_model=self.config.training.base_model,
            dataset_path=dataset_path,
            output_dir=output_dir,
            config=self.config.dict(),
            domain=domain,
            status="training",
            tags=tags or []
        )
        self.registry.register(metadata)
        
        # Record job start (legacy tracking)
        job_info = {
            "job_id": job_id,
            "status": "running",
            "base_model": self.config.training.base_model,
            "dataset_path": dataset_path,
            "output_dir": output_dir,
            "start_time": datetime.now().isoformat(),
            "config": self.config.dict()
        }
        self.job_history.append(job_info)
        
        # Try to run real training
        try:
            # We import here to avoid dependency hard-crash
            from .unsloth_runner import UnslothRunner
            
            # TODO: Move this to a background task/worker in production (Celery/RQ)
            # For now, we run it directly but wrap in try-except to catch immediate errors
            # Note: This blocks the async loop if run directly. In a real async app, use run_in_executor.
            
            logger.info("Initializing Unsloth Runner...")
            runner = UnslothRunner(self.config.training)
            
            # Since UnslothRunner.train is synchronous (blocking), we really should offload it.
            # But complicating with ThreadPoolExecutor for this demo might be overkill.
            # Let's just run it. If it fails due to missing deps, we switch to mock.
            
            # Assume train_dataset.jsonl is inside the dataset directory if a dir passed
            # Or use the path directly if it's a file
            train_file = Path(dataset_path) 
            if train_file.is_dir():
                train_file = train_file / "train.jsonl"
            
            if not train_file.exists():
                raise FileNotFoundError(f"Training file not found: {train_file}")

            # Execute Training
            logger.info(">>> STARTING REAL TRAINING <<<")
            trainer_stats = runner.train(str(train_file), output_dir)
            
            # Update registry with completion
            self.registry.update_status(job_id, "completed")
            
            # Extract metrics from trainer_stats if available
            if trainer_stats and hasattr(trainer_stats, 'metrics'):
                metrics = {
                    "final_loss": trainer_stats.metrics.get("train_loss", 0.0),
                }
                self.registry.update_metrics(job_id, metrics)
            
            # Register GGUF paths
            gguf_base = Path(output_dir)
            for quant in ["q4_k_m", "q5_k_m", "f16"]:
                gguf_dir = gguf_base / f"gguf_{quant}"
                if gguf_dir.exists():
                    # Find .gguf file
                    gguf_files = list(gguf_dir.glob("*.gguf"))
                    if gguf_files:
                        self.registry.add_gguf_path(job_id, quant, str(gguf_files[0]))
            
            job_info["status"] = "completed"
            job_info["end_time"] = datetime.now().isoformat()
            logger.info(f"Job {job_id} completed successfully.")
            
        except ImportError:
            logger.warning("Unsloth/Torch not installed. Falling back to MOCK training.")
            self.registry.update_status(job_id, "mock_completed")
            job_info["status"] = "mock_completed"
            job_info["note"] = "Simulation only - Unsloth libraries missing"
            
        except Exception as e:
            logger.error(f"Training failed: {e}")
            self.registry.update_status(job_id, "failed")
            job_info["status"] = "failed"
            job_info["error"] = str(e)
            job_info["end_time"] = datetime.now().isoformat()
            
        return job_id

    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get status of a training job.
        
        Returns metadata from registry if available, otherwise from job_history.
        """
        # Try registry first
        metadata = self.registry.get_model(job_id)
        if metadata:
            return metadata.to_dict()
        
        # Fallback to legacy job_history
        for job in self.job_history:
            if job["job_id"] == job_id:
                return job
        
        return {"status": "unknown"}
    
    def list_models(
        self,
        domain: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List all registered models.
        
        Args:
            domain: Filter by domain
            status: Filter by status
            
        Returns:
            List of model metadata dictionaries
        """
        models = self.registry.list_models(domain=domain, status=status)
        return [m.to_dict() for m in models]
    
    def get_best_model(
        self,
        metric: str = "final_loss",
        domain: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get best model based on a metric.
        
        Args:
            metric: Metric to optimize (final_loss, perplexity, etc.)
            domain: Filter by domain
            
        Returns:
            Best model metadata or None
        """
        best = self.registry.get_best_model(metric=metric, domain=domain)
        return best.to_dict() if best else None
