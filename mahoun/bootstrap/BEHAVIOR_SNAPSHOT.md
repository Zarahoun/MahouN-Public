# Bootstrap Behavior Snapshot - Architectural Contract

**Date:** 2026-08-05  
**Purpose:** Complete behavioral specification before P0 refactoring  
**Status:** FROZEN - This is the architectural contract

---

## CRITICAL: This Document is the Architectural Contract

**NO observable behavior documented here may change during refactoring.**

Any deviation from this snapshot is a **breaking architectural change** and must be:
1. Explicitly justified
2. Reviewed by architecture team  
3. Documented in a new ADR
4. Tested for backward compatibility

---

## Phase Execution Order (IMMUTABLE)

```
Phase 1:  RUNTIME_INTEGRITY
          ↓
Phase 2:  CONFIGURATION
          ↓
Phase 3:  GOVERNANCE_KERNEL ← CRITICAL GOVERNANCE-FIRST BARRIER
          ↓
Phase 4:  IMMUTABLE_LEDGER
          ↓
Phase 5:  NEO4J
          ↓
Phase 6:  POLICY_ENGINE
          ↓
Phase 7:  EMBEDDING_MODELS
          ↓
Phase 8:  LLM_LOADER
          ↓
Phase 9:  AGENT_REGISTRY
          ↓
Phase 10: SERVICES
          ↓
Phase 11: API
          ↓
Phase 12: READINESS_GATE
```

**CRITICAL INVARIANT:** Phase 3 (GOVERNANCE_KERNEL) MUST complete before ANY service creation.

---

## Phase Dependencies (DAG)

```
RUNTIME_INTEGRITY → (none)
CONFIGURATION → RUNTIME_INTEGRITY
GOVERNANCE_KERNEL → CONFIGURATION
IMMUTABLE_LEDGER → GOVERNANCE_KERNEL
NEO4J → GOVERNANCE_KERNEL
POLICY_ENGINE → NEO4J
EMBEDDING_MODELS → GOVERNANCE_KERNEL, NEO4J
LLM_LOADER → EMBEDDING_MODELS
AGENT_REGISTRY → LLM_LOADER
SERVICES → AGENT_REGISTRY, NEO4J, (conditional: RAG)
API → SERVICES, NEO4J, GOVERNANCE_KERNEL
READINESS_GATE → API
```

**Verification:** No circular dependencies exist.

---

## Critical Invariants (MUST NEVER CHANGE)

1. **Governance-First:** Phase 3 MUST complete before Phase 5+
2. **Fail-Closed:** Any phase failure stops entire bootstrap
3. **Single Initialization:** Each phase runs exactly once
4. **Sequential Execution:** No parallel phase execution
5. **Rollback Order:** Reverse of execution order
6. **Context Immutability:** Previous phases' context cannot be modified by later phases
7. **Service Registry:** Services only added, never removed (except rollback)

---

## BootstrapContext Contract (FROZEN)

**Every phase has EXACTLY ONE context mutation responsibility.**

| Phase | Allowed Context Key | Type | Immutable After Phase |
|-------|-------------------|------|----------------------|
| `RUNTIME_INTEGRITY` | `runtime_info` | `RuntimeInfo` | ✓ |
| `CONFIGURATION` | `config` | `ConfigurationState` | ✓ |
| `GOVERNANCE_KERNEL` | `governance_controller` | `UnifiedGovernanceController` | ✓ |
| `IMMUTABLE_LEDGER` | `immutable_ledger` | `ImmutableLedger` | ✓ |
| `NEO4J` | `neo4j_connection` | `Neo4jConnection` | ✓ |
| `POLICY_ENGINE` | `policy_engine` | `PolicyEngine` | ✓ |
| `EMBEDDING_MODELS` | `embedding_service` | `LocalEmbeddingService` | ✓ |
| `LLM_LOADER` | `model_manager` | `ModelManager` | ✓ |
| `AGENT_REGISTRY` | `agent_registry` | `AgentRegistry` | ✓ |
| `SERVICES` | `services` | `ServiceRegistry` | ✓ |
| `API` | `api_state` | `APIState` | ✓ |
| `READINESS_GATE` | `readiness_report` | `ReadinessReport` | ✓ |

