#!/usr/bin/env python3
import os, ast, sys
from pathlib import Path
from collections import defaultdict

REPO = Path(__file__).parent.resolve()
EXCLUDE = {'.git', '__pycache__', 'venv', '.venv', 'node_modules', 'dist', 'build', 
           '.pytest_cache', '.mypy_cache', '.archived_backups', '.kilo', '.kiro', '.crush', '.bob'}

class Auditor:
    def __init__(self):
        self.files = set()
        self.imports = defaultdict(set)
        self.reverse = defaultdict(set)
        self.entries = set()
        self.reach = set()
    
    def scan(self):
        for root, dirs, files in os.walk(REPO):
            dirs[:] = [d for d in dirs if d not in EXCLUDE]
            for f in files:
                if f.endswith('.py'):
                    p = Path(root, f).relative_to(REPO)
                    if not any(e in p.parts for e in EXCLUDE):
                        self.files.add(p)
    
    def entries_scan(self):
        for f in self.files:
            if f.name == '__init__.py' or str(f).startswith('scripts/') or str(f) in ['api/main.py', 'setup.py']:
                self.entries.add(f)
            if str(f).startswith('tests/'):
                self.entries.add(f)
                
    def parse(self, f):
        imps = set()
        try:
            tree = ast.parse((REPO/f).read_text(errors='ignore'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names: imps.add(a.name.split('.')[0])
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imps.add(node.module.split('.')[0])
        except: pass
        return imps
    
    def resolve(self, imp, from_file):
        res = set()
        if imp.startswith('.'):
            base = from_file.parent
            for _ in range(len(imp) - len(imp.lstrip('.')) - 1): base = base.parent
            mod = imp.lstrip('.')
            tgt = base / mod.replace('.', '/') if mod else base
            init = tgt / '__init__.py'
            if (REPO/init).exists(): res.add(init)
            py = tgt.parent / f"{tgt.name}.py"
            if (REPO/py).exists(): res.add(py)
        else:
            parts = imp.split('.')
            for i in range(len(parts), 0, -1):
                pot = Path(*parts[:i])
                init = pot / '__init__.py'
                if (REPO/init).exists(): res.add(init)
                py = pot.parent / f"{pot.name}.py"
                if (REPO/py).exists(): res.add(py)
        return res & self.files
    
    def build_graph(self):
        for f in self.files:
            for imp in self.parse(f):
                for r in self.resolve(imp, f):
                    self.imports[f].add(r)
                    self.reverse[r].add(f)
    
    def traverse(self):
        stack, seen = list(self.entries), set()
        while stack:
            cur = stack.pop()
            if cur in seen: continue
            seen.add(cur)
            self.reach.add(cur)
            for imp in self.imports[cur]:
                if imp not in seen: stack.append(imp)
    
    def report(self):
        zero = {f for f in self.files if f not in self.reverse and f not in self.entries}
        nontest = {f for f in self.files if not str(f).startswith('tests/')}
        reach_nontest = {f for f in self.reach if f in nontest}
        unreach = nontest - reach_nontest
        
        print("\n" + "="*80)
        print("### [ORPHAN MODULES - ZERO REFERENCES]\n")
        for f in sorted(zero): print(f"- {f}")
        print("\n### [UNREACHABLE IMPORTS - OUTSIDE DEPLOYMENT GRAPH]\n")
        for f in sorted(unreach): print(f"- {f}")
        print("="*80 + "\n")

if __name__ == '__main__':
    a = Auditor()
    print("Scanning..."); a.scan(); print(f"Files: {len(a.files)}")
    print("Entry points..."); a.entries_scan(); print(f"Entries: {len(a.entries)}")
    print("Graph..."); a.build_graph()
    print("Traverse..."); a.traverse(); print(f"Reachable: {len(a.reach)}")
    a.report()
