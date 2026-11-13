"""
HARDENING PATCH P14 + B2-01: Legal Reasoning State Machine
===========================================================
Dedicated state machine for the legal reasoning lifecycle to ensure
transitions are strictly guarded and verifiable. Replaces ad-hoc
async orchestration for verdict generation.

HARDENING B2-01: Force bypass REMOVED
- No force=True parameter allowed
- All transitions MUST follow valid transition rules
- Invalid transitions are HARD REJECTED with audit logging
- Emergency ERROR_OCCURRED transition remains as only exception

Invariant: No state bypass without provenance trail.
"""

import time
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable
import threading

logger = logging.getLogger("legal_state_machine")

class LegalState(Enum):
    """Formal states of the legal reasoning lifecycle"""
    IDLE = "IDLE"
    INGESTING = "INGESTING"
    REASONING = "REASONING"
    VERDICT_GENERATION = "VERDICT_GENERATION"
    LEDGER_COMMIT = "LEDGER_COMMIT"
    ERROR = "ERROR"
    COMPLETED = "COMPLETED"

class LegalTrigger(Enum):
    """Triggers to transition between legal states"""
    START_INGESTION = "START_INGESTION"
    INGESTION_COMPLETE = "INGESTION_COMPLETE"
    START_REASONING = "START_REASONING"
    REASONING_COMPLETE = "REASONING_COMPLETE"
    GENERATE_VERDICT = "GENERATE_VERDICT"
    VERDICT_READY = "VERDICT_READY"
    COMMIT_SUCCESS = "COMMIT_SUCCESS"
    ERROR_OCCURRED = "ERROR_OCCURRED"
    RESET = "RESET"

class LegalReasoningStateMachine:
    """
    Formal state machine for the Mahoun legal reasoning pipeline.
    Enforces that verdicts cannot be generated without proper reasoning,
    and cannot be committed without generation.
    """
    def __init__(self):
        self.state = LegalState.IDLE
        self.state_lock = threading.RLock()
        self.failed_transitions = 0
        self.history: List[str] = []
        
        # Define valid transitions: dict[CurrentState, dict[Trigger, NextState]]
        self.transitions: Dict[LegalState, Dict[LegalTrigger, LegalState]] = {
            LegalState.IDLE: {
                LegalTrigger.START_INGESTION: LegalState.INGESTING
            },
            LegalState.INGESTING: {
                LegalTrigger.INGESTION_COMPLETE: LegalState.REASONING,
                LegalTrigger.ERROR_OCCURRED: LegalState.ERROR
            },
            LegalState.REASONING: {
                LegalTrigger.REASONING_COMPLETE: LegalState.VERDICT_GENERATION,
                LegalTrigger.ERROR_OCCURRED: LegalState.ERROR
            },
            LegalState.VERDICT_GENERATION: {
                LegalTrigger.VERDICT_READY: LegalState.LEDGER_COMMIT,
                LegalTrigger.ERROR_OCCURRED: LegalState.ERROR
            },
            LegalState.LEDGER_COMMIT: {
                LegalTrigger.COMMIT_SUCCESS: LegalState.COMPLETED,
                LegalTrigger.ERROR_OCCURRED: LegalState.ERROR
            },
            LegalState.ERROR: {
                LegalTrigger.RESET: LegalState.IDLE
            },
            LegalState.COMPLETED: {
                LegalTrigger.RESET: LegalState.IDLE
            }
        }
    
    def transition(self, trigger: LegalTrigger) -> tuple[bool, str]:
        """
        Transition to a new state based on a trigger.
        
        HARDENING B2-01: Removed force parameter - no bypass allowed.
        All transitions MUST follow valid transition rules.
        Emergency ERROR_OCCURRED transition is the only exception.
        
        Returns:
            (success: bool, message: str)
        """
        with self.state_lock:
            # Emergency transition to ERROR always allowed
            if trigger == LegalTrigger.ERROR_OCCURRED:
                self._do_transition(trigger, LegalState.ERROR)
                logger.warning(f"Emergency transition to ERROR from {self.state.value}")
                return True, "Emergency transition to ERROR"
            
            # Check valid transition
            valid_transitions = self.transitions.get(self.state, {})
            if trigger in valid_transitions:
                next_state = valid_transitions[trigger]
                self._do_transition(trigger, next_state)
                logger.info(f"Valid transition: {self.state.value} -> {trigger.value} -> {next_state.value}")
                return True, f"Transitioned to {next_state.value}"
            
            # Invalid transition - HARD REJECTION
            self.failed_transitions += 1
            msg = (
                f"INVALID TRANSITION REJECTED: Cannot trigger {trigger.value} "
                f"from state {self.state.value}. "
                f"Valid triggers from {self.state.value}: {[t.value for t in valid_transitions.keys()]}"
            )
            logger.error(msg)
            
            # Audit log the rejection
            self._audit_invalid_transition(trigger, msg)
            
            return False, msg
    
    def _audit_invalid_transition(self, trigger: LegalTrigger, reason: str) -> None:
        """
        Audit log for invalid transition attempts.
        
        HARDENING: All invalid transition attempts are recorded for security review.
        """
        audit_entry = {
            "timestamp": time.time(),
            "current_state": self.state.value,
            "attempted_trigger": trigger.value,
            "reason": reason,
            "failed_transition_count": self.failed_transitions,
        }
        logger.critical(f"AUDIT: Invalid transition attempt: {audit_entry}")
    
    def get_valid_triggers(self) -> List[str]:
        """Get list of valid triggers from current state"""
        return [t.value for t in self.transitions.get(self.state, {}).keys()]
            
    def _do_transition(self, trigger: LegalTrigger, next_state: LegalState):
        self.history.append(f"{self.state.value} -> {trigger.value} -> {next_state.value}")
        self.state = next_state
        logger.info(f"Legal state transitioned to {self.state.value}")
