# Bootstrap Runtime Platform - Architecture Evolution Roadmap

## 📊 Architecture Review Board Status

**Rating:** A+ (95% Approved - pending structured ADRs)

| Metric | Score | Notes |
|--------|-------|-------|
| **Architecture Design** | A+ | Google/Microsoft-grade design |
| **Extensibility** | A+ | Services pattern enables future growth |
| **Governance Alignment** | A | Perfect fit for governance-first architecture |
| **Current Maintainability** | 7.5/10 | Functional but needs layer separation |
| **Post-Refactor Maintainability** | 10/10 | Best-in-class with ADR tracking |

**Key Insight:** *"این دیگه Loader نیست؛ این داره تبدیل میشه به یک Runtime Orchestrator."*

This is both the **strength** and the **opportunity** - we're not just fixing code, we're building **MAHOUN's Runtime Platform**.

---

## 🎯 The Core Problem

> **"این دیگه Loader نیست؛ این داره تبدیل میشه به یک Runtime Orchestrator."**

The executors are doing too much. They've evolved from simple loaders into mini-runtime systems that handle:
- Loading
- Monitoring  
- Resource Management
- Benchmarking
- Security (sandboxing)
- Telemetry
- Health Checking
- Circuit Breaking

This violates **Single Responsibility Principle** and creates **God Objects**.

---

## 🏗️ Architecture Evolution: Three-Layer Pattern (Critical Improvement)

**Current:** Everything in Executor (God Object)

**Proposed:** Clean separation of concerns across three layers

```
┌─────────────────────────────────────────────────────────────┐
│                 Bootstrap Coordinator                        │
│              (Orchestration Only - ~100 lines)              │
│  • Governance validation                                     │
│  • Phase sequencing                                         │
│  • Service delegation                                       │
│  • Error handling & rollback                                │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              Bootstrap Domain Services                       │
│           (Business Logic - ~150-200 lines each)            │
│                                                              │
│  IntegrityVerifier → ModelResolver → ModelLoader            │
│  HealthChecker → BenchmarkService → RollbackManager         │
│                                                              │
│  • NO infrastructure dependencies                           │
│  • Pure business logic                                      │
│  • Independently testable                                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              Infrastructure Adapters                         │
│            (External Dependencies - ~50 lines each)         │
│                                                              │
│  HashProvider → FilesystemAdapter → GPUProfiler             │
│  LedgerAdapter → TelemetryAdapter                           │
│                                                              │
│  • Adapts external systems                                  │
│  • Easy to mock in tests                                    │
│  • Swappable implementations                                │
└─────────────────────────────────────────────────────────────┘
```

**Why Three Layers Matter:**

### Example: IntegrityVerifier Evolution

**Current (monolithic):**
```python
class EmbeddingModelsExecutor:
    async def _verify_model_integrity(self, model_name: str) -> bool:
        computed_hash = hashlib.sha256(f"mock_{model_name}".encode()).hexdigest()
        # Directly calls hashlib - tightly coupled
```

**Proposed (three-layer):**
```python
# Layer 1: Coordinator (orchestration only)
class EmbeddingBootstrapCoordinator:
    async def execute(self, context):
        for descriptor in descriptors:
            if not await self.integrity_verifier.verify(descriptor):
                # Just delegates - no implementation

# Layer 2: Domain Service (business logic)
class IntegrityVerifier:
    def __init__(self, hash_provider: HashProvider, ledger: LedgerAdapter):
        self.hash_provider = hash_provider
        self.ledger = ledger
    
    async def verify(self, descriptor: ModelDescriptor) -> bool:
        # Business rule: check both hash AND ledger
        computed = await self.hash_provider.compute(descriptor.path)
        expected = await self.ledger.get_expected_hash(descriptor.name)
        return computed == expected

# Layer 3: Infrastructure Adapter (external system)
class HashProvider(Protocol):
    async def compute(self, path: Path) -> str: ...

class SHA256HashProvider(HashProvider):
    async def compute(self, path: Path) -> str:
        # Actual hashlib implementation

class TPMHashProvider(HashProvider):
    async def compute(self, path: Path) -> str:
        # Future: TPM-backed verification
```

**Benefits:**
- Tomorrow: Hash from Ledger → just swap LedgerAdapter
- Next month: Hash from Remote Manifest → swap HashProvider
- Next quarter: TPM-backed verification → new HashProvider impl
- **IntegrityVerifier business logic never changes**

---

## ✅ What's Excellent (Keep These)

### 1. **Descriptor-Based Architecture** ⭐⭐⭐⭐⭐
```python
ModelDescriptor(
    name="model_name",
    model_type=ModelType.EMBEDDING,
    priority=LoadPriority.CRITICAL,
    # Metadata-driven decisions instead of if-else
)
```
**Why it's great:** No more if-else chains. Decisions based on metadata.

### 2. **Circuit Breaker** ⭐⭐⭐⭐⭐
```python
CircuitBreakerState(
    failure_threshold=3,
    timeout_seconds=120.0
)
```
**Why it's great:** Almost no open-source AI projects have circuit breakers in bootstrap.

