#!/bin/bash
#
# Gate 4b: Frontend Anti-Mock / Fabrication Detection
# ====================================================
# Extends Gate 4 (Python AST anti-mock) to the frontend.
#
# Catches the exact AIChat.tsx pattern that Gate 4's Python-only AST walk
# could never see: a multi-line hardcoded string returned via a fake
# setTimeout "streaming" loop with hardcoded confidence/citations, while
# the file declares an API intent it never honors.
#
# Layers (zero-tolerance = nonzero exit on first match):
#   B1. Fabrication-marker grep — high-precision phrases that match the
#       known AIChat.tsx problem. Zero tolerance.
#   B2. API-import-without-real-call heuristic — .ts/.tsx under
#       components/ and pages/ that import from ../api/ but contain no
#       fetch/useQuery/useMutation/*Client.* call. WARNINGS, not failures
#       (legitimate reasons exist), but the list is surfaced for review.
#   B3. Suppression marker:  // fabrication-check-ok: <one-line reason>
#       The reason is MANDATORY. A bare suppression fails the gate.
#       Every active suppression is logged so reviewers see them.
#
# This script does NOT early-exit on a single violation; it accumulates
# and reports all findings (matches validate_governance_compliance.py and
# gate_4 style) so one fabrication problem does not hide another.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "================================================"
echo "🔍 Gate 4b: Frontend Anti-Mock / Fabrication Check"
echo "================================================"
echo ""

cd "${PROJECT_ROOT}"

FRONTEND_SRC="${MAHOUN_FRONTEND_SRC:-${PROJECT_ROOT}/frontend/src}"

if [ ! -d "${FRONTEND_SRC}" ]; then
    echo -e "${YELLOW}⚠️  frontend/src not found — skipping frontend antimock${NC}"
    exit 0
fi

VIOLATIONS=0
WARNINGS=0
SUPPRESSIONS_LOG="/tmp/gate4b_suppressions_$$.txt"
VIOLATIONS_LOG="/tmp/gate4b_violations_$$.txt"
WARNINGS_LOG="/tmp/gate4b_warnings_$$.txt"
: > "${SUPPRESSIONS_LOG}"
: > "${VIOLATIONS_LOG}"
: > "${WARNINGS_LOG}"

# ---------------------------------------------------------------------------
# Suppression helpers
# ---------------------------------------------------------------------------

# Print reason after the marker; fail if missing.
# Reads a single line on stdin; echoes the reason (stripped) or "NO_REASON".
extract_suppression_reason() {
    local line="$1"
    # Match: optional whitespace, //, optional whitespace, marker, colon, optional reason
    local reason="${line#*fabrication-check-ok:}"
    # If the strip did nothing, the marker had no colon.
    if [ "$reason" = "$line" ]; then
        echo "NO_COLON"
        return
    fi
    reason="$(echo "$reason" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
    if [ -z "$reason" ]; then
        echo "NO_REASON"
        return
    fi
    echo "$reason"
}

