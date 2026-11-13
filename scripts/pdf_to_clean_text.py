#!/usr/bin/env python3
"""
PDF Legal Text Extraction & Cleaning Pipeline (v2 - Hardened)
=============================================================

Converts raw pdftotext output into a clean, parser-ready text format
matching the conventions of LAWS/all_legal_sentences.txt.

Pipeline stages:
  1. Extract raw text from PDF via pdftotext
  2. Unicode NFKC normalization (Arabic Presentation Forms -> standard chars)
  3. Strip RTL/Bidi control characters (preserve semantically meaningful ZWNJ)
  4. Normalize Persian/Arabic digits and letter shapes (ك -> ک, ي -> ی)
  5. Remove recurring headers/footers, metadata noise, page numbers, and form-feeds
  6. Standardize Article/Clause/Chapter header syntax:
     - `ماده -۱` -> `ماده ۱ -`
     - `ماده «-۷` -> `ماده ۷ - «`
     - `ماده ۱ـ` -> `ماده ۱ -`
  7. Deterministic line-merging for wrapped paragraphs
  8. Save clean, canonical text format

Usage:
    python scripts/pdf_to_clean_text.py <input.pdf> <output.txt>
"""

import re
import subprocess
import sys
import unicodedata
from pathlib import Path

# ============================================================================
# 1. Constants & Mappings
# ============================================================================

# Bidi control characters to strip (preserve \u200c ZWNJ)
BIDI_CONTROLS_EXCEPT_ZWNJ = re.compile(
    "[\u200e\u200f\u200b\u200d"          # LRM, RLM, ZWSP, ZWJ
    "\u202a\u202b\u202c\u202d\u202e"     # LRE, RLE, PDF, LRO, RLO
    "\u2066\u2067\u2068\u2069"           # LRI, RLI, FSI, PDI
    "\ufeff]",                            # BOM / ZWNBSP
)

# Page number alone on a line
PAGE_NUMBER_LINE = re.compile(r"^\s*[0-9۰-۹\(\)\-\.\s]+\s*$")

# Recurring running headers / footers to remove
RUNNING_HEADERS = [
    re.compile(r"^\s*قانون\s+تجارت\s*$"),
    re.compile(r"^\s*لایحه\s+تجارت\s*$"),
    re.compile(r"^\s*محمدباقر\s+قالیباف\s*$"),
    re.compile(r"^\s*حضرت\s+آیت[\s‌]*الله\s+احمد\s+جنتی.*$"),
    re.compile(r"^\s*دبیر\s+محترم\s+شورای\s+نگهبان.*$"),
    re.compile(r"^\s*سلام[\s‌]*علیکم.*$"),
    re.compile(r"^\s*عطف\s+به\s+نامه\s+شماره.*$"),
    re.compile(r"^\s*رونوشت\s*:.*$"),
    re.compile(r"^\s*-\s*معاونت\s+محترم\s+قوانین.*$"),
]

# Character mappings
WESTERN_TO_PERSIAN = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
ARABIC_INDIC_TO_PERSIAN = str.maketrans("٠١٢٣٤٥٦٧٨٩", "۰۱۲۳۴۵۶۷۸۹")
ARABIC_TO_PERSIAN_LETTERS = str.maketrans({
    "\u0643": "\u06a9",  # ك -> ک
    "\u064a": "\u06cc",  # ي -> ی
    "\u0649": "\u06cc",  # ى -> ی
})

# Structural entity starts
STRUCTURAL_LINE = re.compile(
    r"^(ماده|اصل|تبصره|بند|فصل|باب|بخش|مبحث|گفتار|کتاب|قانون)\s",
    re.IGNORECASE,
)

# Article normalization pattern
# Matches: ماده -۱, ماده ۱ـ, ماده «-۷, ماده ۱ -, ماده-۱
P_ARTICLE_SYNTAX = re.compile(
    r"^(ماده|اصل)\s*[«\"'\(\[\{]?\s*[\-ـ–—]?\s*([۰-۹0-9]+)\s*[»\"'\)\]\}]?\s*[\-ـ–—:]?\s*",
)

