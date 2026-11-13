import pytest
import asyncio
from mahoun.metrics import get_metrics_collector
from mahoun.monitoring.legal_metrics import legal_monitoring
from mahoun.reasoning.evidence_linked_verdict import EvidenceLinkedVerdictEngine
from mahoun.graph.ultra_graph_builder import UltraGraphBuilder
from mahoun.reasoning.knowledge_graph import LegalKnowledgeGraph
from mahoun.ledger.writer import create_ledger_writer


@pytest.fixture
def collector():
    # Make sure we start with a clean slate
    c = get_metrics_collector()
    c.reset_all()
    legal_monitoring.reset()
    yield c
    c.reset_all()


@pytest.mark.asyncio
@pytest.mark.p2
async def test_unified_metrics_collection_after_verdict(collector):
    """
    Integration test asserting that the unified metrics collector
    successfully tracks system metrics and legal-specific business metrics
    when the evidence_linked_verdict engine generates a verdict.
    """

    # 1. Initialize the engine with mock backends
    graph_builder = UltraGraphBuilder()
    kg = LegalKnowledgeGraph()
    ledger = create_ledger_writer(backend_type="noop")

    engine = EvidenceLinkedVerdictEngine(
        graph_builder=graph_builder, knowledge_graph=kg, ledger_writer=ledger
    )

    # 2. Assert metrics are initially empty/zero
    initial_metrics = collector.get_all_metrics()
    assert initial_metrics.get("legal_query_throughput_total", 0) == 0
    assert initial_metrics.get("legal_query_latency_seconds_count", 0) == 0

    # 3. Simulate a legal query verdict generation
    question = "Is this contract valid?"
    facts = ["Contract signed", "Consideration paid"]

    verdict = await engine.generate_verdict(question=question, facts=facts)

    assert verdict is not None

    # 4. Assert metrics have been populated correctly by the system after the query

    # 4a. Trigger stats recalculation on legal monitor (to flush gauge values into collector)
    legal_monitoring.get_stats()

    # 4b. Extract the raw metric dictionary
    updated_metrics = collector.get_all_metrics()

    # Assert query throughput logged
    assert updated_metrics.get("legal_query_throughput_total", 0) == 1

    # Assert query latency logged
    assert updated_metrics.get("legal_query_latency_seconds_count", 0) == 1
    assert "legal_query_latency_seconds_sum" in updated_metrics

    # Assert that SLA compliance is explicitly tracked as a gauge in the system
    assert "legal_sla_compliance_rate" in updated_metrics
    assert updated_metrics["legal_sla_compliance_rate"] >= 0.0

    # Ensure system outputs are actually being emitted via Prometheus string payload
    prometheus_output = collector.to_prometheus()

    assert "TYPE legal_query_throughput_total" in prometheus_output
    assert "legal_query_throughput_total 1" in prometheus_output
    assert "legal_query_latency_seconds" in prometheus_output
    assert "legal_sla_compliance_rate" in prometheus_output
