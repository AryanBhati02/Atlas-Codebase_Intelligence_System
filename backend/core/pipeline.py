import asyncio
import gc
import json
import logging
import time
from pathlib import Path

from config import ANALYSIS_TIMEOUT_SECONDS

logger = logging.getLogger("codebase-intel.pipeline")

class PipelineError(Exception):

    def __init__(self, message: str, error_code: str):
        super().__init__(message)
        self.error_code = error_code

async def run_analysis_pipeline(session_id: str, session_dir: Path) -> None:
    from core.session_progress import progress_store

    start = time.monotonic()
    log = logging.getLogger(f"codebase-intel.pipeline.{session_id[:8]}")

    def _elapsed() -> float:
        return time.monotonic() - start

    def _check_timeout() -> None:
        if _elapsed() > ANALYSIS_TIMEOUT_SECONDS:
            raise TimeoutError(
                f"Analysis timed out after {_elapsed():.0f}s "
                f"(limit: {ANALYSIS_TIMEOUT_SECONDS}s). "
                "Try a smaller repository or increase ANALYSIS_TIMEOUT_SECONDS."
            )

    repo_dir = session_dir / "repo"

    repo_is_empty = not repo_dir.exists() or not any(repo_dir.iterdir())
    if repo_is_empty:
        raise PipelineError(
            f"Repository directory not found or is empty for session {session_id}. "
            "Ensure ingestion completed successfully before starting analysis.",
            error_code="REPO_NOT_FOUND",
        )

    entries_path = session_dir / "file_entries.json"
    if not entries_path.exists():
        progress_store.update_sync(session_id, status="scanning")
        log.info(f"Scanning repository directory")
        from core.ingest.file_filter import scan_directory
                                                                                    
        file_entries = await asyncio.to_thread(scan_directory, repo_dir)
        entries_data = [e.model_dump() for e in file_entries]
        await asyncio.to_thread(
            entries_path.write_text,
            json.dumps(entries_data),
            "utf-8",
        )
    else:
        entries_data = json.loads(entries_path.read_text(encoding="utf-8"))

    total = len(entries_data)
    log.info(f"Pipeline starting for {total} files")
    progress_store.update_sync(session_id, status="parsing", total_files=total, parsed_files=0)

    _check_timeout()
    from core.parser.parser_service import parse_all_files_async

    def _on_progress(current: int, total_: int) -> None:
        progress_store.update_sync(session_id, parsed_files=current, total_files=total_)

    parsed = await parse_all_files_async(repo_dir, entries_data, progress_callback=_on_progress)
    _check_timeout()

    progress_store.update_sync(session_id, status="scoring")
    from core.scoring.complexity_scorer import score_files
    parsed = await asyncio.to_thread(score_files, parsed)
    _check_timeout()

    progress_store.update_sync(session_id, status="graph")
    from core.graph.graph_builder import build_graph
    graph_data = await asyncio.to_thread(build_graph, parsed)
    _check_timeout()

    progress_store.update_sync(session_id, status="saving")

    parsed_json = await asyncio.to_thread(json.dumps, parsed)
    graph_json = await asyncio.to_thread(json.dumps, graph_data)

    await asyncio.to_thread(
        (session_dir / "parsed.json").write_text, parsed_json, "utf-8"
    )
    await asyncio.to_thread(
        (session_dir / "graph.json").write_text, graph_json, "utf-8"
    )

    parsed_count = len(parsed)
    
    del parsed, parsed_json, graph_data, graph_json
    gc.collect()

    _check_timeout()
    
    function_count = 0
    try:
        progress_store.update_sync(session_id, status="function_graph")
        log.info("Building function-level call graph…")

        from core.parser.tree_sitter_parser import TreeSitterParser
        from core.parser.call_graph_builder import build_call_graph, graph_to_json, graph_to_pyg_data
        from core.tracer.fusion_engine import FusionEngine
        from core.tracer.git_coedits import GitCoEditExtractor

        ts_parser = TreeSitterParser()
        fn_nodes = await asyncio.to_thread(
            ts_parser.parse_repository, str(repo_dir)
        )
        function_count = len(fn_nodes)
        progress_store.update_sync(session_id, function_count=function_count)
        log.info(f"tree-sitter parsed {function_count} function nodes.")

        fn_graph = await asyncio.to_thread(build_call_graph, fn_nodes)

        coedit_data = {}
        if (repo_dir / ".git").exists():
            try:
                extractor = GitCoEditExtractor(str(repo_dir))
                coedit_data = await asyncio.to_thread(
                    extractor.get_function_coedits, fn_nodes
                )
                log.info(f"Git co-edit pairs computed: {len(coedit_data)}")
            except Exception as coedit_exc:
                log.warning(f"Git co-edit extraction failed; continuing with static graph: {coedit_exc}")
        else:
            log.info("No .git directory found; fusion will use static graph only.")

        fn_graph = await asyncio.to_thread(
            FusionEngine().fuse, fn_graph, coedit_data
        )

        fn_graph_json = await asyncio.to_thread(
            lambda: json.dumps(graph_to_json(fn_graph), ensure_ascii=False)
        )
        await asyncio.to_thread(
            (session_dir / "function_graph.json").write_text, fn_graph_json, "utf-8"
        )
        del fn_graph_json

        fn_pyg_json = await asyncio.to_thread(
            lambda: json.dumps(graph_to_pyg_data(fn_graph), ensure_ascii=False)
        )
        await asyncio.to_thread(
            (session_dir / "function_graph_pyg.json").write_text, fn_pyg_json, "utf-8"
        )
        del fn_pyg_json

        log.info(
            f"Function call graph saved: {fn_graph.number_of_nodes()} nodes, "
            f"{fn_graph.number_of_edges()} edges."
        )
    except Exception as fn_exc:
        
        log.warning(f"Function-level call graph stage failed (non-fatal): {fn_exc}", exc_info=True)

    elapsed = _elapsed()
    log.info(f"Pipeline complete: {parsed_count} files, {function_count} functions in {elapsed:.1f}s")

    progress_store.update_sync(
        session_id,
        status="done",
        parsed_files=(parsed_count),
        total_files=total,
        function_count=function_count,
    )