**RULE:** If Phase N writes to a context key owned by Phase M (M < N), this is a **P0 architectural violation**.

**VALIDATION:**
```python
# Any phase attempting to mutate previous phase's context MUST fail
assert context.runtime_info is context._frozen_keys['runtime_info']
```

---

## State Transition Contract (FROZEN)

**Bootstrap phases transition through exactly these states:**

```
CREATED
   ↓
VALIDATING ← (prerequisite checks)
   ↓
INITIALIZING ← (resource allocation)
   ↓
RUNNING ← (actual phase execution)
   ↓
COMPLETED ← (success path)

ERROR PATHS:
   ↓
FAILED ← (phase execution error)
   ↓
ROLLING_BACK ← (undo journal execution)
   ↓
ROLLED_BACK ← (cleanup complete)
   ↓
TERMINATED ← (final state)
```

**State Transition Rules:**

| From State | To State | Trigger | Reversible |
|-----------|----------|---------|------------|
| `CREATED` | `VALIDATING` | Bootstrap start | ✓ |
| `VALIDATING` | `INITIALIZING` | Prerequisites pass | ✓ |
| `VALIDATING` | `FAILED` | Prerequisites fail | ✗ |
| `INITIALIZING` | `RUNNING` | Resources allocated | ✓ |
| `INITIALIZING` | `FAILED` | Resource allocation fails | ✗ |
| `RUNNING` | `COMPLETED` | Phase success | ✗ |
| `RUNNING` | `FAILED` | Phase error | ✗ |
| `FAILED` | `ROLLING_BACK` | Rollback triggered | ✗ |
| `ROLLING_BACK` | `ROLLED_BACK` | Undo journal complete | ✗ |
| `ROLLED_BACK` | `TERMINATED` | Cleanup complete | ✗ |

**FORBIDDEN TRANSITIONS:**
- `COMPLETED` → `FAILED` (cannot fail after success)
- `ROLLED_BACK` → `RUNNING` (cannot restart after rollback)
- `TERMINATED` → any state (terminal state)

**VALIDATION:**
```python
# Adding a new state requires ADR + constitutional approval
ALLOWED_STATES = frozenset([
    'CREATED', 'VALIDATING', 'INITIALIZING', 
    'RUNNING', 'COMPLETED', 'FAILED',
    'ROLLING_BACK', 'ROLLED_BACK', 'TERMINATED'
])
assert phase.state in ALLOWED_STATES
```

---

## Refactoring Constraints

**DURING P0 REFACTORING, THE FOLLOWING MUST NOT CHANGE:**

✅ **Can Change:**
- Internal executor implementation
- Service extraction to separate classes
- Coordinator pattern adoption
- Descriptor decomposition
- Rollback journal implementation

❌ **Cannot Change:**
- Phase execution order
- Phase dependencies
- Context mutation points
- Service registry keys
- Rollback order
- Exception propagation
- Governance checkpoints
- Observable behavior (logs, metrics, events)

---

**This snapshot is FROZEN. Any change requires explicit architectural approval.**

---

## Machine-Readable Contract & Validation

This behavioral snapshot has a **machine-readable counterpart** for automated validation:

- **Contract:** `mahoun/bootstrap/bootstrap_contract.yaml`
- **Validator:** `mahoun/bootstrap/contract_validator.py`
- **CI Gate:** `ci/gates/gate_bootstrap_contract.sh`

**Run validation:**
```bash
python3 -m mahoun.bootstrap.contract_validator --verbose
```

The validator checks:
1. ✅ Phase execution order unchanged
2. ✅ No circular dependencies in DAG
3. ✅ Context ownership uniqueness
4. ✅ State machine validity
5. ✅ No forbidden state transitions
6. ✅ All architectural invariants defined

**This validation runs automatically in CI** and will block any PR that violates the frozen contract.

---

**Last Updated:** 2026-07-29  
**Snapshot Version:** 1.0  
**Contract Version:** 1.0.0  
**Refactoring Target:** P0 Service Extraction & Coordinator Pattern
