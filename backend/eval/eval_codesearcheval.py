"""
eval_codesearcheval.py
----------------------
CodeSearchEval behavioral precision evaluation.

Tests whether Atlas search returns functions that actually DO what the query
describes. Uses 50 handcrafted behavioral queries covering a broad spectrum
of code patterns (works against any indexed codebase).

Evaluation methodology:
  - Retrieve top-5 results for each query
  - Check relevance using keyword matching against result name / docstring / func_id
  - Compute Precision@1 and Precision@5

Usage (full retriever):
    python eval/eval_codesearcheval.py --output eval/results/codesearcheval_results.json

Usage (embedding-only fallback — no Qdrant/BM25 required):
    python eval/eval_codesearcheval.py --use_embedding_fallback
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("eval_codesearcheval")

BEHAVIORAL_QUERIES = [
    # Algorithms
    {"query": "sort a list of items",                         "expected_behavior": "sort sorted order",              "tags": ["algorithm"]},
    {"query": "search for an element in a collection",        "expected_behavior": "search find lookup get",         "tags": ["algorithm"]},
    {"query": "filter items based on a condition",            "expected_behavior": "filter select condition query",  "tags": ["algorithm"]},
    {"query": "compute the sum or total of values",           "expected_behavior": "sum total aggregate count",      "tags": ["algorithm"]},
    # Serialization
    {"query": "parse JSON data from a string",                "expected_behavior": "json parse decode load",         "tags": ["serialization"]},
    {"query": "serialize an object to JSON",                  "expected_behavior": "json serialize encode dump",     "tags": ["serialization"]},
    {"query": "read and write CSV files",                     "expected_behavior": "csv read write",                 "tags": ["serialization"]},
    {"query": "encode data with base64",                      "expected_behavior": "base64 encode decode",           "tags": ["encoding"]},
    # Validation
    {"query": "validate user email address",                  "expected_behavior": "email validate check clean",     "tags": ["validation"]},
    {"query": "validate form input from a request",           "expected_behavior": "validate input form clean",      "tags": ["validation"]},
    {"query": "check if a string matches a pattern",          "expected_behavior": "regex match pattern check",      "tags": ["validation"]},
    {"query": "sanitize user input to prevent injection",     "expected_behavior": "sanitize clean escape",          "tags": ["security"]},
    # Networking & HTTP
    {"query": "handle HTTP authentication",                   "expected_behavior": "auth authenticate token bearer", "tags": ["security"]},
    {"query": "retry a failed network request",               "expected_behavior": "retry attempt backoff",          "tags": ["networking"]},
    {"query": "handle HTTP timeout and connection error",     "expected_behavior": "timeout error connection handle", "tags": ["networking"]},
    {"query": "make an HTTP GET request",                     "expected_behavior": "get request http fetch",         "tags": ["networking"]},
    {"query": "parse query parameters from a URL",            "expected_behavior": "query params url parse",         "tags": ["routing"]},
    {"query": "build and construct a URL",                    "expected_behavior": "url build construct join",       "tags": ["routing"]},
    {"query": "handle CORS headers in a response",            "expected_behavior": "cors origin headers allow",      "tags": ["middleware"]},
    {"query": "rate limit incoming requests",                 "expected_behavior": "rate limit throttle",            "tags": ["middleware"]},
    # Configuration & Logging
    {"query": "read configuration from environment variables","expected_behavior": "env environment config load settings", "tags": ["config"]},
    {"query": "load settings from a config file",             "expected_behavior": "config settings load read file", "tags": ["config"]},
    {"query": "log error messages with timestamps",           "expected_behavior": "log error message warn info",    "tags": ["logging"]},
    {"query": "write structured logs in JSON format",         "expected_behavior": "log json structured format",     "tags": ["logging"]},
    # Database
    {"query": "paginate database query results",              "expected_behavior": "paginate page limit offset",     "tags": ["database"]},
    {"query": "execute a database query",                     "expected_behavior": "query execute db select",        "tags": ["database"]},
    {"query": "insert a record into the database",            "expected_behavior": "insert create save add",         "tags": ["database"]},
    {"query": "manage database connection pooling",           "expected_behavior": "connection pool database",       "tags": ["database"]},
    # Caching
    {"query": "cache results to avoid recomputation",         "expected_behavior": "cache store memoize",            "tags": ["caching"]},
    {"query": "invalidate or clear cache entries",            "expected_behavior": "cache clear invalidate expire",  "tags": ["caching"]},
    # Datetime
    {"query": "convert between date formats",                 "expected_behavior": "date format convert parse",      "tags": ["datetime"]},
    {"query": "calculate a time difference or duration",      "expected_behavior": "time duration diff delta",       "tags": ["datetime"]},
    # File I/O
    {"query": "read contents of a file",                      "expected_behavior": "file read open content",         "tags": ["file_io"]},
    {"query": "write data to a file",                         "expected_behavior": "file write save output",         "tags": ["file_io"]},
    {"query": "handle file upload from a request",            "expected_behavior": "upload file stream save",        "tags": ["file_io"]},
    # Auth & Sessions
    {"query": "generate authentication token or JWT",         "expected_behavior": "token jwt generate sign key",   "tags": ["security"]},
    {"query": "manage user sessions",                         "expected_behavior": "session user store get set",     "tags": ["session"]},
    {"query": "handle cookie setting in response",            "expected_behavior": "cookie set response header",     "tags": ["cookie"]},
    {"query": "hash a password securely",                     "expected_behavior": "hash password bcrypt security",  "tags": ["security"]},
    # Async
    {"query": "run background tasks asynchronously",          "expected_behavior": "async background task run",      "tags": ["async"]},
    {"query": "handle WebSocket connections",                 "expected_behavior": "websocket connect send receive",  "tags": ["websocket"]},
    {"query": "await an async operation",                     "expected_behavior": "async await coroutine",          "tags": ["async"]},
    # API / Routing
    {"query": "define an API route handler",                  "expected_behavior": "route path handler dispatch view", "tags": ["routing"]},
    {"query": "return a JSON response",                       "expected_behavior": "response json return render",    "tags": ["response"]},
    {"query": "handle request body parsing",                  "expected_behavior": "body request parse data",        "tags": ["request"]},
    {"query": "add middleware to the application",            "expected_behavior": "middleware add register process", "tags": ["middleware"]},
    # Health & Metrics
    {"query": "check application health status",              "expected_behavior": "health check status ping",       "tags": ["health"]},
    {"query": "collect and expose metrics",                   "expected_behavior": "metrics collect expose measure",  "tags": ["metrics"]},
    # Testing utilities
    {"query": "create a test client for API testing",         "expected_behavior": "test client request mock",       "tags": ["testing"]},
    {"query": "mock an external dependency in tests",         "expected_behavior": "mock patch stub test",           "tags": ["testing"]},
]

assert len(BEHAVIORAL_QUERIES) == 50, f"Expected 50 queries, got {len(BEHAVIORAL_QUERIES)}"


def _id_tokens(func_id: str) -> str:
    """
    Extract searchable tokens from a function ID like 'path/to/file.py::ClassName.method_name'.
    Splits on '::', '.', '/', '_' and lowercases.
    """
    if not func_id:
        return ""
    parts = func_id.replace("::", " ").replace("/", " ").replace(".", " ").replace("_", " ")
    return parts.lower()


def is_relevant(result_name: str, result_docstring: str, expected_behavior: str,
                func_id: str = "") -> bool:
    """
    Heuristic relevance check.
    Returns True if the result's name, docstring, or func_id tokens contain
    at least 1-2 keywords from the expected_behavior string (case-insensitive).

    Improvements over v1:
    - Also checks func_id token stream (catches e.g. 'filter_queryset' for 'filter')
    - Lower threshold for short keyword sets
    """
    keywords = expected_behavior.lower().split()
    # Build search text from name + docstring + func_id token stream
    text = " ".join([
        result_name.replace("_", " ").replace(".", " "),
        (result_docstring or "").replace("_", " ").replace("-", " "),
        _id_tokens(func_id),
    ]).lower()

    matches = sum(1 for kw in keywords if kw in text)
    # Threshold: 1 keyword if <=3 keywords, else 2
    required = 1 if len(keywords) <= 3 else 2
    return matches >= required


class EmbeddingFallbackRetriever:
    """
    Lightweight retriever that runs embedding-only search against Qdrant.
    Used when BM25 index is unavailable. Does NOT require bm25_index.pkl.
    Falls back to direct Qdrant vector search.
    """

    def __init__(self, encoder, qdrant, vocab):
        self.encoder = encoder
        self.qdrant = qdrant
        self.vocab = vocab
        self.device = next(encoder.parameters()).device

    def _embed_query(self, query: str):
        import torch
        import numpy as np
        from torch_geometric.data import Data

        token_ids = self.vocab.encode(query, max_length=64)
        n = len(token_ids)

        src, dst = [], []
        window_size = 5
        for i in range(n):
            src.append(i); dst.append(i)
            lo, hi = max(0, i - window_size), min(n - 1, i + window_size)
            for j in range(lo, hi + 1):
                if j != i:
                    src.append(i); dst.append(j)

        x = torch.tensor(token_ids, dtype=torch.long).to(self.device)
        edge_index = torch.tensor([src, dst], dtype=torch.long).to(self.device)
        edge_attr = torch.ones(edge_index.shape[1], 1, dtype=torch.float).to(self.device)
        batch = torch.zeros(n, dtype=torch.long).to(self.device)

        self.encoder.eval()
        with torch.no_grad():
            emb = self.encoder(x, edge_index, edge_attr, batch)

        import numpy as np
        return emb.squeeze(0).cpu().numpy().astype(np.float32)

    async def retrieve(self, query: str, top_k: int = 10):
        """Async embedding-only retrieval (Qdrant vector search only)."""
        import asyncio

        query_emb = self._embed_query(query)
        results_raw = await asyncio.to_thread(
            self.qdrant.search, query_emb, top_k=top_k
        )
        # Return a list of simple namespace objects matching the AgenticRetriever API
        output = []
        for r in results_raw:
            obj = type("R", (), {
                "func_id": r.get("func_id", ""),
                "name": r.get("name", ""),
                "file_path": r.get("file_path", ""),
                "docstring": r.get("docstring", ""),
                "behavioral_score": float(r.get("score", 0.0)),
                "final_score": float(r.get("score", 0.0)),
            })()
            output.append(obj)
        return output


class CodeSearchEvaluator:
    def __init__(self, retriever):
        self.retriever = retriever

    async def evaluate(self, queries: list[dict]) -> dict:
        """
        For each query:
          1. Retrieve top-5 results
          2. Check relevance of each result
          3. Compute Precision@1 and Precision@5
        """
        p1_scores: list[float] = []
        p5_scores: list[float] = []
        per_query: list[dict] = []
        retrieval_failures = 0
        retrieval_successes = 0

        for q_idx, q_item in enumerate(queries):
            query = q_item["query"]
            expected = q_item["expected_behavior"]

            try:
                results = await self.retriever.retrieve(query, top_k=5)
                retrieval_successes += 1
            except Exception as exc:
                retrieval_failures += 1
                logger.warning(f"  [{q_idx+1}/50] RETRIEVAL FAILED for '{query}': {exc}")
                p1_scores.append(0.0)
                p5_scores.append(0.0)
                per_query.append(
                    {
                        "query": query,
                        "expected_behavior": expected,
                        "top_result_name": "",
                        "top_result_func_id": "",
                        "top_result_score": 0.0,
                        "p_at_1": 0.0,
                        "p_at_5": 0.0,
                        "error": str(exc),
                    }
                )
                continue

            if not results:
                logger.warning(f"  [{q_idx+1}/50] No results returned for '{query}'")

            relevance_flags: list[bool] = []
            for r in results:
                name = getattr(r, "name", "") or ""
                doc = getattr(r, "docstring", "") or ""
                fid = getattr(r, "func_id", "") or ""
                relevance_flags.append(is_relevant(name, doc, expected, func_id=fid))

            p1 = 1.0 if relevance_flags and relevance_flags[0] else 0.0
            p5 = sum(relevance_flags) / max(len(relevance_flags), 1)

            p1_scores.append(p1)
            p5_scores.append(p5)

            top_name = getattr(results[0], "name", "") if results else ""
            top_fid  = getattr(results[0], "func_id", "") if results else ""
            top_score = getattr(results[0], "behavioral_score", 0.0) if results else 0.0

            rel_mark = "✓" if p1 == 1.0 else "✗"
            logger.info(
                f"  [{q_idx+1:02d}/50] {rel_mark} P@1={p1:.0f} P@5={p5:.2f}  "
                f"query='{query[:40]}'  top='{top_name}' ({top_fid[:50]})"
            )
            per_query.append(
                {
                    "query": query,
                    "expected_behavior": expected,
                    "tags": q_item.get("tags", []),
                    "top_result_name": top_name,
                    "top_result_func_id": top_fid,
                    "top_result_score": round(float(top_score), 4),
                    "p_at_1": p1,
                    "p_at_5": round(p5, 4),
                    "relevant": relevance_flags,
                }
            )

        n = len(p1_scores)
        avg_p1 = sum(p1_scores) / max(n, 1)
        avg_p5 = sum(p5_scores) / max(n, 1)

        logger.info(
            f"[CodeSearchEval] Done. Retrieval successes={retrieval_successes}, "
            f"failures={retrieval_failures}. "
            f"Precision@1={avg_p1:.4f}  Precision@5={avg_p5:.4f}"
        )

        return {
            "precision_at_1": round(avg_p1, 4),
            "precision_at_5": round(avg_p5, 4),
            "num_queries": n,
            "retrieval_successes": retrieval_successes,
            "retrieval_failures": retrieval_failures,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "per_query_results": per_query,
        }


def _print_results(results: dict) -> None:
    p1 = results["precision_at_1"]
    p5 = results["precision_at_5"]
    n = results["num_queries"]
    succ = results.get("retrieval_successes", n)
    fail = results.get("retrieval_failures", 0)

    try:
        from tabulate import tabulate

        # Summary table
        rows = [
            ["Precision@1 (top result relevant)", f"{p1:.4f}", f"{p1*100:.1f}%"],
            ["Precision@5 (avg over top 5)",       f"{p5:.4f}", f"{p5*100:.1f}%"],
            ["Queries evaluated",                  n,           ""],
            ["Retrieval successes",                succ,        ""],
            ["Retrieval failures",                 fail,        ""],
        ]
        print("\n" + tabulate(rows, headers=["Metric", "Score", "Rate"], tablefmt="simple"))

        # Per-query sample (top 10 only)
        sample_rows = [
            [
                r["query"][:45],
                r["top_result_name"][:30],
                f"{r['p_at_1']:.0f}/{r['p_at_5']:.2f}",
                r.get("error", "")[:30],
            ]
            for r in results["per_query_results"][:10]
        ]
        print("\nSample results (first 10 queries):")
        print(tabulate(sample_rows, headers=["Query", "Top Result", "P@1/P@5", "Error"], tablefmt="simple"))

    except ImportError:
        print("\n" + "=" * 60)
        print("  CodeSearchEval Results")
        print("=" * 60)
        print(f"  Precision@1 : {p1:.4f}  ({p1*100:.1f}%)")
        print(f"  Precision@5 : {p5:.4f}  ({p5*100:.1f}%)")
        print(f"  Queries     : {n}")
        print(f"  Successes   : {succ}  |  Failures: {fail}")
        print("=" * 60)

        # Print all results so user can see what's happening
        print("\nAll query results:")
        for r in results["per_query_results"]:
            mark = "✓" if r["p_at_1"] == 1.0 else "✗"
            err = r.get("error", "")
            err_str = f"  ERR={err[:50]}" if err else ""
            print(f"  {mark} P@1={r['p_at_1']:.0f} P@5={r['p_at_5']:.2f}  "
                  f"'{r['query'][:40]}'  →  '{r['top_result_name'][:30]}'{err_str}")


def _build_fallback_retriever():
    """Build an EmbeddingFallbackRetriever (no BM25 required)."""
    import torch
    from core.model.function_encoder import FunctionEncoder
    from core.model.dataset import Vocabulary
    from core.retrieval.qdrant_store import AtlasQdrantStore

    checkpoint_path = _BACKEND_DIR / "training" / "checkpoints" / "best_model.pt"
    vocab_path      = _BACKEND_DIR / "training" / "data" / "vocab.json"

    if not vocab_path.exists():
        raise FileNotFoundError(f"Vocabulary not found: {vocab_path}")
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"Model checkpoint not found: {checkpoint_path}")

    vocab = Vocabulary.from_file(str(vocab_path))
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    encoder = FunctionEncoder(vocab_size=vocab.size)
    ckpt = torch.load(str(checkpoint_path), map_location=device)
    state_dict = ckpt.get("model_state_dict", ckpt)
    encoder.load_state_dict(state_dict)
    encoder.to(device)
    encoder.eval()
    logger.info(f"Encoder loaded (vocab={vocab.size}, device={device})")

    qdrant = AtlasQdrantStore()
    logger.info("Qdrant connection established (embedding-only mode).")

    return EmbeddingFallbackRetriever(encoder=encoder, qdrant=qdrant, vocab=vocab)


async def main_async(args: argparse.Namespace) -> None:
    if args.use_embedding_fallback:
        logger.info("Using EmbeddingFallbackRetriever (no BM25 / full retriever required).")
        try:
            retriever = _build_fallback_retriever()
        except Exception as exc:
            logger.error(f"Failed to build fallback retriever: {exc}")
            logger.error(traceback.format_exc())
            sys.exit(1)
    else:
        logger.info("Using full AgenticRetriever (Qdrant + BM25 required).")
        try:
            from core.retrieval.retriever_factory import get_retriever
            retriever = get_retriever()
        except FileNotFoundError as exc:
            logger.error(
                f"Retriever setup failed — missing file: {exc}\n"
                "TIP: Run with --use_embedding_fallback if BM25 index is not built yet.\n"
                "TIP: Make sure Qdrant is running (docker run qdrant/qdrant) and the repo "
                "has been indexed (python training/index_repo.py)."
            )
            sys.exit(1)
        except ConnectionError as exc:
            logger.error(
                f"Cannot connect to Qdrant: {exc}\n"
                "TIP: Start Qdrant with: docker run -p 6333:6333 qdrant/qdrant\n"
                "TIP: Or run with --use_embedding_fallback"
            )
            sys.exit(1)
        except Exception as exc:
            logger.error(f"Retriever setup failed unexpectedly: {exc}")
            logger.error(traceback.format_exc())
            sys.exit(1)

    evaluator = CodeSearchEvaluator(retriever)

    logger.info(f"Running {len(BEHAVIORAL_QUERIES)} behavioral queries …")
    results = await evaluator.evaluate(BEHAVIORAL_QUERIES)

    _print_results(results)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Results saved to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "CodeSearchEval: measure behavioral precision of Atlas search "
            "using 50 handcrafted natural-language queries."
        )
    )
    parser.add_argument(
        "--output",
        default="eval/results/codesearcheval_results.json",
        help="Output JSON file path.",
    )
    parser.add_argument(
        "--use_embedding_fallback",
        action="store_true",
        default=False,
        help=(
            "Use embedding-only retrieval (no BM25 / full retriever required). "
            "Use this when BM25 index is not available. Qdrant still needs to be running."
        ),
    )
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
