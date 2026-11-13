#!/bin/bash
# Refactoring Script: Path to 9+
# این اسکریپت کمک می‌کنه پلتفرم رو از 8.0 به 9.4 برسونیم

set -e  # Exit on error

echo "=========================================="
echo "Mahoun Platform: Path to 9+"
echo "Current Score: 8.0/10"
echo "Target Score: 9.4/10"
echo "=========================================="
echo ""

# رنگ‌ها برای خروجی
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# تابع برای چاپ با رنگ
print_step() {
    echo -e "${GREEN}[STEP]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# بررسی اینکه در root directory هستیم
if [ ! -f "core_manifest.yaml" ]; then
    print_error "Please run this script from the project root directory"
    exit 1
fi

# ساخت backup
print_step "Creating backup..."
BACKUP_DIR="backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
cp -r mahoun/core "$BACKUP_DIR/"
cp -r mahoun/reasoning "$BACKUP_DIR/"
cp -r mahoun/ledger "$BACKUP_DIR/"
print_step "Backup created in $BACKUP_DIR"
echo ""

# فاز A1: پاکسازی Core
echo "=========================================="
echo "Phase A1: Core Module Cleanup"
echo "Impact: +0.75 score (Infrastructure 6/10 → 9/10)"
echo "=========================================="
echo ""

read -p "Start Phase A1? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_step "Creating mahoun/infrastructure/ directory..."
    mkdir -p mahoun/infrastructure
    
    print_step "Moving 10 files from core/ to infrastructure/..."
    FILES_TO_MOVE=(
        "validation.py"
        "secrets.py"
        "config.py"
        "settings.py"
        "serialization.py"
        "health_cache.py"
        "paths.py"
        "runtime_config.py"
        "singleton.py"
        "error_handling.py"
    )
    
    for file in "${FILES_TO_MOVE[@]}"; do
        if [ -f "mahoun/core/$file" ]; then
            print_step "Moving $file..."
            mv "mahoun/core/$file" "mahoun/infrastructure/"
        else
            print_warning "$file not found, skipping..."
        fi
    done
    
    print_step "Moving 6 directories from core/ to infrastructure/..."
    DIRS_TO_MOVE=(
        "llm"
        "rag"
        "graph"
        "ingest"
        "monitoring"
        "metrics"
    )
    
    for dir in "${DIRS_TO_MOVE[@]}"; do
        if [ -d "mahoun/core/$dir" ]; then
            print_step "Moving $dir/..."
            mv "mahoun/core/$dir" "mahoun/infrastructure/"
        else
            print_warning "$dir/ not found, skipping..."
        fi
    done
    
    print_step "Phase A1 file moves complete!"
    print_warning "IMPORTANT: You need to update imports manually!"
    print_warning "Run: grep -r 'from mahoun.core.validation' ."
    print_warning "And replace with: from mahoun.infrastructure.validation"
    echo ""
fi

# فاز A2: رفع نقض مرزها
echo "=========================================="
echo "Phase A2: Fix Boundary Violations"
echo "Impact: +0.25 score (Core Capabilities 8/10 → 9/10)"
echo "=========================================="
echo ""

read -p "Start Phase A2? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_warning "Phase A2 requires manual code changes:"
    echo "1. Add GuardrailsProtocol to mahoun/core/protocols.py"
    echo "2. Add UncertaintyProtocol to mahoun/core/protocols.py"
    echo "3. Update mahoun/reasoning/reasoning_chain.py to use protocols"
    echo "4. Update mahoun/reasoning/evidence_linked_verdict.py to use protocols"
    echo "5. Update mahoun/reasoning/adapters.py to inject implementations"
    echo ""
    print_step "See PATH_TO_9_PLUS.md for detailed instructions"
    echo ""
fi

# فاز A3: افزایش پوشش تست
echo "=========================================="
echo "Phase A3: Increase Test Coverage"
echo "Impact: +0.25 score (Test Coverage 8/10 → 9/10)"
echo "=========================================="
echo ""

read -p "Start Phase A3? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_step "Running coverage analysis..."
    if command -v pytest &> /dev/null; then
        pytest --cov=mahoun/core --cov-report=term-missing || true
        echo ""
        print_warning "Write tests for files with low coverage"
        print_warning "Target: 90%+ coverage for mahoun/core/"
    else
        print_error "pytest not found. Please install: pip install pytest pytest-cov"
    fi
    echo ""
fi

# فاز A4: انتقال Ledger Logic
echo "=========================================="
echo "Phase A4: Move Ledger Business Logic"
echo "Impact: +0.25 score (Architecture 9/10 → 10/10)"
echo "=========================================="
echo ""

read -p "Start Phase A4? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_step "Creating mahoun/domain/ directory..."
    mkdir -p mahoun/domain
    
    print_warning "Phase A4 requires manual code changes:"
    echo "1. Create mahoun/domain/privacy_service.py"
    echo "2. Move logic from mahoun/ledger/guards.py"
    echo "3. Move logic from mahoun/ledger/privacy.py"
    echo "4. Move mahoun/ledger/storage.py to mahoun/infrastructure/storage/"
    echo "5. Update ledger to be 'dumb and obedient'"
    echo ""
    print_step "See PATH_TO_9_PLUS.md for detailed instructions"
    echo ""
fi

# اجرای Gate 7
echo "=========================================="
echo "Validation: Running Gate 7"
echo "=========================================="
echo ""

read -p "Run Gate 7 (Architecture Boundary Check)? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if [ -f "ci/first_step/gate_7_architecture.sh" ]; then
        print_step "Running Gate 7..."
        bash ci/first_step/gate_7_architecture.sh || print_error "Gate 7 failed! Fix violations before proceeding."
    else
        print_error "Gate 7 script not found"
    fi
    echo ""
fi

# خلاصه
echo "=========================================="
echo "Summary"
echo "=========================================="
echo ""
print_step "Backup location: $BACKUP_DIR"
echo ""
echo "Next steps:"
echo "1. Update all imports (mahoun.core.* → mahoun.infrastructure.*)"
echo "2. Complete Phase A2 (Fix boundary violations)"
echo "3. Complete Phase A3 (Write tests for core/)"
echo "4. Complete Phase A4 (Move ledger business logic)"
echo "5. Run all tests: pytest tests/"
echo "6. Run Gate 7: bash ci/first_step/gate_7_architecture.sh"
echo "7. Run Gate 8: bash ci/first_step/gate_8_contracts.sh"
echo ""
print_step "Expected result: Platform score 8.0 → 9.4 🎯"
echo ""
echo "For detailed instructions, see:"
echo "- PATH_TO_9_PLUS.md (English)"
echo "- مسیر_رسیدن_به_9.md (Persian)"
echo ""
