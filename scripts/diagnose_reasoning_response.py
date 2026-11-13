#!/usr/bin/env python3
"""
ReasoningResponse TypeError Diagnostic Script
==============================================

Purpose: Diagnose the "TypeError: Any cannot be instantiated" error at
         mahoun/reasoning/verdict_engine_adapter.py:384,477

This script traces the import resolution path for ReasoningResponse and
documents the root cause with evidence.

Requirements: R1 (Eliminate P0 Execution Blockers)
Task: 1.1 Investigate ReasoningResponse TypeError root cause
"""

import sys
from pathlib import Path
from typing import Any

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

print("=" * 80)
print("ReasoningResponse TypeError Diagnostic")
print("=" * 80)
print()

# ============================================================================
# TEST 1: Check what fortress_validator exports
# ============================================================================

print("TEST 1: Checking fortress_validator.py ReasoningResponse import")
print("-" * 80)

from mahoun.core import fortress_validator

# Check what ReasoningResponse resolves to in fortress_validator
rr_from_fortress = getattr(fortress_validator, 'ReasoningResponse', None)
print(f"ReasoningResponse from fortress_validator: {rr_from_fortress}")
print(f"Type: {type(rr_from_fortress)}")
print(f"Is it typing.Any? {rr_from_fortress is Any}")

if rr_from_fortress is Any:
    print("❌ ROOT CAUSE CONFIRMED: ReasoningResponse = Any at runtime")
    print("   Location: mahoun/core/fortress_validator.py:40-43")
    print("   Reason: TYPE_CHECKING guard sets ReasoningResponse = Any in else branch")
else:
    print("✅ ReasoningResponse is correctly typed")

print()

# ============================================================================
# TEST 2: Check actual ReasoningResponse class location
# ============================================================================

print("TEST 2: Locating actual ReasoningResponse class definition")
print("-" * 80)

try:
    from mahoun.reasoning.unified_reasoning_service import ReasoningResponse as ActualRR
    print(f"Actual ReasoningResponse class: {ActualRR}")
    print(f"Module: {ActualRR.__module__}")
    print(f"Type: {type(ActualRR)}")
    print(f"Is dataclass? {hasattr(ActualRR, '__dataclass_fields__')}")
    print("✅ Actual class found at mahoun.reasoning.unified_reasoning_service.ReasoningResponse")
except ImportError as e:
    print(f"❌ Could not import actual ReasoningResponse: {e}")

print()

# ============================================================================
# TEST 3: Demonstrate the TypeError
# ============================================================================

print("TEST 3: Reproducing the TypeError")
print("-" * 80)

# This is what verdict_engine_adapter.py does at lines 384 and 477
try:
    # Import the way adapter does it
    from mahoun.core.fortress_validator import ReasoningResponse
    
    print(f"Attempting to instantiate: {ReasoningResponse}")
    
    # Try to create an instance (this should fail with TypeError if ReasoningResponse = Any)
    response = ReasoningResponse(
        success=True,
        result="test",
        confidence=0.9,
        reasoning_mode=None,
        execution_time_ms=100.0,
        proof_tree=None,
        derived_facts=[],
        metadata={}
    )
    print("✅ Instantiation succeeded (unexpected!)")
    print(f"   Created: {response}")
    
except TypeError as e:
    print(f"❌ TypeError occurred: {e}")
    print("   This is the P0 blocker affecting 9+ API integration tests")

print()

# ============================================================================
# TEST 4: Import resolution path analysis
# ============================================================================

print("TEST 4: Import resolution path analysis")
print("-" * 80)

print("Import chain:")
print("1. mahoun/reasoning/verdict_engine_adapter.py:47")
print("   → from mahoun.core.fortress_validator import ReasoningResponse")
print()
print("2. mahoun/core/fortress_validator.py:35-43")
print("   → if TYPE_CHECKING:")
print("       from mahoun.reasoning.unified_reasoning_service import ReasoningResponse")
print("     else:")
print("       ReasoningResponse = Any  ← RUNTIME FALLBACK (ROOT CAUSE)")
print()
print("3. Result at runtime:")
print("   → ReasoningResponse resolves to typing.Any")
print("   → Any cannot be instantiated")
print("   → TypeError: Any cannot be instantiated")

print()

# ============================================================================
# SUMMARY AND RECOMMENDATIONS
# ============================================================================

print("=" * 80)
print("DIAGNOSTIC SUMMARY")
print("=" * 80)
print()

print("ROOT CAUSE:")
print("-" * 80)
print("File: mahoun/core/fortress_validator.py")
print("Lines: 40-43")
print()
print("Problematic code:")
print("  if TYPE_CHECKING:")
print("      from mahoun.reasoning.unified_reasoning_service import ReasoningResponse")
print("  else:")
print("      ReasoningResponse = Any  # ← This runs at runtime")
print()
print("The TYPE_CHECKING constant is True only during static type checking (mypy).")
print("At runtime, TYPE_CHECKING is False, so the else branch executes,")
print("setting ReasoningResponse = Any instead of importing the actual class.")
print()

print("EVIDENCE:")
print("-" * 80)
print(f"1. fortress_validator.ReasoningResponse is Any: {rr_from_fortress is Any}")
print("2. Actual class exists at: mahoun.reasoning.unified_reasoning_service.ReasoningResponse")
print("3. verdict_engine_adapter.py imports from fortress_validator (gets Any)")
print("4. Lines 384 and 477 attempt ReasoningResponse(...) which fails with TypeError")
print()

print("IMPACT:")
print("-" * 80)
print("- 9+ API integration tests blocked")
print("- test_generate_verdict_success FAILED")
print("- Concurrent validator tests may be affected")
print()

print("RECOMMENDED FIX:")
print("-" * 80)
print("Option 1: Direct import in fortress_validator.py (RECOMMENDED)")
print("  Change lines 40-43 to:")
print("  from mahoun.reasoning.unified_reasoning_service import ReasoningResponse")
print("  (Remove TYPE_CHECKING guard)")
print()
print("Option 2: Change adapter import path")
print("  In verdict_engine_adapter.py line 47:")
print("  from mahoun.reasoning.unified_reasoning_service import ReasoningResponse")
print("  (Bypass fortress_validator)")
print()
print("Option 3: Use late binding in fortress_validator")
print("  Create a getter function that imports ReasoningResponse on first use")
print()

print("=" * 80)
print("Diagnostic complete - evidence documented")
print("=" * 80)
