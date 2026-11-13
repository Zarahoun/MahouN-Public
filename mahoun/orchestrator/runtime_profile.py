"""
MAHOUN Runtime Profile
======================
Descriptive runtime profile for transparency and logging.

This module provides a READ-ONLY view of the current operational profile.
It does NOT control behavior - it simply reports what mode the system is in.

The profile matches the current demo behavior and is used for:
- Logging/transparency in demo output
- Test validation
- Documentation

DO NOT use this for control flow decisions. Use core.runtime_config for that.
"""

from dataclasses import dataclass
from enum import Enum


class MAHOUNMode(str, Enum):
    """MAHOUN operational modes"""
    DESKTOP_MINIMAL = "desktop_minimal"
    PRODUCTION = "production"


class EmbeddingMode(str, Enum):
    """Embedding service modes"""
    DUMMY = "dummy"
    SENTENCE_TRANSFORMERS = "sentence_transformers"
    ULTRA = "ultra"


class ReasoningMode(str, Enum):
    """Reasoning service modes"""
    DISABLED = "disabled"
    FAST = "fast"
    STRICT = "strict"


class RAGMode(str, Enum):
    """RAG operational modes"""
    TEXT_ONLY = "text_only"
    GRAPH_ONLY = "graph_only"
    HYBRID_GRAPH_FIRST = "hybrid_graph_first"


@dataclass
class RuntimeProfile:
    """
    Descriptive runtime profile (read-only, for reporting).
    
    This reflects the CURRENT operational state of the demo,
    not what we want or what's configured.
    """
    mode: MAHOUNMode = MAHOUNMode.DESKTOP_MINIMAL
    embeddings: EmbeddingMode = EmbeddingMode.DUMMY
    reasoning: ReasoningMode = ReasoningMode.DISABLED
    rag_mode: RAGMode = RAGMode.TEXT_ONLY


# Global instance - matches current demo behavior in desktop_minimal environment
# (no torch, no sentence-transformers, simple_memory vector store)
MAHOUN_PROFILE = RuntimeProfile()


def get_current_profile() -> str:
    """
    Get current runtime profile name.
    
    Returns the profile string used for bootstrap configuration.
    Maps environment variables to profile names.
    
    Returns:
        str: Profile name ("BASE", "STANDARD", "ULTRA", etc.)
    """
    import os
    
    # Check environment variable for explicit profile
    profile = os.getenv("MAHOUN_PROFILE", "BASE").upper()
    
    # Validate profile
    valid_profiles = ["BASE", "STANDARD", "ULTRA", "MINIMAL"]
    if profile not in valid_profiles:
        profile = "BASE"  # Default fallback
    
    return profile
