from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from src.backend.knowledge.evidence_organizer import diversify_evidences, merge_parent_evidences, source_family
from src.backend.knowledge.fusion import reciprocal_rank_fusion
from src.backend.knowledge.hybrid_retriever import hybrid_retriever
from src.backend.knowledge.query_rewrite import QueryPlan, build_query_plan
from src.backend.knowledge.reranker import rerank_evidences
from src.backend.knowledge.types import Evidence, OrchestratedRetrievalResult, RetrievalStep


def _evidence_id(evidence: Evidence) -> str:
    locator = str(evidence.locator or "").strip()
    if locator:
        return f"{evidence.source_path}|{locator}"
    return evidence.source_path


def _dedupe_evidence_pool(evidences: list[Evidence]) -> list[Evidence]:
    deduped: dict[str, Evidence] = {}
    for evidence in evidences:
        key = _evidence_id(evidence)
        current = deduped.get(key)
        if current is None or float(evidence.score or 0.0) > float(current.score or 0.0):
            deduped[key] = evidence
    return sorted(deduped.values(), key=lambda item: float(item.score or 0.0), reverse=True)


def _final_evidence_limit(question_type: str) -> int:
    if question_type in {"multi_hop", "cross_file_aggregation"}:
        return 4
    return 3


def _has_correlated_retrieval_evidence(
    vector_evidences: list[Evidence],
    bm25_evidences: list[Evidence],
) -> bool:
    if not vector_evidences or not bm25_evidences:
        return False
    vector_sources = {source_family(item.source_path) for item in vector_evidences}
    bm25_sources = {source_family(item.source_path) for item in bm25_evidences}
    return bool(vector_sources & bm25_sources)


def _matched_entities(query_plan: QueryPlan, evidences: list[Evidence]) -> int:
    if not query_plan.entity_hints:
        return 0
    joined = "\n\n".join(
        " ".join([item.source_path, item.locator, item.snippet]) for item in evidences
    ).lower()
    return sum(1 for entity in query_plan.entity_hints if entity.lower() in joined)


def _has_negative_evidence(evidences: list[Evidence]) -> bool:
    negative_terms = ("loss", "negative", "decline", "decrease", "breach", "failed")
    for evidence in evidences:
        snippet = str(evidence.snippet or "").lower()
        if any(term in snippet for term in negative_terms):
            return True
    return False


def _determine_status(
    query_plan: QueryPlan,
    *,
    vector_evidences: list[Evidence],
    bm25_evidences: list[Evidence],
    final_evidences: list[Evidence],
) -> tuple[str, str]:
    if not final_evidences:
        return (
            "not_found",
            "The current knowledge index does not contain enough evidence for this question.",
        )

    family_count = len({source_family(item.source_path) for item in final_evidences})
    has_corroboration = _has_correlated_retrieval_evidence(vector_evidences, bm25_evidences)
    merged_child_support = max((int(item.supporting_children or 1) for item in final_evidences), default=1)
    matched_entities = _matched_entities(query_plan, final_evidences)

    if query_plan.question_type == "cross_file_aggregation":
        needed_entities = max(2, len(query_plan.entity_hints))
        if family_count >= needed_entities and matched_entities >= needed_entities:
            return (
                "success",
                "Returned diversified evidence across multiple indexed sources for cross-file aggregation.",
            )
        return (
            "partial",
            "The knowledge index found only partial cross-file coverage. Keep unsupported fields explicit.",
        )

    if query_plan.question_type == "compare":
        if family_count >= 2 and matched_entities >= min(2, len(query_plan.entity_hints) or 2):
            return (
                "success",
                "Returned diversified indexed evidence for the requested comparison.",
            )
        return (
            "partial",
            "The knowledge index found only partial comparison coverage. Keep unsupported fields explicit.",
        )

    if query_plan.question_type == "multi_hop":
        if has_corroboration and (family_count >= 2 or merged_child_support >= 3):
            return (
                "success",
                "Returned multi-part indexed evidence with corroboration across channels.",
            )
        return (
            "partial",
            "The knowledge index found only partial multi-hop evidence. Keep missing links explicit.",
        )

    if query_plan.question_type == "negation":
        if has_corroboration and _has_negative_evidence(final_evidences):
            return (
                "success",
                "Returned indexed evidence that directly supports the requested negative conclusion.",
            )
        return (
            "partial",
            "The knowledge index did not return enough direct negative evidence.",
        )

    if has_corroboration or merged_child_support >= 2:
        return (
            "success",
            "Returned evidence from the formal indexed retrieval path with corroboration across vector and BM25.",
        )
    return (
        "partial",
        "The knowledge index returned only weak or single-channel evidence.",
    )


