#!/usr/bin/env python3
"""
HAJIX Verification Script
==========================

Verifies the integrity and consistency of the refactored codebase.
Updated to support async tool calls.
"""

import sys
import os
import asyncio
from pathlib import Path

# Add HAJIX to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def check_module_imports():
    """Check that key modules can be imported."""
    print("=== Module Import Check ===")
    
    modules_to_check = [
        ("mahoun", "MAHOUN package"),
        ("mahoun.mcp", "MCP package"),
        ("mahoun.mcp.registry", "MCP Registry"),
        ("mahoun.mcp.tools", "MCP Tools"),
        ("mahoun.core", "Core package"), 
        # Note: Agents/Pipelines seem to have moved or are different in this version, check directory structure first
    ]
    
    success_count = 0
    for module_name, description in modules_to_check:
        try:
            __import__(module_name)
            print(f"  ✓ {description}: {module_name}")
            success_count += 1
        except ImportError as e:
            print(f"  ✗ {description}: {module_name} - {e}")
    
    print(f"\nImported {success_count}/{len(modules_to_check)} modules")
    return success_count == len(modules_to_check)


def check_tools_registry():
    """Check MCP tools registry."""
    print("\n=== MCP Tools Registry Check ===")
    
    try:
        from mahoun.mcp.registry import TOOLS
        
        expected_tools = ["Graph", "RAG", "Ingest", "Maintenance", "System"]
        
        for tool_name in expected_tools:
            if tool_name in TOOLS:
                tool = TOOLS[tool_name]
                methods = [m for m in dir(tool) if not m.startswith("_")]
                print(f"  ✓ {tool_name}: {methods}")
            else:
                print(f"  ✗ {tool_name}: NOT FOUND")
                return False
        
        return True
        
    except ImportError as e:
        print(f"  ✗ Failed to import registry: {e}")
        return False


async def check_tool_functionality_async():
    """Check that tools actually work (Async version)."""
    print("\n=== Tool Functionality Check ===")
    
    try:
        from mahoun.mcp.registry import TOOLS
        
        # Test Graph tool
        graph_tool = TOOLS["Graph"]
        # Check if async
        if asyncio.iscoroutinefunction(graph_tool.get_graph_summary):
             summary = await graph_tool.get_graph_summary()
        else:
             summary = graph_tool.get_graph_summary()
        print(f"  ✓ Graph.get_graph_summary(): {summary}")
        
        # Test RAG tool
        rag_tool = TOOLS["RAG"]
        if asyncio.iscoroutinefunction(rag_tool.hybrid_search):
            results = await rag_tool.hybrid_search("test query")
        else:
            results = rag_tool.hybrid_search("test query")
            
        # Handle different return types if needed
        count = 0
        if isinstance(results, dict):
            count = len(results.get('results', []))
        elif isinstance(results, list):
            count = len(results)
            
        print(f"  ✓ RAG.hybrid_search(): {count} results")
        
        # Test System tool
        sys_tool = TOOLS["System"]
        if asyncio.iscoroutinefunction(sys_tool.health_check):
            health = await sys_tool.health_check()
        else:
            health = sys_tool.health_check()
        print(f"  ✓ System.health_check(): {health}")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Tool test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_directory_structure():
    """Check that expected directories exist."""
    print("\n=== Directory Structure Check ===")
    
    base = Path(__file__).parent
    
    expected_dirs = [
        "mahoun",
        "mahoun/mcp",
        "mahoun/mcp/tools",
        "mahoun/core",
        "mahoun/pipelines",
        "mahoun/guardrails",
        "mahoun/reasoning",
    ]
    
    all_exist = True
    for dir_name in expected_dirs:
        dir_path = base / dir_name
        if dir_path.exists():
            print(f"  ✓ {dir_name}/")
        else:
            print(f"  ✗ {dir_name}/ - NOT FOUND")
            all_exist = False
    
    return all_exist


async def main_async():
    print("=" * 60)
    print("HAJIX VERIFICATION SCRIPT (ASYNC)")
    print("=" * 60)
    
    results = []
    
    results.append(("Directory Structure", check_directory_structure()))
    results.append(("Module Imports", check_module_imports()))
    results.append(("Tools Registry", check_tools_registry()))
    
    # Run async tool check
    results.append(("Tool Functionality", await check_tool_functionality_async()))
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print("✓ ALL CHECKS PASSED")
        return 0
    else:
        print("✗ SOME CHECKS FAILED")
        return 1

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    sys.exit(main())
