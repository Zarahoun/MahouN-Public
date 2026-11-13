"""
AI Runtime Adapters

This module contains concrete implementations of the AIRuntimeProtocol
for different model formats and runtimes.

Currently supported:
- GGUFAdapter: Local GGUF model execution via llama-cpp-python

All adapters must implement AIRuntimeProtocol and maintain
contract stability with G-0 frozen interfaces.
"""

from .gguf_adapter import GGUFAdapter, GGUFAdapterConfig

__all__ = [
    "GGUFAdapter",
    "GGUFAdapterConfig"
]
