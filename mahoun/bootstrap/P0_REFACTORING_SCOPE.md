# P0 Bootstrap Refactoring - Surgical Scope Definition

**Date:** 2026-08-05  
**Status:** Phase 0.5 - Pre-Refactoring Characterization  
**Risk Level:** LOW (< 20% with proper constraints)

---

## 🎯 **Critical Principle: Surgical Refactoring Only**

```
BootstrapManager
        │
        ▼
Phase DAG
        │
        ▼
Executors  ← REFACTOR HERE ONLY
        │
        ▼
Actual Services
```

---

## 🔒 **TIER-0: LOCKED (Absolute No-Touch Zone)**

These components form the **immutable architecture foundation**. ANY change here requires:
- Constitutional amendment (mahoun/constitutional/)
- Full governance review
- New ADR with justification

### Locked Components:

| Component | File | Status | Reason |
|-----------|------|--------|--------|
| BootstrapManager | `mahoun/bootstrap/manager.py` | 🔒 FROZEN | Core orchestration logic |
| BootstrapContext | `mahoun/bootstrap/manager.py` | 🔒 FROZEN | Context ownership contract frozen |
| Phase DAG | `mahoun/bootstrap/bootstrap_contract.yaml` | 🔒 FROZEN | Execution order immutable |
| State Machine | `mahoun/bootstrap/BEHAVIOR_SNAPSHOT.md` | 🔒 FROZEN | State transitions validated |
| Service Registry | `mahoun/bootstrap/manager.py` | 🔒 FROZEN | Service registration protocol |
| Rollback Strategy | `mahoun/bootstrap/manager.py` | 🔒 FROZEN | Reverse execution order enforced |
| PhaseResult | `mahoun/bootstrap/manager.py` | 🔒 FROZEN | Result contract |
| BootstrapException | `mahoun/bootstrap/manager.py` | 🔒 FROZEN | Error hierarchy |

### Protected Invariants (from bootstrap_contract.yaml):

```yaml
invariants:
  - governance_first_always      # Phase 4 (GOVERNANCE_KERNEL) must complete before phase 5-12
  - fail_closed_on_error         # Any phase failure triggers immediate rollback
  - sequential_execution_strict  # Phases execute in exact DAG order
  - context_immutable_after_phase # Context keys set by phase P cannot be modified by phase P+1..12
  - rollback_reverse_order       # Rollback executes in exact reverse: 12→11→...→1
  - service_registry_append_only # Services can only be added, never removed mid-bootstrap
  - metrics_monotonic_increase   # Metrics accumulate, never decrease
```

---

## ✅ **TIER-1: REFACTORABLE (Safe Surgery Zone)**

These Executors are **God Objects** with high technical debt but isolated blast radius.

### Target Files:

| Executor | File | Lines | Status | Priority |
|----------|------|-------|--------|----------|
| EmbeddingModelsExecutor | `mahoun/bootstrap/executors/ai_ml_components.py` | 1591 | 🔧 REFACTOR | P0 |
| LLMLoaderExecutor | `mahoun/bootstrap/executors/ai_ml_components.py` | (part of 1591) | 🔧 REFACTOR | P0 |
| AgentRegistryExecutor | `mahoun/bootstrap/executors/ai_ml_components.py` | (part of 1591) | 🔧 REFACTOR | P0 |

### Refactoring Constraint:

**Interface Contract (MUST NOT CHANGE):**

```python
class BootstrapPhaseExecutor(ABC):
    @abstractmethod
    async def execute(self, context: BootstrapContext) -> PhaseResult:
        """Execute phase - signature FROZEN"""
        pass

    @abstractmethod
    async def rollback(self, context: BootstrapContext) -> None:
        """Rollback phase - signature FROZEN"""
        pass
```

As long as `execute()` and `rollback()` signatures remain identical, **internal refactoring is safe**.

---

## 📋 **Phase 0.5: Characterization Tests (Current Phase)**

**Goal:** Capture ACTUAL runtime **BEHAVIOR** (not just output) before ANY code changes.

### ⚠️ Critical: Behavioral Contract vs Interface Contract

**Interface contracts protect syntax. Behavioral contracts protect semantics.**

- **Interface Only (Insufficient):** Signature frozen, but behavior can drift
- **Behavioral Contract (Required):** Preserves context mutations, service registry, metrics, events, rollback semantics, exception handling

### Test Structure:

```
tests/bootstrap/characterization/
    contracts/                                # Behavioral contracts
        context_contract.json                 # Context mutation rules
        registry_contract.json                # Service registration rules
        metrics_contract.json                 # Metrics emission rules
        
    scenarios/                                # Test scenarios
        embedding_success.py
        embedding_missing_neo4j.py
        embedding_rollback_failure.py
        llm_success.py
        agent_registry_success.py
        
    test_embedding_executor_behavior.py
    test_llm_executor_behavior.py
    test_agent_registry_executor_behavior.py
    
mahoun/bootstrap/golden_master/
    snapshots/
        embedding_executor_success.json       # Full behavioral snapshot
        embedding_executor_missing_neo4j.json
        ...
```

---

## 📊 **Success Criteria**

### Phase 0.5 (Characterization Tests):

**Priority 1: Behavior Preservation = 100%**

- [ ] Behavioral contracts defined for all 3 executors
- [ ] Context mutation delta captured
- [ ] Service registry delta captured
- [ ] Metrics delta captured
- [ ] Event sequence captured
- [ ] Rollback semantics captured
- [ ] Exception fingerprints captured
- [ ] Golden master snapshots recorded (success + 2 failure scenarios each)
- [ ] CI gate enforces behavioral contract passage

### Phase 1 (Refactoring):

**Priority 1: Behavior Preservation**
- [ ] All characterization tests pass
- [ ] Behavioral contracts satisfied
- [ ] Contract validator passes
- [ ] Integration tests pass

**Priority 2: Complexity Reduction**
- [ ] God Object pattern eliminated
- [ ] Single Responsibility Principle restored
- [ ] Each service <150 lines

**Priority 3: LOC Reduction (Secondary)**
- [ ] Code reduced to ~400-700 lines total
- [ ] Note: Clean 700 lines > obfuscated 400 lines

---

## 🎯 **Risk Assessment (Updated)**

| Scenario | Risk | Mitigation |
|----------|------|------------|
| **Interface Contract Only** | 40-60% | Syntax protected, semantics drift |
| **Behavioral Contract** | 15-25% | Syntax + semantics protected |
| **Behavioral + Diff Verification** | **< 15%** | Complete preservation |

**Overall Risk:** From ~80% (full refactor) → **< 15%** (surgical + behavioral contracts)

---

**This document is subordinate to:**
- `mahoun/bootstrap/BEHAVIOR_SNAPSHOT.md` (architectural behavior)
- `mahoun/bootstrap/bootstrap_contract.yaml` (machine contract)
- `mahoun/constitutional/` (governance authority)

**Any conflict: Constitutional documents win.**
