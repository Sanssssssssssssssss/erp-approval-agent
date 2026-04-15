from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from benchmarks.execution_metadata import attach_execution_metadata
from benchmarks.rfp_security_suite import run_rfp_security_suite
from benchmarks.result_metrics import flatten_case_metrics, summarize_case_metrics
from benchmarks.storage_layout import harness_output_path


DEFAULT_OUTPUT_PATH = harness_output_path()
RAG_SUITES = {"retrieval", "grounding", "rfp_security"}
HARNESS_SUITES = {"contract", "integration", "hard", "rewrite", "scalable", "all"}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the unified harness + RAG benchmark suites.")
    parser.add_argument("--suite", choices=tuple(sorted(HARNESS_SUITES | RAG_SUITES)), default="contract")
    parser.add_argument("--case-file", action="append", default=[], help="Additional case file to load for harness suites.")
    parser.add_argument("--tag", default=None, help="Only run cases containing one tag for harness suites.")
    parser.add_argument("--limit", type=int, default=None, help="Limit loaded cases after filtering.")
    parser.add_argument("--deterministic-only", action="store_true", help="Disable the model-based benchmark judge for harness suites.")
    parser.add_argument("--stub-decisions", action="store_true", help="Use benchmark stub routing/rewrite decisions instead of live LLM decisions where supported.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8015", help="Backend base URL for live RAG suites.")
    parser.add_argument("--pressure-concurrency", type=int, default=1, help="Concurrent benchmark invocations for pressure mode.")
    parser.add_argument("--pressure-rounds", type=int, default=1, help="How many rounds to repeat in pressure mode.")
    parser.add_argument("--pressure-matrix", action="store_true", help="Run the built-in pressure matrix for the rfp_security suite.")
    parser.add_argument("--strategy", default="baseline_hybrid", help="Retrieval strategy name for the rfp_security suite.")
    parser.add_argument("--rewrite-mode", choices=("on", "off"), default="on", help="Enable or disable query rewrite for the rfp_security suite.")
    parser.add_argument("--reranker-mode", choices=("on", "off"), default="on", help="Enable or disable reranker for the rfp_security suite.")
    parser.add_argument("--retrieval-top-k", type=int, default=5, help="Top-k evidence count for the rfp_security suite.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="JSON output path.")
    return parser.parse_args(argv)


def _write_payload(path: Path, payload: dict[str, Any], *, config: dict[str, Any]) -> dict[str, Any]:
    enriched = attach_execution_metadata(payload, config=config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")
    return enriched


async def _run_harness_suite(
    *,
    suite: str,
    case_files: list[str] | None,
    tag: str | None,
    limit: int | None,
    use_live_llm_decisions: bool,
    deterministic_only: bool,
) -> dict[str, Any]:
    from benchmarks.harness_benchmark_lib import run_selected_benchmark

    payload = await run_selected_benchmark(
        suite=suite,
        extra_case_files=case_files,
        tag=tag,
        limit=limit,
        output_path=None,
        use_llm_judge=not deterministic_only,
        use_live_llm_decisions=use_live_llm_decisions,
    )
    payload["benchmark_family"] = "harness"
    return payload


def _run_rag_suite_sync(
    *,
    suite: str,
    base_url: str,
) -> dict[str, Any]:
    from benchmarks.case_loader import BenchmarkSelection
    from benchmarks.runner import BenchmarkRunner

    runner = BenchmarkRunner(
        base_url,
        selection=BenchmarkSelection(module="rag", rag_subtype=suite),
        case_delay_seconds=0.0,
    )
    try:
        payload = runner.run()
    finally:
        runner.close()
    return payload


async def _run_rag_suite(
    *,
    suite: str,
    base_url: str,
) -> dict[str, Any]:
    payload = await asyncio.to_thread(
        _run_rag_suite_sync,
        suite=suite,
        base_url=base_url,
    )
    payload["benchmark_family"] = "rag"
    return payload


def _run_rfp_security_suite_sync(
    *,
    limit: int | None,
    strategy: str,
    rewrite_mode: str,
    reranker_mode: str,
    retrieval_top_k: int,
) -> dict[str, Any]:
    payload = run_rfp_security_suite(
        limit=limit,
        strategy_name=strategy,
        rewrite_enabled=rewrite_mode == "on",
        reranker_enabled=reranker_mode == "on",
        top_k=max(1, int(retrieval_top_k)),
    )
    payload["benchmark_family"] = "rag"
    return payload


async def _run_rfp_security_suite(
    *,
    limit: int | None,
    strategy: str,
    rewrite_mode: str,
    reranker_mode: str,
    retrieval_top_k: int,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        _run_rfp_security_suite_sync,
        limit=limit,
        strategy=strategy,
        rewrite_mode=rewrite_mode,
        reranker_mode=reranker_mode,
        retrieval_top_k=retrieval_top_k,
    )


async def _run_single_payload(
    *,
    suite: str,
    case_files: list[str] | None,
    tag: str | None,
    limit: int | None,
    deterministic_only: bool,
    use_live_llm_decisions: bool,
    base_url: str,
    strategy: str,
    rewrite_mode: str,
    reranker_mode: str,
    retrieval_top_k: int,
) -> dict[str, Any]:
    if suite == "rfp_security":
        return await _run_rfp_security_suite(
            limit=limit,
            strategy=strategy,
            rewrite_mode=rewrite_mode,
            reranker_mode=reranker_mode,
            retrieval_top_k=retrieval_top_k,
        )
    if suite in RAG_SUITES:
        return await _run_rag_suite(
            suite=suite,
            base_url=base_url,
        )
    return await _run_harness_suite(
        suite=suite,
        case_files=case_files,
        tag=tag,
        limit=limit,
        use_live_llm_decisions=use_live_llm_decisions,
        deterministic_only=deterministic_only,
    )


async def _run_rfp_pressure_matrix_payload(
    *,
    suite: str,
    limit: int | None,
    pressure_rounds: int,
    strategy: str,
) -> dict[str, Any]:
    flattened: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    started_at = datetime.now(timezone.utc).isoformat()
    for concurrency in (1, 2, 4, 8):
        for rewrite_mode in ("on", "off"):
            for reranker_mode in ("on", "off"):
                for retrieval_top_k in (5, 10):
                    tasks = [
                        asyncio.to_thread(
                            _run_rfp_security_suite_sync,
                            limit=limit,
                            strategy=strategy,
                            rewrite_mode=rewrite_mode,
                            reranker_mode=reranker_mode,
                            retrieval_top_k=retrieval_top_k,
                        )
                        for _ in range(max(1, concurrency) * max(1, pressure_rounds))
                    ]
                    payloads = await asyncio.gather(*tasks)
                    case_metrics: list[dict[str, Any]] = []
                    for payload in payloads:
                        case_metrics.extend(flatten_case_metrics(payload))
                    for item in case_metrics:
                        item["strategy"] = strategy
                        item["pressure_concurrency"] = concurrency
                        item["rewrite_mode"] = rewrite_mode
                        item["reranker_mode"] = reranker_mode
                        item["retrieval_top_k"] = retrieval_top_k
                    flattened.extend(case_metrics)
                    runs.append(
                        {
                            "strategy": strategy,
                            "pressure_concurrency": concurrency,
                            "rewrite_mode": rewrite_mode,
                            "reranker_mode": reranker_mode,
                            "retrieval_top_k": retrieval_top_k,
                            "summary": summarize_case_metrics(case_metrics),
                            "status": "completed",
                            "invocations": len(payloads),
                        }
                    )
    return {
        "status": "completed",
        "mode": "pressure_matrix",
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "selection": {
            "suite": suite,
            "limit": limit,
            "strategy": strategy,
            "pressure_rounds": pressure_rounds,
        },
        "summary": summarize_case_metrics(flattened),
        "cases": flattened,
        "runs": runs,
    }


async def run_benchmark(
    output_path: Path,
    *,
    suite: str = "contract",
    case_files: list[str] | None = None,
    tag: str | None = None,
    limit: int | None = None,
    deterministic_only: bool = False,
    use_live_llm_decisions: bool = True,
    base_url: str = "http://127.0.0.1:8015",
    pressure_concurrency: int = 1,
    pressure_rounds: int = 1,
    pressure_matrix: bool = False,
    strategy: str = "baseline_hybrid",
    rewrite_mode: str = "on",
    reranker_mode: str = "on",
    retrieval_top_k: int = 5,
    use_llm_judge: bool | None = None,
) -> dict[str, Any]:
    if use_llm_judge is not None:
        judge_mode = "llm" if use_llm_judge else "off"
    config = {
        "suite": suite,
        "tag": tag,
        "limit": limit,
        "deterministic_only": deterministic_only,
        "use_live_llm_decisions": use_live_llm_decisions,
        "extra_case_files": list(case_files or []),
        "base_url": base_url,
        "pressure_concurrency": pressure_concurrency,
        "pressure_rounds": pressure_rounds,
        "pressure_matrix": pressure_matrix,
        "strategy": strategy,
        "rewrite_mode": rewrite_mode,
        "reranker_mode": reranker_mode,
        "retrieval_top_k": retrieval_top_k,
    }
    if pressure_matrix:
        if suite != "rfp_security":
            raise SystemExit("--pressure-matrix is only supported for the rfp_security suite")
        payload = await _run_rfp_pressure_matrix_payload(
            suite=suite,
            limit=limit,
            pressure_rounds=pressure_rounds,
            strategy=strategy,
        )
        return _write_payload(output_path, payload, config=config)

    payload = await _run_single_payload(
        suite=suite,
        case_files=case_files,
        tag=tag,
        limit=limit,
        deterministic_only=deterministic_only,
        use_live_llm_decisions=use_live_llm_decisions,
        base_url=base_url,
        strategy=strategy,
        rewrite_mode=rewrite_mode,
        reranker_mode=reranker_mode,
        retrieval_top_k=retrieval_top_k,
    )
    return _write_payload(output_path, payload, config=config)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    payload = asyncio.run(
        run_benchmark(
            Path(args.output),
            suite=args.suite,
            case_files=list(args.case_file or []),
            tag=args.tag,
            limit=args.limit,
            deterministic_only=bool(args.deterministic_only),
            use_live_llm_decisions=not args.stub_decisions,
            base_url=args.base_url,
            pressure_concurrency=max(1, int(args.pressure_concurrency)),
            pressure_rounds=max(1, int(args.pressure_rounds)),
            pressure_matrix=bool(args.pressure_matrix),
            strategy=str(args.strategy or "baseline_hybrid"),
            rewrite_mode=str(args.rewrite_mode or "on"),
            reranker_mode=str(args.reranker_mode or "on"),
            retrieval_top_k=max(1, int(args.retrieval_top_k)),
        )
    )
    print(args.output)
    print(json.dumps(payload.get("summary", {}), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
