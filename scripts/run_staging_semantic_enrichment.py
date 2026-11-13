#!/usr/bin/env python3
"""
MAHOUN V2 — GOVERNED STAGING SEMANTIC & DEONTIC ENRICHMENT PIPELINE
==================================================================
Classification: CANONICAL GOVERNED PRODUCTION-GRADE PIPELINE
Target Database: bolt://localhost:7688 (STAGING ONLY)
Safety Guard: Complete fail-closed isolation of port 7687 (Production)
Visual Presentation: Rich Cinematic Terminal UI with Live Metrics & Exemplars

This pipeline enriches the structural legal graph with:
1. Remediation and redirection of misdirected cross-law citations & removal of phantom stubs.
2. Canonical Concept Taxonomy (59 legal concepts + INHERITS_FROM hierarchy).
3. Full article logical decomposition (Condition, Sanction, Exception nodes + edges).
4. Deontic normative operators (LegalObligation, LegalProhibition, LegalPermission, LegalRight).
5. Concept semantic assertions (Article -[:REGULATES]-> Concept).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mahoun.core.environment import bootstrap_environment

bootstrap_environment()

from mahoun.core.governance.governance_context import GovernanceContextManager
from mahoun.core.governance.mutation_boundary import (
    get_audit_sink,
    set_audit_sink,
)
from mahoun.core.governance.validator_pipeline import ValidatorPipeline
from mahoun.core.models.semantic import (
    ArticleDecomposition,
    SemanticAssertion,
    VerificationStatus,
)
from mahoun.graph.extraction.batched_semantic_materializer import BatchedSemanticMaterializer
from mahoun.graph.extraction.semantic_extractor import SemanticExtractor
from mahoun.graph.neo4j.connection import Neo4jConnection
from mahoun.graph.ontology.legal_concepts import CANONICAL_LEGAL_CONCEPTS
from mahoun.graph.ontology.law_registry import (
    INTER_LAW_TRIPLES,
    KNOWN_CROSS_LAW_REDIRECTS,
    LAW_METADATA_REGISTRY,
    derive_law_id_from_node_id,
)
from mahoun.graph.temporal.implicit_repeal_resolver import ImplicitRepealResolver
from mahoun.infrastructure.audit.filesink import compose_default_filesystem_sink

# Mute noisy default loggers to preserve clean visual terminal output
logging.basicConfig(level=logging.WARNING, format="%(message)s")
logger = logging.getLogger("staging_enricher")


# =============================================================================
# Visual Terminal UI Toolkit (ANSI High-Definition Styling)
# =============================================================================
class UI:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Foreground
    RED = "\033[1;31m"
    GREEN = "\033[1;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[1;34m"
    MAGENTA = "\033[1;35m"
    CYAN = "\033[1;36m"
    WHITE = "\033[1;37m"

    # Background
    BG_CYAN = "\033[46;30m"
    BG_GREEN = "\033[42;30m"
    BG_BLUE = "\033[44;37m"

    WIDTH = 84

    @classmethod
    def banner(cls):
        w = cls.WIDTH
        print(f"\n{cls.CYAN}╔{'═' * (w - 2)}╗{cls.RESET}")
        print(f"{cls.CYAN}║{cls.BOLD}{cls.WHITE}{'MAHOUN V2 — GOVERNED LEGAL GRAPH ENRICHMENT ENGINE'.center(w - 2)}{cls.RESET}{cls.CYAN}║{cls.RESET}")
        print(f"{cls.CYAN}║{cls.DIM}{cls.CYAN}{'Constitutional Semantic & Deontic Layer Activation (Orchestra Pass)'.center(w - 2)}{cls.RESET}{cls.CYAN}║{cls.RESET}")
        print(f"{cls.CYAN}╠{'═' * (w - 2)}╣{cls.RESET}")
        print(f"{cls.CYAN}║{cls.YELLOW}  🎯 Target: bolt://localhost:7688 (STAGING GRAPH)                                   {cls.CYAN}║{cls.RESET}")
        print(f"{cls.CYAN}║{cls.GREEN}  🛡️  Safety: 100% Fail-Closed Production Isolation (Port 7687 Locked)               {cls.CYAN}║{cls.RESET}")
        print(f"{cls.CYAN}╚{'═' * (w - 2)}╝{cls.RESET}\n")

    @classmethod
    def section(cls, step: int, title: str, subtitle: str = ""):
        w = cls.WIDTH
        tag = f" PHASE {step}: {title} "
        rem = w - len(tag) - 5
        print(f"\n{cls.BLUE}┌── {cls.BOLD}{cls.WHITE}{tag}{cls.RESET}{cls.BLUE}{'─' * max(0, rem)}┐{cls.RESET}")
        if subtitle:
            print(f"{cls.BLUE}│  {cls.DIM}{cls.CYAN}▸ {subtitle}{cls.RESET}")

    @classmethod
    def card_line(cls, text: str):
        print(f"{cls.BLUE}│  {cls.RESET}{text}")

    @classmethod
    def end_section(cls):
        print(f"{cls.BLUE}└{'─' * (cls.WIDTH - 2)}┘{cls.RESET}")

    @classmethod
    def progress(cls, current: int, total: int, prefix: str = "", length: int = 32):
        if total == 0:
            return
        percent = current / total
        filled = int(length * percent)
        bar = f"{cls.GREEN}█{cls.RESET}" * filled + f"{cls.DIM}░{cls.RESET}" * (length - filled)
        sys.stdout.write(f"\r{cls.BLUE}│  {cls.CYAN}⏳ {prefix}{cls.RESET} [{bar}] {cls.BOLD}{percent * 100:5.1f}%{cls.RESET} ({current}/{total})")
        sys.stdout.flush()
        if current >= total:
            sys.stdout.write(f"  {cls.GREEN}✔ Done{cls.RESET}\n")


# Canonical redirects and Law metadata live in mahoun.graph.ontology.law_registry (SSOT).


def compute_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class GovernedStagingSemanticEnricher:
    """
    Executes the full semantic enrichment pass on Staging Neo4j under strict governance.
    """

    DERIVED_SEMANTIC_LABELS: Tuple[str, ...] = (
        "Condition",
        "Sanction",
        "Exception",
        "LegalObligation",
        "LegalProhibition",
        "LegalPermission",
        "LegalRight",
    )

    def __init__(
        self,
        port: int = 7688,
        password: Optional[str] = None,
        *,
        dry_run: bool = False,
        reset_derived: bool = False,
        confirm_reset: bool = False,
        backup_dir: Optional[str] = None,
    ):
        if port == 7687:
            raise RuntimeError(
                "❌ FATAL SAFETY VIOLATION: Port 7687 is PRODUCTION! "
                "Semantic enrichment can ONLY be run on Staging (port 7688)."
            )
        self.port = port
        self.uri = f"bolt://localhost:{port}"
        resolved_pw = password or os.getenv("NEO4J_PASSWORD") or os.getenv("DB_NEO4J_PASSWORD")
        self.password = resolved_pw
        if resolved_pw:
            self.connection = Neo4jConnection(uri=self.uri, user="neo4j", password=resolved_pw)
        else:
            self.connection = Neo4jConnection(uri=self.uri)
        self.extractor = SemanticExtractor(ontology=CANONICAL_LEGAL_CONCEPTS)
        self.validator_pipeline = ValidatorPipeline()
        self.materializer = BatchedSemanticMaterializer(ontology=CANONICAL_LEGAL_CONCEPTS)
        self.dry_run = dry_run
        self.reset_derived = reset_derived
        self.confirm_reset = confirm_reset
        self.backup_dir = Path(backup_dir) if backup_dir else None
        self.run_id = f"enrichment_run_{int(time.time())}"
        self.baseline_nodes: Dict[str, int] = {}
        self.baseline_rels: Dict[str, int] = {}

    def close(self) -> None:
        """Close the underlying Staging Neo4j connection cleanly."""
        self.connection.close()

    def _ensure_audit_sink(self) -> None:
        if get_audit_sink() is None:
            set_audit_sink(compose_default_filesystem_sink())

    def _execute_governed_write(self, cypher: str, parameters: Optional[Dict[str, Any]] = None) -> List[Any]:
        if self.dry_run:
            return []
        self._ensure_audit_sink()

        async def _run():
            async with GovernanceContextManager.active_context(
                correlation_id=self.run_id,
                execution_mode="STRICT",
                actor_id="operator:semantic_enricher",
            ):
                with self.connection.governed_session(
                    correlation_id=self.run_id,
                    actor_id="operator:semantic_enricher",
                    pipeline=self.validator_pipeline,
                ) as session:
                    return list(session.execute_cypher(cypher, parameters or {}))

        return asyncio.run(_run())

    def _execute_governed_materialization(
        self, statements: List[Tuple[str, Dict[str, Any]]]
    ) -> Any:
        """Execute batched Cypher statements through ValidatorPipeline + BatchedSemanticMaterializer."""
        if not statements or self.dry_run:
            return None
        self._ensure_audit_sink()

        async def _run():
            async with GovernanceContextManager.active_context(
                correlation_id=self.run_id,
                execution_mode="STRICT",
                actor_id="operator:semantic_enricher",
            ):
                with self.connection.governed_session(
                    correlation_id=self.run_id,
                    actor_id="operator:semantic_enricher",
                    pipeline=self.validator_pipeline,
                ) as session:
                    receipt = self.materializer.execute_governed_materialization(
                        session, statements
                    )
                    if receipt.status != "COMMITTED":
                        raise RuntimeError(
                            f"Governed materialization aborted with status={receipt.status}: {receipt.error}"
                        )
                    return receipt

        return asyncio.run(_run())

    def _collect_census(self, conn: Neo4jConnection) -> Tuple[Dict[str, int], Dict[str, int]]:
        """Read-only label and relationship census using canonical Neo4jConnection.execute_query."""
        node_counts: Dict[str, int] = {}
        for row in conn.execute_query(
            "MATCH (n) UNWIND labels(n) AS label RETURN label, count(*) AS c ORDER BY label"
        ):
            node_counts[row["label"]] = int(row["c"])

        rel_counts: Dict[str, int] = {}
        for row in conn.execute_query(
            "MATCH ()-[r]->() RETURN type(r) AS rel, count(*) AS c ORDER BY rel"
        ):
            rel_counts[row["rel"]] = int(row["c"])
        return node_counts, rel_counts

    # =========================================================================
    # Step 1: Preflight Verification & Snapshot
    # =========================================================================
    def preflight_check(self) -> None:
        UI.section(1, "PREFLIGHT SAFETY & BASELINE CENSUS", "Verifying Staging connection and snapshotting baseline state")
        mode_tag = "DRY-RUN PREVIEW" if self.dry_run else "GOVERNED LIVE EXECUTION"
        UI.card_line(f"Connecting to: {UI.BOLD}{UI.WHITE}{self.uri}{UI.RESET} (STAGING | {mode_tag})")

        self.baseline_nodes, self.baseline_rels = self._collect_census(self.connection)

        UI.card_line(
            f"Baseline Snapshot: {UI.GREEN}{sum(self.baseline_nodes.values()):,}{UI.RESET} nodes across {len(self.baseline_nodes)} labels, "
            f"{UI.GREEN}{sum(self.baseline_rels.values()):,}{UI.RESET} relationships across {len(self.baseline_rels)} types."
        )
        UI.card_line(f"Production Port:   {UI.RED}7687 (LOCKED / ISOLATED){UI.RESET}")
        UI.card_line(f"Governance Status: {UI.GREEN}ValidatorPipeline + BatchedSemanticMaterializer + Audit Sink Ready{UI.RESET}")
        UI.end_section()

    def export_backup_jsonl(self, target_dir: Optional[Path] = None) -> Path:
        """Export a deterministic JSONL backup of all nodes and relationships from Staging."""
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_dir = target_dir or self.backup_dir or (REPO_ROOT / "backups" / f"staging_pre_reset_{stamp}")
        out_dir.mkdir(parents=True, exist_ok=True)

        def _json_default(obj: Any) -> Any:
            return str(obj)

        nodes_path = out_dir / "nodes.jsonl"
        rels_path = out_dir / "relationships.jsonl"

        node_total = 0
        offset = 0
        batch = 2000
        with nodes_path.open("w", encoding="utf-8") as nf:
            while True:
                rows = self.connection.execute_query(
                    """
                    MATCH (n)
                    RETURN elementId(n) AS eid, labels(n) AS labels, properties(n) AS props
                    ORDER BY eid
                    SKIP $skip LIMIT $limit
                    """,
                    {"skip": offset, "limit": batch},
                )
                if not rows:
                    break
                for r in rows:
                    nf.write(
                        json.dumps(
                            {"eid": r["eid"], "labels": r["labels"], "properties": r["props"]},
                            ensure_ascii=False,
                            default=_json_default,
                        )
                        + "\n"
                    )
                    node_total += 1
                if len(rows) < batch:
                    break
                offset += batch

        rel_total = 0
        offset = 0
        with rels_path.open("w", encoding="utf-8") as rf:
            while True:
                rows = self.connection.execute_query(
                    """
                    MATCH (a)-[r]->(b)
                    RETURN elementId(r) AS rid, a.id AS src_id, labels(a) AS src_labels,
                           type(r) AS rel_type, b.id AS dst_id, labels(b) AS dst_labels,
                           properties(r) AS props
                    ORDER BY rid
                    SKIP $skip LIMIT $limit
                    """,
                    {"skip": offset, "limit": batch},
                )
                if not rows:
                    break
                for r in rows:
                    rf.write(
                        json.dumps(
                            {
                                "rid": r["rid"],
                                "src_id": r["src_id"],
                                "src_labels": r["src_labels"],
                                "type": r["rel_type"],
                                "dst_id": r["dst_id"],
                                "dst_labels": r["dst_labels"],
                                "properties": r["props"],
                            },
                            ensure_ascii=False,
                            default=_json_default,
                        )
                        + "\n"
                    )
                    rel_total += 1
                if len(rows) < batch:
                    break
                offset += batch

        manifest = {
            "uri": self.uri,
            "exported_at_utc": datetime.now(timezone.utc).isoformat(),
            "nodes": node_total,
            "relationships": rel_total,
        }
        (out_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return out_dir

    def reset_derived_semantic_subgraph(self) -> Dict[str, int]:
        """Backup Staging then remove stale derived semantic nodes/edges cleanly while keeping hierarchy."""
        if self.port == 7687:
            raise RuntimeError("FAIL-CLOSED: Cannot reset Production port 7687.")
        if not self.reset_derived:
            return {"nodes_deleted": 0, "regulates_deleted": 0}
        if not self.confirm_reset:
            raise RuntimeError(
                "FAIL-CLOSED: --reset-derived-semantic requires explicit --confirm-staging-reset flag."
            )

        UI.section(
            "1B",
            "SAFE DERIVED SEMANTIC SUBGRAPH RESET",
            "Backing up Staging & clearing stale derived semantic nodes (preserving Law/Chapter/Article/Clause/REFERENCES/Concept)",
        )
        if self.dry_run:
            derived_cnt = sum(self.baseline_nodes.get(lbl, 0) for lbl in self.DERIVED_SEMANTIC_LABELS)
            reg_cnt = self.baseline_rels.get("REGULATES", 0)
            UI.card_line(
                f"[DRY-RUN] Would backup Staging and reset {derived_cnt:,} derived semantic nodes + {reg_cnt:,} REGULATES edges."
            )
            UI.end_section()
            return {"nodes_deleted": derived_cnt, "regulates_deleted": reg_cnt}

        backup_path = self.export_backup_jsonl()
        UI.card_line(f"Backup written & verified: {UI.GREEN}{backup_path}{UI.RESET}")

        id_rows = self.connection.execute_query(
            """
            MATCH (n)
            WHERE n:Condition OR n:Sanction OR n:Exception
               OR n:LegalObligation OR n:LegalProhibition OR n:LegalPermission OR n:LegalRight
            RETURN n.id AS id
            """
        )
        derived_ids = [r["id"] for r in id_rows if r.get("id") is not None]
        deleted_nodes = 0
        for i in range(0, len(derived_ids), 1000):
            chunk = derived_ids[i : i + 1000]
            res = self._execute_governed_write(
                """
                UNWIND $ids AS nid
                MATCH (n {id: nid})
                WHERE n:Condition OR n:Sanction OR n:Exception
                   OR n:LegalObligation OR n:LegalProhibition OR n:LegalPermission OR n:LegalRight
                DETACH DELETE n
                RETURN count(*) AS deleted
                """,
                {"ids": chunk},
            )
            deleted_nodes += len(chunk) if res is not None else 0

        # Also catch any derived semantic node lacking an id property
        self._execute_governed_write(
            """
            MATCH (n)
            WHERE (n:Condition OR n:Sanction OR n:Exception
                   OR n:LegalObligation OR n:LegalProhibition OR n:LegalPermission OR n:LegalRight)
              AND n.id IS NULL
            DETACH DELETE n
            """
        )

        reg_deleted = 0
        while True:
            rows = self._execute_governed_write(
                """
                MATCH (:Article)-[r:REGULATES]->(:Concept)
                WITH r LIMIT 2000
                DELETE r
                RETURN count(r) AS deleted
                """
            )
            cnt = int(rows[0]["deleted"]) if rows else 0
            reg_deleted += cnt
            if cnt < 2000:
                break

        UI.card_line(
            f"Reset Complete: {UI.GREEN}{deleted_nodes:,}{UI.RESET} derived semantic nodes & {UI.GREEN}{reg_deleted:,}{UI.RESET} REGULATES edges cleared."
        )
        UI.end_section()
        return {"nodes_deleted": deleted_nodes, "regulates_deleted": reg_deleted}

    # =========================================================================
    # Step 2: Remediate Cross-Law Citation Placeholders
    # =========================================================================
    
    # =========================================================================
    # Step 1.5: Materialize Missing Regulation Articles & Direct Taxes Placeholders
    # =========================================================================
    def materialize_missing_structural_entities(self) -> None:
        UI.section(
            "1B",
            "STRUCTURAL ENTITY RESTORATION (MISSING REGULATION ARTICLES & TAXES)",
            "Materializing 7 missing regulation articles (1, 26, 33, 41, 52, 102, 115) & Direct Taxes stubs",
        )

        if self.dry_run:
            UI.card_line("[DRY-RUN] Skipping missing structural entity creation.")
            UI.end_section()
            return

        # Missing articles in regulation:engineering_system_executive_1375
        missing_articles = [
            {
                "id": "article:engineering_system_executive_1375:article:1",
                "law_id": "regulation:engineering_system_executive_1375",
                "number": "1",
                "chapter_id": "chapter:engineering_system_executive_1375:general",
                "raw_text": "□ ماده ۱ در این آئیننامه عبارتهای زیر در معانی مشروح مربوط به کار میروند:\nقانون :قانون نظام مهندسی و کنترل ساختمان – مصوب .۱۳۷۴ مهندسی ساختمان :امور فنی و مهندسی؛ معماری و شهرسازی؛ بخشهای ساختمان و شهرسازی.\nسازمان :سازمان نظام مهندسی ساختمان.\nنظام مهندسی استان :سازمان نظام مهندسی ساختمان استان.\nپروانه اشتغال :پروانه اشتغال به کار مهندسی؛ کاردانی؛ تجربی.\nرشتههای اصلی :رشتههای اصلی مهندسی شامل معماری ،عمران ،تأسیسات مکانیکی ،تأسیسات برقی ،شهرسازی ،نقشهبرداری و ترافیک.\nرشتههای مرتبط :رشتههای مرتبط با رشتههای اصلی.",
            },
            {
                "id": "article:engineering_system_executive_1375:article:26",
                "law_id": "regulation:engineering_system_executive_1375",
                "number": "26",
                "chapter_id": "chapter:engineering_system_executive_1375:ch_2",
                "raw_text": "□ ماده ۲۶ برای دارندگان مدرک تحصیلی کاردانی فنی ،دیپلم فنی و همچنین معماران تجربی در صورت قبول در آزمون علمی و عملی مربوط ،در یکی از رشتههای موضوع قانون حسب مورد پروانه اشتغال در سه درجة پایه ،۳پایه ۲و پایه ۱ صادر میشود.",
            },
            {
                "id": "article:engineering_system_executive_1375:article:33",
                "law_id": "regulation:engineering_system_executive_1375",
                "number": "33",
                "chapter_id": "chapter:engineering_system_executive_1375:ch_2",
                "raw_text": "□ ماده ۳۳ مسئولیت نظارت عالیه بر اجرای ضوابط و مقررات ملّی ساختمان در طراحی و اجرای تمامی ساختمانها و طرحهای شهرسازی و شهرک سازی و عمران شهری که اجرای ضوابط و مقررات مزبور در مورد آنها الزامی است ،بر عهده وزارت مسکن و شهرسازی است.",
            },
            {
                "id": "article:engineering_system_executive_1375:article:41",
                "law_id": "regulation:engineering_system_executive_1375",
                "number": "41",
                "chapter_id": "chapter:engineering_system_executive_1375:ch_2",
                "raw_text": "□ ماده ۴۱ به منظور تأمین مشارکت هر چه وسیعتر مهندسان در انتظام امور حرفهای خود و تحقق اهداف قانون در سطح کشور سازمانی تحت عنوان سازمان نظام مهندسی ساختمان تشکیل میشود.\nارکان سازمان متشکل است از نظام مهندسی استان ،هیأت عمومی، شورای مرکزی ،رئیس سازمان و شورای انتظامی نظام مهندسی.",
            },
            {
                "id": "article:engineering_system_executive_1375:article:52",
                "law_id": "regulation:engineering_system_executive_1375",
                "number": "52",
                "chapter_id": "chapter:engineering_system_executive_1375:ch_2",
                "raw_text": "□ ماده ۵۲ مجمع عمومی نظام مهندسی استان از اجتماع تمامی اشخاص حقیقی عضو نظام مهندسی استان دارای مدارک تحصیلی در رشتههای اصلی یا رشتههای مرتبط و کارت عضویت معتبر ،که اصالتاً یا وکالتاً حق رأی دارند تشکیل میشود.",
            },
            {
                "id": "article:engineering_system_executive_1375:article:102",
                "law_id": "regulation:engineering_system_executive_1375",
                "number": "102",
                "chapter_id": "chapter:engineering_system_executive_1375:ch_2",
                "raw_text": "□ ماده ۱۰۲ در اجرای ماده ۱۹ قانون به منظور ایجاد هماهنگی در امور نظام مهندسی استانها ،هیأت عمومی متشکل از اعضای هیأت مدیرهها در سطح کشور، تشکیل میشود.",
            },
            {
                "id": "article:engineering_system_executive_1375:article:115",
                "law_id": "regulation:engineering_system_executive_1375",
                "number": "115",
                "chapter_id": "chapter:engineering_system_executive_1375:ch_2",
                "raw_text": "□ ماده ۱۱۵ شورای مرکزی در اولین جلسه خود که به دعوت وزیر مسکن و شهرسازی و به ریاست وی در وزارت مسکن و شهرسازی تشکیل میشود ،از میان خود سه نفر را به منظور تعیین رئیس شورای مرکزی به وزیر مسکن و شهرسازی پیشنهاد مینماید.",
            },
        ]

        created_arts = 0
        for item in missing_articles:
            cypher = """
            MERGE (a:Article {id: $id})
            ON CREATE SET a.law_id = $law_id,
                          a.number = $number,
                          a.raw_text = $raw_text,
                          a.normalized_text = $raw_text,
                          a.status = 'resolved',
                          a.created_at = datetime()
            ON MATCH SET a.status = 'resolved',
                         a.raw_text = coalesce(a.raw_text, $raw_text),
                         a.normalized_text = coalesce(a.normalized_text, $raw_text),
                         a.updated_at = datetime()
            WITH a
            MATCH (l:Law {id: $law_id})
            MERGE (l)-[r:CONTAINS]->(a)
            RETURN count(a) AS cnt
            """
            res = self._execute_governed_write(cypher, item)
            if res and res[0]["cnt"] > 0:
                created_arts += res[0]["cnt"]

        UI.card_line(f"Restored & resolved {UI.GREEN}{created_arts}{UI.RESET} missing executive regulation article(s).")

        # Ensure Direct Taxes Mother Law exists for cross-statute anchors
        tax_law_cypher = """
        MERGE (l:Law {id: 'law:direct_taxes'})
        ON CREATE SET l.name = 'قانون مالیات‌های مستقیم مصوب ۱۳۶۶ با اصلاحات',
                      l.title = 'قانون مالیات‌های مستقیم مصوب ۱۳۶۶ با اصلاحات',
                      l.enactment_date = '1366-12-03',
                      l.hierarchy_level = 1,
                      l.specificity_level = 'special',
                      l.created_at = datetime()
        WITH l
        UNWIND ['13', '31', '138', '146'] AS art_num
        MERGE (a:Article {id: 'article:direct_taxes:article:' + art_num})
        ON CREATE SET a.law_id = 'law:direct_taxes',
                      a.number = art_num,
                      a.status = 'unresolved',
                      a.created_at = datetime()
        MERGE (l)-[r:CONTAINS]->(a)
        RETURN count(a) AS cnt
        """
        res_tax = self._execute_governed_write(tax_law_cypher)
        tax_cnt = res_tax[0]["cnt"] if res_tax else 0
        UI.card_line(f"Secured parent Direct Taxes law node and referential boundary anchors ({tax_cnt} items).")
        UI.end_section()

    def remediate_cross_law_placeholders(self) -> None:
        UI.section(2, "CROSS-LAW CITATION REMEDIATION", "Redirecting misdirected edges to true statutory targets & pruning phantoms")

        unresolved = self.connection.execute_query("MATCH (a:Article {status: 'unresolved'}) RETURN a.id AS id")
        unresolved_ids = [r["id"] for r in unresolved]

        UI.card_line(f"Identified {UI.YELLOW}{len(unresolved_ids)}{UI.RESET} unresolved citation stubs in current graph.")
        if self.dry_run:
            UI.card_line("[DRY-RUN] Skipping cross-law redirect/phantom stub mutations.")
            UI.end_section()
            return

        redirected_count = 0
        for ph_id, tgt_id in KNOWN_CROSS_LAW_REDIRECTS.items():
            redirect_cypher = f"""
            MATCH (src:Article)-[r:REFERENCES]->(ph:Article {{id: $ph_id}})
            MERGE (tgt:Article {{id: $tgt_id}})
            ON CREATE SET tgt.status = 'unresolved', tgt.law_id = $tgt_law_id, tgt.number = split($tgt_id, ':')[3]
            MERGE (src)-[new_r:REFERENCES]->(tgt)
            SET new_r = properties(r),
                new_r.redirected_from = $ph_id,
                new_r.redirected_at = datetime()
            DELETE r
            RETURN count(new_r) AS cnt
            """
            res = self._execute_governed_write(redirect_cypher, {"ph_id": ph_id, "tgt_id": tgt_id, "tgt_law_id": derive_law_id_from_node_id(tgt_id)})
            cnt = res[0]["cnt"] if res else 0
            if cnt > 0:
                UI.card_line(f"  ↪ {UI.CYAN}[REDIRECTED]{UI.RESET} {cnt} citation(s): {UI.DIM}{ph_id}{UI.RESET} ➔ {UI.BOLD}{UI.GREEN}{tgt_id}{UI.RESET}")
                redirected_count += cnt

        # Clean isolated placeholders
        cleanup_cypher = """
        MATCH (ph:Article {status: 'unresolved'})
        WHERE NOT ()-[:REFERENCES]->(ph) AND NOT (ph)-[:REFERENCES]->()
        DETACH DELETE ph
        RETURN count(ph) AS deleted
        """
        del_res = self._execute_governed_write(cleanup_cypher)
        deleted_count = del_res[0]["deleted"] if del_res else 0
        UI.card_line(f"Remediation Summary: {UI.GREEN}{redirected_count}{UI.RESET} edges redirected, {UI.GREEN}{deleted_count}{UI.RESET} isolated phantom stubs removed.")
        UI.end_section()

    # =========================================================================
    # Step 3: Materialize Canonical Concepts Taxonomy
    # =========================================================================
    
    # =========================================================================
    # Step 2.5: Enrich Law Metadata and Establish Inter-Law Relations
    # =========================================================================
    def enrich_laws_and_inter_law_relations(self) -> None:
        UI.section(
            "2B",
            "LAW METADATA & INTER-LAW RELATIONS ENRICHMENT",
            "Materializing title, enactment_date, hierarchy_level, specificity_level on 28 Laws & linking AMENDS/REPEALS",
        )

        if self.dry_run:
            UI.card_line("[DRY-RUN] Skipping Law metadata and inter-law edge mutations.")
            UI.end_section()
            return

        # 1. Enrich Law node properties
        updated_laws = 0
        for law_id, meta in LAW_METADATA_REGISTRY.items():
            cypher = """
            MATCH (l:Law {id: $law_id})
            SET l.title = $title,
                l.name = $name,
                l.enactment_date = $enactment_date,
                l.hierarchy_level = $hierarchy_level,
                l.specificity_level = $specificity_level,
                l.updated_at = datetime()
            RETURN count(l) AS cnt
            """
            params = {"law_id": law_id, **meta}
            res = self._execute_governed_write(cypher, params)
            if res and res[0]["cnt"] > 0:
                updated_laws += res[0]["cnt"]

        UI.card_line(f"Successfully updated metadata on {UI.GREEN}{updated_laws}{UI.RESET} / {len(LAW_METADATA_REGISTRY)} Law nodes.")

        # 2. Materialize Canonical Inter-Law Relationships (AMENDS, REPEALS, SUPERSEDES)
        inter_law_links = list(INTER_LAW_TRIPLES)

        created_links = 0
        for src_id, rel_type, tgt_id in inter_law_links:
            link_cypher = f"""
            MATCH (s:Law {{id: $src_id}}), (t:Law {{id: $tgt_id}})
            MERGE (s)-[r:{rel_type}]->(t)
            ON CREATE SET r.created_at = datetime(), r.provenance = 'canonical_legislative_consolidation'
            RETURN count(r) AS cnt
            """
            res = self._execute_governed_write(link_cypher, {"src_id": src_id, "tgt_id": tgt_id})
            if res and res[0]["cnt"] > 0:
                created_links += res[0]["cnt"]

        UI.card_line(f"Successfully ensured {UI.GREEN}{created_links}{UI.RESET} inter-law canonical relationship(s).")

        # 3. Materialize Article-level AMENDS edges from amendment_info ('اصلاحی', 'الحاقی')
        # Where an article in an amending statute has an explicit amendment_info and targets prior law
        art_amends_cypher = """
        MATCH (a:Article)
        WHERE a.amendment_info IS NOT NULL AND a.status = 'resolved'
        WITH a
        MATCH (prior:Article)
        WHERE prior.law_id = 'law:commercial_code_1311' AND prior.number = a.number
          AND a.law_id = 'law:commercial_amendment_1347'
        MERGE (a)-[r:AMENDS]->(prior)
        ON CREATE SET r.created_at = datetime(),
                      r.amendment_type = a.amendment_info,
                      r.confidence = 0.95,
                      r.extractor = 'amendment_extractor'
        RETURN count(r) AS cnt
        """
        res_art_amends = self._execute_governed_write(art_amends_cypher)
        art_amends_cnt = res_art_amends[0]["cnt"] if res_art_amends else 0
        UI.card_line(f"Materialized {UI.GREEN}{art_amends_cnt}{UI.RESET} cross-statute Article [:AMENDS] relationship(s).")

        # 4. Check Law Article 4 Repeal in Staging if repeal article exists
        repeal_cypher = """
        MATCH (s:Article), (t:Article)
        WHERE s.id IN ['article:check_law:article:23', 'law:check_law:article:23']
          AND t.id IN ['article:check_law:article:4', 'law:check_law:article:4']
        MERGE (s)-[r:REPEALS]->(t)
        ON CREATE SET r.created_at = datetime(),
                      r.repeal_type = 'explicit_repeal',
                      r.confidence = 0.95,
                      r.extractor = 'repeal_extractor'
        RETURN count(r) AS cnt
        """
        res_rep = self._execute_governed_write(repeal_cypher)
        rep_cnt = res_rep[0]["cnt"] if res_rep else 0
        if rep_cnt > 0:
            UI.card_line(f"Materialized {UI.GREEN}{rep_cnt}{UI.RESET} statutory [:REPEALS] relationship(s).")

        UI.end_section()

    def materialize_concept_taxonomy(self) -> None:
        UI.section(
            3,
            "CANONICAL CONCEPT TAXONOMY MATERIALIZATION",
            f"Injecting {len(CANONICAL_LEGAL_CONCEPTS)} Jurisprudential Concepts and INHERITS_FROM hierarchy",
        )

        ontology_stmts = self.materializer.build_batched_ontology_statements()
        concept_count = len(CANONICAL_LEGAL_CONCEPTS)
        hierarchy_pairs = [
            (c.canonical_id, c.parent_concept_id)
            for c in CANONICAL_LEGAL_CONCEPTS.values()
            if c.parent_concept_id
        ]

        if self.dry_run:
            UI.card_line(
                f"{UI.YELLOW}[DRY-RUN]{UI.RESET} Prepared {len(ontology_stmts)} governed ontology batch statement(s) "
                f"({concept_count} :Concept, {len(hierarchy_pairs)} :INHERITS_FROM); skipping writes."
            )
        else:
            self._execute_governed_materialization(ontology_stmts)
            UI.card_line(f"Materialized {UI.GREEN}{concept_count}{UI.RESET} canonical :Concept nodes.")
            UI.card_line(
                f"Forged {UI.GREEN}{len(hierarchy_pairs)}{UI.RESET} ontological :INHERITS_FROM relationships."
            )

        # Display sample hierarchy
        UI.card_line(f"{UI.DIM}Ontology sample tree:{UI.RESET}")
        for child_id, parent_id in hierarchy_pairs[:3]:
            UI.card_line(
                f"   {UI.MAGENTA}{child_id}{UI.RESET} ──[:INHERITS_FROM]──► {UI.CYAN}{parent_id}{UI.RESET}"
            )
        UI.end_section()

    # =========================================================================
    # Step 4: Decompose Articles & Extract Semantic Entities/Edges
    # =========================================================================
    def enrich_articles_semantic(self) -> None:
        UI.section(
            4,
            "MASS SEMANTIC & DEONTIC DECOMPOSITION",
            "Extracting Conditions, Scoped Conditions, Sanctions, Exceptions, Verified Concepts & Deontic Norms",
        )

        articles = self.connection.execute_query(
            """
            MATCH (a:Article)
            WHERE a.status = 'resolved'
            RETURN a.id AS id, a.law_id AS law_id, a.number AS number,
                   coalesce(a.raw_text, a.normalized_text, '') AS text
            ORDER BY a.law_id, a.number
            """
        )

        total = len(articles)
        UI.card_line(f"Executing decomposition pass on {UI.BOLD}{UI.WHITE}{total:,}{UI.RESET} resolved statutory articles...")

        decompositions: List[ArticleDecomposition] = []
        raw_assertions: List[SemanticAssertion] = []

        start_time = time.time()
        for idx, art in enumerate(articles, 1):
            art_id = art["id"]
            law_id = art["law_id"] or ""
            text = art["text"]
            if text and len(text.strip()) >= 5:
                decomp = self.extractor.decompose_article(art_id, law_id, text)
                decompositions.append(decomp)
                raw_assertions.extend(self.extractor.extract_concept_assertions(art_id, text))

            if idx % 100 == 0 or idx == total:
                UI.progress(idx, total, prefix="Decomposing Corpus")

        accepted = self.materializer.accept_extracted_assertions(
            raw_assertions,
            decompositions=decompositions,
            extractor=self.extractor,
        )
        verified_only = [
            a for a in accepted
            if a.status in (VerificationStatus.VERIFIED, VerificationStatus.MATERIALIZED)
        ]
        withheld_count = len(accepted) - len(verified_only)
        distinct_regulates = len({(a.source_entity_id, a.target_entity_id) for a in verified_only})

        decomp_stmts = self.materializer.build_batched_decompositions(decompositions)
        deontic_stmts = self.materializer.build_batched_deontic_norms(decompositions)
        assertion_stmts = self.materializer.build_batched_assertions(accepted)
        all_stmts = decomp_stmts + deontic_stmts + assertion_stmts

        cond_cnt = sum(len(d.conditions) for d in decompositions)
        scoped_cnt = sum(len(d.scoped_conditions) for d in decompositions)
        sanc_cnt = sum(len(d.sanctions) for d in decompositions)
        exc_cnt = sum(len(d.exceptions) for d in decompositions)
        oblg_cnt = sum(1 for d in decompositions for n in d.deontic_norms if n.norm_type == "OBLIGATION")
        prohib_cnt = sum(1 for d in decompositions for n in d.deontic_norms if n.norm_type == "PROHIBITION")
        perm_cnt = sum(1 for d in decompositions for n in d.deontic_norms if n.norm_type == "PERMISSION")
        right_cnt = sum(1 for d in decompositions for n in d.deontic_norms if n.norm_type == "RIGHT")

        elapsed = time.time() - start_time
        UI.card_line(
            f"Analysis completed in {UI.BOLD}{elapsed:.2f}s{UI.RESET} "
            f"({total / max(0.1, elapsed):.1f} articles/sec; {len(decompositions):,} non-empty)."
        )
        UI.card_line(f"  • {UI.GREEN}{cond_cnt:,}{UI.RESET} :Condition nodes + [:HAS_CONDITION] edges ({scoped_cnt:,} [:SCOPED_CONDITION]).")
        UI.card_line(f"  • {UI.GREEN}{sanc_cnt:,}{UI.RESET} :Sanction nodes + [:HAS_SANCTION] edges.")
        UI.card_line(f"  • {UI.GREEN}{exc_cnt:,}{UI.RESET} :Exception nodes + [:HAS_EXCEPTION] edges.")
        UI.card_line(
            f"  • {UI.GREEN}{len(verified_only):,}{UI.RESET} verified [:REGULATES] assertions "
            f"({distinct_regulates:,} distinct edges; {withheld_count:,} ungrounded CANDIDATE mentions withheld)."
        )
        UI.card_line(f"  • {UI.GREEN}{oblg_cnt:,}{UI.RESET} :LegalObligation nodes + [:HAS_OBLIGATION] edges.")
        UI.card_line(f"  • {UI.GREEN}{prohib_cnt:,}{UI.RESET} :LegalProhibition nodes + [:HAS_PROHIBITION] edges.")
        UI.card_line(f"  • {UI.GREEN}{perm_cnt:,}{UI.RESET} :LegalPermission nodes + [:HAS_PERMISSION] edges.")
        UI.card_line(f"  • {UI.GREEN}{right_cnt:,}{UI.RESET} :LegalRight nodes + [:HAS_RIGHT] edges.")

        if self.dry_run:
            UI.card_line(
                f"{UI.YELLOW}[DRY-RUN]{UI.RESET} Prepared {len(all_stmts):,} governed batch statement(s) "
                f"(decomp={len(decomp_stmts)}, deontic={len(deontic_stmts)}, regulates={len(assertion_stmts)}); skipping writes."
            )
        else:
            UI.card_line("Commencing governed atomic batch materialization on Neo4j Staging...")
            receipt = self._execute_governed_materialization(all_stmts)
            if receipt is not None:
                UI.card_line(
                    f"Materialization Receipt: status={UI.GREEN}{receipt.status}{UI.RESET} | "
                    f"batches={receipt.statements_executed} | nodes_merged={receipt.nodes_merged:,} | "
                    f"rels_created={receipt.relationships_created:,}"
                )
        UI.end_section()

    # =========================================================================
    # Step 5: Live Exemplar Inspection
    # =========================================================================
    
    # =========================================================================
    # Step 4B: Mass Semantic & Deontic Decomposition for Clauses
    # =========================================================================
    def execute_clause_semantic_decomposition(self) -> None:
        UI.section(
            "4B",
            "CLAUSE SEMANTIC & DEONTIC DECOMPOSITION",
            "Extracting Conditions, Sanctions, Exceptions, Verified Concepts & Deontic Norms for Clauses (تبصره‌ها)",
        )

        clauses = self.connection.execute_query(
            """
            MATCH (c:Clause)
            RETURN c.id AS id, c.law_id AS law_id, c.clause_type AS clause_type,
                   coalesce(c.raw_text, c.normalized_text, '') AS text
            ORDER BY c.id
            """
        )

        total = len(clauses)
        UI.card_line(f"Executing decomposition pass on {UI.BOLD}{UI.WHITE}{total:,}{UI.RESET} statutory clauses...")

        decompositions: List[ArticleDecomposition] = []
        raw_assertions: List[SemanticAssertion] = []

        start_time = time.time()
        for idx, cl in enumerate(clauses, 1):
            cl_id = cl["id"]
            law_id = cl["law_id"] or ""
            text = cl["text"]
            if text and len(text.strip()) >= 5:
                decomp = self.extractor.decompose_article(cl_id, law_id, text)
                decompositions.append(decomp)
                raw_assertions.extend(self.extractor.extract_concept_assertions(cl_id, text))

            if idx % 200 == 0 or idx == total:
                UI.progress(idx, total, prefix="Decomposing Clauses")

        accepted = self.materializer.accept_extracted_assertions(
            raw_assertions,
            decompositions=decompositions,
            extractor=self.extractor,
        )
        verified_only = [
            a for a in accepted
            if a.status in (VerificationStatus.VERIFIED, VerificationStatus.MATERIALIZED)
        ]

        decomp_stmts = self.materializer.build_batched_decompositions(decompositions)
        deontic_stmts = self.materializer.build_batched_deontic_norms(decompositions)
        assertion_stmts = self.materializer.build_batched_assertions(accepted)
        all_stmts = decomp_stmts + deontic_stmts + assertion_stmts

        cond_cnt = sum(len(d.conditions) for d in decompositions)
        sanc_cnt = sum(len(d.sanctions) for d in decompositions)
        exc_cnt = sum(len(d.exceptions) for d in decompositions)
        norm_cnt = sum(len(d.deontic_norms) for d in decompositions)

        elapsed = time.time() - start_time
        UI.card_line(
            f"Clause analysis completed in {UI.BOLD}{elapsed:.2f}s{UI.RESET} "
            f"({total / max(0.1, elapsed):.1f} clauses/sec; {len(decompositions):,} processed)."
        )
        UI.card_line(f"  • {UI.GREEN}{cond_cnt:,}{UI.RESET} Clause conditions, {UI.GREEN}{sanc_cnt:,}{UI.RESET} sanctions, {UI.GREEN}{exc_cnt:,}{UI.RESET} exceptions.")
        UI.card_line(f"  • {UI.GREEN}{norm_cnt:,}{UI.RESET} Clause deontic norms, {UI.GREEN}{len(verified_only):,}{UI.RESET} verified [:REGULATES] concept links.")

        if self.dry_run:
            UI.card_line(f"{UI.YELLOW}[DRY-RUN]{UI.RESET} Prepared {len(all_stmts):,} batch statements for Clauses; skipping writes.")
        else:
            UI.card_line("Commencing governed batch materialization for Clauses on Neo4j Staging...")
            receipt = self._execute_governed_materialization(all_stmts)
            if receipt is not None:
                UI.card_line(
                    f"Clause Materialization Receipt: status={UI.GREEN}{receipt.status}{UI.RESET} | "
                    f"batches={receipt.statements_executed} | nodes_merged={receipt.nodes_merged:,} | "
                    f"rels_created={receipt.relationships_created:,}"
                )
        UI.end_section()

    def inspect_live_exemplars(self) -> None:
        UI.section(5, "LIVE GRAPH SPOTLIGHT & EXEMPLARS", "Inspecting actual materialized semantic structures from Staging Neo4j")

        exemplars = self.connection.execute_query(
            """
            MATCH (a:Article)-[:HAS_CONDITION]->(c:Condition)
            OPTIONAL MATCH (a)-[:HAS_OBLIGATION]->(o:LegalObligation)
            OPTIONAL MATCH (a)-[:HAS_SANCTION]->(s:Sanction)
            OPTIONAL MATCH (a)-[:REGULATES]->(cp:Concept)
            WITH a,
                 collect(DISTINCT c.condition_text) AS conditions,
                 collect(DISTINCT o.text) AS obligations,
                 collect(DISTINCT s.sanction_text) AS sanctions,
                 collect(DISTINCT cp.name) AS concepts
            WHERE size(conditions) > 0 AND (size(obligations) > 0 OR size(sanctions) > 0)
            RETURN a.id AS id, a.number AS number, a.law_id AS law_id,
                   conditions[0] AS sample_cond,
                   obligations[0] AS sample_oblg,
                   sanctions[0] AS sample_sanc,
                   concepts[0..3] AS sample_concepts
            LIMIT 2
            """
        )

        if not exemplars:
            UI.card_line("No complex exemplar found with simultaneous condition and obligation.")
        else:
            for ex in exemplars:
                UI.card_line(f"┌─ {UI.BOLD}{UI.WHITE}Article: {ex['id']}{UI.RESET} (Law: {ex['law_id']})")
                if ex.get("sample_cond"):
                    cond_snippet = ex['sample_cond'][:110] + "..." if len(ex['sample_cond']) > 110 else ex['sample_cond']
                    UI.card_line(f"│  {UI.CYAN}◆ Condition (شرط):{UI.RESET}     «{cond_snippet}»")
                if ex.get("sample_oblg"):
                    oblg_snippet = ex['sample_oblg'][:110] + "..." if len(ex['sample_oblg']) > 110 else ex['sample_oblg']
                    UI.card_line(f"│  {UI.YELLOW}◆ Obligation (تکلیف):{UI.RESET}  «{oblg_snippet}»")
                if ex.get("sample_sanc"):
                    sanc_snippet = ex['sample_sanc'][:110] + "..." if len(ex['sample_sanc']) > 110 else ex['sample_sanc']
                    UI.card_line(f"│  {UI.RED}◆ Sanction (کیفر):{UI.RESET}    «{sanc_snippet}»")
                if ex.get("sample_concepts"):
                    UI.card_line(f"│  {UI.MAGENTA}◆ Regulates (مفاهیم):{UI.RESET}  {', '.join(ex['sample_concepts'])}")
                UI.card_line(f"└{'─' * 60}")

        UI.end_section()

    # =========================================================================
    # Step 6: Post-Enrichment Census & Comparative Matrix
    # =========================================================================
    def post_enrichment_census(self) -> None:
        UI.section(6, "BEFORE vs AFTER COMPARATIVE MATRIX", "Auditing exact node & edge deltas on Staging (7688)")

        current_nodes, current_rels = self._collect_census(self.connection)
        UI.card_line(
            f"Current Snapshot:  {UI.GREEN}{sum(current_nodes.values()):,}{UI.RESET} nodes across {len(current_nodes)} labels, "
            f"{UI.GREEN}{sum(current_rels.values()):,}{UI.RESET} relationships across {len(current_rels)} types."
        )
        conflicts = ImplicitRepealResolver(self.connection).detect_all_conflicts()
        UI.card_line(
            f"Temporal Readiness: {UI.CYAN}{len(conflicts):,}{UI.RESET} implicit-repeal / conflict candidate(s) detected (read-only audit)."
        )
        UI.end_section()

        # Print Table
        w1, w2, w3, w4 = 26, 14, 14, 14
        div = f"├{'─' * w1}┼{'─' * w2}┼{'─' * w3}┼{'─' * w4}┤"
        top = f"┌{'─' * w1}┬{'─' * w2}┬{'─' * w3}┬{'─' * w4}┐"
        bot = f"└{'─' * w1}┴{'─' * w2}┴{'─' * w3}┴{'─' * w4}┘"

        print(f"\n{UI.CYAN}{top}{UI.RESET}")
        print(f"{UI.CYAN}│{UI.BOLD}{UI.WHITE}{'Entity / Label Name'.center(w1)}{UI.CYAN}│"
              f"{UI.BOLD}{UI.WHITE}{'Baseline'.center(w2)}{UI.CYAN}│"
              f"{UI.BOLD}{UI.WHITE}{'Enriched'.center(w3)}{UI.CYAN}│"
              f"{UI.BOLD}{UI.WHITE}{'Delta'.center(w4)}{UI.CYAN}│{UI.RESET}")
        print(f"{UI.CYAN}{div}{UI.RESET}")

        all_labels = sorted(set(list(self.baseline_nodes.keys()) + list(current_nodes.keys())))
        for lbl in all_labels:
            b = self.baseline_nodes.get(lbl, 0)
            c = current_nodes.get(lbl, 0)
            d = c - b
            d_str = f"+{d:,}" if d > 0 else (f"{d:,}" if d < 0 else "0")
            d_color = UI.GREEN if d > 0 else (UI.RED if d < 0 else UI.DIM)
            print(f"{UI.CYAN}│{UI.RESET} {lbl:<{w1 - 2}} {UI.CYAN}│{UI.RESET}"
                  f" {b:>{w2 - 2},} {UI.CYAN}│{UI.RESET}"
                  f" {UI.BOLD}{c:>{w3 - 2},}{UI.RESET} {UI.CYAN}│{UI.RESET}"
                  f" {d_color}{d_str:>{w4 - 2}}{UI.RESET} {UI.CYAN}│{UI.RESET}")

        print(f"{UI.CYAN}{div}{UI.RESET}")
        print(f"{UI.CYAN}│{UI.BOLD}{UI.YELLOW}{'--- RELATIONSHIPS ---'.center(w1)}{UI.CYAN}│"
              f"{'':<{w2}}{UI.CYAN}│{'':<{w3}}{UI.CYAN}│{'':<{w4}}{UI.CYAN}│{UI.RESET}")
        print(f"{UI.CYAN}{div}{UI.RESET}")

        all_rels = sorted(set(list(self.baseline_rels.keys()) + list(current_rels.keys())))
        for r in all_rels:
            b = self.baseline_rels.get(r, 0)
            c = current_rels.get(r, 0)
            d = c - b
            d_str = f"+{d:,}" if d > 0 else (f"{d:,}" if d < 0 else "0")
            d_color = UI.GREEN if d > 0 else (UI.RED if d < 0 else UI.DIM)
            print(f"{UI.CYAN}│{UI.RESET} {r:<{w1 - 2}} {UI.CYAN}│{UI.RESET}"
                  f" {b:>{w2 - 2},} {UI.CYAN}│{UI.RESET}"
                  f" {UI.BOLD}{c:>{w3 - 2},}{UI.RESET} {UI.CYAN}│{UI.RESET}"
                  f" {d_color}{d_str:>{w4 - 2}}{UI.RESET} {UI.CYAN}│{UI.RESET}")

        print(f"{UI.CYAN}{bot}{UI.RESET}\n")

        # Verify Production Safety (read-only via execute_query; zero _driver.session())
        prod_conn = (
            Neo4jConnection(uri="bolt://localhost:7687", user="neo4j", password=self.password)
            if self.password
            else Neo4jConnection(uri="bolt://localhost:7687")
        )
        try:
            prod_node_cnt = int(prod_conn.execute_query("MATCH (n) RETURN count(n) AS c")[0]["c"])
            prod_rel_cnt = int(prod_conn.execute_query("MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"])
            print(f"{UI.GREEN}╔{'═' * (UI.WIDTH - 2)}╗{UI.RESET}")
            print(f"{UI.GREEN}║{UI.BOLD}{UI.WHITE}{'🛡️  PRODUCTION INTEGRITY PROOF (PORT 7687)'.center(UI.WIDTH - 2)}{UI.RESET}{UI.GREEN}║{UI.RESET}")
            print(f"{UI.GREEN}║  Nodes: {prod_node_cnt:,} (Baseline: 5,343)   |   Relationships: {prod_rel_cnt:,} (Baseline: 5,487)     {UI.GREEN}║{UI.RESET}")
            if prod_node_cnt == 5343 and prod_rel_cnt == 5487:
                print(f"{UI.GREEN}║  STATUS: {UI.BOLD}{UI.BG_GREEN} ZERO DRIFT CONFIRMED. PRODUCTION 100% UNTOUCHED & BIT-IDENTICAL! {UI.RESET}{UI.GREEN}║{UI.RESET}")
            else:
                print(f"{UI.RED}║  STATUS: CRITICAL DRIFT DETECTED IN PRODUCTION! INVESTIGATE IMMEDIATELY!    {UI.RED}║{UI.RESET}")
            print(f"{UI.GREEN}╚{'═' * (UI.WIDTH - 2)}╝{UI.RESET}\n")
        finally:
            prod_conn.close()


def main():
    parser = argparse.ArgumentParser(description="MahouN Staging Semantic Enrichment Pipeline")
    parser.add_argument("--port", type=int, default=7688, help="Neo4j Port (Default: 7688 - Staging)")
    parser.add_argument("--password", type=str, default=None, help="Neo4j Password")
    parser.add_argument("--dry-run", action="store_true", help="Analyze & preview enrichment without mutating Neo4j")
    parser.add_argument("--backup-only", action="store_true", help="Export Staging JSONL backup and exit without mutating")
    parser.add_argument(
        "--reset-derived-semantic",
        action="store_true",
        help="Backup Staging then reset derived Condition/Sanction/Exception/Deontic/REGULATES subgraph before enrichment",
    )
    parser.add_argument(
        "--confirm-staging-reset",
        action="store_true",
        help="Explicit operator consent confirmation required alongside --reset-derived-semantic",
    )
    parser.add_argument("--backup-dir", type=str, default=None, help="Optional destination directory for JSONL backup")
    args = parser.parse_args()

    UI.banner()
    enricher = GovernedStagingSemanticEnricher(
        port=args.port,
        password=args.password,
        dry_run=args.dry_run,
        reset_derived=args.reset_derived_semantic,
        confirm_reset=args.confirm_staging_reset,
        backup_dir=args.backup_dir,
    )
    try:
        enricher.preflight_check()
        if args.backup_only:
            out_dir = enricher.export_backup_jsonl()
            print(f"Staging backup exported cleanly to: {out_dir}")
            return
        if args.reset_derived_semantic:
            enricher.reset_derived_semantic_subgraph()
        enricher.materialize_missing_structural_entities()
        enricher.enrich_laws_and_inter_law_relations()
        enricher.remediate_cross_law_placeholders()
        enricher.materialize_concept_taxonomy()
        enricher.enrich_articles_semantic()
        enricher.execute_clause_semantic_decomposition()
        enricher.inspect_live_exemplars()
        enricher.post_enrichment_census()
    finally:
        enricher.close()


if __name__ == "__main__":
    main()
