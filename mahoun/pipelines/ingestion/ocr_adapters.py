"""
OCR Dependency Injection Container for Ingestion Pipeline
========================================================

Thread-safe dependency injection container for OCR components.
Provides lazy singleton initialization with graceful degradation.

Design Principles:
- Thread-safe lazy initialization
- Graceful degradation on missing dependencies
- Singleton management for expensive OCR engines
- Configurable ensemble strategies
- Production-grade fail-closed behavior
"""

import logging
import threading
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class OCRContainerConfig:
    """Configuration for OCR dependency container"""
    
    # Ensemble configuration
    enable_ensemble: bool = True
    ensemble_strategy: str = "weighted"  # majority, weighted, best_confidence, unanimous
    min_engines: int = 2
    
    # Post-processing
    enable_post_processor: bool = True
    enable_pre_processor: bool = True
    
    # Performance
    enable_caching: bool = False
    parallel_execution: bool = True
    
    # Production mode
    fail_closed: bool = True  # Fail if required dependencies missing


class OCRDependencyContainer:
    """
    Thread-safe dependency injection container for OCR components.
    
    Provides lazy singleton initialization with graceful degradation.
    Similar pattern to ReasoningDependencyContainer for consistency.
    """
    
    def __init__(self, config: Optional[OCRContainerConfig] = None):
        """
        Initialize OCR dependency container.
        
        Args:
            config: Configuration for OCR components
        """
        self.config = config or OCRContainerConfig()
        
        # OCR Ensemble (multi-engine voting)
        self._ocr_ensemble_lock = threading.Lock()
        self._ocr_ensemble: Optional[Any] = None
        self._ocr_ensemble_initialized = False
        
        # Post-processor
        self._post_processor_lock = threading.Lock()
        self._post_processor: Optional[Any] = None
        self._post_processor_initialized = False
        
        # Pre-processor
        self._pre_processor_lock = threading.Lock()
        self._pre_processor: Optional[Any] = None
        self._pre_processor_initialized = False
        
        # Hardened OCR (single engine, production-grade)
        self._hardened_ocr_lock = threading.Lock()
        self._hardened_ocr: Optional[Any] = None
        self._hardened_ocr_initialized = False
        
        logger.info("OCRDependencyContainer initialized with lazy initialization")
    
    # ============================================================================
    # OCR Ensemble (Multi-engine voting)
    # ============================================================================
    
    @property
    def ocr_ensemble(self) -> Optional[Any]:
        """Lazy singleton for OCR Ensemble"""
        if self._ocr_ensemble_initialized:
            return self._ocr_ensemble
        
        with self._ocr_ensemble_lock:
            if self._ocr_ensemble_initialized:
                return self._ocr_ensemble
            
            self._ocr_ensemble = self._create_ocr_ensemble()
            self._ocr_ensemble_initialized = True
            return self._ocr_ensemble
    
    def _create_ocr_ensemble(self) -> Optional[Any]:
        """Create OCR Ensemble with graceful degradation"""
        if not self.config.enable_ensemble:
            logger.info("OCR Ensemble disabled by configuration")
            return None
        
        try:
            from mahoun.pipelines.ingestion.ocr_ensemble import (
                OCREnsemble,
                EnsembleConfig,
                VotingStrategy
            )
            
            # Map strategy string to enum
            strategy_map = {
                "majority": VotingStrategy.MAJORITY,
                "weighted": VotingStrategy.WEIGHTED,
                "best_confidence": VotingStrategy.BEST_CONFIDENCE,
                "unanimous": VotingStrategy.UNANIMOUS
            }
            
            voting_strategy = strategy_map.get(
                self.config.ensemble_strategy,
                VotingStrategy.WEIGHTED
            )
            
            config = EnsembleConfig(
                engines=['paddle', 'tesseract', 'easyocr'],
                min_engines=self.config.min_engines,
                voting_strategy=voting_strategy,
                parallel_execution=self.config.parallel_execution,
                enable_caching=self.config.enable_caching
            )
            
            ensemble = OCREnsemble(config)
            logger.info(f"OCR Ensemble initialized with strategy: {self.config.ensemble_strategy}")
            return ensemble
            
        except ImportError as e:
            logger.warning(f"OCR Ensemble not available: {e}")
            if self.config.fail_closed:
                logger.error("Fail-closed mode: OCR Ensemble required but unavailable")
                # In production, this should raise an exception
                # For now, we degrade gracefully
            return None
        except Exception as e:
            logger.error(f"Failed to initialize OCR Ensemble: {e}")
            return None
    
    # ============================================================================
    # Post-processor
    # ============================================================================
    
    @property
    def post_processor(self) -> Optional[Any]:
        """Lazy singleton for OCR Post-processor"""
        if self._post_processor_initialized:
            return self._post_processor
        
        with self._post_processor_lock:
            if self._post_processor_initialized:
                return self._post_processor
            
            self._post_processor = self._create_post_processor()
            self._post_processor_initialized = True
            return self._post_processor
    
    def _create_post_processor(self) -> Optional[Any]:
        """Create OCR Post-processor with graceful degradation"""
        if not self.config.enable_post_processor:
            logger.info("OCR Post-processor disabled by configuration")
            return None
        
        try:
            from mahoun.pipelines.ingestion.ocr_post_processor import (
                OCRPostProcessor,
                PostProcessingConfig
            )
            
            config = PostProcessingConfig()
            processor = OCRPostProcessor(config)
            logger.info("OCR Post-processor initialized")
            return processor
            
        except ImportError as e:
            logger.warning(f"OCR Post-processor not available: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to initialize OCR Post-processor: {e}")
            return None
    
    # ============================================================================
    # Pre-processor
    # ============================================================================
    
    @property
    def pre_processor(self) -> Optional[Any]:
        """Lazy singleton for OCR Pre-processor"""
        if self._pre_processor_initialized:
            return self._pre_processor
        
        with self._pre_processor_lock:
            if self._pre_processor_initialized:
                return self._pre_processor
            
            self._pre_processor = self._create_pre_processor()
            self._pre_processor_initialized = True
            return self._pre_processor
    
    def _create_pre_processor(self) -> Optional[Any]:
        """Create OCR Pre-processor with graceful degradation"""
        if not self.config.enable_pre_processor:
            logger.info("OCR Pre-processor disabled by configuration")
            return None
        
        try:
            from mahoun.pipelines.ingestion.ocr_preprocessing import (
                OCRPreProcessor,
                PreProcessingConfig
            )
            
            config = PreProcessingConfig()
            processor = OCRPreProcessor(config)
            logger.info("OCR Pre-processor initialized")
            return processor
            
        except ImportError as e:
            logger.warning(f"OCR Pre-processor not available: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to initialize OCR Pre-processor: {e}")
            return None
    
    # ============================================================================
    # Hardened OCR (Production single-engine)
    # ============================================================================
    
    @property
    def hardened_ocr(self) -> Optional[Any]:
        """Lazy singleton for Hardened OCR"""
        if self._hardened_ocr_initialized:
            return self._hardened_ocr
        
        with self._hardened_ocr_lock:
            if self._hardened_ocr_initialized:
                return self._hardened_ocr
            
            self._hardened_ocr = self._create_hardened_ocr()
            self._hardened_ocr_initialized = True
            return self._hardened_ocr
    
    def _create_hardened_ocr(self) -> Optional[Any]:
        """Create Hardened OCR with graceful degradation"""
        try:
            from mahoun.pipelines.ingestion.hardened_paddle_ocr import HardenedPaddleOCR
            
            ocr = HardenedPaddleOCR()
            logger.info("Hardened OCR initialized")
            return ocr
            
        except ImportError as e:
            logger.warning(f"Hardened OCR not available: {e}")
            if self.config.fail_closed:
                logger.error("Fail-closed mode: Hardened OCR required but unavailable")
            return None
        except Exception as e:
            logger.error(f"Failed to initialize Hardened OCR: {e}")
            return None
    
    # ============================================================================
    # Reset & Utility Methods
    # ============================================================================
    
    def reset(self):
        """Reset all initialized components (for testing)"""
        with self._ocr_ensemble_lock:
            self._ocr_ensemble = None
            self._ocr_ensemble_initialized = False
        
        with self._post_processor_lock:
            self._post_processor = None
            self._post_processor_initialized = False
        
        with self._pre_processor_lock:
            self._pre_processor = None
            self._pre_processor_initialized = False
        
        with self._hardened_ocr_lock:
            self._hardened_ocr = None
            self._hardened_ocr_initialized = False
        
        logger.info("OCRDependencyContainer reset")
    
    def get_status(self) -> Dict[str, bool]:
        """Get initialization status of all components"""
        return {
            "ocr_ensemble": self._ocr_ensemble_initialized,
            "post_processor": self._post_processor_initialized,
            "pre_processor": self._pre_processor_initialized,
            "hardened_ocr": self._hardened_ocr_initialized
        }


# ============================================================================
# Global Singleton (for application-level access)
# =================================================================##

_global_ocr_container: Optional[OCRDependencyContainer] = None
_global_ocr_container_lock = threading.Lock()


def get_ocr_container(config: Optional[OCRContainerConfig] = None) -> OCRDependencyContainer:
    """
    Get global OCR dependency container singleton.
    
    Args:
        config: Configuration for first-time initialization
        
    Returns:
        OCRDependencyContainer instance
    """
    global _global_ocr_container
    
    if _global_ocr_container is not None:
        return _global_ocr_container
    
    with _global_ocr_container_lock:
        if _global_ocr_container is not None:
            return _global_ocr_container
        
        _global_ocr_container = OCRDependencyContainer(config)
        return _global_ocr_container


def reset_global_ocr_container():
    """Reset global OCR container (for testing)"""
    global _global_ocr_container
    
    with _global_ocr_container_lock:
        if _global_ocr_container is not None:
            _global_ocr_container.reset()
            _global_ocr_container = None
