"""
Atlas live-service tests.
Run from: cd backend && .venv/Scripts/python run_tests.py
"""
import json
import pathlib
import sys
import urllib.request
import urllib.error

root = pathlib.Path(__file__).resolve().parent

def get(url, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())

def post(url, payload, timeout=10):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

print("=" * 60)
print("  ATLAS LIVE SERVICE TESTS")
print("=" * 60)

#1. Qdrant collection stats
print("\n[TEST 1] Qdrant — atlas_functions collection")
try:
    info = get("http://localhost:6333/collections/atlas_functions")
    result = info.get("result", {})
    pts = result.get("points_count", result.get("vectors_count", "?"))
    status = result.get("status", "?")
    print("  status:         %s" % status)
    print("  indexed points: %s" % pts)
    if isinstance(pts, int) and pts >= 100:
        print("  [PASS] Qdrant has %d indexed functions" % pts)
    elif isinstance(pts, int):
        print("  [WARN] Only %d points — run index_repo.py to populate" % pts)
    else:
        print("  [INFO] Point count field not found in response")
    print("  Full result: %s" % json.dumps(result)[:300])
except Exception as exc:
    print("  [FAIL] %s" % exc)
    print("  >>> Is Qdrant running? docker run -p 6333:6333 qdrant/qdrant")

#2. Search API — authentication middleware
print("\n[TEST 2] POST /api/search — 'authentication middleware'")
try:
    resp = post("http://localhost:8000/api/search",
                {"query": "authentication middleware", "top_k": 5})
    results = resp if isinstance(resp, list) else resp.get("results", resp.get("data", []))
    print("  returned %d results" % len(results))
    for i, r in enumerate(results[:3]):
        name  = r.get("name", r.get("function_name", "?"))
        score = r.get("behavioral_similarity", r.get("final_score", r.get("score", "?")))
        fpath = r.get("file", r.get("file_path", "?"))
        print("  %d. %s  (score: %s)  %s" % (i + 1, name, score, fpath))
    if results:
        print("  [PASS] Search returned results")
    else:
        print("  [WARN] 0 results — index may be empty")
except urllib.error.HTTPError as exc:
    body = exc.read().decode()[:300]
    print("  [FAIL] HTTP %d: %s" % (exc.code, body))
except Exception as exc:
    print("  [FAIL] %s" % exc)

#3. Search API — validate request parameters
print("\n[TEST 3] POST /api/search — 'validate request parameters'")
try:
    resp = post("http://localhost:8000/api/search",
                {"query": "validate request parameters", "top_k": 5})
    results = resp if isinstance(resp, list) else resp.get("results", resp.get("data", []))
    print("  returned %d results" % len(results))
    for i, r in enumerate(results[:3]):
        name  = r.get("name", r.get("function_name", "?"))
        score = r.get("behavioral_similarity", r.get("final_score", r.get("score", "?")))
        print("  %d. %s  (score: %s)" % (i + 1, name, score))
    if results:
        print("  [PASS]")
    else:
        print("  [WARN] 0 results")
except urllib.error.HTTPError as exc:
    body = exc.read().decode()[:300]
    print("  [FAIL] HTTP %d: %s" % (exc.code, body))
except Exception as exc:
    print("  [FAIL] %s" % exc)

#4. Search health endpoint
print("\n[TEST 4] GET /api/search/health")
try:
    resp = get("http://localhost:8000/api/search/health")
    print("  %s" % json.dumps(resp, indent=2)[:400])
    print("  [PASS]")
except urllib.error.HTTPError as exc:
    print("  [FAIL] HTTP %d" % exc.code)
except Exception as exc:
    print("  [FAIL] %s" % exc)

#5. MCP status endpoint
print("\n[TEST 5] GET /api/mcp/status")
try:
    resp = get("http://localhost:8000/api/mcp/status")
    for k, v in resp.items():
        print("  %-22s: %s" % (k, v))
    connected = resp.get("connected", False)
    indexed   = resp.get("indexed_functions", 0)
    print()
    if connected and indexed >= 100:
        print("  [PASS] Qdrant connected, %d functions indexed" % indexed)
    elif connected:
        print("  [WARN] Connected but only %d functions indexed" % indexed)
    else:
        print("  [WARN] Qdrant not connected — check Qdrant is running")
except urllib.error.HTTPError as exc:
    if exc.code == 404:
        print("  [FAIL] 404 — FastAPI server needs restart to pick up new route")
        print("  >>> Stop uvicorn then: cd backend && uvicorn main:app --port 8000 --reload")
    else:
        print("  [FAIL] HTTP %d" % exc.code)
except Exception as exc:
    print("  [FAIL] %s" % exc)

#6. MCP server standalone boot
print("\n[TEST 6] MCP server standalone boot")
import subprocess, os, time

env = dict(os.environ)
env["PYTHONPATH"] = str(root)
proc = subprocess.Popen(
    [sys.executable, str(root / "api" / "mcp_server.py")],
    stderr=subprocess.PIPE,
    stdout=subprocess.DEVNULL,
    env=env,
    text=True,
)
time.sleep(2)
proc.terminate()
try:
    _, stderr = proc.communicate(timeout=3)
except Exception:
    proc.kill()
    stderr = ""

if "Starting Atlas MCP server" in stderr:
    print("  [PASS] MCP server started cleanly")
    print("  Log: %s" % stderr.strip()[:200])
elif stderr.strip():
    print("  [INFO] stderr output:")
    print("  " + "\n  ".join(stderr.strip().splitlines()[:5]))
else:
    print("  [WARN] No stderr output captured")

#Summary
print()
print("=" * 60)
print("  TRAINING SUMMARY (from training_log.json)")
print("=" * 60)
log_path = root / "training" / "checkpoints" / "training_log.json"
if log_path.exists():
    tlog = json.loads(log_path.read_text())
    cfg = tlog.get("config", {})
    print("  epochs trained : %s"  % cfg.get("epochs", "?"))
    print("  batch size     : %s"  % cfg.get("batch_size", "?"))
    print("  learning rate  : %s"  % cfg.get("lr", "?"))
    print("  static_only    : %s"  % cfg.get("static_only", False))
    print("  best loss      : %.4f" % tlog.get("best_loss", 0))
    print("  training time  : %.0f seconds (%.1f min)" % (
        tlog.get("total_time_seconds", 0),
        tlog.get("total_time_seconds", 0) / 60))
    losses = tlog.get("epoch_losses", [])
    print("  loss curve     :", " -> ".join("%.3f" % e["loss"] for e in losses))
    print()
    print("  NOTE: Only 5 epochs trained. For best MRR@10:")
    print("  Run: python training/train_gatv2.py --epochs 100 --batch_size 16")
else:
    print("  training_log.json not found")

print()
print("=" * 60)
print("  ALL TESTS COMPLETE")
print("=" * 60)
