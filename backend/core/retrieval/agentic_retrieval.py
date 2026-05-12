from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

import networkx as nx
import numpy as np
import torch
import torch.nn.functional as F
from torch_geometric.data import Data

logger = logging.getLogger("codebase-intel.agentic_retrieval")


@dataclass
class RetrievalResult:
    func_id: str
    name: str
    file_path: str
    language: str
    line_start: int
    line_end: int
    behavioral_score: float
    textual_score: float
    final_score: float
    docstring: str
    complexity: int
    is_hot_path: bool


class AgenticRetriever:
    def __init__(
        self,
        encoder,
        qdrant,
        bm25,
        graph: nx.DiGraph,
        vocab,
    ) -> None:
        self.encoder = encoder
        self.qdrant = qdrant
        self.bm25 = bm25
        self.graph = graph
        self.vocab = vocab
        self.behavioral_weight = 0.7
        self.textual_weight = 0.3
        self.device = next(encoder.parameters()).device

    def _embed_query(self, query: str) -> np.ndarray:
        from torch_geometric.data import Data

        token_ids = self.vocab.encode(query, max_length=64)
        n = len(token_ids)

        src = []
        dst = []
        window_size = 5
        for i in range(n):
            src.append(i)
            dst.append(i)
            lo = max(0, i - window_size)
            hi = min(n - 1, i + window_size)
            for j in range(lo, hi + 1):
                if j != i:
                    src.append(i)
                    dst.append(j)

        x = torch.tensor(token_ids, dtype=torch.long).unsqueeze(0).to(self.device)
        x = x.squeeze(0)

        edge_index = torch.tensor([src, dst], dtype=torch.long).to(self.device)
        edge_attr = torch.ones(edge_index.shape[1], 1, dtype=torch.float).to(self.device)
        batch = torch.zeros(n, dtype=torch.long).to(self.device)

        self.encoder.eval()
        with torch.no_grad():
            emb = self.encoder(x, edge_index, edge_attr, batch)

        return emb.squeeze(0).cpu().numpy().astype(np.float32)

    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        language: Optional[str] = None,
    ) -> list[RetrievalResult]:
        query_emb = self._embed_query(query)

        qdrant_task = asyncio.to_thread(
            self.qdrant.search, query_emb, top_k=top_k * 3, language_filter=language
        )
        bm25_task = asyncio.to_thread(self.bm25.search, query, top_k=top_k * 3)

        qdrant_results, bm25_results = await asyncio.gather(qdrant_task, bm25_task)

        candidates: dict[str, dict] = {}

        for r in qdrant_results:
            fid = r["func_id"]
            candidates[fid] = {
                "behavioral_score": float(r["score"]),
                "textual_score": 0.0,
                **r,
            }

        for func_id, score in bm25_results:
            if func_id in candidates:
                candidates[func_id]["textual_score"] = float(score)
            else:
                emb = self.qdrant.get_embedding(func_id)
                if emb is not None:
                    norm_q = np.linalg.norm(query_emb)
                    norm_e = np.linalg.norm(emb)
                    behavioral = float(
                        np.dot(query_emb, emb) / (norm_q * norm_e + 1e-8)
                    )
                    candidates[func_id] = {
                        "behavioral_score": max(0.0, behavioral),
                        "textual_score": float(score),
                        "func_id": func_id,
                        "name": func_id.split("::")[-1] if "::" in func_id else func_id,
                        "file_path": "",
                        "language": "",
                        "line_start": 0,
                        "line_end": 0,
                        "docstring": "",
                        "complexity": 0,
                        "is_hot_path": False,
                    }

        expanded = dict(candidates)
        top_candidate_ids = sorted(
            candidates.keys(),
            key=lambda fid: candidates[fid]["behavioral_score"],
            reverse=True,
        )[:5]

        neighbors_to_fetch: list[str] = []
        for func_id in top_candidate_ids:
            node_id = func_id
            if self.graph.has_node(node_id):
                for neighbor in list(self.graph.successors(node_id)) + list(
                    self.graph.predecessors(node_id)
                ):
                    if neighbor not in expanded and neighbor not in neighbors_to_fetch:
                        neighbors_to_fetch.append(neighbor)

        # Single batched Qdrant call instead of N individual ones
        neighbor_embs = self.qdrant.get_embeddings_batch(neighbors_to_fetch)

        norm_q = np.linalg.norm(query_emb)
        for neighbor, emb in neighbor_embs.items():
            norm_e = np.linalg.norm(emb)
            behavioral = float(
                np.dot(query_emb, emb) / (norm_q * norm_e + 1e-8)
            )
            expanded[neighbor] = {
                "behavioral_score": max(0.0, behavioral),
                "textual_score": 0.0,
                "func_id": neighbor,
                "name": neighbor.split("::")[-1] if "::" in neighbor else neighbor,
                "file_path": "",
                "language": "",
                "line_start": 0,
                "line_end": 0,
                "docstring": "",
                "complexity": 0,
                "is_hot_path": False,
                "graph_boost": 0.05,
            }


        results: list[RetrievalResult] = []
        for func_id, data in expanded.items():
            graph_boost = data.get("graph_boost", 0.0)
            final = (
                self.behavioral_weight * data["behavioral_score"]
                + self.textual_weight * data["textual_score"]
                + graph_boost
            )
            results.append(
                RetrievalResult(
                    func_id=func_id,
                    name=data.get("name", ""),
                    file_path=data.get("file_path", ""),
                    language=data.get("language", ""),
                    line_start=int(data.get("line_start", 0)),
                    line_end=int(data.get("line_end", 0)),
                    behavioral_score=round(float(data["behavioral_score"]), 4),
                    textual_score=round(float(data["textual_score"]), 4),
                    final_score=round(float(final), 4),
                    docstring=data.get("docstring", ""),
                    complexity=int(data.get("complexity", 0)),
                    is_hot_path=bool(data.get("is_hot_path", False)),
                )
            )

        results.sort(key=lambda r: r.final_score, reverse=True)
        return results[:top_k]
