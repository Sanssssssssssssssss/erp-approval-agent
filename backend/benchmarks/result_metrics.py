from __future__ import annotations

import math
from collections import defaultdict
from typing import Any


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return round(values[0], 2)
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[int(position)], 2)
    weight = position - lower
    return round((ordered[lower] * (1 - weight)) + (ordered[upper] * weight), 2)


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _safe_bool_rate(items: list[bool]) -> float | None:
    if not items:
        return None
    return round(sum(1 for item in items if item) / len(items), 4)


def payload_family(payload: dict[str, Any]) -> str:
    cases = list(payload.get("cases", []) or [])
    if not cases:
        return "unknown"
    first = dict(cases[0] or {})
    if "overall_pass" in first or "question_type" in first and "trace" in first:
        return "rag"
    return "harness"


def flatten_case_metrics(payload: dict[str, Any]) -> list[dict[str, Any]]:
    family = payload_family(payload)
    payload_judge = dict(payload.get("judge", {}) or {})
    flattened: list[dict[str, Any]] = []
    for case in list(payload.get("cases", []) or []):
        item = dict(case or {})
        if family == "rag":
            judge = dict(item.get("judge", {}) or {})
            audit = dict(judge.get("audit", {}) or {})
            trace = dict(item.get("trace", {}) or {})
            usage = dict(trace.get("usage", {}) or {})
            sub_scores = dict(judge.get("sub_scores", {}) or {})
            judge_error = str(judge.get("error", "") or "")
            if judge_error == "judge_unavailable" and not payload_judge.get("enabled", False):
                judge_error = ""
            flattened.append(
                {
                    "family": family,
                    "suite": str(payload.get("selection", {}).get("rag_subtype") or payload.get("selection", {}).get("module") or ""),
                    "scenario": str(item.get("question_type", "") or item.get("subtype", "") or item.get("id", "")),
                    "route": str(item.get("detected_route", "") or trace.get("detected_route", "") or ""),
                    "strategy": str(item.get("strategy", payload.get("strategy_config", {}).get("strategy", "")) or ""),
                    "tool": ",".join(str(tool) for tool in item.get("called_tools", []) or trace.get("called_tools", []) or []),
                    "modality": ",".join(str(modality) for modality in item.get("modalities", []) or []),
                    "status": "passed" if bool(item.get("overall_pass")) else "failed",
                    "trace_completeness": bool(item.get("trace_completeness", item.get("overall_pass"))),
                    "judge_score": float(judge.get("score", 0.0) or 0.0) if not judge.get("skipped") else None,
                    "judge_passed": bool(judge.get("passed", judge.get("pass", False))) if not judge.get("skipped") else None,
                    "judge_error": judge_error,
                    "latency_ms": float(item.get("latency_ms", 0) or 0) if item.get("latency_ms") is not None else None,
                    "total_tokens": float(usage.get("total_tokens", 0) or 0) if usage.get("total_tokens") is not None else None,
                    "cost_usd": float(usage.get("cost_usd", 0) or 0) if usage.get("cost_usd") is not None else None,
                    "groundedness_score": float(sub_scores["groundedness"]) if not judge.get("skipped") and "groundedness" in sub_scores else None,
                    "answer_correctness_score": float(sub_scores["answer_correctness"]) if not judge.get("skipped") and "answer_correctness" in sub_scores else None,
                    "citation_support_score": float(sub_scores["citation_support"]) if not judge.get("skipped") and "citation_support" in sub_scores else None,
                    "audit_latency_ms": float(audit.get("latency_ms", 0) or 0) if audit.get("latency_ms") is not None else None,
                    "retrieval_hit_at_k": bool(item.get("retrieval_hit_at_k")) if item.get("retrieval_hit_at_k") is not None else None,
                    "retrieval_recall_at_k": float(item.get("retrieval_recall_at_k", 0.0) or 0.0) if item.get("retrieval_recall_at_k") is not None else None,
                    "evidence_coverage": float(item.get("evidence_coverage", 0.0) or 0.0) if item.get("evidence_coverage") is not None else None,
                    "citation_precision": float(item.get("citation_precision", 0.0) or 0.0) if item.get("citation_precision") is not None else None,
                    "citation_recall": float(item.get("citation_recall", 0.0) or 0.0) if item.get("citation_recall") is not None else None,
                    "groundedness": float(item.get("groundedness", 0.0) or 0.0) if item.get("groundedness") is not None else None,
                    "relevance": float(item.get("relevance", 0.0) or 0.0) if item.get("relevance") is not None else None,
                    "response_completeness": float(item.get("response_completeness", 0.0) or 0.0) if item.get("response_completeness") is not None else None,
                    "unsupported_claim_rate": float(item.get("unsupported_claim_rate", 0.0) or 0.0) if item.get("unsupported_claim_rate") is not None else None,
                }
            )
        else:
            llm_judge = dict(item.get("llm_judge_result", {}) or {})
            audit = dict(llm_judge.get("audit", {}) or {})
            usage = dict(item.get("usage", {}) or {})
            sub_scores = dict(llm_judge.get("sub_scores", {}) or {})
            judge_error = str(item.get("llm_judge_error", "") or llm_judge.get("error", "") or "")
            judge_requested = bool(payload_judge.get("llm_available", False)) or any(
                item.get(field) not in (None, "", {}, [])
                for field in ("llm_judge_score", "llm_judge_passed", "llm_judge_audit")
            )
            if judge_error == "judge_unavailable" and not judge_requested:
                judge_error = ""
            flattened.append(
                {
                    "family": family,
                    "suite": str(item.get("suite", "") or ""),
                    "scenario": str(item.get("scenario", "") or item.get("case_id", "")),
                    "route": str(item.get("outcome", {}).get("route_intent", "") or ""),
                    "tool": ",".join(str(tool) for tool in item.get("outcome", {}).get("tool_names", []) or []),
                    "modality": ",".join(str(tag) for tag in item.get("tags", []) or []),
                    "status": str(item.get("status", "") or "failed"),
                    "trace_completeness": bool(item.get("trace_completeness")),
                    "judge_score": float(item.get("llm_judge_score", 0.0) or 0.0) if item.get("llm_judge_score") is not None else None,
                    "judge_passed": item.get("llm_judge_passed"),
                    "judge_error": judge_error,
                    "latency_ms": float(item.get("latency_ms", 0) or 0) if item.get("latency_ms") is not None else None,
                    "total_tokens": float(usage.get("total_tokens", 0) or 0) if usage.get("total_tokens") is not None else None,
                    "cost_usd": float(usage.get("cost_usd", 0) or 0) if usage.get("cost_usd") is not None else None,
                    "groundedness_score": float(sub_scores["groundedness"]) if "groundedness" in sub_scores else None,
                    "answer_correctness_score": float(sub_scores["answer_correctness"]) if "answer_correctness" in sub_scores else None,
                    "citation_support_score": float(sub_scores["citation_support"]) if "citation_support" in sub_scores else None,
                    "audit_latency_ms": float(audit.get("latency_ms", 0) or 0) if audit.get("latency_ms") is not None else None,
                }
            )
    return flattened


