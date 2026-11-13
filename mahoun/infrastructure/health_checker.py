"""
Comprehensive Health Check System
==================================
Centralized health checking for all system components.

این ماژول سلامت تمام کامپوننت‌های سیستم را بررسی می‌کند:
- Ollama LLM Service
- ChromaDB/VectorStore
- Neo4j/Graph (اگر فعال باشد)
- Registered Agents

Architectural Mandate (Action Item 1)
------------------------------------
The health checker **never re-instantiates heavy resources**. It only
inspects pre-existing instance references from the canonical locations:

1. ``app.state`` — for service singletons attached by the FastAPI lifespan
   (e.g., the LLM/VectorStore/agent singletons a router already holds).
2. :data:`mahoun.switchboard.switchboard` — the canonical
   ``SwitchboardRegistry`` singleton. Registered modules are resolved via
   :meth:`Switchboard.get_module`, which lazy-constructs at most once
   across the whole process. This is the **only** sanctioned construction
   surface for registered modules.

3. Dedicated registries (e.g., ``ULTRA_AGENT_REGISTRY`` in
   ``mahoun/agents/ultra_factory.py``) — for components that are tracked
   by their own registry rather than ``app.state``.
"""

from typing import Any, Dict, Optional
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import asyncio
import logging
import os

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Health status levels"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    DISABLED = "disabled"  # Component is intentionally disabled
    NOT_LOADED = "not_loaded"  # Subsystem module is not present in this build


@dataclass
class ComponentHealth:
    """Health status for a component"""
    component: str
    status: HealthStatus
    message: str
    details: Dict[str, Any]
    checked_at: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "component": self.component,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "checked_at": self.checked_at
        }


