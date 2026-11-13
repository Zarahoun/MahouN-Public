#!/bin/bash
# ============================================================================
# تحلیل فایل‌های قابل انتشار عمومی
# Analyze Public Exposure - What will be visible
# ============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}   تحلیل فایل‌های قابل انتشار عمومی MAHOUN${NC}"
echo -e "${BLUE}   MAHOUN Public Exposure Analysis${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"

# ============================================================================
# 1. آمار کلی
# ============================================================================
echo -e "\n${CYAN}📊 آمار کلی / General Statistics${NC}"
echo "─────────────────────────────────────"

TOTAL_FILES=$(find . -type f | wc -l)
TRACKED_FILES=$(git ls-files | wc -l)
IGNORED_FILES=$((TOTAL_FILES - TRACKED_FILES))

echo -e "کل فایل‌ها / Total files:           ${YELLOW}$TOTAL_FILES${NC}"
echo -e "فایل‌های قابل انتشار / Tracked:     ${GREEN}$TRACKED_FILES${NC}"
echo -e "فایل‌های محافظت‌شده / Ignored:      ${RED}$IGNORED_FILES${NC}"

# ============================================================================
# 2. پوشه‌های قابل انتشار
# ============================================================================
echo -e "\n${CYAN}📁 پوشه‌های قابل انتشار / Public Directories${NC}"
echo "─────────────────────────────────────"

PUBLIC_DIRS=(
    "mahoun"
    "reasoning_logic"
    "api"
    "tests"
    "docs"
    "examples"
    "scripts"
    "ci"
    "frontend"
    ".github"
)

for dir in "${PUBLIC_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        COUNT=$(git ls-files "$dir" 2>/dev/null | wc -l)
        if [ $COUNT -gt 0 ]; then
            echo -e "${GREEN}✓${NC} $dir (${COUNT} فایل)"
        else
            echo -e "${YELLOW}⚠${NC} $dir (خالی یا ignore شده)"
        fi
    else
        echo -e "${RED}✗${NC} $dir (وجود ندارد)"
    fi
done

# ============================================================================
# 3. پوشه‌های محافظت‌شده
# ============================================================================
echo -e "\n${CYAN}🔒 پوشه‌های محافظت‌شده / Protected Directories${NC}"
echo "─────────────────────────────────────"

PRIVATE_DIRS=(
    ".claude"
    ".kiro"
    ".kilo"
    ".qoder"
    "data"
    "models"
    "vector_store_data"
    "uploads"
    "output"
    "runtime"
    "ledger"
    "archive"
    "venv"
)

for dir in "${PRIVATE_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        if git check-ignore "$dir" > /dev/null 2>&1; then
            SIZE=$(du -sh "$dir" 2>/dev/null | cut -f1)
            echo -e "${GREEN}✓${NC} $dir (محافظت شده - حجم: $SIZE)"
        else
            echo -e "${RED}❌ خطر!${NC} $dir (محافظت نشده!)"
        fi
    fi
done

# ============================================================================
# 4. فایل‌های حساس در ریشه
# ============================================================================
echo -e "\n${CYAN}📄 فایل‌های ریشه / Root Files${NC}"
echo "─────────────────────────────────────"

echo -e "\n${GREEN}✅ فایل‌های امن (قابل انتشار):${NC}"
SAFE_FILES=(
    "README.md"
    "LICENSE"
    "pyproject.toml"
    "requirements.txt"
    "Makefile"
    "docker/docker-compose.yml"
    "docker/Dockerfile"
    ".gitignore"
    ".env.example"
)

for file in "${SAFE_FILES[@]}"; do
    if [ -f "$file" ]; then
        if git ls-files --error-unmatch "$file" > /dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} $file"
        else
            echo -e "  ${YELLOW}⚠${NC} $file (موجود اما track نشده)"
        fi
    fi
done

echo -e "\n${RED}🚫 فایل‌های حساس (نباید عمومی شوند):${NC}"
SENSITIVE_PATTERNS=(
    "*FORENSIC*.md"
    "*PHASE_*.md"
    "*EXECUTIVE*.md"
    "*_COMPLETE.md"
    "test_*.py"
    "*.log"
    "Agentrules.md"
    "*manifest.yaml"
)

FOUND_SENSITIVE=0
for pattern in "${SENSITIVE_PATTERNS[@]}"; do
    FILES=$(find . -maxdepth 1 -name "$pattern" -type f 2>/dev/null)
    if [ -n "$FILES" ]; then
        for file in $FILES; do
            if git check-ignore "$file" > /dev/null 2>&1; then
                echo -e "  ${GREEN}✓${NC} $file (محافظت شده)"
            else
                echo -e "  ${RED}❌${NC} $file (خطر! قابل انتشار است)"
                FOUND_SENSITIVE=$((FOUND_SENSITIVE + 1))
            fi
        done
    fi
