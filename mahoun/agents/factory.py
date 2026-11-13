"""
Agent Factory (HAJIX Refactored)
=================================

Factory pattern for creating and managing MAHOUN agents.

Usage:
    # Create single agent
    agent = await AgentFactory.create_agent("doc_parser")
    
    # Create all agents
    agents = await AgentFactory.create_all_agents()
    
    # List available agents
    available = AgentFactory.list_available_agents()
"""

from typing import Any, Dict, List, Optional, Type, Union
import logging

from .base_agent import UltraBaseAgent, AgentConfig
from .legacy_adapter import LegacyBaseAgent
from .doc_parser_agent import UltraDocParserAgent
from .dispute_agent import DisputeAgent
from .claim_agent import UltraClaimAgent
from .timeline_agent import TimelineAgent
from .delay_agent import DelayAgent
from .narrative_agent import NarrativeAgent
from .contract_agent import UltraContractAgent
from .critic_agent import CriticAgent

logger = logging.getLogger(__name__)

# Type alias for agent base class (can be either Ultra or Legacy)
BaseAgent = Union[UltraBaseAgent, LegacyBaseAgent]

# Agent Registry - maps agent type to class
# Note: Registry contains both Ultra agents and Legacy agents
AGENT_REGISTRY: Dict[str, Type] = {
    "doc_parser": UltraDocParserAgent,
    "dispute": DisputeAgent,
    "claim": UltraClaimAgent,
    "timeline": TimelineAgent,
    "delay": DelayAgent,
    "narrative": NarrativeAgent,
    "contract": UltraContractAgent,
    "critic": CriticAgent,
}


class AgentFactory:
    """
    Factory for creating MAHOUN agents.
    
    Provides centralized agent creation with configuration injection
    and lifecycle management.
    """
    
    @staticmethod
    async def create_agent(
        agent_type: str,
        config: Optional[Dict[str, Any]] = None
    ) -> BaseAgent:
        """
        Create and initialize an agent.
        
        Args:
            agent_type: Type of agent (e.g., "doc_parser", "dispute")
            config: Optional configuration dictionary
        
        Returns:
            Initialized agent instance
        
        Raises:
            ValueError: If agent_type is not recognized
        
        Example:
            agent = await AgentFactory.create_agent("doc_parser")
            result = await agent.process({"text": "..."})
        """
        if agent_type not in AGENT_REGISTRY:
            available = ", ".join(AGENT_REGISTRY.keys())
            raise ValueError(
                f"Unknown agent type: '{agent_type}'. Available: {available}"
            )
        
        logger.info(f"Creating agent: {agent_type}")
        
        agent_class = AGENT_REGISTRY[agent_type]
        agent = agent_class(config)
        await agent.initialize()
        
        logger.info(f"Agent created: {agent_type}")
        return agent
    
    @staticmethod
    async def create_all_agents(
        config: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> Dict[str, BaseAgent]:
        """
        Create all registered agents.
        
        Args:
            config: Optional config dict with agent-specific configs
                    Format: {"agent_type": {"config_key": "value"}}
        
        Returns:
            Dictionary mapping agent_type to agent instance
        """
        logger.info(f"Creating all agents ({len(AGENT_REGISTRY)} total)")
        
        agents: Dict[str, Any] = {}
        config = config or {}
        
        for agent_type in AGENT_REGISTRY.keys():
            try:
                agent_config = config.get(agent_type)
                agents[agent_type] = await AgentFactory.create_agent(
                    agent_type, agent_config
                )
            except Exception as e:
                logger.error(f"Failed to create agent '{agent_type}': {e}")
        
        logger.info(f"Created {len(agents)}/{len(AGENT_REGISTRY)} agents")
        return agents
    
    @staticmethod
    def list_available_agents() -> List[str]:
        """
        List all available agent types.
        
        Returns:
            List of agent type strings
        """
        return list(AGENT_REGISTRY.keys())
    
    @staticmethod
    def get_agent_info(agent_type: str) -> Dict[str, Any]:
        """
        Get information about an agent type.
        
        Args:
            agent_type: Type of agent
        
        Returns:
            Dictionary with agent class info
        
        Raises:
            ValueError: If agent_type is not recognized
        """
        if agent_type not in AGENT_REGISTRY:
            raise ValueError(f"Unknown agent type: '{agent_type}'")
        
        agent_class = AGENT_REGISTRY[agent_type]
        return {
            "type": agent_type,
            "class": agent_class.__name__,
            "module": agent_class.__module__,
            "docstring": agent_class.__doc__,
        }
    
    @staticmethod
    def register_agent(agent_type: str, agent_class: Type[BaseAgent]) -> None:
        """
        Register a new agent type.
        
        Args:
            agent_type: Unique identifier for the agent
            agent_class: Agent class (must inherit from BaseAgent)
        
        Raises:
            ValueError: If agent_type already exists or class is invalid
        """
        if agent_type in AGENT_REGISTRY:
            raise ValueError(f"Agent type '{agent_type}' already registered")
        
        if not issubclass(agent_class, BaseAgent):
            raise ValueError("Agent class must inherit from BaseAgent")
        
        AGENT_REGISTRY[agent_type] = agent_class
        logger.info(f"Registered agent: {agent_type}")
