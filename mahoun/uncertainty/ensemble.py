"""
Ensemble Uncertainty Estimation

محاسبه uncertainty از طریق ensemble methods
"""

import numpy as np
from typing import Any, List, Optional, Tuple
from dataclasses import dataclass

try:
    from mahoun.pipelines._logging import setup_logger
    log = setup_logger("ensemble_uncertainty")
except ImportError:
    import logging
    log = logging.getLogger("ensemble_uncertainty")


@dataclass
class EnsembleConfig:
    """Configuration for ensemble uncertainty"""
    min_samples: int = 3
    use_bootstrap: bool = False
    bootstrap_samples: int = 100
    confidence_level: float = 0.95


class EnsembleUncertainty:
    """
    Ensemble-based uncertainty estimation
    
    Calculates:
    - Epistemic uncertainty (model uncertainty) - variance across ensemble
    - Aleatoric uncertainty (data uncertainty) - average variance within models
    - Total uncertainty - combination of both
    
    Example:
        >>> ensemble = EnsembleUncertainty()
        >>> scores = [0.8, 0.85, 0.82, 0.88]
        >>> epistemic, aleatoric, total = ensemble.estimate(scores)
    """
    
    def __init__(self, config: Optional[EnsembleConfig] = None):
        """
        Initialize ensemble uncertainty estimator
        
        Args:
            config: Ensemble configuration
        """
        self.config = config or EnsembleConfig()
        log.info("Ensemble Uncertainty initialized")
    
    def estimate(
        self,
        scores: List[float],
        individual_variances: Optional[List[float]] = None
    ) -> Tuple[float, float, float]:
        """
        Estimate uncertainty from ensemble scores
        
        Args:
            scores: Scores from ensemble members
            individual_variances: Optional variances from each member
            
        Returns:
            (epistemic_uncertainty, aleatoric_uncertainty, total_uncertainty)
        """
        if len(scores) < self.config.min_samples:
            log.warning(f"Too few samples ({len(scores)}), returning default uncertainty")
            return 0.5, 0.0, 0.5
        
        scores_array = np.array(scores)
        
        # Epistemic uncertainty: variance across ensemble
        epistemic = float(np.var(scores_array))
        
        # Aleatoric uncertainty: average of individual variances
        if individual_variances is not None and len(individual_variances) > 0:
            aleatoric = float(np.mean(individual_variances))
        else:
            # Approximate from score spread
            aleatoric = float(np.std(scores_array) * 0.5)
        
        # Total uncertainty: sqrt(epistemic^2 + aleatoric^2)
        total = float(np.sqrt(epistemic ** 2 + aleatoric ** 2))
        
        return epistemic, aleatoric, total
    
    def estimate_with_confidence(
        self,
        scores: List[float]
    ) -> Tuple[float, float, float, Tuple[float, float]]:
        """
        Estimate uncertainty with confidence intervals
        
        Args:
            scores: Scores from ensemble
            
        Returns:
            (epistemic, aleatoric, total, confidence_interval)
        """
        epistemic, aleatoric, total = self.estimate(scores)
        
        # Calculate confidence interval
        scores_array = np.array(scores)
        mean = np.mean(scores_array)
        std = np.std(scores_array)
        
        # Z-score for confidence level
        z_score = 1.96  # 95% confidence
        if self.config.confidence_level == 0.99:
            z_score = 2.576
        elif self.config.confidence_level == 0.90:
            z_score = 1.645
        
        margin = z_score * std / np.sqrt(len(scores))
        confidence_interval = (
            float(mean - margin),
            float(mean + margin)
        )
        
        return epistemic, aleatoric, total, confidence_interval
    
    def bootstrap_estimate(
        self,
        scores: List[float],
        n_bootstrap: Optional[int] = None
    ) -> Tuple[float, float, float]:
        """
        Estimate uncertainty using bootstrap
        
        Args:
            scores: Original scores
            n_bootstrap: Number of bootstrap samples
            
        Returns:
            (epistemic, aleatoric, total)
        """
        n_bootstrap = n_bootstrap or self.config.bootstrap_samples
        scores_array = np.array(scores)
        n_samples = len(scores_array)
        
        # Bootstrap resampling
        bootstrap_means: List[Any] = []
        bootstrap_vars: List[Any] = []
        for _ in range(n_bootstrap):
            # Resample with replacement
            indices = np.random.choice(n_samples, size=n_samples, replace=True)
            bootstrap_sample = scores_array[indices]
            
            bootstrap_means.append(np.mean(bootstrap_sample))
            bootstrap_vars.append(np.var(bootstrap_sample))
        
        # Epistemic: variance of means
        epistemic = float(np.var(bootstrap_means))
        
        # Aleatoric: mean of variances
        aleatoric = float(np.mean(bootstrap_vars))
        
        # Total
        total = float(np.sqrt(epistemic ** 2 + aleatoric ** 2))
        
        return epistemic, aleatoric, total
    
    def decompose_uncertainty(
        self,
        scores: List[float],
        use_bootstrap: Optional[bool] = None
    ) -> dict:
        """
        Full uncertainty decomposition
        
        Args:
            scores: Ensemble scores
            use_bootstrap: Use bootstrap method
            
        Returns:
            Dictionary with all uncertainty components
        """
        use_bootstrap = use_bootstrap if use_bootstrap is not None else self.config.use_bootstrap
        
        if use_bootstrap:
            epistemic, aleatoric, total = self.bootstrap_estimate(scores)
        else:
            epistemic, aleatoric, total = self.estimate(scores)
        
        # Additional metrics
        scores_array = np.array(scores)
        
        return {
            "epistemic_uncertainty": epistemic,
            "aleatoric_uncertainty": aleatoric,
            "total_uncertainty": total,
            "mean_score": float(np.mean(scores_array)),
            "std_score": float(np.std(scores_array)),
            "min_score": float(np.min(scores_array)),
            "max_score": float(np.max(scores_array)),
            "range": float(np.max(scores_array) - np.min(scores_array)),
            "confidence": 1.0 - total,
            "n_samples": len(scores)
        }


# ============================================================================
# Utility Functions
# ============================================================================

def estimate_from_multiple_sources(
    vector_scores: List[float],
    sparse_scores: List[float],
    graph_scores: Optional[List[float]] = None
) -> Tuple[float, float, float]:
    """
    Estimate uncertainty from multiple retrieval sources
    
    Args:
        vector_scores: Scores from vector search
        sparse_scores: Scores from sparse search
        graph_scores: Optional scores from graph search
        
    Returns:
        (epistemic, aleatoric, total)
    """
    # Combine all scores
    all_scores = vector_scores + sparse_scores
    if graph_scores:
        all_scores += graph_scores
    
    # Estimate
    ensemble = EnsembleUncertainty()
    return ensemble.estimate(all_scores)


def calculate_prediction_interval(
    scores: List[float],
    confidence_level: float = 0.95
) -> Tuple[float, float]:
    """
    Calculate prediction interval
    
    Args:
        scores: Score list
        confidence_level: Confidence level (0.90, 0.95, 0.99)
        
    Returns:
        (lower_bound, upper_bound)
    """
    scores_array = np.array(scores)
    mean = np.mean(scores_array)
    std = np.std(scores_array)
    
    # Z-score
    z_scores = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}
    z = z_scores.get(confidence_level, 1.96)
    
    margin = z * std
    
    return float(mean - margin), float(mean + margin)
