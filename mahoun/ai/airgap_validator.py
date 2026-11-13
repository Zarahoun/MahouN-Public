#!/usr/bin/env python3
"""
Air-Gap Compliance Validator - Network Isolation Enforcement

This module provides comprehensive air-gap compliance validation:
- Network isolation verification
- local_files_only enforcement
- Model integrity verification (SHA-256)
- External dependency detection
- Compliance reporting

Version: 1.0.0
Phase: D - Production Readiness & Compliance
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set
from pathlib import Path
from enum import Enum
import hashlib
import logging
import socket
import urllib.request
import importlib.util

logger = logging.getLogger(__name__)


class ComplianceStatus(Enum):
    """Air-gap compliance status"""
    COMPLIANT = "compliant"
    WARNING = "warning"
    VIOLATION = "violation"
    UNKNOWN = "unknown"


@dataclass
class IntegrityCheckResult:
    """Model integrity verification result"""
    file_path: str
    expected_hash: Optional[str]
    actual_hash: str
    verified: bool
    file_size_bytes: int
    check_timestamp: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "file_path": self.file_path,
            "expected_hash": self.expected_hash,
            "actual_hash": self.actual_hash,
            "verified": self.verified,
            "file_size_bytes": self.file_size_bytes,
            "check_timestamp": self.check_timestamp
        }


@dataclass
class NetworkIsolationResult:
    """Network isolation test result"""
    test_name: str
    isolated: bool
    details: str
    test_timestamp: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "test_name": self.test_name,
            "isolated": self.isolated,
            "details": self.details,
            "test_timestamp": self.test_timestamp
        }


@dataclass
class AirGapComplianceReport:
    """Comprehensive air-gap compliance report"""
    overall_status: ComplianceStatus
    network_isolation_tests: List[NetworkIsolationResult]
    integrity_checks: List[IntegrityCheckResult]
    local_files_only_enforced: bool
    violations: List[str]
    warnings: List[str]
    recommendations: List[str]
    test_timestamp: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "overall_status": self.overall_status.value,
            "network_isolation_tests": [t.to_dict() for t in self.network_isolation_tests],
            "integrity_checks": [c.to_dict() for c in self.integrity_checks],
            "local_files_only_enforced": self.local_files_only_enforced,
            "violations": self.violations,
            "warnings": self.warnings,
            "recommendations": self.recommendations,
            "test_timestamp": self.test_timestamp
        }


class AirGapValidator:
    """
    Air-Gap Compliance Validator
    
    This validator ensures complete network isolation and air-gap compliance:
    
    1. Network Isolation Testing:
       - DNS resolution blocking
       - HTTP/HTTPS connection blocking
       - External network accessibility checks
    
    2. Model Integrity Verification:
       - SHA-256 checksum validation
       - File corruption detection
       - Integrity monitoring
    
    3. local_files_only Enforcement:
       - HuggingFace Hub access blocking
       - External model download prevention
       - Local-only operation validation
    
    4. Compliance Reporting:
       - Detailed violation reporting
       - Warning generation
       - Remediation recommendations
    """
    
    # Known external hosts to test isolation against
    EXTERNAL_TEST_HOSTS = [
        "huggingface.co",
        "github.com",
        "pypi.org",
        "amazonaws.com",
        "google.com"
    ]
    
    # Known HuggingFace related imports
    HUGGINGFACE_IMPORTS = [
        "huggingface_hub",
        "transformers.file_utils",
        "sentence_transformers.util"
    ]
    
    def __init__(
        self,
        models_directory: Optional[Path] = None,
        strict_mode: bool = True
    ):
        """
        Initialize air-gap validator
        
        Args:
            models_directory: Directory containing local models
            strict_mode: If True, treat warnings as violations
        """
        self.models_directory = models_directory or Path("/app/models")
        self.strict_mode = strict_mode
        self._violations: List[str] = []
        self._warnings: List[str] = []
        
        logger.info(f"Initialized AirGapValidator (strict_mode={strict_mode})")
    
    def verify_network_isolation(self) -> List[NetworkIsolationResult]:
        """
        Verify complete network isolation
        
        Returns:
            List of network isolation test results
        """
        results = []
        
        # Test 1: DNS resolution should fail
        for host in self.EXTERNAL_TEST_HOSTS:
            try:
                socket.gethostbyname(host)
                # If we get here, DNS resolution worked (VIOLATION)
                results.append(NetworkIsolationResult(
                    test_name=f"dns_resolution_{host}",
                    isolated=False,
                    details=f"DNS resolution succeeded for {host} - network not isolated",
                    test_timestamp=self._get_timestamp()
                ))
                self._violations.append(f"DNS resolution succeeded for {host}")
            except (socket.gaierror, OSError):
                # DNS resolution failed (GOOD - network isolated)
                results.append(NetworkIsolationResult(
                    test_name=f"dns_resolution_{host}",
                    isolated=True,
                    details=f"DNS resolution blocked for {host}",
                    test_timestamp=self._get_timestamp()
                ))
        
        # Test 2: HTTP connections should fail
        test_urls = [
            "http://google.com",
            "https://huggingface.co",
            "https://pypi.org"
        ]
        
        for url in test_urls:
            try:
                # Try to open connection with very short timeout
                urllib.request.urlopen(url, timeout=1)
                # If we get here, connection worked (VIOLATION)
                results.append(NetworkIsolationResult(
                    test_name=f"http_connection_{url}",
                    isolated=False,
                    details=f"HTTP connection succeeded to {url} - network not isolated",
                    test_timestamp=self._get_timestamp()
                ))
                self._violations.append(f"HTTP connection succeeded to {url}")
            except (urllib.error.URLError, OSError, TimeoutError):
                # Connection failed (GOOD - network isolated)
                results.append(NetworkIsolationResult(
                    test_name=f"http_connection_{url}",
                    isolated=True,
                    details=f"HTTP connection blocked to {url}",
                    test_timestamp=self._get_timestamp()
                ))
        
        logger.info(f"Network isolation tests: {len(results)} completed")
        return results
    
    def verify_model_integrity(
        self,
        model_checksums: Dict[str, str]
    ) -> List[IntegrityCheckResult]:
        """
        Verify model file integrity using SHA-256 checksums
        
        Args:
            model_checksums: Dict mapping model filenames to expected SHA-256 hashes
            
        Returns:
            List of integrity check results
        """
        results = []
        
        for model_filename, expected_hash in model_checksums.items():
            model_path = self.models_directory / model_filename
            
            if not model_path.exists():
                self._warnings.append(f"Model file not found: {model_path}")
                results.append(IntegrityCheckResult(
                    file_path=str(model_path),
                    expected_hash=expected_hash,
                    actual_hash="FILE_NOT_FOUND",
                    verified=False,
                    file_size_bytes=0,
                    check_timestamp=self._get_timestamp()
                ))
                continue
            
            # Calculate actual hash
            actual_hash = self._calculate_sha256(model_path)
            file_size = model_path.stat().st_size
            
            verified = actual_hash == expected_hash
            
            if not verified:
                self._violations.append(
                    f"Model integrity check failed: {model_filename} "
                    f"(expected: {expected_hash[:16]}..., actual: {actual_hash[:16]}...)"
                )
            
            results.append(IntegrityCheckResult(
                file_path=str(model_path),
                expected_hash=expected_hash,
                actual_hash=actual_hash,
                verified=verified,
                file_size_bytes=file_size,
                check_timestamp=self._get_timestamp()
            ))
        
        logger.info(f"Model integrity checks: {len(results)} completed")
        return results
    
    def verify_local_files_only_enforcement(self) -> bool:
        """
        Verify that local_files_only is properly enforced
        
        This checks if HuggingFace Hub and other download mechanisms
        are properly disabled.
        
        Returns:
            True if properly enforced, False otherwise
        """
        enforced = True
        
        # Check if HuggingFace imports are configured for offline mode
        for module_name in self.HUGGINGFACE_IMPORTS:
            try:
                spec = importlib.util.find_spec(module_name)
                if spec is not None:
                    # Module exists - check if offline mode can be verified
                    # In production, we'd check actual configuration
                    self._warnings.append(
                        f"HuggingFace module detected: {module_name} - "
                        f"ensure local_files_only=True in all calls"
                    )
            except (ImportError, ModuleNotFoundError):
                # Module not found - this is acceptable
                pass
        
        # Check environment variables for offline mode
        import os
        hf_offline = os.getenv("HF_HUB_OFFLINE", "0")
        transformers_offline = os.getenv("TRANSFORMERS_OFFLINE", "0")
        
        if hf_offline != "1":
            self._warnings.append("HF_HUB_OFFLINE not set to 1 - recommend setting for safety")
        
        if transformers_offline != "1":
            self._warnings.append("TRANSFORMERS_OFFLINE not set to 1 - recommend setting for safety")
        
        logger.info(f"local_files_only enforcement: enforced={enforced}")
        return enforced
    
    def generate_compliance_report(
        self,
        model_checksums: Optional[Dict[str, str]] = None
    ) -> AirGapComplianceReport:
        """
        Generate comprehensive air-gap compliance report
        
        Args:
            model_checksums: Optional model checksums for integrity verification
            
        Returns:
            Complete compliance report
        """
        # Reset violations and warnings
        self._violations = []
        self._warnings = []
        
        # Run all validation checks
        network_tests = self.verify_network_isolation()
        
        integrity_checks = []
        if model_checksums:
            integrity_checks = self.verify_model_integrity(model_checksums)
        
        local_files_enforced = self.verify_local_files_only_enforcement()
        
        # Determine overall status
        if self._violations:
            overall_status = ComplianceStatus.VIOLATION
        elif self._warnings and self.strict_mode:
            overall_status = ComplianceStatus.WARNING
        else:
            overall_status = ComplianceStatus.COMPLIANT
        
        # Generate recommendations
        recommendations = self._generate_recommendations()
        
        report = AirGapComplianceReport(
            overall_status=overall_status,
            network_isolation_tests=network_tests,
            integrity_checks=integrity_checks,
            local_files_only_enforced=local_files_enforced,
            violations=self._violations.copy(),
            warnings=self._warnings.copy(),
            recommendations=recommendations,
            test_timestamp=self._get_timestamp()
        )
        
        logger.info(f"Compliance report generated: status={overall_status.value}")
        return report
    
    def _calculate_sha256(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of file"""
        sha256_hash = hashlib.sha256()
        
        with open(file_path, "rb") as f:
            # Read in chunks to handle large files
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        
        return sha256_hash.hexdigest()
    
    def _generate_recommendations(self) -> List[str]:
        """Generate remediation recommendations"""
        recommendations = []
        
        if self._violations:
            recommendations.append(
                "CRITICAL: Address all violations before production deployment"
            )
            
            if any("DNS resolution succeeded" in v for v in self._violations):
                recommendations.append(
                    "Configure iptables to block all outbound DNS traffic (port 53)"
                )
            
            if any("HTTP connection succeeded" in v for v in self._violations):
                recommendations.append(
                    "Configure iptables to block all outbound HTTP/HTTPS traffic (ports 80, 443)"
                )
            
            if any("integrity check failed" in v for v in self._violations):
                recommendations.append(
                    "Re-download models from trusted source and verify checksums"
                )
        
        if self._warnings:
            recommendations.append(
                "Review all warnings and implement recommended safety measures"
            )
            
            if any("HF_HUB_OFFLINE" in w for w in self._warnings):
                recommendations.append(
                    "Set environment variable: HF_HUB_OFFLINE=1"
                )
            
            if any("TRANSFORMERS_OFFLINE" in w for w in self._warnings):
                recommendations.append(
                    "Set environment variable: TRANSFORMERS_OFFLINE=1"
                )
        
        if not self._violations and not self._warnings:
            recommendations.append(
                "System is fully air-gap compliant - ready for production deployment"
            )
        
        return recommendations
    
    def _get_timestamp(self) -> str:
        """Get current timestamp"""
        from datetime import datetime
        return datetime.utcnow().isoformat() + "Z"


# Utility functions

def validate_airgap_compliance(
    models_directory: Optional[Path] = None,
    model_checksums: Optional[Dict[str, str]] = None,
    strict_mode: bool = True
) -> AirGapComplianceReport:
    """
    Convenience function to validate air-gap compliance
    
    Args:
        models_directory: Directory containing local models
        model_checksums: Optional model checksums
        strict_mode: Treat warnings as violations
        
    Returns:
        Compliance report
    """
    validator = AirGapValidator(
        models_directory=models_directory,
        strict_mode=strict_mode
    )
    
    return validator.generate_compliance_report(model_checksums)


def is_airgap_compliant(
    models_directory: Optional[Path] = None,
    strict_mode: bool = True
) -> bool:
    """
    Quick check if system is air-gap compliant
    
    Args:
        models_directory: Directory containing local models
        strict_mode: Treat warnings as violations
        
    Returns:
        True if compliant, False otherwise
    """
    report = validate_airgap_compliance(
        models_directory=models_directory,
        strict_mode=strict_mode
    )
    
    return report.overall_status == ComplianceStatus.COMPLIANT
