"""
MAHOUN Legal Consolidation Engine — Temporal Legal Validation
============================================================

Classification: LEGAL DOMAIN / STATUTORY CONSOLIDATION
Governed under MAHOUN V2 Constitutional Authority.

Implements article-level temporal lifecycle, preserving complete historical
versions (never deleting amended/repealed provisions). Enables point-in-time
historical legal state reconstruction.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from collections import defaultdict
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from mahoun.legal_consolidation.models import (
    ArticleTemporalVersion,
    LegalStatus,
    NormativeRelationship,
    NormativeRelationType,
)

logger = logging.getLogger(__name__)


def _parse_comparable_date(d_str: Optional[str]) -> Optional[str]:
    """Normalize date string to standard sortable format (YYYY-MM-DD or YYYY/MM/DD)."""
    if not d_str:
        return None
    cleaned = d_str.strip().replace(".", "-").replace("/", "-")
    parts = cleaned.split("-")
    if len(parts) == 3:
        y, m, d = parts
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    return cleaned


class TemporalValidationEngine:
    """
    Manages article version lifecycles, temporal intervals [valid_from, valid_until],
    and point-in-time legal historical reconstruction.
    """

    def __init__(self):
        # article_id -> list of ArticleTemporalVersion sorted by version_number
        self._history: Dict[str, List[ArticleTemporalVersion]] = defaultdict(list)
        self._lock = threading.RLock()

    def register_initial_article(
        self,
        article_id: str,
        law_id: str,
        text: str,
        valid_from: str,
        approval_date: Optional[str] = None,
        notification_date: Optional[str] = None,
        publication_date: Optional[str] = None,
        effective_date: Optional[str] = None,
        valid_until: Optional[str] = None,
    ) -> ArticleTemporalVersion:
        """
        Register Version 1 (the initial enactment) of a legal article.
        """
        with self._lock:
            text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            version_id = f"{article_id}:v1"
            norm_from = _parse_comparable_date(valid_from) or valid_from
            norm_until = _parse_comparable_date(valid_until)

            v1 = ArticleTemporalVersion(
                version_id=version_id,
                article_id=article_id,
                law_id=law_id,
                version_number=1,
                text=text,
                text_sha256=text_hash,
                valid_from=norm_from,
                valid_until=norm_until,
                approval_date=approval_date,
                notification_date=notification_date,
                publication_date=publication_date,
                effective_date=effective_date,
                status=LegalStatus.ACTIVE if not norm_until else LegalStatus.TEMPORALLY_LIMITED,
            )

            self._history[article_id] = [v1]
            logger.info(f"📜 [INITIAL ARTICLE] {version_id} registered. Valid from: {norm_from}")
            return v1

    def apply_normative_amendment(
        self,
        article_id: str,
        new_text: str,
        effective_date: str,
        relationship: NormativeRelationship,
        approval_date: Optional[str] = None,
        publication_date: Optional[str] = None,
    ) -> ArticleTemporalVersion:
        """
        Apply an amendment (AMENDS / SUPERSEDES), closing the prior active version
        and creating a new historical version with incremented version number.
        Historical text is strictly preserved, never overwritten.
        """
        with self._lock:
            history = self._history.get(article_id)
            if not history:
                raise KeyError(f"Article '{article_id}' does not exist in temporal engine.")

            last_version = history[-1]
            norm_eff_date = _parse_comparable_date(effective_date) or effective_date

            # Close prior active version
            # If the prior version was explicitly repealed, preserve its repeal date and status
            if last_version.status == LegalStatus.EXPLICITLY_REPEALED:
                closed_until = last_version.valid_until
                closed_status = LegalStatus.EXPLICITLY_REPEALED
            else:
                closed_until = norm_eff_date
                closed_status = LegalStatus.AMENDED

            # Replace the last element with closed interval
            closed_last = ArticleTemporalVersion(
                version_id=last_version.version_id,
                article_id=last_version.article_id,
                law_id=last_version.law_id,
                version_number=last_version.version_number,
                text=last_version.text,
                text_sha256=last_version.text_sha256,
                valid_from=last_version.valid_from,
                valid_until=closed_until,
                approval_date=last_version.approval_date,
                notification_date=last_version.notification_date,
                publication_date=last_version.publication_date,
                effective_date=last_version.effective_date,
                status=closed_status,
                basis_relation_id=relationship.relation_id,
                basis_evidence_sha256=relationship.evidence_sha256,
                repealed_portions=last_version.repealed_portions,
                amended_portions=last_version.amended_portions,
            )
            history[-1] = closed_last

            # Create new version
            new_v_num = last_version.version_number + 1
            new_text_hash = hashlib.sha256(new_text.encode("utf-8")).hexdigest()
            new_v = ArticleTemporalVersion(
                version_id=f"{article_id}:v{new_v_num}",
                article_id=article_id,
                law_id=last_version.law_id,
                version_number=new_v_num,
                text=new_text,
                text_sha256=new_text_hash,
                valid_from=norm_eff_date,
                valid_until=None,  # currently open-ended
                approval_date=approval_date,
                publication_date=publication_date,
                effective_date=norm_eff_date,
                status=LegalStatus.ACTIVE,
                basis_relation_id=relationship.relation_id,
                basis_evidence_sha256=relationship.evidence_sha256,
            )
            history.append(new_v)
            logger.info(
                f"🔄 [ARTICLE AMENDED] {article_id} transitioned v{last_version.version_number} "
                f"-> v{new_v_num} at {norm_eff_date}"
            )
            return new_v

    def apply_normative_repeal(
        self,
        article_id: str,
        effective_date: str,
        relationship: NormativeRelationship,
        is_partial: bool = False,
        repealed_portion_text: Optional[str] = None,
    ) -> ArticleTemporalVersion:
        """
        Apply a repeal (REPEALS or PARTIALLY_REPEALS).
        Marks the active version with EXPLICITLY_REPEALED or PARTIALLY_REPEALED.
        Historical text remains completely intact.
        """
        with self._lock:
            history = self._history.get(article_id)
            if not history:
                raise KeyError(f"Article '{article_id}' does not exist in temporal engine.")

            last_version = history[-1]
            norm_eff_date = _parse_comparable_date(effective_date) or effective_date

            if is_partial:
                status = LegalStatus.PARTIALLY_REPEALED
                repealed_list = list(last_version.repealed_portions)
                if repealed_portion_text:
                    repealed_list.append(repealed_portion_text)
                new_v_num = last_version.version_number + 1

                # For partial repeal, close prior version and open new partially repealed version
                closed_last = ArticleTemporalVersion(
                    version_id=last_version.version_id,
                    article_id=last_version.article_id,
                    law_id=last_version.law_id,
                    version_number=last_version.version_number,
                    text=last_version.text,
                    text_sha256=last_version.text_sha256,
                    valid_from=last_version.valid_from,
                    valid_until=norm_eff_date,
                    approval_date=last_version.approval_date,
                    effective_date=last_version.effective_date,
                    status=LegalStatus.ACTIVE,
                )
                history[-1] = closed_last

                new_v = ArticleTemporalVersion(
                    version_id=f"{article_id}:v{new_v_num}",
                    article_id=article_id,
                    law_id=last_version.law_id,
                    version_number=new_v_num,
                    text=last_version.text,
                    text_sha256=last_version.text_sha256,
                    valid_from=norm_eff_date,
                    valid_until=None,
                    effective_date=norm_eff_date,
                    status=status,
                    basis_relation_id=relationship.relation_id,
                    basis_evidence_sha256=relationship.evidence_sha256,
                    repealed_portions=tuple(repealed_list),
                )
                history.append(new_v)
                return new_v
            else:
                # Full explicit repeal
                status = LegalStatus.EXPLICITLY_REPEALED
                repealed_ver = ArticleTemporalVersion(
                    version_id=last_version.version_id,
                    article_id=last_version.article_id,
                    law_id=last_version.law_id,
                    version_number=last_version.version_number,
                    text=last_version.text,
                    text_sha256=last_version.text_sha256,
                    valid_from=last_version.valid_from,
                    valid_until=norm_eff_date,
                    approval_date=last_version.approval_date,
                    effective_date=last_version.effective_date,
                    status=status,
                    basis_relation_id=relationship.relation_id,
                    basis_evidence_sha256=relationship.evidence_sha256,
                )
                history[-1] = repealed_ver
                return repealed_ver

    def get_article_at_date(
        self, article_id: str, as_of_date: str
    ) -> Optional[ArticleTemporalVersion]:
        """
        Point-in-Time Temporal Query:
        Returns the exact version of the article that was legally applicable on `as_of_date`.
        Evaluates interval: valid_from <= as_of_date < valid_until (or open-ended when valid_until is None).
        Returns None if the article was not yet enacted or has already been explicitly repealed.
        """
        with self._lock:
            history = self._history.get(article_id)
            if not history:
                return None

            target = _parse_comparable_date(as_of_date) or as_of_date

            for v in history:
                v_from = v.valid_from
                v_until = v.valid_until

                # Lower bound check
                if v_from <= target:
                    # Open-ended active version
                    if v_until is None:
                        return v
                    # Closed interval [valid_from, valid_until)
                    elif target < v_until:
                        return v

            return None

    def get_article_status_at_date(
        self, article_id: str, as_of_date: str
    ) -> LegalStatus:
        """
        Evaluate the legal status of an article at a specific point in time.
        """
        with self._lock:
            history = self._history.get(article_id)
            if not history:
                return LegalStatus.UNVERIFIED

            target = _parse_comparable_date(as_of_date) or as_of_date

            # If date is prior to initial enactment
            if target < history[0].valid_from:
                return LegalStatus.UNVERIFIED

            applicable_ver = self.get_article_at_date(article_id, as_of_date)
            if applicable_ver is not None:
                # If the version was closed due to later amendment, during its own validity it was ACTIVE
                if applicable_ver.status == LegalStatus.AMENDED:
                    return LegalStatus.ACTIVE
                return applicable_ver.status

            # If no version was applicable, check if target falls into a repeal gap
            for v in reversed(history):
                if v.valid_until and target >= v.valid_until:
                    if v.status == LegalStatus.EXPLICITLY_REPEALED:
                        return LegalStatus.EXPLICITLY_REPEALED
                    break

            return LegalStatus.UNVERIFIED

    def get_latest_version(self, article_id: str) -> Optional[ArticleTemporalVersion]:
        """Return the most current historical version snapshot for an article."""
        with self._lock:
            history = self._history.get(article_id)
            if not history:
                return None
            return history[-1]

    def get_full_version_history(self, article_id: str) -> List[ArticleTemporalVersion]:
        """Return the complete chronological version chain for an article."""
        with self._lock:
            return list(self._history.get(article_id, []))
