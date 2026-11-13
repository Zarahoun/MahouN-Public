"""
Unified Uncertainty Service

سرویس یکپارچه برای تخمین uncertainty با روش‌های مختلف
"""

import numpy as np
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

# Import existing calibration
try:
    from mahoun.uncertainty.calibration import UncertaintyCalibrator, CalibrationResult
    HAS_CALIBRATION = True
except ImportError:
    HAS_CALIBRATION = False
    UncertaintyCalibrator: Optional[Any] = None
    CalibrationResult: Optional[Any] = None
# Import our new ensemble
from .ensemble import EnsembleUncertainty, EnsembleConfig

try:
    from mahoun.pipelines._logging import setup_logger
    log = setup_logger("uncertainty_service")
except ImportError:
    import logging
    log = logging.getLogger("uncertainty_service")


# ============================================================================
# Data Models
# ============================================================================

class UncertaintyMethod(str, Enum):
    """Uncertainty estimation methods"""
    ENSEMBLE = "ensemble"
    CALIBRATION = "calibration"
    SIMPLE = "simple"
    COMBINED = "combined"


@dataclass
class UncertaintyEstimate:
    """
    Uncertainty estimate result
    
    Attributes:
        epistemic_uncertainty: Model uncertainty
        aleatoric_uncertainty: Data uncertainty
        total_uncertainty: Combined uncertainty
        confidence: 1 - total_uncertainty
        method: Method used
        metadata: Additional information
    """
    epistemic_uncertainty: float
    aleatoric_uncertainty: float
    total_uncertainty: float
    confidence: float
    method: str
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def is_high_confidence(self, threshold: float = 0.2) -> bool:
        """Check if uncertainty is below threshold (high confidence)"""
        return self.total_uncertainty < threshold
    
    def is_low_confidence(self, threshold: float = 0.5) -> bool:
        """Check if uncertainty is above threshold (low confidence)"""
        return self.total_uncertainty > threshold


@dataclass
class UncertaintyConfig:
    """Configuration for uncertainty service"""
    default_method: UncertaintyMethod = UncertaintyMethod.ENSEMBLE
    enable_calibration: bool = True
    enable_ensemble: bool = True
    ensemble_config: Optional[EnsembleConfig] = None
    calibration_weights: Optional[Dict[str, float]] = None


# ============================================================================
# Uncertainty Service
# ============================================================================

