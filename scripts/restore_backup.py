#!/usr/bin/env python3
"""Restore core/ from backup."""
import shutil
from pathlib import Path

backup = Path("backups/core_backup_20260217_031924")
target = Path("mahoun/core")

if not backup.exists():
    print(f"❌ Backup not found: {backup}")
    exit(1)

print(f"🔄 Restoring from {backup}...")

if target.exists():
    print("   Removing current core/...")
    shutil.rmtree(target)

shutil.copytree(backup, target)
print(f"✅ Restored from {backup}")
