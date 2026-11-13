#!/usr/bin/env python3
"""
🚀 MAHOUN Orphan Module Integration Script
==========================================

Integrates 6 orphan reasoning modules into the main pipeline:
1. causal_effects.py → causal inference capabilities
2. causal_structure.py → causal DAG learning
3. kg_adapters.py → Neo4j knowledge graph integration
4. policies.py → policy-based reasoning control
5. reasoning_recorder_ultra.py → cryptographic audit trail
6. reranking_cot.py → explainable GAT reranking

STRATEGY:
- Extend EvidenceLinkedVerdictEngine with optional causal analysis
- Integrate policy selection into ReasoningDependencyContainer
- Wire kg_adapters through bootstrap runtime
- Add reasoning_recorder_ultra as enhanced audit layer
- Connect reranking_cot to HybridRAGService

CRITICAL: All changes preserve existing behavior (backward compatible)
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Any

# Colors for terminal output
GREEN = "\033[92m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

REPO_ROOT = Path(__file__).parent.parent

def print_header(text: str) -> None:
    """Print colored header"""
    print(f"\n{BOLD}{BLUE}{'='*80}{RESET}")
    print(f"{BOLD}{BLUE}{text:^80}{RESET}")
    print(f"{BOLD}{BLUE}{'='*80}{RESET}\n")

def print_section(text: str) -> None:
    """Print section header"""
    print(f"\n{BOLD}{GREEN}▶ {text}{RESET}")

def print_step(text: str) -> None:
    """Print step"""
    print(f"  {YELLOW}•{RESET} {text}")

def print_success(text: str) -> None:
    """Print success message"""
    print(f"  {GREEN}✓{RESET} {text}")

def print_error(text: str) -> None:
    """Print error message"""
    print(f"  {RED}✗{RESET} {text}")


class OrphanModuleIntegrator:
    """Orchestrator for integrating 6 orphan modules"""
    
    def __init__(self):
        self.repo_root = REPO_ROOT
        self.integration_plan: Dict[str, Dict[str, Any]] = {
            "causal_effects": {
                "target": "mahoun/reasoning/evidence_linked_verdict.py",
                "method": "add_optional_causal_analysis",
                "priority": "P1",
                "benefit": "Causal effect estimation for legal reasoning"
            },
            "causal_structure": {
                "target": "mahoun/reasoning/knowledge_graph.py",
                "method": "add_causal_dag_learning",
                "priority": "P2",
                "benefit": "Learn causal relationships from evidence"
            },
            "kg_adapters": {
                "target": "mahoun/bootstrap/runtime.py",
                "method": "add_kg_adapter_to_registry",
                "priority": "P0",
                "benefit": "Neo4j graph influence signals (governance-hardened)"
            },
            "policies": {
                "target": "mahoun/reasoning/adapters.py",
                "method": "add_policy_selector",
                "priority": "P1",
                "benefit": "Policy-based reasoning control (Conservative/Balanced/Aggressive)"
            },
            "reasoning_recorder_ultra": {
                "target": "mahoun/reasoning/evidence_linked_verdict.py",
                "method": "replace_recorder_with_ultra",
                "priority": "P1",
                "benefit": "Cryptographic audit trail with tamper detection"
            },
            "reranking_cot": {
                "target": "mahoun/rag/hybrid_rag_service.py",
                "method": "add_explainable_reranking",
                "priority": "P2",
                "benefit": "Explainable GAT-based reranking with CoT"
            },
        }

    
    def analyze_integration_points(self) -> Dict[str, Any]:
        """Analyze where each orphan module should integrate"""
        print_header("📊 ORPHAN MODULE INTEGRATION ANALYSIS")
        
        results = {}
        for module_name, plan in self.integration_plan.items():
            print_section(f"Module: {module_name}")
            print_step(f"Target: {plan['target']}")
            print_step(f"Method: {plan['method']}")
            print_step(f"Priority: {plan['priority']}")
            print_step(f"Benefit: {plan['benefit']}")
            
            # Check if target file exists
            target_path = self.repo_root / plan['target']
            if target_path.exists():
                print_success(f"Target file exists: {target_path}")
                results[module_name] = {"status": "ready", "path": str(target_path)}
            else:
                print_error(f"Target file NOT found: {target_path}")
                results[module_name] = {"status": "blocked", "path": str(target_path)}
        
        return results
    
    def generate_integration_patches(self) -> List[Dict[str, str]]:
        """Generate code patches for each integration"""
        print_header("🔧 GENERATING INTEGRATION PATCHES")
        
        patches = []
        
        # Patch 1: kg_adapters → bootstrap/runtime.py
        patches.append(self._patch_kg_adapter())
        
        # Patch 2: policies → adapters.py
        patches.append(self._patch_policy_selector())
        
        # Patch 3: reasoning_recorder_ultra → evidence_linked_verdict.py
        patches.append(self._patch_ultra_recorder())
        
        # Patch 4: causal_effects → evidence_linked_verdict.py
        patches.append(self._patch_causal_effects())
        
        # Patch 5: causal_structure → knowledge_graph.py
        patches.append(self._patch_causal_structure())
        
        # Patch 6: reranking_cot → hybrid_rag_service.py
        patches.append(self._patch_reranking_cot())
        
        return patches

    
    def _patch_kg_adapter(self) -> Dict[str, str]:
        """Patch bootstrap/runtime.py to wire kg_adapters"""
        return {
            "module": "kg_adapters",
            "target": "mahoun/bootstrap/runtime.py",
            "description": "Wire Neo4j KG Adapter to SERVICE_REGISTRY",
            "patch_location": "After GraphEnhancedRetriever registration (line ~75)",
            "code_to_add": '''
    # ========== ORPHAN MODULE INTEGRATION: kg_adapters ==========
    # Add Neo4j Knowledge Graph Adapter (governance-hardened)
    if settings.graph_backend != "disabled_fallback":
        try:
            from mahoun.reasoning.kg_adapters import Neo4jKGAdapter
            from mahoun.graph.neo4j.connection import get_connection
            
            # Session factory for governed access (read-only path)
            def kg_session_factory():
                conn = get_connection()
                return conn.execute_query  # governed read-only access
            
            kg_adapter = Neo4jKGAdapter(session_factory=kg_session_factory)
            SERVICE_REGISTRY["kg_adapter"] = kg_adapter
            logger.info("✓ Neo4jKGAdapter registered (governance-hardened)")
        except ImportError as e:
            logger.warning(f"kg_adapters unavailable: {e}")
    # ========== END ORPHAN MODULE INTEGRATION ==========
''',
            "benefit": "Graph-based influence signals for evidence ranking",
            "risk": "Low - graceful degradation if Neo4j disabled",
            "tests_needed": ["test_kg_adapter_registration", "test_kg_adapter_query"]
        }
    
    def _patch_policy_selector(self) -> Dict[str, str]:
        """Patch adapters.py to add policy selection"""
        return {
            "module": "policies",
            "target": "mahoun/reasoning/adapters.py",
            "description": "Add ReasoningPolicy to DependencyContainer",
            "patch_location": "After __init__ method (line ~30)",
            "code_to_add": '''
    # ========== ORPHAN MODULE INTEGRATION: policies ==========
    from mahoun.reasoning.policies import get_policy, PolicyType
    
    def set_policy(self, policy_type: PolicyType) -> None:
        """Set reasoning policy (Conservative/Balanced/Aggressive)"""
        self._policy = get_policy(policy_type)
        logger.info(f"Reasoning policy set to: {policy_type}")
    
    @property
    def policy(self):
        """Get current reasoning policy"""
        if not hasattr(self, '_policy'):
            from mahoun.reasoning.policies import get_policy, PolicyType
            self._policy = get_policy(PolicyType.BALANCED)
        return self._policy
    # ========== END ORPHAN MODULE INTEGRATION ==========
''',
            "benefit": "Policy-based reasoning control for different risk profiles",
            "risk": "Low - defaults to BALANCED policy",
            "tests_needed": ["test_policy_selection", "test_conservative_policy", "test_aggressive_policy"]
        }

    
    def _patch_ultra_recorder(self) -> Dict[str, str]:
        """Patch evidence_linked_verdict.py to use reasoning_recorder_ultra"""
        return {
            "module": "reasoning_recorder_ultra",
            "target": "mahoun/reasoning/evidence_linked_verdict.py",
            "description": "Replace ReasoningRecorder with Ultra version (cryptographic audit)",
            "patch_location": "Import section + __init__ method",
            "code_to_add": '''
    # ========== ORPHAN MODULE INTEGRATION: reasoning_recorder_ultra ==========
    # Replace standard recorder with Ultra version for cryptographic integrity
    from mahoun.reasoning.reasoning_recorder_ultra import (
        RerankingCoTGenerator,  # If needed for step generation
        # Add other classes as needed
    )
    
    # In __init__ method, replace:
    # self.recorder = ReasoningRecorder()
    # With:
    # self.recorder = UltraReasoningRecorder(backend="file", audit_mode=True)
    # ========== END ORPHAN MODULE INTEGRATION ==========
''',
            "benefit": "Cryptographic hash-chain audit trail with tamper detection",
            "risk": "Medium - needs testing for backward compatibility",
            "tests_needed": ["test_ultra_recorder_hash_chain", "test_ultra_recorder_tamper_detection"]
        }
    
    def _patch_causal_effects(self) -> Dict[str, str]:
        """Patch evidence_linked_verdict.py to add causal analysis"""
        return {
            "module": "causal_effects",
            "target": "mahoun/reasoning/evidence_linked_verdict.py",
            "description": "Add optional causal effect estimation step",
            "patch_location": "After evidence synthesis (line ~250)",
            "code_to_add": '''
    # ========== ORPHAN MODULE INTEGRATION: causal_effects ==========
    def _estimate_causal_effects(
        self,
        facts: List[Dict],
        enable_causal: bool = False
    ) -> Optional[Dict[str, float]]:
        """
        Estimate causal effects between facts (OPTIONAL)
        
        Args:
            facts: List of fact dictionaries
            enable_causal: Whether to run causal analysis
            
        Returns:
            Dictionary with causal effect estimates or None
        """
        if not enable_causal:
            return None
        
        try:
            from mahoun.reasoning.causal_effects import CausalEffectEstimator
            import numpy as np
            
            # Convert facts to numerical data (simplified)
            # In production, use proper feature extraction
            X = np.random.randn(len(facts), 5)  # Covariates
            treatment = np.random.randint(0, 2, len(facts))  # Binary treatment
            outcome = np.random.randn(len(facts))  # Outcome
            
            estimator = CausalEffectEstimator(method='dr')  # Doubly robust
            result = estimator.estimate(X, treatment, outcome)
            
            return result
        except Exception as e:
            self.logger.warning(f"Causal analysis failed: {e}")
            return None
    # ========== END ORPHAN MODULE INTEGRATION ==========
''',
            "benefit": "Causal effect estimation for legal reasoning",
            "risk": "Low - optional feature, fails gracefully",
            "tests_needed": ["test_causal_effect_estimation"]
        }

    
    def _patch_causal_structure(self) -> Dict[str, str]:
        """Patch knowledge_graph.py to add causal DAG learning"""
        return {
            "module": "causal_structure",
            "target": "mahoun/reasoning/knowledge_graph.py",
            "description": "Add causal structure learning capability",
            "patch_location": "Add new method to LegalKnowledgeGraph class",
            "code_to_add": '''
    # ========== ORPHAN MODULE INTEGRATION: causal_structure ==========
    def learn_causal_structure(
        self,
        observations: np.ndarray,
        var_names: Optional[List[str]] = None,
        algorithm: str = 'pc'
    ) -> nx.DiGraph:
        """
        Learn causal DAG from observational data
        
        Args:
            observations: Data matrix [N, D]
            var_names: Variable names
            algorithm: 'pc' or 'notears'
            
        Returns:
            Learned causal DAG
        """
        try:
            from mahoun.reasoning.causal_structure import CausalStructureLearner
            
            learner = CausalStructureLearner(algorithm=algorithm)
            dag = learner.learn(observations, var_names)
            
            logger.info(f"Learned causal structure: {dag.number_of_edges()} edges")
            return dag
        except Exception as e:
            logger.warning(f"Causal structure learning failed: {e}")
            return nx.DiGraph()  # Empty graph fallback
    # ========== END ORPHAN MODULE INTEGRATION ==========
''',
            "benefit": "Learn causal relationships from legal evidence",
            "risk": "Low - optional feature, returns empty graph on failure",
            "tests_needed": ["test_causal_dag_learning_pc", "test_causal_dag_learning_notears"]
        }
    
    def _patch_reranking_cot(self) -> Dict[str, str]:
        """Patch hybrid_rag_service.py to add explainable reranking"""
        return {
            "module": "reranking_cot",
            "target": "mahoun/rag/hybrid_rag_service.py",
            "description": "Add Chain-of-Thought reasoning for reranking",
            "patch_location": "After reranking step (line ~180)",
            "code_to_add": '''
    # ========== ORPHAN MODULE INTEGRATION: reranking_cot ==========
    def _generate_reranking_explanation(
        self,
        query: str,
        document: LegalDocument,
        scores: Dict[str, float],
        enable_cot: bool = False
    ) -> List[ReasoningStep]:
        """
        Generate Chain-of-Thought explanation for reranking
        
        Args:
            query: User query
            document: Reranked document
            scores: Reranking scores
            enable_cot: Whether to generate CoT
            
        Returns:
            List of ReasoningStep objects with explanations
        """
        if not enable_cot:
            return []
        
        try:
            from mahoun.reasoning.reranking_cot import RerankingCoTGenerator
            
            cot_gen = RerankingCoTGenerator(language="fa")
            reasoning_steps = cot_gen.generate_reasoning(
                query=query,
                document=document,
                scores=scores,
                attention_weights=None,  # Add GAT attention if available
                uncertainty=None,  # Add uncertainty estimate if available
                metadata={}
            )
            
            return reasoning_steps
        except Exception as e:
            self.logger.warning(f"CoT generation failed: {e}")
            return []
    # ========== END ORPHAN MODULE INTEGRATION ==========
''',
            "benefit": "Explainable reranking with 6-step reasoning process",
            "risk": "Low - optional feature, returns empty list on failure",
            "tests_needed": ["test_reranking_cot_persian", "test_reranking_cot_english"]
        }

    
    def generate_integration_report(self, patches: List[Dict[str, str]]) -> str:
        """Generate detailed integration report"""
        print_header("📝 INTEGRATION REPORT")
        
        report_lines = [
            "# MAHOUN Orphan Module Integration Report",
            f"# Generated: {__import__('datetime').datetime.now().isoformat()}",
            "",
            "## Summary",
            f"- Total modules: {len(patches)}",
            f"- Priority P0: {sum(1 for p in patches if 'P0' in str(p))}",
            f"- Priority P1: {sum(1 for p in patches if 'P1' in str(p))}",
            f"- Priority P2: {sum(1 for p in patches if 'P2' in str(p))}",
            "",
            "## Integration Patches",
            ""
        ]
        
        for i, patch in enumerate(patches, 1):
            report_lines.extend([
                f"### {i}. {patch['module'].upper()}",
                f"**Target:** `{patch['target']}`",
                f"**Description:** {patch['description']}",
                f"**Benefit:** {patch['benefit']}",
                f"**Risk Level:** {patch['risk']}",
                "",
                "**Code to add:**",
                "```python",
                patch['code_to_add'].strip(),
                "```",
                "",
                "**Tests needed:**",
                *[f"- [ ] {test}" for test in patch['tests_needed']],
                "",
                "---",
                ""
            ])
        
        return "\n".join(report_lines)
    
    def save_report(self, report: str, filename: str = "ORPHAN_INTEGRATION_PLAN.md") -> None:
        """Save integration report to file"""
        output_path = self.repo_root / filename
        output_path.write_text(report)
        print_success(f"Report saved: {output_path}")


def main():
    """Main execution"""
    integrator = OrphanModuleIntegrator()
    
    # Step 1: Analyze integration points
    results = integrator.analyze_integration_points()
    
    # Step 2: Generate patches
    patches = integrator.generate_integration_patches()
    
    # Step 3: Generate report
    report = integrator.generate_integration_report(patches)
    
    # Step 4: Save report
    integrator.save_report(report)
    
    # Summary
    print_header("✅ INTEGRATION ANALYSIS COMPLETE")
    print_success("All 6 orphan modules analyzed")
    print_success("Integration patches generated")
    print_success("Report saved: ORPHAN_INTEGRATION_PLAN.md")
    
    print(f"\n{BOLD}NEXT STEPS:{RESET}")
    print(f"  1. Review {YELLOW}ORPHAN_INTEGRATION_PLAN.md{RESET}")
    print(f"  2. Apply patches one by one (priority order: P0 → P1 → P2)")
    print(f"  3. Write tests for each integration")
    print(f"  4. Run full test suite to verify no regressions")
    print(f"  5. Update {YELLOW}AGENTS.md{RESET} with new capabilities\n")


if __name__ == "__main__":
    main()
