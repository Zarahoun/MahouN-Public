#!/bin/bash
# ============================================================================
# ساخت MAHOUN Community Edition
# Create MAHOUN Community Edition
# ============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}   ساخت MAHOUN Community Edition${NC}"
echo -e "${BLUE}   Creating MAHOUN Community Edition${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"

# ============================================================================
# تنظیمات
# ============================================================================
COMMUNITY_DIR="../mahoun-community"
SOURCE_DIR="."

echo -e "\n${CYAN}📁 مسیر Community Edition: ${YELLOW}$COMMUNITY_DIR${NC}"

# ============================================================================
# 1. ساخت دایرکتوری
# ============================================================================
echo -e "\n${CYAN}1️⃣  ساخت دایرکتوری...${NC}"

if [ -d "$COMMUNITY_DIR" ]; then
    echo -e "${YELLOW}⚠️  دایرکتوری موجود است. حذف می‌شود...${NC}"
    rm -rf "$COMMUNITY_DIR"
fi

mkdir -p "$COMMUNITY_DIR"
cd "$COMMUNITY_DIR"
git init
echo -e "${GREEN}✓ دایرکتوری ساخته شد${NC}"

# ============================================================================
# 2. کپی reasoning_logic
# ============================================================================
echo -e "\n${CYAN}2️⃣  کپی reasoning_logic...${NC}"

cp -r "$SOURCE_DIR/reasoning_logic" .
echo -e "${GREEN}✓ reasoning_logic کپی شد${NC}"

# ============================================================================
# 3. ساخت ساختار پروژه
# ============================================================================
echo -e "\n${CYAN}3️⃣  ساخت ساختار پروژه...${NC}"

mkdir -p docs
mkdir -p examples
mkdir -p tests

echo -e "${GREEN}✓ ساختار پروژه ساخته شد${NC}"

# ============================================================================
# 4. ساخت README.md
# ============================================================================
echo -e "\n${CYAN}4️⃣  ساخت README.md...${NC}"

cat > README.md << 'EOF'
# MAHOUN Reasoning Engine 🧠

