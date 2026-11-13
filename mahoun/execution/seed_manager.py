"""
Seed Manager
============

Deterministic seed management for reproducible executions.

Features:
- Seed versioning
- Seed derivation (parent -> child seeds)
- Seed validation
- Audit trail
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional
from threading import RLock

logger = logging.getLogger(__name__)


@dataclass
class SeedContext:
    """
    Seed context with full lineage.
    """
    seed: int
    version: str = "1.0.0"
    parent_seed: Optional[int] = None
    derivation_path: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, any] = field(default_factory=dict)
    
    def derive_child(self, purpose: str) -> "SeedContext":
        """
        Derive child seed for specific purpose.
        
        Args:
            purpose: Purpose identifier (e.g., "llm_generation", "graph_traversal")
            
        Returns:
            New SeedContext with derived seed
        """
        # Deterministic derivation
        data = f"{self.seed}:{purpose}:{len(self.derivation_path)}"
        child_seed = int(hashlib.sha256(data.encode()).hexdigest()[:8], 16)
        
        return SeedContext(
            seed=child_seed,
            version=self.version,
            parent_seed=self.seed,
            derivation_path=self.derivation_path + [purpose],
            metadata={"derived_from": self.seed, "purpose": purpose}
        )


class SeedManager:
    """
    Production-grade seed manager.
    
    Features:
    - Seed versioning for reproducibility
    - Hierarchical seed derivation
    - Seed validation
    - Audit trail
    - Thread-safe operations
    
    Usage:
        manager = SeedManager()
        
        # Create root seed
        root_ctx = manager.create_seed(seed=42, version="1.0.0")
        
        # Derive child seeds
        llm_ctx = manager.derive_seed(root_ctx, "llm_generation")
        graph_ctx = manager.derive_seed(root_ctx, "graph_traversal")
        
        # Apply seed
        manager.apply_seed(llm_ctx)
    """
    
    def __init__(self, enable_audit: bool = True):
        """
        Initialize seed manager.
        
        Args:
            enable_audit: Enable seed audit trail
        """
        self.enable_audit = enable_audit
        
        # Seed history
        self._seed_history: List[SeedContext] = []
        self._lock = RLock()
        
        # Current seed context
        self._current_context: Optional[SeedContext] = None
        
        logger.info(f"SeedManager initialized (audit={enable_audit})")
    
    def create_seed(
        self,
        seed: Optional[int] = None,
        version: str = "1.0.0",
        metadata: Optional[Dict] = None
    ) -> SeedContext:
        """
        Create root seed context.
        
        Args:
            seed: Seed value (auto-generated if None)
            version: Seed version
            metadata: Additional metadata
            
        Returns:
            SeedContext
        """
        if seed is None:
            # Generate from timestamp
            seed = int(datetime.now(timezone.utc).timestamp() * 1000000) % (2**31)
        
        context = SeedContext(
            seed=seed,
            version=version,
            metadata=metadata or {}
        )
        
        # Store in history
        if self.enable_audit:
            with self._lock:
                self._seed_history.append(context)
        
        logger.debug(f"Created seed context: seed={seed}, version={version}")
        
        return context
    
    def derive_seed(
        self,
        parent_context: SeedContext,
        purpose: str
    ) -> SeedContext:
        """
        Derive child seed from parent.
        
        Args:
            parent_context: Parent seed context
            purpose: Purpose identifier
            
        Returns:
            Derived SeedContext
        """
        child_context = parent_context.derive_child(purpose)
        
        # Store in history
        if self.enable_audit:
            with self._lock:
                self._seed_history.append(child_context)
        
        logger.debug(
            f"Derived seed: parent={parent_context.seed}, "
            f"child={child_context.seed}, purpose={purpose}"
        )
        
        return child_context
    
    def apply_seed(self, context: SeedContext) -> None:
        """
        Apply seed to all random number generators.
        
        Args:
            context: Seed context to apply
        """
        import random
        import numpy as np
        
        # Set Python random
        random.seed(context.seed)
        
        # Set NumPy random
        np.random.seed(context.seed)
        
        # Set PyTorch random if available
        try:
            import torch
            torch.manual_seed(context.seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(context.seed)
                # Make CUDA operations deterministic
                torch.backends.cudnn.deterministic = True
                torch.backends.cudnn.benchmark = False
        except ImportError:
            pass
        
        # Update current context
        with self._lock:
            self._current_context = context
        
        logger.debug(f"Applied seed: {context.seed}")
    
    def get_current_context(self) -> Optional[SeedContext]:
        """Get current seed context"""
        with self._lock:
            return self._current_context
    
    def validate_seed(self, context: SeedContext) -> bool:
        """
        Validate seed context.
        
        Args:
            context: Seed context to validate
            
        Returns:
            True if valid
        """
        # Check seed range
        if not (0 <= context.seed < 2**31):
            logger.error(f"Invalid seed range: {context.seed}")
            return False
        
        # Check version format
        if not context.version or len(context.version.split('.')) != 3:
            logger.error(f"Invalid version format: {context.version}")
            return False
        
        # Check derivation consistency
        if context.parent_seed is not None:
            # Verify derivation
            if not context.derivation_path:
                logger.error("Parent seed set but no derivation path")
                return False
        
        return True
    
    def get_seed_lineage(self, context: SeedContext) -> List[SeedContext]:
        """
        Get full seed lineage (root to current).
        
        Args:
            context: Seed context
            
        Returns:
            List of SeedContext from root to current
        """
        lineage = [context]
        
        # Trace back to root
        current = context
        while current.parent_seed is not None:
            # Find parent in history
            parent = self._find_seed_in_history(current.parent_seed)
            if parent:
                lineage.insert(0, parent)
                current = parent
            else:
                break
        
        return lineage
    
    def _find_seed_in_history(self, seed: int) -> Optional[SeedContext]:
        """Find seed context in history"""
        with self._lock:
            for ctx in reversed(self._seed_history):
                if ctx.seed == seed:
                    return ctx
        return None
    
    def get_statistics(self) -> Dict[str, any]:
        """Get seed manager statistics"""
        with self._lock:
            return {
                "total_seeds": len(self._seed_history),
                "current_seed": self._current_context.seed if self._current_context else None,
                "current_version": self._current_context.version if self._current_context else None,
            }
    
    def export_audit_trail(self) -> List[Dict]:
        """Export seed audit trail"""
        with self._lock:
            return [
                {
                    "seed": ctx.seed,
                    "version": ctx.version,
                    "parent_seed": ctx.parent_seed,
                    "derivation_path": ctx.derivation_path,
                    "timestamp": ctx.timestamp.isoformat(),
                    "metadata": ctx.metadata,
                }
                for ctx in self._seed_history
            ]
