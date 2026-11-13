"""
Ultra Agent Factory - Enterprise-Grade Agent Management
=======================================================
Factory pattern برای ساخت و مدیریت Ultra Agents

Features:
- Lazy Loading (بارگذاری در صورت نیاز)
- Singleton Management (یک نمونه از هر agent)
- Health Monitoring (نظارت بر سلامت)
- Graceful Shutdown (خاموشی ایمن)
- Backward Compatibility (سازگاری با agents قدیمی)

Usage:
    # Create single agent
    agent = await UltraAgentFactory.create("doc_parser")
    
    # Create with custom config
    agent = await UltraAgentFactory.create("contract", config={...})
    
    # Get or create (singleton)
    agent = await UltraAgentFactory.get_or_create("doc_parser")
    
    # List available
    available = UltraAgentFactory.list_available()
    
    # Health check all
    health = await UltraAgentFactory.health_check_all()
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Type
from dataclasses import dataclass

from .base_agent import UltraBaseAgent, AgentConfig

logger = logging.getLogger(__name__)


# ============================================================================
# Agent Registry
# ============================================================================

@dataclass
class AgentRegistration:
    """Registration info for an agent type"""
    agent_class: Type[UltraBaseAgent]
    config_class: Optional[Type[AgentConfig]] = None
    description: str = ""
    category: str = "general"
    priority: int = 1  # Higher = more preferred


# Ultra Agent Registry
ULTRA_AGENT_REGISTRY: Dict[str, AgentRegistration] = {}


def register_ultra_agent(
    name: str,
    agent_class: Type[UltraBaseAgent],
    config_class: Optional[Type[AgentConfig]] = None,
    description: str = "",
    category: str = "general",
    priority: int = 1
):
    """
    Register an Ultra agent type.
    
    Args:
        name: Unique identifier for the agent
        agent_class: Agent class (must inherit from UltraBaseAgent)
        config_class: Optional config class
        description: Human-readable description
        category: Agent category (parsing, analysis, etc.)
        priority: Priority level (higher = preferred)
    """
    if name in ULTRA_AGENT_REGISTRY:
        logger.warning(f"Overwriting agent registration: {name}")
    
    ULTRA_AGENT_REGISTRY[name] = AgentRegistration(
        agent_class=agent_class,
        config_class=config_class,
        description=description,
        category=category,
        priority=priority
    )
    logger.debug(f"Registered Ultra agent: {name}")


# ============================================================================
# Register Built-in Agents
# ============================================================================

def _register_builtin_agents():
    """Register all built-in Ultra agents"""
    try:
        from .doc_parser_agent import UltraDocParserAgent, DocParserConfig
        register_ultra_agent(
            name="doc_parser",
            agent_class=UltraDocParserAgent,
            config_class=DocParserConfig,
            description="پردازش و تجزیه اسناد حقوقی با NER و ذخیره‌سازی",
            category="parsing",
            priority=10
        )
    except ImportError as e:
        logger.warning(f"Could not register UltraDocParserAgent: {e}")
    
    try:
        from .contract_agent import UltraContractAgent, ContractAgentConfig
        register_ultra_agent(
            name="contract",
            agent_class=UltraContractAgent,
            config_class=ContractAgentConfig,
            description="تحلیل قراردادها با Chain-of-Thought reasoning",
            category="analysis",
            priority=10
        )
    except ImportError as e:
        logger.warning(f"Could not register UltraContractAgent: {e}")
    
    try:
        from .dispute_agent import DisputeAgent
        register_ultra_agent(
            name="dispute",
            agent_class=DisputeAgent,
            config_class=None,  # DisputeAgent uses Dict config, not dataclass
            description="شناسایی اختلافات و نقض تعهدات",
            category="analysis",
            priority=9
        )
    except ImportError as e:
        logger.warning(f"Could not register DisputeAgent: {e}")
    
    try:
        from .claim_agent import UltraClaimAgent, ClaimAgentConfig
        register_ultra_agent(
            name="claim",
            agent_class=UltraClaimAgent,
            config_class=ClaimAgentConfig,
            description="تولید محتوای دعوی با استدلال‌های حقوقی",
            category="generation",
            priority=9
        )
    except ImportError as e:
        logger.warning(f"Could not register UltraClaimAgent: {e}")
    
    try:
        from .ultra_narrative_agent import UltraNarrativeAgent, NarrativeAgentConfig
        register_ultra_agent(
            name="narrative",
            agent_class=UltraNarrativeAgent,
            config_class=NarrativeAgentConfig,
            description="تولید روایت حقوقی-فنی کامل",
            category="generation",
            priority=8
        )
    except ImportError as e:
        logger.warning(f"Could not register UltraNarrativeAgent: {e}")
    
    try:
        from .ultra_precedent_agent import UltraPrecedentAgent, PrecedentAgentConfig
        register_ultra_agent(
            name="precedent",
            agent_class=UltraPrecedentAgent,
            config_class=PrecedentAgentConfig,
            description="جستجوی آراء و احکام مشابه",
            category="search",
            priority=9
        )
    except ImportError as e:
        logger.warning(f"Could not register UltraPrecedentAgent: {e}")

    try:
        from .ultra_timeline_agent import UltraTimelineAgent, TimelineConfig
        register_ultra_agent(
            name="timeline",
            agent_class=UltraTimelineAgent,
            config_class=TimelineConfig,
            description="تحلیل زمانی وقایع، استخراج تاریخ‌ها و بررسی تضادهای زمانی",
            category="analysis",
            priority=8
        )
    except ImportError as e:
        logger.warning(f"Could not register UltraTimelineAgent: {e}")

    try:
        from .ultra_delay_agent import UltraDelayAgent, DelayConfig
        register_ultra_agent(
            name="delay",
            agent_class=UltraDelayAgent,
            config_class=DelayConfig,
            description="مدیریت ادعاهای تاخیرات پیمانکار و کارفرما (EOT)",
            category="analysis",
            priority=8
        )
    except ImportError as e:
        logger.warning(f"Could not register UltraDelayAgent: {e}")



    try:
        from .ultra_risk_assessment_agent import UltraRiskAssessmentAgent, RiskAgentConfig
        register_ultra_agent(
            name="risk_assessment",
            agent_class=UltraRiskAssessmentAgent,
            config_class=RiskAgentConfig,
            description="ارزیابی ریسک با Gaussian Process و شبیه‌سازی مالی Monte Carlo",
            category="analysis",
            priority=9
        )
    except ImportError as e:
        logger.warning(f"Could not register UltraRiskAssessmentAgent: {e}")


# Register on module load
_register_builtin_agents()


# ============================================================================
# Ultra Agent Factory
# ============================================================================

class UltraAgentFactory:
    """
    Factory for creating and managing Ultra agents.
    
    این کلاس مدیریت کامل چرخه حیات Ultra agents را انجام می‌دهد:
    - ساخت agents با تنظیمات سفارشی
    - مدیریت singleton برای جلوگیری از ساخت مجدد
    - نظارت بر سلامت agents
    - خاموشی ایمن همه agents
    
    Features:
    - Lazy loading: Agents are created only when needed
    - Singleton pattern: One instance per agent type
    - Health monitoring: Check all agents' health
    - Graceful shutdown: Clean shutdown of all agents
    """
    
    # Singleton instances
    _instances: Dict[str, UltraBaseAgent] = {}
    _lock = asyncio.Lock()
    
    @classmethod
    async def create(
        cls,
        agent_type: str,
        config: Optional[Dict[str, Any]] = None,
        use_singleton: bool = False
    ) -> UltraBaseAgent:
        """
        Create a new agent instance.
        
        Args:
            agent_type: Type of agent (e.g., "doc_parser", "contract")
            config: Optional configuration dictionary
            use_singleton: If True, return existing instance if available
        
        Returns:
            Initialized agent instance
        
        Raises:
            ValueError: If agent_type is not registered
        
        Example:
            agent = await UltraAgentFactory.create("doc_parser")
            result = await agent.process({"text": "..."})
        """
        if agent_type not in ULTRA_AGENT_REGISTRY:
            available = ", ".join(ULTRA_AGENT_REGISTRY.keys())
            raise ValueError(
                f"Unknown agent type: '{agent_type}'. "
                f"Available: {available}"
            )
        
        # Check singleton
        if use_singleton and agent_type in cls._instances:
            logger.debug(f"Returning existing instance: {agent_type}")
            return cls._instances[agent_type]
        
        registration = ULTRA_AGENT_REGISTRY[agent_type]
        
        # Build config
        agent_config: Optional[Any] = None
        if config and registration.config_class:
            agent_config = registration.config_class(**config)
        elif registration.config_class:
            agent_config = registration.config_class()
        
        # Create instance
        logger.info(f"Creating Ultra agent: {agent_type}")
        agent = registration.agent_class(config=agent_config)
        
        # Initialize
        await agent.initialize()
        
        # Store singleton
        if use_singleton:
            cls._instances[agent_type] = agent
        
        logger.info(f"✅ Ultra agent created: {agent_type}")
        return agent
    
    @classmethod
    async def get_or_create(
        cls,
        agent_type: str,
        config: Optional[Dict[str, Any]] = None
    ) -> UltraBaseAgent:
        """
        Get existing agent or create new one (singleton pattern).
        
        Thread-safe singleton access.
        
        Args:
            agent_type: Type of agent
            config: Optional configuration (only used if creating new)
        
        Returns:
            Agent instance
        """
        async with cls._lock:
            if agent_type in cls._instances:
                return cls._instances[agent_type]
            
            agent = await cls.create(agent_type, config, use_singleton=True)
            return agent
    
    @classmethod
    async def create_all(
        cls,
        config: Optional[Dict[str, Dict[str, Any]]] = None,
        categories: Optional[List[str]] = None
    ) -> Dict[str, UltraBaseAgent]:
        """
        Create all registered agents.
        
        Args:
            config: Optional config dict with agent-specific configs
                   Format: {"agent_type": {"config_key": "value"}}
            categories: Optional list of categories to create
        
        Returns:
            Dictionary mapping agent_type -> agent instance
        """
        logger.info(f"Creating all Ultra agents ({len(ULTRA_AGENT_REGISTRY)} registered)")
        
        agents: Dict[str, Any] = {}
        config = config or {}
        
        for agent_type, registration in ULTRA_AGENT_REGISTRY.items():
            # Filter by category
            if categories and registration.category not in categories:
                continue
            
            try:
                agent_config = config.get(agent_type)
                agents[agent_type] = await cls.create(
                    agent_type,
                    agent_config,
                    use_singleton=True
                )
            except Exception as e:
                logger.error(f"Failed to create agent '{agent_type}': {e}")
        
        logger.info(f"✅ Created {len(agents)}/{len(ULTRA_AGENT_REGISTRY)} agents")
        return agents
    
    @classmethod
    def list_available(cls) -> List[Dict[str, Any]]:
        """
        List all available agent types with info.
        
        Returns:
            List of agent info dictionaries
        """
        return [
            {
                "type": name,
                "class": reg.agent_class.__name__,
                "description": reg.description,
                "category": reg.category,
                "priority": reg.priority,
                "is_instantiated": name in cls._instances
            }
            for name, reg in ULTRA_AGENT_REGISTRY.items()
        ]
    
    @classmethod
    def get_agent_info(cls, agent_type: str) -> Dict[str, Any]:
        """
        Get detailed info about an agent type.
        
        Args:
            agent_type: Type of agent
        
        Returns:
            Agent info dictionary
        """
        if agent_type not in ULTRA_AGENT_REGISTRY:
            raise ValueError(f"Unknown agent type: '{agent_type}'")
        
        reg = ULTRA_AGENT_REGISTRY[agent_type]
        
        return {
            "type": agent_type,
            "class": reg.agent_class.__name__,
            "module": reg.agent_class.__module__,
            "description": reg.description,
            "category": reg.category,
            "priority": reg.priority,
            "config_class": reg.config_class.__name__ if reg.config_class else None,
            "docstring": reg.agent_class.__doc__,
            "is_instantiated": agent_type in cls._instances
        }
    
    @classmethod
    async def health_check_all(cls) -> Dict[str, Dict[str, Any]]:
        """
        Check health of all instantiated agents.
        
        Returns:
            Dictionary mapping agent_type -> health status
        """
        results: Dict[str, Any] = {}
        for agent_type, agent in cls._instances.items():
            try:
                health = await agent.health_check()
                results[agent_type] = health
            except Exception as e:
                results[agent_type] = {
                    "healthy": False,
                    "error": str(e)
                }
        
        return results
    
    @classmethod
    async def shutdown_all(cls):
        """
        Gracefully shutdown all instantiated agents.
        """
        logger.info(f"Shutting down {len(cls._instances)} agents...")
        
        for agent_type, agent in list(cls._instances.items()):
            try:
                await agent.shutdown()
                logger.info(f"✅ Shut down: {agent_type}")
            except Exception as e:
                logger.error(f"Error shutting down {agent_type}: {e}")
        
        cls._instances.clear()
        logger.info("All agents shut down")
    
    @classmethod
    def get_instance(cls, agent_type: str) -> Optional[UltraBaseAgent]:
        """
        Get existing instance without creating.
        
        Args:
            agent_type: Type of agent
        
        Returns:
            Agent instance or None if not instantiated
        """
        return cls._instances.get(agent_type)
    
    @classmethod
    def get_all_metrics(cls) -> Dict[str, Dict[str, Any]]:
        """
        Get metrics from all instantiated agents.
        
        Returns:
            Dictionary mapping agent_type -> metrics
        """
        return {
            agent_type: agent.get_metrics()
            for agent_type, agent in cls._instances.items()
        }
    
    @classmethod
    def register(
        cls,
        name: str,
        agent_class: Type[UltraBaseAgent],
        config_class: Optional[Type[AgentConfig]] = None,
        description: str = "",
        category: str = "custom",
        priority: int = 5
    ):
        """
        Register a custom agent type.
        
        Args:
            name: Unique identifier
            agent_class: Agent class (must inherit from UltraBaseAgent)
            config_class: Optional config class
            description: Human-readable description
            category: Agent category
            priority: Priority level
        
        Example:
            class MyCustomAgent(UltraBaseAgent):
                # Implementation
            
            UltraAgentFactory.register(
                "my_custom",
                MyCustomAgent,
                description="My custom agent"
            )
        """
        if not issubclass(agent_class, UltraBaseAgent):
            raise ValueError("Agent class must inherit from UltraBaseAgent")
        
        register_ultra_agent(
            name=name,
            agent_class=agent_class,
            config_class=config_class,
            description=description,
            category=category,
            priority=priority
        )


# ============================================================================
# Backward Compatibility Layer
# ============================================================================

class LegacyAgentAdapter(UltraBaseAgent):
    """
    Adapter to wrap legacy agents as Ultra agents.
    
    این کلاس agents قدیمی را به Ultra agents تبدیل می‌کند
    تا backward compatibility حفظ شود.
    """
    
    def __init__(self, legacy_agent, name: str = "legacy"):
        super().__init__(name=name)
        self._legacy_agent = legacy_agent
    
    async def _initialize_impl(self):
        """Initialize legacy agent"""
        if hasattr(self._legacy_agent, 'initialize'):
            await self._legacy_agent.initialize()
    
    async def _process_impl(
        self,
        input_data: Dict[str, Any],
        correlation_id: Optional[str]
    ) -> Dict[str, Any]:
        """Process using legacy agent"""
        if hasattr(self._legacy_agent, 'process'):
            result = await self._legacy_agent.process(input_data)
            if isinstance(result, dict):
                return result
            return {"result": result}
        raise NotImplementedError("Legacy agent has no process method")
    
    async def _fallback_impl(
        self,
        input_data: Dict[str, Any],
        correlation_id: Optional[str]
    ) -> Dict[str, Any]:
        """No fallback for legacy agents"""
        raise NotImplementedError("Legacy agent fallback not available")


async def wrap_legacy_agent(legacy_agent, name: str = "legacy") -> UltraBaseAgent:
    """
    Wrap a legacy agent as an Ultra agent.
    
    Args:
        legacy_agent: Legacy agent instance
        name: Name for the wrapped agent
    
    Returns:
        UltraBaseAgent wrapper
    
    Example:
        from mahoun.agents.doc_parser_agent import DocParserAgent
        
        legacy = DocParserAgent()
        ultra = await wrap_legacy_agent(legacy, "doc_parser_legacy")
        result = await ultra.process({"text": "..."})
    """
    adapter = LegacyAgentAdapter(legacy_agent, name)
    await adapter.initialize()
    return adapter
