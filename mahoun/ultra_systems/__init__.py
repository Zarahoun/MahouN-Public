"""
Mahoun Ultra Systems
====================
Advanced AI systems integrated into the Mahoun platform.

Namespace: mahoun.ultra_systems
"""

# Keep the historical ultra_systems API. New graph construction should use
# mahoun.graph.ultra_graph_builder directly.
from mahoun.ultra_systems.graph import (
    UltraGraphBuilder,
    UltraGATTrainer,
    UltraGraphQueryService,
)

__all__ = [
    "UltraGraphBuilder",
    "UltraGATTrainer",
    "UltraGraphQueryService",
]
