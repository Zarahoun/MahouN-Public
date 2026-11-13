"""
LLMLoaderCoordinator - Thin Orchestration Layer

Responsibility: Coordinate LLM loading using injected services.
This coordinator contains ZERO business logic — only orchestration!

Architecture:
- All business logic delegated to services
- Services injected via ServiceContainer
- Coordinator = thin orchestration glue
- Handles both local and Ollama-based LLMs
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


class LLMLoaderCoordinator(BootstrapPhaseExecutor):
    """
    Thin coordinator for LLM loading orchestration
    
    Workflow:
    1. Create rollback checkpoint
    2. Resolve LLM spec for profile
    3. Verify model availability (local/Ollama)
    4. Load/connect to LLM
    5. Health check LLM
    6. Benchmark performance
    7. Register in context
    8. Rollback on failure
    
    Supports:
    - Local LLMs (transformers, llama.cpp)
    - Ollama-served LLMs
    - Quantized models (INT8, INT4)
    """
    
    def __init__(self, service_container: ServiceContainer):
        self.container = service_container
        self._phase_name = "llm_loader"
    
    async def execute(self, context: BootstrapContext) -> PhaseResult:
        """Execute LLM loading orchestration"""
        start_time = datetime.utcnow()
        checkpoint_id = f"llm_load_{int(start_time.timestamp())}"
        
        logger.info("Starting LLM loading orchestration")
        
        try:
            # Step 1: Create rollback checkpoint
            checkpoint = self.container.rollback_manager.create_checkpoint(
                checkpoint_id=checkpoint_id,
                metadata={"phase": "llm_loader", "profile": context.runtime_profile}
            )
            
            # Step 2: Resolve LLM spec for profile
            profile = context.runtime_profile
            llm_spec = self.container.model_resolver.resolve_llm_model(
                profile=profile
            )
            
            logger.info(
                f"Resolved LLM: {llm_spec.model_name} "
                f"(type: {llm_spec.model_type}, size: {llm_spec.size_mb}MB)"
            )
            
            # Step 3: Verify model availability/integrity
            if llm_spec.checksum_sha256 and llm_spec.model_path:
                integrity_result = await self.container.integrity_verifier.verify_model(
                    model_name=llm_spec.model_name,
                    expected_checksum=llm_spec.checksum_sha256,
                    model_path=llm_spec.model_path
                )
                
                if not integrity_result.is_valid:
                    raise BootstrapException(
                        f"LLM integrity check failed: {integrity_result.error_message}"
                    )
            
            # Step 4: Load/Connect to LLM
            load_result = await self.container.model_loader.load_model(
                model_name=llm_spec.model_name,
                loader_func=self._create_llm_loader(llm_spec),
                metadata={
                    "profile": profile,
                    "model_type": llm_spec.model_type,
                    "quantization": llm_spec.quantization
                }
            )
            
            if not load_result.success:
                raise BootstrapException(
                    f"Failed to load LLM after {load_result.attempts} attempts: {load_result.error}"
                )
            
            llm = load_result.model
            logger.info(
                f"LLM loaded: {llm_spec.model_name} "
                f"(duration: {load_result.duration_seconds:.2f}s)"
            )
            
            # Step 5: Register cleanup
            self.container.rollback_manager.register_resource(
                checkpoint_id=checkpoint_id,
                resource_type=ResourceType.MODEL,
                identifier=f"llm_{llm_spec.model_name}",
                cleanup_func=lambda: self._cleanup_llm(llm, llm_spec),
                metadata={"model_type": "llm"}
            )
            
            # Step 6: Health check
            health_result = await self.container.health_checker.check_health(
                model_name=llm_spec.model_name,
                model=llm,
                inference_func=lambda m: self._test_llm_inference(m, llm_spec),
                baseline_duration_seconds=llm_spec.baseline_latency_ms / 1000 if llm_spec.baseline_latency_ms else None
            )
            
            if health_result.status == HealthStatus.UNHEALTHY:
                logger.error(f"LLM health check failed: {health_result.errors}")
                await self.container.rollback_manager.rollback(checkpoint_id)
                raise BootstrapException(f"LLM health check failed: {health_result.errors}")
            
            # Step 7: Benchmark (optional)
            benchmark_result = None
            if context.config.get("enable_benchmarking", True):
                try:
                    benchmark_result = await asyncio.wait_for(
                        self.container.benchmark_service.benchmark_model(
                            model_name=llm_spec.model_name,
                            model=llm,
                            inference_func=lambda m: self._test_llm_inference(m, llm_spec),
                            sample_input="What is the legal definition of contract?",
                            metadata={"profile": profile, "model_type": "llm"}
                        ),
                        timeout=120.0  # 2 minutes for LLM benchmark
                    )
                    
                    logger.info(
                        f"LLM benchmark: latency={benchmark_result.latency_ms.mean:.2f}ms "
                        f"(p95={benchmark_result.latency_ms.p95:.2f}ms)"
                    )
                except asyncio.TimeoutError:
                    logger.warning("LLM benchmark timeout, skipping")
            
            # Step 8: Register in context
            context.shared_state["llm"] = llm
            context.shared_state["llm_name"] = llm_spec.model_name
            context.shared_state["llm_type"] = llm_spec.model_type
            context.shared_state["llm_profile"] = profile
            
            # Remove checkpoint
            self.container.rollback_manager.remove_checkpoint(checkpoint_id)
            
            # Success!
            duration = (datetime.utcnow() - start_time).total_seconds()
            
            return PhaseResult(
                success=True,
                phase_name=self._phase_name,
                duration_seconds=duration,
                data={
                    "model_name": llm_spec.model_name,
                    "model_type": llm_spec.model_type,
                    "profile": profile,
                    "health_status": health_result.status.value,
                    "load_duration": load_result.duration_seconds,
                    "benchmark_latency_ms": benchmark_result.latency_ms.mean if benchmark_result else None,
                },
                metadata={
                    "size_mb": llm_spec.size_mb,
                    "quantization": llm_spec.quantization,
                    "load_attempts": load_result.attempts,
                }
            )
        
        except Exception as e:
            logger.error(f"LLM loading failed: {e}", exc_info=True)
            
            # Rollback on failure
            try:
                rollback_result = await self.container.rollback_manager.rollback(
                    checkpoint_id=checkpoint_id,
                    ignore_errors=True
                )
            except Exception as rollback_error:
                logger.error(f"LLM rollback failed: {rollback_error}")
            
            duration = (datetime.utcnow() - start_time).total_seconds()
            
            return PhaseResult(
                success=False,
                phase_name=self._phase_name,
                duration_seconds=duration,
                error=str(e),
                data={},
                metadata={"checkpoint_id": checkpoint_id}
            )
    
    def _create_llm_loader(self, llm_spec):
        """Create loader function for LLM"""
        async def loader():
            model_type = llm_spec.model_type
            model_name = llm_spec.model_name
            
            logger.info(f"Loading LLM: {model_name} (type: {model_type})")
            
            if model_type == "ollama":
                # Ollama-based LLM
                from ollama import AsyncClient
                
                client = AsyncClient()
                
                # Test connection
                try:
                    models = await client.list()
                    available_models = [m['name'] for m in models['models']]
                    
                    if model_name not in available_models:
                        # Try to pull the model
                        logger.info(f"Pulling Ollama model: {model_name}")
                        await client.pull(model_name)
                    
                    return client
                except Exception as e:
                    raise RuntimeError(f"Failed to connect to Ollama or pull model {model_name}: {e}")
            
            elif model_type == "transformers":
                # HuggingFace transformers
                from transformers import AutoTokenizer, AutoModelForCausalLM
                import torch
                
                tokenizer = AutoTokenizer.from_pretrained(model_name)
                model = AutoModelForCausalLM.from_pretrained(
                    model_name,
                    torch_dtype=torch.float16 if llm_spec.quantization == "fp16" else torch.float32,
                    device_map="auto" if torch.cuda.is_available() else None
                )
                
                return {"model": model, "tokenizer": tokenizer}
            
            elif model_type == "llama_cpp":
                # llama.cpp based
                from llama_cpp import Llama
                
                model_path = llm_spec.model_path
                if not model_path or not model_path.exists():
                    raise RuntimeError(f"llama.cpp model file not found: {model_path}")
                
                model = Llama(
                    model_path=str(model_path),
                    n_ctx=4096,  # Context window
                    n_gpu_layers=32 if torch.cuda.is_available() else 0,
                    verbose=False
                )
                
                return model
            
            else:
                raise RuntimeError(f"Unsupported LLM type: {model_type}")
        
        return loader
    
    async def _test_llm_inference(self, llm, llm_spec):
        """Test LLM inference for health check"""
        model_type = llm_spec.model_type
        test_prompt = "What is law?"
        
        try:
            if model_type == "ollama":
                response = await llm.generate(
                    model=llm_spec.model_name,
                    prompt=test_prompt,
                    options={"num_predict": 10}  # Short response
                )
                return response['response']
            
            elif model_type == "transformers":
                model = llm["model"]
                tokenizer = llm["tokenizer"]
                
                inputs = tokenizer.encode(test_prompt, return_tensors="pt")
                if hasattr(model, 'device'):
                    inputs = inputs.to(model.device)
                
                with torch.no_grad():
                    outputs = model.generate(
                        inputs,
                        max_new_tokens=10,
                        do_sample=False,
                        pad_token_id=tokenizer.eos_token_id
                    )
                
                response = tokenizer.decode(outputs[0], skip_special_tokens=True)
                return response
            
            elif model_type == "llama_cpp":
                response = llm(
                    test_prompt,
                    max_tokens=10,
                    temperature=0.0,
                    echo=False
                )
                return response['choices'][0]['text']
            
            else:
                raise RuntimeError(f"Unsupported model type for inference: {model_type}")
        
        except Exception as e:
            logger.error(f"LLM inference test failed: {e}")
            raise
    
    async def _cleanup_llm(self, llm, llm_spec):
        """Cleanup LLM resources"""
        try:
            model_type = llm_spec.model_type
            
            if model_type == "ollama":
                # Ollama client cleanup
                if hasattr(llm, 'close'):
                    await llm.close()
            
            elif model_type == "transformers":
                # Move to CPU and clear cache
                model = llm["model"]
                if hasattr(model, 'to'):
                    model.to('cpu')
                
                del llm["model"]
                del llm["tokenizer"]
                
                import gc
                gc.collect()
                
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except ImportError:
                    pass
            
            elif model_type == "llama_cpp":
                # llama.cpp cleanup
                if hasattr(llm, 'close'):
                    llm.close()
                del llm
            
            logger.debug(f"LLM cleanup complete: {llm_spec.model_name}")
        
        except Exception as e:
            logger.warning(f"LLM cleanup error: {e}")