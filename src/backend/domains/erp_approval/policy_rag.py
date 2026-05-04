from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.backend.domains.erp_approval.case_state_models import ApprovalCaseState, CASE_HARNESS_NON_ACTION_STATEMENT
from src.backend.knowledge import knowledge_indexer
from src.backend.knowledge.retrieval_strategy import BaselineHybridRagStrategy, RetrievalRequest
from src.backend.knowledge.types import Evidence


POLICY_RAG_PATH_FILTER = "knowledge/ERP Approval"


@dataclass
class PolicyRagPlan:
    need_rag: bool = True
    rewritten_queries: list[str] = field(default_factory=list)
    query_hints: list[str] = field(default_factory=list)
    reason: str = "llm policy RAG plan required"
    planner_used: bool = False
    planner_status: str = "model_required"
    planner_error: str = ""
    non_action_statement: str = CASE_HARNESS_NON_ACTION_STATEMENT

    def to_dict(self) -> dict[str, Any]:
        return {
            "need_rag": self.need_rag,
            "rewritten_queries": list(self.rewritten_queries),
            "query_hints": list(self.query_hints),
            "reason": self.reason,
            "planner_used": self.planner_used,
            "planner_status": self.planner_status,
            "planner_error": self.planner_error,
            "non_action_statement": self.non_action_statement,
        }


@dataclass
class PolicyRagContext:
    used: bool
    status: str
    plan: PolicyRagPlan
    evidences: list[Evidence] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""
    path_filter: str = POLICY_RAG_PATH_FILTER
    non_action_statement: str = CASE_HARNESS_NON_ACTION_STATEMENT

    def to_dict(self) -> dict[str, Any]:
        return {
            "used": self.used,
            "status": self.status,
            "plan": self.plan.to_dict(),
            "evidences": [item.to_dict() for item in self.evidences],
            "steps": list(self.steps),
            "reason": self.reason,
            "path_filter": self.path_filter,
            "non_action_statement": self.non_action_statement,
        }


def build_policy_rag_context(
    *,
    base_dir: Path,
    state: ApprovalCaseState,
    user_message: str,
    purpose: str,
    stage_model: Any | None = None,
    top_k: int = 4,
) -> PolicyRagContext:
    """Use the existing knowledge index as policy RAG context for a case turn.

    The model may rewrite the retrieval query and decide whether RAG is needed.
    Retrieval is read-only and restricted to `knowledge/ERP Approval`.
    """

    plan = _build_policy_rag_plan(state=state, user_message=user_message, purpose=purpose, stage_model=stage_model)
    if not plan.need_rag:
        status = plan.planner_status if plan.planner_status in {"model_required", "error", "missing_queries"} else "skipped"
        return PolicyRagContext(used=False, status=status, plan=plan, reason=plan.reason)

    try:
        _ensure_knowledge_index(base_dir)
        strategy = BaselineHybridRagStrategy()
        evidences: list[Evidence] = []
        steps: list[dict[str, Any]] = []
        statuses: list[str] = []
        reasons: list[str] = []
        queries = _dedupe_strings((plan.rewritten_queries or [])[:4])
        if not queries:
            return PolicyRagContext(
                used=False,
                status="missing_queries",
                plan=plan,
                reason="The LLM policy RAG planner requested retrieval but did not provide rewritten_queries.",
            )
        for query in queries:
            result = strategy.retrieve(
                RetrievalRequest(
                    query=query,
                    top_k=top_k,
                    path_filters=(POLICY_RAG_PATH_FILTER,),
                    query_hints=tuple(plan.query_hints),
                    rewrite_enabled=False,
                    reranker_enabled=True,
                    metadata={"purpose": purpose, "case_id": state.case_id},
                )
            )
            scoped_evidences = _filter_policy_evidences(result.evidences)
            if not scoped_evidences:
                scoped_evidences = _filter_policy_evidences(
                    knowledge_indexer.retrieve_bm25(
                        query,
                        top_k=max(top_k * 2, 8),
                        path_filters=[POLICY_RAG_PATH_FILTER],
                        query_hints=plan.query_hints,
                    )
                )
            evidences.extend(scoped_evidences)
            statuses.append(result.status)
            reasons.append(result.reason)
            steps.extend(step.to_dict() for step in result.steps)
        deduped = _dedupe_evidences(evidences)[:top_k]
        if not deduped:
            knowledge_indexer.rebuild_index(build_vector=False)
            for query in queries:
                evidences.extend(
                    _filter_policy_evidences(
                        knowledge_indexer.retrieve_bm25(
                            query,
                            top_k=max(top_k * 3, 10),
                            path_filters=[POLICY_RAG_PATH_FILTER],
                            query_hints=plan.query_hints,
                        )
                    )
                )
            deduped = _dedupe_evidences(evidences)[:top_k]
        status = "success" if deduped else "not_found"
        if not deduped:
            status = "not_found"
        elif "success" in statuses:
            status = "success"
        elif "partial" in statuses and deduped:
            status = "partial"
        return PolicyRagContext(
            used=True,
            status=status,
            plan=plan,
            evidences=deduped,
            steps=steps,
            reason=" | ".join(reason for reason in reasons if reason)[:800],
        )
    except Exception as exc:  # pragma: no cover - defensive error handling, exercised through API smoke
        return PolicyRagContext(
            used=False,
            status="error",
            plan=plan,
            reason=f"{type(exc).__name__}: {exc}",
        )


