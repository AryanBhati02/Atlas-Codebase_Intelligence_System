"""
node_features.py
----------------
Vocabulary class and feature-extraction utilities for FunctionNode objects.
Used to build token-index sequences for embedding input and to produce
per-node feature dicts consumed by the GATv2 training pipeline.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tree_sitter_parser import FunctionNode

_CAMEL_SPLIT_RE = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_NON_ALPHA_RE = re.compile(r"[^a-z0-9]+")


def tokenize_name(name: str) -> list[str]:
    """
    Split a function name into lower-cased tokens.

    Examples::
        "parseJsonResponse"   → ["parse", "json", "response"]
        "parse_json_response" → ["parse", "json", "response"]
        "parse_jsonResponse"  → ["parse", "json", "response"]
        "APIRouter"           → ["api", "router"]
    """
    
    camel_split = _CAMEL_SPLIT_RE.sub("_", name)
    
    tokens = _NON_ALPHA_RE.split(camel_split.lower())
    
    return [t for t in tokens if t]


def _tokenize_body_sample(text: str, max_tokens: int = 50) -> list[str]:
    """
    Tokenise the first *max_tokens* whitespace-delimited tokens of *text*,
    applying the same camelCase + underscore splitting.
    """
    raw_tokens = text.split()[:max_tokens]
    out: list[str] = []
    for raw in raw_tokens:
        out.extend(tokenize_name(raw))
    return out

class Vocabulary:
    """Token-to-integer index vocabulary for function names and bodies."""

    PAD_TOKEN = "<PAD>"
    UNK_TOKEN = "<UNK>"

    def __init__(self) -> None:
        self.token_to_idx: dict[str, int] = {
            self.PAD_TOKEN: 0,
            self.UNK_TOKEN: 1,
        }
        self.idx_to_token: dict[int, str] = {
            0: self.PAD_TOKEN,
            1: self.UNK_TOKEN,
        }
        self.next_idx: int = 2

    
    def _add_token(self, token: str) -> None:
        if token not in self.token_to_idx:
            self.token_to_idx[token] = self.next_idx
            self.idx_to_token[self.next_idx] = token
            self.next_idx += 1

    
    def build_from_nodes(self, nodes: list["FunctionNode"]) -> "Vocabulary":
        """
        Populate the vocabulary from all function names and body samples.
        Returns *self* for chaining.
        """
        for node in nodes:
            for token in tokenize_name(node.name):
                self._add_token(token)
            for token in _tokenize_body_sample(node.body_text, max_tokens=50):
                self._add_token(token)
        return self

    
    def encode(self, text: str, max_length: int = 64) -> list[int]:
        """
        Tokenise *text* and return a list of integer indices, padded or
        truncated to *max_length*.
        """
        tokens = tokenize_name(text)
        indices = [
            self.token_to_idx.get(t, self.token_to_idx[self.UNK_TOKEN])
            for t in tokens
        ]
        
        indices = indices[:max_length]
        
        pad_idx = self.token_to_idx[self.PAD_TOKEN]
        while len(indices) < max_length:
            indices.append(pad_idx)
        return indices

    
    def __len__(self) -> int:
        return self.next_idx

    
    def save(self, path: str) -> None:
        """Save token_to_idx mapping as JSON."""
        Path(path).write_text(
            json.dumps(self.token_to_idx, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load(self, path: str) -> "Vocabulary":
        """Load token_to_idx from JSON and rebuild idx_to_token. Returns self."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.token_to_idx = {k: int(v) for k, v in data.items()}
        self.idx_to_token = {v: k for k, v in self.token_to_idx.items()}
        self.next_idx = max(self.token_to_idx.values()) + 1 if self.token_to_idx else 2
        return self







def extract_node_features(node: "FunctionNode", vocab: Vocabulary) -> dict:
    """
    Return a feature dict for a single FunctionNode.

    ``fan_in`` is left as 0 here — it will be filled in after the call graph
    is built (see call_graph_builder.py).

    Keys
    ----
    token_ids    : list[int]  — encoded name + body prefix, length = 64
    complexity   : int
    fan_in       : int        (0 placeholder; update post-graph)
    fan_out      : int        (based on calls_to list length)
    loc          : int        — line_end − line_start
    param_count  : int
    has_docstring: int        — 1 if docstring present, else 0
    """
    combined_text = node.name + " " + node.body_text[:200]
    return {
        "token_ids": vocab.encode(combined_text, max_length=64),
        "complexity": node.complexity,
        "fan_in": 0,
        "fan_out": len(node.calls_to),
        "loc": max(0, node.line_end - node.line_start),
        "param_count": len(node.parameters),
        "has_docstring": 1 if node.docstring else 0,
    }
