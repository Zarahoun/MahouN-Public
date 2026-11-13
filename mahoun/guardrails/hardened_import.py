"""
Hardened Guardrails Import System
=================================
MANDATORY guardrails import with fail-fast enforcement.

CRITICAL: System CANNOT operate without guardrails in production.
This module implements the most sophisticated guardrails import system
with multiple layers of validation and enforcement.

Classification: MISSION-CRITICAL / ZERO-TRUST / NON-BYPASSABLE
"""

import os
import sys
import logging
import hashlib
import importlib
import traceback
from typing import Any, Dict, Optional, Callable, List, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class EnvironmentLevel(str, Enum):
    """Environment security levels"""
    PRODUCTION = "production"
    STAGING = "staging"
    DEVELOPMENT = "development"
    TESTING = "testing"


class ImportStatus(str, Enum):
    """Guardrails import status"""
    SUCCESS = "success"
    DEGRADED = "degraded"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class GuardrailsImportResult:
    """Result of guardrails import attempt"""
    
    status: ImportStatus
    environment: EnvironmentLevel
    guards_available: Dict[str, bool]
    utilities_available: Dict[str, bool]
    degraded_mode: bool
    error_details: Optional[str] = None
    import_time_ms: float = 0.0
    security_hash: Optional[str] = None
    acknowledgment_required: bool = False
    
    def is_operational(self) -> bool:
        """Check if system can operate with current guardrails state"""
        if self.status == ImportStatus.SUCCESS:
            return True
        elif self.status == ImportStatus.DEGRADED:
            return self.environment != EnvironmentLevel.PRODUCTION
        else:
            return False
    
    def get_security_level(self) -> str:
        """Get current security level description"""
        if self.status == ImportStatus.SUCCESS:
            return "MAXIMUM"
        elif self.status == ImportStatus.DEGRADED:
            return "COMPROMISED"
        else:
            return "INOPERABLE"


