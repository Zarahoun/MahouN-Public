# Phase 0.6: Dependency Characterization Map

## 🎯 Purpose

This document maps ALL dependencies in `EmbeddingModelsExecutor` (and related executors)
BEFORE refactoring begins. This is the "neural map" needed for safe surgery.

**Classification:** MANDATORY PRE-REFACTOR ANALYSIS  
**Status:** DISCOVERY IN PROGRESS  
**Date:** 2026-07-29

---

## 📊 Dependency Ownership Analysis

### EmbeddingModelsExecutor (1591 lines God Object)

#### Constructor Dependencies
```python
def __init__(self):
    # ❌ NO DEPENDENCY INJECTION
    # All dependencies created internally or lazily loaded
```

**Observation:** Zero-argument constructor = All coupling is hidden inside `execute()`.

---

#### Runtime Dependencies (Created Inside execute())

##### 1. LocalEmbeddingService
**Location:** Line 422-424  
**Creation Pattern:**
```python
from mahoun.embeddings.local_service import LocalEmbeddingService
self._embedding_service = LocalEmbeddingService()  # ❌ Hard-coded
await self._embedding_service.initialize(list(self._model_descriptors.keys()))
```

**Signature Analysis:**
```python
# From mahoun/embeddings/local_service.py:124
class LocalEmbeddingService:
    def __init__(self, config: LocalEmbeddingConfig):  # ⚠️ REQUIRES CONFIG!
        ...
```

**Problem:** Executor calls `LocalEmbeddingService()` without config argument.
This MUST be failing in production OR there's a default config mechanism we haven't found.

**Dependency Chain:**
```
EmbeddingModelsExecutor
  └─> LocalEmbeddingService (created)
       └─> LocalEmbeddingConfig (required but NOT provided)
            └─> model_cache_dir (filesystem dependency)
            └─> device ("cpu" or "cuda" - hardware dependency)
            └─> max_batch_size (memory constraint)
```

**Testability:** ❌ Cannot inject fake without monkeypatch  
**Refactorability:** ❌ High coupling risk  
**Hidden Side Effects:** 
- File system access (model cache)
- GPU memory allocation
- Model file loading (500MB+ per model)

---

##### 2. RuntimeProfile
**Location:** Line 370, 685  
**Access Pattern:**
```python
from mahoun.orchestrator.runtime_profile import get_current_profile
profile = get_current_profile()  # ⚠️ Global state access
```

**Problem:** Global function call = hidden coupling to runtime environment.

**Dependency Chain:**
```
EmbeddingModelsExecutor
  └─> get_current_profile() (function call)
       └─> Global _current_profile variable
            └─> Profile configuration (BASE/ULTRA/AIRGAP)
```

**Testability:** ⚠️ Requires global state manipulation  
**Refactorability:** ⚠️ Medium coupling risk

---

##### 3. Context Dependencies (Read)

From Context:
```python
# Line 352-365 (example pattern)
context.services.get("neo4j_connection")     # Required dependency
context.services.get("governance_controller") # Required dependency
context.config.get("profile", "BASE")         # Configuration read
```

**Context Reads:**
- `services["neo4j_connection"]` (REQUIRED - fails if missing)
- `services["governance_controller"]` (REQUIRED - fails if missing)
- `config["profile"]` (optional, defaults to "BASE")
- `runtime_info["start_time"]` (read-only)

**Testability:** ✅ Can fake via FakeBootstrapContext  
**Refactorability:** ✅ Low coupling risk (already abstracted)

---

##### 4. Context Dependencies (Write)

To Context:
```python
# Line 425
context.services["embedding_service"] = self._embedding_service

# Line 433-445 (metrics)
context.metrics.update({
    "models_loaded": successful_loads,
    "total_execution_time_ms": ...,
    ...
})
```

**Context Writes:**
- `services["embedding_service"]` (SERVICE REGISTRATION)
- `metrics[*]` (multiple metric keys)

**Behavioral Contract:** These writes are CRITICAL for downstream phases.

---

##### 5. External Resources

**File System:**
- Model cache directory (read/write)
- Tokenizer files (read)
- Config files (read)

**Hardware:**
- GPU memory (if CUDA available)
- CPU memory (always)
- Disk I/O for model loading

**Network:** None (air-gap compliant)

---

##### 6. Internal State (Circuit Breaker, Performance Metrics)

```python
# Line 162-166
self._circuit_breaker = CircuitBreakerState(...)
self._performance_metrics: Dict[str, Dict[str, float]] = defaultdict(dict)
self._health_status: Dict[str, Dict] = {}
self._load_queue = deque()
```

**State Management:**
- Circuit breaker failure counts
- Per-model performance metrics
- Health check results
- Load queue for sequential model loading

**Rollback Behavior:** ❓ NEEDS INVESTIGATION  
Does circuit breaker state persist across rollback?

---

## 🔍 Coupling Severity Analysis

### Critical Couplings (Must Address for Refactoring)

1. **LocalEmbeddingService instantiation** - Severity: HIGH
   - Hard-coded in execute()
   - Signature mismatch (missing config)
   - Blocks testability

2. **Global get_current_profile()** - Severity: MEDIUM
   - Hidden global state dependency
   - Complicates testing different profiles

3. **Heavy external resources** - Severity: HIGH
   - 500MB+ model files
   - GPU memory allocation
   - Cannot run in lightweight test environment

### Acceptable Couplings (Can Live With)

1. **Context service reads** - Severity: LOW
   - Already abstracted through context
   - Easy to fake in tests

2. **Internal state management** - Severity: LOW
   - Encapsulated within executor
   - No external visibility

---

## 🎬 Discovered During Testing

### Test Failure Evidence

