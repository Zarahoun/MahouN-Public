"""
MAHOUN Legal Consolidation Engine — Domain Models and Status Types
==================================================================

Classification: LEGAL DOMAIN / STATUTORY CONSOLIDATION
Governed under MAHOUN V2 Constitutional Authority.

Defines the domain models, enums, versioning schemas, and review contracts
for continuous, evidence-based legal consolidation of Iranian statutes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class SourceAuthorityType(str, Enum):
    """Authoritative legal source classifications."""
    OFFICIAL_GAZETTE = "official_gazette"                    # روزنامه رسمی جمهوری اسلامی ایران (rrk.ir)
    NATIONAL_DATABASE_DOTIC = "national_database_dotic"       # سامانه ملی قوانین و مقررات (dotic.ir)
    PARLIAMENT_RC = "parliament_rc"                          # مرکز پژوهش‌های مجلس (rc.majlis.ir)
    CENTRAL_BANK = "central_bank"                            # بانک مرکزی جمهوری اسلامی ایران
    EXPEDIENCY_COUNCIL = "expediency_council"                # مجمع تشخیص مصلحت نظام
    SUPREME_COURT = "supreme_court"                          # دیوان عالی کشور (آرای وحدت رویه)
    OTHER_COMPETENT_AUTHORITY = "other_competent_authority"  # سایر مراجع صلاحیت‌دار قانونی


class ChangeType(str, Enum):
    """Classification of legislative changes."""
    NEW_INSTRUMENT = "NEW_INSTRUMENT"                        # تصویب قانون / مقرره جدید
    AMENDMENT = "AMENDMENT"                                  # اصلاح متن ماده یا تبصره
    ADDITION = "ADDITION"                                    # الحاق ماده، تبصره یا بند جدید
    DELETION = "DELETION"                                    # حذف بدون ذکر صریح نسخ
    EXPLICIT_REPEAL = "EXPLICIT_REPEAL"                      # نسخ صریح ماده یا کل قانون
    PARTIAL_REPEAL = "PARTIAL_REPEAL"                        # نسخ جزئی عبارتی از ماده
    POTENTIAL_IMPLICIT_REPEAL = "POTENTIAL_IMPLICIT_REPEAL"  # نسخ ضمنی یا تعارض هنجاری محتمل
    TEMPORAL_CHANGE = "TEMPORAL_CHANGE"                      # تمدید مهلت یا تغییر موعد اجرا


class NormativeRelationType(str, Enum):
    """Normative legal relationship types between provisions."""
    AMENDS = "AMENDS"
    REPEALS = "REPEALS"
    PARTIALLY_REPEALS = "PARTIALLY_REPEALS"
    INTERPRETS = "INTERPRETS"
    CONFLICTS_WITH = "CONFLICTS_WITH"
    SUPERSEDES = "SUPERSEDES"


class LegalStatus(str, Enum):
    """
    Article and provision legal lifecycle status.
    Mandated by MAHOUN Legal Consolidation Specification.
    """
    ACTIVE = "ACTIVE"                                        # لازم‌الاجرا و جاری
    AMENDED = "AMENDED"                                      # اصلاح‌شده (با نسخه لاحق جایگزین گردیده)
    PARTIALLY_REPEALED = "PARTIALLY_REPEALED"                # منسوخ جزئی (بخشی از حکم یا عبارات آن ساقط شده)
    EXPLICITLY_REPEALED = "EXPLICITLY_REPEALED"              # منسوخ صریح (حکم قانوناً بلااثر شده)
    IMPLICIT_REPEAL_CANDIDATE = "IMPLICIT_REPEAL_CANDIDATE"  # کاندیدای نسخ ضمنی (نیازمند رسیدگی ممیز انسانی)
    CONFLICTED = "CONFLICTED"                                # متعارض با قانون لاحق یا خاص
    TEMPORALLY_LIMITED = "TEMPORALLY_LIMITED"                # قانون موقت یا آزمایشی منقضی‌شده
    UNVERIFIED = "UNVERIFIED"                                # تأییدنشده (فرضیه مستندسازی‌نشده ماشین)


class VerificationStatus(str, Enum):
    """Verification and epistemic standing of legal assertions."""
    UNVERIFIED = "UNVERIFIED"
    HYPOTHESIS = "HYPOTHESIS"
    PENDING_REVIEW = "PENDING_REVIEW"
    VERIFIED = "VERIFIED"
    DISPUTED = "DISPUTED"
    REJECTED = "REJECTED"


class ReviewDecision(str, Enum):
    """Jurist decision on human review queue items."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MODIFIED = "MODIFIED"


