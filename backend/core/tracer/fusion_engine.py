"""
fusion_engine.py
----------------
Fuse the static call graph (from tree-sitter parsing) with git co-edit
weights and call-frequency fan-in signals to produce a single weighted
graph whose edges drive GATv2Conv attention.

Fusion formula (per edge u→v):
  weight = w_static * static_score
         + w_coedit * coedit_normalised
         + w_freq   * freq_normalised

  Default weights: static=0.3, coedit=0.5, call_freq=0.2

Node annotations added after fusion:
  is_hot_path    : True if fan_in ≥ 90th-percentile of all nodes
  coupling_score : mean edge weight across all incident edges
  is_isolated    : True if the node has zero edges after fusion

Usage:
    engine = FusionEngine()
    fused  = engine.fuse(static_graph, coedit_data=coedit_dict)
    edge_index, edge_attr = engine.to_pyg_edge_weights(fused, node_order)
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import networkx as nx
import numpy as np
import torch

logger = logging.getLogger("codebase-intel.fusion_engine")


class FusionEngine:
    """
    Combine static call graph topology with dynamic co-edit signals.

    Parameters
    ----------
    static_weight  : contribution of the raw call-graph edge (default 0.3)
    coedit_weight  : contribution of git co-edit normalised score (default 0.5)
    call_freq_weight: contribution of fan-in frequency score (default 0.2)
    """

    def __init__(
        self,
        static_weight: float = 0.3,
        coedit_weight: float = 0.5,
        call_freq_weight: float = 0.2,
        min_coedit_weight: float = 0.05,
        max_coedit_edges: int = 50_000,
    ) -> None:
        self.static_weight    = static_weight
        self.coedit_weight    = coedit_weight
        self.call_freq_weight = call_freq_weight
        self.min_coedit_weight = min_coedit_weight
        self.max_coedit_edges  = max_coedit_edges

    
    
    

    def fuse(
        self,
        static_graph: nx.DiGraph,
        coedit_data: Optional[Dict[Tuple[str, str], float]] = None,
    ) -> nx.DiGraph:
        """
        Create a fused DiGraph with weighted edges and annotated nodes.

        Edge weight computation
        ----------------------
        1. Static-only edge (in call graph, no co-edit data):
               weight = 1.0  (full structural signal)

        2. Co-edit reinforced edge (in call graph AND has co-edit signal):
               weight = static_weight * 1.0
                      + coedit_weight * coedit_score
                      + call_freq_weight * freq_score
           Typically falls in [0.3, 1.0+] — values above 1 are clipped to 1.

        3. Co-edit-only edge (NOT in call graph but files co-edit frequently):
               weight = coedit_weight * coedit_score
           Represents *implicit* coupling that static analysis misses.

        Node attributes added
        --------------------
        fan_in          : number of in-edges
        fan_out         : number of out-edges
        is_hot_path     : fan_in ≥ 90th percentile
        coupling_score  : mean weight of all incident edges (in + out)
        is_isolated     : True if degree == 0 after fusion

        Parameters
        ----------
        static_graph : nx.DiGraph produced by tree-sitter parsing pipeline
        coedit_data  : dict (func_id_a, func_id_b) → normalised weight [0,1]
                       produced by GitCoEditExtractor.get_function_coedits()

        Returns
        -------
        nx.DiGraph with 'weight' edge attribute and annotated nodes.
        """
        coedit_data = coedit_data or {}
        fused = nx.DiGraph()

        
        for node, attrs in static_graph.nodes(data=True):
            fused.add_node(node, **attrs)

        
        fan_in: Dict[str, int] = {
            n: static_graph.in_degree(n) for n in static_graph.nodes()
        }
        max_fan_in = max(fan_in.values(), default=1) or 1
        freq_score: Dict[str, float] = {
            n: v / max_fan_in for n, v in fan_in.items()
        }

        
        static_edge_set: set = set()
        for u, v, edata in static_graph.edges(data=True):
            static_edge_set.add((u, v))
            static_edge_set.add((v, u))   

            co_key   = (u, v) if (u, v) in coedit_data else (v, u)
            co_score = coedit_data.get(co_key, 0.0)
            f_score  = (freq_score.get(u, 0.0) + freq_score.get(v, 0.0)) / 2.0

            if co_score > 0.0:
                
                weight = (
                    self.static_weight * 1.0
                    + self.coedit_weight * co_score
                    + self.call_freq_weight * f_score
                )
            else:
                
                weight = 1.0

            weight = float(np.clip(weight, 0.0, 2.0))   
            fused.add_edge(
                u,
                v,
                weight=weight,
                edge_type=edata.get("edge_type", "call"),
                is_static=True,
                coedit_score=co_score,
                call_freq_score=f_score,
            )

        
        
        
        
        coedit_candidates: list[tuple[float, tuple, tuple]] = []
        for (node_a, node_b), co_score in coedit_data.items():
            if co_score <= 0.0:
                continue
            if (node_a, node_b) in static_edge_set or (node_b, node_a) in static_edge_set:
                continue
            weight = float(np.clip(self.coedit_weight * co_score, 0.0, 1.0))
            if weight < self.min_coedit_weight:
                continue
            coedit_candidates.append((weight, (node_a, node_b), (node_a, node_b, co_score)))

        
        coedit_candidates.sort(key=lambda x: x[0], reverse=True)
        max_pairs = self.max_coedit_edges // 2
        coedit_candidates = coedit_candidates[:max_pairs]

        logger.info(
            f"FusionEngine: adding {len(coedit_candidates)} co-edit-only edge pairs "
            f"(threshold={self.min_coedit_weight}, cap={max_pairs})"
        )

        for weight, (node_a, node_b), (_, _, co_score) in coedit_candidates:
            if not fused.has_node(node_a):
                fused.add_node(node_a)
            if not fused.has_node(node_b):
                fused.add_node(node_b)
            
            fused.add_edge(
                node_a,
                node_b,
                weight=weight,
                edge_type="coedit",
                is_static=False,
                coedit_score=co_score,
                call_freq_score=0.0,
            )
            fused.add_edge(
                node_b,
                node_a,
                weight=weight,
                edge_type="coedit",
                is_static=False,
                coedit_score=co_score,
                call_freq_score=0.0,
            )

        
        self._annotate_nodes(fused)

        logger.info(
            f"FusionEngine: {fused.number_of_nodes()} nodes, "
            f"{fused.number_of_edges()} edges in fused graph."
        )
        return fused

    
    
    

    def _annotate_nodes(self, graph: nx.DiGraph) -> None:
        """Add fan_in, fan_out, is_hot_path, coupling_score, is_isolated."""
        fan_ins  = np.array([graph.in_degree(n) for n in graph.nodes()], dtype=float)
        threshold = np.percentile(fan_ins, 90) if len(fan_ins) > 0 else 0.0

        for node in graph.nodes():
            in_deg  = graph.in_degree(node)
            out_deg = graph.out_degree(node)

            
            in_weights  = [d.get("weight", 1.0) for _, _, d in graph.in_edges(node, data=True)]
            out_weights = [d.get("weight", 1.0) for _, _, d in graph.out_edges(node, data=True)]
            all_weights = in_weights + out_weights
            coupling = float(np.mean(all_weights)) if all_weights else 0.0

            graph.nodes[node]["fan_in"]         = in_deg
            graph.nodes[node]["fan_out"]        = out_deg
            graph.nodes[node]["is_hot_path"]    = bool(in_deg >= threshold and threshold > 0)
            graph.nodes[node]["coupling_score"] = coupling
            graph.nodes[node]["is_isolated"]    = (in_deg + out_deg == 0)

    
    
    

    def to_pyg_edge_weights(
        self,
        fused_graph: nx.DiGraph,
        node_order: List[str],
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Convert the fused NetworkX graph to PyTorch Geometric tensors.

        Parameters
        ----------
        fused_graph : nx.DiGraph returned by fuse()
        node_order  : list of node IDs defining integer indices
                      (index in list = integer node index in PyG)

        Returns
        -------
        edge_index : LongTensor  [2, E]   — source / target node indices
        edge_attr  : FloatTensor [E, 1]   — fusion weights
        """
        node_to_idx: Dict[str, int] = {n: i for i, n in enumerate(node_order)}

        src_list: List[int] = []
        dst_list: List[int] = []
        weight_list: List[float] = []

        for u, v, data in fused_graph.edges(data=True):
            u_idx = node_to_idx.get(u)
            v_idx = node_to_idx.get(v)
            if u_idx is None or v_idx is None:
                continue
            src_list.append(u_idx)
            dst_list.append(v_idx)
            weight_list.append(float(data.get("weight", 1.0)))

        if not src_list:
            if not node_order:
                return (
                    torch.empty((2, 0), dtype=torch.long),
                    torch.empty((0, 1), dtype=torch.float),
                )

            
            edge_index = torch.zeros((2, 1), dtype=torch.long)
            edge_attr  = torch.ones((1, 1), dtype=torch.float)
            return edge_index, edge_attr

        edge_index = torch.tensor([src_list, dst_list], dtype=torch.long)
        edge_attr  = torch.tensor(weight_list, dtype=torch.float).unsqueeze(1)  

        return edge_index, edge_attr