# Does this file path qualify for the static-text exemptions?
is_exempt_by_path() {
    local rel="$1"
    case "$rel" in
        test/*) return 0 ;;
        */test/*) return 0 ;;
    esac
    # Filename-based exemptions (legitimate static UI text)
    local basename
    basename="$(basename "$rel")"
    case "$basename" in
        *constants*|*copy*|*strings*|*i18n*) return 0 ;;
    esac
    return 1
}

# ---------------------------------------------------------------------------
# B1 — Fabrication-marker grep (zero tolerance)
# ---------------------------------------------------------------------------
echo "📋 B1: Scanning frontend/src for fabrication markers..."

# Collect candidate files: .ts/.tsx under frontend/src, minus exempt paths.
# Each line of CANDIDATES_FILE is "<abs>|<rel>" so loops can use both even
# when FRONTEND_SRC is outside PROJECT_ROOT (test fixtures live in /tmp).
CANDIDATES_FILE="/tmp/gate4b_candidates_$$.txt"
: > "${CANDIDATES_FILE}"
while IFS= read -r -d '' f; do
    rel="${f#${FRONTEND_SRC}/}"
    if is_exempt_by_path "$rel"; then continue; fi
    printf '%s|%s\n' "$f" "$rel" >> "${CANDIDATES_FILE}"
done < <(find "${FRONTEND_SRC}" -type f \( -name '*.ts' -o -name '*.tsx' \) -print0)

# Map: rel -> abs (for B1/B3 worker loops)
declare -A ABS_OF
# Map: per-file set of suppressed line numbers (from B3 markers).
declare -A SUPPRESSED_LINES

while IFS='|' read -r abs rel; do
    [ -z "$rel" ] && continue
    ABS_OF["$rel"]="$abs"
    supps=""

    # Read line numbers of any suppression markers in this file.
    SUPPRESSED_LINES["$rel"]=""
    while IFS=: read -r sl _; do
        [ -z "$sl" ] && continue
        # Validate mandatory reason.
        line_text="$(sed -n "${sl}p" "${abs}")"
        reason="$(extract_suppression_reason "${line_text}")"
        if [ "$reason" = "NO_COLON" ] || [ "$reason" = "NO_REASON" ]; then
            echo -e "${RED}❌ B3: suppression marker in ${rel}:${sl} has NO reason (required)${NC}" | tee -a "${VIOLATIONS_LOG}"
            VIOLATIONS=$((VIOLATIONS+1))
            continue
        fi
        echo "${rel}:${sl} :: ${reason}" >> "${SUPPRESSIONS_LOG}"
        SUPPRESSED_LINES["$rel"]="${SUPPRESSED_LINES[$rel]} ${sl}"
    done < <(grep -nE '//[[:space:]]*fabrication-check-ok' "${abs}" 2>/dev/null || true)
done < "${CANDIDATES_FILE}"

# Run the marker patterns. We grep each file individually so we can apply
# per-line suppression and proximité logic for the confidence/citations rule.
# Zero-tolerance markers: precise multi-word phrases. The single-word terms
# (placeholder, hardcoded, fake response) are intentionally NOT standalone
# markers — they fire too often on legitimate HTML placeholder= attributes
# and Tailwind placeholder-* classes. They are only enforced via the
# proximity rule below (next to confidence:/citations:).
MARKER_PATTERNS=(
    -e 'Simulate streaming'
    -e 'Mock Graph Data'
    -e 'replace with actual API call'
    -e 'replace with real'
)

# Standalone proximity trigger words (handled separately below, NOT here).
PROXIMITY_WORDS='placeholder|hardcoded|fake response'

while IFS='|' read -r abs rel; do
    [ -z "$rel" ] && continue
    supps="${SUPPRESSED_LINES[$rel]:-}"
    while IFS= read -r lineinfo; do
        [ -z "$lineinfo" ] && continue
        # lineinfo format from grep -n: "<lineno>:<content>"
        ln="${lineinfo%%:*}"
        content="${lineinfo#*:}"
        # Skip if this exact line is suppressed.
        case " $supps " in
            *" $ln "*) continue ;;
        esac
        echo -e "${RED}❌ B1: fabrication marker in ${rel}:${ln}:${NC} ${content}" | tee -a "${VIOLATIONS_LOG}"
        VIOLATIONS=$((VIOLATIONS+1))
    done < <(grep -niE "${MARKER_PATTERNS[@]}" "${abs}" 2>/dev/null || true)
done < "${CANDIDATES_FILE}"

# Proximity rule: placeholder/hardcoded/fake response adjacent to
# confidence: or citations: within 10 lines in the same file.
while IFS='|' read -r abs rel; do
    [ -z "$rel" ] && continue
    supps="${SUPPRESSED_LINES[$rel]:-}"
    # Find any line with confidence: or citations:
    while IFS= read -r ccline; do
        [ -z "$ccline" ] && continue
        cln="${ccline%%:*}"
        # Window ±10 lines
        lo=$((cln-10 < 1 ? 1 : cln-10))
        hi=$((cln+10))
        window_lines="$(sed -n "${lo},${hi}p" "${abs}")"
        if echo "$window_lines" | grep -qiE "${PROXIMITY_WORDS}"; then
            # Only flag if the candidate line (in window) is not suppressed.
            flagged=no
            while IFS= read -r wlineno; do
                [ -z "$wlineno" ] && continue
                case " $supps " in
                    *" $wlineno "*) continue ;;
                esac
                cnt="$(sed -n "${wlineno}p" "${abs}")"
                if echo "$cnt" | grep -qiE "${PROXIMITY_WORDS}"; then
                    # Exclude legitimate HTML: placeholder="..." attribute
                    # values and Tailwind placeholder-* utility classes
                    # stand alone (no nearby confidence:/citations:). Strip
                    # those forms first; if any trigger token remains, flag it.
                    stripped="$(echo "$cnt" | sed -E 's/placeholder-[A-Za-z0-9:.-]+//g; s/placeholder="[^"]*"//g; s/placeholder='\''[^'\'']*'\''//g')"
                    if echo "$stripped" | grep -qiE "${PROXIMITY_WORDS}"; then
                        echo -e "${RED}❌ B1: fabrication near confidence/citations in ${rel}:${wlineno}:${NC} ${cnt}" | tee -a "${VIOLATIONS_LOG}"
                        VIOLATIONS=$((VIOLATIONS+1))
                        flagged=yes
                    fi
                fi
            done < <(seq "${lo}" "${hi}")
            : "$flagged"
        fi
    done < <(grep -nE '(confidence:|citations:)' "${abs}" 2>/dev/null || true)
done < "${CANDIDATES_FILE}"

echo ""

# ---------------------------------------------------------------------------
# B2 — API-import without real call (warnings)
# ---------------------------------------------------------------------------
echo "📋 B2: Checking components/pages importing from ../api/ for real calls..."

REAL_CALL_RX='(fetch\(|\.then\(|await [A-Za-z_$][A-Za-z0-9_$]*\.[A-Za-z_$][A-Za-z0-9_$]*\(|await [A-Za-z_$][A-Za-z0-9_$]*\(|useQuery\(|useMutation\(|useSWR\(|swr\()'

while IFS='|' read -r abs rel; do
    [ -z "$rel" ] && continue
    # rel is relative to the configured frontend src. Decide if it's under
    # components/ or pages/.
    case "$rel" in
        components/*) ;;
        pages/*) ;;
        *) continue ;;
    esac
    # Only files that import from ../api/ .
    if ! grep -qE "from ['\"]\.\.?/.*api" "${abs}" 2>/dev/null \
       && ! grep -qE "from ['\"]@/api" "${abs}" 2>/dev/null; then
        continue
    fi
    # Whole-file suppression: a "fabrication-check-ok: <reason>" anywhere in
    # the file that names B2 exempts the file from B2 warnings.
    if grep -qE '//[[:space:]]*fabrication-check-ok:.*B2' "${abs}" 2>/dev/null; then
        continue
    fi
    if ! grep -qE "${REAL_CALL_RX}" "${abs}" 2>/dev/null; then
        echo -e "${YELLOW}⚠️  B2: ${rel} imports from ../api/ but contains no real network call${NC}" | tee -a "${WARNINGS_LOG}"
        WARNINGS=$((WARNINGS+1))
    fi
done < "${CANDIDATES_FILE}"

# ---------------------------------------------------------------------------
# B3 — Report suppressions (already validated above; just echo here)
# ---------------------------------------------------------------------------
echo ""
echo "📋 B3: Active suppressions:"
if [ -s "${SUPPRESSIONS_LOG}" ]; then
    while IFS= read -r sline; do
        echo -e "   ${YELLOW}suppress ${sline}${NC}"
    done < "${SUPPRESSIONS_LOG}"
else
    echo -e "   ${GREEN}(none)${NC}"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "================================================"
echo -e "${YELLOW}   Warnings (B2): ${WARNINGS}${NC}"
echo -e "${RED}   Violations (B1/B3): ${VIOLATIONS}${NC}"
echo "================================================"

rm -f "${SUPPRESSIONS_LOG}" "${VIOLATIONS_LOG}" "${WARNINGS_LOG}" "${CANDIDATES_FILE}"

if [ "${VIOLATIONS}" -eq 0 ]; then
    echo -e "${GREEN}✅ Gate 4b: PASSED${NC}"
    echo "Frontend fabrication check complete. Warnings (${WARNINGS}) are advisory only."
    exit 0
else
    echo -e "${RED}❌ Gate 4b: FAILED${NC}"
    echo "Found ${VIOLATIONS} hard violation(s) and ${WARNINGS} warning(s)."
    echo ""
    echo "Hard violations indicate fabrication patterns (hardcoded responses, fake"
    echo "streaming, mock data presented as real output)."
    echo "To suppress a legitimate case, add a marker WITH a reason:"
    echo "    // fabrication-check-ok: <one-line mandatory reason>"
    echo "Reasons like 'placeholder for now' are NOT acceptable."
    exit 1
fi