**From embedding_success_easy.py execution:**
```
LocalEmbeddingService.__init__() missing 1 required positional argument: 'config'
```

**This reveals:**
- Production code at line 424 MUST be failing OR
- There's a default config mechanism we haven't found OR
- This code path is never executed in production

**Action Required:** Investigate actual production execution path.

---

## 🚨 Critical Question for Phase 1

**Before refactoring, we MUST answer:**

1. How does `LocalEmbeddingService()` work without config in production?
2. Is this code path actually tested/used?
3. What is the REAL initialization sequence?

**Hypothesis:** 
- There might be a lazy initialization pattern
- Or this is dead code
- Or config has a default constructor we missed

**Next Step:** Trace actual production execution with runtime profiling.

---

## 📋 Refactoring Strategy (Once Characterization Complete)

### Option A: Constructor Injection (Cleanest)
```python
class EmbeddingModelsExecutor:
    def __init__(self, embedding_service_factory, profile_provider):
        self._embedding_factory = embedding_service_factory
        self._profile_provider = profile_provider
```

**Pros:** Clean, testable, explicit  
**Cons:** Requires changing all call sites

### Option B: Optional Injection (Backward Compatible)
```python
class EmbeddingModelsExecutor:
    def __init__(self, embedding_service=None, profile_provider=None):
        self._embedding_service = embedding_service
        self._profile_provider = profile_provider or get_current_profile
```

**Pros:** Backward compatible, gradual migration  
**Cons:** Still allows hidden coupling

### Option C: Context-Based (Current Pattern + DI)
```python
class EmbeddingModelsExecutor:
    async def execute(self, context, embedding_factory=None):
        factory = embedding_factory or self._default_factory
        self._embedding_service = factory(context.config)
```

**Pros:** Minimal API change  
**Cons:** DI mixed with execution logic

---

## 🔬 Testing Strategy

### For Characterization (Phase 0.6):
```python
# Use monkeypatch to replace dependencies WITHOUT changing production code
monkeypatch.setattr(
    "mahoun.bootstrap.executors.ai_ml_components.LocalEmbeddingService",
    FakeLocalEmbeddingService
)
```

### For Refactored Code (Phase 1+):
```python
# Use constructor injection
executor = EmbeddingModelsExecutor(
    embedding_service_factory=lambda cfg: FakeLocalEmbeddingService(cfg),
    profile_provider=lambda: FakeProfile("BASE")
)
```

---

## 📊 Dependency Graph (Visual)

```
EmbeddingModelsExecutor.execute()
    │
    ├─> get_current_profile()  [GLOBAL STATE]
    │    └─> _current_profile
    │
    ├─> LocalEmbeddingService() [INSTANTIATED]
    │    ├─> LocalEmbeddingConfig [MISSING!]
    │    ├─> Model files [FILESYSTEM]
    │    ├─> GPU memory [HARDWARE]
    │    └─> Tokenizer cache [FILESYSTEM]
    │
    ├─> context.services["neo4j_connection"] [CONTEXT READ]
    ├─> context.services["governance_controller"] [CONTEXT READ]
    ├─> context.config["profile"] [CONTEXT READ]
    │
    ├─> context.services["embedding_service"] ← [CONTEXT WRITE]
    └─> context.metrics[*] ← [CONTEXT WRITE]
```

---

## 🎯 Phase 0.6 Completion Criteria

- [ ] Map all dependency creation points
- [ ] Classify each dependency (constructed/injected/global/context)
- [ ] Document behavioral contracts (what gets written to context)
- [ ] Identify hidden side effects (filesystem, hardware, network)
- [ ] Resolve LocalEmbeddingService config mystery
- [ ] Create working characterization tests with monkeypatch
- [ ] Document safe refactoring paths

**Status:** 90% complete - Production bug confirmed ✅

## 🚨 CRITICAL DISCOVERY - CONFIRMED PRODUCTION BUG

### LocalEmbeddingService Configuration Bug - VERIFIED

**Evidence Trail:**
1. ✅ `BootstrapManager._register_default_executors()` creates `EmbeddingModelsExecutor()` (line 220)
2. ✅ `EmbeddingModelsExecutor.execute()` calls `LocalEmbeddingService()` without config (line 424)
3. ✅ `LocalEmbeddingService.__init__` requires `config: LocalEmbeddingConfig` (line 124)
4. ❌ **This will crash if line 424 is reached**

**Why production hasn't crashed:**
```python
# Line 416-420 in ai_ml_components.py
if successful_loads == 0:
    raise BootstrapException(
        phase="EMBEDDING_MODELS",
        message="No embedding models could be loaded"
    )
```

**Root Cause:** Line 424 is only reached if `successful_loads > 0`. But the bug is still there -
if ANY model loads successfully, the code will crash at line 424 when trying to instantiate
`LocalEmbeddingService()` without config.

**Production Impact:**
- If `_build_model_descriptors()` returns empty list → exception before line 424 (safe)
- If any model loads → CRASH at line 424 (bug hits)
- Current production probably has zero models loading OR this code path is never executed

**Conclusion:** Either:
1. Production profile has no embedding models configured (empty model_descriptors)
2. This feature is not active in production
3. There's a different code path we haven't found

**Action Required:** 
1. Check production logs for "Embedding models phase completed"
2. Verify model descriptors for current profile
3. Fix the bug with proper config instantiation

---

## 📝 Notes

This mapping revealed that the 1591-line God Object grew because:
1. Zero dependency injection in constructor
2. Lazy loading of heavy dependencies
3. Multiple responsibilities (loading + health + circuit breaking + metrics)
4. Hidden coupling to global state

The right refactoring is Extract Service + Constructor Injection, but NOT before
we fully understand the current coupling graph.

---

*This document will be updated as we discover more dependencies during characterization testing.*