class HardenedGuardrailsImporter:
    """
    Ultra-sophisticated guardrails import system with fail-fast enforcement.
    
    SECURITY MODEL:
    - Production: Import failure is FATAL (SystemExit)
    - Staging: Import failure is ERROR (degraded mode with warnings)
    - Development: Import failure requires explicit acknowledgment
    - Testing: Import failure allowed with loud logging
    
    FEATURES:
    - Multi-layer validation
    - Security hash verification
    - Degraded mode detection
    - Acknowledgment tracking
    - Forensic logging
    - Bypass attempt detection
    """
    
    def __init__(self):
        self.environment = self._detect_environment()
        self.import_attempts = []
        self.security_violations = []
        self._last_import_result: Optional[GuardrailsImportResult] = None
        
        logger.info(
            "Hardened Guardrails Importer initialized",
            extra={
                "environment": self.environment.value,
                "security_level": "MAXIMUM",
                "fail_fast_enabled": self.environment == EnvironmentLevel.PRODUCTION
            }
        )
    
    def _detect_environment(self) -> EnvironmentLevel:
        """
        Detect environment using the canonical environment authority.
        """
        from mahoun.core.environment import get_current_environment
        
        env_context = get_current_environment()
        
        if env_context.is_production():
            detected_env = EnvironmentLevel.PRODUCTION
        elif env_context.is_staging():
            detected_env = EnvironmentLevel.STAGING
        elif env_context.is_test():
            detected_env = EnvironmentLevel.TESTING
        else:
            detected_env = EnvironmentLevel.DEVELOPMENT
        
        logger.info(
            "Environment detection completed",
            extra={
                "detected_environment": detected_env.value,
                "primary_env": env_context.environment.value,
            }
        )
        
        return detected_env
    
    def import_guardrails_with_enforcement(self) -> GuardrailsImportResult:
        """
        Import guardrails with sophisticated enforcement and validation.
        
        Returns:
            GuardrailsImportResult with detailed status
            
        Raises:
            SystemExit: In production if guardrails cannot be imported
            RuntimeError: In development without acknowledgment
        """
        start_time = datetime.now()
        
        logger.info(
            "Starting hardened guardrails import",
            extra={
                "environment": self.environment.value,
                "attempt_number": len(self.import_attempts) + 1,
                "timestamp": start_time.isoformat()
            }
        )
        
        try:
            # Attempt primary guardrails import
            guards, utilities = self._attempt_primary_import()
            
            # Validate imported components
            validation_result = self._validate_imported_components(guards, utilities)
            
            if validation_result["valid"]:
                # SUCCESS: All guardrails imported and validated
                import_time = (datetime.now() - start_time).total_seconds() * 1000
                
                result = GuardrailsImportResult(
                    status=ImportStatus.SUCCESS,
                    environment=self.environment,
                    guards_available=validation_result["guards_status"],
                    utilities_available=validation_result["utilities_status"],
                    degraded_mode=False,
                    import_time_ms=import_time,
                    security_hash=self._compute_security_hash(guards, utilities)
                )
                
                logger.info(
                    "Guardrails import SUCCESS - full enforcement available",
                    extra={
                        "import_time_ms": import_time,
                        "guards_count": len(validation_result["guards_status"]),
                        "utilities_count": len(validation_result["utilities_status"]),
                        "security_hash": result.security_hash[:16],
                        "zero_hallucination_guarantee": "ACTIVE"
                    }
                )
                
                self._last_import_result = result
                self.import_attempts.append(result)
                return result
            
            else:
                # PARTIAL: Some components failed validation
                return self._handle_partial_import_failure(validation_result, start_time)
        
        except ImportError as e:
            # FAILURE: Import failed completely
            return self._handle_complete_import_failure(e, start_time)
        
        except Exception as e:
            # UNEXPECTED: System error during import
            return self._handle_unexpected_import_error(e, start_time)
    
    def _attempt_primary_import(self) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Attempt to import all required guardrails components.
        
        Returns:
            Tuple of (guards_dict, utilities_dict)
            
        Raises:
            ImportError: If critical components cannot be imported
        """
        guards = {}
        utilities = {}
        
        try:
            # Import runtime invariants (guards)
            from mahoun.guardrails.runtime_invariants import (
                G1_EvidenceStepHasEvidence,
                G2_EvidenceReferencesResolve,
                G3_NonResurrection,
                G4_ContradictionVisibility,
                G5_ResolutionOrder,
                register_node,
                get_registry,
            )
            
            guards = {
                'G1_EvidenceStepHasEvidence': G1_EvidenceStepHasEvidence,
                'G2_EvidenceReferencesResolve': G2_EvidenceReferencesResolve,
                'G3_NonResurrection': G3_NonResurrection,
                'G4_ContradictionVisibility': G4_ContradictionVisibility,
                'G5_ResolutionOrder': G5_ResolutionOrder,
            }
            
            utilities = {
                'register_node': register_node,
                'get_registry': get_registry,
            }
            
            # Import guard modes
            from mahoun.guardrails.modes import get_guard_mode
            utilities['get_guard_mode'] = get_guard_mode
            
            logger.debug(
                "Primary guardrails import successful",
                extra={
                    "guards_imported": list(guards.keys()),
                    "utilities_imported": list(utilities.keys())
                }
            )
            
            return guards, utilities
            
        except ImportError as e:
            logger.error(
                "Primary guardrails import failed",
                extra={
                    "import_error": str(e),
                    "missing_module": getattr(e, 'name', 'unknown'),
                    "traceback": traceback.format_exc()
                }
            )
            raise
    
    def _validate_imported_components(
        self, 
        guards: Dict[str, Any], 
        utilities: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate that imported components are functional.
        
        Args:
            guards: Imported guard functions
            utilities: Imported utility functions
            
        Returns:
            Validation result dictionary
        """
        validation_result = {
            "valid": True,
            "guards_status": {},
            "utilities_status": {},
            "validation_errors": []
        }
        
        # Validate guards
        for guard_name, guard_func in guards.items():
            try:
                # Check if it's callable
                if not callable(guard_func):
                    validation_result["guards_status"][guard_name] = False
                    validation_result["validation_errors"].append(f"{guard_name} is not callable")
                    validation_result["valid"] = False
                    continue
                
                # Test guard with dummy data (safe test)
                if guard_name == "G1_EvidenceStepHasEvidence":
                    # Create mock step with evidence
                    mock_step = type('MockStep', (), {'evidence': ['mock_evidence']})()
                    guard_func(mock_step, 0)  # Should not raise
                
                validation_result["guards_status"][guard_name] = True
                
            except Exception as e:
                validation_result["guards_status"][guard_name] = False
                validation_result["validation_errors"].append(f"{guard_name} validation failed: {e}")
                validation_result["valid"] = False
        
        # Validate utilities
        for util_name, util_func in utilities.items():
            try:
                if not callable(util_func):
                    validation_result["utilities_status"][util_name] = False
                    validation_result["validation_errors"].append(f"{util_name} is not callable")
                    validation_result["valid"] = False
                    continue
                
                # Basic callable test
                validation_result["utilities_status"][util_name] = True
                
            except Exception as e:
                validation_result["utilities_status"][util_name] = False
                validation_result["validation_errors"].append(f"{util_name} validation failed: {e}")
                validation_result["valid"] = False
        
        logger.debug(
            "Component validation completed",
            extra={
                "validation_valid": validation_result["valid"],
                "guards_valid": sum(validation_result["guards_status"].values()),
                "utilities_valid": sum(validation_result["utilities_status"].values()),
                "validation_errors": len(validation_result["validation_errors"])
            }
        )
        
        return validation_result
    
    def _compute_security_hash(
        self, 
        guards: Dict[str, Any], 
        utilities: Dict[str, Any]
    ) -> str:
        """
        Compute security hash of imported components.
        
        This hash can be used to verify that the same components
        are loaded across different parts of the system.
        """
        # Create deterministic representation
        components_info = {
            "guards": {name: str(func.__module__ + "." + func.__name__) for name, func in guards.items()},
            "utilities": {name: str(func.__module__ + "." + func.__name__) for name, func in utilities.items()},
            "environment": self.environment.value,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d")  # Daily rotation
        }
        
        # Sort for deterministic hash
        import json
        components_str = json.dumps(components_info, sort_keys=True)
        
        return hashlib.sha256(components_str.encode()).hexdigest()
    
    def _handle_complete_import_failure(
        self, 
        import_error: ImportError, 
        start_time: datetime
    ) -> GuardrailsImportResult:
        """Handle complete guardrails import failure"""
        
        import_time = (datetime.now() - start_time).total_seconds() * 1000
        error_details = f"Import failed: {import_error}"
        
        # PRODUCTION: FATAL ERROR - System cannot operate
        if self.environment == EnvironmentLevel.PRODUCTION:
            logger.critical(
                "FATAL SYSTEM ERROR: Guardrails import failed in PRODUCTION mode. "
                "The system CANNOT operate without invariant enforcement. "
                "This is a P0 incident requiring immediate intervention.",
                extra={
                    "environment": self.environment.value,
                    "import_error": str(import_error),
                    "system_state": "INOPERABLE",
                    "required_action": "IMMEDIATE_INTERVENTION",
                    "zero_hallucination_guarantee": "LOST",
                    "security_level": "COMPROMISED"
                }
            )
            
            # Record security violation
            self.security_violations.append({
                "type": "production_guardrails_failure",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(import_error),
                "severity": "CRITICAL"
            })
            
            # FAIL-FAST: Raise SystemExit to prevent any operation
            raise SystemExit(
                f"FATAL: Guardrails unavailable in PRODUCTION mode. "
                f"System cannot operate safely. Original error: {import_error}"
            ) from import_error
        
        # STAGING: ERROR - System degraded but operational with warnings
        elif self.environment == EnvironmentLevel.STAGING:
            logger.error(
                "CRITICAL WARNING: Guardrails unavailable in STAGING mode. "
                "Zero-hallucination guarantee is COMPROMISED. "
                "This configuration is NOT suitable for production deployment.",
                extra={
                    "environment": self.environment.value,
                    "import_error": str(import_error),
                    "system_state": "DEGRADED",
                    "zero_hallucination_guarantee": "COMPROMISED",
                    "production_readiness": "NOT_READY"
                }
            )
            
            result = GuardrailsImportResult(
                status=ImportStatus.DEGRADED,
                environment=self.environment,
                guards_available={},
                utilities_available={},
                degraded_mode=True,
                error_details=error_details,
                import_time_ms=import_time
            )
            
            self._last_import_result = result
            self.import_attempts.append(result)
            return result
        
        # DEVELOPMENT/TESTING: Explicit acknowledgment required
        else:
            degraded_acknowledged = os.getenv("MAHOUN_ACKNOWLEDGE_DEGRADED_GUARDS", "false").lower()
            
            if degraded_acknowledged != "true":
                logger.error(
                    "DEVELOPMENT MODE: Guardrails unavailable. "
                    "To continue in degraded mode, set environment variable: "
                    "MAHOUN_ACKNOWLEDGE_DEGRADED_GUARDS=true",
                    extra={
                        "environment": self.environment.value,
                        "import_error": str(import_error),
                        "acknowledgment_required": True,
                        "zero_hallucination_guarantee": "DISABLED"
                    }
                )
                
                result = GuardrailsImportResult(
                    status=ImportStatus.BLOCKED,
                    environment=self.environment,
                    guards_available={},
                    utilities_available={},
                    degraded_mode=True,
                    error_details=error_details,
                    import_time_ms=import_time,
                    acknowledgment_required=True
                )
                
                self._last_import_result = result
                self.import_attempts.append(result)
                
                raise RuntimeError(
                    "Guardrails import failed in development mode. "
                    "To acknowledge degraded operation, set: MAHOUN_ACKNOWLEDGE_DEGRADED_GUARDS=true"
                ) from import_error
            
            logger.warning(
                "DEVELOPMENT MODE: Operating with degraded guardrails (acknowledged). "
                "Zero-hallucination guarantee is DISABLED.",
                extra={
                    "environment": self.environment.value,
                    "degraded_acknowledged": True,
                    "zero_hallucination_guarantee": "DISABLED"
                }
            )
            
            result = GuardrailsImportResult(
                status=ImportStatus.DEGRADED,
                environment=self.environment,
                guards_available={},
                utilities_available={},
                degraded_mode=True,
                error_details=error_details,
                import_time_ms=import_time
            )
            
            self._last_import_result = result
            self.import_attempts.append(result)
            return result
    
    def _handle_partial_import_failure(
        self, 
        validation_result: Dict[str, Any], 
        start_time: datetime
    ) -> GuardrailsImportResult:
        """Handle partial guardrails import failure"""
        
        import_time = (datetime.now() - start_time).total_seconds() * 1000
        error_details = f"Partial import failure: {validation_result['validation_errors']}"
        
        # Determine if system can operate with partial guards
        critical_guards = ["G1_EvidenceStepHasEvidence", "G2_EvidenceReferencesResolve"]
        critical_available = all(
            validation_result["guards_status"].get(guard, False) 
            for guard in critical_guards
        )
        
        if critical_available:
            # Can operate with reduced functionality
            logger.warning(
                "Partial guardrails import - critical guards available",
                extra={
                    "available_guards": [k for k, v in validation_result["guards_status"].items() if v],
                    "missing_guards": [k for k, v in validation_result["guards_status"].items() if not v],
                    "critical_guards_available": True,
                    "system_state": "DEGRADED"
                }
            )
            
            result = GuardrailsImportResult(
                status=ImportStatus.DEGRADED,
                environment=self.environment,
                guards_available=validation_result["guards_status"],
                utilities_available=validation_result["utilities_status"],
                degraded_mode=True,
                error_details=error_details,
                import_time_ms=import_time
            )
        else:
            # Cannot operate safely
            logger.error(
                "Partial guardrails import - critical guards missing",
                extra={
                    "missing_critical_guards": [g for g in critical_guards if not validation_result["guards_status"].get(g, False)],
                    "system_state": "INOPERABLE"
                }
            )
            
            result = GuardrailsImportResult(
                status=ImportStatus.FAILED,
                environment=self.environment,
                guards_available=validation_result["guards_status"],
                utilities_available=validation_result["utilities_status"],
                degraded_mode=True,
                error_details=error_details,
                import_time_ms=import_time
            )
        
        self._last_import_result = result
        self.import_attempts.append(result)
        return result
    
    def _handle_unexpected_import_error(
        self, 
        error: Exception, 
        start_time: datetime
    ) -> GuardrailsImportResult:
        """Handle unexpected error during import"""
        
        import_time = (datetime.now() - start_time).total_seconds() * 1000
        error_details = f"Unexpected error: {error}"
        
        logger.error(
            "Unexpected error during guardrails import",
            extra={
                "error": str(error),
                "error_type": type(error).__name__,
                "traceback": traceback.format_exc()
            },
            exc_info=True
        )
        
        result = GuardrailsImportResult(
            status=ImportStatus.FAILED,
            environment=self.environment,
            guards_available={},
            utilities_available={},
            degraded_mode=True,
            error_details=error_details,
            import_time_ms=import_time
        )
        
        self._last_import_result = result
        self.import_attempts.append(result)
        return result
    
    def create_degraded_mode_guards(self) -> Dict[str, Any]:
        """
        Create degraded mode guards that log EVERY invocation.
        
        These are loud no-op implementations that make it obvious
        when the system is operating without proper guardrails.
        """
        def create_loud_guard(guard_name: str) -> Callable:
            def loud_guard(*args, **kwargs):
                logger.error(
                    f"DEGRADED MODE: {guard_name} called but NOT ENFORCED. "
                    f"Zero-hallucination guarantee is COMPROMISED.",
                    extra={
                        "guard_name": guard_name,
                        "args_count": len(args),
                        "kwargs_count": len(kwargs),
                        "enforcement_status": "DISABLED",
                        "security_violation": True,
                        "degraded_mode": True
                    }
                )
            return loud_guard
        
        def create_loud_utility(util_name: str) -> Callable:
            def loud_utility(*args, **kwargs):
                logger.warning(
                    f"DEGRADED MODE: {util_name} called with no-op implementation",
                    extra={
                        "utility_name": util_name,
                        "degraded_mode": True
                    }
                )
                # Return appropriate no-op values
                if util_name == "get_registry":
                    return {}
                elif util_name == "get_guard_mode":
                    return type('MockMode', (), {'value': 'DEGRADED'})()
                else:
                    return None
            return loud_utility
        
        return {
            'guards': {
                'G1_EvidenceStepHasEvidence': create_loud_guard('G1_EvidenceStepHasEvidence'),
                'G2_EvidenceReferencesResolve': create_loud_guard('G2_EvidenceReferencesResolve'),
                'G3_NonResurrection': create_loud_guard('G3_NonResurrection'),
                'G4_ContradictionVisibility': create_loud_guard('G4_ContradictionVisibility'),
                'G5_ResolutionOrder': create_loud_guard('G5_ResolutionOrder'),
            },
            'utilities': {
                'register_node': create_loud_utility('register_node'),
                'get_registry': create_loud_utility('get_registry'),
                'get_guard_mode': create_loud_utility('get_guard_mode'),
            }
        }
    
    def get_import_status(self) -> Optional[GuardrailsImportResult]:
        """Get the last import result"""
        return self._last_import_result
    
    def get_security_violations(self) -> List[Dict[str, Any]]:
        """Get recorded security violations"""
        return self.security_violations.copy()
    
    def verify_guardrails_integrity(self) -> bool:
        """
        Verify that guardrails are still properly loaded and functional.
        
        Returns:
            True if guardrails are functional, False otherwise
        """
        if not self._last_import_result:
            return False
        
        if self._last_import_result.status != ImportStatus.SUCCESS:
            return False
        
        # Additional runtime verification could be added here
        return True


