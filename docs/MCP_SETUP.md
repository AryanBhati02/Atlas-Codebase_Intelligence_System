# Atlas MCP Server — Setup Guide

## What is this?

Atlas exposes its behavioral code intelligence as an **MCP (Model Context Protocol)** server.
When Claude Code or Cursor connects to this server it can:

- 🔍 **Search** your codebase by *what code does*, not just text matching
- 🛑 **Check** if functionality already exists before writing duplicates
- 🗺️ **Understand** function context (callers, callees, complexity)
- 🔥 **Find** critical hot-path functions that need careful modification
- 🏗️ **Detect** architectural violations and circular dependencies

---

## Prerequisites

| Dependency | Version | Install |
|---|---|---|
| Python | ≥ 3.10 | — |
| mcp | latest | `pip install mcp` |
| Qdrant running | any | Docker or binary |
| Index built | — | `cd backend && PYTHONPATH=. python training/index_repo.py <path>` |

---

## Setup for Claude Code

1. The `.claude/mcp.json` file is already in the project root — nothing extra needed.
2. Open Claude Code in the project directory:
   ```
   claude
   ```
3. Atlas MCP server starts automatically on every session.
4. Verify the connection — type in Claude Code:
   ```
   Search Atlas for authentication functions
   ```

---

## Setup for Cursor

1. The `.cursor/mcp.json` file is already present.
2. Open the project folder in Cursor.
3. Go to **Settings → MCP** — "Atlas — Behavioral Code Intelligence" should appear as a connected server.
4. If it doesn't appear, restart Cursor or reload the window (`Ctrl+Shift+P → Reload Window`).

---

## Manual standalone verification

Start the MCP server outside of Claude Code to confirm it imports cleanly:

```bash
cd backend
PYTHONPATH=. python api/mcp_server.py
```

You should see log output on stderr like:
```
[INFO] atlas.mcp: Starting Atlas MCP server (stdio transport) …
```
Press `Ctrl+C` to stop.

---

## Available Tools

### 1. `search_codebase`

Search by behavioral similarity — finds functions that *do* what you describe.

**Signature:**
```python
search_codebase(query: str, top_k: int = 5, language: str | None = None) -> str
```

**Example usage in Claude Code:**
```
Search Atlas for "retry HTTP requests with exponential backoff"
```

**Example result:**
```json
[
  {
    "name": "_retry_request",
    "file": "utils/http.py",
    "line": 42,
    "behavioral_similarity": 0.91,
    "textual_score": 0.73,
    "final_score": 0.86,
    "docstring": "Retry an HTTP request up to max_retries times …",
    "complexity": 4,
    "is_hot_path": false,
    "language": "python"
  }
]
```

---

### 2. `check_exists`

Duplicate-detection gate — call **before** implementing any new function.

**Signature:**
```python
check_exists(description: str) -> str
```

**Score thresholds:**
| Score | Meaning |
|---|---|
| ≥ 0.85 | EXISTS — extend, do not duplicate |
| 0.60 – 0.85 | SIMILAR — review before writing |
| < 0.60 | SAFE — new code is fine |

**Example usage:**
```
Check if "validate email address" already exists in Atlas
```

---

### 3. `get_function_context`

Full call-graph context for one function.

**Signature:**
```python
get_function_context(function_name: str) -> str
```

Returns callers, callees, complexity, fan-in, fan-out, and an impact note.

**Example usage:**
```
Get the context for "get_retriever" using Atlas
```

---

### 4. `get_hot_paths`

Top-N highest-impact functions (fan-in × 2 + complexity + fan-out × 0.5).

**Signature:**
```python
get_hot_paths(top_k: int = 10) -> str
```

**Example usage:**
```
Show me the 10 most critical functions in Atlas
```

---

### 5. `get_architecture_rules`

Module dependency map and circular-dependency detection.

**Signature:**
```python
get_architecture_rules() -> str
```

**Example usage:**
```
Analyse the architecture of this codebase using Atlas
```

---

## HTTP Health Check

The main FastAPI server exposes a status endpoint:

```
GET http://localhost:8000/api/mcp/status
```

Example response:
```json
{
  "connected": true,
  "indexed_functions": 1847,
  "collection": "atlas_functions",
  "tools": ["search_codebase", "check_exists", "get_function_context", "get_hot_paths", "get_architecture_rules"],
  "model_loaded": true,
  "bm25_loaded": true
}
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Index not found` error | Run `PYTHONPATH=. python training/index_repo.py <repo_path>` inside `backend/` |
| `Qdrant connection failed` | Start Qdrant: `docker run -p 6333:6333 qdrant/qdrant` |
| `Module not found` | Make sure you run with `PYTHONPATH=backend` or from inside `backend/` |
| Claude Code doesn't see the server | Restart Claude Code; check `.claude/mcp.json` is in the project root |
| Cursor doesn't see the server | Reload Cursor window; verify `.cursor/mcp.json` is correct |

---

## Demo video

Record a 60-second screen capture demonstrating:
1. Asking Claude Code to search for an existing function
2. `check_exists` catching a near-duplicate before you write it
3. `get_hot_paths` showing the riskiest functions
4. `get_architecture_rules` reporting the module structure

