"""
Verdict Execution Replay Service
=================================

Classification: MISSION-CRITICAL / EXECUTION-AUDIT / DETERMINISTIC-REPLAY
Purpose: Extract replay capability from ExecutionController for verdict generation path

This service provides replay functionality for verdict generation requests
without requiring full ExecutionController wrapping of the existing
GovernanceContextManager + Fortress + LedgerCommitService stack.

Key Features:
- Store execution contexts for replay
- Deterministic replay with same inputs
- Checksum verification between original and replay
- Integration with existing governance stack

Usage:
    from mahoun.execution.replay_service import VerdictReplayService
    
    replay_service = VerdictReplayService()
    
    # Store execution context during verdict generation
    execution_id = replay_service.store_context(
        question="What is the law?",
        facts=["fact1", "fact2"],
        correlation_id="req-123"
    )
    
    # Replay later
    replay_result = await replay_service.replay_verdict_execution(execution_id)

Author: MahouN Platform Architecture
Version: 1.0.0
"""

import asyncio
import hashlib
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from threading import RLock
import logging

from mahoun.core.governance import GovernanceContextManager
from mahoun.reasoning.evidence_linked_verdict import EvidenceLinkedVerdictEngine
from mahoun.reasoning.verdict_engine_adapter import create_verdict_engine_adapter
from mahoun.reasoning.ledger_commit_service import create_ledger_commit_service
from mahoun.reasoning.fortress_integration import create_fortress_protected_service
from mahoun.ledger.writer import create_ledger_writer, EvidenceLedgerWriter

logger = logging.getLogger(__name__)


@dataclass
class VerdictExecutionContext:
    """Context for verdict execution that can be replayed"""
    
    execution_id: str
    question: str
    facts: List[str]
    correlation_id: str
    case_id: str
    timestamp: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VerdictExecutionContext":
        """Create from dictionary"""
        return cls(**data)
    
    def compute_input_hash(self) -> str:
        """Compute hash of input parameters for replay verification"""
        input_data = f"{self.question}:{':'.join(sorted(self.facts))}:{self.correlation_id}"
        return hashlib.sha256(input_data.encode()).hexdigest()[:16]


