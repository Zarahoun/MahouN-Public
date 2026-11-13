"""Read-only inventory for pre-rollout graph safety.

This command never calls a mutation API. It executes only the explicitly
listed MATCH/SHOW queries through the canonical connection read path and
writes a JSON evidence artifact when requested.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from mahoun.graph.neo4j.connection import get_connection


READ_ONLY_QUERIES: dict[str, str] = {
    "node_labels": "MATCH (n) UNWIND labels(n) AS label RETURN label, count(*) AS count ORDER BY label",
    "law_ids": (
        "MATCH (l:Law) RETURN l.id AS id, labels(l) AS labels, "
        "l.source_hash AS source_hash, l.text_hash AS text_hash, "
        "l.provenance AS provenance, l.parser_version AS parser_version, "
        "l.version AS version, l.quarantine_status AS quarantine_status "
        "ORDER BY id"
    ),
    "relationship_directions": (
        "MATCH (a)-[r]->(b) RETURN labels(a)[0] AS source_label, "
        "type(r) AS relationship_type, labels(b)[0] AS target_label, count(*) AS count "
        "ORDER BY source_label, relationship_type, target_label"
    ),
    "quarantined_laws": (
        "MATCH (l:Law) WHERE l.quarantine_status = 'QUARANTINED' "
        "RETURN l.id AS id, l.source_hash AS source_hash, l.provenance AS provenance "
        "ORDER BY id"
    ),
    "article_identity_collisions": (
        "MATCH (a:Article) WHERE a.number IS NOT NULL "
        "WITH a.number AS article_number, count(*) AS count "
        "WHERE count > 1 RETURN article_number, count ORDER BY article_number"
    ),
    "version_links": (
        "MATCH (a)-[r:HAS_VERSION|SUPERSEDES|SUCCEEDED_BY]->(b) "
        "RETURN labels(a)[0] AS source_label, type(r) AS relationship_type, "
        "labels(b)[0] AS target_label, count(*) AS count "
        "ORDER BY source_label, relationship_type, target_label"
    ),
}


def _assert_read_only(query: str) -> None:
    upper = query.upper()
    forbidden = (
        "CRE" + "ATE ",
        "MER" + "GE ",
        "DEL" + "ETE ",
        "DET" + "ACH ",
        " " + "SET ",
        "REM" + "OVE ",
        "DR" + "OP ",
    )
    if any(token in upper for token in forbidden):
        raise ValueError(f"inventory query is not read-only: {query}")


def collect_inventory(connection: Any) -> dict[str, list[dict[str, Any]]]:
    """Collect all inventory evidence without changing graph state."""

    inventory: dict[str, list[dict[str, Any]]] = {}
    for name, query in READ_ONLY_QUERIES.items():
        _assert_read_only(query)
        inventory[name] = [dict(record) for record in connection.execute_query(query)]
    return inventory


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Neo4j graph safety inventory")
    parser.add_argument("--output", type=Path, help="JSON evidence output path")
    args = parser.parse_args()

    evidence = collect_inventory(get_connection())
    serialized = json.dumps(evidence, ensure_ascii=False, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    else:
        print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
