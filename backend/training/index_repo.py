from __future__ import annotations

import json
import logging
import os
import sys
from collections import Counter
from pathlib import Path

import argparse
import numpy as np
import torch

logger = logging.getLogger("codebase-intel.index_repo")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


def _make_single_graph(token_ids: list[int], device: torch.device):
    from torch_geometric.data import Data

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

    x = torch.tensor(token_ids, dtype=torch.long, device=device)
    edge_index = torch.tensor([src, dst], dtype=torch.long, device=device)
    edge_attr = torch.ones(edge_index.shape[1], 1, dtype=torch.float, device=device)
    return Data(x=x, edge_index=edge_index, edge_attr=edge_attr)


def embed_functions(functions: list, vocab, encoder, device: torch.device, batch_size: int = 64) -> np.ndarray:
    from torch_geometric.data import Batch

    encoder.eval()
    all_embeddings: list[np.ndarray] = []

    for batch_start in range(0, len(functions), batch_size):
        batch_funcs = functions[batch_start : batch_start + batch_size]
        data_list = []
        for func in batch_funcs:
            combined = func.name + " " + (func.body_text or "")[:200]
            token_ids = vocab.encode(combined, max_length=64)
            data = _make_single_graph(token_ids, device)
            data_list.append(data)

        batched = Batch.from_data_list(data_list).to(device)

        with torch.no_grad():
            embs = encoder(batched.x, batched.edge_index, batched.edge_attr, batched.batch)

        all_embeddings.append(embs.cpu().numpy())
        if (batch_start // batch_size + 1) % 10 == 0:
            logger.info(
                f"Embedded {min(batch_start + batch_size, len(functions))}/{len(functions)} functions"
            )

    return np.vstack(all_embeddings).astype(np.float32)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Embed and index a repository into Atlas Qdrant store."
    )
    parser.add_argument(
        "--repo_path", required=True, help="Path to the cloned repository to index."
    )
    parser.add_argument(
        "--checkpoint",
        default=str(_BACKEND_DIR / "training" / "checkpoints" / "best_model.pt"),
        help="Path to the trained FunctionEncoder checkpoint.",
    )
    parser.add_argument(
        "--vocab_path",
        default=str(_BACKEND_DIR / "training" / "data" / "vocab.json"),
        help="Path to vocab.json.",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and recreate the Qdrant collection before indexing.",
    )
    parser.add_argument(
        "--qdrant_host", default="localhost", help="Qdrant host (default: localhost)"
    )
    parser.add_argument(
        "--qdrant_port", type=int, default=6333, help="Qdrant port (default: 6333)"
    )
    parser.add_argument(
        "--batch_size", type=int, default=64, help="Embedding batch size (default: 64)"
    )
    args = parser.parse_args()

    repo_path = Path(args.repo_path).resolve()
    if not repo_path.exists():
        logger.error(f"Repository path does not exist: {repo_path}")
        sys.exit(1)

    checkpoint_path = Path(args.checkpoint)
    vocab_path = Path(args.vocab_path)
    for p, label in [(checkpoint_path, "checkpoint"), (vocab_path, "vocab")]:
        if not p.exists():
            logger.error(f"{label} not found: {p}")
            sys.exit(1)

    from core.model.function_encoder import FunctionEncoder
    from core.model.dataset import Vocabulary
    from core.parser.tree_sitter_parser import TreeSitterParser
    from core.parser.call_graph_builder import build_call_graph, graph_to_json
    from core.tracer.git_coedits import GitCoEditExtractor
    from core.tracer.fusion_engine import FusionEngine
    from core.retrieval.qdrant_store import AtlasQdrantStore
    from core.retrieval.bm25_index import BM25Index

    logger.info(f"Loading vocabulary from {vocab_path}")
    vocab = Vocabulary.from_file(str(vocab_path))
    vocab_size = vocab.size
    logger.info(f"Vocabulary size: {vocab_size}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Using device: {device}")

    logger.info(f"Loading FunctionEncoder from {checkpoint_path}")
    encoder = FunctionEncoder(vocab_size=vocab_size)
    checkpoint = torch.load(str(checkpoint_path), map_location=device)
    state_dict = checkpoint.get("model_state_dict", checkpoint)
    encoder.load_state_dict(state_dict)
    encoder.to(device)
    encoder.eval()
    logger.info("FunctionEncoder loaded successfully")

    logger.info(f"Parsing repository: {repo_path}")
    ts_parser = TreeSitterParser()
    functions = ts_parser.parse_repository(str(repo_path))
    logger.info(f"Found {len(functions)} functions across the repository")

    if not functions:
        logger.error("No functions parsed — check that tree-sitter grammars are installed.")
        sys.exit(1)

    logger.info("Building call graph ...")
    call_graph = build_call_graph(functions)

    coedit_data = {}
    git_dir = repo_path / ".git"
    if git_dir.exists():
        logger.info("Extracting git co-edit data ...")
        try:
            extractor = GitCoEditExtractor(str(repo_path))
            coedit_data = extractor.get_function_coedits(call_graph)
            logger.info(f"Extracted {len(coedit_data)} co-edit pairs")
        except Exception as exc:
            logger.warning(f"Git co-edit extraction failed (non-fatal): {exc}")

    if coedit_data:
        logger.info("Running FusionEngine ...")
        fusion_engine = FusionEngine()
        fused_graph = fusion_engine.fuse(call_graph, coedit_data=coedit_data)
    else:
        fused_graph = call_graph

    logger.info(f"Embedding {len(functions)} functions ...")
    embeddings = embed_functions(functions, vocab, encoder, device, batch_size=args.batch_size)
    logger.info(f"Embeddings shape: {embeddings.shape}")

    logger.info("Connecting to Qdrant ...")
    qdrant_store = AtlasQdrantStore(host=args.qdrant_host, port=args.qdrant_port)
    qdrant_store.create_collection(recreate=args.recreate)

    logger.info("Upserting function embeddings ...")
    qdrant_store.upsert_functions(functions, embeddings)

    logger.info("Building BM25 index ...")
    bm25_index = BM25Index()
    bm25_index.build_from_functions(functions)

    bm25_path = _BACKEND_DIR / "training" / "data" / "bm25_index.pkl"
    bm25_index.save(str(bm25_path))

    graph_json_path = _BACKEND_DIR / "training" / "data" / "call_graph.json"
    graph_json_path.parent.mkdir(parents=True, exist_ok=True)
    graph_data = graph_to_json(fused_graph)
    graph_json_path.write_text(
        json.dumps(graph_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info(f"Call graph saved to {graph_json_path}")

    lang_counter: Counter = Counter(f.language for f in functions)
    file_counter: Counter = Counter(f.file_path for f in functions)
    complexity_sorted = sorted(functions, key=lambda f: f.complexity, reverse=True)

    collection_info = qdrant_store.get_collection_info()

    print("\n" + "=" * 60)
    print("  Atlas Indexing Complete")
    print("=" * 60)
    print(f"  Indexed {len(functions)} functions from {len(file_counter)} files")
    print(f"  Qdrant collection: {collection_info['name']} ({collection_info['point_count']} points)")
    print(f"  BM25 index: {len(functions)} documents -> {bm25_path}")
    print(f"  Call graph: {fused_graph.number_of_nodes()} nodes, {fused_graph.number_of_edges()} edges")
    print(f"  Languages: " + ", ".join(f"{lang}={cnt}" for lang, cnt in lang_counter.most_common()))
    print("\n  Top 5 most complex functions:")
    for func in complexity_sorted[:5]:
        print(f"    [{func.complexity}] {func.name} ({func.file_path}:{func.line_start})")
    print("=" * 60)


if __name__ == "__main__":
    main()
