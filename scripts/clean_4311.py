#!/usr/bin/env python3
"""
Cleaner & Normalizer for Nashrieh 4311 (شرایط عمومی پیمان)
=========================================================
Extracts raw text from 4311-word.doc, performs Unicode NFKC
normalization, Persian character & digit mapping, paragraph
unwrapping, and header standardizing for LegalCorpusParser.
"""

import re
import subprocess
import sys
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Character mappings
TRANS_MAP = str.maketrans({
    "ك": "ک",
    "ي": "ی",
    "ى": "ی",
    "ئ": "ی",
    "ة": "ه",
    "0": "۰", "1": "۱", "2": "۲", "3": "۳", "4": "۴",
    "5": "۵", "6": "۶", "7": "۷", "8": "۸", "9": "۹",
})

BIDI_CONTROLS = re.compile(
    "[\u200e\u200f\u200b\u200d\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\ufeff]"
)


def extract_doc_text(doc_path: Path) -> str:
    res = subprocess.run(["catdoc", "-d", "utf-8", str(doc_path)], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"catdoc failed: {res.stderr}")
    return res.stdout


def clean_and_standardize(raw_text: str) -> list[str]:
    # 1. NFKC & Bidi
    nfkc = unicodedata.normalize("NFKC", raw_text)
    nobidi = BIDI_CONTROLS.sub("", nfkc)
    text = nobidi.translate(TRANS_MAP)

    lines = [l.strip() for l in text.splitlines()]

    # Structural start regex
    p_chap = re.compile(r"^(فصل\s+[^\n\-–:]+)", re.IGNORECASE)
    p_art = re.compile(r"^ماده\s*([۰-۹]+)\s*[\.:\-ـ]?\s*(.*)", re.IGNORECASE)
    p_clause = re.compile(r"^(تبصره\s*[۰-۹]*|بند\s*[الف-ی۰-۹]+|\([الف-ی۰-۹]+\)|[الف-ی۰-۹]+\s*[\-\)])", re.IGNORECASE)

    output = []
    # Add law title header
    output.append("شرایط عمومی پیمان )نشریه ۴۳۱۱ سازمان برنامه و بودجه(")
    output.append("مصوب سازمان مدیریت و برنامه ریزی کشور")

    i = 0
    while i < len(lines):
        line = lines[i]
        if not line:
            i += 1
            continue

        # Check if chapter
        m_chap = p_chap.match(line)
        if m_chap:
            chap_title = line
            # Look ahead for subtitle
            if i + 1 < len(lines) and not p_art.match(lines[i + 1]) and not p_chap.match(lines[i + 1]):
                if len(lines[i + 1]) < 80:
                    i += 1
                    chap_title += " - " + lines[i]
            output.append(chap_title)
            i += 1
            continue

        # Check if article header
        m_art = p_art.match(line)
        if m_art:
            art_num = m_art.group(1)
            art_rest = m_art.group(2).strip()

            # Ensure proper header format: ماده X - عنوان
            if art_rest:
                header = f"ماده {art_num} - {art_rest}"
            else:
                header = f"ماده {art_num} -"
            output.append(header)
            i += 1
            continue

        # Normal text or clause: merge wrapped lines
        buf = line
        while i + 1 < len(lines):
            nxt = lines[i + 1]
            if not nxt:
                break
            if p_chap.match(nxt) or p_art.match(nxt) or p_clause.match(nxt):
                break
            # If current buffer doesn't end with sentence terminator, merge
            if not buf.rstrip().endswith((".", ":", "؛", "!", "؟")):
                buf += " " + nxt
                i += 1
            else:
                break

        output.append(buf)
        i += 1

    return output


def main():
    doc_path = REPO_ROOT / "4311-word.doc"
    out_path = REPO_ROOT / "data" / "nashrieh_4311_clean.txt"

    print(f"📄 Extracting text from {doc_path.name}...")
    raw = extract_doc_text(doc_path)

    print("🧹 Cleaning, normalizing and formatting lines...")
    clean_lines = clean_and_standardize(raw)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for l in clean_lines:
            f.write(l + "\n")

    print(f"💾 Written {len(clean_lines)} lines to {out_path}")
    articles = [l for l in clean_lines if re.match(r"^ماده\s+[۰-۹]+", l)]
    chapters = [l for l in clean_lines if re.match(r"^فصل\s+", l)]
    print(f"📊 Audit: {len(articles)} articles, {len(chapters)} chapters found.")


if __name__ == "__main__":
    main()
