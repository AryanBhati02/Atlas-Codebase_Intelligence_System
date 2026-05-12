import json
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger("codebase-intel.cache")

@lru_cache(maxsize=16)
def _load_json_cached(path_str: str, mtime: float) -> dict | list:
    return json.loads(Path(path_str).read_text(encoding="utf-8"))

def load_parsed(session_dir: Path) -> list[dict]:
    path = session_dir / "parsed.json"
    if not path.exists():
        return []
    try:
        mtime = path.stat().st_mtime
        result = _load_json_cached(str(path), mtime)
        return result if isinstance(result, list) else []
    except Exception as e:
        logger.warning(f"Failed to load parsed.json: {e}")
        return []

def load_graph(session_dir: Path) -> dict:
    path = session_dir / "graph.json"
    if not path.exists():
        return {"nodes": [], "edges": []}
    try:
        mtime = path.stat().st_mtime
        result = _load_json_cached(str(path), mtime)
        return result if isinstance(result, dict) else {"nodes": [], "edges": []}
    except Exception as e:
        logger.warning(f"Failed to load graph.json: {e}")
        return {"nodes": [], "edges": []}

def load_dead_code(session_dir: Path) -> dict:
    path = session_dir / "dead_code.json"
    if not path.exists():
        return {"dead_files": [], "dead_functions": [], "dead_exports": [], "summary": {}}
    try:
        mtime = path.stat().st_mtime
        result = _load_json_cached(str(path), mtime)
        return result if isinstance(result, dict) else {"dead_files": [], "dead_functions": [], "dead_exports": [], "summary": {}}
    except Exception as e:
        logger.warning(f"Failed to load dead_code.json: {e}")
        return {"dead_files": [], "dead_functions": [], "dead_exports": [], "summary": {}}