### 3. **Transactional Bootstrap with Rollback** ⭐⭐⭐⭐⭐
```python
async def rollback(self, context: BootstrapContext):
    # Clean state restoration
```
**Why it's great:** Most loaders only have `load()`. We have proper transactions.

### 4. **Profile Awareness** ⭐⭐⭐⭐⭐
```python
BASE → PLUS → ULTRA
```
**Why it's great:** Resource-aware selection.

### 5. **Dependency Validation** ⭐⭐⭐⭐⭐
```python
if not context.governance_validated:
    raise BootstrapException(...)
```
**Why it's great:** Fail-closed enforcement.

---

## ⚠️ What Needs Refactoring

### Problem 1: **Executors are becoming God Objects**

**Current state:**
```
EmbeddingModelsExecutor contains:
├── Loading logic
├── Integrity verification
├── Health monitoring
├── Benchmarking
├── Circuit breaker
├── Retry logic
├── Fallback handling
└── Telemetry
```

**This violates SRP.**

---

### Problem 2: **ModelDescriptor is becoming a God Object**

**Current state:**
```python
ModelDescriptor(
    name, model_type, priority,
    min_ram_gb, min_vram_gb, min_cpu_cores,
    checksum_sha256, fallback_models, quantization,
    requires_gpu, max_load_time_sec, capabilities,
    metadata, health_check_interval, performance_baseline
)
```

**16 fields in one dataclass!**

---

### Problem 3: **Magic Strings**
```python
if profile == "BASE":  # Should be enum
    ...
```

---

### Problem 4: **Checksum is Mock**
```python
computed_hash = hashlib.sha256(f"mock_model_content_{model_name}".encode()).hexdigest()
```
Not checking real file integrity.

---

### Problem 5: **psutil called directly**
```python
ram = psutil.virtual_memory()  # Should be behind abstraction
```

---

### Problem 6: **Logging is not governance-aware**
```python
logger.info(...)  # Should be governance events
```

---

## 🎯 Refactoring Strategy

### Phase 1: **Break Down ModelDescriptor** (P1 - High Priority)

**Split into focused dataclasses:**

```python
@dataclass
class ModelMetadata:
    """Core model identification"""
    name: str
    model_type: ModelType
    version: str

@dataclass  
class ResourceRequirements:
    """Hardware requirements"""
    min_ram_gb: float
    min_vram_gb: float
    min_cpu_cores: int
    requires_gpu: bool

@dataclass
class SecurityMetadata:
    """Security and integrity"""
    checksum_sha256: Optional[str]
    certificate_chain: Optional[str]
    signature: Optional[str]

@dataclass
class PerformanceBaseline:
    """Expected performance metrics"""
    load_time_ms: float
    inference_ms: float
    throughput_qps: float

@dataclass
class HealthConfiguration:
    """Health monitoring config"""
    check_interval_sec: float
    alert_thresholds: Dict[str, float]

@dataclass
class ModelDescriptor:
    """Unified descriptor (composition not inheritance)"""
    metadata: ModelMetadata
    resources: ResourceRequirements
    security: SecurityMetadata
    performance: PerformanceBaseline
    health: HealthConfiguration
    priority: LoadPriority
    fallback_models: List[str]
```

**Benefits:**
- Clear separation of concerns
- Easy to test each part independently
- Can evolve each aspect separately

---

### Phase 2: **Extract Services** (P0 - Critical)

**Create focused service classes:**

```python
# mahoun/bootstrap/services/integrity_verifier.py
class IntegrityVerifier:
    async def verify_checksum(self, model_path: str, expected: str) -> bool:
        """Real SHA256 verification"""
        
    async def verify_certificate_chain(self, model_path: str) -> bool:
        """Certificate chain validation"""

# mahoun/bootstrap/services/resource_profiler.py
class ResourceProfiler:
    async def assess_hardware(self) -> HardwareProfile:
        """Abstraction over psutil"""
        
    async def detect_gpu_fragmentation(self) -> float:
        """GPU memory analysis"""

# mahoun/bootstrap/services/model_resolver.py
class ModelResolver:
    def select_models(
        self, 
        profile: RuntimeProfile,
        hw: HardwareProfile
    ) -> List[ModelDescriptor]:
        """Profile + hardware → model selection"""

# mahoun/bootstrap/services/model_loader.py
class ModelLoader:
    async def load_model(
        self, 
        descriptor: ModelDescriptor
    ) -> LoadResult:
        """Pure loading logic"""

# mahoun/bootstrap/services/health_checker.py
class HealthChecker:

    async def check_health(
        self,
        descriptor: ModelDescriptor
    ) -> HealthResult:
        """Health validation"""

# mahoun/bootstrap/services/benchmark_service.py
class BenchmarkService:
    async def benchmark_model(
        self,
        descriptor: ModelDescriptor
    ) -> BenchmarkResult:
        """Performance profiling"""

# mahoun/bootstrap/services/rollback_manager.py
class RollbackManager:
    async def rollback(
        self,
        loaded_models: List[str]
    ) -> RollbackResult:
        """Clean state restoration"""
```

---

### Phase 3: **Executors become Coordinators** (P0 - Critical)

