"""
Risk Assessment Agent
====================

Agent برای ارزیابی ریسک دعوی
"""

from typing import Any, Dict, List, Optional
import logging

from .legacy_adapter import LegacyBaseAgent as BaseAgent

logger = logging.getLogger(__name__)


class RiskAssessmentAgent(BaseAgent):
    """
    Agent برای ارزیابی ریسک دعوی
    
    ویژگی‌ها:
    - تحلیل نقاط قوت/ضعف
    - احتمال موفقیت
    - توصیه‌های استراتژیک
    - Cost-benefit analysis
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("risk_assessment_agent", config)
        self.rag_service = None
        self.reasoning_service = None
        self.dispute_agent = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize dependencies"""
        if self._initialized:
            return
        
        try:
            from mahoun.rag.hybrid_rag_service import create_hybrid_rag_service
            from .dispute_agent import DisputeAgent
            
            self.rag_service = await create_hybrid_rag_service()
            self.dispute_agent = DisputeAgent()
            await self.dispute_agent.initialize()
            
            try:
                from mahoun.reasoning.ultra_reasoning_service import UltraReasoningService
                self.reasoning_service = UltraReasoningService()
            except Exception as e:
                self.logger.warning(f"Could not initialize UltraReasoningService: {e}")
                self.reasoning_service = None
            
            self._initialized = True
            self.logger.info("✅ RiskAssessmentAgent fully initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize RiskAssessmentAgent: {e}", exc_info=True)
            raise
    
    async def _process_impl(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        ارزیابی ریسک دعوی
        
        Args:
            input_data: شامل:
                - case_description: شرح پرونده
                - documents: مدارک
                - claim_type: نوع دعوی
        
        Returns:
            نتیجه شامل:
                - overall_risk: ریسک کلی
                - success_probability: احتمال موفقیت
                - strengths: نقاط قوت
                - weaknesses: نقاط ضعف
                - recommendations: توصیه‌ها
                - cost_benefit: تحلیل هزینه-فایده
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            case_description = input_data.get("case_description", "")
            documents = input_data.get("documents", [])
            claim_type = input_data.get("claim_type", "")
            
            # Step 1: Analyze disputes
            dispute_result = await self.dispute_agent.process({
                "query": case_description,
                "documents": documents
            })
            
            # Step 2: Assess strengths and weaknesses
            strengths, weaknesses = await self._assess_strengths_weaknesses(
                case_description,
                dispute_result,
                documents
            )
            
            # Step 3: Calculate success probability
            success_prob = await self._calculate_success_probability(
                strengths,
                weaknesses,
                dispute_result
            )
            
            # Step 4: Overall risk assessment
            overall_risk = self._calculate_overall_risk(
                success_prob,
                dispute_result.get("risk_assessment", {})
            )
            
            # Step 5: Cost-benefit analysis
            cost_benefit = await self._analyze_cost_benefit(
                claim_type,
                success_prob,
                overall_risk
            )
            
            # Step 6: Strategic recommendations
            recommendations = await self._generate_strategic_recommendations(
                overall_risk,
                success_prob,
                strengths,
                weaknesses
            )
            
            return {
                "success": True,
                "overall_risk": overall_risk,
                "success_probability": success_prob,
                "strengths": strengths,
                "weaknesses": weaknesses,
                "cost_benefit": cost_benefit,
                "recommendations": recommendations,
                "dispute_analysis": dispute_result.get("risk_assessment", {}),
                "metadata": {
                    "risk_level": overall_risk.get("level"),
                    "confidence": overall_risk.get("confidence", 0.0)
                }
            }
            
        except Exception as e:
            return await self.handle_error(e, input_data)
    
    async def _assess_strengths_weaknesses(
        self,
        case_description: str,
        dispute_result: Dict[str, Any],
        documents: List[str]
    ) -> tuple[List[str], List[str]]:
        """ارزیابی نقاط قوت و ضعف"""
        strengths: List[Any] = []
        weaknesses: List[Any] = []
        # Analyze disputes
        disputes = dispute_result.get("disputes", [])
        violations = dispute_result.get("violations", [])
        
        # Strengths
        if len(documents) > 5:
            strengths.append("مستندات کامل و کافی")
        
        if len(violations) == 0:
            strengths.append("عدم نقض تعهدات از طرف شما")
        
        low_severity_disputes = [d for d in disputes if d.get("severity") in ["low", "medium"]]
        if len(low_severity_disputes) > len(disputes) / 2:
            strengths.append("اکثر اختلافات با severity پایین")
        
        # Weaknesses
        if len(disputes) > 10:
            weaknesses.append("تعداد زیاد اختلافات")
        
        critical_disputes = [d for d in disputes if d.get("severity") == "critical"]
        if critical_disputes:
            weaknesses.append(f"{len(critical_disputes)} اختلاف بحرانی")
        
        if len(documents) < 3:
            weaknesses.append("مستندات ناکافی")
        
        return strengths, weaknesses
    
    async def _calculate_success_probability(
        self,
        strengths: List[str],
        weaknesses: List[str],
        dispute_result: Dict[str, Any]
    ) -> float:
        """محاسبه احتمال موفقیت"""
        base_prob = 0.5
        
        # Adjust based on strengths
        strength_bonus = len(strengths) * 0.1
        base_prob += min(0.3, strength_bonus)
        
        # Adjust based on weaknesses
        weakness_penalty = len(weaknesses) * 0.1
        base_prob -= min(0.3, weakness_penalty)
        
        # Adjust based on risk assessment
        risk_assessment = dispute_result.get("risk_assessment", {})
        risk_level = risk_assessment.get("overall_risk", "medium")
        
        risk_adjustments = {
            "critical": -0.2,
            "high": -0.1,
            "medium": 0.0,
            "low": 0.1
        }
        base_prob += risk_adjustments.get(risk_level, 0.0)
        
        # Clamp between 0 and 1
        return max(0.0, min(1.0, base_prob))
    
    def _calculate_overall_risk(
        self,
        success_prob: float,
        dispute_risk: Dict[str, Any]
    ) -> Dict[str, Any]:
        """محاسبه ریسک کلی"""
        # Combine success probability and dispute risk
        risk_score = (1 - success_prob) * 0.6 + (dispute_risk.get("risk_score", 0.5) / 3) * 0.4
        
        if risk_score > 0.7:
            level = "high"
        elif risk_score > 0.4:
            level = "medium"
        else:
            level = "low"
        
        return {
            "level": level,
            "score": risk_score,
            "confidence": 0.8
        }
    
    async def _analyze_cost_benefit(
        self,
        claim_type: str,
        success_prob: float,
        overall_risk: Dict[str, Any]
    ) -> Dict[str, Any]:
        """تحلیل هزینه-فایده"""
        # Simple cost-benefit analysis
        estimated_cost = {
            "low": 10000000,  # 10M
            "medium": 50000000,  # 50M
            "high": 100000000  # 100M
        }.get(overall_risk.get("level", "medium"), 50000000)
        
        expected_value = estimated_cost * success_prob
        
        return {
            "estimated_cost": estimated_cost,
            "success_probability": success_prob,
            "expected_value": expected_value,
            "risk_level": overall_risk.get("level"),
            "recommendation": "مثبت" if expected_value > estimated_cost * 0.6 else "منفی"
        }
    
    async def _generate_strategic_recommendations(
        self,
        overall_risk: Dict[str, Any],
        success_prob: float,
        strengths: List[str],
        weaknesses: List[str]
    ) -> List[str]:
        """تولید توصیه‌های استراتژیک"""
        recommendations: List[Any] = []
        risk_level = overall_risk.get("level", "medium")
        
        if risk_level == "high":
            recommendations.append("⚠️ ریسک بالا - نیاز به مشورت با وکیل متخصص")
            recommendations.append("جمع‌آوری مستندات بیشتر قبل از اقدام")
        
        if success_prob < 0.4:
            recommendations.append("احتمال موفقیت پایین - بررسی امکان سازش")
        
        if len(weaknesses) > len(strengths):
            recommendations.append("نقاط ضعف بیشتر از نقاط قوت - نیاز به تقویت پرونده")
        
        if success_prob > 0.7 and risk_level == "low":
            recommendations.append("✅ شرایط مناسب برای پیگیری دعوی")
        
        return recommendations

