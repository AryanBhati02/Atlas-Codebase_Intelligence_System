"""Full pipeline status check for Atlas — Batch 1 + Batch 2."""
import json
import pathlib
import sys
import urllib.request
import urllib.error

base = pathlib.Path("training")
root = pathlib.Path(__file__).resolve().parent.parent

def ok(label, detail=""):
    d = " " + detail if detail else ""
    print("  [OK] " + label + d)

def fail(label, detail=""):
    d = " " + detail if detail else ""
    print("  [!!] " + label + d)

def info(label, detail=""):
    d = " " + detail if detail else ""
    print("  [--] " + label + d)

print("=" * 60)
print("  ATLAS FULL PIPELINE STATUS CHECK")
print("=" * 60)

# Batch 1
print("\nBATCH 1 — Prerequisites")
print("-" * 40)

fg = base / "fastapi_graph.json"
if fg.exists():
    data = json.loads(fg.read_text(encoding="utf-8"))
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    files = set(n.get("file_path", "") for n in nodes)
    ok("fastapi_graph.json", "— %d functions, %d edges, %d files" % (len(nodes), len(edges), len(files)))
    sample = [n.get("name", "?") for n in nodes[:5]]
    print("       Sample: " + str(sample))
else:
    fail("fastapi_graph.json", "— MISSING")

# 2. best_model.pt
ckpt = base / "checkpoints" / "best_model.pt"
if ckpt.exists():
    mb = ckpt.stat().st_size / 1024 / 1024
    ok("best_model.pt", "— %.1f MB" % mb)
else:
    fail("best_model.pt", "— MISSING")

# 3. training_log.json
log_path = base / "checkpoints" / "training_log.json"
if log_path.exists():
    tdata = json.loads(log_path.read_text(encoding="utf-8"))
    ok("training_log.json", "— " + json.dumps(tdata)[:200])
else:
    info("training_log.json", "— not found")

# 4. vocab.json
vocab = base / "data" / "vocab.json"
if vocab.exists():
    vdata = json.loads(vocab.read_text(encoding="utf-8"))
    if isinstance(vdata, dict):
        sz = len(vdata.get("token_to_id", vdata))
    else:
        sz = len(vdata)
    ok("vocab.json", "— %d tokens" % sz)
else:
    fail("vocab.json", "— MISSING")

# 5. call_graph.json
cg = base / "data" / "call_graph.json"
if cg.exists():
    cgdata = json.loads(cg.read_text(encoding="utf-8"))
    cn = len(cgdata.get("nodes", []))
    ce = len(cgdata.get("edges", []))
    ok("call_graph.json", "— %d nodes, %d edges" % (cn, ce))
else:
    fail("call_graph.json", "— MISSING")

# 6. bm25_index.pkl
bm = base / "data" / "bm25_index.pkl"
if bm.exists():
    kb = bm.stat().st_size / 1024
    ok("bm25_index.pkl", "— %.0f KB" % kb)
else:
    fail("bm25_index.pkl", "— MISSING")

# BATCH 2
print("\nBATCH 2 — Search & MCP")
print("-" * 40)

for path, label in [
    ("training/index_repo.py", "index_repo.py"),
    ("api/mcp_server.py", "mcp_server.py (5 MCP tools)"),
    ("api/routes/mcp_status.py", "mcp_status.py (/api/mcp/status)"),
]:
    p = pathlib.Path(path)
    if p.exists():
        ok(label, "— %d bytes" % p.stat().st_size)
    else:
        fail(label, "— MISSING")

for cfg in [".claude/mcp.json", ".cursor/mcp.json"]:
    p = root / cfg
    if p.exists():
        ok(cfg)
    else:
        fail(cfg, "— MISSING")

doc = root / "docs" / "MCP_SETUP.md"
if doc.exists():
    ok("docs/MCP_SETUP.md", "— %d bytes" % doc.stat().st_size)
else:
    fail("docs/MCP_SETUP.md", "— MISSING")

# MCP tool count
mcp_src = pathlib.Path("api/mcp_server.py")
if mcp_src.exists():
    src = mcp_src.read_text(encoding="utf-8")
    tools = ["search_codebase", "check_exists", "get_function_context", "get_hot_paths", "get_architecture_rules"]
    found = [t for t in tools if ("async def " + t) in src]
    ok("MCP tools registered: %d/5 — %s" % (len(found), ", ".join(found)))

# Sessions check
sessions_dir = pathlib.Path("sessions")
if sessions_dir.exists():
    session_count = len(list(sessions_dir.iterdir()))
    fg_found = 0
    for sd in list(sessions_dir.iterdir())[:20]:
        if (sd / "function_graph.json").exists():
            fg_found += 1
    ok("Sessions: %d total, %d/20 sampled have function_graph.json" % (session_count, fg_found))

#LIVE SERVICES
print("\nLIVE SERVICES")
print("-" * 40)

# FastAPI health
try:
    with urllib.request.urlopen("http://localhost:8000/api/health", timeout=3) as r:
        hdata = json.loads(r.read())
    ok("FastAPI server", "— " + json.dumps(hdata))
except Exception as exc:
    fail("FastAPI server", "— %s" % exc)

# MCP status endpoint
try:
    with urllib.request.urlopen("http://localhost:8000/api/mcp/status", timeout=3) as r:
        mdata = json.loads(r.read())
    ok("/api/mcp/status response:")
    for k, v in mdata.items():
        print("       %s: %s" % (k, v))
except urllib.error.HTTPError as exc:
    fail("/api/mcp/status", "— HTTP %d (server needs restart to pick up new route)" % exc.code)
except Exception as exc:
    fail("/api/mcp/status", "— %s" % exc)

# Qdrant direct
try:
    with urllib.request.urlopen("http://localhost:6333/collections", timeout=3) as r:
        qdata = json.loads(r.read())
    colls = [c["name"] for c in qdata.get("result", {}).get("collections", [])]
    ok("Qdrant", "— collections: %s" % colls)
except Exception as exc:
    fail("Qdrant at localhost:6333", "— %s" % exc)

# SUMMARY
print()
print("=" * 60)
print("  NEXT STEPS")
print("=" * 60)
print("  1. Restart FastAPI to activate /api/mcp/status")
print("  2. In project root: claude   (auto-connects MCP)")
print("  3. Test: 'Search Atlas for authentication functions'")
print("  4. Record 60-second demo video")
print("=" * 60)