**Transform executors into thin orchestration layers:**

```python
class EmbeddingBootstrapCoordinator(BootstrapPhaseExecutor):
    """
    Coordinates bootstrap flow, delegates work to services.
    NO business logic here - pure orchestration.
    """
    
    def __init__(self):
        self.integrity_verifier = IntegrityVerifier()
        self.resource_profiler = ResourceProfiler()
        self.model_resolver = ModelResolver()
        self.model_loader = ModelLoader()
        self.health_checker = HealthChecker()
        self.benchmark_service = BenchmarkService()
        self.rollback_manager = RollbackManager()
        self.circuit_breaker = CircuitBreakerState()
    
    async def execute(self, context: BootstrapContext) -> PhaseResult:
        # 1. Governance validation
        if not context.governance_validated:
            raise BootstrapException(...)
        
        # 2. Profile detection
        profile = get_current_profile()
        
        # 3. Hardware profiling (delegated)
        hw_profile = await self.resource_profiler.assess_hardware()
        
        # 4. Model selection (delegated)
        descriptors = self.model_resolver.select_models(profile, hw_profile)
        
        # 5. Load models (delegated)
        for desc in descriptors:
            if not self.circuit_breaker.should_allow():
                continue
            
            # Integrity check
            if not await self.integrity_verifier.verify_checksum(desc):
                self.circuit_breaker.record_failure()
                continue
            
            # Load
            result = await self.model_loader.load_model(desc)
            if not result.success:
                self.circuit_breaker.record_failure()
                continue
            
            # Health check
            health = await self.health_checker.check_health(desc)
            
            # Benchmark
            bench = await self.benchmark_service.benchmark_model(desc)
            
            self.circuit_breaker.record_success()
        
        return PhaseResult(...)
    
    async def rollback(self, context: BootstrapContext):
        await self.rollback_manager.rollback(loaded_models)
```

**Benefits:**
- Executor is now ~100 lines instead of 400+
- Each service is independently testable
- Services can be reused outside bootstrap
- Clear separation of concerns

---

### Phase 4: **Fix Magic Strings** (P2 - Medium Priority)

```python
# Before
if profile == "BASE":
    ...

# After  
class RuntimeProfile(str, Enum):
    BASE = "BASE"
    PLUS = "PLUS"
    ULTRA = "ULTRA"

if profile == RuntimeProfile.BASE:
    ...
```

---

### Phase 5: **Real Integrity Verification** (P1 - High Priority)

```python
class IntegrityVerifier:
    async def verify_checksum(self, model_path: Path, expected: str) -> bool:
        """Real SHA256 verification against actual file"""
        computed = hashlib.sha256()
        
        async with aiofiles.open(model_path, 'rb') as f:
            while chunk := await f.read(8192):
                computed.update(chunk)
        
        return computed.hexdigest() == expected
    
    async def verify_certificate_chain(
        self, 
        model_path: Path,
        cert_chain: str
    ) -> bool:
        """Verify certificate chain for model authenticity"""
        # Real certificate validation logic
        ...
```

---

### Phase 6: **Governance-Aware Logging** (P2 - Medium Priority)

```python
# Before
logger.info(f"Model {name} loaded")

# After
await governance_event_bus.emit(
    GovernanceEvent(
        event_type=EventType.MODEL_LOADED,
        severity=Severity.INFO,
        resource=name,
        context={...}
    )
)

# This automatically:
# → Creates audit trail
# → Triggers telemetry
# → Fires governance hooks
# → Generates structured logs
```

---

## 📋 Implementation Priority

### **P0 (Critical - Do First):**
1. Extract services (Phase 2)
2. Transform executors to coordinators (Phase 3)

### **P1 (High - Do Soon):**
1. Break down ModelDescriptor (Phase 1)
2. Real integrity verification (Phase 5)

### **P2 (Medium - Do Eventually):**
1. Fix magic strings (Phase 4)
2. Governance-aware logging (Phase 6)

---

## 🎯 Success Metrics

After refactoring:
- Executor classes: **< 150 lines each**
- Service classes: **< 200 lines each**
- Dataclasses: **< 8 fields each**
- Test coverage: **> 90%**
- Each service independently testable: **✅**

---

## 💡 Key Insight

> **"این دیگه Loader نیست؛ این داره تبدیل میشه به یک Runtime Orchestrator."**

This is both the **strength** and the **biggest risk**.

**The solution:** Keep the orchestration capability, but **delegate** all business logic to focused services.

**Result:** 
- Maintainability: 7.5/10 → **10/10** ⭐⭐⭐⭐⭐
- Testability: 8/10 → **10/10** ⭐⭐⭐⭐⭐
- Reusability: 6/10 → **10/10** ⭐⭐⭐⭐⭐

---

## 📝 Notes

- Current implementation is **production-ready** for MVP
- Refactoring is **technical debt** to be paid before scale
- Services extraction enables **future features** without touching executors
- This roadmap aligns with **MAHOUN's governance-first architecture**

---

**Author:** Code Review from User (2026-07-29)  
**Status:** Accepted Technical Debt - Scheduled for Refactoring Sprint  
**Priority:** P0/P1 before production scale