# Clause / Note pattern
P_CLAUSE_SYNTAX = re.compile(
    r"^(تبصره)\s*[«\"'\(\[\{]?\s*[\-ـ–—]?\s*([۰-۹0-9]*)\s*[»\"'\)\]\}]?\s*[\-ـ–—:]?\s*",
)


# ============================================================================
# 2. Pipeline Functions
# ============================================================================

def extract_pdf_text(pdf_path: Path) -> str:
    """Run pdftotext and capture output."""
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pdftotext failed: {result.stderr}")
    return result.stdout


def normalize_unicode(text: str) -> str:
    """NFKC normalization: Arabic Presentation Forms -> standard characters."""
    return unicodedata.normalize("NFKC", text)


def strip_bidi_controls(text: str) -> str:
    """Remove RTL/Bidi control characters but preserve ZWNJ."""
    return BIDI_CONTROLS_EXCEPT_ZWNJ.sub("", text)


def normalize_digits_and_letters(text: str) -> str:
    """Normalize Western/Arabic digits and Persian letter variants."""
    text = text.translate(WESTERN_TO_PERSIAN)
    text = text.translate(ARABIC_INDIC_TO_PERSIAN)
    text = text.translate(ARABIC_TO_PERSIAN_LETTERS)
    return text


def is_running_header(line: str) -> bool:
    """Detect noise running headers / signatures."""
    for p in RUNNING_HEADERS:
        if p.match(line):
            return True
    return False


def standardize_line_header(line: str) -> str:
    """Standardize article and clause syntax at start of line."""
    m_art = P_ARTICLE_SYNTAX.match(line)
    if m_art:
        art_type = m_art.group(1)
        art_num = m_art.group(2)
        rest = line[m_art.end():].strip()
        return f"{art_type} {art_num} - {rest}".strip()

    m_cls = P_CLAUSE_SYNTAX.match(line)
    if m_cls:
        cls_type = m_cls.group(1)
        cls_num = m_cls.group(2).strip()
        rest = line[m_cls.end():].strip()
        if cls_num:
            return f"{cls_type} {cls_num} - {rest}".strip()
        return f"{cls_type} - {rest}".strip()

    return line


_WRAPPED_CITATION_LINKERS = (
    "برخلاف",
    "خلاف",
    "موافق",
    "مقررات",
    "رعایت",
    "مطابق",
    "موضوع",
    "بموجب",
    "به موجب",
    "موجب",
    "طبق",
    "مستند",
    "مستفاد",
    "مندرج در",
    "مذکور در",
    "مذکوردر",
    "از حیث",
    "به استناد",
    "باستناد",
    "که",
)


def is_wrapped_mid_sentence_citation(prev_line: str, next_line: str) -> bool:
    """Return True if next_line starts with an inline citation continuing prev_line."""
    if not prev_line or not next_line:
        return False
    prev_clean = prev_line.replace("\u0640", "").rstrip()
    if not prev_clean or prev_clean.endswith((".", "؟", "!", "؛", ":", ")")):
        return False
    prev_word = prev_clean.rstrip("،,ـ ").strip()
    linker_match = any(
        prev_word == linker
        or prev_word.endswith(" " + linker)
        or prev_word.endswith("\u200c" + linker)
        for linker in _WRAPPED_CITATION_LINKERS
    )
    if not linker_match:
        return False
    return bool(re.match(r"^(?:ماده|اصل|قانون)\s+[۰-۹0-9]+", next_line.replace("\u0640", "").lstrip()))


def clean_raw_page_lines(raw_text: str) -> list[str]:
    """Process page by page to cleanly separate pages and avoid dangling mergers."""
    # Split by form-feed \f (each page in pdftotext is separated by \f)
    pages = raw_text.split("\f")
    cleaned_lines = []

    for page_idx, page in enumerate(pages):
        page_lines = page.split("\n")
        page_clean = []

        for raw_line in page_lines:
            line = raw_line.strip()
            # Collapse internal multi-spaces
            line = re.sub(r" {2,}", " ", line)
            if not line:
                continue

            # Strip page number lines
            if PAGE_NUMBER_LINE.match(line) and len(line) <= 6:
                continue

            # Strip running headers/footers
            if is_running_header(line):
                continue

            # Preserve wrapped mid-sentence cross-references as body continuations
            if not (page_clean and is_wrapped_mid_sentence_citation(page_clean[-1], line)):
                # Standardize article/clause syntax
                line = standardize_line_header(line)

            page_clean.append(line)

        # Merge broken lines strictly within the current page
        merged_page = merge_page_lines(page_clean)
        cleaned_lines.extend(merged_page)

    return cleaned_lines


