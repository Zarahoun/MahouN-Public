"""
Base Domain Engine
==================

کلاس پایه برای تمام Domain Engines
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class BaseDomainEngine(ABC):
    """
    کلاس پایه برای Domain Engines
    
    هر Domain Engine باید:
    1. یک نام منحصر به فرد داشته باشد
    2. متد analyze را پیاده‌سازی کند
    3. قابلیت export نتایج را داشته باشد
    """
    
    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        """
        Initialize domain engine
        
        Args:
            name: نام منحصر به فرد engine
            config: تنظیمات engine
        """
        self.name = name
        self.config = config or {}
        self.logger = logging.getLogger(f"{__name__}.{name}")
        self.logger.info(f"Initialized {name} engine")
    
    @abstractmethod
    async def analyze(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        تحلیل داده‌های ورودی
        
        Args:
            input_data: داده‌های ورودی
            
        Returns:
            نتیجه تحلیل
        """
        raise NotImplementedError(f"{self.name} must implement analyze()")
    
    async def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """
        اعتبارسنجی ورودی
        
        Args:
            input_data: داده‌های ورودی
            
        Returns:
            True اگر ورودی معتبر باشد
        """
        return True
    
    def export_results(self, results: Dict[str, Any], format: str = "json") -> Any:
        """
        Export نتایج به فرمت‌های مختلف
        
        Args:
            results: نتایج تحلیل
            format: فرمت خروجی (json, dict, etc.)
            
        Returns:
            نتایج در فرمت مورد نظر
        """
        if format == "json":
            return results
        elif format == "dict":
            return results
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    def get_status(self) -> Dict[str, Any]:
        """
        دریافت وضعیت engine
        
        Returns:
            اطلاعات وضعیت
        """
        return {
            "name": self.name,
            "status": "ready",
            "config": self.config
        }

