"""mahoun.infrastructure.audit — concrete audit-sink adapters (Tier 2)."""
from mahoun.infrastructure.audit.filesink import (
    FilesystemAuditSink,
    NullAuditSink,
)

__all__ = ["FilesystemAuditSink", "NullAuditSink"]
