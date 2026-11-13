#!/usr/bin/env bash

set -euo pipefail

OUTPUT="dependency_forensics_report.txt"

echo "==================================================" > "$OUTPUT"
echo "MAHOUN DEPENDENCY FORENSICS REPORT" >> "$OUTPUT"
echo "==================================================" >> "$OUTPUT"
echo "Generated: $(date -Iseconds)" >> "$OUTPUT"
echo "" >> "$OUTPUT"

# ==================================================
# 1. IMPORT GRAPH
# ==================================================

echo "==================================================" >> "$OUTPUT"
echo "[1] IMPORT GRAPH" >> "$OUTPUT"
echo "==================================================" >> "$OUTPUT"

grep -RhoP '^from\s+\K[\w\.]+' mahoun api tests scripts 2>/dev/null | \
sort | uniq -c | sort -nr >> "$OUTPUT" || true

echo "" >> "$OUTPUT"

grep -RhoP '^import\s+\K[\w\.]+' mahoun api tests scripts 2>/dev/null | \
sort | uniq -c | sort -nr >> "$OUTPUT" || true

echo "" >> "$OUTPUT"

# ==================================================
# 2. RAW GRAPH ACCESS
# ==================================================

echo "==================================================" >> "$OUTPUT"
echo "[2] RAW GRAPH ACCESS" >> "$OUTPUT"
echo "==================================================" >> "$OUTPUT"

grep -RInE \
"(session\.run|driver\.session|neo4j|GraphDatabase)" \
mahoun api tests \
--include="*.py" >> "$OUTPUT" 2>&1 || true

echo "" >> "$OUTPUT"

# ==================================================
# 3. DIRECT FILESYSTEM COUPLING
# ==================================================

echo "==================================================" >> "$OUTPUT"
echo "[3] FILESYSTEM COUPLING" >> "$OUTPUT"
echo "==================================================" >> "$OUTPUT"

grep -RInE \
"(/home/|Desktop|Documents|Downloads|tmp|temp|backup|archive)" \
mahoun api tests \
--include="*.py" >> "$OUTPUT" 2>&1 || true

echo "" >> "$OUTPUT"

# ==================================================
# 4. PATH MANIPULATION
# ==================================================

echo "==================================================" >> "$OUTPUT"
echo "[4] PATH MANIPULATION" >> "$OUTPUT"
echo "==================================================" >> "$OUTPUT"

grep -RInE \
"(sys\.path|PYTHONPATH|append\(|insert\()" \
mahoun api tests \
--include="*.py" >> "$OUTPUT" 2>&1 || true

echo "" >> "$OUTPUT"

# ==================================================
# 5. DYNAMIC IMPORTS
# ==================================================

echo "==================================================" >> "$OUTPUT"
echo "[5] DYNAMIC IMPORTS" >> "$OUTPUT"
echo "==================================================" >> "$OUTPUT"

grep -RInE \
"(importlib|__import__|exec\(|eval\()" \
mahoun api tests \
--include="*.py" >> "$OUTPUT" 2>&1 || true

echo "" >> "$OUTPUT"

# ==================================================
# 6. GOVERNANCE BYPASS HINTS
# ==================================================

echo "==================================================" >> "$OUTPUT"
echo "[6] GOVERNANCE BYPASS HINTS" >> "$OUTPUT"
echo "==================================================" >> "$OUTPUT"

grep -RInE \
"(skip_validation|disable_governance|bypass|unsafe|TODO|FIXME)" \
mahoun api tests \
--include="*.py" >> "$OUTPUT" 2>&1 || true

echo "" >> "$OUTPUT"

# ==================================================
# 7. ORPHAN PYTHON FILES
# ==================================================

echo "==================================================" >> "$OUTPUT"
echo "[7] POSSIBLE ORPHAN MODULES" >> "$OUTPUT"
echo "==================================================" >> "$OUTPUT"

find mahoun api -name "*.py" | while read -r file; do
    module=$(basename "$file" .py)

    refs=$(grep -R "$module" mahoun api tests scripts 2>/dev/null | wc -l)

    if [ "$refs" -le 1 ]; then
        echo "[ORPHAN?] $file" >> "$OUTPUT"
    fi
done

echo "" >> "$OUTPUT"

# ==================================================
# 8. CIRCULAR IMPORT RISK
# ==================================================

echo "==================================================" >> "$OUTPUT"
echo "[8] CIRCULAR IMPORT RISK" >> "$OUTPUT"
echo "==================================================" >> "$OUTPUT"

grep -RIn "from mahoun" mahoun \
--include="*.py" >> "$OUTPUT" 2>&1 || true

echo "" >> "$OUTPUT"

# ==================================================
# 9. MASSIVE FILES
# ==================================================

echo "==================================================" >> "$OUTPUT"
echo "[9] MASSIVE FILES (>1000 LOC)" >> "$OUTPUT"
echo "==================================================" >> "$OUTPUT"

find mahoun api tests -name "*.py" | while read -r file; do
    lines=$(wc -l < "$file")
    if [ "$lines" -gt 1000 ]; then
        echo "$lines lines - $file" >> "$OUTPUT"
    fi
done

echo "" >> "$OUTPUT"

# ==================================================
# 10. SUMMARY
# ==================================================

RAW_GRAPH=$(grep -ci "session.run" "$OUTPUT" || true)
PATH_MANIP=$(grep -ci "sys.path" "$OUTPUT" || true)
DYNAMIC_IMPORT=$(grep -ci "importlib" "$OUTPUT" || true)
BYPASS=$(grep -ci "bypass" "$OUTPUT" || true)
ORPHANS=$(grep -ci "\[ORPHAN?\]" "$OUTPUT" || true)

RISK=$((RAW_GRAPH*3 + PATH_MANIP*2 + DYNAMIC_IMPORT*2 + BYPASS*5))

echo "==================================================" >> "$OUTPUT"
echo "[10] RISK SUMMARY" >> "$OUTPUT"
echo "==================================================" >> "$OUTPUT"

echo "Raw Graph Access     : $RAW_GRAPH" >> "$OUTPUT"
echo "Path Manipulation    : $PATH_MANIP" >> "$OUTPUT"
echo "Dynamic Imports      : $DYNAMIC_IMPORT" >> "$OUTPUT"
echo "Governance Bypasses  : $BYPASS" >> "$OUTPUT"
echo "Possible Orphans     : $ORPHANS" >> "$OUTPUT"
echo "Risk Score           : $RISK" >> "$OUTPUT"

echo "" >> "$OUTPUT"

echo "=================================================="
echo "DEPENDENCY FORENSICS COMPLETE"
echo "=================================================="
echo "Risk Score: $RISK"
echo "Report:"
echo "$OUTPUT"
echo "=================================================="

echo ""
echo "TOP OFFENDERS:"
echo "=================================================="

grep -Ein \
"(session\.run|driver\.session|sys\.path|importlib|bypass|unsafe)" \
"$OUTPUT" | head -30 || true

echo "=================================================="
