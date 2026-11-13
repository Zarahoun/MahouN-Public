"""
AgentRegistryCoordinator - Thin Orchestration Layer

Responsibility: Coordinate agent registration using injected services.
This coordinator contains ZERO business logic — only orchestration!

Architecture:
- All business logic delegated to services
- Services injected via ServiceContainer
- Coordinator = thin orchestration glue
- Registers AI agents with the system
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from mahoun.bootstrap.manager import (
    BootstrapPhaseExecutor,
    BootstrapContext,
    PhaseResult,
    BootstrapException,
)
from mahoun.bootstrap.services import (
    ServiceContainer,
    IntegrityVerifier,
    ResourceProfiler,
    ModelResolver,
    ModelLoader,
    ModelHealthChecker,
    BenchmarkService,
    RollbackManager,
    ResourceType,
    HealthStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class AgentDescriptor:
    """Agent metadata"""
    name: str
    agent_type: str  # "reasoning", "contract", "legal_research", etc.
    capabilities: List[str]
    dependencies: List[str]  # Required models/services
    priority: int = 1  # Lower = higher priority


class AgentRegistryCoordinator(BootstrapPhaseExecutor):
    """
    Thin coordinator for agent registration
    
    Workflow:
    1. Create rollback checkpoint
    2. Discover available agents
    3. Validate agent dependencies
    4. Register agents by priority
    5. Health check agent initialization
    6. Register in context
    7. Rollback on failure
    
    Agents:
    - Reasoning agents
    - Contract analysis agents
    - Legal research agents
    - RAG augmentation agents
    """
    
    def __init__(self, service_container: ServiceContainer):
        self.container = service_container
        self._phase_name = "agent_registry"
        
        # Define available agents
        self._available_agents = [
            AgentDescriptor(
                name="reasoning_agent",
                agent_type="reasoning",
                capabilities=["legal_reasoning", "case_analysis", "precedent_matching"],
                dependencies=["llm", "embedding_model", "rag_service"],
                priority=1
            ),
            AgentDescriptor(
                name="contract_agent", 
                agent_type="contract",
                capabilities=["contract_analysis", "clause_extraction", "risk_assessment"],
                dependencies=["llm", "embedding_model"],
                priority=2
            ),
            AgentDescriptor(
                name="research_agent",
                agent_type="research", 
                capabilities=["legal_research", "case_discovery", "citation_analysis"],
                dependencies=["embedding_model", "rag_service"],
                priority=3
            )
        ]
    
    async def execute(self, context: BootstrapContext) -> PhaseResult:
        """Execute agent registration orchestration"""
        start_time = datetime.utcnow()
        checkpoint_id = f"agent_registry_{int(start_time.timestamp())}"
        
        logger.info("Starting agent registration orchestration")
        
        try:
            # Step 1: Create rollback checkpoint
            checkpoint = self.container.rollback_manager.create_checkpoint(
                checkpoint_id=checkpoint_id,
                metadata={"phase": "agent_registry", "profile": context.runtime_profile}
            )
            
            # Step 2: Filter agents by available dependencies
            available_agents = self._filter_agents_by_dependencies(context)
            
            if not available_agents:
                logger.warning("No agents can be registered (missing dependencies)")
                return PhaseResult(
                    success=True,
                    phase_name=self._phase_name,
                    duration_seconds=0.1,
                    data={"registered_agents": []},
                    metadata={"warning": "no_agents_available"}
                )
            
            logger.info(f"Registering {len(available_agents)} agents")
            
            # Step 3: Register agents by priority
            registered_agents = {}
            registration_errors = []
            
            for agent_desc in sorted(available_agents, key=lambda a: a.priority):
                try:
                    logger.info(f"Registering agent: {agent_desc.name}")
                    
                    # Load agent class
                    agent = await self._load_agent(agent_desc, context)
                    
                    # Register cleanup
                    self.container.rollback_manager.register_resource(
                        checkpoint_id=checkpoint_id,
                        resource_type=ResourceType.CUSTOM,
                        identifier=f"agent_{agent_desc.name}",
                        cleanup_func=lambda a=agent: self._cleanup_agent(a),
                        metadata={"agent_type": agent_desc.agent_type}
                    )
                    
                    # Health check agent
                    health_ok = await self._test_agent_health(agent, agent_desc)
                    
                    if not health_ok:
                        logger.error(f"Agent health check failed: {agent_desc.name}")
                        registration_errors.append(f"Health check failed: {agent_desc.name}")
                        continue
                    
                    # Register successfully
                    registered_agents[agent_desc.name] = {
                        "agent": agent,
                        "descriptor": agent_desc,
                        "status": "healthy"
                    }
                    
                    logger.info(f"Agent registered: {agent_desc.name} ({agent_desc.agent_type})")
                
                except Exception as e:
                    error_msg = f"Failed to register agent {agent_desc.name}: {e}"
                    logger.error(error_msg)
                    registration_errors.append(error_msg)
            
            # Step 4: Register in context
            context.shared_state["agents"] = registered_agents
            context.shared_state["agent_count"] = len(registered_agents)
            
            # Step 5: Benchmark agents (optional)
            benchmark_results = {}
            if context.config.get("enable_agent_benchmarking", False):
                for name, agent_info in registered_agents.items():
                    try:
                        result = await self._benchmark_agent(agent_info["agent"], agent_info["descriptor"])
                        benchmark_results[name] = result
                    except Exception as e:
                        logger.warning(f"Agent benchmark failed for {name}: {e}")
            
            # Remove checkpoint
            self.container.rollback_manager.remove_checkpoint(checkpoint_id)
            
            # Success!
            duration = (datetime.utcnow() - start_time).total_seconds()
            
            return PhaseResult(
                success=True,
                phase_name=self._phase_name,
                duration_seconds=duration,
                data={
                    "registered_agents": list(registered_agents.keys()),
                    "agent_count": len(registered_agents),
                    "benchmark_results": benchmark_results,
                    "registration_errors": registration_errors
                },
                metadata={
                    "available_agents": len(available_agents),
                    "success_rate": len(registered_agents) / len(available_agents) if available_agents else 0
                }
            )
        
        except Exception as e:
            logger.error(f"Agent registration failed: {e}", exc_info=True)
            
            # Rollback on failure
            try:
                rollback_result = await self.container.rollback_manager.rollback(
                    checkpoint_id=checkpoint_id,
                    ignore_errors=True
                )
            except Exception as rollback_error:
                logger.error(f"Agent rollback failed: {rollback_error}")
            
            duration = (datetime.utcnow() - start_time).total_seconds()
            
            return PhaseResult(
                success=False,
                phase_name=self._phase_name,
                duration_seconds=duration,
                error=str(e),
                data={},
                metadata={"checkpoint_id": checkpoint_id}
            )
    
    def _filter_agents_by_dependencies(self, context: BootstrapContext) -> List[AgentDescriptor]:
        """Filter agents that can be loaded based on available dependencies"""
        available_deps = set()
        
        # Check what's available in context
        if "embedding_model" in context.shared_state:
            available_deps.add("embedding_model")
        if "llm" in context.shared_state:
            available_deps.add("llm")
        if context.config.get("rag_service_available", False):
            available_deps.add("rag_service")
        
        # Filter agents
        available_agents = []
        for agent_desc in self._available_agents:
            if all(dep in available_deps for dep in agent_desc.dependencies):
                available_agents.append(agent_desc)
            else:
                missing_deps = set(agent_desc.dependencies) - available_deps
                logger.info(f"Skipping agent {agent_desc.name}: missing dependencies {missing_deps}")
        
        return available_agents
    
    async def _load_agent(self, agent_desc: AgentDescriptor, context: BootstrapContext):
        """Load and initialize agent"""
        agent_name = agent_desc.name
        agent_type = agent_desc.agent_type
        
        logger.info(f"Loading agent: {agent_name} (type: {agent_type})")
        
        if agent_type == "reasoning":
            # Load reasoning agent
            from mahoun.agents.reasoning_agent import ReasoningAgent
            
            agent = ReasoningAgent(
                llm=context.shared_state["llm"],
                embedding_model=context.shared_state["embedding_model"],
                capabilities=agent_desc.capabilities
            )
            
            await agent.initialize()
            return agent
        
        elif agent_type == "contract":
            # Load contract agent
            from mahoun.agents.contract_agent import ContractAgent
            
            agent = ContractAgent(
                llm=context.shared_state["llm"],
                embedding_model=context.shared_state["embedding_model"],
                capabilities=agent_desc.capabilities
            )
            
            await agent.initialize()
            return agent
        
        elif agent_type == "research":
            # Load research agent
            from mahoun.agents.research_agent import ResearchAgent
            
            agent = ResearchAgent(
                embedding_model=context.shared_state["embedding_model"],
                capabilities=agent_desc.capabilities
            )
            
            await agent.initialize()
            return agent
        
        else:
            raise RuntimeError(f"Unknown agent type: {agent_type}")
    
    async def _test_agent_health(self, agent, agent_desc: AgentDescriptor) -> bool:
        """Test agent health"""
        try:
            # Basic health check
            if hasattr(agent, 'health_check'):
                result = await agent.health_check()
                return result
            
            # Fallback: test basic functionality
            if hasattr(agent, 'process') or hasattr(agent, '__call__'):
                # Agent is callable, assume healthy
                return True
            
            return True  # Default to healthy
        
        except Exception as e:
            logger.error(f"Agent health check failed for {agent_desc.name}: {e}")
            return False
    
    async def _benchmark_agent(self, agent, agent_desc: AgentDescriptor):
        """Benchmark agent performance"""
        try:
            if not hasattr(agent, 'process'):
                return {"status": "no_benchmark", "reason": "not_callable"}
            
            # Simple benchmark
            start_time = datetime.utcnow()
            
            test_input = "Test legal query for benchmarking"
            result = await agent.process(test_input)
            
            duration = (datetime.utcnow() - start_time).total_seconds()
            
            return {
                "status": "success",
                "duration_seconds": duration,
                "response_length": len(str(result)) if result else 0
            }
        
        except Exception as e:
            return {
                "status": "failed", 
                "error": str(e)
            }
    
    async def _cleanup_agent(self, agent):
        """Cleanup agent resources"""
        try:
            if hasattr(agent, 'cleanup'):
                await agent.cleanup()
            elif hasattr(agent, 'close'):
                await agent.close()
            
            # Delete agent
            del agent
            
            logger.debug("Agent cleanup complete")
        
        except Exception as e:
            logger.warning(f"Agent cleanup error: {e}")