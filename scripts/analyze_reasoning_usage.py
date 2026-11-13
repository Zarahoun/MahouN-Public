#!/usr/bin/env python3
"""
تحلیل استفاده از ماژول‌های reasoning در کدبیس MAHOUN
================================================================================
هدف: شناسایی ماژول‌هایی که واقعا استفاده می‌شن vs orphan modules
"""

import os
import re
from pathlib import Path
from collections import defaultdict

# مسیر root
REPO_ROOT = Path("/home/haji/Desktop/KingMahouN")
REASONING_DIR = REPO_ROOT / "mahoun" / "reasoning"

def find_all_python_files():
    """پیدا کردن همه فایل‌های پایتون (به جز __pycache__)"""
    files = []
    for root, dirs, filenames in os.walk(REPO_ROOT):
        # Skip __pycache__ and .git
        dirs[:] = [d for d in dirs if d not in ['__pycache__', '.git', 'venv', 'node_modules']]
        for filename in filenames:
            if filename.endswith('.py'):
                files.append(Path(root) / filename)
    return files

def get_reasoning_modules():
    """لیست همه ماژول‌های reasoning"""
    modules = []
    for file in REASONING_DIR.glob("*.py"):
        if file.name != "__init__.py":
            modules.append(file.stem)
    return sorted(modules)

def search_imports_for_module(module_name, all_files):
    """جستجوی import ها برای یک ماژول خاص"""
    patterns = [
        rf'from\s+mahoun\.reasoning\.{module_name}\s+import',
        rf'import\s+mahoun\.reasoning\.{module_name}',
        rf'from\s+mahoun\.reasoning\s+import.*{module_name}',
    ]
    
    importing_files = []
    
    for file in all_files:
        # Skip the module itself
        if file.stem == module_name and "reasoning" in str(file):
            continue
            
        try:
            content = file.read_text(encoding='utf-8', errors='ignore')
            for pattern in patterns:
                if re.search(pattern, content):
                    importing_files.append(str(file.relative_to(REPO_ROOT)))
                    break
        except Exception:
            pass
    
    return importing_files

def main():
    print("🔍 در حال اسکن کل کدبیس برای یافتن استفاده از ماژول‌های reasoning...")
    print("=" * 80)
    
    # پیدا کردن همه فایل‌ها
    all_files = find_all_python_files()
    print(f"📁 تعداد فایل‌های پایتون: {len(all_files)}")
    
    # پیدا کردن ماژول‌های reasoning
    modules = get_reasoning_modules()
    print(f"📦 تعداد ماژول‌های reasoning: {len(modules)}")
    print("=" * 80)
    
    # آنالیز هر ماژول
    used_modules = {}
    orphan_modules = []
    
    for module in modules:
        importing_files = search_imports_for_module(module, all_files)
        if importing_files:
            used_modules[module] = importing_files
        else:
            orphan_modules.append(module)
    
    # گزارش نهایی
    print(f"\n{'=' * 80}")
    print(f"📊 گزارش کامل استفاده از ماژول‌های reasoning")
    print(f"{'=' * 80}")
    print(f"✅ ماژول‌های استفاده شده: {len(used_modules)}")
    print(f"❌ ماژول‌های استفاده نشده (ORPHAN): {len(orphan_modules)}")
    print(f"📦 مجموع: {len(modules)}")
    print(f"{'=' * 80}")
    
    # نمایش ماژول‌های استفاده شده
    if used_modules:
        print(f"\n✅ ماژول‌های فعال و محل استفاده:")
        print("=" * 80)
        for module, files in sorted(used_modules.items(), key=lambda x: len(x[1]), reverse=True):
            print(f"\n📌 {module}.py")
            print(f"استفاده شده در {len(files)} فایل:")
            for f in files[:5]:  # نمایش 5 مورد اول
                print(f"• {f}")
            if len(files) > 5:
                print(f"... و {len(files) - 5} فایل دیگر")
    
    # نمایش ماژول‌های orphan
    if orphan_modules:
        print(f"\n{'=' * 80}")
        print(f"❌ ماژول‌های ORPHAN (هیچ جا استفاده نشده‌اند):")
        print("=" * 80)
        for module in sorted(orphan_modules):
            file_path = REASONING_DIR / f"{module}.py"
            size = file_path.stat().st_size / 1024  # KB
            print(f"• {module}.py ({size:.1f} KB) 💀")
    
    # آمار نهایی
    print(f"\n{'=' * 80}")
    print(f"📈 آمار نهایی:")
    print(f"• استفاده شده: {len(used_modules)}/{len(modules)} ({len(used_modules)/len(modules)*100:.1f}%)")
    print(f"• Orphan: {len(orphan_modules)}/{len(modules)} ({len(orphan_modules)/len(modules)*100:.1f}%)")
    print("=" * 80)

if __name__ == "__main__":
    main()
