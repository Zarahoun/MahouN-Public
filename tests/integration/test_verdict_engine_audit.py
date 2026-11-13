import pytest
import asyncio
from unittest.mock import AsyncMock
from mahoun.reasoning.evidence_linked_verdict import EvidenceLinkedVerdictEngine
from mahoun.reasoning.knowledge_graph import LegalKnowledgeGraph
from mahoun.graph.ultra_graph_builder import UltraGraphBuilder
from mahoun.reasoning.unified_reasoning_service import ReasoningMode, ReasoningResponse
from mahoun.core.fortress_validator import FortressValidator, ExecutionMode

@pytest.fixture
def base_kg():
    kg = LegalKnowledgeGraph(enable_semantic=False)
    kg.add_legal_rule(
        rule_id="rule_contract_1",
        condition="breach of contract",
        conclusion="liable for damages",
        confidence=0.9
    )
    return kg

@pytest.fixture
def mock_engine(base_kg):
    graph_builder = UltraGraphBuilder()
    ledger_writer = AsyncMock()
    
    engine = EvidenceLinkedVerdictEngine(
        graph_builder=graph_builder,
        knowledge_graph=base_kg,
        ledger_writer=ledger_writer
    )
    # Mock ledger write to avoid blockchain/backend requirements
    engine._write_ledger_entry_async = AsyncMock(return_value="mock_hash_123")
    return engine

@pytest.mark.asyncio
@pytest.mark.p0
async def test_audit_provenance_truncation(mock_engine):
    """
    AUDIT FINDING: Provenance Loss
    Verifies that rich source metadata is truncated during graph construction.
    """
    rich_facts = [
        {"id": "doc_123", "value": "Client committed a breach of contract", "source_metadata": "doc_123_v1"}
    ]
    
    verdict = await mock_engine.generate_verdict(
        question="Is the client liable?",
        facts=rich_facts
    )
    
    # Assert provenance loss
    provenance_preserved = False
    for step in verdict.steps:
        for ev in step.evidence:
            if hasattr(ev, 'properties') and 'source_metadata' in ev.properties:
                provenance_preserved = True
                
    assert not provenance_preserved, "Audit proved: Provenance (source_metadata) is truncated from evidence!"
    
    # Assert that at least the text was preserved
    assert len(verdict.steps) > 0

@pytest.mark.asyncio
@pytest.mark.p0
async def test_audit_rule_traceability(mock_engine):
    """
    AUDIT FINDING: Rule Traceability
    Verifies that the verdict actually links back to the specific rule used.
    """
    facts = ["Client committed a breach of contract"]
    verdict = await mock_engine.generate_verdict(
        question="Is the client liable?",
        facts=facts
    )
    
    # Find if the rule_contract_1 was actually explicitly linked in the evidence
    rule_linked = False
    for step in verdict.steps:
        for ev in step.evidence:
            if ev.node_type == "LegalRule" and "rule_contract_1" in ev.node_id:
                rule_linked = True
                
    assert rule_linked, "Audit failed: Rule traceability is broken. Verdict doesn't link to rule_contract_1."

@pytest.mark.asyncio
@pytest.mark.p0
async def test_audit_unsupported_conclusion_prevention(mock_engine):
    """
    AUDIT FINDING: Unsupported Conclusion Prevention
    Verifies that the engine blocks verdict generation without facts.
    """
    with pytest.raises(RuntimeError) as exc_info:
        await mock_engine.generate_verdict(
            question="Is the client liable?",
            facts=[]
        )
        
    assert "without evidence" in str(exc_info.value), "Audit failed: Engine generated verdict without facts!"

@pytest.mark.asyncio
@pytest.mark.p0
async def test_audit_graph_construction(mock_engine):
    """
    AUDIT FINDING: Graph Construction Integrity
    Verifies that the internal graph building actually creates nodes and edges.
    """
    facts = ["Fact 1", "Fact 2"]
    edge_state = {"counter": 0, "id_map": {}}
    
    nodes, edges = mock_engine._build_case_graph(facts, edge_state)
    
    assert len(nodes) == 2, f"Expected 2 nodes, got {len(nodes)}"
    assert len(edges) == 1, f"Expected 1 sequential edge between facts, got {len(edges)}"
    assert edges[0].source_id == "fact_0"
    assert edges[0].target_id == "fact_1"

