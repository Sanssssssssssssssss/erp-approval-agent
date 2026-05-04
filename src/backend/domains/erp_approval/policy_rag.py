from __future__ import annotations

import re
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
    reason: str = "deterministic policy RAG plan"
    planner_used: bool = False
    planner_status: str = "deterministic"
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
        return PolicyRagContext(used=False, status="skipped", plan=plan, reason=plan.reason)

    try:
        _ensure_knowledge_index(base_dir)
        strategy = BaselineHybridRagStrategy()
        evidences: list[Evidence] = []
        steps: list[dict[str, Any]] = []
        statuses: list[str] = []
        reasons: list[str] = []
        fallback_query = _deterministic_query(state, user_message, purpose)
        queries = _dedupe_strings([*(plan.rewritten_queries or [])[:3], fallback_query])
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
        if not deduped:
            file_fallback = _load_policy_file_fallback(_knowledge_base_dir(Path(base_dir)), queries, top_k=top_k)
            if file_fallback:
                evidences.extend(file_fallback)
                steps.append(
                    {
                        "kind": "knowledge",
                        "stage": "policy_file_fallback",
                        "title": "Scoped ERP policy file fallback",
                        "message": "Indexed policy retrieval returned no scoped ERP evidence, so local ERP policy files were read directly.",
                        "results": [item.to_dict() for item in file_fallback],
                    }
                )
                reasons.append("Scoped ERP policy files were used after indexed retrieval returned no ERP policy evidence.")
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
    except Exception as exc:  # pragma: no cover - defensive fallback, exercised through API smoke
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
    fallback = PolicyRagPlan(
        need_rag=True,
        rewritten_queries=[_deterministic_query(state, user_message, purpose)],
        query_hints=_deterministic_hints(state, purpose),
    )
    if stage_model is None:
        return fallback
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
        "fallback_query": fallback.rewritten_queries[0],
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
            need_rag=True,
            rewritten_queries=fallback.rewritten_queries,
            query_hints=fallback.query_hints,
            reason=fallback.reason,
            planner_used=False,
            planner_status="error",
            planner_error=error,
        )
    queries = _strings(output.get("rewritten_queries"))[:4]
    hints = _strings(output.get("query_hints"))[:12]
    return PolicyRagPlan(
        need_rag=bool(output.get("need_rag", True)),
        rewritten_queries=queries or fallback.rewritten_queries,
        query_hints=hints or fallback.query_hints,
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


def _deterministic_query(state: ApprovalCaseState, user_message: str, purpose: str) -> str:
    approval_type = state.approval_type or "unknown"
    requirement_terms = " ".join(
        str(item.get("label") or item.get("requirement_id") or "")
        for item in (state.evidence_requirements or [])[:10]
    )
    return " ".join(
        part
        for part in [
            approval_type,
            purpose,
            user_message,
            requirement_terms,
            "policy approval matrix required evidence blocking acceptable unacceptable clause",
            "ERP Approval Policy Matrix Procurement PR-CTRL-001 INV-CTRL-001 SUP-CTRL-001",
        ]
        if str(part or "").strip()
    )


def _deterministic_hints(state: ApprovalCaseState, purpose: str) -> list[str]:
    hints = [
        state.approval_type or "unknown",
        purpose,
        "approval matrix",
        "required evidence",
        "blocking",
        "policy clause",
    ]
    for requirement in (state.evidence_requirements or [])[:12]:
        for value in (requirement.get("requirement_id"), requirement.get("label")):
            if value:
                hints.append(str(value))
    return _dedupe_strings(hints)[:16]


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


def _load_policy_file_fallback(base_dir: Path, queries: list[str], *, top_k: int) -> list[Evidence]:
    policy_dir = Path(base_dir) / POLICY_RAG_PATH_FILTER / "policies"
    if not policy_dir.exists():
        return []
    query_text = " ".join(queries).lower()
    candidates: list[Evidence] = []
    for path in sorted(policy_dir.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        snippet = _best_policy_snippet(text, query_text)
        relative_path = path.relative_to(base_dir).as_posix()
        candidates.append(
            Evidence(
                source_path=relative_path,
                source_type="md",
                locator=path.stem,
                snippet=snippet,
                channel="bm25",
                score=_policy_file_score(text, query_text),
                query_variant=" | ".join(queries[:2]),
            )
        )
    return sorted(candidates, key=lambda item: float(item.score or 0.0), reverse=True)[:top_k]


def _best_policy_snippet(text: str, query_text: str, *, max_chars: int = 900) -> str:
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    if not paragraphs:
        return text[:max_chars]
    terms = [term for term in re.split(r"[^a-z0-9_\-\u4e00-\u9fff]+", query_text.lower()) if len(term) >= 3]
    scored = []
    for paragraph in paragraphs:
        lowered = paragraph.lower()
        score = sum(1 for term in terms if term in lowered)
        scored.append((score, paragraph))
    best = max(scored, key=lambda item: item[0])[1]
    return best[:max_chars]


def _policy_file_score(text: str, query_text: str) -> float:
    lowered = text.lower()
    terms = [term for term in re.split(r"[^a-z0-9_\-\u4e00-\u9fff]+", query_text.lower()) if len(term) >= 3]
    return float(sum(1 for term in terms if term in lowered) or 1)


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
