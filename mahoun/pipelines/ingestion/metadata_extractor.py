"""
Metadata Extractor for MAHOUN
=============================

استخراج خودکار metadata از مدارک پیمانکاری:
- تاریخ (تاریخ نامه، تاریخ دریافت)
- شماره نامه/سند
- موضوع
- طرفین (فرستنده/گیرنده)
- امضا
- پیوست‌ها

از کامپوننت‌های موجود استفاده می‌کند:
- LegalNEREngine برای استخراج entities
- Pattern matching برای استخراج اطلاعات ساختاریافته
"""

import logging
import re
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DATE_PATTERN = re.compile(
    r"(?<!\d)(?:"
    r"(?P<year_first>\d{4})\s*[/.,-]\s*(?P<month_first>\d{1,2})"
    r"\s*[/.,-]\s*(?P<day_first>\d{1,2})"
    r"|(?P<day_last>\d{1,2})\s*[/.,-]\s*(?P<month_last>\d{1,2})"
    r"\s*[/.,-]\s*(?P<year_last>\d{4})"
    r")(?!\d)"
)


class MetadataExtractor:
    """
    Metadata Extractor برای استخراج خودکار اطلاعات از مدارک

    این کلاس از کامپوننت‌های موجود استفاده می‌کند:
    - LegalNEREngine برای استخراج entities (اگر موجود باشد)
    - Pattern matching برای استخراج اطلاعات ساختاریافته
    """

    def __init__(self):
        """Initialize Metadata Extractor"""
        # Legal NER Engine (optional)
        self.ner_engine = None
        try:
            from .legal_ner import LegalNEREngine

            self.ner_engine = LegalNEREngine()
            logger.info("✅ LegalNEREngine initialized for metadata extraction")
        except ImportError:
            logger.warning("LegalNEREngine not available, using pattern matching only")

        logger.info("MetadataExtractor initialized")

    async def extract(self, text: str, doc_type: str) -> Dict[str, Any]:
        """
        Extract metadata from document text

        Args:
            text: متن سند
            doc_type: نوع سند (contract, letter, report, etc.)

        Returns:
            Dictionary of extracted metadata
        """
        metadata = {
            "doc_type": doc_type,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
        }

        # Extract basic metadata
        metadata.update(self._extract_dates(text))
        metadata.update(self._extract_document_number(text))
        metadata.update(self._extract_subject(text))
        metadata.update(self._extract_parties(text, doc_type))
        metadata.update(self._extract_signatures(text))
        metadata.update(self._extract_attachments(text))

        # Extract entities using NER (if available)
        if self.ner_engine:
            try:
                entities = self.ner_engine.extract(text)
                metadata["entities"] = {
                    "persons": entities.get("persons", []),
                    "organizations": entities.get("organizations", []),
                    "courts": entities.get("courts", []),
                    "laws": entities.get("laws", []),
                    "topics": entities.get("topics", []),
                }
            except Exception as e:
                logger.warning(f"NER extraction failed: {e}")

        return metadata

    def _extract_dates(self, text: str) -> Dict[str, Any]:
        """Extract dates from text"""
        dates = {
            "date": None,
            "date_received": None,
            "date_issued": None,
            "dates_found": [],
        }

        # Keep the complete date rather than just the first regex capture (year).
        matches = self._valid_date_matches(text[:2000])
        dates["dates_found"] = list(
            dict.fromkeys(self._normalize_digits(match.group(0)) for match in matches)
        )

        # Extract specific dates
        # Date issued (usually at the beginning)
        first_200 = text[:200]
        match = next(iter(self._valid_date_matches(first_200)), None)
        if match:
            dates["date_issued"] = self._normalize_digits(match.group(0))
            dates["date"] = dates["date_issued"]

        # Date received (look for keywords)
        received_keywords = ["تاریخ دریافت", "تاریخ وصول", "received", "received_date"]
        for keyword in received_keywords:
            if keyword in text:
                # Find date after keyword
                keyword_pos = text.find(keyword)
                snippet = text[keyword_pos : keyword_pos + 100]
                match = next(iter(self._valid_date_matches(snippet)), None)
                if match:
                    dates["date_received"] = self._normalize_digits(match.group(0))
                if dates["date_received"]:
                    break

        return dates

    @staticmethod
    def _valid_date_matches(text: str) -> List[re.Match[str]]:
        matches = []
        for match in DATE_PATTERN.finditer(text):
            if match.group("year_first"):
                month = int(match.group("month_first"))
                day = int(match.group("day_first"))
            else:
                month = int(match.group("month_last"))
                day = int(match.group("day_last"))
            if 1 <= month <= 12 and 1 <= day <= 31:
                matches.append(match)
        return matches

    @staticmethod
    def _normalize_digits(value: str) -> str:
        from .persian_normalizer import PersianLegalNormalizer

        return PersianLegalNormalizer.normalize_digits(value)

    def _extract_document_number(self, text: str) -> Dict[str, Any]:
        """Extract document number"""
        # Look for document number patterns
        patterns = [
            r"شماره[:\s]+(\d+(?:[-/]\d+)*)",
            r"ش\.\s*(\d+(?:[-/]\d+)*)",
            r"No[:\s]+(\d+(?:[-/]\d+)*)",
            r"Number[:\s]+(\d+(?:[-/]\d+)*)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text[:500], re.IGNORECASE)
            if match:
                return {"document_number": self._normalize_digits(match.group(1))}

        return {"document_number": None}

    def _extract_subject(self, text: str) -> Dict[str, Any]:
        """Extract subject/title"""
        subject: Optional[Any] = None
        # Look for subject keywords
        keywords = [
            ("موضوع", ":"),
            ("عنوان", ":"),
            ("Subject", ":"),
            ("Title", ":"),
        ]

        for keyword, separator in keywords:
            pattern = f"{keyword}{separator}\\s*(.+?)(?:\\n|$)"
            match = re.search(pattern, text[:1000], re.IGNORECASE)
            if match:
                subject = match.group(1).strip()
                if len(subject) > 5:  # Valid subject
                    break

        # If not found, use first line
        if not subject:
            first_line = text.split("\n")[0].strip()
            if len(first_line) > 10 and len(first_line) < 200:
                subject = first_line

        return {"subject": subject}

    def _extract_parties(self, text: str, doc_type: str) -> Dict[str, Any]:
        """Extract parties (sender/receiver)"""
        parties = {"sender": None, "receiver": None, "parties": []}

        # For contracts, look for party keywords
        if doc_type == "contract":
            party_keywords = ["طرف اول", "طرف دوم", "کارفرما", "پیمانکار"]
            for keyword in party_keywords:
                if keyword in text:
                    # Extract party name after keyword
                    pattern = f"{keyword}[:\\s]+(.+?)(?:\\n|،|$)"
                    match = re.search(pattern, text[:2000])
                    if match:
                        party_name = match.group(1).strip()
                        parties["parties"].append({"role": keyword, "name": party_name})

        # For letters, look for sender/receiver
        elif doc_type == "letter":
            # Sender keywords
            sender_keywords = ["از", "فرستنده", "sender", "from"]
            for keyword in sender_keywords:
                if keyword in text[:500]:
                    pattern = f"{keyword}[:\\s]+(.+?)(?:\\n|،|$)"
                    match = re.search(pattern, text[:500])
                    if match:
                        parties["sender"] = match.group(1).strip()
                        break

            # Receiver keywords
            receiver_keywords = ["به", "گیرنده", "receiver", "to"]
            for keyword in receiver_keywords:
                if keyword in text[:500]:
                    pattern = f"{keyword}[:\\s]+(.+?)(?:\\n|،|$)"
                    match = re.search(pattern, text[:500])
                    if match:
                        parties["receiver"] = match.group(1).strip()
                        break

        return parties

    def _extract_signatures(self, text: str) -> Dict[str, Any]:
        """Extract signature information"""
        signatures = {"has_signature": False, "signature_text": None, "signers": []}
        signature_line = re.compile(
            r"^\s*(?:امضا(?:ء|ی)?|مهر|signature|signed)\s*"
            r"(?::|：|-)?\s*(?P<details>\S.*?)\s*$",
            re.IGNORECASE | re.MULTILINE,
        )
        trailing_text = text[-min(len(text), 2000) :]
        match = signature_line.search(trailing_text)
        if match:
            signatures["has_signature"] = True
            signatures["signature_text"] = match.group(0).strip()

        return signatures

    def _extract_attachments(self, text: str) -> Dict[str, Any]:
        """Extract attachment information"""
        attachments = {
            "has_attachments": False,
            "attachment_count": 0,
            "attachments": [],
        }

        # Look for attachment keywords
        attachment_keywords = ["پیوست", "ضمیمه", "attachment", "enclosure"]

        for keyword in attachment_keywords:
            if keyword in text.lower():
                attachments["has_attachments"] = True

                # Count attachments
                pattern = f"{keyword}[:\\s]*(\\d+)"
                matches = re.findall(pattern, text.lower())
                if matches:
                    attachments["attachment_count"] = len(matches)
                    attachments["attachments"] = [
                        {"number": int(m), "keyword": keyword} for m in matches
                    ]
                break

        return attachments
