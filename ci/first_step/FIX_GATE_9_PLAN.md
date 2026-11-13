# طرح جامع اصلاح Gate 9

## هدف
資产 کردن Gate 9 به صورت کامل (100% pass)

## وضعیت فعلی
```
مجموع: ۴۹۵ تست
✅ پاس: ۴۳۲ (۸۷.۳%)
❌ شکست: ۴۴ (۸.۹%)
❌ خطا: ۱۲ (۲.۴%)
```

## دسته‌بندی مشکلات

### گروه ۱: TrustedHostMiddleware (۲۵ شکست - اولویت ۱)
**فایل**: `tests/governance/test_api_integration.py`
**علت**: middleware درخواست‌های TestClient را به دلیل host header نامعتبر رد می‌کند
**راه‌حل**: Override کردن middleware در fixture

### گروه ۲: Governance Context (۱ شکست - اولویت ۲)
**فایل**: `tests/governance/test_governance_hardening_sprint.py`
**تست**: `test_task6_100_concurrent_no_token_leakage`
**علت**: تست انتظار دارد بدون governance context اجرا شود، ولی context لازم است
**راه‌حل**: برقراری context در تست

### گروه ۳: مشکلات قبلی (۱۸ شکست - اولویت ۳)
**فایل‌ها**: مختلف
**علت**: تنظیمات نادرست تست، dépendency missing، و غیره
**راه‌حل**: بررسی و اصلاح هر کدام

---

## راه‌حل جامع

### اصلاح ۱: فیکسچر client در test_api_integration.py

**فایل**: `tests/governance/test_api_integration.py`

**تغییرات مورد نیاز**:

```python
# در آغاز فایل، import‌های لازم را اضافه کنید
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.testclient import TestClient

# فیکسچر client را کامل اصلاح کنید
@pytest.fixture
def client(mock_verdict_engine):
    """Create test client with mocked verdict engine, governance context, and middleware override"""
    from api.routers.reasoning import get_verdict_engine, require_governance_context
    from mahoun.core.governance.governance_context import GovernanceContext
    
    # Override verdict engine
    app.dependency_overrides[get_verdict_engine] = lambda: mock_verdict_engine
    
    # Override governance context dependency
    def mock_require_governance_context():
        """Mock governance context that returns a valid context"""
        ctx = MagicMock(spec=GovernanceContext)
        ctx.correlation_id = "test-correlation-001"
        ctx.context_id = "test-context-001"
        ctx.actor_id = "test-actor"
        ctx.execution_mode = "STRICT"
        ctx.is_active = True
        return ctx
    
    app.dependency_overrides[require_governance_context] = mock_require_governance_context
    
    # CRITICAL: Override TrustedHostMiddleware for tests
    # Remove all TrustedHostMiddleware instances from the app
    original_middleware = app.user_middleware[:]
    app.user_middleware = [
        m for m in app.user_middleware
        if not isinstance(m, TrustedHostMiddleware)
    ]
    
    # Create test client
    yield TestClient(app, raise_server_exceptions=False)
    
    # Restore original middleware and overrides
    app.user_middleware = original_middleware
    app.dependency_overrides.clear()
```

**تاثیر**: باید ۲۵ تست را پاس کند

---

### اصلاح ۲: تست همزمانی در test_governance_hardening_sprint.py

**فایل**: `tests/governance/test_governance_hardening_sprint.py`
**تست**: `test_task6_100_concurrent_no_token_leakage`

**تغییرات مورد نیاز**:

```python
# در کلاس TestTask6And7ConcurrencyAndTokenIsolation
class TestTask6And7ConcurrencyAndTokenIsolation(unittest.TestCase):
    # ... کدهای موجود ...
    
    def test_task6_100_concurrent_no_token_leakage(self):
        """
        P0 CRITICAL: 100 concurrent reasoning requests must NOT share mutation tokens.
        Each request must have its own isolation boundary.
        """
        # CRITICAL: Establish governance context for the entire test
        from mahoun.core.governance.governance_context import GovernanceContextManager
        
        async def run_concurrent_requests():
            # این تست نیازمند context است
            async with GovernanceContextManager.active_context(
                correlation_id="test-concurrent-001",
                actor_id="test-actor",
                execution_mode="STRICT"
            ):
                # کد اصلی تست را اینجا قرار دهید
                # ...
                pass
        
        # اجرا کردن
        asyncio.run(run_concurrent_requests())
```

**تاثیر**: باید ۱ تست را پاس کند

---

### اصلاح ۳: ثبت marks سفارشی pytest

**مشکل**: هشدارهای "Unknown pytest.mark.p0" در تمام تست‌ها

**راه‌حل**: اضافه کردن علامت‌ها به pyproject.toml

**فایل**: `pyproject.toml`

```toml
[tool.pytest.ini_options]
markers = [
    "p0: P0 CRITICAL - Non-negotiable architectural invariants",
    "p1: P1 HIGH - Architectural hardening and governance",
    "p2: P2 MEDIUM - Integration and contract validation",
    "p3: P3 LOW - Unit tests and edge cases",
]
```

**تاثیر**: حذف هشدارها، اما تست‌ها را پاس/شکست نمی‌کند

---

### اصلاح ۴: بررسی سایر شکست‌ها

عدم دسترسی به لیست کامل شکست‌ها، ولی می‌توانیم دسته‌بندی کنیم:

#### زیرگروه ۴.۱: test_security_bypass_prevention.py (۶ شکست)
**علت احتمالی**: تست‌ها انتظار دارند بدون governance context اجرا شوند
**راه‌حل**: برقراری context یا mock کردن آن

