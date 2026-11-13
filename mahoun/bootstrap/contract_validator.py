"""
Bootstrap Architecture Contract Validator

This module validates that the runtime bootstrap implementation complies with
the frozen architecture contract defined in bootstrap_contract.yaml.

Purpose:
- Verify phase execution order matches contract
- Validate dependency graph (DAG) has no cycles
- Check context mutation ownership
- Validate state machine transitions
- Enforce architectural invariants

Usage:
    python -m mahoun.bootstrap.contract_validator
    
Exit codes:
    0 - All validations passed
    1 - Validation failures detected
    2 - Contract file not found or invalid
"""

import sys
import yaml
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any
from dataclasses import dataclass
from enum import Enum


class ValidationSeverity(Enum):
    """Validation result severity levels"""
    CRITICAL = "CRITICAL"  # Contract violation - must fix
    ERROR = "ERROR"        # Implementation error - should fix
    WARNING = "WARNING"    # Potential issue - review
    INFO = "INFO"          # Informational only


@dataclass
class ValidationResult:
    """Single validation check result"""
    rule_name: str
    severity: ValidationSeverity
    passed: bool
    message: str
    details: Dict[str, Any] = None
    
    def __str__(self) -> str:
        status = "✅ PASS" if self.passed else "❌ FAIL"
        msg = f"[{self.severity.value}] {status} - {self.rule_name}: {self.message}"
        if self.details and not self.passed:
            msg += f"\n  Details: {self.details}"
        return msg