@dataclass(frozen=True)
class MonitoredSourceDocument:
    """
    Immutable representation of an ingested legal source document.
    Preserves cryptographic provenance and retrieval metadata.
    """
    source_id: str
    authority_type: SourceAuthorityType
    source_url: str
    document_identifier: str
    title_fa: str
    raw_content: str
    content_sha256: str
    retrieval_timestamp: str
    publication_date: Optional[str] = None
    is_accessible: bool = True
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED

    def __post_init__(self):
        computed = hashlib.sha256(self.raw_content.encode("utf-8")).hexdigest()
        if self.content_sha256 != computed:
            raise ValueError(
                f"Source document hash mismatch! Expected {self.content_sha256}, got {computed}"
            )


@dataclass(frozen=True)
class DetectedLegalChange:
    """
    Change detected by the syntactic and legislative parser.
    References exact evidence spans and supporting statutory texts.
    """
    change_id: str
    change_type: ChangeType
    source_doc_id: str
    source_article_num: str
    target_law_id: str
    target_article_num: str
    evidence_text: str
    evidence_span: Tuple[int, int]
    evidence_sha256: str
    detected_at: str
    confidence: float = 1.0
    is_explicit: bool = True
    notes: str = ""

    def __post_init__(self):
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"Confidence must be in [0.0, 1.0], got {self.confidence}")


@dataclass(frozen=True)
class NormativeRelationship:
    """
    Formal normative relationship between two legal provisions or enactments.
    Preserves cryptographic Merkle proof and epistemic status.
    """
    relation_id: str
    relation_type: NormativeRelationType
    source_law_id: str
    source_article_id: str
    target_law_id: str
    target_article_id: str
    evidence_text: str
    evidence_sha256: str
    confidence: float
    verification_status: VerificationStatus
    effective_date: Optional[str] = None
    approval_date: Optional[str] = None
    provenance_merkle_root: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_binding_fact(self) -> bool:
        """Only explicitly verified relationships can be treated as legal facts."""
        return self.verification_status == VerificationStatus.VERIFIED


@dataclass(frozen=True)
class ArticleTemporalVersion:
    """
    Article-level historical snapshot preserving temporal validity intervals.
    Enforces valid-time point-in-time retrieval.
    """
    version_id: str
    article_id: str
    law_id: str
    version_number: int
    text: str
    text_sha256: str
    valid_from: str                           # YYYY-MM-DD
    valid_until: Optional[str]                 # YYYY-MM-DD or None (open-ended/active)
    approval_date: Optional[str] = None
    notification_date: Optional[str] = None
    publication_date: Optional[str] = None
    effective_date: Optional[str] = None
    status: LegalStatus = LegalStatus.ACTIVE
    basis_relation_id: Optional[str] = None
    basis_evidence_sha256: Optional[str] = None
    repealed_portions: Tuple[str, ...] = field(default_factory=tuple)
    amended_portions: Tuple[str, ...] = field(default_factory=tuple)


@dataclass
class HumanReviewItem:
    """
    Governance item queued for certified human jurist review.
    Uncertain inferences cannot be promoted to graph without approval.
    """
    review_id: str
    target_type: str                          # "RELATIONSHIP", "IMPLICIT_REPEAL", "CONFLICT", "UNVERIFIED_SOURCE"
    item_id: str
    original_evidence: str
    evidence_sha256: str
    proposed_assertion: Dict[str, Any]
    temporal_impact_summary: str
    reasoning: str
    confidence: float
    status: ReviewDecision = ReviewDecision.PENDING
    reviewer_id: Optional[str] = None
    review_timestamp: Optional[str] = None
    jurist_notes: Optional[str] = None
    signed_authorization_hash: Optional[str] = None


@dataclass(frozen=True)
class ConsolidationRunReceipt:
    """
    Cryptographic execution receipt of a legal consolidation processing cycle.
    Provides verifiable proof of processed sources, changes, and governance items.
    """
    receipt_id: str
    source_doc_id: str
    source_law_id: str
    detected_changes_count: int
    verified_relationships: Tuple[NormativeRelationship, ...]
    queued_for_review_items: Tuple[HumanReviewItem, ...]
    consolidation_merkle_root: str
    processed_at: str
