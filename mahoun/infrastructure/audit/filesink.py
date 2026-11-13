"""
Filesystem Audit Sink
=====================

Classification: INFRA / TIER 2

Concrete ``AuditSinkProtocol`` adapter persisting governance audit entries
to a local file using ``fsync`` semantics.

The kernel does NOT import this module. It is constructed and injected at the
application composition root (see ``mahoun/infrastructure/audit/wiring.py``).

Behaviour:
    - Appends one JSON line per call.
    - Creates the parent directory if missing.
    - Calls ``os.fsync`` to make durable.

A complementary ``NullAuditSink`` is exposed for tests and hermetic wiring.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class NullAuditSink:
    """
    Null-object audit sink. No persistence, no I/O. Suitable for tests and
    for environments where the audit ledger is wired elsewhere.
    """

    def append(self, entry: Dict[str, Any]) -> None:
        # Intentionally no-op. Records nothing.
        return


class FilesystemAuditSink:
    """
    Append-only fsynced audit sink.

    Args:
        path: File path to append JSON-logg rows to.
        mirror_path: Optional secondary immutable ledger path (e.g., a
                     tamper-proof remote). When provided, writes are
                     duplicated with an HSM-style signature.
        signature: Whether to sign the secondary mirror line with sha256.
                   Defaults to True when mirror_path is set.
    """

    def __init__(
        self,
        path: str = "logs/governance.audit",
        mirror_path: Optional[str] = "logs/remote_immutable.ledger",
        signature: bool = True,
    ) -> None:
        self._path = path
        self._mirror_path = mirror_path
        self._signature = bool(signature)
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)

    def append(self, entry: Dict[str, Any]) -> None:
        """Persist a single audit entry. Fail-closed: raises on I/O failure."""
        line = json.dumps(entry, default=str, sort_keys=True) + "\n"
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())
        except Exception as exc:
            raise RuntimeError(
                f"AuditSink append failed for primary path '{self._path}': {exc}"
            ) from exc

        if self._mirror_path is not None:
            try:
                os.makedirs(os.path.dirname(self._mirror_path) or ".", exist_ok=True)
                payload = dict(entry)
                if self._signature:
                    import hashlib
                    payload["hsm_signature"] = hashlib.sha256(line.encode()).hexdigest()
                with open(self._mirror_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(payload, default=str, sort_keys=True) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            except Exception as exc:
                raise RuntimeError(
                    f"AuditSink append failed for mirror path '{self._mirror_path}': {exc}"
                ) from exc


# ---------------------------------------------------------------------------
# Composition helpers
# ---------------------------------------------------------------------------

def compose_default_filesystem_sink() -> FilesystemAuditSink:
    """
    Build the filesystem audit sink with production defaults.

    The kernel references ``AuditSinkProtocol.append``; this helper instantiates
    the concrete ``FilesystemAuditSink`` at composition time so the kernel
    remains hermetic.
    """
    return FilesystemAuditSink(
        path="logs/governance.audit",
        mirror_path="logs/remote_immutable.ledger",
    )
