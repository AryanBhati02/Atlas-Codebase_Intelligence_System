"""
eval_drift.py
-------------
Drift Detection F1 evaluation using git history.

Strategy:
  - Get the last N commits that modify Python/JS/TS files
  - For each commit: parse functions before and after, run DriftDetector
  - Ground truth: functions whose line ranges overlap with `git diff` changed lines
  - Compare Atlas predictions vs ground truth → Precision, Recall, F1
  - Also compute a file-level baseline (any function in a changed file is flagged)

IMPORTANT: This eval needs repos with FULL git history (not shallow clones).
alsoo Clone with: git clone https://github.com/tiangolo/fastapi /tmp/fastapi_full
(Do NOT use --depth=1)

Usage :
    python eval/eval_drift.py --repo_path /tmp/fastapi_full --commits 10
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("eval_drift")

def _run_git(args: list[str], cwd: str, check: bool = False) -> str:
    """Run a git command and return stdout, logging stderr on failure."""
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if stderr:
            logger.warning(f"git {' '.join(args[:3])} failed (exit {result.returncode}): {stderr[:300]}")
        if check:
            raise RuntimeError(f"git command failed: {' '.join(args)}: {stderr[:200]}")
    if result.stdout:
        return result.stdout.strip()
    return ""


def _check_shallow_clone(repo_path: str) -> bool:
    """Return True when the repo is a shallow clone (--depth=N)."""
    shallow_file = Path(repo_path) / ".git" / "shallow"
    return shallow_file.exists()


def _has_parent(repo_path: str, commit_hash: str) -> bool:
    """Return True if commit has at least one parent (i.e. is not the root commit)."""
    out = _run_git(["rev-parse", "--verify", f"{commit_hash}^"], cwd=repo_path)
    return bool(out)


def _normalize_diff_paths(
    changed_ranges: dict[str, list[tuple[int, int]]],
    new_nodes: list,
    commit_hash: str,
) -> dict[str, list[tuple[int, int]]]:
    """
    Reconcile git-diff path keys with FunctionNode.file_path values.

    git diff returns repo-relative paths (e.g. 'backend/core/foo.py').
    parse_repository() also returns repo-relative paths — but relative to
    the directory passed in. If you call parse_repository('backend/') the
    paths will be 'core/foo.py'. This function detects and corrects the
    mismatch by stripping the common leading prefix from diff keys.

    Returns a new dict whose keys align with node.file_path values.
    """
    if not changed_ranges or not new_nodes:
        return changed_ranges

    node_paths: set[str] = {n.file_path for n in new_nodes}

    # 1. Fast-path: direct match already works
    direct_hits = [k for k in changed_ranges if k in node_paths]
    if direct_hits:
        logger.info(
            f"  [PATH-NORM {commit_hash[:7]}] Direct match: {len(direct_hits)}/{len(changed_ranges)} "
            f"diff keys matched node paths. No normalization needed."
        )
        return changed_ranges

    # 2. No direct matches — try stripping leading path components from diff keys
    logger.info(
        f"  [PATH-NORM {commit_hash[:7]}] Zero direct matches. "
        f"Sample diff keys  : {list(changed_ranges.keys())[:3]}"
    )
    logger.info(
        f"  [PATH-NORM {commit_hash[:7]}] Sample node paths : {list(node_paths)[:3]}"
    )

    normalized: dict[str, list[tuple[int, int]]] = {}
    matched_count = 0
    for diff_key, ranges in changed_ranges.items():
        parts = diff_key.split("/")
        matched = False
        for strip_count in range(1, len(parts)):
            candidate = "/".join(parts[strip_count:])
            if candidate in node_paths:
                normalized[candidate] = ranges
                matched = True
                matched_count += 1
                break
        if not matched:
            # 3. Also try stripping leading components from node paths to match diff key
            for np in node_paths:
                np_parts = np.split("/")
                for strip_np in range(1, len(np_parts)):
                    candidate_np = "/".join(np_parts[strip_np:])
                    if diff_key.endswith(candidate_np):
                        normalized[np] = ranges
                        matched = True
                        matched_count += 1
                        break
                if matched:
                    break
        if not matched:
            # Keep original key as fallback (won't match but preserves data)
            normalized.setdefault(diff_key, ranges)

    logger.info(
        f"  [PATH-NORM {commit_hash[:7]}] After normalization: "
        f"{matched_count}/{len(changed_ranges)} diff keys resolved → "
        f"{len(normalized)} total keys in normalized map."
    )
    return normalized



def get_commits_with_python_changes(repo_path: str, n: int = 10) -> list[str]:
    """Return last N commit hashes that modified .py / .js / .ts files."""
    if _check_shallow_clone(repo_path):
        logger.warning(
            "SHALLOW CLONE DETECTED (.git/shallow exists). "
            "Drift eval needs full history — clone with: git clone <url> (no --depth flag). "
            "Attempting to continue anyway but commit history will be incomplete."
        )

    out = _run_git(
        [
            "log",
            "--oneline",
            "--diff-filter=M",
            f"-n", str(n * 3),   # over-sample, then take first N
            "--",
            "*.py",
            "*.js",
            "*.ts",
        ],
        cwd=repo_path,
    )
    if not out:
        logger.warning(
            "git log returned no output. Possible causes: "
            "(1) shallow clone, (2) repo has no .py/.js/.ts commits, "
            "(3) git not on PATH, (4) repo_path is wrong."
        )
    commits = [line.split()[0] for line in out.splitlines() if line.strip()]
    logger.info(f"Found {len(commits)} candidate commits (requested {n}).")
    return commits[:n]


def get_changed_line_ranges(repo_path: str, commit_hash: str) -> dict[str, list[tuple[int, int]]]:
    """
    For a given commit, return a dict mapping filepath → list of (start, end) line ranges
    that were added or modified (compared to parent).

    Paths are always normalised to forward slashes (matching FunctionNode.file_path).
    """
    diff = _run_git(
        ["diff", f"{commit_hash}^1", commit_hash, "--unified=0"],
        cwd=repo_path,
    )
    if not diff:
        logger.warning(f"git diff for {commit_hash} returned empty output — commit may have no parent or diff failed.")

    result: dict[str, list[tuple[int, int]]] = {}
    current_file = ""

    hunk_re = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
    file_re = re.compile(r"^\+\+\+ b/(.+)$")

    for line in diff.splitlines():
        fm = file_re.match(line)
        if fm:
            # Normalise to forward slashes to match parse_repository() output
            current_file = fm.group(1).replace("\\", "/")
            result.setdefault(current_file, [])
            continue
        hm = hunk_re.match(line)
        if hm and current_file:
            start = int(hm.group(1))
            length = int(hm.group(2)) if hm.group(2) is not None else 1
            if length > 0:
                result[current_file].append((start, start + length - 1))

    return result


def checkout_commit(repo_path: str, commit_hash: str) -> None:
    _run_git(["checkout", "-q", commit_hash], cwd=repo_path)


def checkout_back(repo_path: str, original_branch: str) -> None:
    _run_git(["checkout", "-q", original_branch], cwd=repo_path)


def get_current_branch(repo_path: str) -> str:
    result = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path)
    return result.strip() or "HEAD"

class DriftEvaluator:
    def __init__(self, detector, parser):
        self.detector = detector
        self.parser = parser

    def _get_changed_function_ids(
        self,
        all_new_nodes: list,
        changed_ranges: dict[str, list[tuple[int, int]]],
    ) -> set[str]:
        """
        Map git diff line ranges to function IDs.
        A function is "changed" if its [line_start, line_end] overlaps any changed range
        in its file.
        """
        changed_ids: set[str] = set()
        for node in all_new_nodes:
            file_ranges = changed_ranges.get(node.file_path, [])
            for range_start, range_end in file_ranges:
                # Overlap check
                if node.line_start <= range_end and node.line_end >= range_start:
                    changed_ids.add(node.id)
                    break
        return changed_ids

    def _get_baseline_flagged_ids(
        self,
        all_new_nodes: list,
        changed_ranges: dict[str, list[tuple[int, int]]],
    ) -> set[str]:
        """
        Baseline: flag ALL functions in any file that appears in the diff.
        No embeddings — pure file-level detection.
        """
        changed_files = set(changed_ranges.keys())
        return {n.id for n in all_new_nodes if n.file_path in changed_files}

    @staticmethod
    def _f1(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-8)
        return round(precision, 4), round(recall, 4), round(f1, 4)

    def evaluate_on_repo(self, repo_path: str, num_commits: int = 10, threshold: float = 0.15) -> dict:
        """
        Evaluate DriftDetector on the last N commits of a repo.
        """
        original_branch = get_current_branch(repo_path)
        logger.info(f"[DRIFT EVAL] repo_path={repo_path!r}  branch={original_branch!r}")

        commits = get_commits_with_python_changes(repo_path, n=num_commits)

        if not commits:
            logger.warning(
                "No commits with Python/JS/TS changes found. "
                "Check: (1) repo has git history, (2) contains .py/.js/.ts files, "
                "(3) git is on PATH, (4) --repo_path is correct."
            )
            # Extra diagnostics: try a plain git log to see if ANY commits exist
            plain_log = _run_git(["log", "--oneline", "-n", "5"], cwd=repo_path)
            if plain_log:
                logger.info(f"  [DIAG] 'git log --oneline -5' shows commits exist:\n{plain_log}")
                logger.info(
                    "  [DIAG] But none matched '*.py *.js *.ts' with --diff-filter=M. "
                    "Try: git log --oneline -- '*.py' to verify."
                )
            else:
                logger.error(
                    "  [DIAG] 'git log' returned nothing. "
                    "Is repo_path a valid git repository with history?"
                )
            return {
                "error": "No qualifying commits found",
                "num_commits": 0,
                "num_functions_evaluated": 0,
                "per_commit_results": [],
                "atlas_f1": 0.0,
                "atlas_precision": 0.0,
                "atlas_recall": 0.0,
                "baseline_f1": 0.0,
                "baseline_precision": 0.0,
                "baseline_recall": 0.0,
                "improvement_over_baseline": "+0.0%",
                "threshold_used": threshold,
            }

        logger.info(
            f"[DRIFT EVAL] Found {len(commits)} qualifying commits: {commits}"
        )

        # Aggregate metrics
        total_tp = 0
        total_fp = 0
        total_fn = 0
        baseline_tp = 0
        baseline_fp = 0
        baseline_fn = 0
        total_functions = 0
        per_commit: list[dict] = []
        skipped_no_parent = 0
        skipped_no_functions = 0
        skipped_no_groundtruth = 0
        skipped_error = 0

        for idx, commit_hash in enumerate(commits):
            logger.info(f"  [{idx+1}/{len(commits)}] ===== Commit {commit_hash} =====")
            try:
                # --- Guard: skip commits with no parent (e.g. initial commit) ---
                if not _has_parent(repo_path, commit_hash):
                    logger.info(f"  SKIP {commit_hash}: no parent commit (root commit, cannot diff).")
                    skipped_no_parent += 1
                    continue

                changed_ranges = get_changed_line_ranges(repo_path, commit_hash)
                logger.info(
                    f"  git diff produced {len(changed_ranges)} changed files. "
                    f"Sample diff keys: {list(changed_ranges.keys())[:5]}"
                )
                if not changed_ranges:
                    logger.warning(
                        f"  SKIP {commit_hash}: git diff returned no hunks. "
                        "(Merge commit? Binary-only changes? Diff command failed?)"
                    )
                    skipped_no_groundtruth += 1
                    continue

                # Checkout parent snapshot
                logger.info(f"  Checking out parent {commit_hash}^1 …")
                checkout_commit(repo_path, f"{commit_hash}^1")
                old_nodes = self.parser.parse_repository(repo_path)
                logger.info(f"  Parent snapshot: {len(old_nodes)} functions parsed.")

                # Checkout commit snapshot
                logger.info(f"  Checking out commit {commit_hash} …")
                checkout_commit(repo_path, commit_hash)
                new_nodes = self.parser.parse_repository(repo_path)
                logger.info(
                    f"  Commit snapshot: {len(new_nodes)} functions parsed. "
                    f"Sample node paths: {[n.file_path for n in new_nodes[:3]]}"
                )

                if not new_nodes:
                    logger.warning(
                        f"  SKIP {commit_hash}: no functions found at this commit. "
                        "tree-sitter returned 0 — check that tree-sitter Python/JS/TS "
                        "grammars are installed (pip install tree-sitter-python)."
                    )
                    skipped_no_functions += 1
                    continue

                # --- Path normalization: align git-diff keys with node.file_path ---
                changed_ranges = _normalize_diff_paths(changed_ranges, new_nodes, commit_hash)

                ground_truth_ids = self._get_changed_function_ids(new_nodes, changed_ranges)
                logger.info(
                    f"  Ground truth: {len(ground_truth_ids)} functions overlap with diff "
                    f"(out of {len(new_nodes)} new functions, {len(changed_ranges)} changed-file entries)."
                )
                if not ground_truth_ids:
                    logger.warning(
                        f"  SKIP {commit_hash}: 0 functions overlap the diff after path normalization. "
                        "This usually means changed lines fall outside all function bodies "
                        "(e.g. module-level code, comments, blank lines). "
                        f"Changed files: {list(changed_ranges.keys())[:5]}. "
                        f"Node sample: {[(n.file_path, n.line_start, n.line_end) for n in new_nodes[:3]]}. "
                        f"Diff ranges sample: {list(changed_ranges.values())[:3]}."
                    )
                    skipped_no_groundtruth += 1
                    continue

                drift_results = self.detector.detect_drift(old_nodes, new_nodes, threshold=threshold)
                predicted_drifted = {
                    r.function_id
                    for r in drift_results
                    if r.is_drifted and r.drift_type in ("semantic", "structural", "added")
                }

                type_counts: dict[str, int] = {}
                dist_values: list[float] = []
                for r in drift_results:
                    type_counts[r.drift_type] = type_counts.get(r.drift_type, 0) + 1
                    if r.drift_type in ("semantic", "stable"):
                        dist_values.append(r.cosine_distance)
                if dist_values:
                    dist_values_s = sorted(dist_values)
                    n = len(dist_values_s)
                    p50 = dist_values_s[n // 2]
                    p90 = dist_values_s[int(n * 0.9)]
                    logger.info(
                        f"  Cosine dist stats (semantic/stable, n={n}): "
                        f"min={dist_values_s[0]:.4f}  p50={p50:.4f}  "
                        f"p90={p90:.4f}  max={dist_values_s[-1]:.4f}  threshold={threshold}"
                    )
                    below = sum(1 for d in dist_values_s if d <= threshold)
                    logger.info(
                        f"  Functions below threshold (not flagged): {below}/{n} ({below*100//max(n,1)}%). "
                        f"Functions above threshold (flagged semantic/structural): {n-below}/{n}."
                    )
                logger.info(
                    f"  Atlas flagged: {len(predicted_drifted)} functions as drifted "
                    f"(by type: {type_counts})."
                )

                # Baseline predictions
                baseline_predicted = self._get_baseline_flagged_ids(new_nodes, changed_ranges)

                # Metrics for this commit
                tp = len(predicted_drifted & ground_truth_ids)
                fp = len(predicted_drifted - ground_truth_ids)
                fn = len(ground_truth_ids - predicted_drifted)

                b_tp = len(baseline_predicted & ground_truth_ids)
                b_fp = len(baseline_predicted - ground_truth_ids)
                b_fn = len(ground_truth_ids - baseline_predicted)

                prec, rec, f1 = self._f1(tp, fp, fn)
                b_prec, b_rec, b_f1 = self._f1(b_tp, b_fp, b_fn)

                total_tp += tp
                total_fp += fp
                total_fn += fn
                baseline_tp += b_tp
                baseline_fp += b_fp
                baseline_fn += b_fn
                total_functions += len(new_nodes)

                per_commit.append(
                    {
                        "commit": commit_hash,
                        "num_functions": len(new_nodes),
                        "ground_truth_changed": len(ground_truth_ids),
                        "atlas_flagged": len(predicted_drifted),
                        "baseline_flagged": len(baseline_predicted),
                        "atlas_f1": f1,
                        "atlas_precision": prec,
                        "atlas_recall": rec,
                        "baseline_f1": b_f1,
                        "baseline_precision": b_prec,
                        "baseline_recall": b_rec,
                    }
                )
                logger.info(
                    f"  ✓ Atlas F1={f1:.3f} (P={prec:.3f} R={rec:.3f}) | "
                    f"Baseline F1={b_f1:.3f}"
                )

            except Exception as exc:
                logger.error(f"  ERROR processing commit {commit_hash}: {exc}", exc_info=True)
                skipped_error += 1
            finally:
                # Always restore original branch
                try:
                    checkout_back(repo_path, original_branch)
                except Exception:
                    pass

        # Summary diagnostics
        logger.info(
            f"[DRIFT EVAL] Done. Commits evaluated: {len(per_commit)}/{len(commits)}. "
            f"Skipped: no_parent={skipped_no_parent}, no_functions={skipped_no_functions}, "
            f"no_groundtruth={skipped_no_groundtruth}, errors={skipped_error}."
        )

        # Aggregate micro-averaged F1
        atlas_prec, atlas_rec, atlas_f1 = self._f1(total_tp, total_fp, total_fn)
        base_prec, base_rec, base_f1 = self._f1(baseline_tp, baseline_fp, baseline_fn)

        improvement = atlas_f1 - base_f1
        improvement_str = f"+{improvement*100:.1f}%" if improvement >= 0 else f"{improvement*100:.1f}%"

        return {
            "atlas_f1": atlas_f1,
            "atlas_precision": atlas_prec,
            "atlas_recall": atlas_rec,
            "baseline_f1": base_f1,
            "baseline_precision": base_prec,
            "baseline_recall": base_rec,
            "improvement_over_baseline": improvement_str,
            "num_commits": len(per_commit),
            "num_functions_evaluated": total_functions,
            "threshold_used": threshold,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "per_commit_results": per_commit,
        }


def _print_results(results: dict) -> None:
    try:
        from tabulate import tabulate

        rows = [
            ["Atlas F1",            results["atlas_f1"],      results["atlas_precision"],      results["atlas_recall"]],
            ["Baseline (file-lvl)", results["baseline_f1"],   results["baseline_precision"],   results["baseline_recall"]],
        ]
        print("\n" + tabulate(
            rows,
            headers=["Method", "F1", "Precision", "Recall"],
            tablefmt="simple",
            floatfmt=".4f",
        ))
        print(f"  Improvement over baseline: {results['improvement_over_baseline']}")
        print(f"  Commits evaluated: {results['num_commits']}  | Functions: {results['num_functions_evaluated']}")
    except ImportError:
        print("\n" + "=" * 55)
        print("  Drift Detection F1 Results")
        print("=" * 55)
        print(f"  Atlas   F1={results['atlas_f1']:.4f}  P={results['atlas_precision']:.4f}  R={results['atlas_recall']:.4f}")
        print(f"  Baseline F1={results['baseline_f1']:.4f}  P={results['baseline_precision']:.4f}  R={results['baseline_recall']:.4f}")
        print(f"  Improvement: {results['improvement_over_baseline']}")
        print("=" * 55)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate DriftDetector accuracy using git commit history. "
            "IMPORTANT: requires a full-depth clone (not --depth=1). "
            "Clone with: git clone https://github.com/tiangolo/fastapi /tmp/fastapi_full"
        )
    )
    parser.add_argument(
        "--repo_path",
        required=True,
        help="Path to local repo WITH full git history.",
    )
    parser.add_argument(
        "--commits",
        type=int,
        default=10,
        help="Number of commits to evaluate (default: 10).",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.15,
        help="Cosine distance threshold for drift detection (default: 0.15).",
    )
    parser.add_argument(
        "--output",
        default="eval/results/drift_results.json",
        help="Output JSON file path.",
    )
    parser.add_argument(
        "--model_checkpoint",
        default="training/checkpoints/best_model.pt",
        help="Path to trained GATv2 model checkpoint.",
    )
    parser.add_argument(
        "--vocab_path",
        default="training/data/vocab.json",
        help="Path to vocab.json.",
    )
    args = parser.parse_args()

    import torch
    from core.model.function_encoder import FunctionEncoder
    from core.model.dataset import Vocabulary
    from core.parser.tree_sitter_parser import TreeSitterParser
    from core.drift.drift_detector import DriftDetector

    # Load vocab + model
    backend_root = Path(__file__).resolve().parent.parent
    vocab_path = args.vocab_path if os.path.isabs(args.vocab_path) else str(backend_root / args.vocab_path)
    ckpt_path = args.model_checkpoint if os.path.isabs(args.model_checkpoint) else str(backend_root / args.model_checkpoint)

    if not Path(vocab_path).exists():
        logger.error(f"Vocabulary not found: {vocab_path}")
        sys.exit(1)
    if not Path(ckpt_path).exists():
        logger.error(f"Checkpoint not found: {ckpt_path}")
        sys.exit(1)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    vocab = Vocabulary.from_file(vocab_path)
    ckpt = torch.load(ckpt_path, map_location=device)
    stored_vocab_size = ckpt.get("vocab_size", vocab.size)

    encoder = FunctionEncoder(vocab_size=stored_vocab_size)
    encoder.load_state_dict(ckpt["model_state_dict"])
    encoder.to(device)
    encoder.eval()
    logger.info(f"Model loaded ({stored_vocab_size} vocab, device={device})")

    ts_parser = TreeSitterParser()
    detector = DriftDetector(encoder=encoder, vocab=vocab, device=device)
    evaluator = DriftEvaluator(detector=detector, parser=ts_parser)

    logger.info(f"Evaluating on repo: {args.repo_path}  ({args.commits} commits)")
    results = evaluator.evaluate_on_repo(
        repo_path=args.repo_path,
        num_commits=args.commits,
        threshold=args.threshold,
    )

    _print_results(results)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Results saved to {output_path}")


if __name__ == "__main__":
    main()