class UncertaintyService:
    """
    Unified uncertainty quantification service
    
    Methods:
    - Ensemble uncertainty (epistemic + aleatoric)
    - Calibration (from core/uncertainty)
    - Simple variance-based
    - Combined (fusion of multiple methods)
    
    Example:
        >>> service = UncertaintyService()
        >>> scores = [0.8, 0.85, 0.82]
        >>> estimate = service.estimate(scores, method="ensemble")
        >>> print(f"Uncertainty: {estimate.total_uncertainty:.3f}")
    """
    
    def __init__(self, config: Optional[UncertaintyConfig] = None):
        """
        Initialize uncertainty service
        
        Args:
            config: Service configuration
        """
        self.config = config or UncertaintyConfig()
        
        # Initialize components
        self.ensemble = None
        if self.config.enable_ensemble:
            self.ensemble = EnsembleUncertainty(self.config.ensemble_config)
        
        self.calibrator = None
        if self.config.enable_calibration and HAS_CALIBRATION:
            self.calibrator = UncertaintyCalibrator(
                enable_gp=True,
                enable_temperature=True,
                enable_conformal=True,
                fusion_weights=self.config.calibration_weights
            )
            log.info("✅ Calibrator initialized")
        elif self.config.enable_calibration and not HAS_CALIBRATION:
            log.warning("⚠️ Calibration requested but core.uncertainty not available")
        
        log.info(f"Uncertainty Service initialized (method={self.config.default_method.value})")
    
    def estimate(
        self,
        scores: List[float],
        features: Optional[np.ndarray] = None,
        method: Optional[UncertaintyMethod] = None
    ) -> UncertaintyEstimate:
        """
        Estimate uncertainty
        
        Args:
            scores: Model scores
            features: Optional features for advanced methods
            method: Estimation method (overrides default)
            
        Returns:
            Uncertainty estimate
        """
        method = method or self.config.default_method
        
        if method == UncertaintyMethod.ENSEMBLE:
            return self._ensemble_uncertainty(scores)
        elif method == UncertaintyMethod.CALIBRATION:
            return self._calibration_uncertainty(scores)
        elif method == UncertaintyMethod.SIMPLE:
            return self._simple_uncertainty(scores)
        elif method == UncertaintyMethod.COMBINED:
            return self._combined_uncertainty(scores)
        else:
            log.warning(f"Unknown method {method}, using ensemble")
            return self._ensemble_uncertainty(scores)
    
    def _ensemble_uncertainty(
        self,
        scores: List[float]
    ) -> UncertaintyEstimate:
        """Ensemble-based uncertainty"""
        if not self.ensemble:
            return self._simple_uncertainty(scores)
        
        epistemic, aleatoric, total = self.ensemble.estimate(scores)
        
        return UncertaintyEstimate(
            epistemic_uncertainty=epistemic,
            aleatoric_uncertainty=aleatoric,
            total_uncertainty=total,
            confidence=1.0 - total,
            method="ensemble",
            metadata={
                "n_scores": len(scores),
                "mean_score": float(np.mean(scores)),
                "std_score": float(np.std(scores))
            }
        )
    
    def _calibration_uncertainty(
        self,
        scores: List[float]
    ) -> UncertaintyEstimate:
        """Calibration-based uncertainty"""
        if not self.calibrator:
            log.warning("Calibrator not available, falling back to ensemble")
            return self._ensemble_uncertainty(scores)
        
        # Use mean score as confidence
        confidence_score = float(np.mean(scores))
        
        # Calibrate
        result = self.calibrator.calibrate(
            gp_variance=float(np.var(scores)),
            confidence_score=confidence_score
        )
        
        # Extract uncertainty
        uncertainty = result.uncertainty_score if result.uncertainty_score is not None else 0.5
        
        return UncertaintyEstimate(
            epistemic_uncertainty=uncertainty * 0.7,  # Approximate split
            aleatoric_uncertainty=uncertainty * 0.3,
            total_uncertainty=uncertainty,
            confidence=1.0 - uncertainty,
            method="calibration",
            metadata={
                "calibrated_scores": result.calibrated_scores.tolist() if result.calibrated_scores is not None else [],
                "confidence_intervals": result.confidence_intervals
            }
        )
    
    def _simple_uncertainty(
        self,
        scores: List[float]
    ) -> UncertaintyEstimate:
        """Simple variance-based uncertainty"""
        scores_array = np.array(scores)
        
        # Use standard deviation as uncertainty
        std = float(np.std(scores_array))
        
        # Approximate epistemic/aleatoric split
        epistemic = std * 0.7
        aleatoric = std * 0.3
        total = std
        
        return UncertaintyEstimate(
            epistemic_uncertainty=epistemic,
            aleatoric_uncertainty=aleatoric,
            total_uncertainty=total,
            confidence=1.0 - total,
            method="simple"
        )
    
    def _combined_uncertainty(
        self,
        scores: List[float]
    ) -> UncertaintyEstimate:
        """Combined uncertainty from multiple methods"""
        estimates: List[Any] = []
        # Get ensemble estimate
        if self.ensemble:
            estimates.append(self._ensemble_uncertainty(scores))
        
        # Get calibration estimate
        if self.calibrator:
            estimates.append(self._calibration_uncertainty(scores))
        
        # If no estimates, use simple
        if not estimates:
            return self._simple_uncertainty(scores)
        
        # Average uncertainties
        epistemic = np.mean([e.epistemic_uncertainty for e in estimates])
        aleatoric = np.mean([e.aleatoric_uncertainty for e in estimates])
        total = np.mean([e.total_uncertainty for e in estimates])
        
        return UncertaintyEstimate(
            epistemic_uncertainty=float(epistemic),
            aleatoric_uncertainty=float(aleatoric),
            total_uncertainty=float(total),
            confidence=1.0 - float(total),
            method="combined",
            metadata={
                "n_methods": len(estimates),
                "methods": [e.method for e in estimates]
            }
        )
    
    def filter_by_uncertainty(
        self,
        results: List[Any],
        threshold: float = 0.2,
        min_results: int = 3
    ) -> List[Any]:
        """
        Filter results by uncertainty threshold
        
        Args:
            results: Results with uncertainty estimates
            threshold: Max uncertainty to keep
            min_results: Minimum results to return
            
        Returns:
            Filtered results
        """
        if not results:
            return results
        
        # Separate results with and without uncertainty
        with_uncertainty: List[Any] = []
        without_uncertainty: List[Any] = []
        for r in results:
            if hasattr(r, 'uncertainty') and r.uncertainty is not None:
                with_uncertainty.append(r)
            else:
                without_uncertainty.append(r)
        
        # Filter by threshold
        high_confidence = [
            r for r in with_uncertainty
            if r.uncertainty.is_high_confidence(threshold)
        ]
        
        log.debug(
            f"Uncertainty filtering: {len(high_confidence)}/{len(with_uncertainty)} "
            f"high confidence (threshold={threshold})"
        )
        
        # Combine: high confidence + no uncertainty
        filtered = high_confidence + without_uncertainty
        
        # Ensure minimum results
        if len(filtered) < min_results:
            log.warning(
                f"Only {len(filtered)} high-confidence results, "
                f"adding {min_results - len(filtered)} more"
            )
            # Add low-confidence results to meet minimum
            low_confidence = [
                r for r in with_uncertainty
                if not r.uncertainty.is_high_confidence(threshold)
            ]
            filtered.extend(low_confidence[:min_results - len(filtered)])
        
        return filtered
    
    def calibrate(
        self,
        calibration_data: Dict[str, Any]
    ):
        """
        Calibrate uncertainty estimator
        
        Args:
            calibration_data: Calibration dataset
        """
        if self.calibrator:
            self.calibrator.fit(calibration_data)
            log.info("✅ Uncertainty calibrator fitted")
        else:
            log.warning("⚠️ No calibrator available")


# ============================================================================
# Convenience Functions
# ============================================================================

def estimate_uncertainty(
    scores: List[float],
    method: str = "ensemble",
    config: Optional[UncertaintyConfig] = None
) -> UncertaintyEstimate:
    """
    Convenience function for uncertainty estimation
    
    Args:
        scores: Score list
        method: Estimation method
        config: Optional configuration
        
    Returns:
        Uncertainty estimate
    """
    service = UncertaintyService(config)
    return service.estimate(scores, method=UncertaintyMethod(method))


def filter_by_confidence(
    results: List[Any],
    threshold: float = 0.2,
    min_results: int = 3
) -> List[Any]:
    """
    Convenience function for filtering by confidence
    
    Args:
        results: Results with uncertainty
        threshold: Uncertainty threshold
        min_results: Minimum results
        
    Returns:
        Filtered results
    """
    service = UncertaintyService()
    return service.filter_by_uncertainty(results, threshold, min_results)
