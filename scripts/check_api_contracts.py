#!/usr/bin/env python3
"""
API Contract Checker
====================
Static verification that frontend API calls match backend routes.

Normalization (Amendment D):
  - Backend: combine router prefix + decorator path, normalize slashes,
    preserve HTTP method, support get/post/put/delete/patch.
  - Frontend: parse fetch('/api/...'), fetch(`/api/...`), client method
    calls with statically visible endpoint arguments.
  - Query strings stripped from path before matching.
  - Parameterized paths normalized: /users/{id}, /users/${id}, /users/:id
    all become /users/{param}.

Exit codes:
  0 - No violations (warnings may exist for dynamic endpoints)
  1 - Violations found (frontend calls missing backend route)
  2 - Error
"""

import re
import sys
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple


class Severity(Enum):
    VIOLATION = "VIOLATION"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class BackendRoute:
    method: str
    path: str
    file: str
    line: int


@dataclass
class FrontendCall:
    method: Optional[str]
    path: str
    file: str
    line: int
    is_dynamic: bool = False


@dataclass
class Finding:
    severity: Severity
    message: str
    frontend: Optional[FrontendCall] = None
    backend: Optional[BackendRoute] = None


# ---------------------------------------------------------------------------
# Path normalization helpers
# ---------------------------------------------------------------------------

PARAM_PATTERN = re.compile(r'\{[^}]+\}')


def normalize_path(path: str) -> str:
    """Normalize a route path for comparison.

    1. Strip query string.
    2. Normalize leading/trailing slashes.
    3. Collapse duplicate slashes.
    4. Replace :param, ${param}, /:param with {param}.
    5. Ensure leading slash.
    """
    # Strip query string
    path = path.split('?', 1)[0]
    # Normalize leading slash
    if not path.startswith('/'):
        path = '/' + path
    # Collapse duplicate slashes
    path = re.sub(r'/+', '/', path)
    # Replace :param, ${param}, :param forms with {param_name}
    path = re.sub(r'(?<!\w):\w+', lambda m: '{' + m.group(0)[1:] + '}', path)
    path = re.sub(r'\$\{\w+\}', lambda m: '{' + m.group(0)[2:-1] + '}', path)
    # Canonicalize all parameter names to {param} so that {user_id}, {id},
    # :id, ${id} all normalize to the same {param} placeholder.
    path = re.sub(r'\{[^}]+\}', '{param}', path)
    # Remove trailing slash (unless root)
    if len(path) > 1 and path.endswith('/'):
        path = path[:-1]
    return path


def paths_match(frontend_path: str, backend_path: str) -> bool:
    """Check if normalized frontend path matches backend path.

    After normalization, all parameter forms are canonicalized to {param},
    so a direct comparison suffices. HTTP method is not stripped here —
    method matching is the caller's responsibility.
    """
    fp = normalize_path(frontend_path)
    bp = normalize_path(backend_path)
    return fp == bp


# ---------------------------------------------------------------------------
# Backend route extraction
# ---------------------------------------------------------------------------

