# CI Troubleshooting Guide

This guide helps you diagnose and fix common CI gate failures.

## Quick Reference

| Gate | Common Issue | Quick Fix |
|------|-------------|-----------|
| 0 | Stub code in critical paths | Remove `pass` statements, implement functionality |
| 1 | Linting errors | Run `make lint-fix` |
| 2 | Type errors | Fix type annotations, run `mypy mahoun/` |
| 7 | Boundary violations | Remove non-core imports from core modules |
| 8 | Contract validation failures | Fix Pydantic schemas, ensure v2 compliance |

---

## Gate 0: Repo Integrity

### Symptom: "Found 'pass' stubs in critical paths"

**Cause**: Critical code paths contain placeholder `pass` statements instead of real implementations.

**Fix**:
1. Run the gate to see which files have stubs:
   ```bash
   bash ci/first_step/gate_0_integrity.sh
   ```
2. Review each file listed
3. Replace `pass` with actual implementation
4. If the function is intentionally empty, add a docstring explaining why

**Example**:
```python
# BAD - Will fail gate 0
def critical_function():
    pass

# GOOD - Proper implementation
def critical_function():
    """Process critical data."""
    return process_data()

# ACCEPTABLE - Documented empty function
def optional_hook():
    """Optional hook for subclasses to override."""
    pass  # Intentionally empty
```

### Symptom: "Missing core paths"

**Cause**: Required directories don't exist.

**Fix**:
1. Check which paths are missing in the gate output
2. Create the missing directories
3. Ensure they contain at least an `__init__.py`

---

## Gate 1: Format/Lint

### Symptom: "Linting errors found"

**Cause**: Code doesn't conform to ruff style rules.

**Fix**:
```bash
# Auto-fix most issues
make lint-fix

# Or manually
ruff check --fix mahoun/ api/ tests/

# Check what remains
make lint
```

**Common Issues**:
- Unused imports: Remove them
- Line too long: Break into multiple lines
- Missing docstrings: Add them to public functions

---

## Gate 2: Type Safety

### Symptom: "Type checking failed"

**Cause**: Type annotations are missing or incorrect.

**Fix**:
```bash
# Run mypy to see errors
mypy mahoun/

# Common fixes:
# 1. Add type hints to function signatures
# 2. Import types from typing module
# 3. Use Optional[T] for nullable values
# 4. Use Union[T1, T2] for multiple types
```

**Example**:
```python
# BAD - No type hints
def process(data):
    return data.upper()

# GOOD - Proper type hints
def process(data: str) -> str:
    return data.upper()

# GOOD - Optional return
from typing import Optional

def find_user(user_id: str) -> Optional[User]:
    return db.get(user_id)
```

---

## Gate 7: Architecture Boundaries

### Symptom: "Boundary violations detected"

**Cause**: Core modules are importing from non-core modules.

**Fix**:
1. Run the boundary checker:
   ```bash
   python scripts/check_boundaries.py
   ```
2. Review each violation
3. Apply one of these fixes:

**Fix Option 1: Use Dependency Injection**
```python
# BAD - Direct import of non-core module
from mahoun.mcp.server import MCPServer

def process():
    server = MCPServer()
    return server.call()

# GOOD - Use protocol and DI
from mahoun.core.protocols import ServerProtocol

def process(server: ServerProtocol):
    return server.call()
```

**Fix Option 2: Move Code to Correct Module**
```python
# If the imported code is actually core functionality,
# move it to a core module
```

**Fix Option 3: Invert the Dependency**
```python
# Instead of core depending on non-core,
# make non-core depend on core
```

### Symptom: "Module not in manifest"

**Cause**: A module exists but isn't listed in either manifest.

**Fix**:
1. Determine if the module is core or non-core
2. Add it to the appropriate manifest:
   - `core_manifest.yaml` for core modules
   - `non_core_manifest.yaml` for non-core modules

---

## Gate 8: Contract Validation

### Symptom: "Contract tests failed"

**Cause**: Contract schemas don't validate correctly.

**Fix**:
```bash
# Run contract tests to see failures
python -m pytest tests/contracts/ -v

# Common issues and fixes below
```

### Issue: "Support for class-based config is deprecated"

**Cause**: Using Pydantic v1 style `class Config` instead of v2 `model_config`.

**Fix**:
```python
# BAD - Pydantic v1 style
from pydantic import BaseModel

class MyContract(BaseModel):
    field: str
    
    class Config:
        frozen = True

# GOOD - Pydantic v2 style
from pydantic import BaseModel, ConfigDict

class MyContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    field: str
```

