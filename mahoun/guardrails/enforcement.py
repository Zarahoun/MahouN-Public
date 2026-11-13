"""
Guard Enforcement System
=========================

Provides non-bypassable guard enforcement for production.

Architecture:
- Environment-aware (dev/staging/prod)
- Mandatory in production
- Configurable in development
- Logged in staging

Guarantees:
- Production guards CANNOT be disabled
- Development flexibility preserved
- Staging provides warnings
- All violations logged
"""

import logging
import os
from collections.abc import Callable
from enum import Enum
from functools import wraps
from typing import Any

log = logging.getLogger(__name__)


class EnforcementLevel(Enum):
    """
    Guard enforcement levels

    DEVELOPMENT: Guards can be disabled (GUARD_MODE=OFF)
    STAGING: Guards warn but don't block
    PRODUCTION: Guards ALWAYS enforced (non-bypassable)
    """

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


def get_enforcement_level() -> EnforcementLevel:
    """
    Get current enforcement level from canonical environment.
    """
    from mahoun.core.environment import get_current_environment

    env_context = get_current_environment()

    if env_context.is_production():
        return EnforcementLevel.PRODUCTION
    elif env_context.is_staging():
        return EnforcementLevel.STAGING
    else:
        return EnforcementLevel.DEVELOPMENT


def get_guard_mode() -> str:
    """
    Get guard mode from environment

    Returns:
        Guard mode: OFF|WARN|STRICT|AUDIT

    Environment variable:
        GUARD_MODE: OFF|WARN|STRICT|AUDIT

    Default: STRICT

    Note:
        In production, this is IGNORED (always STRICT)
    """
    return os.getenv("GUARD_MODE", "STRICT").upper()


def enforce_guard(guard_func: Callable, *args: Any, **kwargs: Any) -> None:
    """
    Enforce guard with environment-aware behavior

    Args:
        guard_func: Guard function to execute
        *args: Arguments to pass to guard
        **kwargs: Keyword arguments to pass to guard

    Behavior:
    - PRODUCTION: Always execute (non-bypassable)
    - STAGING: Execute and log failures
    - DEVELOPMENT: Respect GUARD_MODE setting

    Raises:
        Exception: If guard fails (in STRICT mode or PRODUCTION)
    """
    level = get_enforcement_level()

    if level == EnforcementLevel.PRODUCTION:
        # PRODUCTION: MANDATORY ENFORCEMENT
        # Guards CANNOT be disabled
        try:
            guard_func(*args, **kwargs)
        except Exception as e:
            log.error(f"PRODUCTION GUARD FAILURE: {guard_func.__name__} - {e}", exc_info=True)
            raise

    elif level == EnforcementLevel.STAGING:
        # STAGING: WARN ON FAILURE
        # Execute but don't block on failure
        try:
            guard_func(*args, **kwargs)
        except Exception as e:
            log.warning(f"STAGING GUARD FAILURE: {guard_func.__name__} - {e}", exc_info=True)
            # Don't raise in staging

    else:
        # DEVELOPMENT: CONFIGURABLE
        # Respect GUARD_MODE setting
        guard_mode = get_guard_mode()

        if guard_mode == "OFF":
            # Guards disabled
            return

        elif guard_mode == "WARN":
            # Execute but only warn on failure
            try:
                guard_func(*args, **kwargs)
            except Exception as e:
                log.warning(f"GUARD WARNING: {guard_func.__name__} - {e}")

        elif guard_mode == "AUDIT":
            # Execute and log all checks
            try:
                guard_func(*args, **kwargs)
                log.info(f"GUARD PASSED: {guard_func.__name__}")
            except Exception as e:
                log.error(f"GUARD FAILED: {guard_func.__name__} - {e}", exc_info=True)
                raise

        else:
            # STRICT (default)
            # Execute and raise on failure
            try:
                guard_func(*args, **kwargs)
            except Exception as e:
                log.error(f"GUARD FAILED: {guard_func.__name__} - {e}", exc_info=True)
                raise