done

# ============================================================================
# 5. بررسی سیکرت‌ها
# ============================================================================
echo -e "\n${CYAN}🔐 بررسی سیکرت‌ها / Secret Scan${NC}"
echo "─────────────────────────────────────"

echo "در حال اسکن فایل‌های قابل انتشار..."

SECRET_FOUND=0

# Check for .env files
ENV_FILES=$(git ls-files | grep -E '\.env$' | grep -v '\.env\.example' || true)
if [ -n "$ENV_FILES" ]; then
    echo -e "${RED}❌ خطر! فایل .env در git:${NC}"
    echo "$ENV_FILES"
    SECRET_FOUND=$((SECRET_FOUND + 1))
fi

# Check for keys
KEY_FILES=$(git ls-files | grep -E '\.(key|pem|p12|pfx)$' || true)
if [ -n "$KEY_FILES" ]; then
    echo -e "${RED}❌ خطر! فایل کلید در git:${NC}"
    echo "$KEY_FILES"
    SECRET_FOUND=$((SECRET_FOUND + 1))
fi

# Check for potential secrets in content
if git grep -iE 'api[_-]?key.*=.*["\'][a-zA-Z0-9]{20,}' -- '*.py' '*.json' '*.yaml' > /dev/null 2>&1; then
    echo -e "${RED}❌ خطر! احتمال API key در کد${NC}"
    SECRET_FOUND=$((SECRET_FOUND + 1))
fi

if [ $SECRET_FOUND -eq 0 ]; then
    echo -e "${GREEN}✓ سیکرتی یافت نشد${NC}"
fi

# ============================================================================
# 6. حجم داده‌ها
# ============================================================================
echo -e "\n${CYAN}💾 تحلیل حجم / Size Analysis${NC}"
echo "─────────────────────────────────────"

REPO_SIZE=$(du -sh . 2>/dev/null | cut -f1)
GIT_SIZE=$(du -sh .git 2>/dev/null | cut -f1)
TRACKED_SIZE=$(git ls-files | xargs -I {} du -ch {} 2>/dev/null | tail -1 | cut -f1)

echo -e "حجم کل پروژه:                    ${YELLOW}$REPO_SIZE${NC}"
echo -e "حجم .git:                         ${YELLOW}$GIT_SIZE${NC}"
echo -e "حجم فایل‌های قابل انتشار:        ${GREEN}$TRACKED_SIZE${NC}"

# ============================================================================
# 7. بزرگترین فایل‌های قابل انتشار
# ============================================================================
echo -e "\n${CYAN}📦 بزرگترین فایل‌های عمومی / Largest Public Files${NC}"
echo "─────────────────────────────────────"

git ls-files | while read file; do
    if [ -f "$file" ]; then
        size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null || echo 0)
        echo "$size $file"
    fi
done | sort -rn | head -10 | while read size file; do
    size_mb=$((size / 1048576))
    size_kb=$((size / 1024))
    if [ $size_mb -gt 0 ]; then
        echo -e "  ${size_mb}MB - $file"
    else
        echo -e "  ${size_kb}KB - $file"
    fi
done

# ============================================================================
# 8. نتیجه نهایی
# ============================================================================
echo -e "\n${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}📋 نتیجه نهایی / Final Verdict${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"

ISSUES=0

# Check protected directories
for dir in "${PRIVATE_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        if ! git check-ignore "$dir" > /dev/null 2>&1; then
            ISSUES=$((ISSUES + 1))
        fi
    fi
done

ISSUES=$((ISSUES + FOUND_SENSITIVE + SECRET_FOUND))

if [ $ISSUES -eq 0 ]; then
    echo -e "\n${GREEN}✅ همه چیز امن است!${NC}"
    echo -e "${GREEN}✅ All Clear! Safe for public release${NC}"
    echo -e "\nپروژه آماده انتشار عمومی است."
    echo -e "Project is ready for public release."
else
    echo -e "\n${RED}❌ مشکلات امنیتی یافت شد: $ISSUES${NC}"
    echo -e "${RED}❌ Security issues found: $ISSUES${NC}"
    echo -e "\n${YELLOW}لطفاً قبل از انتشار عمومی، مشکلات را برطرف کنید.${NC}"
    echo -e "${YELLOW}Please fix issues before public release.${NC}"
fi

echo -e "\n${CYAN}برای جزئیات بیشتر:${NC}"
echo -e "  - مطالعه: ${YELLOW}PUBLIC_RELEASE_STRATEGY.md${NC}"
echo -e "  - مطالعه: ${YELLOW}SECURITY_GUIDELINES.md${NC}"
echo -e "  - اجرا: ${YELLOW}scripts/verify-gitignore.sh${NC}"

echo ""
