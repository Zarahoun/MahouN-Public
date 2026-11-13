#!/usr/bin/env python3
"""Run ExistingKGAudit against the current Neo4j database."""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from mahoun.graph.neo4j.connection import get_connection
from mahoun.graph.validation.existing_kg_audit import ExistingKGAudit
from mahoun.core.governance.ontology_enforcer import OntologyEnforcer


class AuditConnectionAdapter:
    def __init__(self, neo4j_connection):
        self._conn = neo4j_connection
    
    def execute_query(self, query: str, parameters=None):
        return self._conn.execute_query(query, parameters or {})


def main():
    print("=" * 80)
    print("ExistingKGAudit - Knowledge Graph Health Check")
    print("=" * 80)
    print()
    
    print("Connecting to Neo4j...")
    try:
        conn = get_connection()
        adapter = AuditConnectionAdapter(conn)
        print("Connected")
    except Exception as e:
        print(f"Connection failed: {e}")
        return 1
    
    print("\nRunning audit...")
    try:
        enforcer = OntologyEnforcer()
        audit = ExistingKGAudit(adapter, enforcer)
        report = audit.run()
    except Exception as e:
        print(f"Audit failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    print("Audit completed\n")
    
    print("=" * 80)
    print(f"STATUS: {report.status.value}")
    print("=" * 80)
    print()
    
    print("METRICS:")
    for key, value in report.metrics.items():
        print(f"  {key}: {value}")
    print()
    
    print("FINDINGS:")
    for finding in report.findings:
        status_icon = "✅" if finding.status.value == "PASS" else "❌"
        print(f"{status_icon} {finding.name}: {finding.status.value}")
        if finding.count is not None:
            print(f"   Count: {finding.count}")
        print(f"   {finding.detail}")
    print()
    
    if report.graph_fingerprint:
        print(f"Graph Fingerprint: {report.graph_fingerprint[:16]}...")
    
    # Save report
    output_path = Path("reports") / "kg_audit_runtime_baseline.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
    print(f"\nReport saved to: {output_path}")
    
    return 0 if report.status.value == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
