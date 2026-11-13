#!/bin/bash
#
# Gate 10: Constitutional Integrity Verification (Hardened)
# ========================================================
# Anti-tampering design per Amendment C:
# - Manifest file itself is part of the verified surface
# - A SEAL file records the initial manifest hash at bootstrap
# - Any change to manifest without explicit approval = FAIL
# - Approval authorizes EXACTLY one constitutional state (one-shot)
# - Deterministic hashing: recursive find, sorted paths, stable representation
#
# This gate MUST NOT run in pre-commit (blocks local edits before PR).
# It belongs in pre-push / CI pipeline only.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Colors (matching gate_9_governance.sh style)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "================================================"
echo "📜 Gate 10: Constitutional Integrity Check"
echo "================================================"
echo ""

cd "${PROJECT_ROOT}"

CONST_DIR="mahoun/constitutional"
MANIFEST_FILE="${SCRIPT_DIR}/.constitutional_manifest.sha256"
SEAL_FILE="${SCRIPT_DIR}/.constitutional_manifest.seal"
APPROVAL_FILE="${SCRIPT_DIR}/.constitutional_change_approved"

# ---------------------------------------------------------------------------
# Deterministic manifest computation (Amendment C5)
# ---------------------------------------------------------------------------
if [ ! -d "${CONST_DIR}" ]; then
    echo -e "${RED}❌ CRITICAL: ${CONST_DIR} not found${NC}"
    exit 1
fi

# Compute current manifest: per-file "hash  path" lines, sorted by path.
# Uses find -print0 | sort -z for deterministic ordering across runs.
CURRENT_MANIFEST="/tmp/constitutional_current_$$.txt"
: > "${CURRENT_MANIFEST}"
while IFS= read -r -d '' mdfile; do
    rel="${mdfile#${PROJECT_ROOT}/}"
    h=$(sha256sum "${mdfile}" | awk '{print $1}')
    printf '%s  %s\n' "${h}" "${rel}" >> "${CURRENT_MANIFEST}"
done < <(find "${CONST_DIR}" -type f -name '*.md' -print0 | sort -z)

# Combined hash of the manifest (canonical for change detection)
CURRENT_HASH=$(sha256sum "${CURRENT_MANIFEST}" | awk '{print $1}')

# Also hash the manifest file itself (anti-tampering: detects manifest edits)
MANIFEST_CONTENT_HASH=""
if [ -f "${MANIFEST_FILE}" ]; then
    MANIFEST_CONTENT_HASH=$(sha256sum "${MANIFEST_FILE}" | awk '{print $1}')
fi

echo "📁 Constitutional directory: ${CONST_DIR}"
echo "🔐 Current combined hash:    ${CURRENT_HASH}"
echo "📄 Stored manifest:          ${MANIFEST_FILE}"
if [ -n "${MANIFEST_CONTENT_HASH}" ]; then
    echo "🔒 Stored manifest hash:     ${MANIFEST_CONTENT_HASH}"
fi
if [ -f "${SEAL_FILE}" ]; then
    SEAL_HASH=$(cat "${SEAL_FILE}")
    echo "🛡️  Manifest seal:           ${SEAL_HASH}"
fi
echo ""

# ---------------------------------------------------------------------------
# First run: no manifest → bootstrap + create seal
# ---------------------------------------------------------------------------
if [ ! -f "${MANIFEST_FILE}" ]; then
    cp "${CURRENT_MANIFEST}" "${MANIFEST_FILE}"
    # Seal records the initial manifest content hash
    echo "${CURRENT_HASH}" > "${SEAL_FILE}"
    echo -e "${GREEN}✅ Bootstrap: manifest created at ${MANIFEST_FILE}${NC}"
    echo -e "${GREEN}✅ Seal: initial manifest hash recorded at ${SEAL_FILE}${NC}"
    echo -e "${GREEN}✅ Gate 10: PASSED (first run)${NC}"
    rm -f "${CURRENT_MANIFEST}"
    exit 0
fi

# ---------------------------------------------------------------------------
# Anti-tampering: verify manifest file itself hasn't been modified
# without proper authorization (Amendment C1, C2)
# ---------------------------------------------------------------------------
STORED_HASH=$(sha256sum "${MANIFEST_FILE}" | awk '{print $1}')

# Check if manifest content hash matches what's in the seal
if [ -f "${SEAL_FILE}" ]; then
    ORIGINAL_SEAL=$(cat "${SEAL_FILE}")
    if [ "${STORED_HASH}" != "${ORIGINAL_SEAL}" ]; then
        echo -e "${RED}❌ MANIFEST TAMPERING DETECTED${NC}"
        echo "   The stored manifest file has been modified since bootstrap."
        echo "   Seal (original): ${ORIGINAL_SEAL}"
        echo "   Current:         ${STORED_HASH}"
        echo ""
        echo "This indicates an attempt to bypass constitutional integrity by"
        echo "modifying the baseline. Legitimate constitutional evolution"
        echo "requires explicit approval via the approval mechanism."
        echo ""
        echo "To recover: restore the original manifest and seal, or follow"
        echo "the approval process for the new constitutional state."
        rm -f "${CURRENT_MANIFEST}"
        exit 1
    fi
