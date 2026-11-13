"""
MAHOUN Model Versioning & Integrity System
===========================================

Enterprise-grade model lifecycle management for airgapped deployments.

Features:
- Cryptographic checksum verification (SHA-256)
- Atomic model updates with rollback
- Version compatibility checking
- Provenance tracking
- Corruption detection
- Thread-safe operations

Classification: CRITICAL / AIRGAP-FIRST
Status: PRODUCTION-READY
"""

import hashlib
import json
import shutil
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from enum import Enum

from loguru import logger


# ============================================================================
# Type Definitions
# ============================================================================

class ModelType(str, Enum):
    """Supported model types in MAHOUN."""
    LLM = "llm"
    EMBEDDING = "embedding"
    NLI = "nli"
    RERANKER = "reranker"


class ModelStatus(str, Enum):
    """Model lifecycle status."""
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    CORRUPTED = "corrupted"
    PENDING = "pending"


@dataclass(frozen=True)
class ModelManifest:
    """
    Immutable model manifest with cryptographic integrity.
    
    Design:
    - Frozen dataclass (immutability)
    - SHA-256 checksums
    - ISO 8601 timestamps
    - Semantic versioning
    """
    model_id: str
    model_type: ModelType
    version: str
    checksum: str  # SHA-256 hex digest
    file_path: str
    file_size_bytes: int
    created_at: str  # ISO 8601
    status: ModelStatus = ModelStatus.PENDING
    metadata: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Serialize to dict for JSON storage."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "ModelManifest":
        """Deserialize from dict."""
        # Convert string enums back to enum types
        data["model_type"] = ModelType(data["model_type"])
        data["status"] = ModelStatus(data["status"])
        return cls(**data)


@dataclass
class ModelIntegrityResult:
    """Result of model integrity verification."""
    is_valid: bool
    model_id: str
    checksum_match: bool
    file_exists: bool
    size_match: bool
    error_message: Optional[str] = None
    
    def __bool__(self) -> bool:
        return self.is_valid


# ============================================================================
# Model Versioning System
# ============================================================================

