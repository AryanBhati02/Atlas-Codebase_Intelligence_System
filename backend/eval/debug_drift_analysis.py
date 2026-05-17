"""
debug_drift_analysis.py
-----------------------
Deep scientific debugging of Atlas Drift F1 = 0.0.

Investigates:
  1. Cosine distance distributions (are all distances < threshold?)
  2. Function ID intersection (are old/new IDs matching at all?)
  3. Threshold sensitivity sweep (what threshold would yield non-zero F1?)
  4. False positive / false negative analysis (what Atlas misses and why)
  5. Baseline vs Atlas comparison side-by-side
  6. Training objective mismatch hypothesis testing

Usage (from backend/):
    python eval/debug_drift_analysis.py \\
        --repo_path <path_to_repo_with_git_history> \\
        --commits 5 \\
        --output_dir eval/results/drift_debug

The script produces:
  - Console output with full analysis
  - eval/results/drift_debug/commit_<hash>_analysis.json per commit
  - eval/results/drift_debug/summary.json
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("debug_drift")

from eval.eval_drift import (
    get_commits_with_python_changes,
    get_changed_line_ranges,
    checkout_commit,
    checkout_back,
    get_current_branch,
    _has_parent,
    _normalize_diff_paths,
    _check_shallow_clone,
)


def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    idx = max(0, min(len(sorted_values) - 1, int(len(sorted_values) * p / 100)))
    return sorted_values[idx]


def _dist_stats(distances: list[float]) -> dict:
    if not distances:
        return {"count": 0, "min": None, "max": None, "mean": None,
                "p25": None, "p50": None, "p75": None, "p90": None, "p95": None}
    s = sorted(distances)
    mean = sum(s) / len(s)
    return {
        "count": len(s),
        "min": round(s[0], 6),
        "max": round(s[-1], 6),
        "mean": round(mean, 6),
        "p25": round(_percentile(s, 25), 6),
        "p50": round(_percentile(s, 50), 6),
        "p75": round(_percentile(s, 75), 6),
        "p90": round(_percentile(s, 90), 6),
        "p95": round(_percentile(s, 95), 6),
    }


def _threshold_sweep(distances: list[float], ground_truth_ids: set[str],
                     id_to_dist: dict[str, float]) -> list[dict]:
    """
    For thresholds from 0.01 to 0.99 in steps of 0.01,
    compute how many functions Atlas would flag and the resulting F1.
    """
    results = []
    all_ids = set(id_to_dist.keys())
    for t_int in range(1, 100, 2):
        t = t_int / 100
        predicted = {fid for fid, d in id_to_dist.items() if d > t}
        tp = len(predicted & ground_truth_ids)
        fp = len(predicted - ground_truth_ids)
        fn = len(ground_truth_ids - predicted)
        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        f1 = 2 * prec * rec / max(prec + rec, 1e-8)
        results.append({
            "threshold": t,
            "predicted_count": len(predicted),
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
        })
    return results


def _find_optimal_threshold(sweep: list[dict]) -> dict:
    return max(sweep, key=lambda r: r["f1"])

def analyze_commit(
    detector,
    parser,
    repo_path: str,
    commit_hash: str,
    threshold: float,
    output_dir: Path,
) -> dict:
    """
    Full diagnostic analysis for one commit.
    Returns a dict with all findings.
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"ANALYZING COMMIT {commit_hash}")
    logger.info(f"{'='*60}")

    changed_ranges = get_changed_line_ranges(repo_path, commit_hash)
    logger.info(f"  Git diff: {len(changed_ranges)} changed files.")
    logger.info(f"  Diff keys (sample): {list(changed_ranges.keys())[:5]}")

    logger.info(f"  Checking out {commit_hash}^1 (parent)…")
    checkout_commit(repo_path, f"{commit_hash}^1")
    old_nodes = parser.parse_repository(repo_path)
    logger.info(f"  Parent: {len(old_nodes)} functions parsed.")

    logger.info(f"  Checking out {commit_hash} (current)…")
    checkout_commit(repo_path, commit_hash)
    new_nodes = parser.parse_repository(repo_path)
    logger.info(f"  Current: {len(new_nodes)} functions parsed.")

    if not new_nodes or not old_nodes:
        logger.warning("  SKIP: zero functions at old or new snapshot.")
        return {"commit": commit_hash, "error": "zero_functions",
                "old_count": len(old_nodes), "new_count": len(new_nodes)}

    changed_ranges_norm = _normalize_diff_paths(changed_ranges, new_nodes, commit_hash)
    logger.info(
        f"  After path normalization: {len(changed_ranges_norm)} effective changed-file entries.")

    old_ids = {n.id for n in old_nodes}
    new_ids = {n.id for n in new_nodes}
    intersection = old_ids & new_ids
    only_in_old = old_ids - new_ids
    only_in_new = new_ids - old_ids

    logger.info(
        f"  ID intersection: {len(intersection)} matched / "
        f"{len(only_in_old)} removed / {len(only_in_new)} added."
    )
    logger.info(f"  Sample old IDs : {list(old_ids)[:3]}")
    logger.info(f"  Sample new IDs : {list(new_ids)[:3]}")

    if not intersection:
        logger.error(
            "  CRITICAL: old∩new is EMPTY — zero functions can be compared! "
            "This means function IDs changed completely between commits. "
            "Possible cause: file renamed, class refactor, or ID includes line number."
        )

    def _get_gt(nodes, ranges):
        changed_ids: set[str] = set()
        for node in nodes:
            file_ranges = ranges.get(node.file_path, [])
            for rs, re in file_ranges:
                if node.line_start <= re and node.line_end >= rs:
                    changed_ids.add(node.id)
                    break
        return changed_ids

    ground_truth_ids = _get_gt(new_nodes, changed_ranges_norm)
    logger.info(
        f"  Ground truth: {len(ground_truth_ids)} functions overlap with diff "
        f"(out of {len(new_nodes)} new functions)."
    )
    if ground_truth_ids:
        logger.info(f"  Sample GT IDs: {list(ground_truth_ids)[:3]}")
    else:
        logger.warning(
            "  Ground truth is EMPTY — this commit will be skipped by evaluator. "
            "Inspect diff ranges vs node line ranges."
        )
        sample_nodes = [(n.file_path, n.line_start, n.line_end, n.id) for n in new_nodes[:5]]
        sample_ranges = [(k, v[:2]) for k, v in list(changed_ranges_norm.items())[:5]]
        logger.warning(f"  Sample new nodes: {sample_nodes}")
        logger.warning(f"  Sample changed ranges: {sample_ranges}")

    logger.info(f"  Embedding {len(intersection)} matched functions…")
    if not intersection:
        logger.warning("  Cannot compute cosine distances: intersection is empty.")
        return {
            "commit": commit_hash,
            "old_count": len(old_nodes),
            "new_count": len(new_nodes),
            "intersection_count": 0,
            "ground_truth_count": len(ground_truth_ids),
            "error": "empty_intersection",
        }

    old_matched = [n for n in old_nodes if n.id in intersection]
    new_matched = [n for n in new_nodes if n.id in intersection]

    old_embeddings = detector.embed_all(old_matched)
    new_embeddings = detector.embed_all(new_matched)

    import numpy as np
    distances: list[float] = []
    id_to_dist: dict[str, float] = {}

    for fid in intersection:
        old_emb = old_embeddings.get(fid)
        new_emb = new_embeddings.get(fid)
        if old_emb is None or new_emb is None:
            continue
        norm_o = np.linalg.norm(old_emb)
        norm_n = np.linalg.norm(new_emb)
        cos_sim = float(np.dot(old_emb, new_emb) / (norm_o * norm_n + 1e-8))
        cos_dist = 1.0 - cos_sim
        distances.append(cos_dist)
        id_to_dist[fid] = cos_dist

    logger.info(
        f"  Computed {len(distances)} cosine distances for matched function pairs."
    )

    stats = _dist_stats(distances)
    logger.info(f"  Cosine distance distribution:")
    logger.info(f"    min={stats['min']}  max={stats['max']}  mean={stats['mean']}")
    logger.info(f"    p25={stats['p25']}  p50={stats['p50']}  p75={stats['p75']}")
    logger.info(f"    p90={stats['p90']}  p95={stats['p95']}")

    predicted_drifted = {fid for fid, d in id_to_dist.items() if d > threshold}
    logger.info(
        f"  At threshold={threshold}: {len(predicted_drifted)}/{len(id_to_dist)} "
        f"matched functions flagged as drifted."
    )
    if not predicted_drifted:
        logger.warning(
            f"  ZERO functions pass threshold={threshold}. "
            f"Max distance seen = {stats['max']}. "
            f"This is the primary cause of F1=0."
        )

    added_count = len(only_in_new)
    removed_count = len(only_in_old)
    logger.info(f"  Added (always flagged as drifted): {added_count}")
    logger.info(f"  Removed (in old only):              {removed_count}")

    tp = len(predicted_drifted & ground_truth_ids)
    fp = len(predicted_drifted - ground_truth_ids)
    fn = len(ground_truth_ids - predicted_drifted)
    prec = tp / max(tp + fp, 1)
    rec = tp / max(tp + fn, 1)
    f1 = 2 * prec * rec / max(prec + rec, 1e-8)

    logger.info(f"  Atlas  @ threshold={threshold}: TP={tp} FP={fp} FN={fn} "
                f"P={prec:.4f} R={rec:.4f} F1={f1:.4f}")

    fn_ids = list(ground_truth_ids - predicted_drifted)[:10]
    fn_details = []
    for fid in fn_ids:
        dist = id_to_dist.get(fid, "NOT_IN_INTERSECTION")
        fn_details.append({"id": fid, "cosine_dist": dist, "threshold": threshold})
        logger.info(f"  FN: {fid[:80]}  cosine_dist={dist!r}")

    fp_ids = list(predicted_drifted - ground_truth_ids)[:10]
    fp_details = []
    for fid in fp_ids:
        dist = id_to_dist.get(fid, "?")
        fp_details.append({"id": fid, "cosine_dist": dist})
        logger.info(f"  FP: {fid[:80]}  cosine_dist={dist!r}")

    changed_files = set(changed_ranges_norm.keys())
    baseline_predicted = {n.id for n in new_nodes if n.file_path in changed_files}
    b_tp = len(baseline_predicted & ground_truth_ids)
    b_fp = len(baseline_predicted - ground_truth_ids)
    b_fn = len(ground_truth_ids - baseline_predicted)
    b_prec = b_tp / max(b_tp + b_fp, 1)
    b_rec = b_tp / max(b_tp + b_fn, 1)
    b_f1 = 2 * b_prec * b_rec / max(b_prec + b_rec, 1e-8)
    logger.info(f"  Baseline (file-level): TP={b_tp} FP={b_fp} FN={b_fn} "
                f"P={b_prec:.4f} R={b_rec:.4f} F1={b_f1:.4f}")

    sweep = _threshold_sweep(distances, ground_truth_ids, id_to_dist)
    opt = _find_optimal_threshold(sweep)
    logger.info(
        f"  OPTIMAL threshold for this commit: {opt['threshold']} "
        f"→ F1={opt['f1']} (TP={opt['tp']} FP={opt['fp']} FN={opt['fn']})"
    )

    nonzero_f1 = [r for r in sweep if r["f1"] > 0]
    if nonzero_f1:
        logger.info(
            f"  Thresholds giving F1>0: [{nonzero_f1[0]['threshold']} … "
            f"{nonzero_f1[-1]['threshold']}]  ({len(nonzero_f1)} values)"
        )
    else:
        logger.warning("  NO threshold gives F1>0 for this commit!")

    gt_in_intersection = [fid for fid in ground_truth_ids if fid in id_to_dist]
    gt_distances = [id_to_dist[fid] for fid in gt_in_intersection]
    gt_stats = _dist_stats(sorted(gt_distances))
    logger.info(
        f"  Cosine distances of GROUND-TRUTH functions (n={len(gt_distances)}): "
        f"min={gt_stats.get('min')} max={gt_stats.get('max')} mean={gt_stats.get('mean')}"
    )

    non_gt_distances = [d for fid, d in id_to_dist.items()
                        if fid not in ground_truth_ids]
    non_gt_stats = _dist_stats(sorted(non_gt_distances))
    logger.info(
        f"  Cosine distances of NON-GROUND-TRUTH functions (n={len(non_gt_distances)}): "
        f"min={non_gt_stats.get('min')} max={non_gt_stats.get('max')} mean={non_gt_stats.get('mean')}"
    )

    if gt_distances and non_gt_distances:
        gt_mean = gt_stats["mean"] or 0
        non_gt_mean = non_gt_stats["mean"] or 0
        separability = gt_mean - non_gt_mean
        logger.info(
            f"  Separability (GT mean dist - non-GT mean dist): {separability:.6f}  "
            f"{'[POSITIVE = model gives GT higher dist — good]' if separability > 0 else '[NEGATIVE = model cannot separate GT from non-GT — failure]'}"
        )

    artifact = {
        "commit": commit_hash,
        "old_count": len(old_nodes),
        "new_count": len(new_nodes),
        "intersection_count": len(intersection),
        "added_count": added_count,
        "removed_count": removed_count,
        "ground_truth_count": len(ground_truth_ids),
        "ground_truth_in_intersection": len(gt_in_intersection),
        "diff_files": len(changed_ranges_norm),
        "cosine_dist_stats": stats,
        "gt_cosine_dist_stats": gt_stats,
        "non_gt_cosine_dist_stats": non_gt_stats,
        "atlas_results": {
            "threshold": threshold,
            "predicted_count": len(predicted_drifted),
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
        },
        "baseline_results": {
            "predicted_count": len(baseline_predicted),
            "tp": b_tp, "fp": b_fp, "fn": b_fn,
            "precision": round(b_prec, 4),
            "recall": round(b_rec, 4),
            "f1": round(b_f1, 4),
        },
        "optimal_threshold": opt,
        "threshold_sweep": sweep,
        "false_negatives_sample": fn_details,
        "false_positives_sample": fp_details,
    }

    out_file = output_dir / f"commit_{commit_hash}_analysis.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2)
    logger.info(f"  Artifact saved: {out_file}")

    return artifact

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Deep diagnostic analysis of Atlas Drift F1=0.0. "
            "Inspects cosine distance distributions, ID intersections, "
            "threshold sensitivity, and FP/FN breakdown."
        )
    )
    parser.add_argument("--repo_path", required=True,
                        help="Path to repo with full git history.")
    parser.add_argument("--commits", type=int, default=5,
                        help="Number of commits to analyze (default: 5).")
    parser.add_argument("--threshold", type=float, default=0.15,
                        help="Cosine distance threshold (default: 0.15).")
    parser.add_argument("--output_dir", default="eval/results/drift_debug",
                        help="Directory for per-commit JSON artifacts.")
    parser.add_argument("--model_checkpoint",
                        default="training/checkpoints/best_model.pt")
    parser.add_argument("--vocab_path",
                        default="training/data/vocab.json")
    args = parser.parse_args()

    import torch
    from core.model.function_encoder import FunctionEncoder
    from core.model.dataset import Vocabulary
    from core.parser.tree_sitter_parser import TreeSitterParser
    from core.drift.drift_detector import DriftDetector

    backend_root = Path(__file__).resolve().parent.parent
    vocab_path = (args.vocab_path if os.path.isabs(args.vocab_path)
                  else str(backend_root / args.vocab_path))
    ckpt_path = (args.model_checkpoint if os.path.isabs(args.model_checkpoint)
                 else str(backend_root / args.model_checkpoint))

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
    logger.info(f"Model loaded (vocab={stored_vocab_size}, device={device})")

    ts_parser = TreeSitterParser()
    detector = DriftDetector(encoder=encoder, vocab=vocab, device=device)

    output_dir = (Path(args.output_dir) if os.path.isabs(args.output_dir)
                  else backend_root / args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if _check_shallow_clone(args.repo_path):
        logger.warning(
            "SHALLOW CLONE: git history is truncated. "
            "Results may be incomplete. Clone with full depth for best results."
        )

    original_branch = get_current_branch(args.repo_path)
    logger.info(f"Repo: {args.repo_path}  branch={original_branch}")
    commits = get_commits_with_python_changes(args.repo_path, n=args.commits)

    if not commits:
        logger.error("No qualifying commits found. Exiting.")
        sys.exit(1)

    logger.info(f"Will analyze {len(commits)} commits: {commits}")

    commit_results: list[dict] = []
    for commit_hash in commits:
        try:
            result = analyze_commit(
                detector, ts_parser, args.repo_path, commit_hash,
                args.threshold, output_dir,
            )
            commit_results.append(result)
        except Exception as exc:
            logger.error(f"Error analyzing {commit_hash}: {exc}", exc_info=True)
        finally:
            try:
                checkout_back(args.repo_path, original_branch)
            except Exception:
                pass

    print("\n" + "="*70)
    print("  CROSS-COMMIT DIAGNOSTIC SUMMARY")
    print("="*70)

    valid = [r for r in commit_results if "error" not in r]
    if not valid:
        print("  No commits produced valid analysis.")
    else:
        all_dists_flat: list[float] = []
        all_gt_dists:  list[float] = []
        all_non_gt_dists: list[float] = []
        atlas_f1s: list[float] = []
        base_f1s: list[float] = []
        optimal_thresholds: list[float] = []
        zero_intersection = 0
        zero_gt = 0

        for r in valid:
            if r.get("intersection_count", 0) == 0:
                zero_intersection += 1
            if r.get("ground_truth_count", 0) == 0:
                zero_gt += 1
            stats = r.get("cosine_dist_stats", {})
            if stats.get("mean") is not None:
                pass

            gt_stats = r.get("gt_cosine_dist_stats", {})
            non_gt_stats = r.get("non_gt_cosine_dist_stats", {})

            ar = r.get("atlas_results", {})
            br = r.get("baseline_results", {})
            atlas_f1s.append(ar.get("f1", 0.0))
            base_f1s.append(br.get("f1", 0.0))

            ot = r.get("optimal_threshold", {})
            if ot:
                optimal_thresholds.append(ot.get("threshold", 0))

            print(f"\n  Commit {r['commit'][:10]}:")
            print(f"    Old={r.get('old_count','?')}  New={r.get('new_count','?')}  "
                  f"Intersect={r.get('intersection_count','?')}  "
                  f"GT={r.get('ground_truth_count','?')}")
            cs = r.get("cosine_dist_stats", {})
            print(f"    Cosine dist: mean={cs.get('mean')}  "
                  f"p50={cs.get('p50')}  p90={cs.get('p90')}  max={cs.get('max')}")
            gt_cs = r.get("gt_cosine_dist_stats", {})
            ngt_cs = r.get("non_gt_cosine_dist_stats", {})
            print(f"    GT func dist: mean={gt_cs.get('mean')}  "
                  f"non-GT dist: mean={ngt_cs.get('mean')}  "
                  f"separability={round((gt_cs.get('mean') or 0) - (ngt_cs.get('mean') or 0), 6)}")
            print(f"    Atlas F1={ar.get('f1')}  Baseline F1={br.get('f1')}")
            print(f"    Optimal threshold: {ot.get('threshold')} → F1={ot.get('f1')}")

        print(f"\n  Commits with EMPTY intersection: {zero_intersection}/{len(valid)}")
        print(f"  Commits with EMPTY ground truth: {zero_gt}/{len(valid)}")
        if atlas_f1s:
            avg_atlas = sum(atlas_f1s) / len(atlas_f1s)
            avg_base  = sum(base_f1s) / len(base_f1s)
            avg_opt   = sum(optimal_thresholds) / len(optimal_thresholds) if optimal_thresholds else None
            print(f"\n  Average Atlas F1   : {avg_atlas:.4f}")
            print(f"  Average Baseline F1: {avg_base:.4f}")
            if avg_opt:
                print(f"  Average OPTIMAL threshold: {avg_opt:.2f}")

    print("\n" + "="*70)
    print("  FAILURE MODE HYPOTHESES")
    print("="*70)
    print("""
  H1 — Cosine distances cluster near 0 (model collapses):
       → Check 'cosine_dist_stats.max' above. If max < 0.15, confirmed.

  H2 — Threshold=0.15 too strict for this model:
       → Check 'optimal_threshold.threshold' above. If optimal > 0.15, confirmed.

  H3 — Old∩New intersection empty (ID instability):
       → Check 'intersection_count' above. If 0, confirmed.

  H4 — Ground truth empty (path mismatch / all non-function changes):
       → Check 'ground_truth_count' above. If consistently 0, confirmed.

  H5 — Model cannot separate changed vs unchanged functions:
       → Check 'separability' (GT mean dist - non-GT mean dist).
         If <= 0, the model actively anti-separates GT from non-GT.

  H6 — Training objective (InfoNCE on intent-verb pairs) unrelated to drift:
       → InfoNCE trains the model to cluster functions by SEMANTIC INTENT
         (docstring verbs: 'parse', 'load', 'validate'…). Two versions of
         the SAME function will appear VERY SIMILAR to the model even if
         the code changed — because the function NAME and intent haven't
         changed. This would cause cosine distances to cluster near 0
         for all matched pairs, regardless of actual code change.
    """)

    summary = {
        "repo_path": args.repo_path,
        "threshold_used": args.threshold,
        "commits_analyzed": len(commit_results),
        "commits_valid": len(valid),
        "per_commit": commit_results,
    }
    summary_path = output_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    logger.info(f"Summary saved: {summary_path}")
    print(f"\n  Full artifacts: {output_dir}")
    print("="*70)


if __name__ == "__main__":
    main()
