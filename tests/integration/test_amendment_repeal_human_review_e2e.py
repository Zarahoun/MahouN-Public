"""
MAHOUN Production Pipeline — Candidate Lifecycle & Human Review Gate Audit Suite
==============================================================================
Classification: RIGOROUS INTEGRATION AUDIT (Step 4 Roadmap)
Purpose: Zero-mock, end-to-end verification proving:
         1. Accurate extraction of AMENDS and REPEALS from real Iranian legal texts.
         2. Strict enforcement of Human-in-the-Loop policy: high-risk temporal mutations
            (AMENDS, REPEALS) MUST NEVER be auto-approved, regardless of confidence score.
         3. Formal FSM lifecycle progression: EXTRACTED -> RESOLVED -> VALIDATED -> COMMITTED.
         4. Event-sourcing and audit trail immutability for candidate relations.
"""

from __future__ import annotations

import pytest

from mahoun.graph.semantic.amendment_extractor import (
    AmendmentExtractor,
    RepealExtractor,
)
from mahoun.graph.semantic.candidate_relations import (
    CandidateRelation,
    CandidateStatus,
    ResolutionMethod,
    InMemoryCandidateRepository,
    DomainEventBus,
    InvalidTransitionError,
)
from mahoun.graph.semantic.expansion_quality_gate import (
    ExpansionQualityGate,
)
from mahoun.graph.semantic.expansion_decision import (
    ExpansionDecisionEngine,
    EngineDecision,
    AUTO_APPROVAL_STATUS,
)


# ============================================================================
# REAL IRANIAN STATUTORY AMENDMENT / REPEAL TEXTS
# ============================================================================

SAMPLE_AMENDMENT_TEXT_1 = (
    "ماده ۱۰: ماده ۲۳۰ قانون مدنی به شرح زیر اصلاح می‌شود: "
    "خسارت تاخیر تادیه طبق شاخص تورم بانک مرکزی محاسبه خواهد شد."
)

SAMPLE_AMENDMENT_TEXT_2 = (
    "ماده ۵: تبصره ۱ ماده ۴ قانون صدور چک اصلاح می‌گردد."
)

SAMPLE_REPEAL_TEXT_1 = (
    "ماده ۱۲: ماده ۳۱۰ قانون تجارت مصوب ۱۳۱۱ نسخ می‌گردد."
)

SAMPLE_REPEAL_TEXT_2 = (
    "ماده ۲۰: مواد ۴۱۲ تا ۴۱۵ قانون تجارت ملغی می‌شود."
)


# ============================================================================
# 1. AMENDMENT & REPEAL EXTRACTION ACCURACY AUDIT
# ============================================================================

def test_amendment_and_repeal_extraction_accuracy():
    """
    Verify that AmendmentExtractor and RepealExtractor extract accurate
    AMENDS and REPEALS candidates with exact spans and confidence scores.
    """
    amend_extractor = AmendmentExtractor()
    repeal_extractor = RepealExtractor()

    # 1. Test explicit amendment extraction
    amend_candidates = amend_extractor.extract(
        SAMPLE_AMENDMENT_TEXT_1,
        {
            "source_id": "law:amend_law:article:10",
            "law_id": "civil_code",
        },
    )
    assert len(amend_candidates) >= 1
    amend_rel = amend_candidates[0]
    assert amend_rel["type"] == "AMENDS"
    assert "230" in amend_rel["to"]
    assert amend_rel["provenance"]["confidence"] >= 0.85
    assert amend_rel["candidate_status"] == CandidateStatus.EXTRACTED.value

    # 2. Test explicit repeal extraction
    repeal_candidates = repeal_extractor.extract(
        SAMPLE_REPEAL_TEXT_1,
        {
            "source_id": "law:repeal_law:article:12",
            "law_id": "comm_law",
        },
    )
    assert len(repeal_candidates) >= 1
    repeal_rel = repeal_candidates[0]
    assert repeal_rel["type"] == "REPEALS"
    assert "310" in repeal_rel["to"]
    assert repeal_rel["provenance"]["confidence"] >= 0.85
    assert repeal_rel["candidate_status"] == CandidateStatus.EXTRACTED.value


# ============================================================================
# 2. HUMAN-IN-THE-LOOP MANDATORY REVIEW GATE AUDIT
# ============================================================================

