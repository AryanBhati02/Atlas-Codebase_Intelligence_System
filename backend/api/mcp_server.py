"""
Atlas MCP Server — Behavioral Code Intelligence for Claude Code & Cursor.

Exposes 5 tools over the Model Context Protocol (stdio transport):
  1. search_codebase        — semantic / behavioral similarity search
  2. check_exists           — duplicate-detection before writing new code
  3. get_function_context   — callers, callees, complexity for one function
  4. get_hot_paths          — highest-impact (fan-in + complexity) functions
  5. get_architecture_rules — module dependency map & circular-dep detection

Usage (standalone verification):
    cd backend
    PYTHONPATH=. python api/mcp_server.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from mcp.server.fastmcp import FastMCP  # noqa: E402  (import after path fix)

logger = logging.getLogger("atlas.mcp")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)

mcp = FastMCP("Atlas — Behavioral Code Intelligence")

_retriever = None

def _get_retriever():
    """Return the AgenticRetriever singleton, loading it on first call."""
    global _retriever
    if _retriever is None:
        logger.info("Initialising AgenticRetriever (first tool call) …")
        from core.retrieval.retriever_factory import get_retriever  # noqa: PLC0415
        _retriever = get_retriever()
        logger.info("AgenticRetriever ready.")
    return _retriever


def _safe_retriever():
    """Like _get_retriever() but returns (retriever, None) or (None, error_str)."""
    try:
        return _get_retriever(), None
    except FileNotFoundError as exc:
        return None, f"Index not found: {exc}. Run index_repo.py first."
    except ConnectionError as exc:
        return None, f"Qdrant connection failed: {exc}. Is Qdrant running on localhost:6333?"
    except Exception as exc:
        return None, f"Failed to initialise retriever: {exc}"

@mcp.tool()
async def search_codebase(query: str, top_k: int = 5, language: str | None = None) -> str:
    """Search the indexed codebase by BEHAVIORAL similarity.

    Finds functions that DO what your query describes, not just text matches.
    Cross-language: a Python sort and a JavaScript sort both match "sort an array".

    Use this BEFORE writing any new code to find existing implementations.
    Results are sorted by behavioral similarity (0.0-1.0), where 1.0 is identical
    behavior.

    Args:
        query: Natural language description of what you are looking for
               (e.g. "parse JSON configuration", "handle authentication errors").
        top_k: Number of results to return (default 5, max 20).
        language: Optional filter — "python", "javascript", or "typescript".

    Returns:
        JSON list of matching functions with behavioral similarity scores.
    """
    retriever, err = _safe_retriever()
    if err:
        return json.dumps({"error": err})

    top_k = max(1, min(top_k, 20))  # clamp to [1, 20]

    try:
        results = await retriever.retrieve(query, top_k=top_k, language=language)
    except Exception as exc:
        logger.exception("search_codebase failed")
        return json.dumps({"error": f"Retrieval failed: {exc}"})

    return json.dumps(
        [
            {
                "name": r.name,
                "file": r.file_path,
                "line": r.line_start,
                "behavioral_similarity": r.behavioral_score,
                "textual_score": r.textual_score,
                "final_score": r.final_score,
                "docstring": (r.docstring or "")[:200],
                "complexity": r.complexity,
                "is_hot_path": r.is_hot_path,
                "language": r.language,
            }
            for r in results
        ],
        indent=2,
    )

@mcp.tool()
async def check_exists(description: str) -> str:
    """Check if functionality ALREADY EXISTS before writing new code.

    This is the most important tool. Call it BEFORE implementing any new function.

    Interpretation of scores:
    - Above 0.85 : This functionality EXISTS. Extend the existing function,
                   do NOT duplicate.
    - 0.60 – 0.85: SIMILAR functionality exists. Review the match before
                   writing new code.
    - Below 0.60 : No close match found. Safe to write new code.

    Args:
        description: What the new function would do
                     (e.g. "validate email addresses",
                      "retry failed HTTP requests with exponential backoff").

    Returns:
        JSON with top match, similarity score, and a plain-English recommendation.
    """
    retriever, err = _safe_retriever()
    if err:
        return json.dumps({"error": err})

    try:
        results = await retriever.retrieve(description, top_k=3)
    except Exception as exc:
        logger.exception("check_exists retrieval failed")
        return json.dumps({"error": f"Retrieval failed: {exc}"})

    if not results:
        return json.dumps(
            {
                "exists": False,
                "similar": False,
                "recommendation": "No matches found. Safe to write new code.",
                "matches": [],
            }
        )

    top = results[0]

    if top.behavioral_score >= 0.85:
        recommendation = (
            f"DUPLICATE RISK: '{top.name}' at {top.file_path}:{top.line_start} "
            f"already does this (similarity: {top.behavioral_score:.2f}). "
            f"Extend it instead of writing new code."
        )
    elif top.behavioral_score >= 0.60:
        recommendation = (
            f"SIMILAR: '{top.name}' at {top.file_path}:{top.line_start} "
            f"does something similar (similarity: {top.behavioral_score:.2f}). "
            f"Review it before writing new code."
        )
    else:
        recommendation = "No close behavioral match found. Safe to write new code."

    return json.dumps(
        {
            "exists": top.behavioral_score >= 0.85,
            "similar": top.behavioral_score >= 0.60,
            "recommendation": recommendation,
            "top_match": {
                "name": top.name,
                "file": top.file_path,
                "line": top.line_start,
                "similarity": top.behavioral_score,
                "docstring": (top.docstring or "")[:200],
            },
            "other_matches": [
                {
                    "name": r.name,
                    "file": r.file_path,
                    "similarity": r.behavioral_score,
                }
                for r in results[1:]
            ],
        },
        indent=2,
    )

@mcp.tool()
async def get_function_context(function_name: str) -> str:
    """Get the full behavioral context for a specific function.

    Returns who calls this function (callers), what it calls (callees),
    its complexity score, whether it is on a hot path, and its docstring.

    Call this BEFORE modifying an existing function to understand its impact.

    Args:
        function_name: The function name to look up.
                       Can be an exact name ("add_api_route") or a qualified
                       name ("APIRouter.include_router"). Substring matching
                       is used as a fallback.

    Returns:
        JSON with callers, callees, complexity, fan-in/fan-out, and an impact
        note indicating how many other functions depend on this one.
    """
    retriever, err = _safe_retriever()
    if err:
        return json.dumps({"error": err})

    graph = retriever.graph

    if graph.number_of_nodes() == 0:
        return json.dumps(
            {
                "error": (
                    "Call graph is empty. Run index_repo.py to generate it, "
                    "then restart the MCP server."
                )
            }
        )

    matching_nodes: list[tuple[str, dict]] = []
    for node_id in graph.nodes():
        node_data = graph.nodes[node_id]
        name = node_data.get("name", "")
        if name == function_name or node_id == function_name:
            matching_nodes.insert(0, (node_id, node_data))  # exact — put first
        elif function_name.lower() in node_id.lower() or function_name.lower() in name.lower():
            matching_nodes.append((node_id, node_data))

    if not matching_nodes:
        return json.dumps(
            {
                "error": (
                    f"Function '{function_name}' not found in the indexed codebase. "
                    f"Use search_codebase() to find the correct name."
                ),
                "hint": "The graph contains functions from the last indexed repository.",
            }
        )

    node_id, node_data = matching_nodes[0]

    callers = [
        {
            "name": graph.nodes[n].get("name", n),
            "file": graph.nodes[n].get("file_path", ""),
        }
        for n in graph.predecessors(node_id)
    ]
    callees = [
        {
            "name": graph.nodes[n].get("name", n),
            "file": graph.nodes[n].get("file_path", ""),
        }
        for n in graph.successors(node_id)
    ]

    fan_in = len(callers)
    impact = "HIGH IMPACT — modify with care and add tests first." if fan_in > 5 else "Moderate impact."

    ambiguous = []
    if len(matching_nodes) > 1:
        for alt_id, alt_data in matching_nodes[1:5]:
            ambiguous.append(
                {
                    "node_id": alt_id,
                    "name": alt_data.get("name", alt_id),
                    "file": alt_data.get("file_path", ""),
                }
            )

    result = {
        "function": function_name,
        "matched_node": node_id,
        "file": node_data.get("file_path", ""),
        "line_start": node_data.get("line_start", 0),
        "line_end": node_data.get("line_end", 0),
        "complexity": node_data.get("complexity", 0),
        "is_hot_path": node_data.get("is_hot_path", False),
        "docstring": node_data.get("docstring", ""),
        "callers": callers,
        "callees": callees,
        "fan_in": fan_in,
        "fan_out": len(callees),
        "impact_note": f"Called by {fan_in} function(s). {impact}",
    }
    if ambiguous:
        result["ambiguous_matches"] = ambiguous
        result["note"] = "Multiple nodes matched; showing the best match above."

    return json.dumps(result, indent=2)

@mcp.tool()
async def get_hot_paths(top_k: int = 10) -> str:
    """Return the most critical functions in the codebase (hot paths).

    These are functions with the highest fan-in (most callers) and highest
    coupling scores. Bugs in these functions have the widest blast radius.

    MODIFY THESE WITH EXTRA CARE. Add or review tests before changing them.

    Args:
        top_k: Number of hot-path functions to return (default 10, max 50).

    Returns:
        JSON list of critical functions sorted by impact score (descending).
        Impact score = fan_in × 2 + complexity + fan_out × 0.5
    """
    retriever, err = _safe_retriever()
    if err:
        return json.dumps({"error": err})

    graph = retriever.graph

    if graph.number_of_nodes() == 0:
        return json.dumps(
            {
                "warning": "Call graph is empty. No hot-path data available.",
                "hot_paths": [],
            }
        )

    top_k = max(1, min(top_k, 50))

    scored: list[dict] = []
    for node_id in graph.nodes():
        node_data = graph.nodes[node_id]
        fan_in = graph.in_degree(node_id)
        fan_out = graph.out_degree(node_id)
        complexity = int(node_data.get("complexity", 0))
 
        impact = fan_in * 2 + complexity + fan_out * 0.5
        scored.append(
            {
                "name": node_data.get("name", node_id),
                "file": node_data.get("file_path", ""),
                "line": node_data.get("line_start", 0),
                "fan_in": fan_in,
                "fan_out": fan_out,
                "complexity": complexity,
                "impact_score": round(impact, 2),
                "warning": (
                    "HIGH IMPACT — test thoroughly before modifying"
                    if fan_in > 5
                    else "Moderate impact"
                ),
            }
        )

    scored.sort(key=lambda x: x["impact_score"], reverse=True)
    return json.dumps(scored[:top_k], indent=2)

@mcp.tool()
async def get_architecture_rules() -> str:
    """Analyse the current architectural structure and detect potential violations.

    Shows the module dependency structure, identifies circular dependencies,
    and flags unusual coupling patterns.

    Call this before making structural changes (moving files, adding new modules,
    changing import patterns).

    Returns:
        JSON with:
        - modules        : dict of module → {depends_on, dependency_count}
        - circular_dependencies : list of [mod_a, mod_b] pairs
        - total_modules  : int
        - cross_module_edges : int
        - health         : "HEALTHY" or a warning string
        - recommendation : actionable advice
    """
    retriever, err = _safe_retriever()
    if err:
        return json.dumps({"error": err})

    graph = retriever.graph

    if graph.number_of_nodes() == 0:
        return json.dumps(
            {
                "warning": "Call graph is empty. No architecture data available.",
                "modules": {},
                "circular_dependencies": [],
                "health": "UNKNOWN",
            }
        )

    def _module_of(file_path: str) -> str:
        """Return the top-two path components as the logical module label."""
        if not file_path:
            return "<unknown>"
        parts = file_path.replace("\\", "/").split("/")
        return "/".join(parts[:2]) if len(parts) >= 2 else file_path

    module_deps: dict[str, set[str]] = {}

    for node_id in graph.nodes():
        node_data = graph.nodes[node_id]
        src_mod = _module_of(node_data.get("file_path", ""))
        module_deps.setdefault(src_mod, set())

        for successor in graph.successors(node_id):
            tgt_data = graph.nodes[successor]
            tgt_mod = _module_of(tgt_data.get("file_path", ""))
            if tgt_mod != src_mod:
                module_deps[src_mod].add(tgt_mod)

    seen_pairs: set[tuple[str, str]] = set()
    circular: list[list[str]] = []
    for mod_a, deps_a in module_deps.items():
        for mod_b in deps_a:
            if mod_b in module_deps and mod_a in module_deps.get(mod_b, set()):
                pair = tuple(sorted([mod_a, mod_b]))
                if pair not in seen_pairs:
                    seen_pairs.add(pair)  # type: ignore[arg-type]
                    circular.append(list(pair))

    cross_module_edges = sum(len(deps) for deps in module_deps.values())
    health = (
        "HEALTHY"
        if not circular
        else f"WARNING: {len(circular)} circular dependency pair(s) detected"
    )
    recommendation = (
        "No circular dependencies detected — clean layered architecture."
        if not circular
        else (
            "Consider breaking circular dependencies by extracting shared "
            "interfaces or introducing an abstraction layer between the "
            "affected modules."
        )
    )

    return json.dumps(
        {
            "modules": {
                mod: {
                    "depends_on": sorted(list(deps)),
                    "dependency_count": len(deps),
                }
                for mod, deps in sorted(module_deps.items())
            },
            "circular_dependencies": circular,
            "total_modules": len(module_deps),
            "cross_module_edges": cross_module_edges,
            "health": health,
            "recommendation": recommendation,
        },
        indent=2,
    )

if __name__ == "__main__":
    logger.info("Starting Atlas MCP server (stdio transport) …")
    mcp.run(transport="stdio")
