from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

from src.backend.domains.rfp_security.exports import build_section_level_draft
from src.backend.domains.rfp_security.normalizers import normalize_rfp_security_query
from src.backend.domains.rfp_security.policies import evaluate_policy_decision
from src.backend.knowledge.indexer import knowledge_indexer
from src.backend.knowledge.retrieval_registry import get_retrieval_strategy
from src.backend.knowledge.retrieval_strategy import RetrievalRequest
from src.backend.runtime.config import get_settings

try:
    from .case_loader import BenchmarkSelection, load_cases
    from .evaluator import evaluate_case, summarize_results
except ImportError:  # pragma: no cover - fallback for running inside backend cwd
    from benchmarks.case_loader import BenchmarkSelection, load_cases
    from benchmarks.evaluator import evaluate_case, summarize_results


_INDEX_LOCK = threading.Lock()
_INDEX_READY = False


def _supports_embeddings() -> bool:
    settings = get_settings()
    return settings.embedding_provider == "local" or bool(settings.embedding_api_key)


def _indexed_source_types() -> set[str]:
    counts = dict(knowledge_indexer.build_stats().get("source_type_counts", {}) or {})
    return {str(key).strip().lower() for key in counts if str(key).strip()}


def ensure_index_ready() -> tuple[dict[str, Any], set[str]]:
    global _INDEX_READY
    with _INDEX_LOCK:
        settings = get_settings()
        knowledge_indexer.configure(settings.project_root)
        if not _INDEX_READY or not knowledge_indexer.status().ready:
            knowledge_indexer.rebuild_index(build_vector=_supports_embeddings())
            _INDEX_READY = True
        return knowledge_indexer.status().to_dict(), _indexed_source_types()


def _build_trace(answer: str, retrieval_evidences, final_evidences, steps) -> dict[str, Any]:
    retrieval_sources = [item.source_path for item in retrieval_evidences]
    return {
        "detected_route": "knowledge",
        "called_tools": [],
        "retrieval_sources": retrieval_sources,
        "knowledge_used": True,
        "final_answer": answer,
        "error_message": "",
        "trace_completeness": bool(answer or retrieval_evidences),
        "final_evidence_results": [item.to_dict() for item in final_evidences],
        "retrieval_steps": [item.to_dict() for item in steps],
        "usage": {},
    }


def _planning_evidence_pool(retrieval) -> list[Any]:
    combined: list[Any] = list(retrieval.evidences)
    seen: set[str] = set()

    def remember(items) -> None:
        for evidence in items:
            locator = str(getattr(evidence, "locator", "") or "").strip()
            evidence_id = f"{evidence.source_path}|{locator}" if locator else str(evidence.source_path)
            if evidence_id in seen:
                continue
            seen.add(evidence_id)
            combined.append(evidence)

    remember(retrieval.evidences)
    for stage_name in ("parent_merge", "rerank", "fused", "vector", "bm25"):
        for step in retrieval.steps:
            if getattr(step, "stage", "") == stage_name and getattr(step, "results", None):
                remember(step.results)
    return combined


