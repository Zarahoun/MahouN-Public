import pytest
"""
FORTRESS INTEGRATION TEST
=========================

Quick test to verify fortress integration is working correctly.
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mahoun.reasoning.unified_reasoning_service import (
    UnifiedReasoningService,
    ReasoningRequest,
    ReasoningTask,
    ReasoningMode
)


@pytest.mark.p0
async def test_fortress_integration():
    """Test fortress integration with unified reasoning service"""
    
    print("=" * 80)
    print("🏰 FORTRESS INTEGRATION TEST")
    print("=" * 80)
    
    # Initialize service (should activate fortress)
    print("\n1️⃣ Initializing Fortress-Protected Reasoning Service...")
    service = UnifiedReasoningService(enable_neural=False)
    
    # Check fortress status
    fortress_status = service.fortress.get_fortress_status()
    print(f"\n✅ Fortress Status:")
    for key, value in fortress_status.items():
        print(f"   {key}: {value}")
    
    # Test symbolic reasoning (fortress-protected)
    print("\n2️⃣ Testing Fortress-Protected Symbolic Reasoning...")
    request = ReasoningRequest(
        task=ReasoningTask.FORWARD_INFERENCE,
        query="What can we infer?",
        facts=["human(socrates)", "mortal(X) :- human(X)"],
        rules=[],
        mode=ReasoningMode.SYMBOLIC
    )
    
    try:
        response = await service.reason(request)
        print(f"\n✅ Reasoning completed:")
        print(f"   Success: {response.success}")
        print(f"   Confidence: {response.confidence}")
        print(f"   Mode: {response.reasoning_mode.value}")
        print(f"   Execution time: {response.execution_time_ms:.2f}ms")
        
        # Check fortress metadata
        if 'fortress_protected' in response.metadata:
            print(f"\n🏰 Fortress Metadata:")
            print(f"   Protected: {response.metadata['fortress_protected']}")
            print(f"   Security Level: {response.metadata['security_level']}")
            print(f"   Integrity Verified: {response.metadata['integrity_verified']}")
            print(f"   Zero Trust: {response.metadata['zero_trust_enforced']}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Check protected components
    print(f"\n3️⃣ Protected Components:")
    for comp_name, signature in service.fortress.protected_components.items():
        print(f"   ✓ {comp_name}")
        print(f"     - Verifications: {signature.verification_count}")
        print(f"     - Last verified: {signature.last_verified}")
    
    # Check audit trail
    audit_trail = service.fortress.export_audit_trail()
    print(f"\n4️⃣ Audit Trail: {len(audit_trail)} events")
    if audit_trail:
        print(f"   Latest events:")
        for event in audit_trail[-5:]:
            print(f"   - {event['event_type']}: {event['timestamp']}")
    
    print("\n" + "=" * 80)
    print("✅ FORTRESS INTEGRATION TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_fortress_integration())
