"""
drift_detector.py
-----------------
Semantic drift detection for codebases using GATv2 embeddings.

Compares two snapshots of a codebase (old_nodes vs new_nodes) and returns
DriftResult objects ranked by how much each function has changed semantically.
"""

from __future__ import annotations

import logging
import numpy as np
import networkx as nx
from dataclasses import dataclass
from typing import Optional

import torch
from torch_geometric.data import Batch, Data

logger = logging.getLogger("atlas.drift_detector")


@dataclass
class DriftResult:
    function_id: str
    name: str
    file_path: str
    old_complexity: int
    new_complexity: int
    cosine_distance: float
    is_drifted: bool
    drift_type: str
    details: str


class DriftDetector:
    """
    Detect semantic drift between two snapshots of a codebase.

    Uses the trained GATv2 FunctionEncoder to embed each function and then
    compares embeddings via cosine distance.
    """

    def __init__(self, encoder, vocab, device: str = "cpu"):
        self.encoder = encoder
        self.vocab = vocab
        self.device = device
        self.encoder.eval()
        self.encoder.to(device)
        self._max_seq_len = 64
        self._window_size = 5

    def _make_pyg_data(self, token_ids: list[int]) -> Data:
        """Build a single PyG Data object from a list of token IDs."""
        from core.model.dataset import create_token_graph

        N = len(token_ids)
        x = torch.tensor(token_ids, dtype=torch.long)
        edge_index, edge_attr = create_token_graph(token_ids, window_size=self._window_size)
        return Data(x=x, edge_index=edge_index, edge_attr=edge_attr)

    def embed_function(self, node) -> np.ndarray:
        """
        Embed a single FunctionNode using the trained GATv2 encoder.

        Tokenises name + first 200 chars of body_text, creates a PyG Data
        object, and runs it through the encoder with no_grad.

        Returns a 128-dim numpy array (L2-normalised).
        """
        text = node.name + " " + (node.body_text or "")[:200]
        token_ids = self.vocab.encode(text, max_length=self._max_seq_len)
        data = self._make_pyg_data(token_ids)

        # Add batch dimension (single graph)
        data = data.to(self.device)
        batch_vec = torch.zeros(data.num_nodes, dtype=torch.long, device=self.device)

        with torch.no_grad():
            emb = self.encoder(data.x, data.edge_index, data.edge_attr, batch_vec)

        return emb.squeeze(0).cpu().numpy()

    def embed_all(self, nodes: list) -> dict[str, np.ndarray]:
        """
        Embed all FunctionNodes in batches of 64.

        Returns dict mapping function_id -> 128-dim numpy array.
        """
        batch_size = 64
        result: dict[str, np.ndarray] = {}

        for start in range(0, len(nodes), batch_size):
            chunk = nodes[start: start + batch_size]
            data_list: list[Data] = []
            for node in chunk:
                text = node.name + " " + (node.body_text or "")[:200]
                token_ids = self.vocab.encode(text, max_length=self._max_seq_len)
                data_list.append(self._make_pyg_data(token_ids))

            batch = Batch.from_data_list(data_list).to(self.device)

            with torch.no_grad():
                embs = self.encoder(batch.x, batch.edge_index, batch.edge_attr, batch.batch)

            embs_np = embs.cpu().numpy()
            for i, node in enumerate(chunk):
                result[node.id] = embs_np[i]

        return result

    def detect_drift(
        self,
        old_nodes: list,
        new_nodes: list,
        threshold: float = 0.15,
    ) -> list[DriftResult]:
        """
        Compare two versions of a codebase and detect semantic drift.

        Algorithm:
        1. Embed all functions in old_nodes and new_nodes.
        2. Match by ID (filepath::name). Unmatched → added/removed.
        3. For matched pairs compute cosine distance = 1 - cosine_similarity.
           - distance > threshold → "semantic" drift
           - |complexity_change| > 3 (but distance OK) → "structural" drift
        4. Return all DriftResults sorted by cosine_distance descending.
        """
        logger.info(f"Embedding {len(old_nodes)} old + {len(new_nodes)} new functions …")

        old_embeddings = self.embed_all(old_nodes)
        new_embeddings = self.embed_all(new_nodes)

        old_by_id: dict[str, object] = {n.id: n for n in old_nodes}
        new_by_id: dict[str, object] = {n.id: n for n in new_nodes}

        results: list[DriftResult] = []
        matched_old: set[str] = set()
        matched_new: set[str] = set()

        for func_id in set(old_by_id.keys()) & set(new_by_id.keys()):
            old_emb = old_embeddings[func_id]
            new_emb = new_embeddings[func_id]

            norm_old = np.linalg.norm(old_emb)
            norm_new = np.linalg.norm(new_emb)
            cos_sim = float(
                np.dot(old_emb, new_emb) / (norm_old * norm_new + 1e-8)
            )
            cos_dist = 1.0 - cos_sim

            old_node = old_by_id[func_id]
            new_node = new_by_id[func_id]
            complexity_change = abs(new_node.complexity - old_node.complexity)

            is_drifted = cos_dist > threshold
            drift_type = "semantic" if is_drifted else "stable"
            if complexity_change > 3 and not is_drifted:
                drift_type = "structural"
                is_drifted = True

            details = f"Cosine distance: {cos_dist:.4f}"
            if complexity_change > 0:
                details += (
                    f", complexity changed by {complexity_change}"
                    f" ({old_node.complexity} → {new_node.complexity})"
                )

            results.append(
                DriftResult(
                    function_id=func_id,
                    name=new_node.name,
                    file_path=new_node.file_path,
                    old_complexity=old_node.complexity,
                    new_complexity=new_node.complexity,
                    cosine_distance=round(cos_dist, 4),
                    is_drifted=is_drifted,
                    drift_type=drift_type,
                    details=details,
                )
            )
            matched_old.add(func_id)
            matched_new.add(func_id)

        for func_id in set(new_by_id.keys()) - matched_new:
            node = new_by_id[func_id]
            results.append(
                DriftResult(
                    function_id=func_id,
                    name=node.name,
                    file_path=node.file_path,
                    old_complexity=0,
                    new_complexity=node.complexity,
                    cosine_distance=1.0,
                    is_drifted=True,
                    drift_type="added",
                    details="New function added",
                )
            )

        for func_id in set(old_by_id.keys()) - matched_old:
            node = old_by_id[func_id]
            results.append(
                DriftResult(
                    function_id=func_id,
                    name=node.name,
                    file_path=node.file_path,
                    old_complexity=node.complexity,
                    new_complexity=0,
                    cosine_distance=1.0,
                    is_drifted=True,
                    drift_type="removed",
                    details="Function removed",
                )
            )

        results.sort(key=lambda r: r.cosine_distance, reverse=True)
        drifted = sum(1 for r in results if r.is_drifted)
        logger.info(f"Drift detection complete: {drifted}/{len(results)} functions flagged.")
        return results

    def check_architecture_rules(
        self, graph: nx.DiGraph, rules: list[dict]
    ) -> list[dict]:
        """
        Validate a call graph against architectural dependency rules.

        Rules format:
            [{"from_module": "api", "to_module": "database",
              "allowed": False, "reason": "API should not access DB directly"}]

        Module is derived from the first path component of file_path.
        Returns list of violation dicts.
        """
        violations: list[dict] = []

        for src_node, dst_node, edge_data in graph.edges(data=True):
            src_file = graph.nodes[src_node].get("file_path", src_node)
            dst_file = graph.nodes[dst_node].get("file_path", dst_node)

            src_parts = src_file.replace("\\", "/").split("/")
            dst_parts = dst_file.replace("\\", "/").split("/")
            src_module = src_parts[0] if src_parts else ""
            dst_module = dst_parts[0] if dst_parts else ""

            for rule in rules:
                if (
                    rule.get("from_module") == src_module
                    and rule.get("to_module") == dst_module
                    and not rule.get("allowed", True)
                ):
                    violations.append(
                        {
                            "rule": rule.get("reason", "Violated dependency rule"),
                            "from_function": src_node,
                            "to_function": dst_node,
                            "from_file": src_file,
                            "to_file": dst_file,
                            "from_module": src_module,
                            "to_module": dst_module,
                        }
                    )

        return violations
