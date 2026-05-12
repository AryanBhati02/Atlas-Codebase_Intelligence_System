"""
dataset.py
----------
FunctionPairDataset — PyTorch Dataset for contrastive GATv2 training.

Data source: CodeSearchNet Python (loaded via HuggingFace `datasets`).

Positive pair construction (fast heuristic):
  Group functions whose docstring starts with the same *intent verb* (first
  word, lowercased).  Within each group pick random pairs.  Functions that
  share an intent are semantically related — a good contrastive positive.

Graph representation per function:
  Each function is encoded as a token graph where:
    - Nodes  = token positions (max_seq_len nodes total)
    - Edges  = sliding-window connectivity (window_size=5) + self-loops
    - x      = token IDs  [max_seq_len]   (long)
    - edge_attr = 1.0 for all edges       [E, 1]  (float)
  The batch dimension is handled by PyG's Batch.from_data_list().

Vocabulary:
  Simple character-split token vocabulary stored as vocab.json
  {"<PAD>": 0, "<UNK>": 1, "def": 2, ...}

Usage:
    ds      = FunctionPairDataset("training/data/codesearchnet_python",
                                   "training/data/vocab.json")
    loader  = DataLoader(ds, batch_size=16, collate_fn=collate_pairs)
    batch_a, batch_b = next(iter(loader))
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import torch
from torch.utils.data import Dataset
from torch_geometric.data import Batch, Data

logger = logging.getLogger("codebase-intel.dataset")
_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[0-9]+|[^\s\w]")


def _tokenise(code: str) -> List[str]:
    """Split source code into a list of string tokens."""
    return _TOKEN_RE.findall(code)


class Vocabulary:
    """
    Token-to-index mapping.

    Special tokens:
      0 → <PAD>   (padding / out-of-vocabulary)
      1 → <UNK>   (unknown token)
    """

    PAD_IDX = 0
    UNK_IDX = 1

    def __init__(self, token_to_idx: Optional[Dict[str, int]] = None) -> None:
        if token_to_idx is not None:
            self.token_to_idx = token_to_idx
        else:
            self.token_to_idx = {"<PAD>": self.PAD_IDX, "<UNK>": self.UNK_IDX}

    @property
    def size(self) -> int:
        return len(self.token_to_idx)

    def encode(self, code: str, max_length: int = 64) -> List[int]:
        """Tokenise *code* and return a list of indices (truncated/padded to max_length)."""
        tokens = _tokenise(code)[:max_length]
        ids = [self.token_to_idx.get(t, self.UNK_IDX) for t in tokens]
        
        ids += [self.PAD_IDX] * (max_length - len(ids))
        return ids

    @classmethod
    def from_file(cls, vocab_path: str) -> "Vocabulary":
        with open(vocab_path, "r", encoding="utf-8") as f:
            token_to_idx = json.load(f)
        return cls(token_to_idx)

    def save(self, vocab_path: str) -> None:
        os.makedirs(Path(vocab_path).parent, exist_ok=True)
        with open(vocab_path, "w", encoding="utf-8") as f:
            json.dump(self.token_to_idx, f, indent=2)

    @classmethod
    def build_from_codes(
        cls,
        code_samples: List[str],
        max_vocab_size: int = 10_000,
    ) -> "Vocabulary":
        """
        Build vocabulary from a list of source-code strings.
        The most frequent max_vocab_size tokens are kept.
        """
        freq: Dict[str, int] = defaultdict(int)
        for code in code_samples:
            for tok in _tokenise(code):
                freq[tok] += 1

        
        sorted_tokens = sorted(freq.keys(), key=lambda t: freq[t], reverse=True)
        top_tokens = sorted_tokens[: max_vocab_size - 2]

        token_to_idx: Dict[str, int] = {"<PAD>": cls.PAD_IDX, "<UNK>": cls.UNK_IDX}
        for idx, tok in enumerate(top_tokens, start=2):
            token_to_idx[tok] = idx

        vocab = cls(token_to_idx)
        logger.info(f"Built vocabulary: {vocab.size} tokens from {len(code_samples)} samples.")
        return vocab

def create_token_graph(
    token_ids: List[int],
    window_size: int = 5,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """
    Build a sliding-window token graph.

    For token at position i, connect to all tokens in the window
    [max(0, i - window_size), min(N-1, i + window_size)] plus a self-loop.

    Parameters
    ----------
    token_ids   : list of integer token IDs, length N
    window_size : half-width of the connectivity window

    Returns
    -------
    edge_index : LongTensor  [2, E]
    edge_attr  : FloatTensor [E, 1]  (all 1.0 — fusion weights only at inference)
    """
    N = len(token_ids)
    src: List[int] = []
    dst: List[int] = []

    for i in range(N):
        
        src.append(i)
        dst.append(i)
        
        lo = max(0, i - window_size)
        hi = min(N - 1, i + window_size)
        for j in range(lo, hi + 1):
            if j != i:
                src.append(i)
                dst.append(j)

    edge_index = torch.tensor([src, dst], dtype=torch.long)
    edge_attr  = torch.ones(edge_index.shape[1], 1, dtype=torch.float)
    return edge_index, edge_attr

def _extract_intent_verb(docstring: str) -> str:
    """
    Return the first meaningful lowercase word of a docstring.
    Used to group functions by their top-level intent.
    """
    if not docstring:
        return ""
    
    clean = re.sub(r"[`*#]", "", docstring).strip()
    words = clean.lower().split()
    if not words:
        return ""
    
    fillers = {"a", "an", "the", "this", "that", "it", "is", "are", "to", "in"}
    for word in words:
        alpha = re.sub(r"[^a-z]", "", word)
        if len(alpha) >= 3 and alpha not in fillers:
            return alpha
    return words[0]


def build_pairs_from_codesearchnet(
    dataset,
    max_pairs: int = 200_000,
    seed: int = 42,
) -> List[Tuple[int, int]]:
    """
    Create positive training pairs by grouping functions with the same
    *intent verb* (first meaningful word of their docstring).

    Parameters
    ----------
    dataset   : HuggingFace dataset split with 'docstring' and 'code' fields
    max_pairs : maximum number of pairs to generate (default 200 K)
    seed      : random seed for reproducibility

    Returns
    -------
    list of (idx_a, idx_b) index pairs into the dataset
    """
    rng = random.Random(seed)
    groups: Dict[str, List[int]] = defaultdict(list)

    for idx, example in enumerate(dataset):
        verb = _extract_intent_verb(example.get("func_documentation_string", "") or "")
        if verb:
            groups[verb].append(idx)

    pairs: List[Tuple[int, int]] = []
    for verb, indices in groups.items():
        if len(indices) < 2:
            continue
        rng.shuffle(indices)
        
        for k in range(0, len(indices) - 1, 2):
            pairs.append((indices[k], indices[k + 1]))
            if len(pairs) >= max_pairs:
                break
        if len(pairs) >= max_pairs:
            break

    rng.shuffle(pairs)
    logger.info(
        f"Built {len(pairs)} positive pairs from {len(groups)} intent-verb groups."
    )
    return pairs[:max_pairs]

class FunctionPairDataset(Dataset):
    """
    PyTorch Dataset that yields positive (Data, Data) pairs for contrastive
    GATv2 training.

    Each item is a tuple of two PyG Data objects, one per function in the pair.

    Parameters
    ----------
    data_dir    : path to CodeSearchNet Python split saved with
                  datasets.save_to_disk() (contains dataset_dict.json etc.)
    vocab_path  : path to vocab.json produced by build_vocab.py
    max_seq_len : maximum number of tokens (= graph nodes) per function
    seed        : random seed for pair construction
    """

    def __init__(
        self,
        data_dir: str,
        vocab_path: str,
        max_seq_len: int = 64,
        seed: int = 42,
        max_pairs: int = 200_000,
    ) -> None:
        super().__init__()
        self.max_seq_len = max_seq_len

        
        logger.info(f"Loading vocabulary from {vocab_path}")
        self.vocab = Vocabulary.from_file(vocab_path)

        
        logger.info(f"Loading CodeSearchNet dataset from {data_dir}")
        self.dataset: Any
        try:
            from datasets import load_from_disk  
            self.dataset = load_from_disk(data_dir)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load dataset from {data_dir}. "
                f"Run `build_vocab.py --download` first. Original error: {exc}"
            ) from exc

        
        logger.info("Building positive training pairs …")
        self.pairs: List[Tuple[int, int]] = build_pairs_from_codesearchnet(
            self.dataset, seed=seed, max_pairs=max_pairs
        )

        logger.info(
            f"FunctionPairDataset ready: {len(self.pairs)} pairs, "
            f"vocab_size={self.vocab.size}, max_seq_len={max_seq_len}"
        )

    def __len__(self) -> int:
        return len(self.pairs)

    def __getitem__(self, idx: int) -> Tuple[Data, Data]:
        """
        Return a (data_a, data_b) pair of PyG Data objects.

        Each Data has:
          x          : LongTensor [max_seq_len]   — token IDs
          edge_index : LongTensor [2, E]
          edge_attr  : FloatTensor [E, 1]         — all 1.0 during training
        """
        idx_a, idx_b = self.pairs[idx]
        code_a = self.dataset[idx_a].get("whole_func_string", "") or ""
        code_b = self.dataset[idx_b].get("whole_func_string", "") or ""

        data_a = self._make_graph(code_a)
        data_b = self._make_graph(code_b)
        return data_a, data_b

    def _make_graph(self, code: str) -> Data:
        """
        Turn a raw source-code string into a PyG Data object.

        Nodes  = token positions (N = max_seq_len)
        Edges  = sliding-window (window=5) + self-loops
        """
        token_ids = self.vocab.encode(code, max_length=self.max_seq_len)
        x = torch.tensor(token_ids, dtype=torch.long)   

        edge_index, edge_attr = create_token_graph(token_ids, window_size=5)

        return Data(x=x, edge_index=edge_index, edge_attr=edge_attr)

def collate_pairs(
    batch: List[Tuple[Data, Data]],
) -> Tuple[Batch, Batch]:
    """
    Custom collate function that batches a list of (Data, Data) pairs into
    two PyG Batch objects.

    Usage:
        DataLoader(dataset, batch_size=16, collate_fn=collate_pairs)
    """
    batch_a = Batch.from_data_list([pair[0] for pair in batch])
    batch_b = Batch.from_data_list([pair[1] for pair in batch])
    return batch_a, batch_b
