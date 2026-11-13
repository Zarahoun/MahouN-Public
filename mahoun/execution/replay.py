"""
Request Replay
==============

Request replay capability for debugging and verification.

Features:
- Exact request replay with same seed
- Replay verification (checksum matching)
- Replay diff analysis
- Batch replay
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ReplayableRequest:
    """
    Replayable request with all necessary information.
    """
    request_id: str
    timestamp: datetime
    seed: int
    handler_name: str
    input_data: Dict[str, Any]
    output_data: Optional[Any] = None
    error: Optional[str] = None
    checksum: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReplayableRequest":
        """Create from dictionary"""
        data = data.copy()
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)
    
    def to_json(self) -> str:
        """Convert to JSON"""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
    
    @classmethod
    def from_json(cls, json_str: str) -> "ReplayableRequest":
        """Create from JSON"""
        return cls.from_dict(json.loads(json_str))


@dataclass
class ReplayResult:
    """
    Replay result with verification.
    """
    original: ReplayableRequest
    replayed: ReplayableRequest
    checksum_match: bool
    output_match: bool
    diff: Optional[Dict[str, Any]] = None
    
    def is_exact_match(self) -> bool:
        """Check if replay is exact match"""
        return self.checksum_match and self.output_match


class RequestReplay:
    """
    Production-grade request replay system.
    
    Features:
    - Store replayable requests
    - Exact replay with same seed
    - Replay verification
    - Diff analysis
    - Batch replay
    
    Usage:
        replay = RequestReplay(storage_dir="./replay_storage")
        
        # Store request
        request = ReplayableRequest(
            request_id="req_123",
            timestamp=datetime.now(timezone.utc),
            seed=42,
            handler_name="verdict_engine",
            input_data={"query": "test"},
            output_data={"result": "success"},
            checksum="abc123"
        )
        replay.store(request)
        
        # Replay request
        result = await replay.replay(
            request_id="req_123",
            handler=my_handler
        )
        
        if result.is_exact_match():
            print("Replay verified!")
    """
    
    def __init__(
        self,
        storage_dir: str = "./replay_storage",
        enable_auto_store: bool = True
    ):
        """
        Initialize request replay.
        
        Args:
            storage_dir: Directory to store replayable requests
            enable_auto_store: Auto-store all requests
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.enable_auto_store = enable_auto_store
        
        logger.info(f"RequestReplay initialized (storage={storage_dir})")
    
    def store(self, request: ReplayableRequest) -> None:
        """
        Store replayable request.
        
        Args:
            request: ReplayableRequest to store
        """
        # Store as JSON file
        filename = f"{request.request_id}.json"
        filepath = self.storage_dir / filename
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(request.to_json())
            
            logger.debug(f"Stored replayable request: {request.request_id}")
            
        except Exception as e:
            logger.error(f"Failed to store request {request.request_id}: {e}")
    
    def load(self, request_id: str) -> Optional[ReplayableRequest]:
        """
        Load replayable request.
        
        Args:
            request_id: Request ID to load
            
        Returns:
            ReplayableRequest or None if not found
        """
        filename = f"{request_id}.json"
        filepath = self.storage_dir / filename
        
        if not filepath.exists():
            logger.warning(f"Request {request_id} not found in storage")
            return None
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return ReplayableRequest.from_json(f.read())
                
        except Exception as e:
            logger.error(f"Failed to load request {request_id}: {e}")
            return None
    
    async def replay(
        self,
        request_id: str,
        handler: Any,
        verify: bool = True
    ) -> ReplayResult:
        """
        Replay a request.
        
        Args:
            request_id: Request ID to replay
            handler: Handler function to execute
            verify: Verify replay against original
            
        Returns:
            ReplayResult with verification
            
        Raises:
            ValueError: If request not found
        """
        # Load original request
        original = self.load(request_id)
        if not original:
            raise ValueError(f"Request {request_id} not found")
        
        logger.info(f"Replaying request {request_id} (seed={original.seed})")
        
        # Set seed for deterministic execution
        self._set_seed(original.seed)
        
        # Execute handler
        try:
            # Import execution controller
            from .controller import ExecutionContext
            
            # Create replay context
            context = ExecutionContext(
                request_id=f"{request_id}_replay",
                timestamp=datetime.now(timezone.utc),
                seed=original.seed,
                replay_of=request_id,
                metadata={"replay": True}
            )
            
            # Execute
            output = await handler(context, original.input_data)
            
            # Create replayed request
            replayed = ReplayableRequest(
                request_id=f"{request_id}_replay",
                timestamp=datetime.now(timezone.utc),
                seed=original.seed,
                handler_name=original.handler_name,
                input_data=original.input_data,
                output_data=output,
                metadata={"replayed_from": request_id}
            )
            
            # Compute checksum
            replayed.checksum = self._compute_checksum(replayed)
            
            # Verify if requested
            if verify:
                checksum_match = (replayed.checksum == original.checksum)
                output_match = self._compare_outputs(
                    original.output_data,
                    replayed.output_data
                )
                diff = self._compute_diff(
                    original.output_data,
                    replayed.output_data
                ) if not output_match else None
                
                result = ReplayResult(
                    original=original,
                    replayed=replayed,
                    checksum_match=checksum_match,
                    output_match=output_match,
                    diff=diff
                )
                
                if result.is_exact_match():
                    logger.info(f"Replay verified: exact match")
                else:
                    logger.warning(
                        f"Replay mismatch: "
                        f"checksum={checksum_match}, output={output_match}"
                    )
                
                return result
            else:
                return ReplayResult(
                    original=original,
                    replayed=replayed,
                    checksum_match=False,
                    output_match=False
                )
                
        except Exception as e:
            logger.error(f"Replay failed: {e}", exc_info=True)
            
            # Create failed replay
            replayed = ReplayableRequest(
                request_id=f"{request_id}_replay",
                timestamp=datetime.now(timezone.utc),
                seed=original.seed,
                handler_name=original.handler_name,
                input_data=original.input_data,
                error=str(e),
                metadata={"replayed_from": request_id}
            )
            
            return ReplayResult(
                original=original,
                replayed=replayed,
                checksum_match=False,
                output_match=False,
                diff={"error": str(e)}
            )
    
    async def batch_replay(
        self,
        request_ids: List[str],
        handler: Any,
        verify: bool = True
    ) -> List[ReplayResult]:
        """
        Replay multiple requests.
        
        Args:
            request_ids: List of request IDs
            handler: Handler function
            verify: Verify replays
            
        Returns:
            List of ReplayResult
        """
        results = []
        
        for request_id in request_ids:
            try:
                result = await self.replay(request_id, handler, verify)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to replay {request_id}: {e}")
        
        # Log summary
        if verify:
            exact_matches = sum(1 for r in results if r.is_exact_match())
            logger.info(
                f"Batch replay complete: {exact_matches}/{len(results)} exact matches"
            )
        
        return results
    
    def list_requests(
        self,
        limit: int = 100,
        handler_name: Optional[str] = None
    ) -> List[str]:
        """
        List stored requests.
        
        Args:
            limit: Maximum number of requests
            handler_name: Filter by handler name
            
        Returns:
            List of request IDs
        """
        request_ids = []
        
        for filepath in sorted(self.storage_dir.glob("*.json"), reverse=True):
            if len(request_ids) >= limit:
                break
            
            # Load and check filter
            if handler_name:
                try:
                    request = self.load(filepath.stem)
                    if request and request.handler_name == handler_name:
                        request_ids.append(filepath.stem)
                except Exception:
                    logger.debug(f"Skipping unreadable request at {filepath}")
            else:
                request_ids.append(filepath.stem)
        
        return request_ids
    
    def _set_seed(self, seed: int) -> None:
        """Set seed for all RNGs"""
        import random
        import numpy as np
        
        random.seed(seed)
        np.random.seed(seed)
        
        try:
            import torch
            torch.manual_seed(seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(seed)
        except ImportError:
            pass
    
    def _compute_checksum(self, request: ReplayableRequest) -> str:
        """Compute checksum for request"""
        import hashlib
        
        data = f"{request.request_id}:{request.seed}:{str(request.output_data)}"
        return hashlib.sha256(data.encode()).hexdigest()
    
    def _compare_outputs(self, output1: Any, output2: Any) -> bool:
        """Compare two outputs"""
        try:
            return output1 == output2
        except Exception:
            return str(output1) == str(output2)
    
    def _compute_diff(self, output1: Any, output2: Any) -> Dict[str, Any]:
        """Compute diff between outputs"""
        return {
            "original": str(output1)[:1000],  # Truncate for readability
            "replayed": str(output2)[:1000],
            "type_match": type(output1) == type(output2),
        }