**Zero-hallucination symbolic reasoning engine for AI systems**

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12+-green.svg)](https://python.org)

---

## 🎯 What is MAHOUN?

MAHOUN Reasoning Engine is a **deterministic symbolic reasoning system** designed for high-stakes AI applications where hallucinations are unacceptable.

Perfect for:
- 🏛️ **Legal AI** - Contract analysis, case law reasoning
- 🏥 **Healthcare AI** - Clinical decision support, drug interactions
- 💰 **Financial AI** - Compliance checking, risk assessment
- 🔬 **Research AI** - Scientific reasoning, hypothesis testing

---

## ✨ Features

- ✅ **Forward & Backward Chaining** - Flexible reasoning strategies
- ✅ **RETE Algorithm** - Efficient pattern matching
- ✅ **Unification** - First-order logic support
- ✅ **Knowledge Base** - Structured fact and rule storage
- ✅ **100% Deterministic** - Same input = same output, always
- ✅ **Full Audit Trail** - Complete reasoning provenance
- ✅ **Zero Dependencies** - Pure Python, no external libs

---

## 🚀 Quick Start

### Installation

```bash
pip install mahoun-reasoning
```

### Basic Example

```python
from reasoning_logic import KnowledgeBase, ForwardChaining

# Create knowledge base
kb = KnowledgeBase()

# Add rules
kb.add_rule("mortal(X) :- human(X)")
kb.add_rule("human(X) :- person(X)")

# Add facts
kb.add_fact("person(socrates)")

# Run forward chaining
engine = ForwardChaining(kb)
result = engine.query("mortal(socrates)")

print(result.success)  # True
print(result.proof)    # Complete derivation trace
```

### Legal Reasoning Example

```python
from reasoning_logic import KnowledgeBase, BackwardChaining

kb = KnowledgeBase()

# Legal rules
kb.add_rule("liable(X) :- breach_of_contract(X), damages_proven(X)")
kb.add_rule("breach_of_contract(X) :- contract_exists(X), obligation_not_met(X)")

# Facts
kb.add_fact("contract_exists(case_123)")
kb.add_fact("obligation_not_met(case_123)")
kb.add_fact("damages_proven(case_123)")

# Query
engine = BackwardChaining(kb)
result = engine.query("liable(case_123)")

if result.success:
    print("Liability established")
    print("Reasoning chain:", result.proof)
```

---

## 📚 Documentation

- [Getting Started](docs/getting-started.md)
- [Architecture](docs/architecture.md)
- [API Reference](docs/api-reference.md)
- [Examples](examples/)

---

## 🏢 Enterprise Edition

Need more power? Check out **[MAHOUN Enterprise](https://mahoun.ai/enterprise)**:

- 🚀 **Knowledge Graph** - Neo4j integration, graph reasoning
- 🚀 **RAG System** - Retrieval-augmented generation
- 🚀 **REST API** - Production-ready web service
- 🚀 **Web UI** - Beautiful dashboard
- 🚀 **Guardrails** - Safety and compliance checks
- 🚀 **Audit Ledger** - Immutable reasoning logs
- 🚀 **Cloud Deployment** - Managed infrastructure
- 🚀 **24/7 Support** - Expert assistance

[Request Demo](https://mahoun.ai/demo) | [Pricing](https://mahoun.ai/pricing)

---

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## 📄 License

Apache License 2.0 - See [LICENSE](LICENSE) file for details.

---

## 🌟 Star History

If you find MAHOUN useful, please star the repo! ⭐

---

## 📞 Contact

- Website: [mahoun.ai](https://mahoun.ai)
- Email: hello@mahoun.ai
- Twitter: [@mahoun_ai](https://twitter.com/mahoun_ai)

---

**Built with ❤️ for the AI community**
EOF

echo -e "${GREEN}✓ README.md ساخته شد${NC}"

# ============================================================================
# 5. ساخت LICENSE
# ============================================================================
echo -e "\n${CYAN}5️⃣  ساخت LICENSE...${NC}"

cat > LICENSE << 'EOF'
Apache License
Version 2.0, January 2004
http://www.apache.org/licenses/

Copyright 2026 MAHOUN Platform

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
EOF

echo -e "${GREEN}✓ LICENSE ساخته شد${NC}"

# ============================================================================
# 6. ساخت CONTRIBUTING.md
# ============================================================================
echo -e "\n${CYAN}6️⃣  ساخت CONTRIBUTING.md...${NC}"

cat > CONTRIBUTING.md << 'EOF'
# Contributing to MAHOUN

Thank you for your interest in contributing to MAHOUN! 🎉

## How to Contribute

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/amazing-feature`
3. **Make your changes**
4. **Add tests** for your changes
5. **Run tests**: `pytest tests/`
6. **Commit**: `git commit -m "Add amazing feature"`
7. **Push**: `git push origin feature/amazing-feature`
8. **Open a Pull Request**

## Code Style

- Follow PEP 8
- Use type hints
- Add docstrings
- Keep functions small and focused

## Testing

All contributions must include tests:

```bash
pytest tests/ -v
```

## Questions?

Open an issue or email us at hello@mahoun.ai
EOF

echo -e "${GREEN}✓ CONTRIBUTING.md ساخته شد${NC}"

# ============================================================================
# 7. ساخت requirements.txt
# ============================================================================
echo -e "\n${CYAN}7️⃣  ساخت requirements.txt...${NC}"

cat > requirements.txt << 'EOF'
# MAHOUN Community Edition - Requirements
# Python 3.12+

# Core (no external dependencies for reasoning engine)
# All reasoning logic is pure Python

# Development dependencies
pytest>=7.0.0
pytest-cov>=4.0.0
mypy>=1.0.0
ruff>=0.1.0
EOF

echo -e "${GREEN}✓ requirements.txt ساخته شد${NC}"

# ============================================================================
# 8. ساخت pyproject.toml
# ============================================================================
echo -e "\n${CYAN}8️⃣  ساخت pyproject.toml...${NC}"

cat > pyproject.toml << 'EOF'
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "mahoun-reasoning"
version = "0.1.0"
description = "Zero-hallucination symbolic reasoning engine"
readme = "README.md"
requires-python = ">=3.12"
license = {text = "Apache-2.0"}
authors = [
    {name = "MAHOUN Team", email = "hello@mahoun.ai"}
]
keywords = ["reasoning", "ai", "symbolic", "logic", "knowledge-graph"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: Apache Software License",
    "Programming Language :: Python :: 3.12",
    "Topic :: Scientific/Engineering :: Artificial Intelligence",
]

[project.urls]
Homepage = "https://mahoun.ai"
Documentation = "https://docs.mahoun.ai"
Repository = "https://github.com/mahoun/mahoun-community"
"Bug Tracker" = "https://github.com/mahoun/mahoun-community/issues"

[tool.setuptools.packages.find]
include = ["reasoning_logic*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
python_functions = "test_*"

[tool.mypy]
python_version = "3.12"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true

[tool.ruff]
line-length = 100
target-version = "py312"
EOF

echo -e "${GREEN}✓ pyproject.toml ساخته شد${NC}"

# ============================================================================
# 9. ساخت .gitignore
# ============================================================================
echo -e "\n${CYAN}9️⃣  ساخت .gitignore...${NC}"

cat > .gitignore << 'EOF'
# Python
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
*.so
*.egg
*.egg-info/
dist/
build/

# Testing
.pytest_cache/
.coverage
htmlcov/

# IDE
.vscode/
.idea/
*.swp

# OS
.DS_Store
EOF

echo -e "${GREEN}✓ .gitignore ساخته شد${NC}"

# ============================================================================
# 10. ساخت مثال‌ها
# ============================================================================
echo -e "\n${CYAN}🔟  ساخت مثال‌ها...${NC}"

cat > examples/simple_reasoning.py << 'EOF'
"""
Simple reasoning example
"""
from reasoning_logic import KnowledgeBase, ForwardChaining

def main():
    # Create knowledge base
    kb = KnowledgeBase()
    
    # Add rules
    kb.add_rule("mortal(X) :- human(X)")
    kb.add_fact("human(socrates)")
    
    # Run reasoning
    engine = ForwardChaining(kb)
    result = engine.query("mortal(socrates)")
    
    print(f"Query: mortal(socrates)")
    print(f"Result: {result.success}")
    print(f"Proof: {result.proof}")

if __name__ == "__main__":
    main()
EOF

echo -e "${GREEN}✓ مثال‌ها ساخته شد${NC}"

# ============================================================================
# 11. اولین commit
# ============================================================================
echo -e "\n${CYAN}1️⃣1️⃣  اولین commit...${NC}"

git add .
git commit -m "Initial community release

- Symbolic reasoning engine
- Forward and backward chaining
- RETE algorithm
- Knowledge base management
- Zero external dependencies"

echo -e "${GREEN}✓ Commit انجام شد${NC}"

# ============================================================================
# نتیجه
# ============================================================================
echo -e "\n${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ MAHOUN Community Edition آماده است!${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"

echo -e "\n${CYAN}📍 مسیر:${NC} $COMMUNITY_DIR"
echo -e "\n${CYAN}مراحل بعدی:${NC}"
echo -e "  1. ${YELLOW}cd $COMMUNITY_DIR${NC}"
echo -e "  2. ${YELLOW}git remote add origin <your-repo-url>${NC}"
echo -e "  3. ${YELLOW}git push -u origin main${NC}"
echo -e "  4. ${YELLOW}# ساخت release در GitHub${NC}"
echo -e "  5. ${YELLOW}# انتشار در PyPI${NC}"

echo -e "\n${GREEN}🚀 موفق باشی!${NC}\n"