def run_rfp_security_suite(
    *,
    limit: int | None = None,
    strategy_name: str = "baseline_hybrid",
    rewrite_enabled: bool = True,
    reranker_enabled: bool = True,
    top_k: int = 5,
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc).isoformat()
    selection = BenchmarkSelection(module="rag", rag_subtype="rfp_security")
    cases = load_cases(selection)
    if limit is not None:
        cases = cases[:limit]
    index_status, indexed_types = ensure_index_ready()
    strategy = get_retrieval_strategy(strategy_name)
    results: list[dict[str, Any]] = []

    for case in cases:
        started = time.perf_counter()
        query = str(case.get("query") or case.get("input") or "")
        normalized = normalize_rfp_security_query(
            query,
            tags=list(case.get("tags", []) or []),
            risk_level=str(case.get("risk_level", "medium") or "medium"),
            required_points=list(case.get("gold_required_points", []) or case.get("must_include", []) or []),
        )
        retrieval = strategy.retrieve(
            RetrievalRequest(
                query=normalized.normalized_query,
                top_k=max(1, int(top_k or 5)),
                query_hints=normalized.search_terms,
                rewrite_enabled=bool(rewrite_enabled),
                reranker_enabled=bool(reranker_enabled),
                metadata={
                    "case_id": case.get("id", ""),
                    "tags": list(normalized.tags),
                    "risk_level": normalized.risk_level,
                },
            )
        )
        planning_evidences = _planning_evidence_pool(retrieval)
        policy = evaluate_policy_decision(normalized, planning_evidences)
        draft = build_section_level_draft(normalized, planning_evidences, policy)
        selected_evidence_ids = set(draft.selected_evidence_ids)
        selected_evidences = [
            evidence for evidence in planning_evidences
            if selected_evidence_ids and (
                (f"{evidence.source_path}|{str(evidence.locator or '').strip()}" in selected_evidence_ids)
                or (evidence.source_path in selected_evidence_ids)
            )
        ]
        trace = _build_trace(draft.answer, retrieval.evidences, selected_evidences, retrieval.steps)
        evaluated = evaluate_case(case, trace, indexed_types)
        evaluated["latency_ms"] = int((time.perf_counter() - started) * 1000)
        evaluated["strategy"] = retrieval.strategy
        evaluated["query_variants"] = list(retrieval.query_variants)
        evaluated["retrieved_ids"] = list(retrieval.diagnostics.get("retrieved_ids", []))
        evaluated["rerank_scores"] = list(retrieval.diagnostics.get("rerank_scores", []))
        evaluated["evidence_bundle_summary"] = dict(retrieval.diagnostics.get("evidence_bundle_summary", {}) or {})
        evaluated["risk_level"] = normalized.risk_level
        evaluated["gold_evidence_ids"] = list(case.get("gold_evidence_ids", []) or [])
        evaluated["gold_required_points"] = list(case.get("gold_required_points", []) or [])
        evaluated["draft"] = draft.to_dict()
        evaluated["policy"] = policy.to_dict()
        evaluated["groundedness"] = draft.groundedness
        evaluated["relevance"] = draft.relevance
        evaluated["response_completeness"] = draft.response_completeness
        evaluated["unsupported_claim_rate"] = draft.unsupported_claim_rate
        evaluated["judge"] = {
            "requested": False,
            "configured": False,
            "skipped": True,
            "skip_reason": "rfp_security suite uses deterministic scoring by default",
        }
        evaluated["trace"] = {
            "detected_route": trace["detected_route"],
            "called_tools": trace["called_tools"],
            "retrieval_sources": trace["retrieval_sources"],
            "final_answer": trace["final_answer"],
            "error_message": trace["error_message"],
            "trace_completeness": trace["trace_completeness"],
            "usage": trace["usage"],
        }
        results.append(evaluated)

    summary = summarize_results(results)
    summary["groundedness"] = round(
        sum(float(item.get("groundedness", 0.0) or 0.0) for item in results) / len(results),
        4,
    ) if results else 0.0
    summary["relevance"] = round(
        sum(float(item.get("relevance", 0.0) or 0.0) for item in results) / len(results),
        4,
    ) if results else 0.0
    summary["response_completeness"] = round(
        sum(float(item.get("response_completeness", 0.0) or 0.0) for item in results) / len(results),
        4,
    ) if results else 0.0
    summary["unsupported_claim_rate"] = round(
        sum(float(item.get("unsupported_claim_rate", 0.0) or 0.0) for item in results) / len(results),
        4,
    ) if results else 0.0

    return {
        "status": "completed",
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "benchmark_family": "rag",
        "selection": {
            "module": "rag",
            "rag_subtype": "rfp_security",
            "suite": "rfp_security",
        },
        "strategy_config": {
            "strategy": strategy_name,
            "rewrite_enabled": bool(rewrite_enabled),
            "reranker_enabled": bool(reranker_enabled),
            "top_k": int(top_k or 5),
        },
        "knowledge_index_status": index_status,
        "indexed_source_types": sorted(indexed_types),
        "judge": {
            "configured": False,
            "mode": "off",
            "rubric": "deterministic_rfp_security",
        },
        "summary": summary,
        "cases": results,
    }


__all__ = ["ensure_index_ready", "run_rfp_security_suite"]
