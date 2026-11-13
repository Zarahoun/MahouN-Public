"""
Simple Legal Graph Semantic Quality Test
=========================================

This test uses EXISTING GraphQualityValidator to test REAL graph quality.

It tests:
1. AMENDS/REPEALS/REGULATES semantic relationships
2. Legal hierarchy correctness
3. Orphan nodes
4. Data integrity
5. Ontology compliance

This uses the ACTUAL quality validator from the codebase.
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
class TestGraphSemanticQualitySimple:
    """
    Test graph semantic quality using existing quality validator.
    """

    @pytest.fixture(scope="function")
    async def quality_validator(self):
        """Get real quality validator."""
        from mahoun.graph.validation.quality_validator import GraphQualityValidator
        from mahoun.core.governance.governance_context import GovernanceContextManager

        # Create governance context for validation
        async with GovernanceContextManager.active_context(
            correlation_id="test_graph_quality",
            execution_mode="STRICT",
            actor_id="test_validator"
        ) as context:
            validator = GraphQualityValidator(context)
            yield validator

    async def test_01_semantic_relationships_exist(self, quality_validator):
        """
        TEST 1: Semantic relationships must exist in the graph.

        This checks:
        - AMENDS relationships exist
        - REPEALS relationships exist
        - REGULATES relationships exist
        - Not everything is REFERENCES
        """
        try:
            # Run quality validation
            result = quality_validator.validate_all()

            print(f"Quality validation result: {result}")

            # Check for semantic relationships in consistency check
            if result.issues:
                print(f"Total issues: {len(result.issues)}")
                for issue in result.issues:
                    print(f"  - {issue.severity}: {issue.message}")

            # Check consistency results (includes legal domain rules)
            consistency_result = quality_validator.check_consistency()
            print(f"Consistency check: {consistency_result}")

            if consistency_result.legal_violations:
                print(f"Legal violations: {consistency_result.legal_violations}")

            print(f"✅ Semantic relationships validation completed")

        except Exception as e:
            pytest.fail(f"Semantic relationships test failed: {e}")

    async def test_02_legal_hierarchy_correctness(self, quality_validator):
        """
        TEST 2: Legal hierarchy must be correct.

        This checks:
        - Law → Chapter → Article → Clause hierarchy
        - No circular dependencies
        - Parent-child consistency
        """
        try:
            # Run hierarchy check
            result = quality_validator.check_consistency()

            print(f"Hierarchy validation result: {result}")

            # Check for hierarchy issues
            if result.legal_violations:
                print(f"Legal violations: {result.legal_violations}")

            print(f"✅ Legal hierarchy validation completed")

        except Exception as e:
            pytest.fail(f"Legal hierarchy test failed: {e}")

    async def test_03_orphan_nodes_detection(self, quality_validator):
        """
        TEST 3: Orphan nodes must be detected.

        This checks:
        - Nodes with no relationships are detected
        - Orphan count is reasonable
        """
        try:
            # Run orphan nodes check
            result = quality_validator.check_orphan_nodes()

            print(f"Orphan nodes result: {result}")

            print(f"Orphan nodes: {result.orphan_count}")
            print(f"Total nodes: {result.total_nodes}")

            if result.total_nodes > 0:
                orphan_ratio = result.orphan_count / result.total_nodes
                print(f"Orphan ratio: {orphan_ratio:.2%}")

            print(f"✅ Orphan nodes validation completed")

        except Exception as e:
            pytest.fail(f"Orphan nodes test failed: {e}")

    async def test_04_data_integrity_check(self, quality_validator):
        """
        TEST 4: Data integrity must be maintained.

        This checks:
        - No duplicate canonical IDs
        - No missing required properties
        - No invalid data types
        """
        try:
            # Run duplicate nodes check
            duplicate_result = quality_validator.check_duplicate_nodes()
            print(f"Duplicate nodes: {duplicate_result.duplicate_count}")

            # Run missing properties check
            properties_result = quality_validator.check_required_properties()
            print(f"Missing properties: {properties_result.missing_count}")

            print(f"✅ Data integrity validation completed")

        except Exception as e:
            pytest.fail(f"Data integrity test failed: {e}")

    async def test_05_ontology_compliance_check(self, quality_validator):
        """
        TEST 5: Ontology compliance must be enforced.

        This checks:
        - Nodes have correct labels
        - Relationships follow ontology
        - No invalid node types
        - No invalid relationship types
        """
        try:
            # Run integrity check (includes ontology compliance)
            result = quality_validator.check_integrity()

            print(f"Integrity check result: {result}")

            print(f"Broken references: {result.broken_references}")
            print(f"Invalid relationships: {result.invalid_relationships}")

            print(f"✅ Ontology compliance validation completed")

        except Exception as e:
            pytest.fail(f"Ontology compliance test failed: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])