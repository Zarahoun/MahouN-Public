"""
Prepare Clean Banking Laws Corpus
=================================
Processes 'LAWS/qavanin-poli-banki/polivabanki.txt' and splits it into two validated,
clean legal text files ready for deterministic parsing and Neo4j compilation:
1. data/monetary_banking_1351_clean.txt (قانون پولی و بانکی کشور مصوب ۱۳۵۱) - 45 Articles
2. data/central_bank_1402_clean.txt (قانون بانک مرکزی ایران مصوب ۱۴۰۲) - 67 Articles
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_PATH = REPO_ROOT / "LAWS" / "qavanin-poli-banki" / "polivabanki.txt"


def clean_law1(lines: list) -> list:
    cleaned = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            cleaned.append("")
            i += 1
            continue

        # Skip raw metadata repeal tags
        if line.startswith("نسخ‌صریح") or line.startswith("نسخ صریح"):
            i += 1
            continue

        # Detect missing "ماده ۳۱ -" header before line 682: "الف - تشکیل بانک فقط بصورت شرکت سهامی عام..."
        if "تشکیل بانک فقط بصورت شرکت سهامی عام" in line and not any("ماده ۳۱" in c or "ماده 31" in c for c in cleaned[-10:]):
            cleaned.append("ماده ۳۱ - تشکیل و اداره بانک‌ها")

        # Normalize Article headers
        line = re.sub(r'^(ماده)\s*(\d+|[الف-ی]+)\s*[\-ـ:]*\s*', r'\1 \2 - ', line)

        # Normalize Chapter headers
        line = re.sub(r'^(قسمت|فصل|بخش|باب)\s+([^\-–:]+)\s*[\-ـ:]*\s*(.*)', r'\1 \2 - \3', line)

        cleaned.append(line)
        i += 1

    return cleaned


def clean_law2(lines: list) -> list:
    cleaned = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            cleaned.append("")
            i += 1
            continue

        # Normalize Article headers (including ZWNJ and attached digits)
        line = re.sub(r'^(ماده)\s*[\u200c\s]*(\d+|[الف-ی]+)\s*[\-ـ:]*\s*', r'\1 \2 - ', line)

        # Normalize Chapter headers
        line = re.sub(r'^(فصل|بخش|باب)\s+([^:\-–]+)[:\-–ـ]\s*(.*)', r'\1 \2 - \3', line)

        cleaned.append(line)
        i += 1

    return cleaned


def main():
    print(f"Reading source from {SOURCE_PATH}...")
    with open(SOURCE_PATH, "r", encoding="utf-8") as f:
        text = f.read()

    lines = text.splitlines()

    law1_raw = lines[:845]
    law2_raw = lines[845:]

    law1_clean = clean_law1(law1_raw)
    law2_clean = clean_law2(law2_raw)

    out1 = REPO_ROOT / "data" / "monetary_banking_1351_clean.txt"
    out2 = REPO_ROOT / "data" / "central_bank_1402_clean.txt"

    out1.write_text("\n".join(law1_clean), encoding="utf-8")
    out2.write_text("\n".join(law2_clean), encoding="utf-8")

    # Verification
    arts1 = [l for l in law1_clean if re.match(r"^ماده\s+(\d+|[الف-ی]+)\s*-", l)]
    arts2 = [l for l in law2_clean if re.match(r"^ماده\s+(\d+|[الف-ی]+)\s*-", l)]

    print("==================================================")
    print("Corpus Preparation Complete:")
    print(f"  Law 1 (1351): {len(law1_clean)} lines, {len(arts1)} Articles -> {out1.name}")
    print(f"  Law 2 (1402): {len(law2_clean)} lines, {len(arts2)} Articles -> {out2.name}")
    print("==================================================")


if __name__ == "__main__":
    main()