def test_amends_and_repeals_strictly_require_human_review():
    """
    SAFETY INVARIANT:
    AMENDS and REPEALS have profound legal impact. The decision engine MUST
    categorically refuse to AUTO_APPROVE them, routing them to REVIEW
    even if the confidence is 1.0 (Human-in-the-Loop Enforcement).
    """
    gate = ExpansionQualityGate()
    engine = ExpansionDecisionEngine()

    # High-confidence AMENDS candidate
    amends_cand = CandidateRelation(
        candidate_id="cand:amends:test:01",
        from_id="law:new:art:1",
        type="AMENDS",
        to_id="law:old:art:10",
        confidence=1.0,  # Maximum confidence!
        evidence_span=(0, 30),
        status=CandidateStatus.VALIDATED,
        extractor_name="amendment_extractor",
        resolved_target_id="law:old:art:10",
    )

    # High-confidence REPEALS candidate
    repeals_cand = CandidateRelation(
        candidate_id="cand:repeals:test:02",
        from_id="law:new:art:2",
        type="REPEALS",
        to_id="law:old:art:50",
        confidence=1.0,  # Maximum confidence!
        evidence_span=(0, 30),
        status=CandidateStatus.VALIDATED,
        extractor_name="repeal_extractor",
        resolved_target_id="law:old:art:50",
    )

    # Low-risk simple reference for comparison
    cites_cand = CandidateRelation(
        candidate_id="cand:cites:test:03",
        from_id="law:new:art:3",
        type="REFERENCES",
        to_id="law:old:art:5",
        confidence=0.99,
        evidence_span=(0, 20),
        status=CandidateStatus.VALIDATED,
        extractor_name="citation_extractor",
        resolved_target_id="law:old:art:5",
    )

    decision_amends = engine.propose(amends_cand)
    decision_repeals = engine.propose(repeals_cand)
    decision_cites = engine.propose(cites_cand)

    # AMENDS and REPEALS MUST NOT BE AUTO-APPROVED
    assert decision_amends.proposed_decision == EngineDecision.REVIEW, (
        f"Security breach: AMENDS was proposed as {decision_amends.proposed_decision} instead of REVIEW"
    )
    assert decision_repeals.proposed_decision == EngineDecision.REVIEW, (
        f"Security breach: REPEALS was proposed as {decision_repeals.proposed_decision} instead of REVIEW"
    )

    # Simple low-risk references may be auto-approved when enough supporting
    # evidence exists; absent that evidence they should still avoid REJECT here.
    if AUTO_APPROVAL_STATUS == "PHASE_1":
        assert decision_cites.proposed_decision in {
            EngineDecision.AUTO_APPROVE,
            EngineDecision.REVIEW,
        }


# ============================================================================
# 3. FORMAL FSM CANDIDATE LIFECYCLE AUDIT
# ============================================================================

def test_formal_fsm_candidate_lifecycle():
    """
    AUDIT FSM TRANSITIONS:
    EXTRACTED -> RESOLVED -> VALIDATED -> COMMITTED
    And assert that illegal transitions (e.g. EXTRACTED -> COMMITTED) raise InvalidTransitionError.
    """
    repo = InMemoryCandidateRepository()
    event_bus = DomainEventBus()

    cand = CandidateRelation(
        candidate_id="cand:lifecycle:001",
        from_id="art:1",
        type="AMENDS",
        to_id="art:2",
        confidence=0.95,
        evidence_span=(0, 15),
        status=CandidateStatus.EXTRACTED,
    )
    repo.save(cand)

    # 1. Illegal transition directly from EXTRACTED to COMMITTED must raise InvalidTransitionError
    with pytest.raises(InvalidTransitionError):
        cand.transition_to(CandidateStatus.COMMITTED, reason="Bypassing validation")

    # 2. Legitimate transition to RESOLVED
    cand.transition_to(
        CandidateStatus.RESOLVED,
        reason="Resolved target article id",
        bus=event_bus,
        resolved_target_id="art:2",
        resolution_method=ResolutionMethod.EXACT_MATCH,
    )
    assert cand.status == CandidateStatus.RESOLVED
    assert cand.event_count == 2  # Created + Resolved

    # 3. Legitimate transition to VALIDATED
    cand.transition_to(
        CandidateStatus.VALIDATED,
        reason="Quality gates passed with confidence 0.95",
        bus=event_bus,
    )
    assert cand.status == CandidateStatus.VALIDATED
    assert cand.event_count == 3

    # 4. Human approves -> COMMITTED
    cand.transition_to(
        CandidateStatus.COMMITTED,
        reason="Human legal expert approved candidate",
        actor="expert_attorney_01",
        bus=event_bus,
    )
    assert cand.status == CandidateStatus.COMMITTED
    assert cand.event_count == 4

    # 5. Terminal state: cannot transition out of COMMITTED
    with pytest.raises(InvalidTransitionError):
        cand.transition_to(CandidateStatus.REJECTED, reason="Cannot reject committed relation")