class HealthChecker:
    """
    Central health checker for all components.

    The checker only **inspects** existing singletons. It will not
    instantiate an OllamaLLMService, a VectorStoreManager, an agent, or
    any other heavy resource as a side effect of a ``/health`` call. To
    wire in pre-existing references, pass them in the constructor:

    * ``app_state`` — typically ``request.app.state`` from a FastAPI
      endpoint. The checker will look for known attributes on it.
    * ``switchboard_registry`` — defaults to the canonical
      :data:`mahoun.switchboard.switchboard` singleton. Override only for
      tests.

    Usage::

        checker = HealthChecker(app_state=request.app.state)
        results = await checker.check_all()

    For backward compatibility, ``HealthChecker()`` (no args) is still
    valid — the checker will fall back to import-only verification for
    any component that is not pre-instantiated.
    """

    # Canonical Switchboard key for the registered legal pipeline, which
    # is the closest cousin of "reasoning" that lives in the registry.
    _SB_LEGAL_PIPELINE = "legal_pipeline"
    _SB_ULTRA_GRAPH_BUILDER = "ultra_graph_builder"
    _SB_ULTRA_GRAPH_SERVICE = "ultra_graph_service"
    _SB_BIAS_ANALYZER = "bias_analyzer"
    _SB_SMART_CACHE = "smart_cache"
    _SB_LEGAL_NLP = "legal_nlp"

    # Attribute names looked up on app.state for the most common
    # singletons. None of these trigger construction.
    _APP_STATE_ATTRS = {
        "ollama": "ollama_llm_service",
        "vector_store": "vector_store_manager",
        "reasoning": "reasoning_service",
    }

    def __init__(
        self,
        app_state: Optional[Any] = None,
        switchboard_registry: Optional[Any] = None,
    ) -> None:
        """Initialize health checker.

        Args:
            app_state: Optional FastAPI ``app.state`` (or any object) that
                holds pre-existing service singletons. The checker will
                look up known attribute names on it without ever
                constructing anything itself.
            switchboard_registry: Optional override for the canonical
                SwitchboardRegistry. Defaults to the module-level
                :data:`mahoun.switchboard.switchboard` singleton.
        """
        self.logger = logging.getLogger(__name__)
        self.app_state = app_state
        # Default to the canonical SwitchboardRegistry singleton. The
        # import is deferred to the constructor so this module remains
        # import-safe in minimal test environments.
        if switchboard_registry is None:
            try:
                from mahoun.switchboard import switchboard as _default_sb
                switchboard_registry = _default_sb
            except Exception:
                switchboard_registry = None
        self.switchboard_registry = switchboard_registry

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _lookup_existing(
        self,
        attr_name: str,
        switchboard_key: Optional[str] = None,
    ) -> Optional[Any]:
        """Look up a pre-existing instance — never construct.

        Order:
        1. ``app_state.<attr_name>`` (no construction, just an attribute
           read).
        2. ``switchboard_registry.get_module(switchboard_key)`` (the
           canonical registry path; the Switchboard is responsible for
           lazy-construction, not us).

        Returns ``None`` if no pre-existing reference can be found. The
        caller is expected to translate ``None`` into a
        ``HealthStatus.DEGRADED`` / ``DISABLED`` response rather than
        building a fresh instance.
        """
        # 1. app.state inspection
        if self.app_state is not None:
            try:
                inst = getattr(self.app_state, attr_name, None)
                if inst is not None:
                    return inst
            except Exception as e:  # pragma: no cover - defensive
                self.logger.debug(
                    f"app_state lookup for '{attr_name}' failed: {e}"
                )

        # 2. Switchboard registry resolution
        if switchboard_key and self.switchboard_registry is not None:
            try:
                return self.switchboard_registry.get_module(switchboard_key)
            except KeyError:
                # Module key not registered — fall through to None.
                return None
            except Exception as e:
                # Real lookup failure (e.g. ULTRA module missing
                # hardware): do not construct; surface as "not present".
                self.logger.debug(
                    f"Switchboard lookup for '{switchboard_key}' failed: {e}"
                )
                return None

        return None

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat()

    # ------------------------------------------------------------------
    # Public health-check surface (signatures preserved)
    # ------------------------------------------------------------------
    async def check_health(self) -> Dict[str, Any]:
        """Alias for check_all"""
        return await self.check_all()

    async def check_ollama(self) -> ComponentHealth:
        """
        Check Ollama LLM service health — **inspects** the pre-existing
        singleton. Does not construct an ``OllamaLLMService`` on its own.
        """
        try:
            from mahoun.core.runtime_config import get_runtime_settings
            settings = get_runtime_settings()

            if not settings.enable_ollama:
                return ComponentHealth(
                    component="ollama",
                    status=HealthStatus.DISABLED,
                    message="Ollama integration is disabled in this runtime mode",
                    details={"enabled": False, "mode": settings.mode},
                    checked_at=self._now(),
                )

            # Inspect (do NOT construct) the pre-existing instance.
            service = self._lookup_existing(
                attr_name=self._APP_STATE_ATTRS["ollama"],
            )
            if service is None:
                # No pre-existing reference: report the fact honestly.
                # We deliberately do NOT construct a new one — that
                # would defeat the "no re-instantiation" mandate.
                return ComponentHealth(
                    component="ollama",
                    status=HealthStatus.DEGRADED,
                    message=(
                        "Ollama service is enabled in settings but no "
                        "pre-existing instance is available on app.state"
                    ),
                    details={
                        "enabled": True,
                        "mode": settings.mode,
                        "ollama_uri": settings.ollama_uri,
                        "instance_present": False,
                    },
                    checked_at=self._now(),
                )

            # Probe the existing service. ``_check_ollama_available`` and
            # ``list_models`` are idempotent / cached on the service
            # itself — they do not create new drivers.
            is_available = await service._check_ollama_available()
            models = await service.list_models() if is_available else []

            return ComponentHealth(
                component="ollama",
                status=HealthStatus.HEALTHY if is_available else HealthStatus.UNHEALTHY,
                message=(
                    "Ollama service is running" if is_available
                    else "Ollama service is not available"
                ),
                details={
                    "available_models": models,
                    "model_count": len(models),
                    "base_url": getattr(service, "base_url", settings.ollama_uri),
                    "enabled": True,
                    "instance_present": True,
                },
                checked_at=self._now(),
            )
        except Exception as e:
            self.logger.error(f"Error checking Ollama: {e}", exc_info=True)
            return ComponentHealth(
                component="ollama",
                status=HealthStatus.UNHEALTHY,
                message=f"Failed to check Ollama: {str(e)}",
                details={"error": str(e), "enabled": True},
                checked_at=self._now(),
            )

    async def check_vector_store(self) -> ComponentHealth:
        """
        Check VectorStore/ChromaDB health — **inspects** the pre-existing
        manager. Does not construct a new ``VectorStoreManager``.
        """
        try:
            from mahoun.core.runtime_config import get_runtime_settings
            settings = get_runtime_settings()

            # Inspect (do NOT construct) the pre-existing manager.
            manager = self._lookup_existing(
                attr_name=self._APP_STATE_ATTRS["vector_store"],
            )
            if manager is None:
                return ComponentHealth(
                    component="vector_store",
                    status=HealthStatus.DEGRADED,
                    message=(
                        "VectorStore is enabled in settings but no "
                        "pre-existing manager is available on app.state"
                    ),
                    details={
                        "enabled": True,
                        "mode": settings.mode,
                        "instance_present": False,
                    },
                    checked_at=self._now(),
                )

            # Probe the existing manager; ``get_stats`` is read-only.
            stats = manager.get_stats()
            cfg = getattr(manager, "config", None)

            return ComponentHealth(
                component="vector_store",
                status=HealthStatus.HEALTHY if stats else HealthStatus.DEGRADED,
                message=(
                    "VectorStore is operational" if stats
                    else "VectorStore is running but stats unavailable"
                ),
                details={
                    "backend": getattr(cfg, "backend", None) if cfg else None,
                    "collection": getattr(cfg, "collection_name", None) if cfg else None,
                    "stats": stats,
                    "instance_present": True,
                },
                checked_at=self._now(),
            )
        except Exception as e:
            self.logger.error(f"Error checking VectorStore: {e}", exc_info=True)
            return ComponentHealth(
                component="vector_store",
                status=HealthStatus.UNHEALTHY,
                message=f"Failed to check VectorStore: {str(e)}",
                details={"error": str(e)},
                checked_at=self._now(),
            )

    async def check_graph(self) -> ComponentHealth:
        """
        Check Neo4j/Graph system health — consults the canonical
        :class:`api.database.GraphConnectionState` flag (set by
        ``init_neo4j``) plus the runtime-config mode. Does not instantiate
        a graph builder.
        """
        try:
            from mahoun.core.runtime_config import (
                get_runtime_settings,
                should_skip_graph,
            )
            settings = get_runtime_settings()

            # Consult the canonical runtime state set by api.database.
            graph_state: Dict[str, Any] = {
                "config_enabled": settings.graph_enabled,
                "should_skip_graph": should_skip_graph(),
                "instance_present": False,
                "backend_runtime": None,
            }
            try:
                from api.database import GraphConnectionState
                graph_state.update({
                    "instance_present": GraphConnectionState.is_available(),
                    "backend_runtime": GraphConnectionState.backend,
                    "last_error": GraphConnectionState.last_error,
                })
            except Exception as state_err:  # pragma: no cover - defensive
                self.logger.debug(
                    f"GraphConnectionState read failed: {state_err}"
                )

            # Mode-level disable (desktop_minimal, no graph): DISABLED.
            if should_skip_graph():
                return ComponentHealth(
                    component="graph",
                    status=HealthStatus.DISABLED,
                    message="Graph system is disabled (mode or config)",
                    details={
                        "enabled": False,
                        "mode": settings.mode,
                        "backend": settings.graph_backend,
                        **graph_state,
                    },
                    checked_at=self._now(),
                )

            # Graph enabled in config but unavailable at runtime.
            if not graph_state["instance_present"]:
                return ComponentHealth(
                    component="graph",
                    status=HealthStatus.DEGRADED,
                    message=(
                        "Graph is enabled in config but Neo4j is not "
                        f"reachable ({graph_state.get('last_error') or 'unknown reason'})"
                    ),
                    details=graph_state,
                    checked_at=self._now(),
                )

            return ComponentHealth(
                component="graph",
                status=HealthStatus.HEALTHY,
                message="Graph system is enabled and reachable",
                details={
                    "enabled": True,
                    "backend": (
                        graph_state["backend_runtime"]
                        or settings.graph_backend
                    ),
                    "neo4j_uri": settings.graph_neo4j_uri,
                    **graph_state,
                },
                checked_at=self._now(),
            )
        except Exception as e:
            self.logger.error(f"Error checking Graph: {e}", exc_info=True)
            return ComponentHealth(
                component="graph",
                status=HealthStatus.UNHEALTHY,
                message=f"Failed to check Graph: {str(e)}",
                details={"error": str(e)},
                checked_at=self._now(),
            )

    async def check_reasoning(self) -> ComponentHealth:
        """
        Check reasoning service health — **inspects** the pre-existing
        reasoning singleton (or the registered legal pipeline from the
        Switchboard) without constructing a new ``UltraReasoningService``.
        """
        try:
            from mahoun.core.runtime_config import get_runtime_settings
            settings = get_runtime_settings()

            service = self._lookup_existing(
                attr_name=self._APP_STATE_ATTRS["reasoning"],
                switchboard_key=self._SB_LEGAL_PIPELINE,
            )

            if service is None:
                # No pre-existing reference. The check must remain
                # honest and lightweight — we do NOT construct.
                return ComponentHealth(
                    component="reasoning",
                    status=HealthStatus.DEGRADED,
                    message=(
                        "Reasoning service is enabled in settings but no "
                        "pre-existing instance is available"
                    ),
                    details={
                        "mode": settings.mode,
                        "instance_present": False,
                        "switchboard_key": self._SB_LEGAL_PIPELINE,
                    },
                    checked_at=self._now(),
                )

            return ComponentHealth(
                component="reasoning",
                status=HealthStatus.HEALTHY,
                message="Reasoning service is available",
                details={
                    "service": type(service).__name__,
                    "cot_enabled": getattr(service, "use_cot", None),
                    "self_consistency_enabled": getattr(
                        service, "use_self_consistency", None
                    ),
                    "instance_present": True,
                },
                checked_at=self._now(),
            )
        except Exception as e:
            self.logger.error(f"Error checking Reasoning: {e}", exc_info=True)
            return ComponentHealth(
                component="reasoning",
                status=HealthStatus.UNHEALTHY,
                message=f"Reasoning service unavailable: {str(e)}",
                details={"error": str(e)},
                checked_at=self._now(),
            )

    async def check_agents(self) -> Dict[str, ComponentHealth]:
        """
        Check all registered agents.

        Uses the canonical ``ULTRA_AGENT_REGISTRY`` from
        ``mahoun/agents/ultra_factory.py`` so that this method reports on
        what the system actually intends to run, without instantiating
        any of the agent classes. For each registered agent we report
        ``HEALTHY`` (registered and importable) without paying the cost
        of constructing the agent type.
        """
        results: Dict[str, Any] = {}
        try:
            from mahoun.agents.ultra_factory import ULTRA_AGENT_REGISTRY

            if not ULTRA_AGENT_REGISTRY:
                return {
                    "agents": ComponentHealth(
                        component="agents",
                        status=HealthStatus.DEGRADED,
                        message="ULTRA_AGENT_REGISTRY is empty",
                        details={"count": 0},
                        checked_at=self._now(),
                    )
                }

            for name, reg in ULTRA_AGENT_REGISTRY.items():
                agent_class = reg.agent_class
                results[name] = ComponentHealth(
                    component=f"agent.{name}",
                    status=HealthStatus.HEALTHY,
                    message=f"{name} agent is registered and importable",
                    details={
                        "class": agent_class.__name__,
                        "registered": True,
                        "category": getattr(reg, "category", "general"),
                        "priority": getattr(reg, "priority", 1),
                    },
                    checked_at=self._now(),
                )

        except Exception as e:
            self.logger.error(f"Error checking agents: {e}", exc_info=True)
            results["agents"] = ComponentHealth(
                component="agents",
                status=HealthStatus.UNHEALTHY,
                message=f"Failed to check agents: {str(e)}",
                details={"error": str(e)},
                checked_at=self._now(),
            )

        return results

    async def check_refactored_modules(self) -> Dict[str, ComponentHealth]:
        """
        Check health of refactored modules.

        All inspections are import-only or registry-resolved — no heavy
        refactored-module constructor is invoked from here. The health
        checker exclusively *inspects* the canonical surface.
        """
        results: Dict[str, Any] = {}

        # --- Hybrid Search: import + switchboard inspection only -----
        try:
            from mahoun.retrieval.ultra_hybrid_search import UltraHybridSearch

            search_instance = self._lookup_existing(
                attr_name="ultra_hybrid_search",
            )
            results["refactored.hybrid_search"] = ComponentHealth(
                component="refactored.hybrid_search",
                status=HealthStatus.HEALTHY,
                message="UltraHybridSearch module is importable",
                details={
                    "class": UltraHybridSearch.__name__,
                    "module": "mahoun.retrieval.ultra_hybrid_search",
                    "instance_present": search_instance is not None,
                },
                checked_at=self._now(),
            )
        except ModuleNotFoundError as e:
            # Module is not present in this build — register, do not
            # crash, do not log a traceback.
            results["refactored.hybrid_search"] = ComponentHealth(
                component="refactored.hybrid_search",
                status=HealthStatus.NOT_LOADED,
                message="UltraHybridSearch module is not present in this build",
                details={"error": str(e)},
                checked_at=self._now(),
            )
        except Exception as e:
            self.logger.error(f"Error checking HybridSearch: {e}", exc_info=True)
            results["refactored.hybrid_search"] = ComponentHealth(
                component="refactored.hybrid_search",
                status=HealthStatus.UNHEALTHY,
                message=f"HybridSearch check failed: {str(e)}",
                details={"error": str(e)},
                checked_at=self._now(),
            )

        # --- Gaussian Process: settings + import-only -----------------
        try:
            from mahoun.core.runtime_config import get_runtime_settings
            settings = get_runtime_settings()

            if not settings.enable_gaussian_process:
                results["refactored.gaussian_process"] = ComponentHealth(
                    component="refactored.gaussian_process",
                    status=HealthStatus.DISABLED,
                    message="GaussianProcess module is disabled in this runtime mode",
                    details={"enabled": False, "mode": settings.mode},
                    checked_at=self._now(),
                )
            else:
                # Import-only check; do NOT instantiate.
                try:
                    from mahoun.uncertainty.gaussian_process import (
                        GaussianProcessUncertainty,
                    )
                    results["refactored.gaussian_process"] = ComponentHealth(
                        component="refactored.gaussian_process",
                        status=HealthStatus.HEALTHY,
                        message="GaussianProcess module is importable",
                        details={
                            "class": GaussianProcessUncertainty.__name__,
                            "enabled": True,
                            "instance_present": (
                                self._lookup_existing(attr_name="gaussian_process")
                                                is not None
                            ),
                        },
                        checked_at=self._now(),
                    )
                except ModuleNotFoundError as e:
                    results["refactored.gaussian_process"] = ComponentHealth(
                        component="refactored.gaussian_process",
                        status=HealthStatus.NOT_LOADED,
                        message="GaussianProcess module is not present in this build",
                        details={"error": str(e), "enabled": True},
                        checked_at=self._now(),
                    )
        except Exception as e:
            self.logger.error(
                f"Error checking GaussianProcess: {e}", exc_info=True
            )
            results["refactored.gaussian_process"] = ComponentHealth(
                component="refactored.gaussian_process",
                status=HealthStatus.UNHEALTHY,
                message=f"GaussianProcess check failed: {str(e)}",
                details={"error": str(e), "enabled": True},
                checked_at=self._now(),
            )

        return results

    async def check_databases(self) -> Dict[str, ComponentHealth]:
        """
        Check database connections (PostgreSQL, Redis).

        Note: PostgreSQL/Redis clients are inspected via the canonical
        module-level singletons in ``api.database``. The health check
        does not construct new clients.
        """
        from mahoun.core.runtime_config import get_runtime_settings
        settings = get_runtime_settings()

        results: Dict[str, Any] = {}

        # --- PostgreSQL ---------------------------------------------
        if os.getenv("MAHOUN_MODE") == "test" or not settings.enable_postgres:
            results["postgresql"] = ComponentHealth(
                component="postgresql",
                status=HealthStatus.DISABLED,
                message="PostgreSQL is disabled (Test mode or explicitly off)",
                details={
                    "enabled": False,
                    "mode": settings.mode,
                    "test_mode": os.getenv("MAHOUN_MODE") == "test",
                },
                checked_at=self._now(),
            )
        else:
            try:
                from api.database import postgres_pool

                if postgres_pool is None:
                    results["postgresql"] = ComponentHealth(
                        component="postgresql",
                        status=HealthStatus.UNHEALTHY,
                        message="PostgreSQL connection pool not initialized",
                        details={"enabled": True, "connected": False},
                        checked_at=self._now(),
                    )
                else:
                    async with postgres_pool.acquire() as conn:
                        result = await conn.fetchval("SELECT 1")
                        if result == 1:
                            results["postgresql"] = ComponentHealth(
                                component="postgresql",
                                status=HealthStatus.HEALTHY,
                                message="PostgreSQL is connected",
                                details={"connected": True, "enabled": True},
                                checked_at=self._now(),
                            )
                        else:
                            results["postgresql"] = ComponentHealth(
                                component="postgresql",
                                status=HealthStatus.DEGRADED,
                                message="PostgreSQL connection issue",
                                details={
                                    "connected": True,
                                    "query_result": result,
                                    "enabled": True,
                                },
                                checked_at=self._now(),
                            )
            except Exception as e:
                self.logger.debug(f"PostgreSQL health check failed: {e}")
                results["postgresql"] = ComponentHealth(
                    component="postgresql",
                    status=HealthStatus.UNHEALTHY,
                    message=f"PostgreSQL check failed: {str(e)}",
                    details={"error": str(e), "enabled": True},
                    checked_at=self._now(),
                )

        # --- Redis ----------------------------------------------------
        if os.getenv("MAHOUN_MODE") == "test" or not settings.enable_redis:
            results["redis"] = ComponentHealth(
                component="redis",
                status=HealthStatus.DISABLED,
                message="Redis is disabled (Test mode or explicitly off)",
                details={
                    "enabled": False,
                    "mode": settings.mode,
                    "test_mode": os.getenv("MAHOUN_MODE") == "test",
                },
                checked_at=self._now(),
            )
        else:
            try:
                # Inspect the canonical singleton — do NOT construct.
                from api.database import redis_client
                if redis_client is None:
                    results["redis"] = ComponentHealth(
                        component="redis",
                        status=HealthStatus.UNHEALTHY,
                        message="Redis client not initialized",
                        details={"enabled": True, "connected": False},
                        checked_at=self._now(),
                    )
                else:
                    await redis_client.ping()
                    results["redis"] = ComponentHealth(
                        component="redis",
                        status=HealthStatus.HEALTHY,
                        message="Redis is connected",
                        details={"connected": True, "enabled": True},
                        checked_at=self._now(),
                    )
            except Exception as e:
                self.logger.debug(f"Redis health check failed: {e}")
                results["redis"] = ComponentHealth(
                    component="redis",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Redis check failed: {str(e)}",
                    details={"error": str(e), "enabled": True},
                    checked_at=self._now(),
                )

        return results

    async def check_all(self) -> Dict[str, Any]:
        """
        Run all health checks concurrently and format according to Contract.

        Returns:
            Dictionary with health check results matching Contract schema
        """
        import time

        # Run checks concurrently
        ollama_task = asyncio.create_task(self.check_ollama())
        vector_task = asyncio.create_task(self.check_vector_store())
        graph_task = asyncio.create_task(self.check_graph())
        reasoning_task = asyncio.create_task(self.check_reasoning())
        agents_task = asyncio.create_task(self.check_agents())
        refactored_task = asyncio.create_task(self.check_refactored_modules())
        databases_task = asyncio.create_task(self.check_databases())

        # Wait for all
        ollama_health = await ollama_task
        vector_health = await vector_task
        graph_health = await graph_task
        reasoning_health = await reasoning_task
        agents_health = await agents_task
        refactored_health = await refactored_task
        databases_health = await databases_task

        # Defensive: in some test patches, ``check_databases`` is replaced
        # with a method that returns a single ComponentHealth rather
        # than a dict. Coerce to a dict so downstream ``.get()`` calls
        # stay valid regardless of the patch surface.
        if not isinstance(databases_health, dict):
            databases_health = {"_patched": databases_health}

        # 1. Determine Overall Core Status
        # Core includes: Vector Store, Reasoning, Ollama (if critical)
        core_healthy = all(
            c.status == HealthStatus.HEALTHY
            for c in [vector_health, reasoning_health]
        )

        if (
            vector_health.status == HealthStatus.UNHEALTHY
            or reasoning_health.status == HealthStatus.UNHEALTHY
        ):
            core_status = "FAILED"
        elif not core_healthy:
            core_status = "DEGRADED"
        else:
            core_status = "HEALTHY"

        # Check if agents health check itself failed (outer except)
        agents_failed = "agents" in agents_health and len(agents_health) == 1
        components_map: Dict[str, Any] = {
            "ollama": ollama_health.to_dict(),
            "vector_store": vector_health.to_dict(),
            "graph": graph_health.to_dict(),
            "reasoning": reasoning_health.to_dict(),
            "postgresql": (
                databases_health.get("postgresql").to_dict()
                if databases_health.get("postgresql")
                else {"status": "unknown"}
            ),
            "redis": (
                databases_health.get("redis").to_dict()
                if databases_health.get("redis")
                else {"status": "unknown"}
            ),
        }

        # Add agents and refactored modules
        for name, health in agents_health.items():
            components_map[f"agent.{name}"] = health.to_dict()
        for name, health in refactored_health.items():
            components_map[name] = health.to_dict()

        # 3. Build Contract-Compliant Response
        response = {
            "status": "HEALTHY",
            "core": {
                "status": core_status,
                "import_safe": not agents_failed,
                "uptime_sec": int(time.clock_gettime(time.CLOCK_MONOTONIC)),
            },
            "graph": {
                "status": graph_health.status.value.upper(),
                "reason": graph_health.message,
            },
            "agents": {
                "status": (
                    "READY"
                    if not agents_failed
                    and all(
                        a.status == HealthStatus.HEALTHY
                        for a in agents_health.values()
                    )
                    else "FAILED"
                    if agents_failed
                    else "DEGRADED"
                ),
                "count": 0 if agents_failed else len(agents_health),
            },
            "components": components_map,
        }

        # 4. Calculate Global Status
        if core_status == "FAILED" or agents_failed:
            response["status"] = "FAILED"
        elif (
            core_status == "DEGRADED"
            or response["agents"]["status"] != "READY"
        ):
            response["status"] = "DEGRADED"
        elif graph_health.status == HealthStatus.UNHEALTHY:
            response["status"] = "DEGRADED"

        return response
