"""
MAHOUN Legal Consolidation Engine — Change Detection & Legislative Analysis
===========================================================================

Classification: LEGAL DOMAIN / STATUTORY CONSOLIDATION
Governed under MAHOUN V2 Constitutional Authority.

Detects, classifies, and extracts legislative changes (amendments, repeals,
additions, deletions, implicit conflicts) from Persian statutory enactments.
References exact character spans, supporting articles, and evidence SHA-256 hashes.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from mahoun.legal_consolidation.models import (
    ChangeType,
    DetectedLegalChange,
    MonitoredSourceDocument,
)

logger = logging.getLogger(__name__)


def normalize_persian_digits(s: str) -> str:
    """Normalize Persian and Arabic digits to ASCII digits."""
    persian_digits = "۰۱۲۳۴۵۶۷۸۹"
    arabic_digits = "٠١٢٣٤٥٦٧٨٩"
    for i, d in enumerate(persian_digits):
        s = s.replace(d, str(i))
    for i, d in enumerate(arabic_digits):
        s = s.replace(d, str(i))
    return s


CANONICAL_LAW_ALIASES = {
    "تجارت": "commercial_code",
    "قانون تجارت": "commercial_code",
    "لایحه قانونی تجارت": "commercial_code",
    "مدنی": "civil_code",
    "قانون مدنی": "civil_code",
    "کار": "labor_law",
    "قانون کار": "labor_law",
    "ثبت": "registration_law",
    "ثبت اسناد و املاک": "registration_law",
    "قانون ثبت": "registration_law",
    "قانون ثبت اسناد و املاک": "registration_law",
    "مجازات اسلامی": "islamic_penal_code",
    "قانون مجازات اسلامی": "islamic_penal_code",
    "آیین دادرسی مدنی": "civil_procedure_code",
    "قانون آیین دادرسی مدنی": "civil_procedure_code",
    "آیین دادرسی کیفری": "criminal_procedure_code",
    "قانون آیین دادرسی کیفری": "criminal_procedure_code",
    "شوراهای حل اختلاف": "dispute_resolution_councils_law",
    "چک": "check_law",
    "صدور چک": "check_law",
    "قانون صدور چک": "check_law",
    "پولی و بانکی": "monetary_banking_1351",
    "پولی و بانکی کشور": "monetary_banking_1351",
    "قانون پولی و بانکی": "monetary_banking_1351",
    "قانون پولی و بانکی کشور": "monetary_banking_1351",
    "مبارزه با پولشویی": "anti_money_laundering",
    "قانون مبارزه با پولشویی": "anti_money_laundering",
}


# Standard Persian Legislative Regex Patterns
PATTERNS = [
    # 1. Explicit Repeal (نسخ صریح)
    (
        ChangeType.EXPLICIT_REPEAL,
        re.compile(
            r"(?:ماده|مواد|بند|تبصره)[\s\u200c]+([۰-۹\d]+(?:[\s\u200c]*،[\s\u200c]*[۰-۹\d]+)*)[\s\u200c]+(?:قانون|لایحه[\s\u200c]+قانونی)[\s\u200c]+([^،.\n]+?)[\s\u200c]+(?:صراحتاً|صریحاً)?[\s\u200c]*(?:نسخ|لغو)(?:[\s\u200c]+و[\s\u200c]+ملغی[\s\u200c]*الاثر)?[\s\u200c]+(?:می[\s\u200c]*گردد|می[\s\u200c]*شود|شد|از[\s\u200c]+تاریخ[\s\u200c]+لازم[\s\u200c]*الاجرا[\s\u200c]+شدن[\s\u200c]+این[\s\u200c]+قانون[\s\u200c]+لغو[\s\u200c]+می[\s\u200c]*گردد)",
            re.UNICODE,
        ),
        True,  # is_explicit
    ),
    # 2. Amendment / Substitution (اصلاح / جایگزینی)
    (
        ChangeType.AMENDMENT,
        re.compile(
            r"(?:ماده|تبصره|بند)[\s\u200c]+([۰-۹\d]+)[\s\u200c]+(?:قانون|لایحه)[\s\u200c]+([^،.\n]+?)[\s\u200c]+به[\s\u200c]+شرح[\s\u200c]+زیر[\s\u200c]+اصلاح[\s\u200c]+(?:می[\s\u200c]*گردد|می[\s\u200c]*شود)",
            re.UNICODE,
        ),
        True,
    ),
    # 3. Addition / Annexation (الحاق)
    (
        ChangeType.ADDITION,
        re.compile(
            r"(?:یک[\s\u200c]+تبصره|ماده[\s\u200c]+مکرر|ماده[\s\u200c]+[۰-۹\d]+[\s\u200c]+مکرر|یک[\s\u200c]+ماده)[\s\u200c]+به[\s\u200c]+(?:عنوان[\s\u200c]+)?(?:ماده|تبصره)[\s\u200c]+([۰-۹\d]+)?[\s\u200c]*(?:قانون|لایحه)[\s\u200c]+([^،.\n]+?)[\s\u200c]+الحاق[\s\u200c]+(?:می[\s\u200c]*گردد|می[\s\u200c]*شود)",
            re.UNICODE,
        ),
        True,
    ),
    # 4. Partial Repeal (نسخ جزئی / حذف بخشی از حکم)
    (
        ChangeType.PARTIAL_REPEAL,
        re.compile(
            r"(?:عبارت|واژه|کلمات)[\s\u200c]+[«\"]([^»\"]+)[»\"][\s\u200c]+از[\s\u200c]+(?:متن[\s\u200c]+)?(?:ماده|تبصره)[\s\u200c]+([۰-۹\d]+)[\s\u200c]+(?:قانون|لایحه)[\s\u200c]+([^،.\n]+?)[\s\u200c]+حذف[\s\u200c]+(?:می[\s\u200c]*گردد|می[\s\u200c]*شود)",
            re.UNICODE,
        ),
        True,
    ),
    # 5. Potential Implicit Repeal / Conflict Clause (نسخ ضمنی / مقررات مغایر)
    (
        ChangeType.POTENTIAL_IMPLICIT_REPEAL,
        re.compile(
            r"(?:کلیه[\s\u200c]+قوانین[\s\u200c]+و[\s\u200c]+مقررات[\s\u200c]+مغایر|احکام[\s\u200c]+مغایر|قوانین[\s\u200c]+مغایر|مقررات[\s\u200c]+مغایر)(?:[\s\u200c]+با[\s\u200c]+(?:این[\s\u200c]+قانون|این[\s\u200c]+ماده|آن))?[\s\u200c]*(?:از[\s\u200c]+تاریخ[\s\u200c]+لازم[\s\u200c]*الاجرا[\s\u200c]+شدن[\s\u200c]+(?:این[\s\u200c]+قانون[\s\u200c]+)?)?(?:ملغی|منسوخ|کان[\s\u200c]*لم[\s\u200c]*یکن|باطل)[\s\u200c]*(?:می[\s\u200c]*باشند|می[\s\u200c]*گردند|می[\s\u200c]*شود|است|اعلام[\s\u200c]+می[\s\u200c]*شود)?",
            re.UNICODE,
        ),
        False,  # is_explicit = False (General conflict clause, requires human interpretation)
    ),
    # 6. Temporal Change / Extension (تمدید مهلت یا تغییر موعد)
    (
        ChangeType.TEMPORAL_CHANGE,
        re.compile(
            r"(?:مهلت|مدت)[\s\u200c]+اجرای[\s\u200c]+(?:آزمایشی[\s\u200c]+)?قانون[\s\u200c]+([^،.\n]+?)[\s\u200c]+تا[\s\u200c]+تاریخ[\s\u200c]+([۰-۹\d/]+)[\s\u200c]+تمدید[\s\u200c]+(?:می[\s\u200c]*گردد|می[\s\u200c]*شود)",
            re.UNICODE,
        ),
        True,
    ),
]


class LegalChangeDetector:
    """
    Syntactic & legislative pattern analysis engine.
    Extracts evidence-anchored changes from legal enactments.
    """

    def __init__(self):
        self._counter = 0

    def detect_changes_in_text(
        self,
        source_doc_id: str,
        text: str,
        source_article_num: str = "general",
    ) -> List[DetectedLegalChange]:
        """
        Scan statutory text for legislative modifications.
        Returns a list of structured, evidence-backed changes.
        """
        detected: List[DetectedLegalChange] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        for change_type, pattern, is_explicit in PATTERNS:
            for match in pattern.finditer(text):
                self._counter += 1
                span = match.span()
                matched_text = match.group(0).strip()
                evidence_hash = hashlib.sha256(matched_text.encode("utf-8")).hexdigest()

                target_article = "ALL"
                target_law = "UNKNOWN"

                groups = match.groups()
                if len(groups) >= 2:
                    if change_type in (ChangeType.EXPLICIT_REPEAL, ChangeType.AMENDMENT):
                        target_article = groups[0].strip() if groups[0] else "ALL"
                        target_law = groups[1].strip() if groups[1] else "UNKNOWN"
                    elif change_type == ChangeType.PARTIAL_REPEAL:
                        target_article = groups[1].strip() if groups[1] else "ALL"
                        target_law = groups[2].strip() if len(groups) > 2 and groups[2] else "UNKNOWN"
                    elif change_type == ChangeType.TEMPORAL_CHANGE:
                        target_law = groups[0].strip() if groups[0] else "UNKNOWN"
                        target_article = f"VALID_UNTIL:{groups[1].strip()}" if len(groups) > 1 and groups[1] else "ALL"
                elif len(groups) == 1 and change_type == ChangeType.TEMPORAL_CHANGE:
                    target_law = groups[0].strip() if groups[0] else "UNKNOWN"

                # Normalize Persian numerals and resolve canonical law identifiers
                target_article = normalize_persian_digits(target_article)
                # Strip enactment year suffix e.g. "مصوب ۱۳۵۵" or "مصوب 1355" or "با اصلاحات بعدی"
                clean_target_law = re.sub(r"[\s\u200c]*مصوب[\s\u200c]*[۰-۹\d]+.*$", "", target_law.strip())
                clean_target_law = re.sub(r"[\s\u200c]*با[\s\u200c]+اصلاحات.*$", "", clean_target_law).strip()
                target_law = CANONICAL_LAW_ALIASES.get(
                    clean_target_law,
                    CANONICAL_LAW_ALIASES.get(target_law.strip(), target_law.strip())
                )

                # Determine effective source article
                effective_src_article = source_article_num
                if effective_src_article in ("general", "full_document") and "ماده واحده" in text:
                    effective_src_article = "1"

                # Implicit repeal candidate has lower initial confidence and is never explicit
                confidence = 1.0 if is_explicit else 0.65

                change = DetectedLegalChange(
                    change_id=f"change_{source_doc_id}_{self._counter:04d}",
                    change_type=change_type,
                    source_doc_id=source_doc_id,
                    source_article_num=effective_src_article,
                    target_law_id=target_law,
                    target_article_num=target_article,
                    evidence_text=matched_text,
                    evidence_span=span,
                    evidence_sha256=evidence_hash,
                    detected_at=now_iso,
                    confidence=confidence,
                    is_explicit=is_explicit,
                    notes=(
                        "Explicit legislative amendment"
                        if is_explicit
                        else "General repeal/conflict clause; requires jurist review"
                    ),
                )
                detected.append(change)

        # Preserve exact document order
        detected.sort(key=lambda c: c.evidence_span[0])
        logger.info(f"🔍 [CHANGE DETECTOR] Found {len(detected)} legislative changes in {source_doc_id}")
        return detected

    def detect_changes_in_document(
        self, doc: MonitoredSourceDocument
    ) -> List[DetectedLegalChange]:
        """Convenience method to scan a MonitoredSourceDocument directly."""
        return self.detect_changes_in_text(
            source_doc_id=doc.source_id,
            text=doc.raw_content,
            source_article_num="full_document",
        )
