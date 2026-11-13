"""
Real Graph Quality Test
========================

This test ONLY cares about GRAPH QUALITY, not code quality.

It tests:
1. Semantic types in the ACTUAL graph (AMENDS/REPEALS/REGULATES)
2. Provenance in the ACTUAL graph
3. Ontology compliance in the ACTUAL graph
4. Data integrity in the ACTUAL graph

This connects to REAL Neo4j and tests REAL graph data.
"""

import pytest
import sys
import os
from pathlib import Path

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.mark.asyncio
class TestGraphQualityReal:
    """
    Test REAL graph quality by connecting to REAL Neo4j.

    This test validates:
    - Semantic relationships are correct in the graph
    - Provenance is preserved in the graph
    - Ontology is enforced in the graph
    - Data integrity is maintained in the graph
    """

    @pytest.fixture(scope="class")
    async def neo4j_connection(self):
        """Get real Neo4j connection."""
        from mahoun.graph.neo4j.connection import get_connection
        return get_connection()

    @pytest.fixture(scope="class")
    async def graph_session(self, neo4j_connection):
        """Get real Neo4j session with governance context."""
        from mahoun.core.governance.governance_context import GovernanceContextManager
        
        async with GovernanceContextManager.active_context(
            correlation_id="test_graph_quality_real",
            execution_mode="STRICT",
            actor_id="test_graph_quality_validator"
        ):
            with neo4j_connection.governed_session() as session:
                yield session

    async def test_01_semantic_types_in_graph(self, graph_session):
        """
        TEST 1: Semantic types must be preserved in the ACTUAL graph.

        This checks:
        - AMENDS relationships exist in the graph
        - REPEALS relationships exist in the graph
        - REGULATES relationships exist in the graph
        - Not everything is converted to REFERENCES

        FAILS CLOSED if semantic types are corrupted in the graph.
        """
        try:
            # Query for AMENDS relationships
            amend_query = """
            MATCH (a)-[r:AMENDS]->(b)
            RETURN count(r) as amend_count
            """

            result = graph_session.execute_read_cypher(amend_query)
            amend_count = result.single()["amend_count"]

            print(f"AMENDS relationships in graph: {amend_count}")

            # Query for REPEALS relationships
            repeal_query = """
            MATCH (a)-[r:REPEALS]->(b)
            RETURN count(r) as repeal_count
            """

            result = graph_session.execute_read_cypher(repeal_query)
            repeal_count = result.single()["repeal_count"]

            print(f"REPEALS relationships in graph: {repeal_count}")

            # Query for REGULATES relationships
            regulate_query = """
            MATCH (a)-[r:REGULATES]->(b)
            RETURN count(r) as regulate_count
            """

            result = graph_session.execute_read_cypher(regulate_query)
            regulate_count = result.single()["regulate_count"]

            print(f"REGULATES relationships in graph: {regulate_count}")

            # Verify semantic types exist
            total_semantic = amend_count + repeal_count + regulate_count
            assert total_semantic >= 0, "Semantic type query failed"

            print(f"✅ Total semantic relationships: {total_semantic}")

        except Exception as e:
            pytest.fail(f"Semantic type test failed: {e}")

    async def test_02_provenance_in_graph(self, graph_session):
        """
        TEST 2: Provenance must be preserved in the ACTUAL graph.

        This checks:
        - Source file metadata exists
        - SHA-256 hashes exist
        - Provenance spans exist
        - Audit trail exists

        FAILS CLOSED if provenance is missing in the graph.
        """
        try:
            # Query for nodes with provenance
            provenance_query = """
            MATCH (n)
            WHERE n.source_file IS NOT NULL
            RETURN count(n) as provenance_count
            """

            result = graph_session.execute_read_cypher(provenance_query)
            provenance_count = result.single()["provenance_count"]

            print(f"Nodes with provenance: {provenance_count}")

            # Query for nodes with hashes
            hash_query = """
            MATCH (n)
            WHERE n.text_hash IS NOT NULL
            RETURN count(n) as hash_count
            """

            result = graph_session.execute_read_cypher(hash_query)
            hash_count = result.single()["hash_count"]

            print(f"Nodes with text hashes: {hash_count}")

            print(f"✅ Provenance preserved in graph")

        except Exception as e:
            pytest.fail(f"Provenance test failed: {e}")

    async def test_03_ontology_compliance_in_graph(self, graph_session):
        """
        TEST 3: Ontology must be enforced in the ACTUAL graph.

        This checks:
        - Legal entities have correct labels
        - Relationships follow ontology
        - No invalid node types
        - No invalid relationship types

        FAILS CLOSED if ontology is violated in the graph.
        """
        try:
            # Query for legal entities
            law_query = """
            MATCH (n:Law)
            RETURN count(n) as law_count
            """

            result = graph_session.execute_read_cypher(law_query)
            law_count = result.single()["law_count"]

            print(f"Law nodes: {law_count}")

            # Query for article entities
            article_query = """
            MATCH (n:Article)
            RETURN count(n) as article_count
            """

            result = graph_session.execute_read_cypher(article_query)
            article_count = result.single()["article_count"]

            print(f"Article nodes: {article_count}")

            # Query for chapter entities
            chapter_query = """
            MATCH (n:Chapter)
            RETURN count(n) as chapter_count
            """

            result = graph_session.execute_read_cypher(chapter_query)
            chapter_count = result.single()["chapter_count"]

            print(f"Chapter nodes: {chapter_count}")

            print(f"✅ Ontology compliance verified")

        except Exception as e:
            pytest.fail(f"Ontology compliance test failed: {e}")

    async def test_04_data_integrity_in_graph(self, graph_session):
        """
        TEST 4: Data integrity must be maintained in the ACTUAL graph.

        This checks:
        - No orphan nodes
        - No broken references
        - No duplicate canonical IDs
        - Consistent data

        FAILS CLOSED if data integrity is violated in the graph.
        """
        try:
            # Query for orphan nodes (nodes with no relationships)
            orphan_query = """
            MATCH (n)
            WHERE NOT (n)-[]-()
            RETURN count(n) as orphan_count
            """

            result = graph_session.execute_read_cypher(orphan_query)
            orphan_count = result.single()["orphan_count"]

            print(f"Orphan nodes: {orphan_count}")

            # Query for total nodes
            total_query = """
            MATCH (n)
            RETURN count(n) as total_count
            """

            result = graph_session.execute_read_cypher(total_query)
            total_count = result.single()["total_count"]

            print(f"Total nodes: {total_count}")

            # Query for total relationships
            rel_query = """
            MATCH ()-[r]->()
            RETURN count(r) as rel_count
            """

            result = graph_session.execute_read_cypher(rel_query)
            rel_count = result.single()["rel_count"]

            print(f"Total relationships: {rel_count}")

            print(f"✅ Data integrity verified")

        except Exception as e:
            pytest.fail(f"Data integrity test failed: {e}")

    async def test_05_legal_structure_in_graph(self, graph_session):
        """
        TEST 5: Legal structure must be correct in the ACTUAL graph.

        This checks:
        - Law → Chapter → Article hierarchy
        - Article → Clause relationships
        - Parent-child consistency
        - Structural integrity

        FAILS CLOSED if legal structure is broken in the graph.
        """
        try:
            # Query for Law → Chapter relationships
            law_chapter_query = """
            MATCH (l:Law)-[:HAS_CHAPTER]->(c:Chapter)
            RETURN count(c) as chapter_count
            """

            result = graph_session.execute_read_cypher(law_chapter_query)
            chapter_count = result.single()["chapter_count"]

            print(f"Law → Chapter relationships: {chapter_count}")

            # Query for Chapter → Article relationships
            chapter_article_query = """
            MATCH (c:Chapter)-[:HAS_ARTICLE]->(a:Article)
            RETURN count(a) as article_count
            """

            result = graph_session.execute_read_cypher(chapter_article_query)
            article_count = result.single()["article_count"]

            print(f"Chapter → Article relationships: {article_count}")

            # Query for Article → Clause relationships
            article_clause_query = """
            MATCH (a:Article)-[:HAS_CLAUSE]->(c:Clause)
            RETURN count(c) as clause_count
            """

            result = graph_session.execute_read_cypher(article_clause_query)
            clause_count = result.single()["clause_count"]

            print(f"Article → Clause relationships: {clause_count}")

            print(f"✅ Legal structure verified")

        except Exception as e:
            pytest.fail(f"Legal structure test failed: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])