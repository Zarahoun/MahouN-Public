#!/usr/bin/env python3
"""
🛡️ MahouN Architecture Quarantine Manager
========================================

Provides a non-destructive, 100% reversible quarantine staging mechanism for
modules classified as DELETE_CANDIDATE by the Architecture Intelligence Suite.

Features:
- Stage: Moves target files to .quarantine/ storing original path & SHA256 checksum.
- Restore: Reverses quarantine, restoring files to exact original locations.
- List: Displays currently quarantined modules.
- Dry-run mode: Simulates staging/restoration without mutating the filesystem.
"""

import sys
import json
import shutil
import hashlib
import argparse
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime


class QuarantineManager:
    def __init__(self, repo_root: str):
        self.repo_root = Path(repo_root)
        self.quarantine_dir = self.repo_root / '.quarantine'
        self.manifest_file = self.quarantine_dir / 'quarantine_manifest.json'
        self.reports_dir = self.repo_root / 'architecture_reports'

    def _ensure_dirs(self):
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)

    def _load_manifest(self) -> Dict[str, Any]:
        if self.manifest_file.exists():
            try:
                with open(self.manifest_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {'quarantined_files': {}, 'created_at': datetime.now().isoformat()}

    def _save_manifest(self, manifest: Dict[str, Any]):
        self._ensure_dirs()
        with open(self.manifest_file, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

    def _calculate_checksum(self, file_path: Path) -> str:
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            hasher.update(f.read())
        return hasher.hexdigest()

    def get_delete_candidates(self) -> List[Dict[str, Any]]:
        orphan_file = self.reports_dir / 'Orphan_Candidates.json'
        if not orphan_file.exists():
            print(f"❌ Error: {orphan_file} not found. Run ultra_production_tracker.py first.")
            return []

        with open(orphan_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        delete_cand_modules = data.get('delete_candidates', [])
        details = data.get('details', {})

        results = []
        for mod in delete_cand_modules:
            mod_info = details.get(mod, {})
            rel_path = mod_info.get('path')
            if rel_path:
                results.append({
                    'module': mod,
                    'path': rel_path,
                    'confidence': mod_info.get('confidence', 0),
                    'reasons': mod_info.get('reasons', [])
                })
        return results

    def stage_quarantine(self, dry_run: bool = True) -> int:
        candidates = self.get_delete_candidates()
        print(f"🔍 Found {len(candidates)} multi-source confirmed delete candidates for quarantine review.")

        if not candidates:
            return 0

        manifest = self._load_manifest()
        staged_count = 0

        for cand in candidates:
            rel_path = cand['path']
            src_file = self.repo_root / rel_path

            if not src_file.exists():
                continue

            checksum = self._calculate_checksum(src_file)
            target_quarantine_path = self.quarantine_dir / rel_path

            print(f"  [STAGE] {rel_path} -> .quarantine/{rel_path}")

            if not dry_run:
                target_quarantine_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src_file), str(target_quarantine_path))

                manifest['quarantined_files'][rel_path] = {
                    'module': cand['module'],
                    'original_path': rel_path,
                    'quarantine_path': str(target_quarantine_path.relative_to(self.repo_root)),
                    'checksum': checksum,
                    'quarantined_at': datetime.now().isoformat(),
                    'confidence': cand['confidence'],
                    'reasons': cand['reasons']
                }
                staged_count += 1
            else:
                staged_count += 1

        if not dry_run and staged_count > 0:
            self._save_manifest(manifest)
            print(f"\n✅ Staged {staged_count} files into quarantine successfully.")
        elif dry_run:
            print(f"\n🔍 [DRY-RUN] Would stage {staged_count} files into quarantine. No files mutated.")

        return staged_count

    def restore_quarantine(self, dry_run: bool = True) -> int:
        manifest = self._load_manifest()
        quarantined = manifest.get('quarantined_files', {})

        if not quarantined:
            print("ℹ️ No quarantined files found in manifest to restore.")
            return 0

        print(f"🔄 Restoring {len(quarantined)} files from quarantine...")
        restored_count = 0
        to_remove = []

        for rel_path, info in quarantined.items():
            quarantine_file = self.repo_root / info['quarantine_path']
            dest_file = self.repo_root / rel_path

            if not quarantine_file.exists():
                print(f"  ⚠️ Warning: Quarantined file not found: {info['quarantine_path']}")
                continue

            print(f"  [RESTORE] {info['quarantine_path']} -> {rel_path}")

            if not dry_run:
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(quarantine_file), str(dest_file))
                to_remove.append(rel_path)
                restored_count += 1
            else:
                restored_count += 1

        if not dry_run:
            for r in to_remove:
                del manifest['quarantined_files'][r]
            self._save_manifest(manifest)
            print(f"\n✅ Restored {restored_count} files from quarantine successfully.")
        else:
            print(f"\n🔍 [DRY-RUN] Would restore {restored_count} files. No files mutated.")

        return restored_count

    def list_quarantine(self):
        manifest = self._load_manifest()
        quarantined = manifest.get('quarantined_files', {})

        print(f"📋 Currently Quarantined Files: {len(quarantined)}")
        print("=" * 60)
        for rel_path, info in quarantined.items():
            print(f"- {info['module']} ({rel_path})")
            print(f"  Date: {info['quarantined_at']} | Hash: {info['checksum'][:12]}")
        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Mahoun Architecture Quarantine Manager")
    parser.add_argument('--stage', action='store_true', help="Stage delete candidates into .quarantine/")
    parser.add_argument('--restore', action='store_true', help="Restore all quarantined files")
    parser.add_argument('--list', action='store_true', help="List quarantined files")
    parser.add_argument('--dry-run', action='store_true', help="Simulate operation without mutating files")

    args = parser.parse_args()
    repo_root = '/home/haji/Desktop/KingMahouN'

    mgr = QuarantineManager(repo_root)

    if args.list:
        mgr.list_quarantine()
    elif args.restore:
        mgr.restore_quarantine(dry_run=args.dry_run)
    elif args.stage:
        mgr.stage_quarantine(dry_run=args.dry_run)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
