from __future__ import annotations

import hashlib
import logging
from typing import Optional

import numpy as np

logger = logging.getLogger("codebase-intel.qdrant_store")

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance,
        FieldCondition,
        Filter,
        MatchValue,
        PointStruct,
        VectorParams,
        NamedVector,
        ScoredPoint,
    )
    from qdrant_client.models import QueryRequest
    _QDRANT_AVAILABLE = True
except ImportError:
    _QDRANT_AVAILABLE = False
    logger.warning("qdrant-client not installed — AtlasQdrantStore will be unavailable.")

try:
    from qdrant_client.models import QueryRequest as _QR  # noqa: F401
    _HAS_QUERY_POINTS = True
except ImportError:
    _HAS_QUERY_POINTS = False


def _func_id_to_point_id(func_id: str) -> int:
    return int(hashlib.md5(func_id.encode()).hexdigest()[:16], 16)


class AtlasQdrantStore:
    def __init__(self, host: str = "localhost", port: int = 6333) -> None:
        if not _QDRANT_AVAILABLE:
            raise RuntimeError(
                "qdrant-client is not installed. Run: pip install qdrant-client"
            )
        self.host = host
        self.port = port
        self.collection_name = "atlas_functions"
        self.embedding_dim = 128
        self._client: Optional[QdrantClient] = None

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            try:
                self._client = QdrantClient(host=self.host, port=self.port, timeout=5.0)
            except Exception as exc:
                raise ConnectionError(
                    f"Cannot connect to Qdrant at {self.host}:{self.port}. "
                    f"Is Qdrant running? Original error: {exc}"
                ) from exc
        return self._client

    def create_collection(self, recreate: bool = False) -> None:
        existing = [c.name for c in self.client.get_collections().collections]
        if self.collection_name in existing:
            if recreate:
                self.client.delete_collection(self.collection_name)
                logger.info(f"Deleted existing Qdrant collection '{self.collection_name}'")
            else:
                logger.info(
                    f"Qdrant collection '{self.collection_name}' already exists — skipping creation."
                )
                return

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=self.embedding_dim, distance=Distance.COSINE),
        )
        logger.info(
            f"Created Qdrant collection '{self.collection_name}' (dim={self.embedding_dim}, cosine)"
        )

    def upsert_functions(self, functions: list, embeddings: np.ndarray) -> None:
        if len(functions) == 0:
            logger.warning("upsert_functions called with empty function list — nothing to do.")
            return

        batch_size = 100
        total = len(functions)
        points_uploaded = 0

        for batch_start in range(0, total, batch_size):
            batch_funcs = functions[batch_start : batch_start + batch_size]
            batch_embs = embeddings[batch_start : batch_start + batch_size]

            points = []
            for func, emb in zip(batch_funcs, batch_embs):
                point_id = _func_id_to_point_id(func.id)
                docstring = (func.docstring or "")[:500]
                payload = {
                    "func_id": func.id,
                    "name": func.name,
                    "file_path": func.file_path,
                    "language": func.language,
                    "line_start": func.line_start,
                    "line_end": func.line_end,
                    "complexity": func.complexity,
                    "docstring": docstring,
                    "parameters": func.parameters,
                    "fan_in": 0,
                    "fan_out": len(func.calls_to),
                    "is_hot_path": False,
                }
                points.append(
                    PointStruct(
                        id=point_id,
                        vector=emb.tolist(),
                        payload=payload,
                    )
                )

            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
                wait=True,
            )
            points_uploaded += len(points)
            logger.debug(f"Upserted batch {batch_start // batch_size + 1}: {points_uploaded}/{total}")

        logger.info(f"Upserted {points_uploaded} function embeddings to Qdrant")

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 10,
        language_filter: Optional[str] = None,
    ) -> list[dict]:
        query_filter = None
        if language_filter is not None:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="language",
                        match=MatchValue(value=language_filter),
                    )
                ]
            )

        hits = self._search_vectors(query_vector.tolist(), top_k, query_filter)

        output = []
        for hit in hits:
            payload = hit.payload or {}
            output.append(
                {
                    "func_id": payload.get("func_id", ""),
                    "name": payload.get("name", ""),
                    "file_path": payload.get("file_path", ""),
                    "language": payload.get("language", ""),
                    "score": float(hit.score),
                    "line_start": payload.get("line_start", 0),
                    "line_end": payload.get("line_end", 0),
                    "docstring": payload.get("docstring", ""),
                    "is_hot_path": bool(payload.get("is_hot_path", False)),
                    "complexity": int(payload.get("complexity", 1)),
                }
            )
        return output

    def _search_vectors(self, vector: list, limit: int, query_filter) -> list:
        """Unified search that works with both old (.search) and new (.query_points) API."""
        # qdrant-client >= 1.7 uses query_points(); older used search()
        if hasattr(self.client, 'query_points'):
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=vector,
                limit=limit,
                query_filter=query_filter,
                with_payload=True,
            )
            # query_points returns a QueryResponse with .points attribute
            return response.points
        else:
            # Legacy API fallback
            return self.client.search(  # type: ignore[attr-defined]
                collection_name=self.collection_name,
                query_vector=vector,
                limit=limit,
                query_filter=query_filter,
                with_payload=True,
            )

    def get_embedding(self, func_id: str) -> Optional[np.ndarray]:
        point_id = _func_id_to_point_id(func_id)
        # Try to retrieve by ID first (works in both old and new API)
        try:
            if hasattr(self.client, 'retrieve'):
                results = self.client.retrieve(
                    collection_name=self.collection_name,
                    ids=[point_id],
                    with_vectors=True,
                    with_payload=False,
                )
            else:
                # qdrant-client 1.7+ fallback via scroll
                scroll_results, _ = self.client.scroll(
                    collection_name=self.collection_name,
                    scroll_filter=Filter(
                        must=[
                            FieldCondition(
                                key="func_id",
                                match=MatchValue(value=func_id),
                            )
                        ]
                    ),
                    limit=1,
                    with_vectors=True,
                    with_payload=False,
                )
                results = scroll_results
        except Exception:
            try:
                scroll_results, _ = self.client.scroll(
                    collection_name=self.collection_name,
                    scroll_filter=Filter(
                        must=[
                            FieldCondition(
                                key="func_id",
                                match=MatchValue(value=func_id),
                            )
                        ]
                    ),
                    limit=1,
                    with_vectors=True,
                    with_payload=False,
                )
                results = scroll_results
            except Exception:
                return None

        if not results:
            return None

        point = results[0]
        vec = getattr(point, "vector", None)
        if vec is None:
            return None
        if isinstance(vec, dict):
            # Named vectors format — take first value
            vec = next(iter(vec.values()), None)
        if vec is None:
            return None
        return np.array(vec, dtype=np.float32)

    def get_embeddings_batch(self, func_ids: list[str]) -> dict[str, np.ndarray]:
        """
        Fetch embeddings for multiple func_ids in a single Qdrant call.
        Returns a dict mapping func_id -> embedding (only for found entries).
        """
        if not func_ids:
            return {}

        point_ids = [_func_id_to_point_id(fid) for fid in func_ids]
        id_to_func = {_func_id_to_point_id(fid): fid for fid in func_ids}

        try:
            results = self.client.retrieve(
                collection_name=self.collection_name,
                ids=point_ids,
                with_vectors=True,
                with_payload=True,  # need payload to map back to func_id
            )
        except Exception as exc:
            logger.debug(f"get_embeddings_batch retrieve failed: {exc}")
            return {}

        output: dict[str, np.ndarray] = {}
        for point in results:
            # Try payload func_id first, fall back to reverse id map
            payload = getattr(point, "payload", None) or {}
            func_id = payload.get("func_id") or id_to_func.get(point.id)
            if func_id is None:
                continue
            vec = getattr(point, "vector", None)
            if vec is None:
                continue
            if isinstance(vec, dict):
                vec = next(iter(vec.values()), None)
            if vec is not None:
                output[func_id] = np.array(vec, dtype=np.float32)
        return output

    def get_collection_info(self) -> dict:
        info = self.client.get_collection(self.collection_name)
        return {
            "name": self.collection_name,
            "status": str(info.status),
            "point_count": info.points_count,
            "vector_size": info.config.params.vectors.size
            if hasattr(info.config.params.vectors, "size")
            else self.embedding_dim,
        }

    def is_healthy(self) -> bool:
        try:
            self.client.get_collections()
            return True
        except Exception:
            return False
