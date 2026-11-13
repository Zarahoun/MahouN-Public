"""
Legacy Agent Adapter
====================

Provides backward compatibility for agents that use the old BaseAgent interface.
This adapter bridges the gap between the old simple BaseAgent and the new UltraBaseAgent.

The adapter wraps the simple process(input_data) interface to be compatible with
the Ultra interface process(input_data, correlation_id=None).
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Union
from dataclasses import dataclass, field
import logging
import time


@dataclass
class LegacyAgentResult:
    """
    Result wrapper for legacy agents to match UltraBaseAgent's AgentResult interface.
    """
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    correlation_id: Optional[str] = None
    processing_time_ms: float = 0.0
    retries_used: int = 0
    fallback_used: bool = False
    warnings: list = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "error_type": self.error_type,
            "correlation_id": self.correlation_id,
            "processing_time_ms": self.processing_time_ms,
            "retries_used": self.retries_used,
            "fallback_used": self.fallback_used,
            "warnings": self.warnings,
        }


class LegacyBaseAgent(ABC):
    """
    Legacy base agent interface for backward compatibility.
    
    This class provides a simpler interface that matches the old BaseAgent,
    while also being compatible with the UltraBaseAgent interface used by
    Factory and Orchestrator.
    
    For new agents, use UltraBaseAgent directly.
    """
    
    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        """
        Initialize agent.
        
        Args:
            name: Unique agent identifier
            config: Optional configuration dictionary
        """
        self.name = name
        self.config = config or {}
        self.logger = logging.getLogger(f"{__name__}.{name}")
        self._initialized = False
        
        self.logger.info(f"Agent initialized: {name}")
    
    async def initialize(self) -> None:
        """Initialize agent dependencies. Override in subclasses."""
        self._initialized = True
        
    def start_background_tasks(self) -> None:
        """Compatibility: No background tasks for legacy agent."""
        pass
        
    async def close(self) -> None:
        """Graceful shutdown for legacy agent."""
        self._initialized = False
        
    async def shutdown(self) -> None:
        """Alias for close()"""
        await self.close()
    
    async def process(
        self, 
        input_data: Dict[str, Any],
        correlation_id: Optional[str] = None
    ) -> Union[Dict[str, Any], LegacyAgentResult]:
        """
        Process input and produce output.
        
        Compatible with both Legacy (returns Dict) and Ultra (returns AgentResult) interfaces.
        
        Args:
            input_data: Input data dictionary
            correlation_id: Optional correlation ID for tracing (ignored in legacy impl)
            
        Returns:
            Processing result dictionary or LegacyAgentResult
        """
        start_time = time.time()
        
        try:
            # Call the actual implementation
            result = await self._process_impl(input_data)
            processing_time = (time.time() - start_time) * 1000
            
            # If result is already a dict with 'success' key, wrap it
            if isinstance(result, dict):
                return LegacyAgentResult(
                    success=result.get("success", True),
                    data=result,
                    correlation_id=correlation_id,
                    processing_time_ms=processing_time
                )
            return result
            
        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            self.logger.error(f"Error in {self.name}: {e}", exc_info=True)
            
            return LegacyAgentResult(
                success=False,
                error=str(e),
                error_type=type(e).__name__,
                correlation_id=correlation_id,
                processing_time_ms=processing_time
            )
    
    @abstractmethod
    async def _process_impl(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Actual processing implementation. Override in subclasses.
        
        Args:
            input_data: Input data dictionary
            
        Returns:
            Processing result dictionary
        """
        pass
    
    async def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """
        Validate input data.
        
        Args:
            input_data: Input data to validate
            
        Returns:
            True if input is valid
        """
        return True
    
    async def handle_error(
        self, 
        error: Exception, 
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle processing error.
        
        Args:
            error: Exception that occurred
            context: Additional context information
            
        Returns:
            Error response dictionary
        """
        self.logger.error(f"Error in {self.name}: {error}", exc_info=True)
        
        return {
            "success": False,
            "error": str(error),
            "agent": self.name,
            "context": context
        }
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get agent status information.
        
        Returns:
            Status dictionary with name and config
        """
        return {
            "name": self.name,
            "status": "ready" if self._initialized else "not_initialized",
            "config": self.config,
        }


# Alias for backward compatibility
BaseAgent = LegacyBaseAgent
