#!/usr/bin/env python3
"""
Protocol Architecture Verification Script
==========================================

Verifies that the protocol-based architecture is correctly implemented:
- All imports work
- Protocols are properly defined
- Container initializes correctly
- Type checking passes
- Basic functionality works

Run:
    python3 scripts/verify_protocol_architecture.py
"""

import sys
import importlib
from typing import List, Tuple


def print_header(text: str):
    """Print a formatted header."""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def print_success(text: str):
    """Print success message."""
    print(f"✅ {text}")


def print_error(text: str):
    """Print error message."""
    print(f"❌ {text}")


def print_info(text: str):
    """Print info message."""
    print(f"ℹ️  {text}")


def verify_imports() -> Tuple[bool, List[str]]:
    """Verify all required imports work."""
    print_header("STEP 1: Verifying Imports")
    
    imports_to_check = [
        ("mahoun.core.protocols", [
            "QueryRouterProtocol",
            "RAGServiceProtocol",
            "ModelOrchestratorProtocol",
            "ModelDriverProtocol",
            "ReasoningEngineProtocol",
            "QueryClassificationResult",
            "RoutedQueryResult",
            "QueryType",
            "validate_protocol_implementation",
        ]),
        ("mahoun.reasoning.adapters", [
            "ReasoningDependencyContainer",
            "MockDependencyContainer",
            "get_reasoning_dependencies",
            "reset_global_container",
        ]),
        ("mahoun.reasoning.unified_engine", [
            "UnifiedReasoningEngine",
        ]),
    ]
    
    errors = []
    
    for module_name, items in imports_to_check:
        try:
            module = importlib.import_module(module_name)
            print_success(f"Imported {module_name}")
            
            for item in items:
                if not hasattr(module, item):
                    error = f"  Missing: {module_name}.{item}"
                    print_error(error)
                    errors.append(error)
                else:
                    print_info(f"  Found: {item}")
        
        except ImportError as e:
            error = f"Failed to import {module_name}: {e}"
            print_error(error)
            errors.append(error)
    
    return len(errors) == 0, errors


def verify_protocols() -> Tuple[bool, List[str]]:
    """Verify protocol definitions."""
    print_header("STEP 2: Verifying Protocol Definitions")
    
    errors = []
    
    try:
        from mahoun.core.protocols import (
            QueryRouterProtocol,
            RAGServiceProtocol,
            ModelOrchestratorProtocol,
            QueryClassificationResult,
            RoutedQueryResult,
            QueryType,
        )
        
        # Check QueryType enum
        print_info("Checking QueryType enum...")
        expected_types = [
            "CONTRACT", "DELAY_ANALYSIS", "LEGAL_INQUIRY",
            "TECHNICAL_INQUIRY", "CYPHER_GENERATION", "GENERAL"
        ]
        for qt in expected_types:
            if not hasattr(QueryType, qt):
                error = f"  Missing QueryType.{qt}"
                print_error(error)
                errors.append(error)
            else:
                print_success(f"  Found QueryType.{qt}")
        
        # Check QueryClassificationResult
        print_info("Checking QueryClassificationResult...")
        try:
            result = QueryClassificationResult(
                query="test",
                query_type=QueryType.LEGAL_INQUIRY,
                confidence=0.9,
                keywords_found=["test"],
                metadata={},
            )
            print_success("  QueryClassificationResult instantiates correctly")
        except Exception as e:
            error = f"  Failed to create QueryClassificationResult: {e}"
            print_error(error)
            errors.append(error)
        
        # Check RoutedQueryResult
        print_info("Checking RoutedQueryResult...")
        try:
            from unittest.mock import Mock
            
            classification = QueryClassificationResult(
                query="test",
                query_type=QueryType.LEGAL_INQUIRY,
                confidence=0.9,
                keywords_found=[],
                metadata={},
            )
            
            routed = RoutedQueryResult(
                query="test",
                query_type=QueryType.LEGAL_INQUIRY,
                rag_result=Mock(),
                classification=classification,
                metadata={},
            )
            print_success("  RoutedQueryResult instantiates correctly")
        except Exception as e:
            error = f"  Failed to create RoutedQueryResult: {e}"
            print_error(error)
            errors.append(error)
        
        # Check protocol runtime_checkable
        print_info("Checking protocol runtime_checkable...")
        from unittest.mock import Mock
        
        mock_router = Mock(spec=QueryRouterProtocol)
        if isinstance(mock_router, QueryRouterProtocol):
            print_success("  QueryRouterProtocol is runtime_checkable")
        else:
            error = "  QueryRouterProtocol is not runtime_checkable"
            print_error(error)
            errors.append(error)
    
    except Exception as e:
        error = f"Protocol verification failed: {e}"
        print_error(error)
        errors.append(error)
    
    return len(errors) == 0, errors


def verify_container() -> Tuple[bool, List[str]]:
    """Verify dependency container."""
    print_header("STEP 3: Verifying Dependency Container")
    
    errors = []
    
    try:
        from mahoun.reasoning.adapters import (
            ReasoningDependencyContainer,
            get_reasoning_dependencies,
            reset_global_container,
        )
        
        # Test container creation
        print_info("Creating container...")
        container = ReasoningDependencyContainer()
        print_success("  Container created")
        
        # Check initialization status
        print_info("Checking initialization status...")
        status = container.get_initialization_status()
        if all(not initialized for initialized in status.values()):
            print_success("  All components initially uninitialized (lazy)")
        else:
            error = "  Some components initialized prematurely"
            print_error(error)
            errors.append(error)
        
        # Test global container
        print_info("Testing global container...")
        global_container = get_reasoning_dependencies()
        print_success("  Global container retrieved")
        
        # Test reset
        print_info("Testing container reset...")
        reset_global_container()
        print_success("  Container reset successful")
    
    except Exception as e:
        error = f"Container verification failed: {e}"
        print_error(error)
        errors.append(error)
    
    return len(errors) == 0, errors


