"""
eval_mrr.py
-----------
MRR@10 evaluation script for the trained GATv2 function encoder.

Metric: Mean Reciprocal Rank at cutoff 10 (MRR@10)
  For each query function q in the test set:
    1. Embed q with the trained model.
    2. Rank all other test embeddings by cosine similarity to q.
    3. Find the rank of the "ground-truth positive" match.
    4. MRR contribution = 1/rank  if rank ≤ 10,  else 0.

Positive match definition (consistent with training):
  The function whose docstring shares the same intent verb as q's docstring.
  Among all candidates with that same intent verb, the one with the highest
  TF-style overlap with q's docstring is chosen as the single positive.
  If no candidate with the same intent verb exists → query is skipped.

Usage:
    python training/eval_mrr.py \\
        --checkpoint training/checkpoints/best_model.pt \\
        --data_dir   training/data/codesearchnet_python \\
        --vocab_path training/data/vocab.json \\
        --n_samples  5000

Output:
    Console: MRR@10, Hits@1, Hits@5, Hits@10
    File   : eval/results/mrr_results.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, cast

import torch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _dataset_text(dataset: Any, index: int, key: str) -> str:
    row = cast(Mapping[str, object], dataset[index])
    value = row.get(key, "")
    return value if isinstance(value, str) else ""

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("eval_mrr")

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate GATv2 encoder with MRR@10 on CodeSearchNet Python test split."
    )
    parser.add_argument(
        "--checkpoint",
        default="training/checkpoints/best_model.pt",
        help="Path to trained model checkpoint (.pt).",
    )
    parser.add_argument(
        "--data_dir",
        default="training/data/codesearchnet_python_test",
        help="Path to CodeSearchNet Python TEST split (save_to_disk format). "
             "Falls back to downloading if not found.",
    )
    parser.add_argument(
        "--vocab_path",
        default="training/data/vocab.json",
        help="Path to vocab.json.",
    )
    parser.add_argument(
        "--n_samples",
        type=int,
        default=5000,
        help="Number of test functions to evaluate (full set takes too long).",
    )
    parser.add_argument(
        "--output_dir",
        default="eval/results",
        help="Directory to write mrr_results.json.",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--batch_size",
        type=int,
        default=64,
        help="Embedding batch size (no InfoNCE matrix here — can be larger).",
    )
    parser.add_argument(
        "--static_only",
        action="store_true",
        default=False,
        help="Label results as 'static_only' model (no fused embeddings).",
    )
    return parser.parse_args()

import re as _re

_TOKEN_RE_EVAL = _re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[0-9]+|[^\s\w]")


def _tokenise(code: str) -> list[str]:
    return _TOKEN_RE_EVAL.findall(code)


def _intent_verb(docstring: str) -> str:
    if not docstring:
        return ""
    clean = _re.sub(r"[`*#]", "", docstring).strip()
    words = clean.lower().split()
    fillers = {"a", "an", "the", "this", "that", "it", "is", "are", "to", "in"}
    for word in words:
        alpha = _re.sub(r"[^a-z]", "", word)
        if len(alpha) >= 3 and alpha not in fillers:
            return alpha
    return words[0] if words else ""


def _docstring_overlap(doc_a: str, doc_b: str) -> int:
    """Simple word-overlap count for picking the best positive."""
    words_a = set(doc_a.lower().split())
    words_b = set(doc_b.lower().split())
    return len(words_a & words_b)

def embed_functions(
    model,
    vocab,
    code_list: list[str],
    device: torch.device,
    batch_size: int = 64,
    max_seq_len: int = 64,
) -> torch.Tensor:
    """
    Embed a list of code strings with the trained model.

    Returns FloatTensor [N, out_dim] on CPU.
    """
    from core.model.dataset import create_token_graph  
    from torch_geometric.data import Batch, Data

    model.eval()
    all_embeddings: list[torch.Tensor] = []

    with torch.no_grad():
        for start in range(0, len(code_list), batch_size):
            chunk = code_list[start : start + batch_size]
            graphs: list[Data] = []

            for code in chunk:
                token_ids = vocab.encode(code, max_length=max_seq_len)
                x = torch.tensor(token_ids, dtype=torch.long)
                edge_index, edge_attr = create_token_graph(token_ids, window_size=5)
                graphs.append(Data(x=x, edge_index=edge_index, edge_attr=edge_attr))

            batch = cast(Any, Batch.from_data_list(cast(Any, graphs))).to(device)

            
            prev_ckpt = model.use_checkpointing
            model.use_checkpointing = False
            z = model(batch.x, batch.edge_index, batch.edge_attr, batch.batch)
            model.use_checkpointing = prev_ckpt

            all_embeddings.append(z.cpu())

    return torch.cat(all_embeddings, dim=0)  

def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)
    torch.manual_seed(args.seed)

    backend_root  = Path(__file__).resolve().parents[1]
    ckpt_path     = str(backend_root / args.checkpoint)  if not os.path.isabs(args.checkpoint)  else args.checkpoint
    data_dir      = str(backend_root / args.data_dir)    if not os.path.isabs(args.data_dir)    else args.data_dir
    vocab_path    = str(backend_root / args.vocab_path)  if not os.path.isabs(args.vocab_path)  else args.vocab_path
    output_dir    = str(backend_root / args.output_dir)  if not os.path.isabs(args.output_dir)  else args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Evaluating on {device}")

    from core.model.dataset import Vocabulary  

    if not os.path.isfile(vocab_path):
        logger.error(f"Vocabulary not found: {vocab_path}. Run build_vocab.py first.")
        sys.exit(1)
    vocab = Vocabulary.from_file(vocab_path)
    logger.info(f"Vocabulary loaded: {vocab.size} tokens")

    from core.model.function_encoder import FunctionEncoder  

    if not os.path.isfile(ckpt_path):
        logger.error(f"Checkpoint not found: {ckpt_path}")
        sys.exit(1)

    ckpt = torch.load(ckpt_path, map_location=device)
    stored_vocab_size = ckpt.get("vocab_size", vocab.size)

    model = FunctionEncoder(
        vocab_size=stored_vocab_size,
        embed_dim=128,
        hidden_dim=64,
        out_dim=128,
        heads=4,
        dropout=0.2,
    ).to(device)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()
    logger.info(
        f"Model loaded from {ckpt_path} "
        f"(trained epoch {ckpt.get('epoch', '?')}, "
        f"loss {ckpt.get('loss', float('nan')):.4f})"
    )

    try:
        from datasets import load_from_disk, load_dataset  
    except ImportError:
        logger.error("The `datasets` library is not installed. Run: pip install datasets")
        sys.exit(1)

    
    test_dataset: Any = None
    test_data_path = Path(data_dir)

    if test_data_path.exists():
        try:
            test_dataset = load_from_disk(str(test_data_path))
            logger.info(f"Test dataset loaded from {data_dir}: {len(test_dataset)} examples")
        except Exception as exc:
            logger.warning(f"Could not load from {data_dir}: {exc}")

    if test_dataset is None:
        logger.info("Downloading CodeSearchNet Python test split …")
        try:
            full_ds = load_dataset("code_search_net", "python")
            test_dataset = full_ds["test"]
            
            test_dataset.save_to_disk(str(test_data_path))
            logger.info(f"Test dataset downloaded and saved to {data_dir}: {len(test_dataset)} examples")
        except Exception as exc:
            logger.error(f"Failed to download dataset: {exc}")
            sys.exit(1)

    total_examples = len(test_dataset)
    n_samples = min(args.n_samples, total_examples)
    sample_indices = rng.sample(range(total_examples), n_samples)
    logger.info(f"Sampled {n_samples} functions from {total_examples} total")

    sample_codes      = [_dataset_text(test_dataset, i, "whole_func_string") for i in sample_indices]
    sample_docstrings = [_dataset_text(test_dataset, i, "func_documentation_string") for i in sample_indices]

    sample_verbs = [_intent_verb(doc) for doc in sample_docstrings]

    
    verb_to_positions: dict[str, list[int]] = defaultdict(list)
    for pos, verb in enumerate(sample_verbs):
        if verb:
            verb_to_positions[verb].append(pos)

    query_to_positive: dict[int, int] = {}
    for verb, positions in verb_to_positions.items():
        if len(positions) < 2:
            continue
        for q_pos in positions:
            best_pos  = -1
            best_score = -1
            for candidate_pos in positions:
                if candidate_pos == q_pos:
                    continue
                score = _docstring_overlap(
                    sample_docstrings[q_pos], sample_docstrings[candidate_pos]
                )
                if score > best_score:
                    best_score = score
                    best_pos   = candidate_pos
            if best_pos >= 0:
                query_to_positive[q_pos] = best_pos

    eligible_queries = list(query_to_positive.keys())
    logger.info(
        f"Eligible queries (have at least one positive): {len(eligible_queries)} "
        f"out of {n_samples}"
    )
    if not eligible_queries:
        logger.error("No eligible queries found. The test split may be too small or lack docstrings.")
        sys.exit(1)

    
    logger.info("Computing embeddings for all sampled functions …")
    embeddings = embed_functions(
        model, vocab, sample_codes, device,
        batch_size=args.batch_size, max_seq_len=64,
    )   

    logger.info("Computing MRR@10 …")

    reciprocal_ranks: list[float] = []
    hits_at_1  = 0
    hits_at_5  = 0
    hits_at_10 = 0

    emb_norm = torch.nn.functional.normalize(embeddings, dim=-1)   

    for q_pos in eligible_queries:
        gold_pos = query_to_positive[q_pos]
        q_vec    = emb_norm[q_pos].unsqueeze(0)         

        
        sims = torch.mv(emb_norm, q_vec.squeeze(0))     

        
        sims[q_pos] = -2.0

        
        gold_sim = sims[gold_pos].item()
        rank = int((sims > gold_sim).sum().item()) + 1  

        if rank <= 10:
            reciprocal_ranks.append(1.0 / rank)
            hits_at_10 += 1
        else:
            reciprocal_ranks.append(0.0)

        if rank == 1:
            hits_at_1 += 1
        if rank <= 5:
            hits_at_5 += 1

    n_queries = len(eligible_queries)
    mrr       = sum(reciprocal_ranks) / n_queries
    hits1     = hits_at_1  / n_queries
    hits5     = hits_at_5  / n_queries
    hits10    = hits_at_10 / n_queries

    from datetime import datetime, timezone

    model_label = "static_only" if args.static_only else "fused"

    # ── tabulate output ────────────────────────────────────────────────────
    try:
        from tabulate import tabulate as _tabulate
        table_rows = [
            ["MRR@10",    f"{mrr:.4f}",   f"{mrr * 100:.2f}%"],
            ["Hits@1",    f"{hits1:.4f}",  f"{hits1 * 100:.2f}%"],
            ["Hits@5",    f"{hits5:.4f}",  f"{hits5 * 100:.2f}%"],
            ["Hits@10",   f"{hits10:.4f}", f"{hits10 * 100:.2f}%"],
        ]
        print()
        print(_tabulate(
            table_rows,
            headers=["Metric", "Score", "Percentage"],
            tablefmt="simple",
        ))
        print(f"  Queries evaluated : {n_queries}  |  Model : {model_label}")
    except ImportError:
        # Fallback when tabulate not installed
        print()
        print("=" * 55)
        print(f"  MRR@10 Evaluation Results  [{model_label}]")
        print("=" * 55)
        print(f"  MRR@10 = {mrr:.4f}  on {n_queries} test queries")
        print(f"  Hits@1  : {hits1:.2%}")
        print(f"  Hits@5  : {hits5:.2%}")
        print(f"  Hits@10 : {hits10:.2%}")
        print("=" * 55)

    timestamp = datetime.now(tz=timezone.utc).isoformat()
    results = {
        "mrr_at_10": round(mrr, 6),
        "hits_at_1": round(hits1, 6),
        "hits_at_5": round(hits5, 6),
        "hits_at_10": round(hits10, 6),
        "num_queries": n_queries,
        "model": model_label,
        "timestamp": timestamp,
        "checkpoint": ckpt_path,
        "n_total_sampled": n_samples,
        "model_epoch": ckpt.get("epoch"),
        "model_train_loss": ckpt.get("loss"),
    }
    out_path = os.path.join(output_dir, "mrr_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Results saved to {out_path}")


if __name__ == "__main__":
    main()