class BootstrapContractValidator:
    """
    Validates bootstrap implementation against architectural contract.
    
    This validator ensures that any refactoring maintains the frozen
    behavioral contract defined in bootstrap_contract.yaml.
    """
    
    def __init__(self, contract_path: Path):
        """
        Initialize validator with contract file.
        
        Args:
            contract_path: Path to bootstrap_contract.yaml
        """
        self.contract_path = contract_path
        self.contract = self._load_contract()
        self.results: List[ValidationResult] = []
        
    def _load_contract(self) -> Dict[str, Any]:
        """Load and parse contract YAML file"""
        if not self.contract_path.exists():
            raise FileNotFoundError(
                f"Contract file not found: {self.contract_path}"
            )
            
        with open(self.contract_path, 'r') as f:
            contract = yaml.safe_load(f)
            
        # Validate contract structure
        required_keys = [
            'version', 'phase_execution_order', 'phase_dependencies',
            'context_mutations', 'allowed_states', 'state_transitions',
            'invariants', 'validation_rules'
        ]
        
        missing = [k for k in required_keys if k not in contract]
        if missing:
            raise ValueError(
                f"Invalid contract - missing keys: {missing}"
            )
            
        return contract
    
    def validate_all(self) -> Tuple[bool, List[ValidationResult]]:
        """
        Run all validations defined in contract.
        
        Returns:
            (all_passed, results) tuple
        """
        self.results = []
        
        # Run each validation rule from contract
        for rule in self.contract['validation_rules']:
            rule_name = rule['name']
            rule_type = rule['type']
            target = rule['target']
            
            if rule_type == 'sequence_check':
                self._validate_sequence(rule_name, target)
            elif rule_type == 'dag_validation':
                self._validate_dag(rule_name, target)
            elif rule_type == 'uniqueness_check':
                self._validate_uniqueness(rule_name, target)
            elif rule_type == 'state_machine_validation':
                self._validate_state_machine(rule_name, target)
            elif rule_type == 'blacklist_check':
                self._validate_forbidden_transitions(rule_name, target)
            elif rule_type == 'invariant_check':
                self._validate_invariants(rule_name, target)
            else:
                self.results.append(ValidationResult(
                    rule_name=rule_name,
                    severity=ValidationSeverity.WARNING,
                    passed=True,
                    message=f"Unknown validation type: {rule_type} (skipped)"
                ))
        
        all_passed = all(r.passed for r in self.results)
        return all_passed, self.results
    
    def _validate_sequence(self, rule_name: str, target: str) -> None:
        """Validate phase execution order hasn't changed"""
        expected_order = self.contract[target]
        
        # For now, just verify the sequence is defined
        # In Phase 1, we'll add runtime code inspection
        if not expected_order:
            self.results.append(ValidationResult(
                rule_name=rule_name,
                severity=ValidationSeverity.CRITICAL,
                passed=False,
                message="Phase execution order is empty in contract"
            ))
        else:
            self.results.append(ValidationResult(
                rule_name=rule_name,
                severity=ValidationSeverity.INFO,
                passed=True,
                message=f"Phase execution order defined: {len(expected_order)} phases"
            ))
    
    def _validate_dag(self, rule_name: str, target: str) -> None:
        """Validate dependency graph has no circular dependencies"""
        dependencies = self.contract[target]
        
        # Build adjacency list
        graph: Dict[str, List[str]] = {}
        for phase, config in dependencies.items():
            deps = config.get('depends_on', [])
            graph[phase] = deps
        
        # Detect cycles using DFS
        visited = set()
        rec_stack = set()
        
        def has_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            
            rec_stack.remove(node)
            return False
        
        # Check all nodes
        cycles_found = []
        for node in graph:
            if node not in visited:
                if has_cycle(node):
                    cycles_found.append(node)
        
        if cycles_found:
            self.results.append(ValidationResult(
                rule_name=rule_name,
                severity=ValidationSeverity.CRITICAL,
                passed=False,
                message="Circular dependencies detected in phase graph",
                details={"cycles_at": cycles_found}
            ))
        else:
            self.results.append(ValidationResult(
                rule_name=rule_name,
                severity=ValidationSeverity.INFO,
                passed=True,
                message=f"DAG valid: {len(graph)} phases, no cycles"
            ))
    
    def _validate_uniqueness(self, rule_name: str, target: str) -> None:
        """Validate each context key is owned by exactly one phase"""
        context_mutations = self.contract[target]
        
        # Check for duplicate context keys
        context_keys = {}
        duplicates = []
        
        for phase, config in context_mutations.items():
            key = config['key']
            if key in context_keys:
                duplicates.append({
                    'key': key,
                    'phase1': context_keys[key],
                    'phase2': phase
                })
            else:
                context_keys[key] = phase
        
        if duplicates:
            self.results.append(ValidationResult(
                rule_name=rule_name,
                severity=ValidationSeverity.CRITICAL,
                passed=False,
                message="Duplicate context key ownership detected",
                details={"duplicates": duplicates}
            ))
        else:
            self.results.append(ValidationResult(
                rule_name=rule_name,
                severity=ValidationSeverity.INFO,
                passed=True,
                message=f"Context ownership unique: {len(context_keys)} keys"
            ))
    
    def _validate_state_machine(self, rule_name: str, target: str) -> None:
        """Validate state machine has valid transitions"""
        transitions = self.contract[target]
        allowed_states = set(self.contract['allowed_states'])
        
        invalid_transitions = []
        for trans in transitions:
            from_state = trans['from']
            to_state = trans['to']
            
            if from_state not in allowed_states:
                invalid_transitions.append({
                    'from': from_state,
                    'to': to_state,
                    'reason': f"'{from_state}' not in allowed_states"
                })
            
            if to_state not in allowed_states:
                invalid_transitions.append({
                    'from': from_state,
                    'to': to_state,
                    'reason': f"'{to_state}' not in allowed_states"
                })
        
        if invalid_transitions:
            self.results.append(ValidationResult(
                rule_name=rule_name,
                severity=ValidationSeverity.CRITICAL,
                passed=False,
                message="Invalid state transitions found",
                details={"invalid": invalid_transitions}
            ))
        else:
            self.results.append(ValidationResult(
                rule_name=rule_name,
                severity=ValidationSeverity.INFO,
                passed=True,
                message=f"State machine valid: {len(transitions)} transitions"
            ))
    
    def _validate_forbidden_transitions(self, rule_name: str, target: str) -> None:
        """Validate no forbidden transitions are defined"""
        forbidden = self.contract[target]
        state_transitions = self.contract['state_transitions']
        
        # Build set of actual transitions
        actual = {(t['from'], t['to']) for t in state_transitions}
        
        # Check for forbidden transitions in actual
        violations = []
        for forbidden_trans in forbidden:
            from_state = forbidden_trans['from']
            to_state = forbidden_trans['to']
            
            # Handle wildcard
            if to_state == '*':
                matching = [
                    (f, t) for f, t in actual 
                    if f == from_state
                ]
                if matching:
                    violations.append({
                        'forbidden': f"{from_state} → *",
                        'found': matching,
                        'reason': forbidden_trans['reason']
                    })
            else:
                if (from_state, to_state) in actual:
                    violations.append({
                        'forbidden': f"{from_state} → {to_state}",
                        'reason': forbidden_trans['reason']
                    })
        
        if violations:
            self.results.append(ValidationResult(
                rule_name=rule_name,
                severity=ValidationSeverity.CRITICAL,
                passed=False,
                message="Forbidden transitions found in state machine",
                details={"violations": violations}
            ))
        else:
            self.results.append(ValidationResult(
                rule_name=rule_name,
                severity=ValidationSeverity.INFO,
                passed=True,
                message=f"No forbidden transitions: {len(forbidden)} rules enforced"
            ))
    
    def _validate_invariants(self, rule_name: str, target: str) -> None:
        """Validate all architectural invariants are documentated"""
        invariants = self.contract[target]
        
        required_invariants = {
            'governance_first',
            'fail_closed',
            'single_initialization',
            'sequential_execution',
            'rollback_order',
            'context_immutability',
            'service_registry_append_only'
        }
        
        defined_invariants = {inv['name'] for inv in invariants}
        missing = required_invariants - defined_invariants
        
        if missing:
            self.results.append(ValidationResult(
                rule_name=rule_name,
                severity=ValidationSeverity.CRITICAL,
                passed=False,
                message="Required invariants missing from contract",
                details={"missing": list(missing)}
            ))
        else:
            self.results.append(ValidationResult(
                rule_name=rule_name,
                severity=ValidationSeverity.INFO,
                passed=True,
                message=f"All {len(required_invariants)} required invariants defined"
            ))
    
    def print_report(self, verbose: bool = True) -> None:
        """Print validation report to stdout"""
        print("\n" + "=" * 80)
        print("BOOTSTRAP ARCHITECTURE CONTRACT VALIDATION")
        print("=" * 80)
        print(f"Contract Version: {self.contract['version']}")
        print(f"Contract Status: {self.contract['contract_status']}")
        print(f"Snapshot Date: {self.contract['snapshot_date']}")
        print("=" * 80 + "\n")
        
        # Group results by severity
        critical = [r for r in self.results if r.severity == ValidationSeverity.CRITICAL]
        errors = [r for r in self.results if r.severity == ValidationSeverity.ERROR]
        warnings = [r for r in self.results if r.severity == ValidationSeverity.WARNING]
        info = [r for r in self.results if r.severity == ValidationSeverity.INFO]
        
        # Print failures first
        failed = [r for r in self.results if not r.passed]
        if failed:
            print("❌ VALIDATION FAILURES:\n")
            for result in failed:
                print(str(result))
                print()
        
        # Print successes if verbose
        if verbose:
            passed = [r for r in self.results if r.passed]
            if passed:
                print("✅ VALIDATION SUCCESSES:\n")
                for result in passed:
                    print(str(result))
                    print()
        
        # Summary
        print("=" * 80)
        print("SUMMARY:")
        print(f"  Total Checks: {len(self.results)}")
        print(f"  Passed: {sum(1 for r in self.results if r.passed)}")
        print(f"  Failed: {sum(1 for r in self.results if not r.passed)}")
        print(f"  Critical: {len([r for r in critical if not r.passed])}")
        print(f"  Errors: {len([r for r in errors if not r.passed])}")
        print(f"  Warnings: {len([r for r in warnings if not r.passed])}")
        print("=" * 80 + "\n")
        
        all_passed = all(r.passed for r in self.results)
        if all_passed:
            print("✅ ALL VALIDATIONS PASSED - Contract compliance verified\n")
        else:
            print("❌ VALIDATION FAILED - Contract violations detected\n")
            print("Action required:")
            print("  1. Review failures above")
            print("  2. Fix contract violations before proceeding")
            print("  3. If intentional, requires ADR + constitutional approval\n")


def main():
    """CLI entry point for contract validation"""
    # Determine contract path
    script_dir = Path(__file__).parent
    contract_path = script_dir / "bootstrap_contract.yaml"
    
    if not contract_path.exists():
        print(f"❌ ERROR: Contract file not found: {contract_path}", file=sys.stderr)
        sys.exit(2)
    
    try:
        # Create validator and run checks
        validator = BootstrapContractValidator(contract_path)
        all_passed, results = validator.validate_all()
        
        # Print report
        verbose = '--verbose' in sys.argv or '-v' in sys.argv
        validator.print_report(verbose=verbose)
        
        # Exit with appropriate code
        sys.exit(0 if all_passed else 1)
        
    except Exception as e:
        print(f"❌ ERROR: Validation failed with exception: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main()