### Issue: "min_items is deprecated"

**Cause**: Using deprecated `min_items` instead of `min_length`.

**Fix**:
```python
# BAD
from pydantic import Field
from typing import List

field: List[str] = Field(..., min_items=1)

# GOOD
field: List[str] = Field(..., min_length=1)
```

### Issue: "Validation error: field required"

**Cause**: Contract is missing required fields.

**Fix**:
```python
# Ensure all required fields are present
from pydantic import Field

class MyContract(BaseModel):
    required_field: str = Field(..., description="This is required")
    optional_field: str = Field(default="", description="This is optional")
```

### Issue: "Extra fields are not permitted"

**Cause**: Contract has `extra="forbid"` but test is passing extra fields.

**Fix**:
```python
# Remove extra fields from test data
data = {
    "required_field": "value",
    # "extra_field": "not allowed"  # Remove this
}
```

### Issue: "Field validation failed"

**Cause**: Field validator is rejecting valid input.

**Fix**:
1. Review the validator logic
2. Check if the validation rule is too strict
3. Update validator or test data

```python
from pydantic import field_validator

class MyContract(BaseModel):
    confidence: float
    
    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("Confidence must be between 0 and 1")
        return v
```

---

## General Debugging Tips

### 1. Run Gates Individually

Instead of running the full pipeline, run individual gates:
```bash
bash ci/first_step/gate_7_architecture.sh
bash ci/first_step/gate_8_contracts.sh
```

### 2. Use Verbose Mode

Add `-v` or `-vv` to pytest commands for more detail:
```bash
python -m pytest tests/contracts/ -vv
```

### 3. Run Specific Tests

Test a single contract file:
```bash
python -m pytest tests/contracts/test_core_contracts.py -v
```

Test a specific test:
```bash
python -m pytest tests/contracts/test_core_contracts.py::TestRuntimeSettingsOutput::test_valid_runtime_settings -v
```

### 4. Check Recent Changes

If gates were passing before, check what changed:
```bash
git diff HEAD~1 mahoun/
```

### 5. Review Manifests

Ensure manifests are up to date:
```bash
cat core_manifest.yaml
cat non_core_manifest.yaml
```

---

## Getting Help

If you're stuck:

1. **Read the gate output carefully** - It usually tells you exactly what's wrong
2. **Check the relevant documentation**:
   - Architecture: `docs/ARCHITECTURE.md`
   - Contracts: `.kiro/specs/contract-formalization/design.md`
   - Manifests: `core_manifest.yaml` and `non_core_manifest.yaml`
3. **Review recent commits** - Did someone break the build?
4. **Ask the team** - Someone may have seen this before

---

## Common Patterns

### Pattern: "I added a new core module"

Checklist:
- [ ] Add module to `core_manifest.yaml`
- [ ] Create contract schemas in `mahoun/schemas/contracts/`
- [ ] Create contract tests in `tests/contracts/`
- [ ] Ensure no imports from non-core modules
- [ ] Run gate 7 and gate 8

### Pattern: "I added a new non-core module"

Checklist:
- [ ] Add module to `non_core_manifest.yaml`
- [ ] Ensure it doesn't import from core modules (unless via protocols)
- [ ] Run gate 7

### Pattern: "I modified a contract"

Checklist:
- [ ] Update contract schema in `mahoun/schemas/contracts/`
- [ ] Update contract tests in `tests/contracts/`
- [ ] Ensure Pydantic v2 compliance
- [ ] Run gate 8

### Pattern: "I refactored code"

Checklist:
- [ ] Run all gates to ensure nothing broke
- [ ] Check for new boundary violations (gate 7)
- [ ] Check for contract changes (gate 8)
- [ ] Update tests if behavior changed

---

## Prevention

### Before Committing

Run the full CI pipeline locally:
```bash
bash scripts/ci_run_first_step.sh
```

### During Development

Run relevant gates frequently:
```bash
# After changing core modules
bash ci/first_step/gate_7_architecture.sh

# After changing contracts
bash ci/first_step/gate_8_contracts.sh

# Quick check
make lint && make typecheck
```

### Code Review

Reviewers should verify:
- [ ] All gates pass
- [ ] No new boundary violations
- [ ] Contracts are updated if interfaces changed
- [ ] Tests are updated if behavior changed