def guard(func: Callable) -> Callable:
    """
    Decorator to mark function as guard

    Usage:
        @guard
        def G1_EvidenceStepHasEvidence(step, index):
            if not step.evidence:
                raise ValueError(f"Step {index} has no evidence")

    Effect:
        Wraps function with enforce_guard() logic
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        enforce_guard(func, *args, **kwargs)

    return wrapper


def require_production() -> None:
    """
    Require production environment

    Raises:
        RuntimeError: If not in production

    Use case:
        Operations that should ONLY run in production
    """
    level = get_enforcement_level()
    if level != EnforcementLevel.PRODUCTION:
        raise RuntimeError(f"This operation requires PRODUCTION environment. Current: {level.value}")


def forbid_production() -> None:
    """
    Forbid production environment

    Raises:
        RuntimeError: If in production

    Use case:
        Dangerous operations that should NEVER run in production
    """
    level = get_enforcement_level()
    if level == EnforcementLevel.PRODUCTION:
        raise RuntimeError("This operation is FORBIDDEN in PRODUCTION environment")


class GuardContext:
    """
    Context manager for temporary guard mode override

    Usage:
        with GuardContext(mode="WARN"):
            # Guards will warn but not fail
            process_data()

    Note:
        Does NOT work in production (guards always enforced)
    """

    def __init__(self, mode: str):
        """
        Initialize context

        Args:
            mode: Guard mode (OFF|WARN|STRICT|AUDIT)
        """
        self.mode = mode.upper()
        self.original_mode: str | None = None
        self.level = get_enforcement_level()

    def __enter__(self) -> "GuardContext":
        """Enter context"""
        if self.level == EnforcementLevel.PRODUCTION:
            log.warning("GuardContext has no effect in PRODUCTION (guards always enforced)")
            return self

        # Save original mode
        self.original_mode = os.getenv("GUARD_MODE")

        # Set new mode
        os.environ["GUARD_MODE"] = self.mode
        log.debug(f"Guard mode temporarily set to {self.mode}")

        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context"""
        if self.level == EnforcementLevel.PRODUCTION:
            return

        # Restore original mode
        if self.original_mode is not None:
            os.environ["GUARD_MODE"] = self.original_mode
        else:
            os.environ.pop("GUARD_MODE", None)

        log.debug("Guard mode restored")


# Example usage
if __name__ == "__main__":
    from mahoun.core.environment import reset_environment, temporary_environment

    print("🛡️  Guard Enforcement System Test")
    print("=" * 60)

    # Test guard decorator
    @guard
    def test_guard(value: int):
        if value < 0:
            raise ValueError("Value must be non-negative")

    # Test in development
    reset_environment()
    with temporary_environment("development"):
        os.environ["GUARD_MODE"] = "STRICT"
        print(f"Current enforcement level: {get_enforcement_level().value}")
        print(f"Current guard mode: {get_guard_mode()}")

        try:
            test_guard(10)
            print("✓ Guard passed with valid value")
        except ValueError:
            print("✗ Guard failed unexpectedly")

        try:
            test_guard(-5)
            print("✗ Guard should have failed")
        except ValueError:
            print("✓ Guard correctly failed with invalid value")

        # Test with WARN mode
        os.environ["GUARD_MODE"] = "WARN"
        try:
            test_guard(-5)
            print("✓ Guard warned but didn't block (WARN mode)")
        except ValueError:
            print("✗ Guard blocked in WARN mode")

        # Test context manager
        os.environ["GUARD_MODE"] = "STRICT"
        with GuardContext(mode="OFF"):
            try:
                test_guard(-5)
                print("✓ Guard disabled in context (OFF mode)")
            except ValueError:
                print("✗ Guard still active in OFF context")

    # Test production enforcement
    reset_environment()
    with temporary_environment("production"):
        os.environ["GUARD_MODE"] = "OFF"  # Should be ignored
        print(f"Current enforcement level: {get_enforcement_level().value}")

        try:
            test_guard(-5)
            print("✗ Guard should be enforced in production")
        except ValueError:
            print("✓ Guard enforced in production (GUARD_MODE=OFF ignored)")