@dataclass
class ReplayResult:
    """Result of a replay operation"""
    
    execution_id: str
    replay_id: str
    original_context: VerdictExecutionContext
    replay_successful: bool
    checksum_match: bool
    original_checksum: Optional[str]
    replay_checksum: Optional[str]
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class VerdictReplayService:
    """
    Service for replaying verdict execution requests.
    
    This service extracts the replay capability from ExecutionController
    and integrates it with the existing verdict generation pipeline
    without requiring a full wrapper around the governance stack.
    """
    
    def __init__(self, max_history: int = 1000):
        """
        Initialize replay service.
        
        Args:
            max_history: Maximum number of execution contexts to store
        """
        self.max_history = max_history
        
        # Execution context storage (in production, use persistent storage)
        self._contexts: Dict[str, VerdictExecutionContext] = {}
        self._results: Dict[str, Any] = {}  # Store original results for comparison
        self._lock = RLock()
        
        # Statistics
        self.stats = {
            "contexts_stored": 0,
            "replays_attempted": 0,
            "replays_successful": 0,
            "checksum_matches": 0,
        }
        
        logger.info(f"VerdictReplayService initialized (max_history={max_history})")
    
    def store_execution_context(
        self,
        question: str,
        facts: List[str],
        correlation_id: str,
        case_id: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> str:
        """
        Store execution context for potential replay.
        
        Args:
            question: The legal question
            facts: List of facts
            correlation_id: Correlation ID from governance context
            case_id: Case identifier
            user_id: Optional user identifier
            session_id: Optional session identifier
            
        Returns:
            execution_id for later replay
        """
        # Lookup key only — not a determinism input. Replay correctness is
        # verified via response_checksum comparison, not ID equality.
        # See AGENTS.md / audit history (Round 13) for full downstream trace.
        execution_id = str(uuid.uuid4())
        
        context = VerdictExecutionContext(
            execution_id=execution_id,
            question=question,
            facts=facts.copy(),
            correlation_id=correlation_id,
            case_id=case_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            user_id=user_id,
            session_id=session_id
        )
        
        with self._lock:
            self._contexts[execution_id] = context
            self.stats["contexts_stored"] += 1
            
            # Trim history if needed
            if len(self._contexts) > self.max_history:
                # Remove oldest contexts
                oldest_keys = sorted(
                    self._contexts.keys(),
                    key=lambda k: self._contexts[k].timestamp
                )[:len(self._contexts) - self.max_history]
                
                for key in oldest_keys:
                    del self._contexts[key]
                    if key in self._results:
                        del self._results[key]
        
        logger.debug(f"Stored execution context {execution_id} for replay")
        return execution_id
    
    def store_execution_result(
        self,
        execution_id: str,
        result: Any,
        response_checksum: Optional[str] = None
    ) -> None:
        """
        Store execution result for replay comparison.
        
        Args:
            execution_id: The execution ID
            result: The verdict result
            response_checksum: Optional checksum of the response
        """
        with self._lock:
            self._results[execution_id] = {
                "result": result,
                "checksum": response_checksum or self._compute_result_checksum(result),
                "stored_at": datetime.now(timezone.utc).isoformat()
            }
    
    async def replay_verdict_execution(
        self,
        execution_id: str,
        verdict_engine: Optional[EvidenceLinkedVerdictEngine] = None
    ) -> ReplayResult:
        """
        Replay a verdict execution with the same inputs.
        
        Args:
            execution_id: ID of the execution to replay
            verdict_engine: Optional verdict engine (uses default if None)
            
        Returns:
            ReplayResult with comparison data
        """
        with self._lock:
            self.stats["replays_attempted"] += 1
        
        # Get original context
        context = self._get_context(execution_id)
        if not context:
            return ReplayResult(
                execution_id=execution_id,
                # Lookup key only — not a determinism input.
                replay_id=str(uuid.uuid4()),
                original_context=None,
                replay_successful=False,
                checksum_match=False,
                original_checksum=None,
                replay_checksum=None,
                error=f"Execution context {execution_id} not found"
            )
        
        logger.info(f"Replaying verdict execution {execution_id}")
        
        # Per-replay attempt identifier only — not a determinism input.
        # The same execution may be replayed multiple times; each attempt needs
        # its own ID. Replay correctness is verified via response_checksum
        # comparison, not ID equality. See AGENTS.md / audit history (Round 13).
        replay_id = str(uuid.uuid4())
        start_time = datetime.now()
        
        try:
            # Get original result for comparison
            original_data = self._results.get(execution_id, {})
            original_checksum = original_data.get("checksum")
            
            # Execute replay through the same pipeline as original
            replay_result = await self._execute_verdict_replay(
                context, verdict_engine
            )
            
            # Compute replay checksum
            replay_checksum = self._compute_result_checksum(replay_result)
            
            # Compare checksums
            checksum_match = (
                original_checksum is not None and 
                replay_checksum == original_checksum
            )
            
            execution_time_ms = (
                datetime.now() - start_time
            ).total_seconds() * 1000
            
            # Update statistics
            with self._lock:
                self.stats["replays_successful"] += 1
                if checksum_match:
                    self.stats["checksum_matches"] += 1
            
            logger.info(
                f"Replay {replay_id} completed: "
                f"checksum_match={checksum_match}, "
                f"time={execution_time_ms:.2f}ms"
            )
            
            return ReplayResult(
                execution_id=execution_id,
                replay_id=replay_id,
                original_context=context,
                replay_successful=True,
                checksum_match=checksum_match,
                original_checksum=original_checksum,
                replay_checksum=replay_checksum,
                execution_time_ms=execution_time_ms
            )
            
        except Exception as e:
            logger.error(f"Replay {replay_id} failed: {e}", exc_info=True)
            
            return ReplayResult(
                execution_id=execution_id,
                replay_id=replay_id,
                original_context=context,
                replay_successful=False,
                checksum_match=False,
                original_checksum=None,
                replay_checksum=None,
                error=str(e),
                execution_time_ms=(
                    datetime.now() - start_time
                ).total_seconds() * 1000
            )
    
    async def _execute_verdict_replay(
        self,
        context: VerdictExecutionContext,
        verdict_engine: Optional[EvidenceLinkedVerdictEngine] = None
    ) -> Any:
        """
        Execute verdict replay through the same pipeline as original.
        
        This uses the existing GovernanceContextManager + Fortress + 
        LedgerCommitService stack to ensure replay follows the same path.
        """
        # Use default verdict engine if none provided
        if verdict_engine is None:
            # Import here to avoid circular dependency
            from api.routers.reasoning import get_verdict_engine
            verdict_engine = get_verdict_engine()
        
        # Create governance context for replay
        async with GovernanceContextManager.active_context(
            correlation_id=f"{context.correlation_id}-replay",
            execution_mode="STRICT",
            actor_id=context.user_id
        ) as gov_ctx:
            
            # Set up the same pipeline as original verdict generation
            adapted_engine = create_verdict_engine_adapter(verdict_engine)
            
            # Get ledger writer for commit service
            from mahoun.ledger.blockchain import ImmutableLedger
            immutable_ledger = ImmutableLedger()
            ledger_writer = EvidenceLedgerWriter(blockchain=immutable_ledger)
            
            # Create ledger commit service
            ledger_commit_service = create_ledger_commit_service(
                ledger_writer=ledger_writer,
                strict_mode=True
            )
            
            # Wrap with Fortress protection
            protected_service = create_fortress_protected_service(
                reasoning_service=adapted_engine,
                strict_mode=True,
                ledger_commit_service=ledger_commit_service
            )
            
            # Execute reasoning with replay context
            verdict = await protected_service.reason(
                request=type(
                    "ReasoningRequest",
                    (),
                    {
                        "question": context.question,
                        "facts": context.facts,
                        "correlation_id": gov_ctx.correlation_id,
                        "case_id": f"{context.case_id}-replay",
                        "execution_id": f"{context.execution_id}-replay",
                    },
                )(),
                correlation_id=gov_ctx.correlation_id,
            )
            
            return verdict
    
    def _get_context(self, execution_id: str) -> Optional[VerdictExecutionContext]:
        """Get execution context by ID"""
        with self._lock:
            return self._contexts.get(execution_id)
    
    def _compute_result_checksum(self, result: Any) -> str:
        """Compute checksum of result for comparison"""
        # Convert result to string representation for checksum
        # This is a simplified approach - in production, consider more sophisticated
        # serialization that handles nested objects consistently
        result_str = str(result)
        return hashlib.sha256(result_str.encode()).hexdigest()[:16]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get replay service statistics"""
        with self._lock:
            return {
                **self.stats,
                "contexts_in_memory": len(self._contexts),
                "results_in_memory": len(self._results),
                "success_rate": (
                    self.stats["replays_successful"] / 
                    max(self.stats["replays_attempted"], 1)
                ),
                "checksum_match_rate": (
                    self.stats["checksum_matches"] / 
                    max(self.stats["replays_successful"], 1)
                ) if self.stats["replays_successful"] > 0 else 0.0,
            }
    
    def get_execution_history(
        self,
        limit: int = 100,
        user_id: Optional[str] = None
    ) -> List[VerdictExecutionContext]:
        """Get execution history with optional user filtering"""
        with self._lock:
            contexts = list(self._contexts.values())
            
            if user_id:
                contexts = [c for c in contexts if c.user_id == user_id]
            
            # Sort by timestamp (newest first)
            contexts.sort(key=lambda c: c.timestamp, reverse=True)
            
            return contexts[:limit]


# Global instance for use across the application
_global_replay_service: Optional[VerdictReplayService] = None


def get_verdict_replay_service() -> VerdictReplayService:
    """Get the global verdict replay service instance"""
    global _global_replay_service
    if _global_replay_service is None:
        _global_replay_service = VerdictReplayService()
    return _global_replay_service


def store_verdict_execution_context(
    question: str,
    facts: List[str],
    correlation_id: str,
    case_id: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None
) -> str:
    """
    Convenience function to store execution context.
    
    Returns execution_id for later replay.
    """
    service = get_verdict_replay_service()
    return service.store_execution_context(
        question=question,
        facts=facts,
        correlation_id=correlation_id,
        case_id=case_id,
        user_id=user_id,
        session_id=session_id
    )


def store_verdict_execution_result(
    execution_id: str,
    result: Any,
    response_checksum: Optional[str] = None
) -> None:
    """
    Convenience function to store execution result.
    """
    service = get_verdict_replay_service()
    service.store_execution_result(
        execution_id=execution_id,
        result=result,
        response_checksum=response_checksum
    )