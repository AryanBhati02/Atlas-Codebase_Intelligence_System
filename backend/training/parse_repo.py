"""
parse_repo.py
-------------
Standalone CLI script to parse a repository (local path or GitHub URL)
into a function-level call graph and save the output as JSON.

Usage examples
--------------
  python training/parse_repo.py --input https://github.com/tiangolo/fastapi
  python training/parse_repo.py --input /path/to/local/repo --output my_graph.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from core.parser.tree_sitter_parser import TreeSitterParser
from core.parser.call_graph_builder import build_call_graph, graph_to_json, graph_to_pyg_data
from core.tracer.fusion_engine import FusionEngine
from core.tracer.git_coedits import GitCoEditExtractor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("atlas.parse_repo")







def _clone_repo(url: str, target_dir: str) -> None:
    """Shallow-clone *url* into *target_dir* using git."""
    logger.info(f"Cloning {url} …")
    result = subprocess.run(
        ["git", "clone", "--depth=1", url, target_dir],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git clone failed (exit {result.returncode}):\n{result.stderr.strip()}"
        )
    logger.info("Clone complete.")


def _fmt_table(rows: list[tuple], headers: tuple, col_widths: tuple) -> str:
    """Format a simple fixed-width table as a string."""
    sep = "  "
    header_line = sep.join(h.ljust(w) for h, w in zip(headers, col_widths))
    divider = sep.join("-" * w for w in col_widths)
    lines = [header_line, divider]
    for row in rows:
        lines.append(sep.join(str(v).ljust(w) for v, w in zip(row, col_widths)))
    return "\n".join(lines)







def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse a repository into a function-level call graph."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="GitHub URL (https://... or git@...) or local filesystem path.",
    )
    parser.add_argument(
        "--output",
        default="parsed_graph.json",
        help="Output JSON path for the call graph (default: parsed_graph.json).",
    )
    args = parser.parse_args()

    input_val: str = args.input
    output_path = Path(args.output)
    pyg_output_path = output_path.with_name(
        output_path.stem + "_pyg" + output_path.suffix
    )

    
    
    
    tmp_dir: str | None = None
    repo_path: str

    is_remote = input_val.startswith("http") or input_val.startswith("git@")
    if is_remote:
        tmp_dir = tempfile.mkdtemp(prefix="atlas_clone_")
        try:
            _clone_repo(input_val, tmp_dir)
        except RuntimeError as exc:
            logger.error(str(exc))
            shutil.rmtree(tmp_dir, ignore_errors=True)
            sys.exit(1)
        repo_path = tmp_dir
    else:
        repo_path = os.path.abspath(input_val)
        if not os.path.isdir(repo_path):
            logger.error(f"Path does not exist or is not a directory: {repo_path}")
            sys.exit(1)

    
    
    
    try:
        ts_parser = TreeSitterParser()
        logger.info(f"Parsing repository: {repo_path}")
        nodes = ts_parser.parse_repository(repo_path)

        if not nodes:
            logger.warning("No function nodes found. Check that tree-sitter language packages are installed.")

        
        unique_files = len({n.file_path for n in nodes})

        
        lang_counts: dict[str, int] = {"python": 0, "javascript": 0, "typescript": 0}
        for n in nodes:
            lang = n.language.lower()
            if lang in lang_counts:
                lang_counts[lang] += 1

        logger.info("Building call graph …")
        graph = build_call_graph(nodes)

        coedit_data = {}
        if (Path(repo_path) / ".git").exists():
            try:
                extractor = GitCoEditExtractor(repo_path)
                coedit_data = extractor.get_function_coedits(nodes)
                logger.info(f"Git co-edit pairs computed: {len(coedit_data)}")
            except Exception as coedit_exc:
                logger.warning(f"Git co-edit extraction failed; continuing with static graph: {coedit_exc}")
        else:
            logger.info("No .git directory found; fusion will use static graph only.")

        graph = FusionEngine().fuse(graph, coedit_data)

        
        
        
        print()
        print(f"Parsed {len(nodes)} functions across {unique_files} files")
        print(f"Call graph: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
        print(
            f"Languages: Python={lang_counts['python']}, "
            f"JavaScript={lang_counts['javascript']}, "
            f"TypeScript={lang_counts['typescript']}"
        )
        print()

        
        sorted_by_complexity = sorted(
            graph.nodes(data=True),
            key=lambda x: x[1].get("complexity", 1),
            reverse=True,
        )[:10]
        print("Top 10 most complex functions:")
        rows_c = [
            (attrs.get("name", nid), attrs.get("file_path", ""), attrs.get("complexity", 1))
            for nid, attrs in sorted_by_complexity
        ]
        print(_fmt_table(rows_c, ("Name", "File", "Complexity"), (45, 55, 10)))
        print()

        
        sorted_by_fan_in = sorted(
            graph.nodes(data=True),
            key=lambda x: x[1].get("fan_in", 0),
            reverse=True,
        )[:10]
        print("Top 10 most depended-on functions (highest fan-in):")
        rows_fi = [
            (attrs.get("name", nid), attrs.get("file_path", ""), attrs.get("fan_in", 0))
            for nid, attrs in sorted_by_fan_in
        ]
        print(_fmt_table(rows_fi, ("Name", "File", "Fan-in"), (45, 55, 8)))
        print()

        
        sorted_by_fan_out = sorted(
            graph.nodes(data=True),
            key=lambda x: x[1].get("fan_out", 0),
            reverse=True,
        )[:10]
        print("Top 10 biggest callers (highest fan-out):")
        rows_fo = [
            (attrs.get("name", nid), attrs.get("file_path", ""), attrs.get("fan_out", 0))
            for nid, attrs in sorted_by_fan_out
        ]
        print(_fmt_table(rows_fo, ("Name", "File", "Fan-out"), (45, 55, 8)))
        print()

        
        
        
        graph_json = graph_to_json(graph)
        pyg_data = graph_to_pyg_data(graph)

        output_path.write_text(
            json.dumps(graph_json, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(f"Graph JSON saved → {output_path}")

        pyg_output_path.write_text(
            json.dumps(pyg_data, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(f"PyG data saved   → {pyg_output_path}")

    finally:
        
        if tmp_dir is not None:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            logger.info("Temporary clone directory removed.")


if __name__ == "__main__":
    main()