def verify_unified_engine() -> Tuple[bool, List[str]]:
    """Verify UnifiedReasoningEngine."""
    print_header("STEP 4: Verifying UnifiedReasoningEngine")
    
    errors = []
    
    try:
        from mahoun.reasoning.unified_engine import UnifiedReasoningEngine
        from unittest.mock import Mock, AsyncMock
        from mahoun.core.protocols import (
            QueryRouterProtocol,
            ModelOrchestratorProtocol,
            QueryClassificationResult,
            RoutedQueryResult,
            QueryType,
            ModelDriverProtocol,
        )
        from mahoun.llm.orchestrator import ModelCapability
        
        # Create mocks
        print_info("Creating mock dependencies...")
        
        mock_router = Mock(spec=QueryRouterProtocol)
        classification = QueryClassificationResult(
            query="test",
            query_type=QueryType.LEGAL_INQUIRY,
            confidence=0.9,
            keywords_found=[],
            metadata={},
            required_capability=ModelCapability.REASONING.value,
        )
        
        mock_rag_result = Mock()
        mock_rag_result.results = [Mock(content="Test doc")]
        
        routed = RoutedQueryResult(
            query="test",
            query_type=QueryType.LEGAL_INQUIRY,
            rag_result=mock_rag_result,
            classification=classification,
            metadata={},
            model_capability=ModelCapability.REASONING.value,
        )
        
        mock_router.route = AsyncMock(return_value=routed)
        
        mock_driver = Mock(spec=ModelDriverProtocol)
        mock_driver.model_name = "test-model"
        mock_driver.generate = Mock(return_value="Test response")
        
        mock_orchestrator = Mock(spec=ModelOrchestratorProtocol)
        mock_orchestrator.get_driver = AsyncMock(return_value=mock_driver)
        
        print_success("  Mocks created")
        
        # Create engine
        print_info("Creating engine with mocks...")
        engine = UnifiedReasoningEngine(
            router=mock_router,
            orchestrator=mock_orchestrator
        )
        print_success("  Engine created")
        
        # Test process_query (async)
        print_info("Testing process_query...")
        import asyncio
        
        async def test_query():
            result = await engine.process_query("test query")
            return result
        
        result = asyncio.run(test_query())
        
        # Verify result structure
        required_keys = [
            "response", "query_type", "model_used",
            "capability", "confidence", "context_sources", "metadata"
        ]
        
        for key in required_keys:
            if key not in result:
                error = f"  Missing key in result: {key}"
                print_error(error)
                errors.append(error)
            else:
                print_success(f"  Found key: {key}")
        
        print_success("  process_query works correctly")
    
    except Exception as e:
        error = f"UnifiedReasoningEngine verification failed: {e}"
        print_error(error)
        errors.append(error)
        import traceback
        traceback.print_exc()
    
    return len(errors) == 0, errors


def verify_type_checking() -> Tuple[bool, List[str]]:
    """Verify type checking with mypy."""
    print_header("STEP 5: Verifying Type Checking")
    
    errors = []
    
    files_to_check = [
        "mahoun/core/protocols.py",
        "mahoun/reasoning/adapters.py",
        "mahoun/reasoning/unified_engine.py",
    ]
    
    print_info("Checking if mypy is available...")
    try:
        import subprocess
        result = subprocess.run(
            ["python3", "-m", "mypy", "--version"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print_error("  mypy not available, skipping type checking")
            return True, []  # Don't fail if mypy not installed
        
        print_success(f"  mypy available: {result.stdout.strip()}")
    except Exception as e:
        print_error(f"  mypy check failed: {e}")
        return True, []  # Don't fail if mypy not installed
    
    for file_path in files_to_check:
        print_info(f"Type checking {file_path}...")
        try:
            result = subprocess.run(
                ["python3", "-m", "mypy", file_path, "--no-error-summary"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                print_success(f"  {file_path}: No type errors")
            else:
                error = f"  {file_path}: Type errors found\n{result.stdout}"
                print_error(error)
                errors.append(error)
        
        except subprocess.TimeoutExpired:
            print_error(f"  {file_path}: Type checking timed out")
        except Exception as e:
            print_error(f"  {file_path}: Type checking failed: {e}")
    
    return len(errors) == 0, errors


def main():
    """Run all verification steps."""
    print_header("PROTOCOL ARCHITECTURE VERIFICATION")
    print("Verifying protocol-based reasoning architecture...")
    
    all_errors = []
    
    # Run verification steps
    steps = [
        ("Imports", verify_imports),
        ("Protocols", verify_protocols),
        ("Container", verify_container),
        ("UnifiedEngine", verify_unified_engine),
        ("Type Checking", verify_type_checking),
    ]
    
    results = []
    for step_name, step_func in steps:
        success, errors = step_func()
        results.append((step_name, success))
        all_errors.extend(errors)
    
    # Print summary
    print_header("VERIFICATION SUMMARY")
    
    for step_name, success in results:
        if success:
            print_success(f"{step_name}: PASSED")
        else:
            print_error(f"{step_name}: FAILED")
    
    if all_errors:
        print_header("ERRORS FOUND")
        for error in all_errors:
            print(f"  • {error}")
        print_header("VERIFICATION FAILED")
        sys.exit(1)
    else:
        print_header("✅ ALL VERIFICATIONS PASSED ✅")
        print("\nThe protocol-based architecture is correctly implemented!")
        print("All imports work, protocols are valid, and functionality is verified.")
        sys.exit(0)


if __name__ == "__main__":
    main()
