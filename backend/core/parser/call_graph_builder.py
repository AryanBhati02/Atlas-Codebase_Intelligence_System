"""
call_graph_builder.py
---------------------
Builds a NetworkX DiGraph of function-to-function call edges
from a list of FunctionNode objects produced by TreeSitterParser.

Also provides conversion utilities:
  - graph_to_json()     → JSON-serialisable dict (for API/frontend)
  - graph_to_pyg_data() → PyTorch Geometric compatible format (for GATv2 training)
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from typing import Optional

import networkx as nx  

from .tree_sitter_parser import FunctionNode

logger = logging.getLogger("codebase-intel.call_graph_builder")

def build_call_graph(nodes: list[FunctionNode]) -> nx.DiGraph:
    """
    Build a directed call graph from a list of FunctionNode objects.

    Resolution strategy for callee names:
      1. Exact match on full node id  (filepath::ClassName.method)
      2. Qualified name match         (ClassName.method  or  method)
      3. Short name match             (method) — prefer same file, then same dir
    """
    graph = nx.DiGraph()

    for node in nodes:
        graph.add_node(
            node.id,
            name=node.name,
            file_path=node.file_path,
            language=node.language,
            line_start=node.line_start,
            line_end=node.line_end,
            parameters=node.parameters,
            return_type=node.return_type,
            docstring=node.docstring,
            calls_to=node.calls_to,
            complexity=node.complexity,
            body_text=node.body_text,
            fan_in=0,
            fan_out=0,
        )

    id_index: dict[str, FunctionNode] = {n.id: n for n in nodes}

    name_index: dict[str, list[FunctionNode]] = defaultdict(list)
    short_index: dict[str, list[FunctionNode]] = defaultdict(list)

    for node in nodes:
        name_index[node.name].append(node)
        
        short = node.name.split(".")[-1]
        short_index[short].append(node)

    def _resolve(called_name: str, caller: FunctionNode) -> Optional[str]:
        """Try to resolve *called_name* to a node ID, given the *caller* context."""
        
        if called_name in id_index:
            return called_name

        
        candidates = name_index.get(called_name, [])
        if not candidates:
            candidates = short_index.get(called_name, [])

        if not candidates:
            return None

        if len(candidates) == 1:
            return candidates[0].id

        
        same_file = [c for c in candidates if c.file_path == caller.file_path]
        if same_file:
            return same_file[0].id

        
        caller_dir = os.path.dirname(caller.file_path)
        same_dir = [c for c in candidates if os.path.dirname(c.file_path) == caller_dir]
        if same_dir:
            return same_dir[0].id

        
        return candidates[0].id

    edge_count = 0
    for node in nodes:
        for called_name in node.calls_to:
            resolved_id = _resolve(called_name, node)
            if resolved_id is not None:
                if not graph.has_edge(node.id, resolved_id):
                    graph.add_edge(node.id, resolved_id, edge_type="call")
                    edge_count += 1

    logger.info(
        f"Call graph built: {graph.number_of_nodes()} nodes, {edge_count} edges resolved."
    )

    for node_id in graph.nodes:
        graph.nodes[node_id]["fan_in"] = graph.in_degree(node_id)
        graph.nodes[node_id]["fan_out"] = graph.out_degree(node_id)

    return graph

def graph_to_json(graph: nx.DiGraph) -> dict:
    """
    Convert the call graph to a JSON-serialisable dict.

    Schema::

        {
            "nodes": [{"id", "name", "file_path", "language",
                       "line_start", "line_end", "complexity",
                       "fan_in", "fan_out", "parameters", "docstring"}],
            "edges": [{"source", "target", "edge_type"}],
            "stats": {"total_nodes", "total_edges",
                      "avg_complexity", "max_fan_in", "max_fan_out"}
        }
    """
    nodes_out = []
    complexities: list[int] = []
    fan_ins: list[int] = []
    fan_outs: list[int] = []

    for node_id, attrs in graph.nodes(data=True):
        complexity = attrs.get("complexity", 1)
        fan_in = attrs.get("fan_in", 0)
        fan_out = attrs.get("fan_out", 0)
        complexities.append(complexity)
        fan_ins.append(fan_in)
        fan_outs.append(fan_out)

        nodes_out.append(
            {
                "id": node_id,
                "name": attrs.get("name", ""),
                "file_path": attrs.get("file_path", ""),
                "language": attrs.get("language", ""),
                "line_start": attrs.get("line_start", 0),
                "line_end": attrs.get("line_end", 0),
                "complexity": complexity,
                "fan_in": fan_in,
                "fan_out": fan_out,
                "parameters": attrs.get("parameters", []),
                "docstring": attrs.get("docstring", ""),
                "is_hot_path": bool(attrs.get("is_hot_path", False)),
                "coupling_score": float(attrs.get("coupling_score", 0.0)),
                "is_isolated": bool(attrs.get("is_isolated", False)),
            }
        )

    edges_out = []
    edge_weights: list[float] = []
    for u, v, data in graph.edges(data=True):
        weight = float(data.get("weight", 1.0))
        edge_weights.append(weight)
        edges_out.append(
            {
                "source": u,
                "target": v,
                "edge_type": data.get("edge_type", "call"),
                "weight": weight,
                "is_static": bool(data.get("is_static", data.get("edge_type", "call") == "call")),
                "coedit_score": float(data.get("coedit_score", 0.0)),
                "call_freq_score": float(data.get("call_freq_score", 0.0)),
            }
        )

    n = len(complexities)
    stats = {
        "total_nodes": graph.number_of_nodes(),
        "total_edges": graph.number_of_edges(),
        "avg_complexity": round(sum(complexities) / n, 3) if n else 0.0,
        "max_fan_in": max(fan_ins) if fan_ins else 0,
        "max_fan_out": max(fan_outs) if fan_outs else 0,
        "avg_edge_weight": round(sum(edge_weights) / len(edge_weights), 3) if edge_weights else 0.0,
        "hot_path_count": sum(1 for _, attrs in graph.nodes(data=True) if attrs.get("is_hot_path")),
        "isolated_count": sum(1 for _, attrs in graph.nodes(data=True) if attrs.get("is_isolated")),
    }

    return {"nodes": nodes_out, "edges": edges_out, "stats": stats}


def graph_to_pyg_data(graph: nx.DiGraph) -> dict:
    """
    Convert the call graph to PyTorch Geometric compatible format.

    Returns::

        {
            "node_ids":      list[str],           # ordered list of node IDs
            "edge_index":    [[src_idx,...], [tgt_idx,...]],
            "node_features": {
                "complexity":   list[int],
                "fan_in":       list[int],
                "fan_out":      list[int],
                "loc":          list[int],   # line_end - line_start
                "param_count":  list[int],
            }
        }
    """
    node_ids = list(graph.nodes())
    node_to_idx = {nid: i for i, nid in enumerate(node_ids)}

    src_indices: list[int] = []
    tgt_indices: list[int] = []
    edge_attr: list[list[float]] = []

    for u, v, data in graph.edges(data=True):
        if u in node_to_idx and v in node_to_idx:
            src_indices.append(node_to_idx[u])
            tgt_indices.append(node_to_idx[v])
            edge_attr.append([float(data.get("weight", 1.0))])

    complexities: list[int] = []
    fan_ins: list[int] = []
    fan_outs: list[int] = []
    locs: list[int] = []
    param_counts: list[int] = []
    coupling_scores: list[float] = []
    hot_paths: list[int] = []
    isolated: list[int] = []

    for nid in node_ids:
        attrs = graph.nodes[nid]
        complexities.append(attrs.get("complexity", 1))
        fan_ins.append(attrs.get("fan_in", 0))
        fan_outs.append(attrs.get("fan_out", 0))
        line_start = attrs.get("line_start", 0)
        line_end = attrs.get("line_end", 0)
        locs.append(max(0, line_end - line_start))
        param_counts.append(len(attrs.get("parameters", [])))
        coupling_scores.append(float(attrs.get("coupling_score", 0.0)))
        hot_paths.append(1 if attrs.get("is_hot_path", False) else 0)
        isolated.append(1 if attrs.get("is_isolated", False) else 0)

    return {
        "node_ids": node_ids,
        "edge_index": [src_indices, tgt_indices],
        "edge_attr": edge_attr,
        "node_features": {
            "complexity": complexities,
            "fan_in": fan_ins,
            "fan_out": fan_outs,
            "loc": locs,
            "param_count": param_counts,
            "coupling_score": coupling_scores,
            "is_hot_path": hot_paths,
            "is_isolated": isolated,
        },
    }
