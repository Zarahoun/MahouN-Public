"""Regression tests for canonical governance-context construction."""

from pathlib import Path

from mahoun.core.governance.governance_context import GovernanceContextManager


ROOT = Path(__file__).parents[2]


def test_startup_monitoring_context_uses_canonical_factory():
    context = GovernanceContextManager.create_context(
        correlation_id="startup-test",
        execution_mode="STRICT",
        actor_id="system",
    )

    assert context.correlation_id == "startup-test"
    assert context.actor_id == "system"
    assert context.execution_mode == "STRICT"
    assert context.governance_scope_injected is True


def test_runtime_application_surfaces_do_not_construct_context_directly():
    for relative_path in ("api/main.py", "api/routers/monitoring.py"):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "GovernanceContext(" not in source
        assert "GovernanceContextManager.create_context(" in source


def test_startup_uses_current_orchestrator_factory_keyword():
    source = (ROOT / "api/main.py").read_text(encoding="utf-8")

    assert "enable_auto_scale=False" in source
    assert "enable_auto_scaling=" not in source
