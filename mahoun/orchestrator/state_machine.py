"""
State Machine
=============

Production-grade state machine with:
- Comprehensive state management
- Transition guards and conditions
- State entry/exit actions
- Rollback capabilities
- Detailed metrics and monitoring
- Thread-safe operations
"""

import time
import numpy as np
from dataclasses import dataclass, field
from threading import Lock, RLock
from collections import defaultdict, deque
from typing import Any, Callable, Dict, List, Optional, Tuple
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class SystemState(Enum):
    """System states with descriptions"""
    IDLE = "idle"
    COLLECTING = "collecting"
    LEARNING = "learning"
    VALIDATING = "validating"
    DEPLOYING = "deploying"
    MONITORING = "monitoring"
    ROLLBACK = "rollback"
    ERROR = "error"
    SHUTDOWN = "shutdown"
    
    def is_terminal(self) -> bool:
        """Check if state is terminal"""
        return self in {SystemState.SHUTDOWN, SystemState.ERROR}
    
    def is_operational(self) -> bool:
        """Check if state is operational"""
        return self in {
            SystemState.COLLECTING,
            SystemState.LEARNING,
            SystemState.VALIDATING,
            SystemState.DEPLOYING,
            SystemState.MONITORING
        }


class TransitionTrigger(Enum):
    """Transition triggers"""
    START = "start"
    FEEDBACK_THRESHOLD = "feedback_threshold"
    LEARNING_COMPLETE = "learning_complete"
    VALIDATION_PASSED = "validation_passed"
    VALIDATION_FAILED = "validation_failed"
    DEPLOYMENT_COMPLETE = "deployment_complete"
    ANOMALY_DETECTED = "anomaly_detected"
    MANUAL_ROLLBACK = "manual_rollback"
    ERROR_OCCURRED = "error_occurred"
    RECOVERY_COMPLETE = "recovery_complete"
    STOP = "stop"
    PAUSE = "pause"
    RESUME = "resume"


@dataclass
class StateTransition:
    """State transition record with full context"""
    from_state: SystemState
    to_state: SystemState
    trigger: TransitionTrigger
    timestamp: float
    duration_in_previous_state: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error_message: Optional[str] = None


@dataclass
class StateCondition:
    """Condition that must be met for transition"""
    name: str
    check: Callable[[], bool]
    description: str
    required: bool = True
    critical: bool = False  # HARDENING PATCH P16: Critical conditions cannot be bypassed by force=True
    
    def evaluate(self) -> tuple[bool, Optional[str]]:
        """Evaluate condition and return result with reason"""
        try:
            result = self.check()
            if not result:
                return False, f"Condition '{self.name}' not met: {self.description}"
            return True, None
        except Exception as e:
            return False, f"Condition '{self.name}' failed: {str(e)}"


@dataclass
class StateMetrics:
    """Metrics for a state"""
    entry_count: int = 0
    total_duration: float = 0.0
    min_duration: float = float('inf')
    max_duration: float = 0.0
    durations: deque = field(default_factory=lambda: deque(maxlen=100))
    error_count: int = 0
    last_entry: Optional[float] = None
    last_exit: Optional[float] = None
    
    def record_entry(self):
        """Record state entry"""
        self.entry_count += 1
        self.last_entry = time.time()
        
    def record_exit(self):
        """Record state exit"""
        if self.last_entry:
            duration = time.time() - self.last_entry
            self.total_duration += duration
            self.min_duration = min(self.min_duration, duration)
            self.max_duration = max(self.max_duration, duration)
            self.durations.append(duration)
            self.last_exit = time.time()
            
    def get_avg_duration(self) -> float:
        """Get average duration"""
        if self.entry_count == 0:
            return 0.0
        return self.total_duration / self.entry_count
    
    def get_recent_avg_duration(self, n: int = 10) -> float:
        """Get recent average duration"""
        if not self.durations:
            return 0.0
        recent = list(self.durations)[-n:]
        return sum(recent) / len(recent)


