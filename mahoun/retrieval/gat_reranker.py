"""
GAT-based Reranker for Graph-Enhanced Retrieval
================================================

Graph Attention Network reranker with:
- Multi-head attention
- Uncertainty quantification (MC Dropout + GP)
- Chain-of-thought explanations
- Graph builder integration
- Async support

Imported from pipelines/gnn/gat_reranker.py and enhanced.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, Union, TYPE_CHECKING
from dataclasses import dataclass, field
from pathlib import Path
import asyncio

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch_geometric.nn import GATv2Conv
    from torch_geometric.data import Data
    from torch_geometric.utils import k_hop_subgraph
    HAS_TORCH = True
    if TYPE_CHECKING:
        from torch import Tensor
except ImportError:
    HAS_TORCH = False
    torch: Optional[Any] = None  # type: ignore[no-redef]
    nn: Optional[Any] = None  # type: ignore[assignment]
    F: Optional[Any] = None  # type: ignore[assignment]
    Data = Any  # type: ignore[misc]
    if TYPE_CHECKING:
        Tensor = Any  # type: ignore[misc]
    else:
        Tensor = Any

try:
    import networkx as nx  # type: ignore[no-redef]
except ImportError:
    nx: Optional[Any] = None  # type: ignore[assignment]
logger = logging.getLogger(__name__)


@dataclass
class RerankResult:
    """Reranking result with uncertainty and explanation"""
    doc_id: str
    score: float
    rank: int
    method: str = "gat"
    uncertainty: Optional[float] = None
    confidence_interval: Optional[Tuple[float, float]] = None
    explanation: Optional[str] = None
    attention_weights: Optional[List] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        result = {
            "doc_id": self.doc_id,
            "score": float(self.score),
            "rank": self.rank,
            "method": self.method,
            "metadata": self.metadata
        }
        
        if self.uncertainty is not None:
            result["uncertainty"] = float(self.uncertainty)
        
        if self.confidence_interval is not None:
            result["confidence_interval"] = [
                float(self.confidence_interval[0]),
                float(self.confidence_interval[1])
            ]
        
        if self.explanation:
            result["explanation"] = self.explanation
        
        return result


if HAS_TORCH:
    class GATRerankerModel(nn.Module):
        """
        Graph Attention Network for document reranking
        
        Architecture:
        - Multi-layer GAT with attention mechanism
        - Edge-aware message passing
        - Score prediction head
        """
        
        def __init__(
            self,
            in_channels: int = 1024,
            hidden_channels: int = 256,
            out_channels: int = 128,
            num_heads: int = 4,
            num_layers: int = 2,
            dropout: float = 0.1,
            edge_dim: int = 6,
        ):
            """
            Initialize GAT Reranker Model
            
            Args:
                in_channels: Input feature dimension (embedding size)
                hidden_channels: Hidden layer dimension
                out_channels: Output dimension before scoring
                num_heads: Number of attention heads
                num_layers: Number of GAT layers
                dropout: Dropout probability
                edge_dim: Edge feature dimension
            """
            super().__init__()
            
            self.in_channels = in_channels
            self.hidden_channels = hidden_channels
            self.out_channels = out_channels
            self.num_heads = num_heads
            self.num_layers = num_layers
            self.dropout = dropout
            
            # GAT layers
            self.convs = nn.ModuleList()
            
            # First layer
            self.convs.append(
                GATv2Conv(
                    in_channels,
                    hidden_channels,
                    heads=num_heads,
                    dropout=dropout,
                    edge_dim=edge_dim,
                    concat=True,
                )
            )
            
            # Hidden layers
            for _ in range(num_layers - 1):
                self.convs.append(
                    GATv2Conv(
                        hidden_channels * num_heads,
                        hidden_channels,
                        heads=num_heads,
                        dropout=dropout,
                        edge_dim=edge_dim,
                        concat=True,
                    )
                )
            
            # Score prediction head
            self.score_head = nn.Sequential(
                nn.Linear(hidden_channels * num_heads, out_channels),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(out_channels, 1),
                nn.Sigmoid(),
            )
            
            logger.info(
                f"GAT Reranker Model initialized: {num_layers} layers, "
                f"{num_heads} heads, {hidden_channels} hidden dim"
            )
        
        def forward(
            self,
            x: Tensor,
            edge_index: Tensor,
            edge_attr: Optional[Tensor] = None,
            return_attention: bool = False,
        ) -> Union[Tensor, Tuple[Tensor, List]]:
            """
            Forward pass through GAT
            
            Args:
                x: Node features [num_nodes, in_channels]
                edge_index: Edge connectivity [2, num_edges]
                edge_attr: Edge features [num_edges, edge_dim]
                return_attention: Whether to return attention weights
            
            Returns:
                scores: Relevance scores [num_nodes, 1]
                attention_weights: List of (edge_index, alpha) per layer (if requested)
            """
            attention_weights: List[Any] = []
            # Message passing through GAT layers
            for i, conv in enumerate(self.convs):
                x, (edge_idx, alpha) = conv(
                    x, edge_index, edge_attr=edge_attr, return_attention_weights=True
                )
                x = F.elu(x)
                x = F.dropout(x, p=self.dropout, training=self.training)
                
                if return_attention:
                    attention_weights.append((edge_idx, alpha))
            
            # Predict scores
            scores = self.score_head(x)
            
            if return_attention:
                return scores, attention_weights
            
            return scores
        
        def predict_with_uncertainty(
            self,
            x: Tensor,
            edge_index: Tensor,
            edge_attr: Optional[Tensor] = None,
            num_samples: int = 10
        ) -> Tuple[Tensor, Tensor]:
            """
            Predict with uncertainty using MC Dropout
            
            Args:
                x: Node features
                edge_index: Edge indices
                edge_attr: Edge attributes
                num_samples: Number of MC samples
            
            Returns:
                (mean_scores, std_scores)
            """
            self.train()  # Enable dropout
            
            predictions_list: List[Any] = []
            for _ in range(num_samples):
                with torch.no_grad():
                    scores = self.forward(x, edge_index, edge_attr)
                    predictions_list.append(scores)
            
            predictions = torch.stack(predictions_list)  # type: ignore[attr-defined]
            mean_scores = predictions.mean(dim=0)  # type: ignore[attr-defined]
            std_scores = predictions.std(dim=0)  # type: ignore[attr-defined]
            
            self.eval()
            
            return mean_scores, std_scores

else:
    # Dummy class for when torch is not available
    class GATRerankerModel:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any):
            raise ImportError("PyTorch not available")


class GATReranker:
    """
    GAT-based reranker service
    
    Features:
    - Load pre-trained GAT model
    - Extract k-hop subgraphs
    - Combine retrieval score, GAT score, PageRank
    - Generate explanations
    - Uncertainty quantification
    - Async support
    """
    
    def __init__(
        self,
        model_path: Optional[str] = None,
        graph_data: Optional[Data] = None,
        device: str = "cuda" if HAS_TORCH and torch.cuda.is_available() else "cpu",
        fallback_to_pagerank: bool = True,
        enable_uncertainty: bool = True,
    ):
        """
        Initialize GAT Reranker
        
        Args:
            model_path: Path to trained GAT model
            graph_data: PyG graph data
            device: Device for inference
            fallback_to_pagerank: Use PageRank if model unavailable
            enable_uncertainty: Enable uncertainty quantification
        """
        if not HAS_TORCH:
            raise ImportError(
                "PyTorch and PyTorch Geometric required. "
                "Install with: pip install torch torch-geometric"
            )
        
        logger.info(f"Initializing GAT Reranker on {device}")
        
        self.device = device
        self.fallback_to_pagerank = fallback_to_pagerank
        self.enable_uncertainty = enable_uncertainty
        self.model = None
        self.graph_data = graph_data
        self.pagerank_scores = None
        
        # Load model
        if model_path and Path(model_path).exists():
            try:
                self.model = self._load_model(model_path)
                logger.info(f"Loaded GAT model from {model_path}")
            except Exception as e:
                logger.warning(f"Could not load GAT model: {e}")
                if not fallback_to_pagerank:
                    raise
        else:
            if model_path:
                logger.warning(f"Model not found at {model_path}")
            if not fallback_to_pagerank:
                raise FileNotFoundError(f"Model not found: {model_path}")
        
        # Precompute PageRank if graph available
        if self.graph_data is not None and nx is not None:
            self._compute_pagerank()
        
        # Determine mode
        if self.model and self.graph_data:
            self.mode = "gat"
            logger.info("Mode: GAT reranking")
        elif self.graph_data:
            self.mode = "pagerank"
            logger.info("Mode: PageRank fallback")
        else:
            self.mode = "none"
            logger.warning("Mode: No reranking (passthrough)")
    
    def _load_model(self, model_path: str) -> GATRerankerModel:
        """Load trained GAT model"""
        checkpoint = torch.load(model_path, map_location=self.device)
        
        # Get model config
        config = checkpoint.get("config", {})
        
        model = GATRerankerModel(
            in_channels=config.get("in_channels", 1024),
            hidden_channels=config.get("hidden_channels", 256),
            out_channels=config.get("out_channels", 128),
            num_heads=config.get("num_heads", 4),
            num_layers=config.get("num_layers", 2),
            dropout=config.get("dropout", 0.1),
            edge_dim=config.get("edge_dim", 6),
        )
        
        model.load_state_dict(checkpoint["model_state_dict"])
        model.to(self.device)
        model.eval()
        
        return model
    
    def _compute_pagerank(self):
        """Precompute PageRank scores"""
        if nx is None:
            logger.warning("NetworkX not available, skipping PageRank")
            return
        
        logger.info("Computing PageRank scores...")
        
        # Convert to NetworkX
        G = nx.DiGraph()
        
        num_edges = self.graph_data.edge_index.shape[1]
        for i in range(num_edges):
            src = self.graph_data.edge_index[0, i].item()
            dst = self.graph_data.edge_index[1, i].item()
            weight = self.graph_data.edge_attr[i, 0].item() if self.graph_data.edge_attr is not None else 1.0
            G.add_edge(src, dst, weight=weight)
        
        # Compute PageRank
        pagerank = nx.pagerank(G, weight="weight")
        
        # Convert to tensor
        num_nodes = self.graph_data.num_nodes
        self.pagerank_scores = torch.zeros(num_nodes)
        for node_idx, score in pagerank.items():
            self.pagerank_scores[node_idx] = score
        
        logger.info("PageRank computed")
    
    def rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
        top_k: int = 50,
        alpha: float = 0.5,
        beta: float = 0.3,
        gamma: float = 0.2,
        k_hop: int = 2,
        return_explanation: bool = False,
        return_uncertainty: bool = True,
    ) -> List[RerankResult]:
        """
        Rerank search results
        
        Final Score = alpha * retrieval_score + beta * gat_score + gamma * pagerank
        
        Args:
            query: Search query
            results: List of search results with 'id' and 'score'
            top_k: Number of results to return
            alpha: Weight for retrieval score
            beta: Weight for GAT score
            gamma: Weight for PageRank score
            k_hop: K-hop neighborhood for subgraph
            return_explanation: Whether to return explanations
            return_uncertainty: Whether to return uncertainty estimates
        
        Returns:
            List of RerankResult objects
        """
        if self.mode == "none":
            logger.warning("No reranking available, returning original results")
            return self._convert_to_rerank_results(results[:top_k])
        
        # Extract result IDs and map to node indices
        result_indices: List[Any] = []
        id_to_result: Dict[str, Any] = {}
        for result in results:
            doc_id = result.get("id", result.get("doc_id"))
            if doc_id and hasattr(self.graph_data, "doc_id_to_idx"):
                if doc_id in self.graph_data.doc_id_to_idx:
                    idx = self.graph_data.doc_id_to_idx[doc_id]
                    result_indices.append(idx)
                    id_to_result[idx] = result
        
        if not result_indices:
            logger.warning("No results found in graph")
            return self._convert_to_rerank_results(results[:top_k])
        
        # Compute GAT scores
        gat_scores: Dict[str, Any] = {}
        if self.mode == "gat":
            try:
                gat_scores = self._compute_gat_scores(
                    result_indices,
                    k_hop,
                    return_explanation,
                    return_uncertainty
                )
            except Exception as e:
                logger.error(f"GAT scoring failed: {e}")
                if self.fallback_to_pagerank:
                    self.mode = "pagerank"
                else:
                    raise
        
        # Compute PageRank scores
        pagerank_scores_dict: Dict[str, Any] = {}
        if self.pagerank_scores is not None:
            for idx in result_indices:
                pagerank_scores_dict[idx] = self.pagerank_scores[idx].item()
        
        # Combine scores
        reranked_results: List[Any] = []
        for idx in result_indices:
            result = id_to_result[idx]
            doc_id = result.get("id", result.get("doc_id"))
            
            # Get individual scores
            retrieval_score = result.get("score", 0.0)
            gat_score = gat_scores.get(idx, {}).get("score", 0.0)
            pagerank_score = pagerank_scores_dict.get(idx, 0.0)
            
            # Normalize PageRank
            pagerank_normalized = 0.0
            if self.pagerank_scores is not None:
                max_pr = self.pagerank_scores.max().item()
                if max_pr > 0:
                    pagerank_normalized = pagerank_score / max_pr
            
            # Compute final score
            final_score = alpha * retrieval_score + beta * gat_score + gamma * pagerank_normalized
            
            # Get uncertainty
            uncertainty: Optional[Any] = None
            confidence_interval: Optional[Any] = None
            if return_uncertainty and "uncertainty" in gat_scores.get(idx, {}):
                uncertainty = gat_scores[idx]["uncertainty"]
                ci_lower = final_score - 1.96 * uncertainty
                ci_upper = final_score + 1.96 * uncertainty
                confidence_interval = (ci_lower, ci_upper)
            
            # Get explanation
            explanation: Optional[Any] = None
            if return_explanation and "explanation" in gat_scores.get(idx, {}):
                explanation = gat_scores[idx]["explanation"]
            
            reranked_results.append(RerankResult(
                doc_id=doc_id,
                score=final_score,
                rank=0,  # Will be updated after sorting
                method="gat" if self.mode == "gat" else "pagerank",
                uncertainty=uncertainty,
                confidence_interval=confidence_interval,
                explanation=explanation,
                metadata=result.get("metadata", {})
            ))
        
        # Sort by score
        reranked_results.sort(key=lambda x: x.score, reverse=True)
        
        # Update ranks
        for i, result in enumerate(reranked_results):
            result.rank = i + 1
        
        return reranked_results[:top_k]
    
    def _compute_gat_scores(
        self,
        result_indices: List[int],
        k_hop: int,
        return_explanation: bool,
        return_uncertainty: bool
    ) -> Dict[int, Dict[str, Any]]:
        """Compute GAT scores for result nodes"""
        if not self.model:
            return {}
        
        # Extract subgraph
        subgraph_data = self._prepare_subgraph(result_indices, k_hop)
        subgraph_data = subgraph_data.to(self.device)
        
        # Forward pass
        self.model.eval()
        
        if return_uncertainty and self.enable_uncertainty:
            # MC Dropout for uncertainty
            mean_scores, std_scores = self.model.predict_with_uncertainty(
                subgraph_data.x,
                subgraph_data.edge_index,
                subgraph_data.edge_attr,
                num_samples=10
            )
            scores = mean_scores
            uncertainties = std_scores
        else:
            with torch.no_grad():
                if return_explanation:
                    scores, attention_weights = self.model(
                        subgraph_data.x,
                        subgraph_data.edge_index,
                        subgraph_data.edge_attr,
                        return_attention=True
                    )
                else:
                    scores = self.model(
                        subgraph_data.x,
                        subgraph_data.edge_index,
                        subgraph_data.edge_attr
                    )
                    attention_weights: Optional[Any] = None
            uncertainties: Optional[Any] = None
        # Map back to original indices
        gat_scores: Dict[str, Any] = {}
        for i, orig_idx in enumerate(subgraph_data.original_indices):
            score_dict = {"score": scores[i, 0].item()}
            
            if uncertainties is not None:
                score_dict["uncertainty"] = uncertainties[i, 0].item()
            
            if return_explanation and attention_weights:
                explanation = self._explain_ranking(i, attention_weights, subgraph_data)
                score_dict["explanation"] = explanation
            
            gat_scores[orig_idx] = score_dict
        
        return gat_scores
    
    def _prepare_subgraph(self, node_indices: List[int], k_hop: int) -> Data:
        """Extract k-hop subgraph around result nodes"""
        subset, edge_index, mapping, edge_mask = k_hop_subgraph(
            node_idx=torch.tensor(node_indices, dtype=torch.long),
            num_hops=k_hop,
            edge_index=self.graph_data.edge_index,
            relabel_nodes=True,
            num_nodes=self.graph_data.num_nodes,
        )
        
        # Extract features
        x = self.graph_data.x[subset]
        edge_attr = self.graph_data.edge_attr[edge_mask] if self.graph_data.edge_attr is not None else None
        
        # Create subgraph data
        subgraph_data = Data(
            x=x,
            edge_index=edge_index,
            edge_attr=edge_attr,
            num_nodes=len(subset)
        )
        
        # Store original indices
        subgraph_data.original_indices = subset.tolist()
        
        return subgraph_data
    
    def _explain_ranking(
        self,
        node_idx: int,
        attention_weights: List[Tuple[Tensor, Tensor]],
        subgraph_data: Data,
    ) -> str:
        """Generate explanation for ranking decision"""
        explanations: List[Any] = []
        for layer_idx, (edge_index, alpha) in enumerate(attention_weights):
            # Find edges where this node is the target
            mask = edge_index[1] == node_idx
            
            if mask.sum() == 0:
                continue
            
            # Get source nodes and attention weights
            src_nodes = edge_index[0][mask]
            attn_weights = alpha[mask]
            
            # Get top-3 most important neighbors
            top_k = min(3, len(src_nodes))
            if top_k > 0:
                top_values, top_indices = torch.topk(attn_weights.mean(dim=1), k=top_k)
                
                explanations.append(
                    f"Layer {layer_idx}: Top neighbors with attention "
                    f"{[f'{v.item():.3f}' for v in top_values]}"
                )
        
        return " | ".join(explanations) if explanations else "No explanation available"
    
    def _convert_to_rerank_results(self, results: List[Dict[str, Any]]) -> List[RerankResult]:
        """Convert dict results to RerankResult objects"""
        rerank_results: List[Any] = []
        for i, result in enumerate(results):
            rerank_results.append(RerankResult(
                doc_id=result.get("id", result.get("doc_id", str(i))),
                score=result.get("score", 0.0),
                rank=i + 1,
                method="passthrough",
                metadata=result.get("metadata", {})
            ))
        
        return rerank_results
    
    async def rerank_async(
        self,
        query: str,
        results: List[Dict[str, Any]],
        top_k: int = 50,
        **kwargs
    ) -> List[RerankResult]:
        """Async version of rerank"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.rerank(query, results, top_k, **kwargs)
        )
    
    def set_graph(self, graph_data: Data):
        """Set graph data"""
        self.graph_data = graph_data
        if nx is not None:
            self._compute_pagerank()
        logger.info("Graph data updated")


# Convenience function
def create_gat_reranker(
    model_path: Optional[str] = None,
    graph_data: Optional[Data] = None,
    **kwargs
) -> GATReranker:
    """
    Create GAT reranker instance
    
    Args:
        model_path: Path to trained model
        graph_data: PyG graph data
        **kwargs: Additional arguments
    
    Returns:
        GATReranker instance
    """
    return GATReranker(model_path=model_path, graph_data=graph_data, **kwargs)
