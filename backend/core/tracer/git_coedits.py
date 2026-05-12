"""
git_coedits.py
--------------
Extract git co-edit frequency features: which functions (or files) tend to
change together in the same commit.

Co-editing is a strong proxy for *runtime coupling* — if two pieces of code
always get modified together they are implicitly coupled, even when there is
no explicit call between them.  These weights become edge_attr inputs to the
FusionEngine and ultimately to GATv2Conv.

Usage (standalone):
    extractor = GitCoEditExtractor("/path/to/repo")
    matrix    = extractor.extract_coedit_matrix(max_commits=500)
    weights   = extractor.get_function_coedits(function_node_list)
"""

from __future__ import annotations

import logging
import subprocess
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger("codebase-intel.git_coedits")


class GitCoEditExtractor:
    """
    Walk recent git commits and compute a co-edit frequency matrix.

    File-level co-edits are always available (requires only `git log`).
    Function-level co-edits are approximated from file-level coupling plus
    same-file git-blame proximity.

    Parameters
    ----------
    repo_path : absolute path to the root of the git repository
    """

    def __init__(self, repo_path: str) -> None:
        self.repo_path = str(Path(repo_path).resolve())

    def extract_coedit_matrix(
        self,
        max_commits: int = 500,
    ) -> Dict[Tuple[str, str], int]:
        """
        Walk the last *max_commits* commits and count how many times each
        pair of files was changed in the same commit.

        Returns
        -------
        dict mapping (file_a, file_b) → co-edit count, where file_a < file_b
        (lexicographic order to avoid duplicates), sorted by frequency descending.
        """
        cmd = [
            "git", "log",
            "--name-only",
            f"--pretty=format:COMMIT:%H",
            f"-n", str(max_commits),
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.repo_path,
                timeout=60,
            )
        except FileNotFoundError:
            logger.error("git not found in PATH — cannot extract co-edits.")
            return {}
        except subprocess.TimeoutExpired:
            logger.warning("git log timed out; returning partial results.")
            return {}

        if result.returncode != 0:
            logger.warning(
                f"git log returned exit code {result.returncode}: {result.stderr.strip()}"
            )
            return {}

        coedit_count: Dict[Tuple[str, str], int] = defaultdict(int)

        
        raw_output = result.stdout
        
        commit_blocks = raw_output.split("COMMIT:")

        for block in commit_blocks:
            lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
            if not lines:
                continue
            
            
            files = [ln for ln in lines[1:] if ln and not ln.startswith("COMMIT:")]

            
            files = [f.replace("\\", "/") for f in files]

            
            files = list(dict.fromkeys(files))

            if len(files) < 2:
                continue

            
            for file_a, file_b in combinations(sorted(files), 2):
                coedit_count[(file_a, file_b)] += 1

        
        sorted_matrix = dict(
            sorted(coedit_count.items(), key=lambda kv: kv[1], reverse=True)
        )
        logger.info(
            f"Co-edit matrix: {len(sorted_matrix)} file pairs across ≤{max_commits} commits."
        )
        return sorted_matrix

    def get_function_coedits(
        self,
        function_nodes: list,
        max_commits: int = 500,
    ) -> Dict[Tuple[str, str], float]:
        """
        Approximate *function*-level co-edit weights from file-level co-edits.

        Strategy
        --------
        * Cross-file pairs: weight = normalised co-edit count  (0.0 – 1.0).
          Only pairs whose files appear together in the co-edit matrix are
          included (sparse — avoids an O(n²) dense pass over all functions).
        * Same-file pairs: weight = 0.5 (moderate default coupling — they
          share a file and may share commit history).

        Parameters
        ----------
        function_nodes : list of objects with `id` (str) and `file_path` (str)
                         attributes (e.g. FunctionNode from tree_sitter_parser).
        max_commits    : passed through to extract_coedit_matrix.

        Returns
        -------
        dict mapping (func_id_a, func_id_b) → weight [0.0, 1.0]
        """
        
        file_to_funcs: Dict[str, List[str]] = defaultdict(list)
        for fn in function_nodes:
            if isinstance(fn, dict):
                fp = str(fn.get("file_path", "") or "")
                fid = str(fn.get("id", "") or fn)
            else:
                fp = getattr(fn, "file_path", None) or ""
                fid = getattr(fn, "id", None) or str(fn)
            fp = fp.replace("\\", "/")
            if fp and fid:
                file_to_funcs[fp].append(fid)

        func_weights: Dict[Tuple[str, str], float] = {}

        file_matrix = self.extract_coedit_matrix(max_commits=max_commits)

        
        if file_matrix:
            
            max_count = max(file_matrix.values())
            normalised: Dict[Tuple[str, str], float] = {
                pair: count / max_count for pair, count in file_matrix.items()
            }

            for (file_a, file_b), weight in normalised.items():
                funcs_a = file_to_funcs.get(file_a, [])
                funcs_b = file_to_funcs.get(file_b, [])
                if not funcs_a or not funcs_b:
                    continue
                for fid_a in funcs_a:
                    for fid_b in funcs_b:
                        key = (fid_a, fid_b) if fid_a <= fid_b else (fid_b, fid_a)
                        
                        if key not in func_weights or func_weights[key] < weight:
                            func_weights[key] = weight
        else:
            logger.info("Empty file-level co-edit matrix; same-file defaults still apply.")

        
        for fp, funcs in file_to_funcs.items():
            if len(funcs) < 2:
                continue
            for fid_a, fid_b in combinations(sorted(funcs), 2):
                key = (fid_a, fid_b)
                if key not in func_weights:
                    func_weights[key] = 0.5

        logger.info(
            f"Function-level co-edit weights: {len(func_weights)} pairs computed."
        )
        return func_weights