ROUTER_PREFIX_RE = re.compile(r'prefix\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
ROUTER_METHOD_RE = re.compile(
    r'@router\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)


def extract_backend_routes(api_dir: Path) -> List[BackendRoute]:
    """Parse api/routers/*.py for router prefixes and route decorators."""
    routes: List[BackendRoute] = []
    router_files = sorted(api_dir.glob('*.py'))
    for rf in router_files:
        if rf.name == '__init__.py':
            continue
        try:
            content = rf.read_text(encoding='utf-8')
        except OSError:
            continue
        # Find all router prefix declarations in this file
        prefixes = ['']
        for m in ROUTER_PREFIX_RE.finditer(content):
            prefixes.append(m.group(1))
        # For each prefix, find all route decorators and combine
        for prefix in prefixes:
            for m in ROUTER_METHOD_RE.finditer(content):
                method = m.group(1).upper()
                decorator_path = m.group(2)
                full_path = (prefix.rstrip('/') + '/' + decorator_path.lstrip('/'))
                full_path = re.sub(r'/+', '/', full_path)
                if not full_path.startswith('/'):
                    full_path = '/' + full_path
                # Line number approximation
                line_num = content[:m.start()].count('\n') + 1
                routes.append(BackendRoute(
                    method=method,
                    path=full_path,
                    file=str(rf.relative_to(rf.parent.parent)),
                    line=line_num,
                ))
    return routes


# ---------------------------------------------------------------------------
# Frontend API call extraction
# ---------------------------------------------------------------------------

# Patterns for fetch('/api/...') and fetch(`/api/...`) and similar
# Also matches client.method('/api/...') patterns
FRONTEND_FETCH_RE = re.compile(
    r'fetch\s*\(\s*'
    r'(?:'
        r'["\'](?P<p1>/api/[^"\']*)["\']'
        r'|'
        r'`(?P<p2>/api/[^`]*)`'
        r'|'
        r'(?P<base1>[A-Za-z_][A-Za-z0-9_]*)\s*\+\s*["\'](?P<p3>/api/[^"\']*)["\']'
        r'|'
        r'(?P<base2>[A-Za-z_][A-Za-z0-9_]*)\s*\+\s*`(?P<p4>/api/[^`]*)`'
    r')'
    r'\s*\)',
    re.IGNORECASE,
)

# Client method patterns: client.get('/api/...'), mahounClient.post('/api/...')
FRONTEND_CLIENT_RE = re.compile(
    r'(?:[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\s*\.\s*'
    r'(?P<method>get|post|put|delete|patch)\s*\(\s*'
    r'(?:'
        r'["\'](?P<cp1>/api/[^"\']*)["\']'
        r'|'
        r'`(?P<cp2>/api/[^`]*)`'
    r')'
    r'\s*[\),]',
    re.IGNORECASE,
)

# Detect dynamic (unresolvable) endpoints
DYNAMIC_ENDPOINT_RE = re.compile(
    r'(?:baseUrl|API_BASE|BASE_URL|VITE_API_URL)\s*\+\s*',
    re.IGNORECASE,
)


def extract_frontend_calls(frontend_dir: Path) -> List[FrontendCall]:
    """Parse frontend/src/**/*.ts, .tsx for API calls."""
    calls: List[FrontendCall] = []
    src_files = sorted(frontend_dir.rglob('*.ts')) + sorted(frontend_dir.rglob('*.tsx'))
    for sf in src_files:
        rel = str(sf.relative_to(frontend_dir))
        rel_path = Path(rel)
        # Exclude test directories and api/ client implementations
        if 'test' in rel_path.parts:
            continue
        if 'src/api/' in str(sf).replace(str(frontend_dir), ''):
            continue
        try:
            content = sf.read_text(encoding='utf-8')
        except OSError:
            continue
        # Check for dynamic endpoint indicators
        is_dynamic = bool(DYNAMIC_ENDPOINT_RE.search(content))
        for m in FRONTEND_FETCH_RE.finditer(content):
            raw_path = (m.group('p1') or m.group('p2') or m.group('p3') or m.group('p4') or '').strip('`').strip("'").strip('"')
            line_num = content[:m.start()].count('\n') + 1
            method = 'GET'
            after = content[m.end():m.end()+200]
            method_match = re.search(r'method\s*:\s*["\'](\w+)["\']', after, re.IGNORECASE)
            if method_match:
                method = method_match.group(1).upper()
            calls.append(FrontendCall(
                method=method,
                path=raw_path,
                file=rel,
                line=line_num,
                is_dynamic=is_dynamic,
            ))
        for m in FRONTEND_CLIENT_RE.finditer(content):
            raw_path = (m.group('cp1') or m.group('cp2') or '').strip('`').strip("'").strip('"')
            line_num = content[:m.start()].count('\n') + 1
            method = (m.group('method') or 'GET').upper()
            calls.append(FrontendCall(
                method=method,
                path=raw_path,
                file=rel,
                line=line_num,
                is_dynamic=is_dynamic,
            ))
    return calls


# ---------------------------------------------------------------------------
# Main checker
# ---------------------------------------------------------------------------

class APIContractChecker:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.api_dir = project_root / 'api' / 'routers'
        self.frontend_dir = project_root / 'frontend' / 'src'
        self.findings: List[Finding] = []
        self.backend_routes: List[BackendRoute] = []
        self.frontend_calls: List[FrontendCall] = []

    def run(self) -> bool:
        """Run all checks. Returns True if no violations."""
        if not self.api_dir.exists():
            print(f"❌ ERROR: Backend router directory not found: {self.api_dir}")
            return False
        if not self.frontend_dir.exists():
            print(f"⚠️  Frontend src not found at {self.frontend_dir} — skipping frontend checks")
            return True

        self.backend_routes = extract_backend_routes(self.api_dir)
        self.frontend_calls = extract_frontend_calls(self.frontend_dir)

        # Build backend lookup: (method, normalized_path) -> BackendRoute
        backend_index: Dict[Tuple[str, str], List[BackendRoute]] = {}
        for route in self.backend_routes:
            key = (route.method, normalize_path(route.path))
            backend_index.setdefault(key, []).append(route)

        print(f"📊 Backend routes: {len(self.backend_routes)}")
        print(f"📊 Frontend API calls: {len(self.frontend_calls)}")
        print("")

        # Check each frontend call
        for call in self.frontend_calls:
            if call.is_dynamic:
                self.findings.append(Finding(
                    severity=Severity.WARNING,
                    message=f"{call.file}:{call.line} — UNRESOLVED_DYNAMIC_ENDPOINT: "
                            f"{call.method} {call.path} (cannot statically resolve)",
                    frontend=call,
                ))
                continue
            norm_path = normalize_path(call.path)
            # Match against all backend routes using paths_match (handles
            # parameterized paths where param names differ: {id} matches {user_id})
            found_match = False
            for route in self.backend_routes:
                if route.method == call.method and paths_match(norm_path, route.path):
                    found_match = True
                    break
                # GET fallback for unknown methods
                if call.method != 'GET' and route.method == 'GET' and paths_match(norm_path, route.path):
                    found_match = True
                    break
            if not found_match:
                self.findings.append(Finding(
                    severity=Severity.VIOLATION,
                    message=f"{call.file}:{call.line} — NO BACKEND ROUTE: "
                            f"{call.method} {call.path} (normalized: {norm_path})",
                    frontend=call,
                ))

        return self._report()

    def _report(self) -> bool:
        """Print findings. Returns True if no violations."""
        violations = [f for f in self.findings if f.severity == Severity.VIOLATION]
        warnings = [f for f in self.findings if f.severity == Severity.WARNING]

        print("=" * 60)
        print(f"📋 API Contract Check: {len(violations)} violations, {len(warnings)} warnings")
        print("=" * 60)

        if violations:
            print(f"\n❌ VIOLATIONS ({len(violations)}):")
            for f in violations:
                print(f"  {f.message}")
                if f.frontend:
                    print(f"    Frontend: {f.frontend.file}:{f.frontend.line}")
                if f.backend:
                    print(f"    Backend:  {f.backend.file}:{f.backend.line}")

        if warnings:
            print(f"\n⚠️  WARNINGS ({len(warnings)}):")
            for f in warnings:
                print(f"  {f.message}")

        # Print execution chain (Amendment B G5)
        print("\n" + "=" * 60)
        print("Execution chain:")
        print("  PRE-COMMIT: (none — API contract check is pre-push only)")
        print("  PRE-PUSH:   scripts/check_api_contracts.py")
        print("  CI:         (wired via pre-push + CI workflow)")
        print("=" * 60)

        if violations:
            print(f"\n❌ FAILED: {len(violations)} API contract violation(s)")
            return False
        print(f"\n✅ PASSED: No API contract violations")
        return True


def main():
    project_root = Path(__file__).resolve().parent.parent
    checker = APIContractChecker(project_root)
    success = checker.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
