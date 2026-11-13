import os
import logging
import importlib
from pathlib import Path
from typing import Any, Dict, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SwitchboardRegistry")


class Switchboard:
    def __init__(self):
        self._registry: Dict[str, Dict[str, Any]] = {}
        self.ultra_mode_enabled = os.getenv("ULTRA_MODE", "False").lower() in (
            "true",
            "1",
        )
        self.cpu_safe_profile = os.getenv(
            "MAHOUN_CPU_SAFE_PROFILE", "true"
        ).lower() in ("true", "1", "yes", "on")
        self.hardware_ready = self._validate_hardware()

    def _validate_hardware(self) -> bool:
        """Report accelerator availability without blocking graph execution.

        Graph parsing, Neo4j schema bootstrap, and semantic materialization are
        CPU-capable. GPU availability remains telemetry for model components,
        but it is not an architectural prerequisite for graph construction.
        """
        if not self.ultra_mode_enabled:
            return False
        try:
            import torch
            available = bool(torch.cuda.is_available())
            logger.info(
                "[Hardware Validation] CUDA %s; CPU graph execution remains enabled.",
                "detected" if available else "unavailable",
            )
            return available
        except ImportError:
            logger.info(
                "[Hardware Validation] PyTorch unavailable; CPU graph execution remains enabled."
            )
            return False

    def register(
        self,
        module_key: str,
        base_path: str,
        ultra_path: Optional[str] = None,
        cpu_safe: bool = False,
    ):
        """Register a module or class for lazy loading."""
        target_path = base_path
        mode_resolved = "BASE"

        ultra_allowed = (
            self.ultra_mode_enabled
            and ultra_path
            and (not self.cpu_safe_profile or self.hardware_ready or cpu_safe)
        )
        if ultra_allowed:
            target_path = ultra_path
            mode_resolved = "ULTRA"

        self._registry[module_key] = {
            "path": target_path,
            "base_path": base_path,
            "mode": mode_resolved,
            "cpu_safe": cpu_safe,
            "instance": None,
        }

        logger.info(
            f"🔰 [Switchboard] Registered '{module_key}' -> Mode: [{mode_resolved}]"
        )

    def get_module(self, module_key: str) -> Any:
        """Lazy load and return the module instance or class."""
        if module_key not in self._registry:
            raise KeyError(f"Module '{module_key}' is not mapped in the Switchboard.")

        info = self._registry[module_key]
        if info["instance"] is None:
            # First invocation: perform the import
            try:
                module_name, class_name = info["path"].rsplit(".", 1)
                module = importlib.import_module(module_name)
                cls = getattr(module, class_name)
                # Since signatures match, we return the class directly (or instance depending on design)
                # Let's return the class itself, so callers can instantiate if they need to,
                # or if it's a singleton, they can manage it.
                info["instance"] = cls()
                logger.info(f"[{info['mode']}] Lazy loaded {module_key} successfully.")
            except ImportError as e:
                # Fallback to Base mode is FORBIDDEN in Zero-Trust Hardening
                if info["mode"] == "ULTRA":
                    from mahoun.core.fortress_validator import SecurityBreachException, ViolationType, ViolationSeverity
                    logger.critical(
                        f"[GOVERNANCE FAILURE] Failed to load ULTRA module for '{module_key}': {e}. "
                        "Fallback to BASE is forbidden to maintain epistemic integrity."
                    )
                    raise SecurityBreachException(
                        message=f"Failed to load mandatory ULTRA module: {module_key}",
                        violation_type=ViolationType.SILENT_FAILURE,
                        severity=ViolationSeverity.CRITICAL,
                        forensic_context={"module_key": module_key, "error": str(e)}
                    ) from e
                else:
                    raise RuntimeError(
                        f"Failed to load BASE module {module_key}: {str(e)}"
                    )

            if module_key == "legal_pipeline" and info["mode"].startswith("BASE"):
                try:
                    from mahoun.core.protocols import LLMServiceProtocol
                except ImportError:
                    raise RuntimeError(
                        "Cannot load legal_pipeline in BASE mode: LLMServiceProtocol isn't satisfied."
                    )

        return info["instance"]

    def get_schema(self, schema_key: str) -> str:
        """Resolve database schema file paths based on running mode."""
        base_dir = "mahoun/graph/schema/"

        # Mapping base SQL schemas and Ultra Cypher schemas
        schema_map = {
            "ingestion": {"BASE": "sql/master_schema.sql", "ULTRA": "cypher/ultra_neo4j_schema.cypher"},
            "governance": {
                "BASE": "sql/master_schema.sql",
                "ULTRA": "cypher/ultra_neo4j_schema.cypher",
            },
        }

        if schema_key not in schema_map:
            raise KeyError(f"Schema '{schema_key}' not mapped.")

        mode = "ULTRA" if self.ultra_mode_enabled else "BASE"
        selected_file = schema_map[schema_key].get(mode, schema_map[schema_key]["BASE"])
        target_path = Path(__file__).resolve().parent / "graph" / "schema" / selected_file

        if not target_path.exists():
            logger.error(f"Database schema missing at {target_path}")
            raise FileNotFoundError(
                f"Strict Mode Error: Database schema missing at {target_path}"
            )

        logger.info(
            f"🔰 [Switchboard Schema] Resolved '{schema_key}' -> {target_path} [{mode}]"
        )
        return str(target_path)


# Singleton export
switchboard = Switchboard()


def bootstrap_switchboard():
    """Register all orphaned modules based on their phase priorities."""

    # Phase A: Logic & Hardening (Zero-Cost Rewiring) - Base Only
    switchboard.register(
        "legal_pipeline",
        base_path="mahoun.pipelines.ingestion.hardened_legal_pipeline.HardenedLegalPipeline",
    )
    switchboard.register(
        "bias_analyzer", base_path="mahoun.governance.bias_analysis.BiasAnalyzer"
    )
    switchboard.register(
        "smart_cache", base_path="mahoun.infrastructure.cache.smart_cache.SmartCache"
    )

    # Added for tests
    switchboard.register(
        "document_normalizer",
        base_path="mahoun.pipelines.ingestion.document_normalizer.DocumentNormalizer",
    )
    switchboard.register(
        "metadata_extractor",
        base_path="mahoun.pipelines.ingestion.metadata_extractor.MetadataExtractor",
    )
    switchboard.register(
        "ocr_handler", base_path="mahoun.pipelines.ingestion.ocr_handler.OCRHandler"
    )
    switchboard.register(
        "document_handler_factory",
        base_path="mahoun.pipelines.ingestion.document_handlers.DocumentHandlerFactory",
    )
    switchboard.register(
        "ultra_graph_builder",
        base_path="mahoun.graph.ultra_graph_builder.UltraGraphBuilder",
    )
    # Phase C: Passive Ultra Registration
    switchboard.register(
        "legal_nlp",
        base_path="mahoun.nlp.persian_legal_nlp.PersianLegalNLP",
        ultra_path="mahoun.nlp.ultra_persian_legal_nlp.UltraPersianLegalNLP",
        cpu_safe=True,
    )
    switchboard.register(
        "citation_auditor",
        base_path="mahoun.guardrails.ultra_citation_auditor.UltraCitationAuditor",
        ultra_path="mahoun.guardrails.ultra_citation_auditor.UltraCitationAuditor",
        cpu_safe=True,
    )
    switchboard.register(
        "ultra_graph_service",
        base_path="mahoun.graph.graph_query_service.GraphQueryService",
        # The neural graph-query implementation requires a connection and
        # heavyweight model components; keep it BASE on constrained hosts.
    )


# Automatically run bootstrap on import
bootstrap_switchboard()
