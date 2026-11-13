# First Step CI - Gate Scripts

This directory contains the gate scripts for Phase-1 CI/CD (laptop-safe).

## Gate Scripts

| Script | Gate | Purpose | Duration |
|--------|------|---------|----------|
| `gate_0_integrity.sh` | 0 | Repo Integrity | ~2s |
| `gate_1_lint.sh` | 1 | Format/Lint | ~5s |
| `gate_2_types.sh` | 2 | Type Safety | ~10s |
| `gate_3_reality.sh` | 3 | Phase-1 Reality Tests | ~30s |
| `gate_4_antimock.sh` | 4 | Anti-Mock Proof | ~5s |
| `gate_5_determinism.sh` | 5 | Determinism Proof | ~60s |
| `gate_6_artifacts.sh` | 6 | Artifact + Traceability | ~5s |

## Running Gates

### All Gates (Recommended)
```bash
cd /home/haji/Desktop/Platform
./scripts/ci_run_first_step.sh
```

### Individual Gates
```bash
# From project root
./ci/first_step/gate_0_integrity.sh
./ci/first_step/gate_1_lint.sh
./ci/first_step/gate_2_types.sh
./ci/first_step/gate_3_reality.sh
./ci/first_step/gate_4_antimock.sh
./ci/first_step/gate_5_determinism.sh
./ci/first_step/gate_6_artifacts.sh
```

## Gate Details

### Gate 0: Repo Integrity
**Checks for:**
- `pass` as sole function body
- `TODO`/`FIXME` in core code
- `raise NotImplementedError` in non-abstract code
- Empty returns (`return {}`, `return None`)
- Secrets (AWS keys, passwords, tokens)

**Paths checked:**
- `mahoun/`
- `output/`
- `api/`

### Gate 1: Format/Lint
**Tools:**
- `ruff check` - Linting
- `ruff format` - Formatting

**Rules:** E, F, I, UP, N, W (minimum)

### Gate 2: Type Safety
**Tools (in order of preference):**
- `basedpyright`
- `pyright`
- `mypy`

**Strategy:** Baseline approach - no new errors allowed

### Gate 3: Phase-1 Reality Tests
**What runs:**
```bash
pytest first_step_ci_cd/ -q --tb=short
```

**137 tests:**
- 18 Import tests
- 33 Structure tests
- 29 Contract tests
- 27 Light logic tests
- 30 Anti-mock tests

### Gate 4: Anti-Mock Proof
**Checks:**
1. Runs `first_step_ci_cd/test_5_anti_mock.py`
2. Verifies module complexity (line counts)

**Thresholds (configurable in `complexity_thresholds.json`):**
- `mahoun/agents/base_agent.py`: 500+ lines
- `mahoun/agents/claim_agent.py`: 400+ lines
- `output/base_generator.py`: 40+ lines
- `output/claim_generator.py`: 35+ lines

### Gate 5: Determinism Proof
**Method:**
1. Run tests twice
2. Compare exit codes
3. Compare test counts
4. Compare junit XML hashes (timestamps removed)

**Fail if:** Any difference detected

### Gate 6: Artifact + Traceability
**Generates:**
- `reality_report.json` - Machine-readable metadata
- `ci_summary.md` - Human-readable summary
- `junit.xml` - Test results (from Gate 3)

## Configuration Files

### `complexity_thresholds.json`
Defines minimum line counts for critical modules.

Example:
```json
{
  "mahoun/agents/base_agent.py": 500,
  "mahoun/agents/claim_agent.py": 400,
  "output/base_generator.py": 40
}
```

## Exit Codes

- `0` - Gate passed
- `1` - Gate failed
- `>1` - Severe failure (e.g., secrets detected)

## Environment Variables

- `MAHOUN_NO_EXTERNAL_CALLS=1` - Disable external service calls
- `MAHOUN_TEST_MODE=1` - Enable test mode
- `PYTHONHASHSEED=0` - Ensure determinism

## Troubleshooting

### "Gate 0 failed: placeholder detected"
Remove `pass`, `TODO`, or `raise NotImplementedError` from indicated file.

### "Gate 1 failed: formatting"
Run: `ruff format .`

### "Gate 2 failed: type errors"
Fix type hints or update baseline.

### "Gate 3 failed: tests failing"
Debug with: `pytest first_step_ci_cd/ -v`

### "Gate 5 failed: non-deterministic"
Check for:
- `random.random()` without seed
- `datetime.now()` in tests
- Network calls
- Dictionary/set iteration

## Maintenance

### Weekly
- Review gate durations
- Check for flaky tests

### Monthly
- Update complexity thresholds
- Review secrets patterns

## See Also

- `../../CI_LOCK.md` - Complete CI/CD documentation
- `../../first_step_ci_cd/README.md` - Test suite documentation
- `../../scripts/ci_run_first_step.sh` - Main runner script