@pytest.mark.asyncio
@pytest.mark.p0
async def test_audit_conflict_resolution(mock_engine, base_kg):
    """
    AUDIT FINDING: Conflict Resolution
    Injects a contradictory rule and verifies how the engine resolves it.
    """
    # Add a contradictory rule
    base_kg.add_legal_rule(
        rule_id="rule_contract_2",
        condition="breach of contract",
        conclusion="NOT liable for damages",
        confidence=0.9
    )
    
    facts = ["Client committed a breach of contract"]
    verdict = await mock_engine.generate_verdict(
        question="Is the client liable?",
        facts=facts
    )
    
    has_unresolved = len(verdict.unresolved_conflicts) > 0
    
    assert has_unresolved, "Governance Fix: Contradiction was correctly flagged as unresolved."
    assert verdict.final_verdict == "UNDETERMINED", "Governance Fix: Unresolved conflicts correctly trigger UNDETERMINED verdict."

@pytest.mark.asyncio
@pytest.mark.p0
async def test_audit_citation_traceability():
    """
    AUDIT FINDING: R-07 Citation Traceability
    Verifies that rules without explicit source citations fail closed.
    """
    # Create rule without source
    kg = LegalKnowledgeGraph(enable_semantic=False)
    kg.add_legal_rule(
        rule_id="rule_contract_no_source",
        condition="breach of contract",
        conclusion="liable for damages",
        confidence=0.9
    )
    
    graph_builder = UltraGraphBuilder()
    ledger_writer = AsyncMock()
    
    mock_engine = EvidenceLinkedVerdictEngine(
        graph_builder=graph_builder,
        knowledge_graph=kg,
        ledger_writer=ledger_writer
    )
    mock_engine._write_ledger_entry_async = AsyncMock(return_value="mock_hash_123")
    
    facts = ["Client committed a breach of contract"]
    verdict = await mock_engine.generate_verdict(
        question="Is the client liable?",
        facts=facts
    )
    
    from mahoun.reasoning.verdict_engine_adapter import VerdictEngineAdapter
    from mahoun.core.fortress_validator import FortressValidator
    
    adapter = VerdictEngineAdapter(mock_engine)
    response = adapter._transform_verdict_to_response(verdict, "test_1", 10.0)
    
    validator = FortressValidator(strict_mode=True)
    with pytest.raises(Exception) as exc_info:
        await validator.validate(response)
        
    assert "Citation Traceability Violation" in str(exc_info.value), "Audit passed: Validator failed closed when source citation was missing."

@pytest.mark.asyncio
@pytest.mark.p0
async def test_audit_neural_bypass_governance_catch():
    """
    AUDIT FINDING: Neural Bypass Governance Check
    Verifies that FortressValidator blocks missing proof trees even in NEURAL mode,
    preventing the ReasoningResponse unvalidated bypass.
    """
    validator = FortressValidator(execution_mode=ExecutionMode.ENTERPRISE_FULL, strict_mode=False)
    
    # Create an unvalidated neural response with NO proof tree
    mock_neural = ReasoningResponse.create_unvalidated(
        success=True,
        result="Fallback verdict",
        confidence=0.8,
        reasoning_mode=ReasoningMode.NEURAL,
        execution_time_ms=100.0,
        proof_tree=None,
        derived_facts=["synthetic_fact_1"],
        metadata={"agreement_score": 0.9}
    )
    
    neural_validation = await validator.validate(mock_neural)
    
    # Verify that FortressValidator DOES catch it with a CRITICAL violation!
    has_critical_proof_block = any(
        v["severity"] == "CRITICAL" and v["type"] == "MISSING_PROOF_TREE" 
        for v in neural_validation.violations
    )
    assert has_critical_proof_block, "FortressValidator should block missing proof trees even in NEURAL mode!"
