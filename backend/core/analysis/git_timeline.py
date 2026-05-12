import json
import logging
import subprocess
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("codebase-intel.git")

def extract_timeline(repo_dir: Path) -> list[dict]:
    if not (repo_dir / ".git").exists():
        return []

    try:
        result = subprocess.run(
            [
                "git", "log",
                "--pretty=format:%H|%aI|%an|%s",
                "--name-status",
                "-50",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(repo_dir),
        )
        if result.returncode != 0:
            return []
    except Exception as e:
        logger.warning(f"Git log failed for {repo_dir}: {e}")
        return []

    stdout = result.stdout.strip()
    if not stdout:
        return []

    lines = stdout.split("\n")
    commits: list[dict] = []
    current: dict | None = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if "|" in line and len(line.split("|")) >= 4:
            parts = line.split("|", 3)
            if len(parts[0]) == 40:  
                if current:
                    commits.append(current)
                current = {
                    "hash": parts[0],
                    "short_hash": parts[0][:7],
                    "timestamp": parts[1],
                    "author": parts[2],
                    "message": parts[3],
                    "files_changed": [],
                }
                continue

        if current and "\t" in line:
            parts = line.split("\t", 1)
            if len(parts) == 2 and parts[0] in ("A", "M", "D", "R", "C"):
                current["files_changed"].append({
                    "path": parts[1],
                    "status": parts[0],
                })

    if current:
        commits.append(current)

    return commits

def get_commit_diff(repo_dir: Path, commit_hash: str) -> dict:
    if not (repo_dir / ".git").exists():
        return {"hash": commit_hash, "files": []}

    try:
        
        info_result = subprocess.run(
            ["git", "log", "-1", "--pretty=format:%s|%an|%aI", commit_hash],
            capture_output=True, text=True, timeout=10, cwd=str(repo_dir),
        )
        message, author, timestamp = "", "", ""
        if info_result.returncode == 0 and info_result.stdout:
            parts = info_result.stdout.strip().split("|", 2)
            message = parts[0] if len(parts) > 0 else ""
            author = parts[1] if len(parts) > 1 else ""
            timestamp = parts[2] if len(parts) > 2 else ""

        stat_result = subprocess.run(
            ["git", "diff", "--numstat", f"{commit_hash}~1", commit_hash],
            capture_output=True, text=True, timeout=10, cwd=str(repo_dir),
        )
        
        files = []
        if stat_result.returncode == 0:
            for line in stat_result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) >= 3:
                    adds = int(parts[0]) if parts[0] != "-" else 0
                    dels = int(parts[1]) if parts[1] != "-" else 0
                    files.append({
                        "path": parts[2],
                        "additions": adds,
                        "deletions": dels,
                        "status": "M" if adds > 0 and dels > 0 else "A" if adds > 0 else "D",
                    })

        if not files:
            ns_result = subprocess.run(
                ["git", "diff", "--name-status", f"{commit_hash}~1", commit_hash],
                capture_output=True, text=True, timeout=10, cwd=str(repo_dir),
            )
            if ns_result.returncode == 0:
                for line in ns_result.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    parts = line.split("\t", 1)
                    if len(parts) == 2:
                        files.append({
                            "path": parts[1],
                            "status": parts[0],
                            "additions": 0,
                            "deletions": 0,
                        })

        return {
            "hash": commit_hash,
            "short_hash": commit_hash[:7],
            "message": message,
            "author": author,
            "timestamp": timestamp,
            "files": files,
        }
    except Exception:
        return {"hash": commit_hash, "files": []}

def parse_coverage(session_dir: Path) -> dict:
    coverage_map: dict[str, float] = {}
    
    for candidate in ["coverage.json", "coverage-summary.json", ".coverage.json"]:
        coverage_path = session_dir / "repo" / candidate
        if coverage_path.exists():
            try:
                data = json.loads(coverage_path.read_text(encoding="utf-8"))
                
                if "total" in data and isinstance(data.get("total"), dict):
                    for file_path, stats in data.items():
                        if file_path == "total":
                            continue
                        if isinstance(stats, dict):
                            lines = stats.get("lines", {})
                            pct = lines.get("pct", 0) if isinstance(lines, dict) else 0
                            coverage_map[file_path] = round(pct, 1)
                
                elif all(isinstance(v, (int, float)) for v in data.values()):
                    coverage_map = {k: round(v, 1) for k, v in data.items()}
            except Exception:
                pass
    
    lcov_path = session_dir / "repo" / "coverage" / "lcov.info"
    if not coverage_map and lcov_path.exists():
        try:
            content = lcov_path.read_text(encoding="utf-8")
            current_file = None
            lines_hit = 0
            lines_total = 0
            for line in content.split("\n"):
                if line.startswith("SF:"):
                    current_file = line[3:].strip()
                    lines_hit = 0
                    lines_total = 0
                elif line.startswith("LH:"):
                    lines_hit = int(line[3:].strip())
                elif line.startswith("LF:"):
                    lines_total = int(line[3:].strip())
                elif line.startswith("end_of_record") and current_file:
                    pct = (lines_hit / lines_total * 100) if lines_total > 0 else 0
                    coverage_map[current_file] = round(pct, 1)
                    current_file = None
        except Exception:
            pass

    has_coverage = len(coverage_map) > 0
    result = {
        "coverage": coverage_map,
        "has_coverage": has_coverage,
        "files_covered": len(coverage_map),
        "avg_coverage": round(
            sum(coverage_map.values()) / max(len(coverage_map), 1), 1
        ) if has_coverage else 0,
    }
    
    if not has_coverage:
        result["note"] = "Coverage data must be pre-generated by running your test suite (e.g., producing lcov.info or coverage.json). Codebase Intelligence does not run your code."
        
    return result

def get_cached_timeline(session_dir: Path) -> list[dict] | None:
    cache_path = session_dir / "git_timeline.json"
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None

def cache_timeline(session_dir: Path, timeline: list[dict]) -> None:
    cache_path = session_dir / "git_timeline.json"
    cache_path.write_text(json.dumps(timeline, default=str), encoding="utf-8")
