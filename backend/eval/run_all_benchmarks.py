"""
run_all_benchmarks.py
---------------------
Convenience script to run all Atlas evaluation harnesses in sequence
and produce a combined benchmark report.

Usage:
    cd backend
    python eval/run_all_benchmarks.py --repo_path /tmp/fastapi_full
"""

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_all_benchmarks")

BACKEND_DIR = Path(__file__).resolve().parents[1]
EVAL_DIR = BACKEND_DIR / "eval"
RESULTS_DIR = EVAL_DIR / "results"
TRAINING_DIR = BACKEND_DIR / "training"
CHECKPOINT = TRAINING_DIR / "checkpoints" / "best_model.pt"


def run_script(script_path: str, extra_args: list[str] | None = None) -> bool:
    """Run a Python script as a subprocess. Returns True on success."""
    cmd = [sys.executable, script_path] + (extra_args or [])
    logger.info(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            cwd=str(BACKEND_DIR),
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.stdout:
            print(result.stdout[-2000:])  # last 2k chars
        if result.returncode != 0:
            logger.error(f"Script failed (exit {result.returncode})")
            if result.stderr:
                print(result.stderr[-1000:], file=sys.stderr)
            return False
        return True
    except subprocess.TimeoutExpired:
        logger.error(f"Script timed out after 600s: {script_path}")
        return False
    except Exception as e:
        logger.error(f"Failed to run {script_path}: {e}")
        return False


def load_json(path: Path) -> dict | None:
    """Load a JSON file if it exists."""
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run all Atlas benchmarks in sequence.")
    p.add_argument(
        "--repo_path",
        default=None,
        help="Path to a repo with git history (for drift and SWE-bench evals).",
    )
    p.add_argument(
        "--checkpoint",
        default=str(CHECKPOINT),
        help=f"Path to trained model checkpoint (default: {CHECKPOINT})",
    )
    p.add_argument(
        "--skip_swebench",
        action="store_true",
        help="Skip SWE-Bench eval (requires Ollama).",
    )
    p.add_argument(
        "--skip_drift",
        action="store_true",
        help="Skip Drift eval (requires repo with git history).",
    )
    p.add_argument(
        "--output_dir",
        default=str(RESULTS_DIR),
        help=f"Results directory (default: {RESULTS_DIR})",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, dict | str] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "benchmarks_run": [],
    }
    benchmarks_run: list[str] = []

    # ====================================================================
    # 1. MRR@10
    # ====================================================================
    print("\n" + "=" * 60)
    print("  [1/4]  MRR@10 Evaluation")
    print("=" * 60)
    mrr_script = str(TRAINING_DIR / "eval_mrr.py")
    if Path(mrr_script).exists():
        extra = ["--checkpoint", args.checkpoint]
        success = run_script(mrr_script, extra)
        mrr_data = load_json(out_dir / "mrr_results.json")
        if mrr_data:
            results["mrr"] = mrr_data
            benchmarks_run.append("MRR@10")
            logger.info(f"MRR@10 = {mrr_data.get('mrr_at_10', '?')}")
        elif not success:
            results["mrr"] = "FAILED"
    else:
        logger.warning(f"MRR script not found: {mrr_script}")
        results["mrr"] = "SKIPPED — script not found"

    # ====================================================================
    # 2. CodeSearchEval
    # ====================================================================
    print("\n" + "=" * 60)
    print("  [2/4]  CodeSearchEval")
    print("=" * 60)
    cse_script = str(EVAL_DIR / "eval_codesearcheval.py")
    if Path(cse_script).exists():
        success = run_script(cse_script)
        cse_data = load_json(out_dir / "codesearcheval_results.json")
        if cse_data:
            results["codesearcheval"] = {
                "precision_at_1": cse_data.get("precision_at_1"),
                "precision_at_5": cse_data.get("precision_at_5"),
                "num_queries": cse_data.get("num_queries"),
            }
            benchmarks_run.append("CodeSearchEval")
            logger.info(f"P@1 = {cse_data.get('precision_at_1', '?')}")
        elif not success:
            results["codesearcheval"] = "FAILED"
    else:
        logger.warning(f"CodeSearchEval script not found: {cse_script}")
        results["codesearcheval"] = "SKIPPED — script not found"

    # ====================================================================
    # 3. Drift Detection
    # ====================================================================
    print("\n" + "=" * 60)
    print("  [3/4]  Drift Detection")
    print("=" * 60)
    drift_script = str(EVAL_DIR / "eval_drift.py")
    if args.skip_drift:
        logger.info("Drift eval skipped (--skip_drift).")
        results["drift"] = "SKIPPED"
    elif not args.repo_path:
        logger.warning("Drift eval skipped — no --repo_path provided.")
        results["drift"] = "SKIPPED — no repo_path"
    elif Path(drift_script).exists():
        extra = ["--repo_path", args.repo_path, "--commits", "10"]
        success = run_script(drift_script, extra)
        drift_data = load_json(out_dir / "drift_results.json")
        if drift_data:
            results["drift"] = drift_data
            benchmarks_run.append("Drift")
            logger.info(f"F1 = {drift_data.get('atlas_f1', '?')}")
        elif not success:
            results["drift"] = "FAILED"
    else:
        logger.warning(f"Drift script not found: {drift_script}")
        results["drift"] = "SKIPPED — script not found"

    # ====================================================================
    # 4. SWE-Bench
    # ====================================================================
    print("\n" + "=" * 60)
    print("  [4/4]  SWE-Bench")
    print("=" * 60)
    swe_script = str(EVAL_DIR / "eval_swebench.py")
    if args.skip_swebench:
        logger.info("SWE-Bench eval skipped (--skip_swebench).")
        results["swebench"] = "SKIPPED"
    elif not args.repo_path:
        logger.warning("SWE-Bench eval skipped — no --repo_path provided.")
        results["swebench"] = "SKIPPED — no repo_path"
    elif Path(swe_script).exists():
        extra = ["--repo_path", args.repo_path, "--tasks", "50"]
        success = run_script(swe_script, extra)
        swe_data = load_json(out_dir / "swebench_results.json")
        if swe_data:
            results["swebench"] = swe_data
            benchmarks_run.append("SWE-Bench")
            logger.info(
                f"pass@1 = {swe_data.get('pass_at_1', '?')}, "
                f"pass@5 = {swe_data.get('pass_at_5', '?')}"
            )
        elif not success:
            results["swebench"] = "FAILED"
    else:
        logger.warning(f"SWE-Bench script not found: {swe_script}")
        results["swebench"] = "SKIPPED — script not found"

    # ====================================================================
    # Combined report
    # ====================================================================
    results["benchmarks_run"] = benchmarks_run

    report_path = out_dir / "benchmark_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    logger.info(f"Combined report → {report_path}")

    # ====================================================================
    # Markdown summary
    # ====================================================================
    md_lines = [
        "# Atlas Benchmark Summary",
        "",
        f"*Generated: {results['timestamp']}*",
        "",
        "| Metric | Value |",
        "|--------|-------|",
    ]

    mrr = results.get("mrr")
    if isinstance(mrr, dict):
        md_lines.append(f"| MRR@10 (Fused GATv2) | **{mrr.get('mrr_at_10', '—')}** |")
        md_lines.append(f"| Hits@1 | {mrr.get('hits_at_1', '—')} |")
        md_lines.append(f"| Hits@5 | {mrr.get('hits_at_5', '—')} |")

    cse = results.get("codesearcheval")
    if isinstance(cse, dict):
        md_lines.append(
            f"| CodeSearchEval P@1 | **{cse.get('precision_at_1', '—')}** |"
        )
        md_lines.append(f"| CodeSearchEval P@5 | {cse.get('precision_at_5', '—')} |")

    drift = results.get("drift")
    if isinstance(drift, dict):
        md_lines.append(f"| Drift Detection F1 | **{drift.get('atlas_f1', '—')}** |")

    swe = results.get("swebench")
    if isinstance(swe, dict):
        md_lines.append(f"| SWE-Bench pass@1 | **{swe.get('pass_at_1', '—')}** |")
        md_lines.append(f"| SWE-Bench pass@5 | {swe.get('pass_at_5', '—')} |")

    md_lines.append("")

    summary_path = out_dir / "benchmark_summary.md"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    logger.info(f"Markdown summary → {summary_path}")

    # ====================================================================
    # Print table
    # ====================================================================
    print("\n" + "=" * 60)
    print("  COMBINED BENCHMARK RESULTS")
    print("=" * 60)
    for line in md_lines[4:]:
        print(f"  {line}")
    print(f"\n  Benchmarks run: {', '.join(benchmarks_run) or 'none'}")
    print(f"  Report: {report_path}")
    print(f"  Summary: {summary_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