class StateMachine:
    """
    State Machine

    Features:
    - Thread-safe state transitions
    - Transition guards and conditions
    - State entry/exit callbacks
    - Comprehensive metrics
    - Rollback support
    - Transition history with analysis
    """
    
    def __init__(self, max_history: int = 1000):
        """
        Initialize state machine
        
        Args:
            max_history: Maximum transition history to keep
        """
        self.current_state = SystemState.IDLE
        self.previous_state: Optional[SystemState] = None
        self.state_lock = RLock()
        
        # History and metrics
        self.transition_history: deque[StateTransition] = deque(maxlen=max_history)
        self.state_metrics: Dict[SystemState, StateMetrics] = {
            state: StateMetrics() for state in SystemState
        }
        
        # Transition configuration
        self.valid_transitions = self._build_transition_table()
        self.transition_conditions: Dict[tuple[SystemState, TransitionTrigger], List[StateCondition]] = {}
        
        # Callbacks
        self.state_entry_callbacks: Dict[SystemState, List[Callable]] = defaultdict(list)
        self.state_exit_callbacks: Dict[SystemState, List[Callable]] = defaultdict(list)
        self.transition_callbacks: List[Callable[[StateTransition], None]] = []
        self.error_callbacks: List[Callable[[str, Exception], None]] = []
        
        # State timing
        self.state_entry_time: Optional[float] = None
        self.state_entry_time = time.time()
        
        # Statistics
        self.total_transitions = 0
        self.failed_transitions = 0
        self.error_count = 0
        self.rollback_count = 0
        
        # Rollback stack
        self.state_stack: List[SystemState] = [SystemState.IDLE]
        
        # Record initial state
        self.state_metrics[SystemState.IDLE].record_entry()
        
        logger.info("Initialized Advanced StateMachine")
        
    def _build_transition_table(self) -> Dict[SystemState, Dict[TransitionTrigger, SystemState]]:
        """Build comprehensive transition table"""
        return {
            SystemState.IDLE: {
                TransitionTrigger.START: SystemState.COLLECTING,
                TransitionTrigger.STOP: SystemState.SHUTDOWN,
            },
            SystemState.COLLECTING: {
                TransitionTrigger.FEEDBACK_THRESHOLD: SystemState.LEARNING,
                TransitionTrigger.ERROR_OCCURRED: SystemState.ERROR,
                TransitionTrigger.STOP: SystemState.SHUTDOWN,
                TransitionTrigger.PAUSE: SystemState.IDLE,
            },
            SystemState.LEARNING: {
                TransitionTrigger.LEARNING_COMPLETE: SystemState.VALIDATING,
                TransitionTrigger.ERROR_OCCURRED: SystemState.ERROR,
                TransitionTrigger.STOP: SystemState.SHUTDOWN,
            },
            SystemState.VALIDATING: {
                TransitionTrigger.VALIDATION_PASSED: SystemState.DEPLOYING,
                TransitionTrigger.VALIDATION_FAILED: SystemState.COLLECTING,
                TransitionTrigger.ERROR_OCCURRED: SystemState.ERROR,
                TransitionTrigger.STOP: SystemState.SHUTDOWN,
            },
            SystemState.DEPLOYING: {
                TransitionTrigger.DEPLOYMENT_COMPLETE: SystemState.MONITORING,
                TransitionTrigger.ERROR_OCCURRED: SystemState.ROLLBACK,
                TransitionTrigger.STOP: SystemState.SHUTDOWN,
            },
            SystemState.MONITORING: {
                TransitionTrigger.ANOMALY_DETECTED: SystemState.ROLLBACK,
                TransitionTrigger.FEEDBACK_THRESHOLD: SystemState.LEARNING,
                TransitionTrigger.MANUAL_ROLLBACK: SystemState.ROLLBACK,
                TransitionTrigger.STOP: SystemState.SHUTDOWN,
            },
            SystemState.ROLLBACK: {
                TransitionTrigger.RECOVERY_COMPLETE: SystemState.COLLECTING,
                TransitionTrigger.ERROR_OCCURRED: SystemState.ERROR,
                TransitionTrigger.STOP: SystemState.SHUTDOWN,
            },
            SystemState.ERROR: {
                TransitionTrigger.RECOVERY_COMPLETE: SystemState.IDLE,
                TransitionTrigger.STOP: SystemState.SHUTDOWN,
            },
            SystemState.SHUTDOWN: {},
        }
        
    def transition(
        self,
        trigger: TransitionTrigger,
        metadata: Optional[Dict[str, Any]] = None,
        force: bool = False
    ) -> tuple[bool, Optional[str]]:
        """
        Attempt state transition
        
        Args:
            trigger: Transition trigger
            metadata: Optional metadata
            force: Force transition even if conditions not met
            
        Returns:
            (success, error_message)
        """
        with self.state_lock:
            # Validate transition
            if not self._is_valid_transition(trigger):
                msg = f"Invalid transition: {self.current_state.value} with trigger {trigger.value}"
                logger.warning(msg)
                self.failed_transitions += 1
                return False, msg
                
            target_state = self.valid_transitions[self.current_state][trigger]
            
            # HARDENING PATCH P16: Evaluate conditions. If force=True, non-critical required conditions are bypassed, but critical ones are still enforced.
            conditions_met, reason = self._check_conditions(trigger, force)
            if not conditions_met:
                logger.warning(f"Transition conditions not met (force={force}): {reason}")
                self.failed_transitions += 1
                return False, reason
                    
            # Execute transition
            return self._execute_transition(target_state, trigger, metadata or {})
            
    def _is_valid_transition(self, trigger: TransitionTrigger) -> bool:
        """Check if transition is valid"""
        return trigger in self.valid_transitions.get(self.current_state, {})
        
    def _check_conditions(self, trigger: TransitionTrigger, force: bool = False) -> tuple[bool, Optional[str]]:
        """Check all conditions for transition. If force=True, ignores non-critical conditions."""
        key = (self.current_state, trigger)
        conditions = self.transition_conditions.get(key, [])
        
        for condition in conditions:
            met, reason = condition.evaluate()
            
            # If it failed, check if we must enforce it
            if not met:
                if condition.critical:
                    return False, f"[CRITICAL] {reason}"
                elif condition.required and not force:
                    return False, reason
                elif condition.required and force:
                    logger.warning(f"Force bypassing required condition: {condition.name}")
                
        return True, None
        
    def _execute_transition(
        self,
        target_state: SystemState,
        trigger: TransitionTrigger,
        metadata: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """Execute state transition with full lifecycle"""
        try:
            # Calculate duration in current state
            duration = time.time() - self.state_entry_time if self.state_entry_time else 0.0
            
            # Call exit callbacks
            self._call_exit_callbacks(target_state)
            
            # Record exit from current state
            self.state_metrics[self.current_state].record_exit()
            
            # Update state
            self.previous_state = self.current_state
            self.current_state = target_state
            self.state_entry_time = time.time()
            
            # Update state stack for rollback
            if target_state != SystemState.ROLLBACK:
                self.state_stack.append(target_state)
                if len(self.state_stack) > 10:
                    self.state_stack.pop(0)
                    
            # Record entry to new state
            self.state_metrics[target_state].record_entry()
            
            # Create transition record
            transition = StateTransition(
                from_state=self.previous_state,
                to_state=target_state,
                trigger=trigger,
                timestamp=time.time(),
                duration_in_previous_state=duration,
                metadata=metadata,
                success=True
            )
            
            self.transition_history.append(transition)
            self.total_transitions += 1
            
            # Update statistics
            if target_state == SystemState.ERROR:
                self.error_count += 1
            elif target_state == SystemState.ROLLBACK:
                self.rollback_count += 1
                
            # Call entry callbacks
            self._call_entry_callbacks(self.previous_state)
            
            # Call transition callbacks
            self._call_transition_callbacks(transition)
            
            # Log transition
            logger.info(
                f"State transition: {self.previous_state.value} → {target_state.value} "
                f"(trigger: {trigger.value}, duration: {duration:.2f}s)"
            )
            
            # Log metrics
            logger.info(
                "State transition: %s → %s (trigger: %s, duration: %.2fs)",
                self.previous_state.value,
                target_state.value,
                trigger.value,
                duration,
            )
            
            return True, None
            
        except Exception as e:
            error_msg = f"Transition execution failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self._call_error_callbacks(error_msg, e)
            
            # Record failed transition
            transition = StateTransition(
                from_state=self.previous_state or self.current_state,
                to_state=target_state,
                trigger=trigger,
                timestamp=time.time(),
                duration_in_previous_state=0.0,
                metadata=metadata,
                success=False,
                error_message=error_msg
            )
            self.transition_history.append(transition)
            self.failed_transitions += 1
            
            return False, error_msg
            
    def _call_exit_callbacks(self, target_state: SystemState):
        """Call exit callbacks for current state"""
        for callback in self.state_exit_callbacks[self.current_state]:
            try:
                callback(self.current_state, target_state)
            except Exception as e:
                logger.error(f"Exit callback failed: {e}")
                
    def _call_entry_callbacks(self, previous_state: SystemState):
        """Call entry callbacks for new state"""
        for callback in self.state_entry_callbacks[self.current_state]:
            try:
                callback(previous_state, self.current_state)
            except Exception as e:
                logger.error(f"Entry callback failed: {e}")
                
    def _call_transition_callbacks(self, transition: StateTransition):
        """Call transition callbacks"""
        for callback in self.transition_callbacks:
            try:
                callback(transition)
            except Exception as e:
                logger.error(f"Transition callback failed: {e}")
                
    def _call_error_callbacks(self, message: str, exception: Exception):
        """Call error callbacks"""
        for callback in self.error_callbacks:
            try:
                callback(message, exception)
            except Exception as e:
                logger.error(f"Error callback failed: {e}")
                
    def add_condition(
        self,
        state: SystemState,
        trigger: TransitionTrigger,
        name: str,
        check: Callable[[], bool],
        description: str,
        required: bool = True,
        critical: bool = False
    ):
        """Add transition condition"""
        key = (state, trigger)
        if key not in self.transition_conditions:
            self.transition_conditions[key] = []
            
        condition = StateCondition(name, check, description, required, critical)
        self.transition_conditions[key].append(condition)
        
        logger.info(f"Added condition for {state.value} + {trigger.value}: {name}")
        
    def register_state_entry_callback(self, state: SystemState, callback: Callable):
        """Register callback for state entry"""
        self.state_entry_callbacks[state].append(callback)
        
    def register_state_exit_callback(self, state: SystemState, callback: Callable):
        """Register callback for state exit"""
        self.state_exit_callbacks[state].append(callback)
        
    def register_transition_callback(self, callback: Callable):
        """Register callback for any transition"""
        self.transition_callbacks.append(callback)
        
    def register_error_callback(self, callback: Callable):
        """Register callback for errors"""
        self.error_callbacks.append(callback)
        
    def rollback_to_previous(self) -> tuple[bool, Optional[str]]:
        """Rollback to previous stable state"""
        if len(self.state_stack) < 2:
            return False, "No previous state to rollback to"
            
        previous = self.state_stack[-2]
        return self.transition(
            TransitionTrigger.MANUAL_ROLLBACK,
            metadata={"rollback_to": previous.value},
            force=True
        )
        
    def get_current_state(self) -> SystemState:
        """Get current state"""
        with self.state_lock:
            return self.current_state
            
    def get_state_duration(self) -> float:
        """Get duration in current state"""
        with self.state_lock:
            if self.state_entry_time:
                return time.time() - self.state_entry_time
            return 0.0
            
    def get_valid_triggers(self) -> List[TransitionTrigger]:
        """Get valid triggers for current state"""
        with self.state_lock:
            return list(self.valid_transitions.get(self.current_state, {}).keys())
            
    def get_transition_history(self, limit: Optional[int] = None) -> List[StateTransition]:
        """Get transition history"""
        with self.state_lock:
            history = list(self.transition_history)
            if limit:
                return history[-limit:]
            return history
            
    def get_state_metrics(self, state: Optional[SystemState] = None) -> Dict[str, Any]:
        """Get metrics for state(s)"""
        with self.state_lock:
            if state:
                metrics = self.state_metrics[state]
                return {
                    "entry_count": metrics.entry_count,
                    "total_duration": metrics.total_duration,
                    "avg_duration": metrics.get_avg_duration(),
                    "recent_avg_duration": metrics.get_recent_avg_duration(),
                    "min_duration": metrics.min_duration if metrics.min_duration != float('inf') else 0.0,
                    "max_duration": metrics.max_duration,
                    "error_count": metrics.error_count,
                }
            else:
                return {
                    state.value: {
                        "entry_count": m.entry_count,
                        "avg_duration": m.get_avg_duration(),
                        "recent_avg": m.get_recent_avg_duration(),
                    }
                    for state, m in self.state_metrics.items()
                    if m.entry_count > 0
                }
                
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics"""
        with self.state_lock:
            return {
                "current_state": self.current_state.value,
                "previous_state": self.previous_state.value if self.previous_state else None,
                "state_duration": self.get_state_duration(),
                "total_transitions": self.total_transitions,
                "failed_transitions": self.failed_transitions,
                "success_rate": (self.total_transitions - self.failed_transitions) / max(self.total_transitions, 1),
                "error_count": self.error_count,
                "rollback_count": self.rollback_count,
                "state_metrics": self.get_state_metrics(),
                "recent_transitions": [
                    {
                        "from": t.from_state.value,
                        "to": t.to_state.value,
                        "trigger": t.trigger.value,
                        "duration": t.duration_in_previous_state,
                        "success": t.success,
                    }
                    for t in list(self.transition_history)[-10:]
                ],
            }
            
    def reset(self):
        """Reset state machine to IDLE"""
        with self.state_lock:
            self.current_state = SystemState.IDLE
            self.previous_state = None
            self.state_entry_time = time.time()
            self.state_stack = [SystemState.IDLE]
            
        logger.info("State machine reset to IDLE")