#### زیرگروه ۴.۲: test_architecture_guard.py (۱۰ شکست)
**علت احتمالی**: مشکلات در validation معماری
**راه‌حل**: بررسی و اصلاح تست‌ها

#### زیرگروه ۴.۳: test_schema_governance.py (۱ شکست)
**علت**: Schema governance enforcement
**راه‌حل**: بررسی و اصلاح تست

#### زیرگروه ۴.۴: test_unified_governance_controller.py (۱ شکست)
**علت**: متغیر query_type
**راه‌حل**: بررسی و اصلاح تست

#### زیرگروه ۴.۵: test_hardened_infrastructure.py (۱۲ خطا)
**علت**: TypeError: can only concatenate list (not "tuple") to list
**راه‌حل**: بررسی کد و اصلاح type errors

---

## لیست کامل فایل‌هایی که نیاز به اصلاح دارند

### اولویت ۱ (فوری - باید انجام شود)
1. `tests/governance/test_api_integration.py` - اصلاح فیکسچر client

### اولویت ۲ (بالا - باید انجام شود)
2. `tests/governance/test_governance_hardening_sprint.py` - اصلاح تست همزمانی
3. `tests/governance/test_security_bypass_prevention.py` - بررسی ۶ شکست
4. `tests/governance/test_architecture_guard.py` - بررسی ۱۰ شکست

### اولویت ۳ (متوسط - پس از اولویت ۱ و ۲)
5. `tests/governance/test_schema_governance.py` - بررسی ۱ شکست
6. `tests/governance/test_unified_governance_controller.py` - بررسی ۱ شکست
7. `tests/governance/test_hardened_infrastructure.py` - بررسی ۱۲ خطا

### اولویت ۴ (پایین - بهینه‌سازی)
8. `pyproject.toml` - ثبت marks سفارشی pytest

---

## تخمین زمان

| اولویت | تعداد تست‌ها | زمان تخمینی | نتیجه مورد انتظار |
|--------|---------------|--------------|---------------------|
| ۱ | ۲۵ | ۳۰ دقیقه | ✅ پاس شدن ۲۵ تست |
| ۲ | ۱۷ | ۲ ساعت | ✅ پاس شدن ۱۷ تست |
| ۳ | ۱۴ | ۳ ساعت | ✅ پاس شدن ۱۴ تست |
| ۴ | - | ۳۰ دقیقه | ⚠️ حذف هشدارها |
| **جمع** | **۵۶** | **۶ ساعت** | **رسیدن به ۱۰۰%** |

---

## دستورالعمل اجرا

### مرحله ۱: اعمال اصلاحات فوری (۳۰ دقیقه)
```bash
# اصلاح فیکسچر client
edit tests/governance/test_api_integration.py

# اجرا کردن تست‌های API integration
pytest tests/governance/test_api_integration.py -v
```

### مرحله ۲: اصلاحات اولویت بالا (۲ ساعت)
```bash
# اصلاح تست همزمانی
edit tests/governance/test_governance_hardening_sprint.py

# بررسی و اصلاح security bypass tests
edit tests/governance/test_security_bypass_prevention.py

# بررسی و اصلاح architecture guard tests  
edit tests/governance/test_architecture_guard.py

# اجرا کردن تمام تست‌های governance
pytest tests/governance/test_api_integration.py tests/governance/test_governance_hardening_sprint.py tests/governance/test_security_bypass_prevention.py tests/governance/test_architecture_guard.py -v
```

### مرحله ۳: اصلاحات اولویت متوسط (۳ ساعت)
```bash
# بررسی و اصلاح سایر فایل‌ها
edit tests/governance/test_schema_governance.py
edit tests/governance/test_unified_governance_controller.py
edit tests/governance/test_hardened_infrastructure.py

# اجرا کردن کامل Gate 9
bash ci/first_step/gate_9_governance.sh
```

### مرحله ۴: بهینه‌سازی (۳۰ دقیقه)
```bash
# ثبت marks سفارشی
edit pyproject.toml

# اجرا کردن نهایی
bash ci/first_step/gate_9_governance.sh
```

---

## معیارهای موفقیت

✅ **Gate 9 پاس شود**: تمام ۴۹۵ تست پاس شوند
✅ **هیچ شکست جدیدی**: تغییرات ما شکست جدید ایجاد نکنند
✅ **حفظ معماری**: تمام قواعد معماری (RULE 1-15) حفظ شوند
✅ **تست‌های سخت**: تمام تست‌ها با سختی کامل اجرا شوند

---

## نکات مهم

1. **هر تغییر را پس از اعمال تست کنید**:
   ```bash
   pytest <file> -v
   ```

2. **از hardcoding خودداری کنید**: راه‌حل‌ها باید عمومی باشند

3. **مستندات را به‌روزرسانی کنید**: پس از هر تغییر مهم، مستندات را آپدیت کنید

4. **composition را حفظ کنید**: تغییرات باید minimal و focused باشند

5. ** pacientes**: بعضی از شکست‌ها ممکن است نیاز به بررسی عمیق‌تر داشته باشند

---

## نتیجه

با اعمال این اصلاحات، **Gate 9 باید به صورت کامل پاس شود**. در حال حاضر، مشکلات اصلی:
- زیرساخت تست (TrustedHostMiddleware)
- عدم برقراری governance context در بعضی تست‌ها

این مشکلات **قابل حل** هستند و نیاز به حدود **۶ ساعت** زمان دارند.
