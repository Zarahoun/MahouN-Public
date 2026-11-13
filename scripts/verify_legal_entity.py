#!/usr/bin/env python3
"""
MAHOUN Legal Entity & Rule Pre-Flight Verifier
==============================================
CLI tool to rigorously validate candidate legal entities, rules, articles,
and relationships against the MahouN Governance Ontology and Evidence Integrity
standards BEFORE ingestion into the Knowledge Graph.

Usage:
    # Verify a single article inline:
    python scripts/verify_legal_entity.py --type Article \
        --id "article:civil_code:article:10" \
        --law "civil_code" \
        --text "قراردادهای خصوصی نسبت به کسانی که آن را منعقد نموده‌اند نافذ است..." \
        --concept "concept:freedom_of_contract"

    # Verify a batch JSON file of candidate rules/entities:
    python scripts/verify_legal_entity.py --file candidate_rules.json
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Ensure MahouN root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mahoun.core.governance.ontology_enforcer import OntologyEnforcer
from mahoun.core.governance.violations import GovernanceViolationError
from mahoun.graph.ontology.legal_concepts import CANONICAL_LEGAL_CONCEPTS


class LegalEntityVerifier:
    """Pre-flight validation engine for legal knowledge graph candidates."""

    def __init__(self) -> None:
        self.ontology_enforcer = OntologyEnforcer()
        self.allowed_labels = set(self.ontology_enforcer._valid_relationships.keys())

    def verify_article(
        self,
        article_id: str,
        law_id: str,
        text: str,
        concept_id: str | None = None,
        notes: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        """Validate an Article candidate node and its relationships."""
        issues: List[str] = []
        warnings: List[str] = []

        # 1. Structure checks
        if not article_id or not article_id.startswith("article:"):
            issues.append(f"Invalid article ID format: '{article_id}'. Must start with 'article:'")
        if not law_id:
            issues.append("Missing law_id reference")
        if not text or len(text.strip()) < 5:
            issues.append("Article operative text is empty or too short")

        # 2. SHA-256 Provenance computation
        clean_text = text.strip()
        evidence_hash = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()

        # 3. Ontology Relationship checks
        # Check Law -[:CONTAINS]-> Article
        try:
            self.ontology_enforcer.validate_relationship("Law", "CONTAINS", "Article")
        except GovernanceViolationError as e:
            issues.append(f"Ontology violation for Law -> Article: {e}")

        # Check Article -[:REGULATES]-> Concept if concept provided
        if concept_id:
            if concept_id not in CANONICAL_LEGAL_CONCEPTS:
                warnings.append(f"Concept '{concept_id}' not found in CANONICAL_LEGAL_CONCEPTS taxonomy")
            try:
                self.ontology_enforcer.validate_relationship("Article", "REGULATES", "Concept")
            except GovernanceViolationError as e:
                issues.append(f"Ontology violation for Article -> Concept: {e}")

        # 4. Notes checks
        notes_verified = []
        if notes:
            for i, note in enumerate(notes):
                note_text = note.get("text", "").strip()
                if not note_text:
                    issues.append(f"Note {i+1} has empty text")
                    continue
                note_hash = hashlib.sha256(note_text.encode("utf-8")).hexdigest()
                note_id = note.get("id", f"{article_id}:note:{i+1}")
                notes_verified.append({
                    "id": note_id,
                    "text": note_text,
                    "evidence_sha256": note_hash,
                    "is_exception": note.get("is_exception", False),
                })

        return {
            "valid": len(issues) == 0,
            "entity_id": article_id,
            "law_id": law_id,
            "evidence_sha256": evidence_hash,
            "concept_id": concept_id,
            "notes_count": len(notes_verified),
            "notes": notes_verified,
            "issues": issues,
            "warnings": warnings,
        }

    def verify_relationship(
        self,
        source_label: str,
        rel_type: str,
        target_label: str,
    ) -> Tuple[bool, str]:
        """Validate a relationship against OntologyEnforcer rules."""
        try:
            self.ontology_enforcer.validate_relationship(source_label, rel_type, target_label)
            return True, "Valid"
        except GovernanceViolationError as e:
            return False, str(e)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify legal entities and rules before Knowledge Graph ingestion.")
    parser.add_argument("--type", choices=["Article", "UnifiedPrecedent", "Concept"], default="Article", help="Type of entity")
    parser.add_argument("--id", help="Canonical ID (e.g., article:civil_code:article:10)")
    parser.add_argument("--law", help="Law ID (e.g., civil_code)")
    parser.add_argument("--text", help="Operative legal text")
    parser.add_argument("--concept", help="Associated legal concept ID (e.g., concept:freedom_of_contract)")
    parser.add_argument("--file", type=Path, help="Path to JSON file containing candidate entities to verify")
    args = parser.parse_args()

    verifier = LegalEntityVerifier()

    print("=" * 65)
    print("🛡️  MAHOUN Legal Knowledge Graph Pre-Flight Verifier")
    print("=" * 65)

    if args.file:
        if not args.file.exists():
            print(f"❌ File not found: {args.file}")
            sys.exit(1)
        with open(args.file, "r", encoding="utf-8") as f:
            data = json.load(f)

        candidates = data if isinstance(data, list) else [data]
        all_valid = True
        print(f"Verifying {len(candidates)} candidate(s) from {args.file.name}...\n")

        for idx, item in enumerate(candidates, start=1):
            res = verifier.verify_article(
                article_id=item.get("id", ""),
                law_id=item.get("law_id", ""),
                text=item.get("text", ""),
                concept_id=item.get("concept_id"),
                notes=item.get("notes"),
            )
            status = "✅ PASSED" if res["valid"] else "❌ FAILED"
            print(f"[{idx}/{len(candidates)}] {res['entity_id']}: {status}")
            print(f"   SHA-256: {res['evidence_sha256']}")
            if res["warnings"]:
                for w in res["warnings"]:
                    print(f"   ⚠️  Warning: {w}")
            if res["issues"]:
                all_valid = False
                for err in res["issues"]:
                    print(f"   🛑 Error: {err}")
            print("-" * 50)

        sys.exit(0 if all_valid else 1)

    elif args.id and args.text:
        res = verifier.verify_article(
            article_id=args.id,
            law_id=args.law or "unknown",
            text=args.text,
            concept_id=args.concept,
        )
        print(f"Entity ID:       {res['entity_id']}")
        print(f"Law ID:          {res['law_id']}")
        print(f"Evidence SHA256: {res['evidence_sha256']}")
        if res["concept_id"]:
            print(f"Concept:         {res['concept_id']}")
        
        if res["warnings"]:
            print("\n⚠️  Warnings:")
            for w in res["warnings"]:
                print(f" - {w}")

        if res["issues"]:
            print("\n❌ Validation Errors:")
            for err in res["issues"]:
                print(f" - {err}")
            print("\nResult: ❌ REJECTED by Ontology & Evidence Guard")
            sys.exit(1)
        else:
            print("\nResult: ✅ VERIFIED — Ready for Governed Graph Ingestion")
            sys.exit(0)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
