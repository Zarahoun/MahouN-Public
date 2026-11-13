"""
Advanced W&B Logger
===================

Professional-grade W&B logging with advanced features.

Extracted from legacy code with upgrades.
"""


import os
import sys
import time
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

import torch
import numpy as np

try:
    import wandb
    WANDB_AVAILABLE = True
except ImportError:
    WANDB_AVAILABLE = False
    wandb = None

from mahoun.pipelines._logging import setup_logger

log = setup_logger("wandb_logger")


class AdvancedWandBLogger:
    """
    Professional-grade W&B logging with advanced features
    
    Features:
    - Comprehensive metrics logging
    - Graph statistics
    - Uncertainty analysis
    - Model artifacts
    - Custom charts
    
    Upgraded from legacy code with:
    - Better error handling
    - Type hints
    - Graceful degradation
    """
    
    def __init__(
        self,
        project_name: str = "mahoun-legal-ai",
        entity: Optional[str] = None,
        enabled: bool = True
    ):
        """
        Initialize W&B Logger
        
        Args:
            project_name: W&B project name
            entity: W&B entity (team/user)
            enabled: Enable W&B logging
        """
        self.project_name = project_name
        self.entity = entity
        self.enabled = enabled and WANDB_AVAILABLE
        self.run = None
        self.is_initialized = False
        self.metrics_buffer: List[Tuple[Dict, Optional[int]]] = []
        self.custom_charts: Dict[str, Any] = {}
        
        if not WANDB_AVAILABLE and enabled:
            log.warning("W&B not available. Install with: pip install wandb")
            self.enabled = False
        
        log.info(
            f"Initialized AdvancedWandBLogger: "
            f"project={project_name}, enabled={self.enabled}"
        )
    
    def initialize_run(
        self,
        config: Dict[str, Any],
        run_name: Optional[str] = None,
        tags: Optional[List[str]] = None,
        notes: Optional[str] = None
    ):
        """
        Initialize W&B run
        
        Args:
            config: Run configuration
            run_name: Custom run name
            tags: Run tags
            notes: Run notes
        """
        if not self.enabled:
            log.warning("W&B not enabled, skipping initialization")
            return
        
        try:
            # Enhanced configuration
            enhanced_config = {
                **config,
                "system_info": {
                    "python_version": sys.version,
                    "torch_version": torch.__version__,
                    "cuda_available": torch.cuda.is_available(),
                    "gpu_name": (
                        torch.cuda.get_device_name(0)
                        if torch.cuda.is_available()
                        else None
                    ),
                },
                "timestamp": datetime.now().isoformat(),
                "architecture": "mahoun_v2",
            }
            
            # Initialize run
            self.run = wandb.init(
                project=self.project_name,
                entity=self.entity,
                name=run_name or f"mahoun-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
                config=enhanced_config,
                tags=(tags or []) + ["mahoun", "legal-ai", "v2"],
                notes=notes or "MAHOUN Legal AI Training Run",
            )
            
            self.is_initialized = True
            
            # Setup custom charts
            self._setup_custom_charts()
            
            log.info(f"✅ W&B run initialized: {self.run.url}")
            
        except Exception as e:
            log.error(f"Failed to initialize W&B: {e}")
            self.is_initialized = False
            self.enabled = False
    
    def _setup_custom_charts(self):
        """Setup custom W&B charts"""
        if not self.is_initialized:
            return
        
        try:
            # Custom charts can be added here
            log.debug("Custom W&B charts configured")
        except Exception as e:
            log.warning(f"Failed to setup custom charts: {e}")
    
    def log_metrics(
        self,
        metrics: Dict[str, Any],
        step: Optional[int] = None,
        commit: bool = True
    ):
        """
        Log metrics to W&B
        
        Args:
            metrics: Metrics dictionary
            step: Step number
            commit: Commit immediately
        """
        if not self.enabled:
            return
        
        if not self.is_initialized:
            log.warning("W&B not initialized, buffering metrics")
            self.metrics_buffer.append((metrics, step))
            return
        
        try:
            # Add timestamp
            enhanced_metrics = {
                **metrics,
                "timestamp": time.time(),
            }
            
            # Log to W&B
            wandb.log(enhanced_metrics, step=step, commit=commit)
            
            log.debug(f"Logged metrics: {list(metrics.keys())}")
            
        except Exception as e:
            log.error(f"Failed to log metrics: {e}")
    
    def log_graph_statistics(self, graphs: List[Any]):
        """
        Log graph neural network statistics
        
        Args:
            graphs: List of PyG Data objects
        """
        if not self.enabled or not self.is_initialized:
            return
        
        try:
            node_counts = [g.num_nodes for g in graphs if g is not None]
            edge_counts = [
                g.edge_index.shape[1] for g in graphs if g is not None
            ]
            
            if not node_counts:
                return
            
            graph_stats = {
                "graph/avg_nodes": np.mean(node_counts),
                "graph/avg_edges": np.mean(edge_counts),
                "graph/max_nodes": max(node_counts),
                "graph/min_nodes": min(node_counts),
                "graph/total_graphs": len(node_counts),
            }
            
            self.log_metrics(graph_stats)
            
            log.debug("Logged graph statistics to W&B")
            
        except Exception as e:
            log.error(f"Failed to log graph statistics: {e}")
    
    def log_uncertainty_analysis(
        self,
        predictions: torch.Tensor,
        uncertainties: torch.Tensor,
        true_values: Optional[torch.Tensor] = None
    ):
        """
        Log uncertainty quantification analysis
        
        Args:
            predictions: Predictions
            uncertainties: Uncertainties
            true_values: True values (optional)
        """
        if not self.enabled or not self.is_initialized:
            return
        
        try:
            uncertainty_stats = {
                "uncertainty/avg": torch.mean(uncertainties).item(),
                "uncertainty/max": torch.max(uncertainties).item(),
                "uncertainty/min": torch.min(uncertainties).item(),
                "uncertainty/std": torch.std(uncertainties).item(),
            }
            
            # Calibration analysis if true values provided
            if true_values is not None:
                errors = torch.abs(predictions - true_values)
                
                # Correlation
                correlation = torch.corrcoef(
                    torch.stack([uncertainties, errors])
                )[0, 1].item()
                
                uncertainty_stats["uncertainty/error_correlation"] = correlation
            
            self.log_metrics(uncertainty_stats)
            
            log.debug("Logged uncertainty analysis to W&B")
            
        except Exception as e:
            log.error(f"Failed to log uncertainty analysis: {e}")
    
    def log_model_artifacts(
        self,
        model_path: str,
        model_type: str,
        metadata: Dict[str, Any]
    ):
        """
        Log model artifacts
        
        Args:
            model_path: Path to model
            model_type: Model type
            metadata: Model metadata
        """
        if not self.enabled or not self.is_initialized:
            return
        
        try:
            # Enhanced metadata
            enhanced_metadata = {
                **metadata,
                "model_type": model_type,
                "timestamp": datetime.now().isoformat(),
                "file_size": (
                    os.path.getsize(model_path)
                    if os.path.exists(model_path)
                    else 0
                ),
            }
            
            # Create artifact
            artifact = wandb.Artifact(
                name=f"mahoun-{model_type}-model",
                type="model",
                description=f"MAHOUN {model_type} model",
                metadata=enhanced_metadata,
            )
            
            # Add files
            if os.path.isdir(model_path):
                artifact.add_dir(model_path)
            else:
                artifact.add_file(model_path)
            
            # Log artifact
            self.run.log_artifact(artifact)
            
            log.info(f"✅ Model artifacts logged: {model_path}")
            
        except Exception as e:
            log.error(f"Failed to log model artifacts: {e}")
    
    def flush_buffered_metrics(self):
        """Flush any buffered metrics"""
        if not self.metrics_buffer or not self.is_initialized:
            return
        
        log.info(f"Flushing {len(self.metrics_buffer)} buffered metrics")
        
        for metrics, step in self.metrics_buffer:
            self.log_metrics(metrics, step, commit=False)
        
        # Commit all
        if self.enabled:
            wandb.log({}, commit=True)
        
        self.metrics_buffer.clear()
    
    def finish_run(self, summary: Optional[Dict[str, Any]] = None):
        """
        Finish W&B run
        
        Args:
            summary: Run summary
        """
        if not self.is_initialized:
            return
        
        try:
            # Flush buffered metrics
            self.flush_buffered_metrics()
            
            # Add summary
            if summary:
                for key, value in summary.items():
                    wandb.run.summary[key] = value
            
            # Finish run
            wandb.finish()
            
            log.info("✅ W&B run finished successfully")
            
        except Exception as e:
            log.error(f"Error finishing W&B run: {e}")
        finally:
            self.is_initialized = False
            self.run = None
    
    def watch_model(self, model: torch.nn.Module, log_freq: int = 100):
        """
        Watch model for gradients and parameters
        
        Args:
            model: PyTorch model
            log_freq: Logging frequency
        """
        if not self.enabled or not self.is_initialized:
            return
        
        try:
            wandb.watch(model, log="all", log_freq=log_freq)
            log.info("Started watching model")
        except Exception as e:
            log.error(f"Failed to watch model: {e}")