@dataclass(frozen=True)
class RetrievalRequest:
    query: str
    top_k: int = 4
    path_filters: tuple[str, ...] = ()
    query_hints: tuple[str, ...] = ()
    chunk_types: tuple[str, ...] = ()
    rewrite_enabled: bool = True
    reranker_enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalResult:
    status: str
    evidences: list[Evidence] = field(default_factory=list)
    steps: list[RetrievalStep] = field(default_factory=list)
    fallback_used: bool = False
    reason: str = ""
    question_type: str = "direct_fact"
    entity_hints: list[str] = field(default_factory=list)
    query_variants: list[str] = field(default_factory=list)
    strategy: str = "baseline_hybrid"
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_orchestrated_result(self) -> OrchestratedRetrievalResult:
        return OrchestratedRetrievalResult(
            status=self.status,  # type: ignore[arg-type]
            evidences=list(self.evidences),
            steps=list(self.steps),
            fallback_used=self.fallback_used,
            reason=self.reason,
            question_type=self.question_type,
            entity_hints=list(self.entity_hints),
            strategy=self.strategy,
            query_variants=list(self.query_variants),
            diagnostics=dict(self.diagnostics),
        )


class RetrievalStrategy(Protocol):
    name: str

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        ...


class BaselineHybridRagStrategy:
    name = "baseline_hybrid"

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        query_plan = self._build_query_plan(request.query, rewrite_enabled=request.rewrite_enabled)
        hybrid_result = hybrid_retriever.retrieve(
            request.query,
            top_k=max(1, int(request.top_k)),
            path_filters=list(request.path_filters) or None,
            query_hints=list(request.query_hints) or None,
            query_plan=query_plan,
            chunk_types=list(request.chunk_types) or None,
        )
        steps: list[RetrievalStep] = [
            RetrievalStep(
                kind="knowledge",
                stage="indexed_retrieval",
                title="Formal knowledge retrieval",
                message=(
                    f"Strategy={self.name}; rewrite={'on' if request.rewrite_enabled else 'off'}; "
                    f"reranker={'on' if request.reranker_enabled else 'off'}; top_k={request.top_k}"
                ),
            )
        ]
        if hybrid_result.query_variants:
            steps.append(
                RetrievalStep(
                    kind="knowledge",
                    stage="query_rewrite",
                    title="Query rewrites",
                    message=" | ".join(hybrid_result.query_variants[:6]),
                )
            )
        if hybrid_result.vector_evidences:
            steps.append(
                RetrievalStep(
                    kind="knowledge",
                    stage="vector",
                    title="Vector retrieval",
                    message="Vector retrieval returned indexed evidence candidates.",
                    results=hybrid_result.vector_evidences[: max(request.top_k * 2, 8)],
                )
            )
        if hybrid_result.bm25_evidences:
            steps.append(
                RetrievalStep(
                    kind="knowledge",
                    stage="bm25",
                    title="BM25 retrieval",
                    message="BM25 retrieval returned indexed evidence candidates.",
                    results=hybrid_result.bm25_evidences[: max(request.top_k * 2, 8)],
                )
            )
        fused = reciprocal_rank_fusion(
            [hybrid_result.vector_evidences, hybrid_result.bm25_evidences],
            top_k=max(request.top_k * 4, 12),
        )
        if fused:
            steps.append(
                RetrievalStep(
                    kind="knowledge",
                    stage="fused",
                    title="Fused evidence",
                    message="Reciprocal-rank fusion merged candidates from vector and BM25 retrieval.",
                    results=fused,
                )
            )
        candidate_pool = _dedupe_evidence_pool(fused)
        reranked = (
            rerank_evidences(
                query_plan,
                candidate_pool,
                top_k=max(request.top_k * 3, 10),
                preferred_families=list(request.path_filters) or None,
            )
            if request.reranker_enabled
            else candidate_pool[: max(request.top_k * 3, 10)]
        )
        if reranked:
            steps.append(
                RetrievalStep(
                    kind="knowledge",
                    stage="rerank" if request.reranker_enabled else "rank_passthrough",
                    title="Heuristic rerank" if request.reranker_enabled else "Rank passthrough",
                    message=(
                        "Heuristic rerank prioritized entity, time, and evidence-family matches."
                        if request.reranker_enabled
                        else "Reranker disabled; fused candidates passed through in score order."
                    ),
                    results=reranked,
                )
            )
        merged = merge_parent_evidences(reranked, top_k=max(request.top_k * 3, 10))
        if merged:
            steps.append(
                RetrievalStep(
                    kind="knowledge",
                    stage="parent_merge",
                    title="Parent merge",
                    message="Sibling chunks from the same parent were merged into richer parent-level evidence.",
                    results=merged,
                )
            )
        final_limit = _final_evidence_limit(query_plan.question_type)
        diversified = diversify_evidences(
            merged,
            question_type=query_plan.question_type,
            entity_hints=query_plan.entity_hints,
            top_k=final_limit,
        )
        final_evidences = diversified or merged or reranked or candidate_pool
        if diversified:
            steps.append(
                RetrievalStep(
                    kind="knowledge",
                    stage="diversified",
                    title="Diversified evidence pick",
                    message="Final evidence selection enforced lightweight source diversification.",
                    results=diversified[:final_limit],
                )
            )
        status, reason = _determine_status(
            query_plan,
            vector_evidences=hybrid_result.vector_evidences,
            bm25_evidences=hybrid_result.bm25_evidences,
            final_evidences=final_evidences,
        )
        diagnostics = {
            "strategy": self.name,
            "query_variants": list(query_plan.query_variants),
            "retrieved_ids": [_evidence_id(item) for item in candidate_pool[: max(request.top_k * 4, 12)]],
            "rerank_scores": [
                {
                    "evidence_id": _evidence_id(item),
                    "score": float(item.score or 0.0),
                }
                for item in reranked[: max(request.top_k * 2, 8)]
            ],
            "evidence_bundle_summary": {
                "question_type": query_plan.question_type,
                "candidate_count": len(candidate_pool),
                "final_count": len(final_evidences[:final_limit]),
                "source_families": sorted({source_family(item.source_path) for item in final_evidences[:final_limit]}),
            },
        }
        return RetrievalResult(
            status=status,
            evidences=final_evidences[:final_limit],
            steps=steps,
            fallback_used=False,
            reason=reason,
            question_type=query_plan.question_type,
            entity_hints=list(query_plan.entity_hints),
            query_variants=list(query_plan.query_variants),
            strategy=self.name,
            diagnostics=diagnostics,
        )

    def _build_query_plan(self, query: str, *, rewrite_enabled: bool) -> QueryPlan:
        plan = build_query_plan(query, prefer_llm=rewrite_enabled)
        if rewrite_enabled:
            return plan
        return QueryPlan(
            original_query=plan.original_query,
            question_type=plan.question_type,
            query_variants=[plan.original_query],
            entity_hints=list(plan.entity_hints),
            keyword_hints=list(plan.keyword_hints),
            rewrite_needed=False,
            planner_reason="rewrite disabled for baseline_hybrid",
            planner_source=plan.planner_source,
        )


__all__ = [
    "BaselineHybridRagStrategy",
    "RetrievalRequest",
    "RetrievalResult",
    "RetrievalStrategy",
]
