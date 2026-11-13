# CI Pipeline Stages

This document describes the stages of the Mahoun CI pipeline and their ordering.

## Overview

The Mahoun CI pipeline is organized into distinct stages that enforce quality gates in a specific order. Each stage builds on the previous one, ensuring that fundamental issues are caught before more expensive checks run.

## Stage Ordering

```
ARCHITECTURE → CONTRACT → BEHAVIOR → PERFORMANCE
(Gates 0-7)   (Gate 8)   (Future)   (Future)
```

## Stage 1: ARCHITECTURE (Gates 0-7)

**Purpose**: Enforce architectural boundaries and structural integrity

**Gates**:
- **Gate 0: Repo Integrity** - Verifies core paths exist and no stub code in critical paths
- **Gate 1: Format/Lint** - Enforces code style with ruff
- **Gate DI Allowlist** - Enforces Neo4j dependency injection allowlist (blocks driver creation outside authorized files)
- **Gate 2: Type Safety** - Enforces type correctness with mypy
- **Gate 3: Phase-1 Reality Tests** - Runs basic reality checks
- **Gate 4: Anti-Mock Proof** - Ensures tests use real implementations, not mocks
- **Gate 5: Determinism Proof** - Verifies deterministic behavior
- **Gate 6: Artifact + Traceability** - Ensures proper artifact generation
- **Gate 7: Architecture Boundaries** - Enforces core/non-core module boundaries

**Why First?**
- Architectural violations can invalidate all other tests
- Fast to run (mostly static analysis)
- Catches fundamental design issues early
- Prevents wasted time on tests that would fail anyway

**Exit Behavior**: If any gate fails, the pipeline stops immediately. No point running contracts or behavior tests if the architecture is broken.

## Stage 2: CONTRACT (Gate 8)

**Purpose**: Validate that all core module interfaces conform to their formal contracts

**Gates**:
- **Gate 8: Contract Validation** - Runs all contract tests to verify:
  - Input schema compliance
  - Output schema compliance
  - Error handling contracts
  - Invariant enforcement (G1-G5, EL-I1-I7)
  - Immutability guarantees

**Why Second?**
- Contracts define the "shape" of the system
- Must pass before testing behavior
- Validates that interfaces are correctly defined
- Ensures all 6 core modules have valid contracts

**What It Tests**:
- `mahoun/schemas/contracts/core_contracts.py` - Core module contracts
- `mahoun/schemas/contracts/reasoning_contracts.py` - Reasoning engine contracts
- `mahoun/schemas/contracts/graph_contracts.py` - Graph builder contracts
- `mahoun/schemas/contracts/invariants_contracts.py` - Invariant system contracts
- `mahoun/schemas/contracts/schemas_contracts.py` - Schema validation contracts
- `mahoun/schemas/contracts/ledger_contracts.py` - Ledger contracts

**Test Count**: 287 contract tests (as of Phase 2 completion)

**Exit Behavior**: If contracts fail, the pipeline stops. No point testing behavior if the contracts are invalid.

## Stage 3: BEHAVIOR (Future)

**Purpose**: Validate that the system behaves correctly according to its contracts

**Planned Tests**:
- Unit tests for core modules
- Integration tests for module interactions
- End-to-end tests for complete workflows
- Property-based tests for invariant verification

**Why Third?**
- Behavior tests are more expensive than contract tests
- Requires valid architecture and contracts
- Tests actual functionality, not just structure

**Exit Behavior**: If behavior tests fail, the pipeline stops before performance tests.

## Stage 4: PERFORMANCE (Future)

**Purpose**: Ensure the system meets performance requirements

**Planned Tests**:
- Latency benchmarks
- Throughput tests
- Memory usage profiling
- Scalability tests

**Why Last?**
- Most expensive to run
- Only meaningful if behavior is correct
- Can be skipped for rapid iteration

## Running Stages

### Run All Stages
```bash
bash scripts/ci_run_first_step.sh
```

### Run Individual Gates
```bash
# Architecture stage
bash ci/first_step/gate_0_integrity.sh
bash ci/first_step/gate_1_lint.sh
bash ci/gates/gate_di_allowlist.sh        # Neo4j DI enforcement
bash ci/first_step/gate_2_types.sh
bash ci/first_step/gate_3_reality.sh
bash ci/first_step/gate_4_antimock.sh
bash ci/first_step/gate_5_determinism.sh
bash ci/first_step/gate_6_artifacts.sh
bash ci/first_step/gate_7_architecture.sh

# Contract stage
bash ci/first_step/gate_8_contracts.sh
```

## Stage Dependencies

```
Gate 0 (Repo Integrity)
  ↓
Gate 1 (Format/Lint)
  ↓
Gate DI Allowlist (Neo4j DI Enforcement)
  ↓
Gate 2 (Type Safety)
  ↓
Gate 3 (Reality Tests)
  ↓
Gate 4 (Anti-Mock)
  ↓
Gate 5 (Determinism)
  ↓
Gate 6 (Artifacts)
  ↓
Gate 7 (Architecture)
  ↓
Gate 8 (Contracts)
  ↓
[Future: Behavior Tests]
  ↓
[Future: Performance Tests]
```

## Design Principles

### 1. Fail Fast
Each stage stops the pipeline on failure. No point running expensive tests if fundamentals are broken.

### 2. Increasing Cost
Stages are ordered by execution cost:
- Architecture: Seconds (static analysis)
- Contracts: Seconds (schema validation)
- Behavior: Minutes (actual execution)
- Performance: Minutes to hours (benchmarking)

### 3. Increasing Specificity
Each stage gets more specific:
- Architecture: "Is the structure correct?"
- Contracts: "Are the interfaces correct?"
- Behavior: "Does it work correctly?"
- Performance: "Does it work fast enough?"

### 4. Independence
Each gate within a stage should be independently runnable for debugging.

## Adding New Gates

When adding a new gate, consider:

1. **Which stage does it belong to?**
   - Structure/boundaries → ARCHITECTURE
   - Interface validation → CONTRACT
   - Functionality → BEHAVIOR
   - Speed/efficiency → PERFORMANCE

2. **What is its execution cost?**
   - Place cheaper gates earlier in the stage

3. **What does it depend on?**
   - Ensure dependencies run before it

4. **How does it fail?**
   - Provide clear, actionable error messages
   - Include fix instructions in the output

## Troubleshooting

See `ci/first_step/TROUBLESHOOTING.md` for common failures and resolutions.
