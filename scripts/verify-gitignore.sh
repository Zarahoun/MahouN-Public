#!/bin/bash
# ============================================================================
# MAHOUN Platform - .gitignore Verification Script
# ============================================================================
# PURPOSE: Verify .gitignore is working correctly before public release
# ============================================================================

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🔍 MAHOUN .gitignore Verification${NC}"
echo "===================================="

# ============================================================================
# 1. CHECK UNTRACKED FILES
# ============================================================================
echo -e "\n${YELLOW}📋 Checking untracked files...${NC}"
UNTRACKED=$(git ls-files --others --exclude-standard)

if [ -z "$UNTRACKED" ]; then
    echo -e "${GREEN}✓ No untracked files (all properly ignored)${NC}"
else
    echo -e "${YELLOW}Untracked files found:${NC}"
    echo "$UNTRACKED" | head -20
    if [ $(echo "$UNTRACKED" | wc -l) -gt 20 ]; then
        echo "... and $(($(echo "$UNTRACKED" | wc -l) - 20)) more"
    fi
fi

# ============================================================================
# 2. CHECK FOR SENSITIVE FILES IN TRACKED FILES
# ============================================================================
echo -e "\n${YELLOW}🔐 Checking tracked files for sensitive patterns...${NC}"

SENSITIVE_PATTERNS=(
    "\.env$"
    "\.key$"
    "\.pem$"
    "\.sqlite$"
    "\.db$"
    "api_key"
    "secret"
    "credential"
    "password"
)

VIOLATIONS=0
for pattern in "${SENSITIVE_PATTERNS[@]}"; do
    MATCHES=$(git ls-files | grep -iE "$pattern" | grep -v "\.example" | grep -v "\.md$" | grep -v "test_" || true)
    if [ -n "$MATCHES" ]; then
        echo -e "${RED}❌ Found tracked files matching '$pattern':${NC}"
        echo "$MATCHES"
        VIOLATIONS=$((VIOLATIONS + 1))
    fi
done

if [ $VIOLATIONS -eq 0 ]; then
    echo -e "${GREEN}✓ No sensitive files in tracked files${NC}"
fi

# ============================================================================
# 3. CHECK WHAT WOULD BE COMMITTED
# ============================================================================
echo -e "\n${YELLOW}📦 Files that would be committed (staged):${NC}"
STAGED=$(git diff --cached --name-only)
if [ -z "$STAGED" ]; then
    echo -e "${GREEN}✓ No staged files${NC}"
else
    echo "$STAGED"
fi

# ============================================================================
# 4. CHECK FOR LARGE FILES
# ============================================================================
echo -e "\n${YELLOW}📊 Checking for large files in repository...${NC}"
LARGE_FILES=$(git ls-files | while read file; do
    if [ -f "$file" ]; then
        size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null || echo 0)
        if [ "$size" -gt 1048576 ]; then  # 1MB
            echo "$file ($((size / 1048576))MB)"
        fi
    fi
done)

if [ -z "$LARGE_FILES" ]; then
    echo -e "${GREEN}✓ No large files (>1MB) in repository${NC}"
else
    echo -e "${YELLOW}Large files found:${NC}"
    echo "$LARGE_FILES"
fi

# ============================================================================
# 5. VERIFY CRITICAL DIRECTORIES ARE IGNORED
# ============================================================================
echo -e "\n${YELLOW}📁 Verifying critical directories are ignored...${NC}"

CRITICAL_DIRS=(
    "venv"
    "__pycache__"
    ".pytest_cache"
    "node_modules"
    ".venv"
    "data"
    "models"
    "logs"
)

for dir in "${CRITICAL_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        if git check-ignore "$dir" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ $dir is properly ignored${NC}"
        else
            echo -e "${RED}❌ $dir exists but is NOT ignored${NC}"
            VIOLATIONS=$((VIOLATIONS + 1))
        fi
    fi
done

# ============================================================================
# 6. CHECK EXAMPLE FILES EXIST
# ============================================================================
echo -e "\n${YELLOW}📝 Checking for example configuration files...${NC}"

EXAMPLE_FILES=(
    ".env.example"
    ".env.backend.example"
)

for file in "${EXAMPLE_FILES[@]}"; do
    if [ -f "$file" ]; then
        if git ls-files --error-unmatch "$file" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ $file exists and is tracked${NC}"
        else
            echo -e "${YELLOW}⚠️  $file exists but is not tracked${NC}"
        fi
    else
        echo -e "${RED}❌ $file does not exist${NC}"
    fi
done

# ============================================================================
# 7. SUMMARY
# ============================================================================
echo -e "\n===================================="
if [ $VIOLATIONS -gt 0 ]; then
    echo -e "${RED}❌ VERIFICATION FAILED${NC}"
    echo -e "${RED}   $VIOLATIONS issue(s) detected${NC}"
    exit 1
else
    echo -e "${GREEN}✅ VERIFICATION PASSED${NC}"
    echo -e "${GREEN}   Repository is ready for public release${NC}"
    exit 0
fi
