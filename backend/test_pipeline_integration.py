"""
Verify Check #4: pipeline integration writes function_graph.json into session directories.
Run from: backend/
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

SESSION_ID = "0248f28a4f3a"
SESSION_DIR = Path("sessions") / SESSION_ID


async def main() -> None:
    
    from core import session_progress  

    from core.pipeline import run_analysis_pipeline

    print(f"Running pipeline on session {SESSION_ID} …")
    try:
        await run_analysis_pipeline(SESSION_ID, SESSION_DIR)
    except Exception as exc:
        print(f"Pipeline raised: {exc}")
        raise

    fg = SESSION_DIR / "function_graph.json"
    if fg.exists():
        data = json.loads(fg.read_text(encoding="utf-8"))
        stats = data.get("stats", {})
        print("SUCCESS: function_graph.json written")
        print(f"  nodes : {stats.get('total_nodes', '?')}")
        print(f"  edges : {stats.get('total_edges', '?')}")
    else:
        print("FAIL: function_graph.json was NOT created")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
