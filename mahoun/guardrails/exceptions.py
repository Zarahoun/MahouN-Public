"""
Runtime Guard Exceptions
========================
Exceptions raised when invariants are violated.
"""
from typing import Dict


class InvariantViolation(Exception):
    """
    Raised when a runtime invariant is violated.
    
    Attributes:
        invariant_name: Name of the violated invariant
        details: Dictionary with additional context
    """
    
    def __init__(self, invariant_name: str, details: dict | None = None):
        self.invariant_name = invariant_name
        self.details = details or {}
        message = f"Invariant violation: {invariant_name}"
        if details:
            message += f" | Details: {details}"
        super().__init__(message)
    
    def __repr__(self) -> str:
        return f"InvariantViolation(name={self.invariant_name!r}, details={self.details!r})"