def is_structural_start(line: str) -> bool:
    """Detect structural headers that must start a new block."""
    if STRUCTURAL_LINE.match(line):
        return True
    # Numbered items: ۱ - , ۲ - , ۱ ـ
    if re.match(r"^[۰-۹0-9]+\s*[\-ـ–—\.]\s*", line):
        return True
    return False


def merge_page_lines(lines: list[str]) -> list[str]:
    """Merge lines within a single page so paragraphs stay intact."""
    if not lines:
        return lines

    merged = [lines[0]]
    for line in lines[1:]:
        prev = merged[-1]

        # Never merge into a new structural element, except wrapped inline citations
        if is_structural_start(line) and not is_wrapped_mid_sentence_citation(prev, line):
            merged.append(line)
            continue

        # If previous line does NOT end with sentence terminator, merge
        if not prev.rstrip().endswith((".", "؟", "!", "؛", ":")):
            merged[-1] = prev + " " + line
        else:
            merged.append(line)

    return merged


# ============================================================================
# 3. Main Pipeline Runner
# ============================================================================

def process_pdf(pdf_path: Path, output_path: Path) -> dict:
    """Full extraction and normalization pipeline."""
    print("\n╭──────────────────────────────────────────────────────────────────────╮")
    print("│ MAHOUN • PDF LEGAL TEXT CLEANER                                     │")
    print("├──────────────────────────────────────────────────────────────────────┤")
    print(f"│ Input : {pdf_path.name:<59} │")
    raw_text = extract_pdf_text(pdf_path)

    print("│ [1/5] Unicode NFKC normalization                                  │")
    text = normalize_unicode(raw_text)

    print("│ [2/5] Removing bidi control characters                            │")
    text = strip_bidi_controls(text)

    print("│ [3/5] Normalizing Persian digits and letter shapes                │")
    text = normalize_digits_and_letters(text)

    print("│ [4/5] Filtering page noise and standardizing structure            │")
    clean_lines = clean_raw_page_lines(text)

    print("│ [5/5] Writing clean corpus                                          │")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for line in clean_lines:
            f.write(line + "\n")

    # Quality check metrics
    art_matches = [l for l in clean_lines if re.match(r"^(ماده|اصل)\s+[۰-۹0-9]+", l)]
    ch_matches = [l for l in clean_lines if re.match(r"^(فصل|باب|بخش|مبحث|گفتار|کتاب)\s", l)]
    cls_matches = [l for l in clean_lines if re.match(r"^(تبصره|بند)\s", l)]

    print("├──────────────────────────────────────────────────────────────────────┤")
    print(f"│ Output: {str(output_path)[:57]:<57} │")
    print(f"│ Lines: {len(clean_lines):<59} │")
    print(f"│ Articles: {len(art_matches):<56} │")
    print(f"│ Chapters: {len(ch_matches):<56} │")
    print(f"│ Clauses: {len(cls_matches):<57} │")
    print("╰──────────────────────────────────────────────────────────────────────╯\n")

    return {
        "file": pdf_path.name,
        "total_lines": len(clean_lines),
        "articles": len(art_matches),
        "chapters": len(ch_matches),
        "clauses": len(cls_matches),
    }


def main():
    if len(sys.argv) != 3:
        print("Usage: python scripts/pdf_to_clean_text.py <input.pdf> <output.txt>")
        sys.exit(1)

    pdf_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    if not pdf_path.exists():
        print(f"❌ File not found: {pdf_path}")
        sys.exit(1)

    process_pdf(pdf_path, output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