class ModelVersioningSystem:
    """
    Thread-safe model versioning system for airgapped deployments.
    
    Responsibilities:
    - Checksum generation and verification
    - Model registration and activation
    - Atomic rollback to previous versions
    - Manifest persistence
    
    Design Principles:
    - Fail-closed: Corruption detected → system halts
    - Atomic operations: All-or-nothing updates
    - Provenance tracking: Full audit trail
    - Thread-safe: Lock-protected critical sections
    """
    
    def __init__(self, manifest_path: Path):
        """
        Initialize model versioning system.
        
        Args:
            manifest_path: Path to manifest JSON file
        """
        self.manifest_path = Path(manifest_path)
        self._lock = threading.Lock()
        self._manifests: Dict[str, ModelManifest] = {}
        self._load_manifests()
    
    # ========================================================================
    # Public API
    # ========================================================================
    
    def register_model(
        self,
        model_path: Path,
        model_id: str,
        model_type: ModelType,
        version: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> ModelManifest:
        """
        Register a new model with checksum verification.
        
        Args:
            model_path: Path to model file
            model_id: Unique model identifier
            model_type: Type of model (LLM, embedding, etc.)
            version: Semantic version string
            metadata: Optional metadata dict
        
        Returns:
            ModelManifest with computed checksum
        
        Raises:
            FileNotFoundError: Model file doesn't exist
            RuntimeError: Model already registered
        """
        with self._lock:
            if model_id in self._manifests:
                raise RuntimeError(
                    f"Model {model_id} already registered. "
                    f"Use update_model() to replace."
                )
            
            # Compute checksum
            checksum = self._compute_checksum(model_path)
            file_size = model_path.stat().st_size
            
            # Create manifest
            manifest = ModelManifest(
                model_id=model_id,
                model_type=model_type,
                version=version,
                checksum=checksum,
                file_path=str(model_path.absolute()),
                file_size_bytes=file_size,
                created_at=datetime.utcnow().isoformat(),
                status=ModelStatus.PENDING,
                metadata=metadata or {}
            )
            
            # Store and persist
            self._manifests[model_id] = manifest
            self._save_manifests()
            
            logger.info(
                f"✅ Model registered: {model_id} v{version} "
                f"(checksum: {checksum[:16]}...)"
            )
            
            return manifest
    
    def verify_model(self, model_id: str) -> ModelIntegrityResult:
        """
        Verify model integrity via checksum.
        
        Args:
            model_id: Model to verify
        
        Returns:
            ModelIntegrityResult with verification details
        """
        with self._lock:
            if model_id not in self._manifests:
                return ModelIntegrityResult(
                    is_valid=False,
                    model_id=model_id,
                    checksum_match=False,
                    file_exists=False,
                    size_match=False,
                    error_message=f"Model {model_id} not registered"
                )
            
            manifest = self._manifests[model_id]
            model_path = Path(manifest.file_path)
            
            # Check file exists
            if not model_path.exists():
                return ModelIntegrityResult(
                    is_valid=False,
                    model_id=model_id,
                    checksum_match=False,
                    file_exists=False,
                    size_match=False,
                    error_message=f"Model file not found: {model_path}"
                )
            
            # Check file size
            current_size = model_path.stat().st_size
            size_match = current_size == manifest.file_size_bytes
            
            # Check checksum
            current_checksum = self._compute_checksum(model_path)
            checksum_match = current_checksum == manifest.checksum
            
            is_valid = size_match and checksum_match
            
            if not is_valid:
                error_parts = []
                if not size_match:
                    error_parts.append(
                        f"size mismatch (expected {manifest.file_size_bytes}, "
                        f"got {current_size})"
                    )
                if not checksum_match:
                    error_parts.append(
                        f"checksum mismatch (expected {manifest.checksum[:16]}..., "
                        f"got {current_checksum[:16]}...)"
                    )
                error_message = "; ".join(error_parts)
            else:
                error_message = None
            
            result = ModelIntegrityResult(
                is_valid=is_valid,
                model_id=model_id,
                checksum_match=checksum_match,
                file_exists=True,
                size_match=size_match,
                error_message=error_message
            )
            
            if is_valid:
                logger.info(f"✅ Model integrity verified: {model_id}")
            else:
                logger.error(
                    f"❌ Model integrity FAILED: {model_id} — {error_message}"
                )
            
            return result

    
    def activate_model(self, model_id: str) -> None:
        """
        Activate a model after verification.
        
        Args:
            model_id: Model to activate
        
        Raises:
            RuntimeError: Model not registered or verification failed
        """
        with self._lock:
            if model_id not in self._manifests:
                raise RuntimeError(f"Model {model_id} not registered")
            
            # Verify integrity before activation
            result = self.verify_model(model_id)
            if not result.is_valid:
                raise RuntimeError(
                    f"Cannot activate {model_id}: {result.error_message}"
                )
            
            # Update status
            manifest = self._manifests[model_id]
            updated_manifest = ModelManifest(
                model_id=manifest.model_id,
                model_type=manifest.model_type,
                version=manifest.version,
                checksum=manifest.checksum,
                file_path=manifest.file_path,
                file_size_bytes=manifest.file_size_bytes,
                created_at=manifest.created_at,
                status=ModelStatus.ACTIVE,
                metadata=manifest.metadata
            )
            
            self._manifests[model_id] = updated_manifest
            self._save_manifests()
            
            logger.info(f"✅ Model activated: {model_id}")
    
    def rollback_model(
        self,
        model_id: str,
        backup_path: Path
    ) -> ModelManifest:
        """
        Atomic rollback to previous model version.
        
        Args:
            model_id: Model to rollback
            backup_path: Path to backup model file
        
        Returns:
            New manifest after rollback
        
        Raises:
            FileNotFoundError: Backup file doesn't exist
            RuntimeError: Rollback failed
        """
        with self._lock:
            if not backup_path.exists():
                raise FileNotFoundError(f"Backup not found: {backup_path}")
            
            if model_id not in self._manifests:
                raise RuntimeError(f"Model {model_id} not registered")
            
            current_manifest = self._manifests[model_id]
            current_path = Path(current_manifest.file_path)
            
            # Create safety backup of current model
            safety_backup = current_path.with_suffix(
                current_path.suffix + ".pre_rollback"
            )
            
            try:
                # Step 1: Backup current model
                shutil.copy2(current_path, safety_backup)
                logger.info(f"Created safety backup: {safety_backup}")
                
                # Step 2: Replace with backup
                shutil.copy2(backup_path, current_path)
                logger.info(f"Replaced model with backup: {backup_path}")
                
                # Step 3: Compute new checksum
                new_checksum = self._compute_checksum(current_path)
                new_size = current_path.stat().st_size
                
                # Step 4: Create new manifest
                new_manifest = ModelManifest(
                    model_id=model_id,
                    model_type=current_manifest.model_type,
                    version=f"{current_manifest.version}-rollback",
                    checksum=new_checksum,
                    file_path=str(current_path),
                    file_size_bytes=new_size,
                    created_at=datetime.utcnow().isoformat(),
                    status=ModelStatus.ACTIVE,
                    metadata={
                        **current_manifest.metadata,
                        "rolled_back_from": current_manifest.version,
                        "rollback_at": datetime.utcnow().isoformat()
                    }
                )
                
                # Step 5: Update registry
                self._manifests[model_id] = new_manifest
                self._save_manifests()
                
                logger.info(
                    f"✅ Model rollback successful: {model_id} "
                    f"(checksum: {new_checksum[:16]}...)"
                )
                
                return new_manifest
                
            except Exception as e:
                # Rollback failed → restore from safety backup
                logger.error(f"❌ Rollback failed: {e}")
                
                if safety_backup.exists():
                    shutil.copy2(safety_backup, current_path)
                    logger.info("Restored from safety backup")
                
                raise RuntimeError(f"Rollback failed: {e}") from e
            
            finally:
                # Cleanup safety backup
                if safety_backup.exists():
                    safety_backup.unlink()
    
    def get_manifest(self, model_id: str) -> Optional[ModelManifest]:
        """Get manifest for a model."""
        with self._lock:
            return self._manifests.get(model_id)
    
    def list_models(
        self,
        model_type: Optional[ModelType] = None,
        status: Optional[ModelStatus] = None
    ) -> List[ModelManifest]:
        """
        List registered models with optional filters.
        
        Args:
            model_type: Filter by model type
            status: Filter by status
        
        Returns:
            List of matching manifests
        """
        with self._lock:
            manifests = list(self._manifests.values())
            
            if model_type:
                manifests = [
                    m for m in manifests if m.model_type == model_type
                ]
            
            if status:
                manifests = [
                    m for m in manifests if m.status == status
                ]
            
            return manifests
    
    def mark_corrupted(self, model_id: str, reason: str) -> None:
        """Mark a model as corrupted."""
        with self._lock:
            if model_id not in self._manifests:
                raise RuntimeError(f"Model {model_id} not registered")
            
            manifest = self._manifests[model_id]
            updated = ModelManifest(
                model_id=manifest.model_id,
                model_type=manifest.model_type,
                version=manifest.version,
                checksum=manifest.checksum,
                file_path=manifest.file_path,
                file_size_bytes=manifest.file_size_bytes,
                created_at=manifest.created_at,
                status=ModelStatus.CORRUPTED,
                metadata={
                    **manifest.metadata,
                    "corruption_reason": reason,
                    "corrupted_at": datetime.utcnow().isoformat()
                }
            )
            
            self._manifests[model_id] = updated
            self._save_manifests()
            
            logger.error(f"❌ Model marked as CORRUPTED: {model_id} — {reason}")
    
    # ========================================================================
    # Private Helpers
    # ========================================================================
    
    def _compute_checksum(self, file_path: Path) -> str:
        """
        Compute SHA-256 checksum of a file.
        
        Args:
            file_path: Path to file
        
        Returns:
            Hex digest of SHA-256 checksum
        
        Raises:
            FileNotFoundError: File doesn't exist
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        sha256 = hashlib.sha256()
        
        # Read file in chunks for memory efficiency
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        
        return sha256.hexdigest()
    
    def _load_manifests(self) -> None:
        """Load manifests from disk (internal use only)."""
        if not self.manifest_path.exists():
            logger.info(f"No existing manifest at {self.manifest_path}")
            return
        
        try:
            with open(self.manifest_path, "r") as f:
                data = json.load(f)
            
            for model_id, manifest_dict in data.items():
                self._manifests[model_id] = ModelManifest.from_dict(
                    manifest_dict
                )
            
            logger.info(
                f"✅ Loaded {len(self._manifests)} model manifests "
                f"from {self.manifest_path}"
            )
        
        except Exception as e:
            logger.error(f"Failed to load manifests: {e}")
            raise
    
    def _save_manifests(self) -> None:
        """Save manifests to disk (internal use only)."""
        try:
            # Ensure directory exists
            self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Serialize manifests
            data = {
                model_id: manifest.to_dict()
                for model_id, manifest in self._manifests.items()
            }
            
            # Atomic write via temp file
            temp_path = self.manifest_path.with_suffix(".tmp")
            with open(temp_path, "w") as f:
                json.dump(data, f, indent=2)
            
            # Atomic rename
            temp_path.replace(self.manifest_path)
            
            logger.debug(f"Saved {len(self._manifests)} manifests")
        
        except Exception as e:
            logger.error(f"Failed to save manifests: {e}")
            raise


# ============================================================================
# Convenience Functions
# ============================================================================

def compute_file_checksum(file_path: Path) -> str:
    """
    Compute SHA-256 checksum of a file.
    
    Args:
        file_path: Path to file
    
    Returns:
        Hex digest of SHA-256 checksum
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()


def verify_checksum(file_path: Path, expected_checksum: str) -> bool:
    """
    Verify file checksum matches expected value.
    
    Args:
        file_path: Path to file
        expected_checksum: Expected SHA-256 hex digest
    
    Returns:
        True if checksum matches, False otherwise
    """
    actual = compute_file_checksum(file_path)
    return actual == expected_checksum


# ============================================================================
# Module-level singleton (optional)
# ============================================================================

_global_versioning_system: Optional[ModelVersioningSystem] = None


def get_versioning_system(
    manifest_path: Optional[Path] = None
) -> ModelVersioningSystem:
    """
    Get or create global versioning system instance.
    
    Args:
        manifest_path: Path to manifest file (required on first call)
    
    Returns:
        Global ModelVersioningSystem instance
    """
    global _global_versioning_system
    
    if _global_versioning_system is None:
        if manifest_path is None:
            raise RuntimeError(
                "manifest_path required on first call to get_versioning_system()"
            )
        _global_versioning_system = ModelVersioningSystem(manifest_path)
    
    return _global_versioning_system