fi

# ---------------------------------------------------------------------------
# Compare current constitutional state vs stored manifest
# ---------------------------------------------------------------------------
if [ "${CURRENT_HASH}" = "${STORED_HASH}" ]; then
    echo -e "${GREEN}✅ Constitutional documents unchanged${NC}"
    echo -e "${GREEN}✅ Gate 10: PASSED${NC}"
    rm -f "${CURRENT_MANIFEST}"
    exit 0
fi

# Constitutional files have changed
echo -e "${YELLOW}⚠️  Constitutional documents have CHANGED${NC}"
echo -e "   Stored hash:  ${STORED_HASH}"
echo -e "   Current hash: ${CURRENT_HASH}"
echo ""

# List changed files by diffing per-file lines
# NOTE: `diff` returns exit 1 when differences are found. Under `set -euo pipefail`
# this would abort the script before the approval check section. The `|| true`
# guard allows the pipeline to complete regardless of diff's exit code.
echo "📋 Changed files:"
diff -u "${MANIFEST_FILE}" "${CURRENT_MANIFEST}" | grep -E '^[+-][^+-]' | while IFS= read -r dline; do
    echo "   ${dline}"
done || true
echo ""

# ---------------------------------------------------------------------------
# Look for approval: file or env var (Amendment C3)
# ---------------------------------------------------------------------------
APPROVED_HASH=""

if [ -f "${APPROVAL_FILE}" ]; then
    APPROVED_HASH=$(cat "${APPROVAL_FILE}" | tr -d '[:space:]')
    echo "📄 Found approval file: ${APPROVAL_FILE}"
    echo "   Approved hash: ${APPROVED_HASH}"
fi

if [ -n "${CONSTITUTIONAL_CHANGE_APPROVED:-}" ]; then
    if [ -n "${APPROVED_HASH}" ] && [ "${APPROVED_HASH}" != "${CONSTITUTIONAL_CHANGE_APPROVED}" ]; then
        echo -e "${RED}❌ CONFLICT: approval file hash (${APPROVED_HASH}) != env var (${CONSTITUTIONAL_CHANGE_APPROVED})${NC}"
        exit 1
    fi
    APPROVED_HASH="${CONSTITUTIONAL_CHANGE_APPROVED}"
    echo "🌍 Found approval via CONSTITUTIONAL_CHANGE_APPROVED env var"
    echo "   Approved hash: ${APPROVED_HASH}"
fi

if [ -z "${APPROVED_HASH}" ]; then
    echo -e "${RED}❌ NO APPROVAL FOUND${NC}"
    echo ""
    echo "Constitutional changes require explicit approval per"
    echo "mahoun/constitutional/workflows/governance.md"
    echo ""
    echo "To approve this change:"
    echo "  1. Compute the current combined hash:"
    echo "       (printed above as 'Current hash')"
    echo "  2. Write it to the approval file:"
    echo "       echo '<CURRENT_HASH>' > ${APPROVAL_FILE}"
    echo "  3. Re-run this gate (or push — it runs in pre-push)"
    echo ""
    echo "Alternatively, set the environment variable:"
    echo "  export CONSTITUTIONAL_CHANGE_APPROVED=<CURRENT_HASH>"
    echo ""
    rm -f "${CURRENT_MANIFEST}"
    exit 1
fi

# Verify approval hash matches current constitutional state hash
if [ "${APPROVED_HASH}" != "${CURRENT_HASH}" ]; then
    echo -e "${RED}❌ APPROVAL HASH MISMATCH${NC}"
    echo "   Approved: ${APPROVED_HASH}"
    echo "   Current:  ${CURRENT_HASH}"
    echo ""
    echo "The approval was for a different constitutional state."
    echo "Re-compute the current hash and update the approval file/env var."
    rm -f "${CURRENT_MANIFEST}"
    exit 1
fi

# Approval matches → accept change
echo -e "${GREEN}✅ Approved change accepted${NC}"
echo "   Updating manifest..."
cp "${CURRENT_MANIFEST}" "${MANIFEST_FILE}"

# Update seal to new manifest hash (legitimate evolution)
echo "${CURRENT_HASH}" > "${SEAL_FILE}"
echo "   Seal updated to new manifest hash"

# One-shot: delete approval file so it cannot be reused for a future change
if [ -f "${APPROVAL_FILE}" ]; then
    rm -f "${APPROVAL_FILE}"
    echo "   Approval file consumed (one-shot, Amendment C3)"
fi

echo -e "${GREEN}✅ Gate 10: PASSED (approved constitutional evolution recorded)${NC}"
rm -f "${CURRENT_MANIFEST}"
exit 0