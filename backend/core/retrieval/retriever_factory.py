from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import torch

logger = logging.getLogger("codebase-intel.retriever_factory")

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

_retriever_instance = None


def get_retriever():
    global _retriever_instance
    if _retriever_instance is not None:
        return _retriever_instance

    import networkx as nx

    from core.model.function_encoder import FunctionEncoder
    from core.model.dataset import Vocabulary
    from core.retrieval.qdrant_store import AtlasQdrantStore
    from core.retrieval.bm25_index import BM25Index
    from core.retrieval.agentic_retrieval import AgenticRetriever

    checkpoint_path = _BACKEND_DIR / "training" / "checkpoints" / "best_model.pt"
    vocab_path = _BACKEND_DIR / "training" / "data" / "vocab.json"
    bm25_path = _BACKEND_DIR / "training" / "data" / "bm25_index.pkl"
    graph_path = _BACKEND_DIR / "training" / "data" / "call_graph.json"

    if not vocab_path.exists():
        raise FileNotFoundError(f"Vocabulary not found: {vocab_path}")
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"Model checkpoint not found: {checkpoint_path}")
    if not bm25_path.exists():
        raise FileNotFoundError(
            f"BM25 index not found: {bm25_path}. Run index_repo.py first."
        )

    logger.info(f"Loading vocabulary from {vocab_path}")
    vocab = Vocabulary.from_file(str(vocab_path))
    vocab_size = vocab.size

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Retriever using device: {device}")

    logger.info(f"Loading FunctionEncoder from {checkpoint_path}")
    encoder = FunctionEncoder(vocab_size=vocab_size)
    checkpoint = torch.load(str(checkpoint_path), map_location=device)
    state_dict = checkpoint.get("model_state_dict", checkpoint)
    encoder.load_state_dict(state_dict)
    encoder.to(device)
    encoder.eval()
    logger.info("FunctionEncoder loaded")

    logger.info("Connecting to Qdrant ...")
    qdrant = AtlasQdrantStore()

    logger.info(f"Loading BM25 index from {bm25_path}")
    bm25 = BM25Index()
    bm25.load(str(bm25_path))

    graph: nx.DiGraph = nx.DiGraph()
    if graph_path.exists():
        logger.info(f"Loading call graph from {graph_path}")
        try:
            graph_data = json.loads(graph_path.read_text(encoding="utf-8"))
            for node in graph_data.get("nodes", []):
                graph.add_node(node["id"], **{k: v for k, v in node.items() if k != "id"})
            for edge in graph_data.get("edges", []):
                graph.add_edge(edge["source"], edge["target"])
            logger.info(
                f"Call graph loaded: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges"
            )
        except Exception as exc:
            logger.warning(f"Failed to load call graph (continuing without it): {exc}")
    else:
        logger.warning(
            f"Call graph not found at {graph_path}. Graph-expansion will be disabled. "
            f"Run index_repo.py to generate it."
        )

    retriever = AgenticRetriever(
        encoder=encoder,
        qdrant=qdrant,
        bm25=bm25,
        graph=graph,
        vocab=vocab,
    )

    _retriever_instance = retriever
    logger.info("AgenticRetriever singleton created and cached")
    return _retriever_instance


def reset_retriever() -> None:
    global _retriever_instance
    _retriever_instance = None
    logger.info("AgenticRetriever singleton reset")
