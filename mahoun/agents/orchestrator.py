"""
Ultra Orchestrator - DAG-based Workflow Execution
=================================================
Orchestrator پیشرفته با قابلیت اجرای DAG

Features:
- DAG-based Workflow (گراف جهت‌دار بدون چرخه)
- Parallel Execution با Dependency Resolution
- Checkpoint/Resume Support
- Real-time Progress Tracking
- Workflow Visualization
- Error Recovery & Rollback
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set
from collections import defaultdict

try:
    from config.runtime import RuntimeConfig
    from mahoun.llm.ultra_loader import UltraModelLoader
    from mahoun.llm.router import ExpertRouter
    from mahoun.llm.bandit import BanditController
    from mahoun.llm.uncertainty import UncertaintyModel
    from mahoun.llm.ultra_engine import UltraLLMEngine
    from mahoun.llm.fallback import AVAILABLE_MODELS, MODEL_CAPS
except ImportError:
    pass

from .base_agent import UltraBaseAgent, AgentResult, AgentConfig
from mahoun.switchboard import switchboard

logger = logging.getLogger(__name__)


# ============================================================================
# Enums and Data Classes
# ============================================================================


class NodeStatus(str, Enum):
    """Workflow node execution status"""

    PENDING = "pending"
    READY = "ready"  # Dependencies satisfied
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class WorkflowStatus(str, Enum):
    """Overall workflow status"""

    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class WorkflowNode:
    """
    A node in the workflow DAG.

    Represents a single agent execution step.
    """

    id: str
    agent_name: str
    config: Dict[str, Any] = field(default_factory=dict)

    # Dependencies (node IDs that must complete first)
    dependencies: List[str] = field(default_factory=list)

    # Execution settings
    required: bool = True  # If False, workflow continues on failure
    timeout: float = 60.0  # seconds
    retries: int = 0  # Additional retries beyond agent's own

    # Runtime state
    status: NodeStatus = NodeStatus.PENDING
    result: Optional[AgentResult] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error: Optional[str] = None


@dataclass
class WorkflowDAG:
    """
    Directed Acyclic Graph for workflow definition.

    Usage:
        dag = WorkflowDAG(name="my_workflow")
        dag.add_node(WorkflowNode(id="parse", agent_name="doc_parser"))
        dag.add_node(WorkflowNode(id="analyze", agent_name="dispute", dependencies=["parse"]))
        dag.add_node(WorkflowNode(id="report", agent_name="narrative", dependencies=["analyze"]))
    """

    name: str
    nodes: Dict[str, WorkflowNode] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_node(self, node: WorkflowNode):
        """Add a node to the DAG"""
        if node.id in self.nodes:
            raise ValueError(f"Node '{node.id}' already exists")
        self.nodes[node.id] = node

    def validate(self) -> List[str]:
        """
        Validate DAG structure.

        Returns list of validation errors (empty if valid).
        """
        errors: List[Any] = []
        # Check for missing dependencies
        for node_id, node in self.nodes.items():
            for dep_id in node.dependencies:
                if dep_id not in self.nodes:
                    errors.append(
                        f"Node '{node_id}' depends on unknown node '{dep_id}'"
                    )

        # Check for cycles using DFS
        visited = set()
        rec_stack = set()

        def has_cycle(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)

            for dep_id in self.nodes[node_id].dependencies:
                # Skip if dependency doesn't exist (already caught above)
                if dep_id not in self.nodes:
                    continue
                if dep_id not in visited:
                    if has_cycle(dep_id):
                        return True
                elif dep_id in rec_stack:
                    return True

            rec_stack.remove(node_id)
            return False

        for node_id in self.nodes:
            if node_id not in visited:
                if has_cycle(node_id):
                    errors.append(f"Cycle detected involving node '{node_id}'")
                    break

        return errors

    def get_execution_order(self) -> List[List[str]]:
        """
        Get execution order as levels (nodes in same level can run in parallel).

        Returns:
            List of levels, each level is a list of node IDs
        """
        # Calculate in-degree for each node
        in_degree = {node_id: 0 for node_id in self.nodes}
        for node in self.nodes.values():
            for dep_id in node.dependencies:
                if dep_id in in_degree:
                    in_degree[node.id] = in_degree.get(node.id, 0)

        # Recalculate based on dependencies
        in_degree = {
            node_id: len(node.dependencies) for node_id, node in self.nodes.items()
        }

        levels: List[Any] = []
        remaining = set(self.nodes.keys())

        while remaining:
            # Find nodes with no remaining dependencies
            ready = [
                node_id
                for node_id in remaining
                if all(dep not in remaining for dep in self.nodes[node_id].dependencies)
            ]

            if not ready:
                # Cycle detected or invalid state
                break

            levels.append(ready)
            remaining -= set(ready)

        return levels


@dataclass
class ExecutionContext:
    """Context passed between workflow nodes"""

    workflow_id: str
    initial_data: Dict[str, Any] = field(default_factory=dict)
    node_results: Dict[str, Any] = field(default_factory=dict)
    variables: Dict[str, Any] = field(default_factory=dict)

    def get_input_for_node(self, node: WorkflowNode) -> Dict[str, Any]:
        """Build input data for a node based on dependencies"""
        input_data = self.initial_data.copy()

        # Add results from dependencies
        for dep_id in node.dependencies:
            if dep_id in self.node_results:
                input_data[f"_{dep_id}_result"] = self.node_results[dep_id]

        # Add node-specific config
        input_data.update(node.config)

        # Add variables
        input_data.update(self.variables)

        return input_data


@dataclass
class WorkflowCheckpoint:
    """Checkpoint for workflow resume"""

    workflow_id: str
    dag_name: str
    timestamp: datetime
    completed_nodes: List[str]
    node_results: Dict[str, Any]
    context_variables: Dict[str, Any]


# ============================================================================
# Ultra Orchestrator
# ============================================================================


class UltraOrchestrator:
    """
    Enterprise-grade workflow orchestrator with DAG support.

    Features:
    - DAG-based execution with dependency resolution
    - Parallel execution of independent nodes
    - Checkpoint/Resume for long workflows
    - Real-time progress callbacks
    - Error recovery and rollback

    Usage:
        orchestrator = UltraOrchestrator()

        # Register agents
        orchestrator.register_agent("doc_parser", DocParserAgent())
        orchestrator.register_agent("dispute", DisputeAgent())

        # Define workflow
        dag = WorkflowDAG(name="analysis")
        dag.add_node(WorkflowNode(id="parse", agent_name="doc_parser"))
        dag.add_node(WorkflowNode(id="analyze", agent_name="dispute", dependencies=["parse"]))

        # Execute
        result = await orchestrator.execute_workflow(dag, {"text": "..."})
    """

    def __init__(self):
        self.agents: Dict[str, UltraBaseAgent] = {}
        self.workflows: Dict[str, Dict[str, Any]] = {}
        self.checkpoints: Dict[str, WorkflowCheckpoint] = {}

        # Integrity Guard
        self.integrity_threshold = 0.7
        self.enable_integrity_guard = True

        # Progress callbacks
        self._progress_callbacks: List[
            Callable[[str, str, float], Awaitable[None]]
        ] = []

        self.logger = logging.getLogger(f"{__name__}.UltraOrchestrator")
        self.logger.info("UltraOrchestrator initialized")

        # Initialize Aggressive LLM Engine
        try:
            self.runtime_config = RuntimeConfig.load()

            # Allow local provider or forced upgrade
            if self.runtime_config.llm.provider == "local":
                self.logger.info("Initializing Aggressive Ultra LLM Engine...")

                model_dir = self.runtime_config.llm.model_path

                # 1. Loader
                self.loader = UltraModelLoader(model_dir)

                # 2. Router
                self.router = ExpertRouter(MODEL_CAPS)

                # 3. Bandit
                self.bandit = BanditController(AVAILABLE_MODELS)

                # 4. Uncertainty
                self.uncertainty = UncertaintyModel()

                # 5. Engine
                self.llm_engine = UltraLLMEngine(
                    self.loader, self.router, self.bandit, self.uncertainty
                )
                self.logger.info("✅ Ultra LLM Engine Active")
            else:
                self.llm_engine = None
        except Exception as e:
            self.logger.warning(f"Could not initialize Ultra LLM Engine: {e}")
            self.llm_engine = None
            self.runtime_config = None

    async def ask(self, prompt: str) -> str:
        """
        Direct query to the Ultra LLM engine.

        Args:
            prompt: Input text

        Returns:
            Generated text
        """
        if not self.llm_engine:
            raise RuntimeError("Ultra LLM Engine is not active")

        text, confidence = await self.llm_engine.generate(prompt)
        return text

    # ========================================================================
    # Agent Management
    # ========================================================================

    def register_agent(self, name: str, agent: UltraBaseAgent):
        """Register an agent"""
        if name in self.agents:
            self.logger.warning(f"Overwriting agent '{name}'")
        self.agents[name] = agent
        self.logger.info(f"Registered agent: {name}")

    def unregister_agent(self, name: str):
        """Unregister an agent"""
        if name in self.agents:
            del self.agents[name]
            self.logger.info(f"Unregistered agent: {name}")

    def get_agent(self, name: str) -> Optional[UltraBaseAgent]:
        """Get agent by name"""
        return self.agents.get(name)

    # ========================================================================
    # Workflow Execution
    # ========================================================================

    async def execute_workflow(
        self,
        dag: WorkflowDAG,
        initial_data: Dict[str, Any],
        checkpoint: Optional[WorkflowCheckpoint] = None,
        max_parallel: int = 5,
    ) -> Dict[str, Any]:
        """
        Execute a workflow DAG.

        Args:
            dag: Workflow DAG definition
            initial_data: Initial input data
            checkpoint: Optional checkpoint to resume from
            max_parallel: Maximum parallel node executions

        Returns:
            Workflow result with all node results
        """
        # Validate DAG
        errors = dag.validate()
        if errors:
            return {
                "success": False,
                "error": f"Invalid DAG: {errors}",
                "workflow_id": None,
            }

        # Create workflow context
        workflow_id = str(uuid.uuid4())[:8]
        context = ExecutionContext(workflow_id=workflow_id, initial_data=initial_data)

        # Resume from checkpoint if provided
        if checkpoint:
            context.node_results = checkpoint.node_results
            context.variables = checkpoint.context_variables
            for node_id in checkpoint.completed_nodes:
                if node_id in dag.nodes:
                    dag.nodes[node_id].status = NodeStatus.COMPLETED

        self.logger.info(f"Starting workflow '{dag.name}' (ID: {workflow_id})")
        start_time = time.time()

        # Track workflow
        self.workflows[workflow_id] = {
            "dag": dag,
            "status": WorkflowStatus.RUNNING,
            "start_time": datetime.now().isoformat(),
            "context": context,
        }

        try:
            # Get execution levels
            levels = dag.get_execution_order()
            total_nodes = len(dag.nodes)
            completed_nodes = 0

            for level_idx, level in enumerate(levels):
                self.logger.info(
                    f"Executing level {level_idx + 1}/{len(levels)}: {level}"
                )

                # Filter out already completed nodes
                pending_nodes = [
                    node_id
                    for node_id in level
                    if dag.nodes[node_id].status != NodeStatus.COMPLETED
                ]

                if not pending_nodes:
                    completed_nodes += len(level)
                    continue

                # Execute nodes in parallel (with limit)
                semaphore = asyncio.Semaphore(max_parallel)

                async def execute_with_semaphore(node_id: str):
                    async with semaphore:
                        return await self._execute_node(dag.nodes[node_id], context)

                tasks = [execute_with_semaphore(node_id) for node_id in pending_nodes]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Process results
                for node_id, result in zip(pending_nodes, results):
                    node = dag.nodes[node_id]

                    if isinstance(result, Exception):
                        node.status = NodeStatus.FAILED
                        node.error = str(result)

                        if node.required:
                            raise result
                    else:
                        completed_nodes += 1

                    # Report progress
                    progress = completed_nodes / total_nodes
                    await self._report_progress(workflow_id, node_id, progress)

                # Create checkpoint after each level
                self._create_checkpoint(workflow_id, dag, context)

            # Workflow completed
            self.workflows[workflow_id]["status"] = WorkflowStatus.COMPLETED
            self.workflows[workflow_id]["end_time"] = datetime.now().isoformat()

            duration = time.time() - start_time
            self.logger.info(f"Workflow '{dag.name}' completed in {duration:.2f}s")

            return {
                "success": True,
                "workflow_id": workflow_id,
                "dag_name": dag.name,
                "duration_seconds": duration,
                "node_results": context.node_results,
                "final_data": self._build_final_data(dag, context),
            }

        except Exception as e:
            self.workflows[workflow_id]["status"] = WorkflowStatus.FAILED
            self.workflows[workflow_id]["error"] = str(e)
            self.logger.error(f"Workflow '{dag.name}' failed: {e}")

            return {
                "success": False,
                "workflow_id": workflow_id,
                "dag_name": dag.name,
                "error": str(e),
                "node_results": context.node_results,
                "checkpoint": self.checkpoints.get(workflow_id),
            }

    async def _execute_node(
        self, node: WorkflowNode, context: ExecutionContext
    ) -> AgentResult:
        """Execute a single workflow node"""
        node.status = NodeStatus.RUNNING
        node.start_time = datetime.now()

        # Get agent from primary registry or fallback to switchboard
        agent = self.agents.get(node.agent_name)
        if not agent:
            try:
                # Use Switchboard to transparently load Base or Ultra module via uniform interface
                agent_class_or_instance = switchboard.get_module(node.agent_name)
                # Lazy instantiation if class is returned
                agent = (
                    agent_class_or_instance()
                    if isinstance(agent_class_or_instance, type)
                    else agent_class_or_instance
                )
                self.agents[node.agent_name] = agent
                self.logger.info(
                    f"Loaded '{node.agent_name}' dynamically from Switchboard."
                )
            except (KeyError, Exception) as e:
                self.logger.warning(
                    f"Feature '{node.agent_name}' not found in Switchboard: {e}"
                )

        if not agent:
            node.status = NodeStatus.FAILED
            node.error = f"Agent '{node.agent_name}' not found"
            raise ValueError(node.error)

        # Build input
        input_data = context.get_input_for_node(node)

        self.logger.info(f"Executing node '{node.id}' with agent '{node.agent_name}'")

        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                agent.process(
                    input_data, correlation_id=f"{context.workflow_id}-{node.id}"
                ),
                timeout=node.timeout,
            )

            node.end_time = datetime.now()
            node.result = result

            if result.success:
                node.status = NodeStatus.COMPLETED
                context.node_results[node.id] = result.data
                self.logger.info(f"Node '{node.id}' completed successfully")

                # Integrity Guard: Validate text responses
                if self.enable_integrity_guard:
                    if isinstance(result.data, dict) and "answer" in result.data:
                        await self._validate_integrity(node, result, context)
            else:
                node.status = NodeStatus.FAILED
                node.error = result.error
                self.logger.warning(f"Node '{node.id}' failed: {result.error}")

                if node.required:
                    raise RuntimeError(
                        f"Required node '{node.id}' failed: {result.error}"
                    )

            return result

        except asyncio.TimeoutError:
            node.status = NodeStatus.FAILED
            node.error = f"Timeout after {node.timeout}s"
            node.end_time = datetime.now()

            if node.required:
                raise

            return AgentResult(success=False, error=node.error)

    async def _validate_integrity(
        self, node: WorkflowNode, result: AgentResult, context: ExecutionContext
    ):
        """Run Red-Teaming (Critic Agent) on the result"""
        critic = self.get_agent("critic")
        if not critic:
            # Try to create it via factory if not registered
            from .factory import AgentFactory

            try:
                critic = await AgentFactory.create_agent("critic")
                self.register_agent("critic", critic)
            except Exception as e:
                self.logger.warning(f"Could not initialize Critic Agent: {e}")
                return

        validation_input = {
            "query": context.initial_data.get("query", "No query provided"),
            "answer": result.data.get("answer", ""),
            "context": result.data.get("context", [])
            or context.initial_data.get("context", []),
        }

        self.logger.info(f"Running Integrity Guard for node '{node.id}'...")
        val_result = await critic.process(validation_input)

        if val_result.success:
            faithfulness = val_result.data.get("faithfulness_score", 1.0)
            result.data["integrity_report"] = val_result.data

            if faithfulness < self.integrity_threshold:
                self.logger.warning(
                    f"⚠️ INTEGRITY ALERT (node '{node.id}'): Faithfulness score {faithfulness} is below threshold!"
                )
                result.warnings.append(
                    f"Potential hallucination detected (Faithfulness: {faithfulness})"
                )

                # In strict mode, we could fail the node here
                # node.status = NodeStatus.FAILED
                # node.error = "Integrity check failed"

    def _build_final_data(
        self, dag: WorkflowDAG, context: ExecutionContext
    ) -> Dict[str, Any]:
        """Build final output from all node results"""
        final_data = context.initial_data.copy()

        # Add all node results
        for node_id, result in context.node_results.items():
            if isinstance(result, dict):
                final_data.update(result)
            final_data[f"_{node_id}"] = result

        return final_data

    # ========================================================================
    # Checkpoint Management
    # ========================================================================

    def _create_checkpoint(
        self, workflow_id: str, dag: WorkflowDAG, context: ExecutionContext
    ):
        """Create a checkpoint for the workflow"""
        completed = [
            node_id
            for node_id, node in dag.nodes.items()
            if node.status == NodeStatus.COMPLETED
        ]

        checkpoint = WorkflowCheckpoint(
            workflow_id=workflow_id,
            dag_name=dag.name,
            timestamp=datetime.now(),
            completed_nodes=completed,
            node_results=context.node_results.copy(),
            context_variables=context.variables.copy(),
        )

        self.checkpoints[workflow_id] = checkpoint

    def get_checkpoint(self, workflow_id: str) -> Optional[WorkflowCheckpoint]:
        """Get checkpoint for a workflow"""
        return self.checkpoints.get(workflow_id)

    # ========================================================================
    # Progress Tracking
    # ========================================================================

    def on_progress(self, callback: Callable[[str, str, float], Awaitable[None]]):
        """Register progress callback"""
        self._progress_callbacks.append(callback)

    async def _report_progress(self, workflow_id: str, node_id: str, progress: float):
        """Report progress to all callbacks"""
        for callback in self._progress_callbacks:
            try:
                await callback(workflow_id, node_id, progress)
            except Exception as e:
                self.logger.warning(f"Progress callback error: {e}")

    # ========================================================================
    # Status and Metrics
    # ========================================================================

    def get_workflow_status(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a workflow"""
        if workflow_id not in self.workflows:
            return None

        workflow = self.workflows[workflow_id]
        dag = workflow["dag"]

        node_statuses = {
            node_id: {
                "status": node.status.value,
                "agent": node.agent_name,
                "start_time": node.start_time.isoformat() if node.start_time else None,
                "end_time": node.end_time.isoformat() if node.end_time else None,
                "error": node.error,
            }
            for node_id, node in dag.nodes.items()
        }

        return {
            "workflow_id": workflow_id,
            "dag_name": dag.name,
            "status": workflow["status"].value,
            "start_time": workflow.get("start_time"),
            "end_time": workflow.get("end_time"),
            "error": workflow.get("error"),
            "nodes": node_statuses,
        }

    def get_all_agent_status(self) -> Dict[str, Any]:
        """Get status of all registered agents"""
        return {name: agent.get_status() for name, agent in self.agents.items()}

    # ========================================================================
    # Workflow Visualization
    # ========================================================================

    def visualize_dag(self, dag: WorkflowDAG, format: str = "ascii") -> str:
        """
        Generate visual representation of workflow DAG.

        Args:
            dag: WorkflowDAG to visualize
            format: Output format - "ascii", "mermaid", "dot", "json"

        Returns:
            String representation of the DAG
        """
        if format == "ascii":
            return self._visualize_ascii(dag)
        elif format == "mermaid":
            return self._visualize_mermaid(dag)
        elif format == "dot":
            return self._visualize_dot(dag)
        elif format == "json":
            return self._visualize_json(dag)
        else:
            raise ValueError(
                f"Unknown format: {format}. Use: ascii, mermaid, dot, json"
            )

    def _visualize_ascii(self, dag: WorkflowDAG) -> str:
        """Generate ASCII art visualization"""
        lines: List[Any] = []
        lines.append(f"╔══════════════════════════════════════════╗")
        lines.append(f"║  Workflow: {dag.name:<29} ║")
        lines.append(f"╠══════════════════════════════════════════╣")

        levels = dag.get_execution_order()

        for level_idx, level in enumerate(levels):
            # Level header
            lines.append(f"║  Level {level_idx + 1}:                                ║")

            for node_id in level:
                node = dag.nodes[node_id]
                status_icon = self._get_status_icon(node.status)
                deps = ", ".join(node.dependencies) if node.dependencies else "none"

                # Node info
                node_line = f"║    {status_icon} [{node_id}] → {node.agent_name}"
                lines.append(f"{node_line:<43}║")

                if node.dependencies:
                    dep_line = f"║       └─ deps: {deps}"
                    lines.append(f"{dep_line:<43}║")

            if level_idx < len(levels) - 1:
                lines.append(f"║         ↓                                 ║")

        lines.append(f"╚══════════════════════════════════════════╝")

        # Legend
        lines.append("")
        lines.append("Legend: ○ pending  ◐ running  ● completed  ✗ failed  ⊘ skipped")

        return "\n".join(lines)

    def _visualize_mermaid(self, dag: WorkflowDAG) -> str:
        """
        Generate Mermaid diagram syntax.

        Can be rendered at: https://mermaid.live/
        """
        lines = ["```mermaid", "flowchart TD"]
        lines.append(f"    subgraph {dag.name}")

        # Define nodes
        for node_id, node in dag.nodes.items():
            status_class = self._get_mermaid_class(node.status)
            label = f"{node_id}\\n({node.agent_name})"
            lines.append(f'    {node_id}["{label}"]:::{status_class}')

        lines.append("    end")
        lines.append("")

        # Define edges
        for node_id, node in dag.nodes.items():
            for dep_id in node.dependencies:
                lines.append(f"    {dep_id} --> {node_id}")

        # Style definitions
        lines.append("")
        lines.append("    classDef pending fill:#f9f9f9,stroke:#999")
        lines.append("    classDef running fill:#fff3cd,stroke:#ffc107")
        lines.append("    classDef completed fill:#d4edda,stroke:#28a745")
        lines.append("    classDef failed fill:#f8d7da,stroke:#dc3545")
        lines.append("    classDef skipped fill:#e2e3e5,stroke:#6c757d")
        lines.append("```")

        return "\n".join(lines)

    def _visualize_dot(self, dag: WorkflowDAG) -> str:
        """
        Generate Graphviz DOT format.

        Can be rendered with: dot -Tpng workflow.dot -o workflow.png
        """
        lines = [f'digraph "{dag.name}" {{']
        lines.append("    rankdir=TB;")
        lines.append("    node [shape=box, style=rounded];")
        lines.append("")

        # Define nodes with colors
        for node_id, node in dag.nodes.items():
            color = self._get_dot_color(node.status)
            label = f"{node_id}\\n{node.agent_name}"
            lines.append(
                f'    "{node_id}" [label="{label}", fillcolor="{color}", style="filled,rounded"];'
            )

        lines.append("")

        # Define edges
        for node_id, node in dag.nodes.items():
            for dep_id in node.dependencies:
                lines.append(f'    "{dep_id}" -> "{node_id}";')

        lines.append("}")

        return "\n".join(lines)

    def _visualize_json(self, dag: WorkflowDAG) -> str:
        """Generate JSON representation for web visualization"""
        import json

        nodes: List[Any] = []
        edges: List[Any] = []
        levels = dag.get_execution_order()
        level_map: Dict[str, Any] = {}
        for level_idx, level in enumerate(levels):
            for node_id in level:
                level_map[node_id] = level_idx

        for node_id, node in dag.nodes.items():
            nodes.append(
                {
                    "id": node_id,
                    "label": node_id,
                    "agent": node.agent_name,
                    "status": node.status.value,
                    "level": level_map.get(node_id, 0),
                    "required": node.required,
                    "timeout": node.timeout,
                    "start_time": node.start_time.isoformat()
                    if node.start_time
                    else None,
                    "end_time": node.end_time.isoformat() if node.end_time else None,
                    "error": node.error,
                }
            )

            for dep_id in node.dependencies:
                edges.append({"source": dep_id, "target": node_id})

        return json.dumps(
            {
                "name": dag.name,
                "nodes": nodes,
                "edges": edges,
                "levels": len(levels),
                "metadata": dag.metadata,
            },
            indent=2,
            ensure_ascii=False,
        )

    def _get_status_icon(self, status: NodeStatus) -> str:
        """Get ASCII icon for status"""
        icons = {
            NodeStatus.PENDING: "○",
            NodeStatus.READY: "◎",
            NodeStatus.RUNNING: "◐",
            NodeStatus.COMPLETED: "●",
            NodeStatus.FAILED: "✗",
            NodeStatus.SKIPPED: "⊘",
            NodeStatus.CANCELLED: "⊗",
        }
        return icons.get(status, "?")

    def _get_mermaid_class(self, status: NodeStatus) -> str:
        """Get Mermaid class for status"""
        classes = {
            NodeStatus.PENDING: "pending",
            NodeStatus.READY: "pending",
            NodeStatus.RUNNING: "running",
            NodeStatus.COMPLETED: "completed",
            NodeStatus.FAILED: "failed",
            NodeStatus.SKIPPED: "skipped",
            NodeStatus.CANCELLED: "skipped",
        }
        return classes.get(status, "pending")

    def _get_dot_color(self, status: NodeStatus) -> str:
        """Get Graphviz color for status"""
        colors = {
            NodeStatus.PENDING: "#f9f9f9",
            NodeStatus.READY: "#e3f2fd",
            NodeStatus.RUNNING: "#fff3cd",
            NodeStatus.COMPLETED: "#d4edda",
            NodeStatus.FAILED: "#f8d7da",
            NodeStatus.SKIPPED: "#e2e3e5",
            NodeStatus.CANCELLED: "#e2e3e5",
        }
        return colors.get(status, "#ffffff")

    def visualize_workflow_status(
        self, workflow_id: str, format: str = "ascii"
    ) -> Optional[str]:
        """
        Visualize current status of a running/completed workflow.

        Args:
            workflow_id: ID of the workflow
            format: Output format

        Returns:
            Visualization string or None if workflow not found
        """
        if workflow_id not in self.workflows:
            return None

        dag = self.workflows[workflow_id]["dag"]
        return self.visualize_dag(dag, format)

    def get_workflow_timeline(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """
        Get timeline of workflow execution.

        Returns timing information for each node.
        """
        if workflow_id not in self.workflows:
            return None

        workflow = self.workflows[workflow_id]
        dag = workflow["dag"]

        timeline: List[Any] = []
        for node_id, node in dag.nodes.items():
            entry = {
                "node_id": node_id,
                "agent": node.agent_name,
                "status": node.status.value,
            }

            if node.start_time:
                entry["start_time"] = node.start_time.isoformat()
            if node.end_time:
                entry["end_time"] = node.end_time.isoformat()
            if node.start_time and node.end_time:
                duration = (node.end_time - node.start_time).total_seconds()
                entry["duration_seconds"] = round(duration, 3)

            timeline.append(entry)

        # Sort by start time
        timeline.sort(key=lambda x: x.get("start_time", "9999"))

        return {
            "workflow_id": workflow_id,
            "dag_name": dag.name,
            "status": workflow["status"].value,
            "timeline": timeline,
        }

    def print_workflow_summary(self, workflow_id: str) -> str:
        """
        Print a human-readable summary of workflow execution.
        """
        if workflow_id not in self.workflows:
            return f"Workflow {workflow_id} not found"

        workflow = self.workflows[workflow_id]
        dag = workflow["dag"]

        lines: List[Any] = []
        lines.append(f"═══ Workflow Summary: {dag.name} ═══")
        lines.append(f"ID: {workflow_id}")
        lines.append(f"Status: {workflow['status'].value}")
        lines.append(f"Start: {workflow.get('start_time', 'N/A')}")
        lines.append(f"End: {workflow.get('end_time', 'N/A')}")
        lines.append("")

        # Node summary
        completed = sum(
            1 for n in dag.nodes.values() if n.status == NodeStatus.COMPLETED
        )
        failed = sum(1 for n in dag.nodes.values() if n.status == NodeStatus.FAILED)
        pending = sum(1 for n in dag.nodes.values() if n.status == NodeStatus.PENDING)

        lines.append(f"Nodes: {len(dag.nodes)} total")
        lines.append(f"  ● Completed: {completed}")
        lines.append(f"  ✗ Failed: {failed}")
        lines.append(f"  ○ Pending: {pending}")
        lines.append("")

        # Node details
        lines.append("Node Details:")
        for node_id, node in dag.nodes.items():
            icon = self._get_status_icon(node.status)
            duration = ""
            if node.start_time and node.end_time:
                dur = (node.end_time - node.start_time).total_seconds()
                duration = f" ({dur:.2f}s)"
            lines.append(f"  {icon} {node_id}: {node.agent_name}{duration}")
            if node.error:
                lines.append(f"      Error: {node.error[:50]}...")

        return "\n".join(lines)