def render_policy_rag_evidence_block(context: PolicyRagContext, *, max_chars: int = 2400) -> str:
    if not context.evidences:
        return "No indexed policy evidence was retrieved from knowledge/ERP Approval."
    lines = []
    for index, evidence in enumerate(context.evidences, start=1):
        snippet = " ".join(str(evidence.snippet or "").split())
        if len(snippet) > 520:
            snippet = snippet[:517].rstrip() + "..."
        lines.append(f"{index}. {evidence.source_path} | {evidence.locator}\n{snippet}")
    text = "\n\n".join(lines)
    if len(text) > max_chars:
        return text[: max(0, max_chars - 3)].rstrip() + "..."
    return text


def _build_policy_rag_plan(
    *,
    state: ApprovalCaseState,
    user_message: str,
    purpose: str,
    stage_model: Any | None,
) -> PolicyRagPlan:
    if stage_model is None:
        return PolicyRagPlan(
            need_rag=False,
            rewritten_queries=[],
            query_hints=[],
            reason="LLM policy RAG planner is required before retrieval runs.",
            planner_used=False,
            planner_status="model_required",
        )
    system_prompt = (
        "Role: ERP policy RAG query planner. Decide whether the current case turn needs local policy retrieval, "
        "then rewrite the query for the knowledge index. Use only the user's message, case summary, approval type, "
        "and evidence requirements. Do not answer the user. Do not approve, reject, route, pay, comment, or write ERP. "
        "Return JSON only with fields: need_rag, rewritten_queries, query_hints, reason, non_action_statement. "
        "Keep rewritten_queries short and retrieval-oriented. Prefer Chinese and English policy keywords."
    )
    payload = {
        "case_id": state.case_id,
        "approval_type": state.approval_type,
        "approval_id": state.approval_id,
        "purpose": purpose,
        "user_message": user_message,
        "requirement_ids": [item.get("requirement_id", "") for item in state.evidence_requirements],
        "path_filter": POLICY_RAG_PATH_FILTER,
        "non_action_statement": CASE_HARNESS_NON_ACTION_STATEMENT,
    }
    output, error = stage_model.review_custom_json_role(
        role_name="policy_rag_query_rewrite",
        system_prompt=system_prompt,
        payload=payload,
    )
    if error:
        return PolicyRagPlan(
            need_rag=False,
            rewritten_queries=[],
            query_hints=[],
            reason="LLM policy RAG planner failed; retrieval was not run.",
            planner_used=False,
            planner_status="error",
            planner_error=error,
        )
    need_rag = bool(output.get("need_rag", True))
    queries = _strings(output.get("rewritten_queries"))[:4]
    hints = _strings(output.get("query_hints"))[:12]
    if need_rag and not queries:
        return PolicyRagPlan(
            need_rag=False,
            rewritten_queries=[],
            query_hints=hints,
            reason="LLM policy RAG planner requested retrieval but returned no rewritten_queries.",
            planner_used=True,
            planner_status="missing_queries",
        )
    return PolicyRagPlan(
        need_rag=need_rag,
        rewritten_queries=queries,
        query_hints=hints,
        reason=str(output.get("reason") or "model policy RAG plan")[:300],
        planner_used=True,
        planner_status="executed",
    )


def _ensure_knowledge_index(base_dir: Path) -> None:
    knowledge_base_dir = _knowledge_base_dir(Path(base_dir))
    knowledge_indexer.configure(knowledge_base_dir)
    status = knowledge_indexer.status()
    if not status.bm25_ready and not status.building:
        knowledge_indexer.rebuild_index(build_vector=False)
    else:
        knowledge_indexer.warm_start()
    probe = _filter_policy_evidences(
        knowledge_indexer.retrieve_bm25(
            "ERP Approval Policy Matrix PR-CTRL-001 required evidence approval matrix",
            top_k=3,
            path_filters=[POLICY_RAG_PATH_FILTER],
            query_hints=["ERP Approval", "approval matrix", "required evidence"],
        )
    )
    if not probe:
        knowledge_indexer.rebuild_index(build_vector=False)


def _knowledge_base_dir(base_dir: Path) -> Path:
    candidate = Path(base_dir).resolve()
    for path in (candidate, *candidate.parents):
        if (path / "knowledge" / "ERP Approval").exists():
            return path
    for path in (candidate, *candidate.parents):
        if (path / "knowledge").exists():
            return path
    return candidate


def _dedupe_evidences(evidences: list[Evidence]) -> list[Evidence]:
    output: dict[str, Evidence] = {}
    for evidence in evidences:
        key = f"{evidence.source_path}|{evidence.locator}|{' '.join(str(evidence.snippet or '').split())[:220]}"
        current = output.get(key)
        if current is None or float(evidence.score or 0.0) > float(current.score or 0.0):
            output[key] = evidence
    return sorted(output.values(), key=lambda item: float(item.score or 0.0), reverse=True)


def _filter_policy_evidences(evidences: list[Evidence]) -> list[Evidence]:
    return [
        evidence
        for evidence in evidences
        if str(evidence.source_path or "").replace("\\", "/").startswith(f"{POLICY_RAG_PATH_FILTER}/")
    ]


def _strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return _dedupe_strings([str(item).strip() for item in value if str(item).strip()])
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output
