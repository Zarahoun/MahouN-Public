# Wiring Fixes - مشکلات Wiring و راه حل‌ها

## 🔍 مشکلات پیدا شده

### ✅ 1. Import اشتباه در enhanced_chunker.py
**مشکل:**
```python
from .pipeline import Chunk  # ❌ Chunk در pipeline.py نیست!
```

**راه حل:**
```python
from pipelines.smart_chunker import Chunk  # ✅
```

**وضعیت:** ✅ برطرف شد

---

### ⚠️ 2. API Router از EnhancedIngestionPipeline استفاده نمی‌کند
**مشکل:**
- `api/routers/ingest.py` فقط از `IngestionPipeline` استفاده می‌کند (خط 38)
- Enhanced version استفاده نمی‌شود

**گزینه‌های راه حل:**

#### گزینه A: Environment Variable برای انتخاب
```python
use_enhanced = os.getenv("USE_ENHANCED_INGESTION", "false").lower() == "true"
if use_enhanced:
    from pipelines.ingestion.enhanced_pipeline import EnhancedIngestionPipeline
    _ingestion_pipeline = EnhancedIngestionPipeline()
else:
    from pipelines.ingestion.pipeline import IngestionPipeline
    _ingestion_pipeline = IngestionPipeline()
```

#### گزینه B: Feature Flag در Config
استفاده از runtime config برای enable/disable

#### گزینه C: Separate Endpoint
ساخت endpoint جداگانه `/ingest/enhanced`

**توصیه:** گزینه A (Environment Variable) - ساده‌ترین راه

---

### ✅ 3. Import های دیگر
**بررسی شده:**
- ✅ `enhanced_pipeline.py` - import های Chunk درست است
- ✅ `llm_enhanced_parser.py` - import json موجود است
- ✅ `__init__.py` - exports درست هستند

---

## 📋 Checklist Wiring

- [x] Chunk import در enhanced_chunker.py اصلاح شد
- [x] Import های enhanced_pipeline.py درست هستند
- [ ] API Router برای استفاده از Enhanced pipeline به‌روزرسانی شود
- [x] Export ها در __init__.py درست هستند
- [x] No circular imports
- [x] No linter errors

---

## 🎯 اقدامات لازم

1. ✅ Fix import در enhanced_chunker.py
2. ⚠️ Update API router (اختیاری - بستگی به نیاز دارد)
3. ✅ Verify all imports

