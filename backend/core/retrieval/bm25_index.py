from __future__ import annotations

import logging
import pickle
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger("codebase-intel.bm25_index")

try:
    from rank_bm25 import BM25Okapi
    _BM25_AVAILABLE = True
except ImportError:
    _BM25_AVAILABLE = False
    logger.warning("rank_bm25 not installed — BM25Index will be unavailable. Run: pip install rank_bm25")

_NON_ALPHA_RE = re.compile(r"[^a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    lowered = text.lower()
    tokens = _NON_ALPHA_RE.split(lowered)
    return [t for t in tokens if len(t) >= 2]


class BM25Index:
    def __init__(self) -> None:
        if not _BM25_AVAILABLE:
            raise RuntimeError(
                "rank_bm25 is not installed. Run: pip install rank_bm25"
            )
        self.bm25: Optional[BM25Okapi] = None
        self.func_ids: list[str] = []
        self.corpus: list[list[str]] = []

    def build_from_functions(self, functions: list) -> None:
        self.func_ids = []
        self.corpus = []

        for func in functions:
            text_parts = [func.name or ""]
            if func.docstring:
                text_parts.append(func.docstring)
            if func.parameters:
                text_parts.append(" ".join(func.parameters))

            combined = " ".join(text_parts)
            tokens = _tokenize(combined)
            self.corpus.append(tokens)
            self.func_ids.append(func.id)

        self.bm25 = BM25Okapi(self.corpus)
        logger.info(f"BM25 index built with {len(self.func_ids)} functions")

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        if self.bm25 is None or not self.func_ids:
            logger.warning("BM25 index not built — call build_from_functions() first.")
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        scores = self.bm25.get_scores(query_tokens)

        indexed_scores = sorted(
            enumerate(scores), key=lambda x: x[1], reverse=True
        )[:top_k]

        max_score = indexed_scores[0][1] if indexed_scores else 0.0
        if max_score <= 0.0:
            return [(self.func_ids[i], 0.0) for i, _ in indexed_scores]

        return [
            (self.func_ids[i], float(score) / max_score)
            for i, score in indexed_scores
            if score > 0.0
        ]

    def save(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(
                {
                    "bm25": self.bm25,
                    "func_ids": self.func_ids,
                    "corpus": self.corpus,
                },
                f,
            )
        logger.info(f"BM25 index saved to {path}")

    def load(self, path: str) -> "BM25Index":
        with open(path, "rb") as f:
            data = pickle.load(f)
        self.bm25 = data["bm25"]
        self.func_ids = data["func_ids"]
        self.corpus = data["corpus"]
        logger.info(f"BM25 index loaded from {path} ({len(self.func_ids)} documents)")
        return self