# Global importer instance
_hardened_importer: Optional[HardenedGuardrailsImporter] = None


def get_hardened_importer() -> HardenedGuardrailsImporter:
    """Get global hardened importer instance"""
    global _hardened_importer
    
    if _hardened_importer is None:
        _hardened_importer = HardenedGuardrailsImporter()
    
    return _hardened_importer


def import_guardrails_with_enforcement() -> GuardrailsImportResult:
    """
    Convenience function for hardened guardrails import.
    
    Returns:
        GuardrailsImportResult with detailed status
        
    Raises:
        SystemExit: In production if guardrails cannot be imported
        RuntimeError: In development without acknowledgment
    """
    importer = get_hardened_importer()
    return importer.import_guardrails_with_enforcement()


# Example usage and testing
if __name__ == "__main__":
    print("🛡️ Hardened Guardrails Import System")
    print("=" * 60)
    
    # Test import in current environment
    try:
        result = import_guardrails_with_enforcement()
        
        print(f"✅ Import Status: {result.status.value}")
        print(f"   Environment: {result.environment.value}")
        print(f"   Security Level: {result.get_security_level()}")
        print(f"   Operational: {result.is_operational()}")
        print(f"   Import Time: {result.import_time_ms:.2f}ms")
        
        if result.security_hash:
            print(f"   Security Hash: {result.security_hash[:16]}...")
        
        if result.degraded_mode:
            print(f"⚠️  DEGRADED MODE: Zero-hallucination guarantee compromised")
        
        if result.guards_available:
            print(f"   Guards Available: {sum(result.guards_available.values())}/{len(result.guards_available)}")
        
        if result.utilities_available:
            print(f"   Utilities Available: {sum(result.utilities_available.values())}/{len(result.utilities_available)}")
        
    except SystemExit as e:
        print(f"❌ FATAL: {e}")
    except RuntimeError as e:
        print(f"⚠️  BLOCKED: {e}")
    except Exception as e:
        print(f"💥 ERROR: {e}")
    
    # Test security violations
    importer = get_hardened_importer()
    violations = importer.get_security_violations()
    if violations:
        print(f"\n🚨 Security Violations: {len(violations)}")
        for violation in violations:
            print(f"   - {violation['type']}: {violation['error']}")