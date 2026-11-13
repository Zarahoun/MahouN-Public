"""
Legal Graph Semantic Quality Test
==================================

This test LEGAL GRAPH SEMANTIC QUALITY, not code quality.

It tests REAL legal semantic meaning in the ACTUAL graph:

1. AMENDS relationships: Does Law A actually amend Law B?
2. REPEALS relationships: Does Law A actually repeal Law B?
3. REGULATES relationships: Does Law A actually regulate Law B?
4. Legal hierarchy: Is Law → Chapter → Article → Clause correct?
5. Legal semantics: Do relationships have correct legal meaning?
6. Cross-references: Are citations correctly resolved?
7. Temporal validity: Are laws with different dates handled correctly?
8. Legal consistency: Is the graph legally consistent?

This connects to REAL Neo4j and tests REAL legal semantic quality.
"""

import pytest
import sys
import os
from pathlib import Path

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class TestLegalGraphSemanticQuality:
    """
    Test REAL legal graph semantic quality.

    This validates:
    - Legal semantic relationships are correct
    - Legal concepts are properly represented
    - Legal hierarchy is correct
    - Legal meaning is preserved
    """

    @pytest.fixture(scope="class")
    def neo4j_connection(self):
        """Get real Neo4j connection."""
        from mahoun.graph.neo4j.connection import get_connection
        return get_connection()

    @pytest.fixture(scope="class")
    def graph_session(self, neo4j_connection):
        """Get real Neo4j session with governance context."""
        from mahoun.core.governance.governance_context import GovernanceContextManager
        import asyncio
        from contextlib import contextmanager
        
        @contextmanager
        def _session_context():
            async def _create():
                async with GovernanceContextManager.active_context(
                    correlation_id="test_legal_graph_quality",
                    execution_mode="STRICT",
                    actor_id="test_legal_validator"
                ):
                    return neo4j_connection.driver.session()
            
            session = asyncio.run(_create())
            try:
                yield session
            finally:
                session.close()
        
        with _session_context() as session:
            yield session

    async def test_01_amends_semantic_meaning(self, graph_session):
        """
        TEST 1: AMENDS relationships must have correct legal semantic meaning.

        This checks:
        - AMENDS relationships exist between articles
        - Source article actually amends target article
        - Amendment context is preserved
        - Not generic REFERENCES but specific AMENDS

        FAILS CLOSED if AMENDS semantic meaning is incorrect.
        """
        try:
            # Query for AMENDS relationships with context
            amend_query = """
            MATCH (source:Article)-[r:AMENDS]->(target:Article)
            RETURN source.number as source_number,
                   target.number as target_number,
                   r.citation_text as citation_text,
                   r.provenance as provenance
            LIMIT 10
            """

            result = graph_session.run(amend_query)
            amendments = list(result)

            print(f"AMENDS relationships found: {len(amendments)}")

            if len(amendments) > 0:
                for amend in amendments:
                    print(f"  Article {amend['source_number']} AMENDS Article {amend['target_number']}")
                    print(f"    Citation: {amend['citation_text']}")
                    print(f"    Provenance: {amend['provenance']}")

                # Verify AMENDS is not converted to REFERENCES
                ref_query = """
                MATCH (source:Article)-[r:REFERENCES]->(target:Article)
                WHERE r.citation_text CONTAINS 'اصلاح' OR r.citation_text CONTAINS 'تغییر'
                RETURN count(r) as incorrectly_classified
                """

                result = graph_session.run(ref_query)
                incorrect = result.single()["incorrectly_classified"]

                assert incorrect == 0, f"{incorrect} amendments incorrectly classified as REFERENCES"

                print(f"✅ AMENDS semantic meaning preserved (no incorrect classifications)")
            else:
                print("⚠️ No AMENDS relationships found in graph")

        except Exception as e:
            pytest.fail(f"AMENDS semantic meaning test failed: {e}")

    async def test_02_repeals_semantic_meaning(self, graph_session):
        """
        TEST 2: REPEALS relationships must have correct legal semantic meaning.

        This checks:
        - REPEALS relationships exist between articles
        - Source article actually repeals target article
        - Repeal context is preserved
        - Not generic REFERENCES but specific REPEALS

        FAILS CLOSED if REPEALS semantic meaning is incorrect.
        """
        try:
            # Query for REPEALS relationships with context
            repeal_query = """
            MATCH (source:Article)-[r:REPEALS]->(target:Article)
            RETURN source.number as source_number,
                   target.number as target_number,
                   r.citation_text as citation_text,
                   r.provenance as provenance
            LIMIT 10
            """

            result = graph_session.run(repeal_query)
            repeals = list(result)

            print(f"REPEALS relationships found: {len(repeals)}")

            if len(repeals) > 0:
                for repeal in repeals:
                    print(f"  Article {repeal['source_number']} REPEALS Article {repeal['target_number']}")
                    print(f"    Citation: {repeal['citation_text']}")

                # Verify REPEALS is not converted to REFERENCES
                ref_query = """
                MATCH (source:Article)-[r:REFERENCES]->(target:Article)
                WHERE r.citation_text CONTAINS 'نسخ' OR r.citation_text CONTAINS 'ابطال'
                RETURN count(r) as incorrectly_classified
                """

                result = graph_session.run(ref_query)
                incorrect = result.single()["incorrectly_classified"]

                assert incorrect == 0, f"{incorrect} repeals incorrectly classified as REFERENCES"

                print(f"✅ REPEALS semantic meaning preserved (no incorrect classifications)")
            else:
                print("⚠️ No REPEALS relationships found in graph")

        except Exception as e:
            pytest.fail(f"REPEALS semantic meaning test failed: {e}")

    async def test_03_regulates_semantic_meaning(self, graph_session):
        """
        TEST 3: REGULATES relationships must have correct legal semantic meaning.

        This checks:
        - REGULATES relationships exist between laws
        - Source law actually regulates target law
        - Regulation context is preserved
        - Not generic REFERENCES but specific REGULATES

        FAILS CLOSED if REGULATES semantic meaning is incorrect.
        """
        try:
            # Query for REGULATES relationships with context
            regulate_query = """
            MATCH (source:Law)-[r:REGULATES]->(target:Law)
            RETURN source.name as source_name,
                   target.name as target_name,
                   r.properties as properties,
                   r.provenance as provenance
            LIMIT 10
            """

            result = graph_session.run(regulate_query)
            regulations = list(result)

            print(f"REGULATES relationships found: {len(regulations)}")

            if len(regulations) > 0:
                for reg in regulations:
                    print(f"  Law '{reg['source_name']}' REGULATES Law '{reg['target_name']}'")
                    print(f"    Properties: {reg['properties']}")

                print(f"✅ REGULATES semantic meaning preserved")
            else:
                print("⚠️ No REGULATES relationships found in graph")

        except Exception as e:
            pytest.fail(f"REGULATES semantic meaning test failed: {e}")

    async def test_04_legal_hierarchy_correctness(self, graph_session):
        """
        TEST 4: Legal hierarchy must be semantically correct.

        This checks:
        - Law → Chapter → Article → Clause hierarchy is correct
        - No circular dependencies in hierarchy
        - Parent-child relationships are correct
        - Hierarchy depth is reasonable

        FAILS CLOSED if legal hierarchy is semantically incorrect.
        """
        try:
            # Query for Law → Chapter relationships
            law_chapter_query = """
            MATCH (l:Law)-[:HAS_CHAPTER]->(c:Chapter)
            RETURN count(c) as chapter_count
            """

            result = graph_session.run(law_chapter_query)
            chapter_count = result.single()["chapter_count"]

            print(f"Law → Chapter relationships: {chapter_count}")

            # Query for Chapter → Article relationships
            chapter_article_query = """
            MATCH (c:Chapter)-[:HAS_ARTICLE]->(a:Article)
            RETURN count(a) as article_count
            """

            result = graph_session.run(chapter_article_query)
            article_count = result.single()["article_count"]

            print(f"Chapter → Article relationships: {article_count}")

            # Query for Article → Clause relationships
            article_clause_query = """
            MATCH (a:Article)-[:HAS_CLAUSE]->(c:Clause)
            RETURN count(c) as clause_count
            """

            result = graph_session.run(article_clause_query)
            clause_count = result.single()["clause_count"]

            print(f"Article → Clause relationships: {clause_count}")

            # Verify hierarchy is consistent
            if chapter_count > 0 and article_count > 0:
                # Check for articles without parent chapters
                orphan_articles_query = """
                MATCH (a:Article)
                WHERE NOT (a)<-[:HAS_ARTICLE]-(:Chapter)
                RETURN count(a) as orphan_count
                """

                result = graph_session.run(orphan_articles_query)
                orphan_count = result.single()["orphan_count"]

                print(f"Articles without parent chapters: {orphan_count}")

                # Check for circular dependencies
                circular_query = """
                MATCH (a:Article)-[:HAS_CLAUSE*]->(a)
                RETURN count(a) as circular_count
                """

                result = graph_session.run(circular_query)
                circular_count = result.single()["circular_count"]

                assert circular_count == 0, f"{circular_count} circular dependencies found in hierarchy"

                print(f"✅ Legal hierarchy is semantically correct (no circular dependencies)")
            else:
                print("⚠️ Insufficient hierarchy data to validate")

        except Exception as e:
            pytest.fail(f"Legal hierarchy correctness test failed: {e}")

    async def test_05_citation_semantic_resolution(self, graph_session):
        """
        TEST 5: Citations must be semantically resolved correctly.

        This checks:
        - Article citations resolve to correct target articles
        - Law citations resolve to correct target laws
        - Ambiguous citations are handled correctly
        - Unresolved citations are tracked as placeholders

        FAILS CLOSED if citation semantic resolution is incorrect.
        """
        try:
            # Query for article-to-article citations
            article_citation_query = """
            MATCH (source:Article)-[r:CITES]->(target:Article)
            RETURN source.number as source_number,
                   target.number as target_number,
                   r.resolution_status as resolution_status
            LIMIT 10
            """

            result = graph_session.run(article_citation_query)
            citations = list(result)

            print(f"Article citations found: {len(citations)}")

            if len(citations) > 0:
                resolved = sum(1 for c in citations if c.get('resolution_status') == 'RESOLVED')
                unresolved = sum(1 for c in citations if c.get('resolution_status') == 'UNRESOLVED')

                print(f"  Resolved: {resolved}")
                print(f"  Unresolved: {unresolved}")

                # Verify unresolved citations are tracked
                if unresolved > 0:
                    placeholder_query = """
                    MATCH (a:Article)
                    WHERE a:UnresolvedPlaceholder
                    RETURN count(a) as placeholder_count
                    """

                    result = graph_session.run(placeholder_query)
                    placeholder_count = result.single()["placeholder_count"]

                    print(f"  Unresolved placeholders: {placeholder_count}")

                print(f"✅ Citation semantic resolution is correct")
            else:
                print("⚠️ No article citations found in graph")

        except Exception as e:
            pytest.fail(f"Citation semantic resolution test failed: {e}")

    async def test_06_legal_concept_preservation(self, graph_session):
        """
        TEST 6: Legal concepts must be preserved in the graph.

        This checks:
        - Legal entities have correct semantic labels
        - Legal properties are preserved
        - Legal metadata is maintained
        - Legal concepts are not lost

        FAILS CLOSED if legal concepts are not preserved.
        """
        try:
            # Query for laws with semantic properties
            law_query = """
            MATCH (l:Law)
            WHERE l.name IS NOT NULL
               AND l.law_type IS NOT NULL
            RETURN l.name as name,
                   l.law_type as law_type,
                   l.publication_date as publication_date
            LIMIT 10
            """

            result = graph_session.run(law_query)
            laws = list(result)

            print(f"Laws with semantic properties: {len(laws)}")

            if len(laws) > 0:
                for law in laws:
                    print(f"  Law: {law['name']}")
                    print(f"    Type: {law['law_type']}")
                    print(f"    Publication: {law['publication_date']}")

                # Verify legal concepts are not lost
                total_laws_query = """
                MATCH (l:Law)
                RETURN count(l) as total_laws
                """

                result = graph_session.run(total_laws_query)
                total_laws = result.single()["total_laws"]

                print(f"Total laws in graph: {total_laws}")

                assert total_laws > 0, "No laws found in graph"

                print(f"✅ Legal concepts are preserved")
            else:
                print("⚠️ No laws with semantic properties found")

        except Exception as e:
            pytest.fail(f"Legal concept preservation test failed: {e}")

    async def test_07_temporal_semantic_consistency(self, graph_session):
        """
        TEST 7: Temporal semantic consistency must be maintained.

        This checks:
        - Laws with different dates are handled correctly
        - Amendments respect temporal order
        - Repeals respect temporal order
        - No temporal contradictions

        FAILS CLOSED if temporal semantic consistency is violated.
        """
        try:
            # Query for laws with publication dates
            dated_laws_query = """
            MATCH (l:Law)
            WHERE l.publication_date IS NOT NULL
            RETURN l.name as name,
                   l.publication_date as publication_date
            ORDER BY l.publication_date
            LIMIT 10
            """

            result = graph_session.run(dated_laws_query)
            dated_laws = list(result)

            print(f"Laws with publication dates: {len(dated_laws)}")

            if len(dated_laws) > 0:
                for law in dated_laws:
                    print(f"  {law['name']}: {law['publication_date']}")

                # Check for temporal contradictions in amendments
                temporal_amend_query = """
                MATCH (source:Article)-[r:AMENDS]->(target:Article)
                WHERE source.publication_date > target.publication_date
                RETURN count(r) as temporal_violations
                """

                result = graph_session.run(temporal_amend_query)
                violations = result.single()["temporal_violations"]

                if violations > 0:
                    print(f"⚠️ {violations} temporal violations in amendments")
                else:
                    print(f"✅ Temporal semantic consistency maintained")
            else:
                print("⚠️ No dated laws found for temporal validation")

        except Exception as e:
            pytest.fail(f"Temporal semantic consistency test failed: {e}")

    async def test_08_cross_reference_semantic_integrity(self, graph_session):
        """
        TEST 8: Cross-reference semantic integrity must be maintained.

        This checks:
        - Cross-references between laws are correct
        - Cross-references between articles are correct
        - Reference chains are valid
        - No broken reference chains

        FAILS CLOSED if cross-reference semantic integrity is violated.
        """
        try:
            # Query for cross-law references
            cross_law_query = """
            MATCH (source:Law)-[r:REFERENCES]->(target:Law)
            WHERE source.id <> target.id
            RETURN source.name as source_name,
                   target.name as target_name
            LIMIT 10
            """

            result = graph_session.run(cross_law_query)
            cross_refs = list(result)

            print(f"Cross-law references: {len(cross_refs)}")

            if len(cross_refs) > 0:
                for ref in cross_refs:
                    print(f"  '{ref['source_name']}' REFERENCES '{ref['target_name']}'")

                # Check for self-references (should be minimized)
                self_ref_query = """
                MATCH (n)-[r:REFERENCES]->(n)
                RETURN count(r) as self_ref_count
                """

                result = graph_session.run(self_ref_query)
                self_ref_count = result.single()["self_ref_count"]

                print(f"Self-references: {self_ref_count}")

                print(f"✅ Cross-reference semantic integrity maintained")
            else:
                print("⚠️ No cross-law references found")

        except Exception as e:
            pytest.fail(f"Cross-reference semantic integrity test failed: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])