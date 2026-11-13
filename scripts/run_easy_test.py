#!/usr/bin/env python3
"""Direct test runner to debug"""
import sys
import asyncio
sys.path.insert(0, '.')

# Import test function
from tests.bootstrap.characterization.scenarios.embedding_success_easy import test_embedding_executor_easy_success

print("=" * 80)
print("RUNNING EASY TEST DIRECTLY")
print("=" * 80)

async def main():
    try:
        result = await test_embedding_executor_easy_success()
        print("\n✅ TEST PASSED")
        print(f"   Snapshot: {result}")
        return 0
    except Exception as e:
        print(f"\n❌ TEST FAILED: {type(e).__name__}")
        print(f"   Message: {e}")
        import traceback
        traceback.print_exc()
        return 1

exit_code = asyncio.run(main())
sys.exit(exit_code)
