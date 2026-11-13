"""
Metrics Tracker
===============

Track and compute evaluation metrics.
"""


from typing import List, Dict, Any

import numpy as np

from mahoun.pipelines._logging import setup_logger

log = setup_logger("metrics_tracker")


class MetricsTracker:
    """
    Track and compute evaluation metrics
    
    Metrics:
    - Retrieval: Recall@k, Precision@k, MRR
    - Reasoning: EM, F1
    - Trust: Unsupported rate
    - Ops: Latency, Token count
    """
    
    def __init__(self):
        """Initialize metrics tracker"""
        self.metrics: Dict[str, List[float]] = defaultdict(list)
        log.info("Initialized MetricsTracker")
    
    def add_metric(self, name: str, value: float):
        """Add metric value"""
        self.metrics[name].append(value)
    
    def compute_recall_at_k(
        self,
        retrieved: List[str],
        relevant: List[str],
        k: int
    ) -> float:
        """
        Compute Recall@k
        
        Args:
            retrieved: Retrieved document IDs
            relevant: Relevant document IDs
            k: Top-k
            
        Returns:
            Recall@k score
        """
        if not relevant:
            return 0.0
        
        retrieved_k = set(retrieved[:k])
        relevant_set = set(relevant)
        
        hits = len(retrieved_k & relevant_set)
        recall = hits / len(relevant_set)
        
        return recall
    
    def compute_precision_at_k(
        self,
        retrieved: List[str],
        relevant: List[str],
        k: int
    ) -> float:
        """
        Compute Precision@k
        
        Args:
            retrieved: Retrieved document IDs
            relevant: Relevant document IDs
            k: Top-k
            
        Returns:
            Precision@k score
        """
        if not retrieved:
            return 0.0
        
        retrieved_k = set(retrieved[:k])
        relevant_set = set(relevant)
        
        hits = len(retrieved_k & relevant_set)
        precision = hits / min(k, len(retrieved))
        
        return precision
    
    def compute_mrr(
        self,
        retrieved: List[str],
        relevant: List[str]
    ) -> float:
        """
        Compute Mean Reciprocal Rank
        
        Args:
            retrieved: Retrieved document IDs
            relevant: Relevant document IDs
            
        Returns:
            MRR score
        """
        relevant_set = set(relevant)
        
        for i, doc_id in enumerate(retrieved, 1):
            if doc_id in relevant_set:
                return 1.0 / i
        
        return 0.0
    
    def get_summary(self) -> Dict[str, float]:
        """Get summary statistics"""
        summary = {}
        
        for name, values in self.metrics.items():
            if values:
                summary[f"{name}/mean"] = np.mean(values)
                summary[f"{name}/std"] = np.std(values)
                summary[f"{name}/min"] = np.min(values)
                summary[f"{name}/max"] = np.max(values)
        
        return summary
    
    def reset(self):
        """Reset all metrics"""
        self.metrics.clear()
        log.debug("Reset metrics")