def summarize_case_metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [float(item["latency_ms"]) for item in items if item.get("latency_ms") is not None]
    judge_scores = [float(item["judge_score"]) for item in items if item.get("judge_score") is not None]
    tokens = [float(item["total_tokens"]) for item in items if item.get("total_tokens") is not None and item.get("total_tokens") > 0]
    costs = [float(item["cost_usd"]) for item in items if item.get("cost_usd") is not None and item.get("cost_usd") > 0]
    groundedness = [float(item["groundedness_score"]) for item in items if item.get("groundedness_score") is not None]
    correctness = [float(item["answer_correctness_score"]) for item in items if item.get("answer_correctness_score") is not None]
    citation_support = [float(item["citation_support_score"]) for item in items if item.get("citation_support_score") is not None]
    retrieval_hits = [bool(item["retrieval_hit_at_k"]) for item in items if item.get("retrieval_hit_at_k") is not None]
    retrieval_recalls = [float(item["retrieval_recall_at_k"]) for item in items if item.get("retrieval_recall_at_k") is not None]
    evidence_coverages = [float(item["evidence_coverage"]) for item in items if item.get("evidence_coverage") is not None]
    citation_precisions = [float(item["citation_precision"]) for item in items if item.get("citation_precision") is not None]
    citation_recalls = [float(item["citation_recall"]) for item in items if item.get("citation_recall") is not None]
    groundedness_proxies = [float(item["groundedness"]) for item in items if item.get("groundedness") is not None]
    relevance = [float(item["relevance"]) for item in items if item.get("relevance") is not None]
    completeness = [float(item["response_completeness"]) for item in items if item.get("response_completeness") is not None]
    unsupported_rates = [float(item["unsupported_claim_rate"]) for item in items if item.get("unsupported_claim_rate") is not None]
    trace_completeness = [bool(item["trace_completeness"]) for item in items if item.get("trace_completeness") is not None]
    judge_passed = [bool(item["judge_passed"]) for item in items if item.get("judge_passed") is not None]
    errors = [item for item in items if str(item.get("judge_error", "") or "").strip()]

    breakdown: dict[str, dict[str, dict[str, Any]]] = {}
    for dimension in ("suite", "scenario", "route", "tool", "modality", "family"):
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in items:
            key = str(item.get(dimension, "") or "unknown")
            grouped[key].append(item)
        breakdown[dimension] = {
            key: {
                "count": len(group_items),
                "pass_rate": _safe_bool_rate([group_item.get("status") == "passed" for group_item in group_items]),
                "mean_judge_score": _avg([float(group_item["judge_score"]) for group_item in group_items if group_item.get("judge_score") is not None]),
            }
            for key, group_items in sorted(grouped.items())
        }

    return {
        "total_cases": len(items),
        "pass_rate": _safe_bool_rate([item.get("status") == "passed" for item in items]),
        "judge_pass_rate": _safe_bool_rate(judge_passed),
        "judge_score_mean": _avg(judge_scores),
        "judge_score_p50": _percentile(judge_scores, 0.5),
        "judge_score_p95": _percentile(judge_scores, 0.95),
        "latency_ms_p50": _percentile(latencies, 0.5),
        "latency_ms_p95": _percentile(latencies, 0.95),
        "latency_ms_mean": _avg(latencies),
        "avg_total_tokens": _avg(tokens),
        "avg_cost_usd": _avg(costs),
        "error_rate": round(len(errors) / len(items), 4) if items else 0.0,
        "trace_completeness": _safe_bool_rate(trace_completeness),
        "groundedness_score_mean": _avg(groundedness),
        "answer_correctness_score_mean": _avg(correctness),
        "citation_support_score_mean": _avg(citation_support),
        "retrieval_hit_at_k": _safe_bool_rate(retrieval_hits),
        "retrieval_recall_at_k": _avg(retrieval_recalls),
        "evidence_coverage": _avg(evidence_coverages),
        "citation_precision": _avg(citation_precisions),
        "citation_recall": _avg(citation_recalls),
        "groundedness": _avg(groundedness_proxies),
        "relevance": _avg(relevance),
        "response_completeness": _avg(completeness),
        "unsupported_claim_rate": _avg(unsupported_rates),
        "scenario_breakdown": breakdown,
    }


__all__ = ["flatten_case_metrics", "payload_family", "summarize_case_metrics"]
