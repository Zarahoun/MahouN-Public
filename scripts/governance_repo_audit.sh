#!/usr/bin/env bash

# =========================================================
# MAHOUN REPOSITORY CONTAMINATION AUDIT
# Governance / Archive / Backup Isolation Scanner
# =========================================================

set -euo pipefail

ROOT_DIR="$(pwd)"
OUTPUT_FILE="governance_repo_audit_report.txt"

echo "==================================================" > "$OUTPUT_FILE"
echo "MAHOUN GOVERNANCE REPOSITORY AUDIT REPORT" >> "$OUTPUT_FILE"
echo "==================================================" >> "$OUTPUT_FILE"
echo "Generated: $(date -Iseconds)" >> "$OUTPUT_FILE"
echo "Root: $ROOT_DIR" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

# =========================================================
# SECTION 1 - DETECT ARCHIVE / BACKUP DIRECTORIES
# =========================================================

echo "==================================================" >> "$OUTPUT_FILE"
echo "[1] ARCHIVE / BACKUP / SNAPSHOT DIRECTORIES" >> "$OUTPUT_FILE"
echo "==================================================" >> "$OUTPUT_FILE"

find . -type d \( \
-name "*backup*" -o \
-name "*archive*" -o \
-name "*snapshot*" -o \
-name "Mahoun_v2*" -o \
-name "kingmahoun*" \
\) >> "$OUTPUT_FILE" 2>&1 || true

echo "" >> "$OUTPUT_FILE"

# =========================================================
# SECTION 2 - SEARCH FOR DANGEROUS REFERENCES
# =========================================================

echo "==================================================" >> "$OUTPUT_FILE"
echo "[2] DANGEROUS REFERENCE SCAN" >> "$OUTPUT_FILE"
echo "==================================================" >> "$OUTPUT_FILE"

grep -RInE \
"(backup|archive|snapshot|Mahoun_v2|kingmahoun)" \
mahoun/ api/ tests/ scripts/ \
--include="*.py" >> "$OUTPUT_FILE" 2>&1 || true

echo "" >> "$OUTPUT_FILE"

# =========================================================
# SECTION 3 - IMPORT/PATH MANIPULATION
# =========================================================

echo "==================================================" >> "$OUTPUT_FILE"
echo "[3] IMPORT PATH MANIPULATION SCAN" >> "$OUTPUT_FILE"
echo "==================================================" >> "$OUTPUT_FILE"

grep -RInE \
"(sys\.path|PYTHONPATH|append\(|insert\()" \
mahoun/ api/ tests/ \
--include="*.py" >> "$OUTPUT_FILE" 2>&1 || true

echo "" >> "$OUTPUT_FILE"

# =========================================================
# SECTION 4 - HARDCODED ABSOLUTE PATHS
# =========================================================

echo "==================================================" >> "$OUTPUT_FILE"
echo "[4] HARDCODED PATH SCAN" >> "$OUTPUT_FILE"
echo "==================================================" >> "$OUTPUT_FILE"

grep -RInE \
"(/home/haji|Desktop|Documents|backup|archive|snapshot)" \
mahoun/ api/ tests/ \
--include="*.py" >> "$OUTPUT_FILE" 2>&1 || true

echo "" >> "$OUTPUT_FILE"

# =========================================================
# SECTION 5 - RAW NEO4J ACCESS
# =========================================================

echo "==================================================" >> "$OUTPUT_FILE"
echo "[5] RAW NEO4J ACCESS SCAN" >> "$OUTPUT_FILE"
echo "==================================================" >> "$OUTPUT_FILE"

grep -RInE \
"(session\.run\(|driver\.session\(|\.run\()" \
mahoun/ api/ tests/ \
--include="*.py" >> "$OUTPUT_FILE" 2>&1 || true

echo "" >> "$OUTPUT_FILE"

# =========================================================
# SECTION 6 - GOVERNANCE CONTEXT BYPASS
# =========================================================

echo "==================================================" >> "$OUTPUT_FILE"
echo "[6] GOVERNANCE CONTEXT BYPASS SCAN" >> "$OUTPUT_FILE"
echo "==================================================" >> "$OUTPUT_FILE"

grep -RInE \
"(GovernanceContextManager\._local_context|bypass|disable_governance|skip_validation)" \
mahoun/ api/ tests/ \
--include="*.py" >> "$OUTPUT_FILE" 2>&1 || true

echo "" >> "$OUTPUT_FILE"

# =========================================================
# SECTION 7 - GIT STATUS
# =========================================================

echo "==================================================" >> "$OUTPUT_FILE"
echo "[7] GIT STATUS" >> "$OUTPUT_FILE"
echo "==================================================" >> "$OUTPUT_FILE"

git status >> "$OUTPUT_FILE" 2>&1 || true

echo "" >> "$OUTPUT_FILE"

# =========================================================
# SECTION 8 - SUMMARY
# =========================================================

echo "==================================================" >> "$OUTPUT_FILE"
echo "[8] AUDIT COMPLETE" >> "$OUTPUT_FILE"
echo "==================================================" >> "$OUTPUT_FILE"

echo "Audit completed at: $(date -Iseconds)" >> "$OUTPUT_FILE"

echo ""
echo "=================================================="
echo "MAHOUN GOVERNANCE AUDIT COMPLETE"
echo "=================================================="
echo "Report saved to:"
echo "$OUTPUT_FILE"
echo "=================================================="
