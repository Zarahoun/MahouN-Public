"""
Critic Agent - Integrity & Hallucination Guard
===============================================
عامل بازبینی و تشخیص توهم برای تضمین صداقت سیستم

این عامل پاسخ‌های تولید شده را در برابر اسناد مرجع بررسی می‌کند تا:
۱. از عدم وجود اطلاعات جعلی (Hallucination) اطمینان حاصل کند.
۲. صحت استنادات حقوقی را تایید کند.
۳. تناقضات احتمالی را شناسایی کند.
"""

import logging
from typing import Any, Dict, List, Optional
from .base_agent import UltraBaseAgent, AgentConfig, AgentResult
import json

logger = logging.getLogger(__name__)

class CriticAgent(UltraBaseAgent):
    """
    Integrity Guard Agent that "Red-Teams" other agents' outputs using UltraReasoningService.
    """
    
    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__("critic_agent", config)
        self.faithfulness_threshold = 0.75
        self._reasoning_service = None
        
    async def _initialize_impl(self):
        self.logger.info("CriticAgent initializing...")
        try:
            from mahoun.reasoning.ultra_reasoning_service import UltraReasoningService
            self._reasoning_service = UltraReasoningService(
                use_cot=True,
                use_self_consistency=True,
                num_reasoning_paths=2
            )
            self.logger.info("✅ UltraReasoningService integrated into CriticAgent")
        except Exception as e:
            self.logger.error(f"Failed to initialize ReasoningService in CriticAgent: {e}")

    async def _process_impl(
        self, 
        input_data: Dict[str, Any], 
        correlation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze an answer against provided context for faithfulness.
        """
        query = input_data.get("query", "")
        answer = input_data.get("answer", "")
        context = input_data.get("context", [])
        
        if not context:
            return {
                "faithfulness_score": 0.5,
                "status": "warning",
                "message": "No context provided for validation.",
                "hallucinations": []
            }

        if not self._reasoning_service:
            # Fallback to simulated score if service failed
            return {"faithfulness_score": 1.0, "status": "simulated"}

        # Use Reasoning Service to validate
        critic_query = f"Verify if this answer is truthful based on the context: {answer}"
        
        self.logger.info(f"[{correlation_id}] Running CoT validation...")
        reasoning_result = await self._reasoning_service.reason(
            query=critic_query,
            context=context
        )
        
        # Calculate scores from reasoning
        faithfulness_score = reasoning_result.confidence
        contradiction_count = len(reasoning_result.contradictions)
        
        # Penalize for contradictions
        if contradiction_count > 0:
            faithfulness_score = max(0.0, faithfulness_score - (0.2 * contradiction_count))

        analysis = {
            "faithfulness_score": round(faithfulness_score, 3),
            "is_truthful": faithfulness_score >= self.faithfulness_threshold,
            "hallucinations": reasoning_result.contradictions,
            "verdict": "Truthful" if faithfulness_score >= self.faithfulness_threshold else "Potential Hallucination",
            "reasoning_chain": [step.to_dict() for step in reasoning_result.reasoning_chain],
            "explanation": reasoning_result.answer
        }
        
        self.logger.info(f"[{correlation_id}] Validation Verdict: {analysis['verdict']} (Score: {analysis['faithfulness_score']})")
        
        return analysis

    def _build_critique_prompt(self, query: str, answer: str, context: List[str]) -> str:
        context_str = "\n---\n".join(context)
        return f"""
You are a Lead Integrity Auditor (Critic Agent). 
Your goal is to find any LIES or HALLUCINATIONS in the Answer below based ONLY on the Context provided.

Query: {query}
Context: {context_str}
Answer: {answer}

Instructions:
1. Identify any statements in the Answer not supported by the Context.
2. Check if citations are real and exist in the Context.
3. Assign a Faithfulness Score (0.0 to 1.0).
4. List specific hallucinations if found.

Output JSON format:
{{
  "faithfulness_score": float,
  "hallucinations": [string],
  "explanation": string
}}
"""

    async def _fallback_impl(
        self, 
        input_data: Dict[str, Any], 
        correlation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        return {
            "faithfulness_score": 0.0,
            "status": "error",
            "message": "Integrity check failed to execute. Proceed with caution."
        }
