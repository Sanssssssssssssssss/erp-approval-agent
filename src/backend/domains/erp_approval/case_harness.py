from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.backend.domains.erp_approval.case_context import CaseContextAssembler
from src.backend.domains.erp_approval.case_memory_store import CaseMemoryStore
from src.backend.domains.erp_approval.case_patch_validator import CasePatchValidator, contract_for_state
from src.backend.domains.erp_approval.case_review import APPROVAL_TYPE_CN
from src.backend.domains.erp_approval.case_review_service import (
    CaseReviewEvidenceInput,
    CaseReviewRequest,
    CaseReviewResponse,
    run_local_case_review,
)
from src.backend.domains.erp_approval.case_stage_model import CaseStageModelDecision
from src.backend.domains.erp_approval.case_state_models import (
    ApprovalCaseState,
    CaseAcceptedEvidence,
    CaseAuditEvent,
    CASE_HARNESS_NON_ACTION_STATEMENT,
    CasePatch,
    CaseRejectedEvidence,
    CaseTurnIntent,
    CaseTurnRequest,
    CaseTurnResponse,
)
from src.backend.domains.erp_approval.service import parse_approval_request


class CaseHarness:
    """Owns local approval case state transitions for each user turn."""

    def __init__(self, base_dir: Path | str, *, stage_model: Any | None = None) -> None:
        self.base_dir = Path(base_dir)
        self.store = CaseMemoryStore(base_dir)
        self.context_assembler = CaseContextAssembler()
        self.validator = CasePatchValidator()
        self.stage_model = stage_model

    def handle_turn(self, request: CaseTurnRequest) -> CaseTurnResponse:
        lock_case_id = self._lock_case_id(request)
        with self.store.case_lock(lock_case_id):
            return self._handle_turn_locked(request)

    def _handle_turn_locked(self, request: CaseTurnRequest) -> CaseTurnResponse:
        now = _now()
        existing_state = self.store.get(request.case_id) if request.case_id.strip() else None
        state = existing_state or self._create_state(request, now)
        if existing_state is not None and request.expected_turn_count is not None and request.expected_turn_count != existing_state.turn_count:
            return self._turn_conflict_response(existing_state, request, now)
        turn_id = f"turn-{state.turn_count + 1:04d}"
        intent = classify_case_turn(request.user_message, has_case=existing_state is not None, has_evidence=bool(request.extra_evidence))
        contract = contract_for_state(state)
        context_pack = self.context_assembler.assemble(state, contract, request.user_message)
        self.store.append_audit_event(
            _event(turn_id, state.case_id, "turn_received", now, {"intent": intent, "context_pack": context_pack})
        )

        candidates = self._candidate_evidence(request, state, turn_id, intent)
        provisional_review = self._review(state, request.user_message, candidates)
        model_decision, model_error = self._review_with_stage_model(
            context_pack=context_pack,
            candidates=candidates,
            review=provisional_review,
            deterministic_intent=intent,
        )
        intent = self._intent_from_stage_model(intent, model_decision, contract)
        accepted, rejected, warnings = self._review_candidate_evidence(candidates, provisional_review, now)
        accepted, rejected, warnings = self._apply_stage_model_decision(
            candidates=candidates,
            accepted=accepted,
            rejected=rejected,
            warnings=warnings,
            decision=model_decision,
            now=now,
        )
        final_candidates = candidates if accepted else []
        final_review = provisional_review if accepted else self._review(state, request.user_message, [])
        patch = self._build_patch(
            state=state,
            turn_id=turn_id,
            intent=intent,
            accepted=accepted,
            rejected=rejected,
            review=final_review,
            warnings=warnings,
            created_new=existing_state is None,
            model_decision=model_decision,
            model_error=model_error,
        )
        patch = self.validator.validate(state, patch, contract, review=final_review)

        events: list[CaseAuditEvent] = []
        if existing_state is None:
            events.append(_event(turn_id, state.case_id, "case_created", now, {"approval_type": state.approval_type, "approval_id": state.approval_id}))
        if candidates:
            events.append(_event(turn_id, state.case_id, "evidence_submitted", now, {"source_ids": [item.source_id for item in candidates]}))
        if patch.accepted_evidence:
            events.append(_event(turn_id, state.case_id, "evidence_accepted", now, {"source_ids": [item.source_id for item in patch.accepted_evidence]}))
        if patch.rejected_evidence:
            events.append(_event(turn_id, state.case_id, "evidence_rejected", now, {"source_ids": [item.source_id for item in patch.rejected_evidence], "reasons": patch.rejection_reasons}))
        if intent == "off_topic":
            events.append(_event(turn_id, state.case_id, "off_topic_rejected", now, {"message_preview": request.user_message[:240]}))
        if model_decision is not None:
            events.append(
                _event(
                    turn_id,
                    state.case_id,
                    "case_stage_model_reviewed",
                    now,
                    {
                        "turn_intent": model_decision.turn_intent,
                        "patch_type": model_decision.patch_type,
                        "evidence_decision": model_decision.evidence_decision,
                        "confidence": model_decision.confidence,
                        "error": model_error,
                    },
                )
            )

        if patch.allowed_to_apply:
            state = self._apply_patch(state, patch, final_review, now, turn_id, mutate_case=intent != "off_topic")
            for evidence in patch.accepted_evidence:
                evidence_path = self.store.write_evidence_text(state.case_id, evidence.source_id, evidence.content)
                for stored in state.accepted_evidence:
                    if stored.source_id == evidence.source_id:
                        stored.metadata["local_evidence_file"] = evidence_path
            dossier = render_case_dossier(state, final_review, patch)
            self.store.write_dossier(state.case_id, dossier)
            state = state.model_copy(update={"dossier_version": state.dossier_version + 1, "audit_event_count": state.audit_event_count + len(events)})
            self.store.upsert(state)
            events.append(_event(turn_id, state.case_id, "case_state_persisted", now, {"stage": state.stage, "dossier_version": state.dossier_version}))
        else:
            dossier = self.store.read_dossier(state.case_id) or render_case_dossier(state, final_review, patch)
            events.append(_event(turn_id, state.case_id, "case_patch_rejected", now, {"warnings": patch.warnings}))

        for event in events:
            self.store.append_audit_event(event)
        return CaseTurnResponse(
            case_state=state,
            contract=contract_for_state(state),
            patch=patch,
            review=final_review,
            dossier=dossier,
            audit_events=events,
            storage_paths=self.store.paths_for(state.case_id),
            operation_scope="persistent_case_turn",
            non_action_statement=CASE_HARNESS_NON_ACTION_STATEMENT,
        )

    def get_case(self, case_id: str) -> ApprovalCaseState | None:
        return self.store.get(case_id)

    def get_dossier(self, case_id: str) -> str:
        return self.store.read_dossier(case_id)

    def list_cases(self, limit: int = 50) -> list[ApprovalCaseState]:
        return self.store.list_recent(limit=limit)

    def _lock_case_id(self, request: CaseTurnRequest) -> str:
        if request.case_id.strip():
            return request.case_id.strip()
        approval_request = parse_approval_request("", request.user_message)
        approval_id = approval_request.approval_id or _stable_suffix(request.user_message)
        return f"erp-case:{approval_id}"

    def _turn_conflict_response(self, state: ApprovalCaseState, request: CaseTurnRequest, now: str) -> CaseTurnResponse:
        turn_id = f"turn-conflict-{state.turn_count + 1:04d}"
        contract = contract_for_state(state)
        review = self._review(state, request.user_message, [])
        patch = CasePatch(
            patch_id=f"case-patch-conflict:{state.case_id}:{turn_id}",
            turn_id=turn_id,
            case_id=state.case_id,
            patch_type="no_case_change",
            turn_intent="ask_status",
            evidence_decision="not_evidence",
            warnings=[
                f"case_state version conflict: expected turn_count {request.expected_turn_count}, current turn_count {state.turn_count}.",
                "本轮输入未写入案卷；请刷新当前 case_state 后重新提交。",
            ],
            allowed_to_apply=False,
        )
        event = _event(
            turn_id,
            state.case_id,
            "case_turn_conflict",
            now,
            {"expected_turn_count": request.expected_turn_count, "current_turn_count": state.turn_count},
        )
        self.store.append_audit_event(event)
        dossier = self.store.read_dossier(state.case_id) or render_case_dossier(state, review, patch)
        return CaseTurnResponse(
            case_state=state,
            contract=contract,
            patch=patch,
            review=review,
            dossier=dossier,
            audit_events=[event],
            storage_paths=self.store.paths_for(state.case_id),
            operation_scope="persistent_case_turn_conflict",
            non_action_statement=CASE_HARNESS_NON_ACTION_STATEMENT,
        )

    def _create_state(self, request: CaseTurnRequest, now: str) -> ApprovalCaseState:
        approval_request = parse_approval_request("", request.user_message)
        approval_id = approval_request.approval_id or _stable_suffix(request.user_message)
        case_id = request.case_id.strip() or f"erp-case:{approval_id}"
        return ApprovalCaseState(
            case_id=case_id,
            approval_type=approval_request.approval_type,
            approval_id=approval_request.approval_id,
            stage="draft",
            created_at=now,
            updated_at=now,
            source_request=request.user_message.strip(),
            request=approval_request.model_dump(),
            non_action_statement=CASE_HARNESS_NON_ACTION_STATEMENT,
        )

    def _candidate_evidence(
        self,
        request: CaseTurnRequest,
        state: ApprovalCaseState,
        turn_id: str,
        intent: CaseTurnIntent,
    ) -> list[CaseReviewEvidenceInput]:
        candidates = [_normalize_evidence_input(item, state.case_id, turn_id, index) for index, item in enumerate(request.extra_evidence, start=1)]
        if not candidates and intent == "submit_evidence":
            record_type = infer_case_evidence_record_type("", "本轮用户提交材料", request.user_message)
            candidates.append(
                CaseReviewEvidenceInput(
                    title="本轮用户提交材料",
                    record_type=record_type,
                    content=request.user_message,
                    source_id=f"local_evidence://{record_type}/{_source_slug(state.case_id)}/{turn_id}-1",
                    metadata={"submitted_via": "user_message", "read_only": True},
                )
            )
        return candidates

    def _review(self, state: ApprovalCaseState, user_message: str, candidates: list[CaseReviewEvidenceInput]) -> CaseReviewResponse:
        evidence = [item.to_review_input() for item in state.accepted_evidence] + candidates
        request_data = dict(state.request or {})
        request_data["user_message"] = state.source_request or user_message
        request_data["extra_evidence"] = [item.model_dump() for item in evidence]
        return run_local_case_review(CaseReviewRequest.model_validate(request_data), base_dir=self.base_dir)

    def _review_with_stage_model(
        self,
        *,
        context_pack: dict[str, Any],
        candidates: list[CaseReviewEvidenceInput],
        review: CaseReviewResponse,
        deterministic_intent: CaseTurnIntent,
    ) -> tuple[CaseStageModelDecision | None, str]:
        if self.stage_model is None:
            return None, ""
        if not candidates and deterministic_intent in {"create_case", "ask_required_materials", "ask_status", "off_topic"}:
            return None, ""
        try:
            return (
                self.stage_model.review_turn(
                    context_pack=context_pack,
                    candidates=candidates,
                    review=review,
                    deterministic_intent=deterministic_intent,
                ),
                "",
            )
        except Exception as exc:  # pragma: no cover - live model/runtime dependent
            return (
                CaseStageModelDecision(
                    warnings=["阶段模型调用失败，已退回 deterministic fallback。"],
                    reviewer_message="阶段模型调用失败，本轮仍由 deterministic evidence gate 处理。",
                ),
                f"{type(exc).__name__}: {exc}",
            )

    def _intent_from_stage_model(
        self,
        deterministic_intent: CaseTurnIntent,
        decision: CaseStageModelDecision | None,
        contract,
    ) -> CaseTurnIntent:
        if decision is None or not decision.turn_intent:
            return deterministic_intent
        if decision.turn_intent in contract.allowed_intents:
            return decision.turn_intent  # type: ignore[return-value]
        return deterministic_intent

    def _review_candidate_evidence(
        self,
        candidates: list[CaseReviewEvidenceInput],
        review: CaseReviewResponse,
        now: str,
    ) -> tuple[list[CaseAcceptedEvidence], list[CaseRejectedEvidence], list[str]]:
        accepted: list[CaseAcceptedEvidence] = []
        rejected: list[CaseRejectedEvidence] = []
        warnings: list[str] = []
        claims = list(review.evidence_claims)
        for item in candidates:
            source_claims = [claim for claim in claims if claim.get("source_id") == item.source_id]
            supported_claims = [
                claim
                for claim in source_claims
                if claim.get("verification_status") in {"supported", "needs_review", "conflict"} and claim.get("supports_requirement_ids")
            ]
            if not item.content.strip():
                rejected.append(_rejected(item, now, ["材料内容为空，不能写入案卷。"]))
            elif item.record_type in {"local_note", "user_statement"}:
                rejected.append(_rejected(item, now, ["这只是用户陈述或本地备注，不能满足阻断性证据要求。"]))
            elif _looks_like_weak_user_statement(item):
                rejected.append(_rejected(item, now, ["这更像口头说明或主观陈述，缺少正式记录编号、金额、状态或来源字段，不能替代 ERP/附件证据。"]))
            elif not supported_claims:
                rejected.append(_rejected(item, now, ["未抽取到可支持必备证据清单的 claim，不能写入 accepted_evidence。"]))
            else:
                requirement_ids = _unique([req for claim in supported_claims for req in claim.get("supports_requirement_ids") or []])
                claim_ids = _unique([str(claim.get("claim_id") or "") for claim in supported_claims])
                if any(claim.get("verification_status") == "conflict" for claim in supported_claims):
                    warnings.append(f"{item.source_id} 已作为证据收录，但存在冲突，需要人工复核。")
                accepted.append(
                    CaseAcceptedEvidence(
                        source_id=item.source_id,
                        title=item.title,
                        record_type=item.record_type,
                        content=item.content,
                        accepted_at=now,
                        claim_ids=claim_ids,
                        requirement_ids=requirement_ids,
                        metadata=dict(item.metadata or {}),
                    )
                )
        return accepted, rejected, warnings

    def _apply_stage_model_decision(
        self,
        *,
        candidates: list[CaseReviewEvidenceInput],
        accepted: list[CaseAcceptedEvidence],
        rejected: list[CaseRejectedEvidence],
        warnings: list[str],
        decision: CaseStageModelDecision | None,
        now: str,
    ) -> tuple[list[CaseAcceptedEvidence], list[CaseRejectedEvidence], list[str]]:
        if decision is None:
            return accepted, rejected, warnings
        warnings = _unique(warnings + list(decision.warnings))
        candidate_by_source = {item.source_id: item for item in candidates}
        accepted_by_source = {item.source_id: item for item in accepted}
        rejected_by_source = {item.source_id: item for item in rejected}
        model_rejections = {
            item.source_id: item.reasons or ["模型判断该材料不足以写入 accepted_evidence。"]
            for item in decision.rejected_evidence
            if item.source_id
        }

        if decision.turn_intent == "off_topic":
            model_rejections = {
                item.source_id: ["模型判断本轮输入与当前审批案件无关，不能污染案卷。"]
                for item in candidates
            }

        if decision.accepted_source_ids:
            allowed_sources = set(decision.accepted_source_ids)
            for source_id in list(accepted_by_source):
                if source_id not in allowed_sources:
                    model_rejections.setdefault(source_id, ["模型未确认该材料可作为本轮 accepted evidence。"])
            for source_id in allowed_sources:
                if source_id not in accepted_by_source:
                    warnings.append(f"模型尝试接受 {source_id}，但本地证据门没有发现可支持必备要求的 claim，已拒绝。")

        if decision.evidence_decision in {"rejected", "needs_clarification"} and candidates and not model_rejections:
            model_rejections = {
                item.source_id: [decision.reviewer_message or "模型要求补充澄清，本轮材料暂不写入 accepted_evidence。"]
                for item in candidates
            }

        for source_id, reasons in model_rejections.items():
            accepted_by_source.pop(source_id, None)
            if source_id in candidate_by_source:
                rejected_by_source[source_id] = _rejected(candidate_by_source[source_id], now, reasons)

        for source_id, item in accepted_by_source.items():
            item.metadata["stage_model_review"] = "accepted" if source_id in decision.accepted_source_ids else "not_overridden"
        return list(accepted_by_source.values()), list(rejected_by_source.values()), _unique(warnings)

    def _build_patch(
        self,
        *,
        state: ApprovalCaseState,
        turn_id: str,
        intent: CaseTurnIntent,
        accepted: list[CaseAcceptedEvidence],
        rejected: list[CaseRejectedEvidence],
        review: CaseReviewResponse,
        warnings: list[str],
        created_new: bool,
        model_decision: CaseStageModelDecision | None,
        model_error: str,
    ) -> CasePatch:
        if intent == "off_topic":
            patch_type = "no_case_change"
            decision = "not_evidence"
        elif accepted:
            patch_type = "accept_evidence"
            decision = "accepted"
        elif rejected:
            patch_type = "reject_evidence"
            decision = "rejected"
        elif intent == "request_final_memo":
            patch_type = "final_memo"
            decision = "not_evidence"
        elif created_new:
            patch_type = "create_case"
            decision = "not_evidence"
        else:
            patch_type = "answer_status"
            decision = "not_evidence"
        return CasePatch(
            patch_id=f"case-patch:{state.case_id}:{turn_id}",
            turn_id=turn_id,
            case_id=state.case_id,
            patch_type=patch_type,  # type: ignore[arg-type]
            turn_intent=intent,
            evidence_decision=decision,  # type: ignore[arg-type]
            accepted_evidence=accepted,
            rejected_evidence=rejected,
            requirements_satisfied=[item.get("requirement_id", "") for item in review.evidence_requirements if item.get("status") == "satisfied"],
            requirements_missing=list(review.evidence_sufficiency.get("missing_requirement_ids") or []),
            dossier_patch=_dossier_patch(intent, accepted, rejected, review),
            rejection_reasons=_unique([reason for item in rejected for reason in item.reasons]),
            next_questions=list(review.evidence_sufficiency.get("next_questions") or []),
            warnings=warnings,
            model_review=(
                model_decision.to_patch_metadata(used=True, error=model_error)
                if model_decision is not None
                else {"used": False, "error": "", "non_action_statement": CASE_HARNESS_NON_ACTION_STATEMENT}
            ),
        )

    def _apply_patch(
        self,
        state: ApprovalCaseState,
        patch: CasePatch,
        review: CaseReviewResponse,
        now: str,
        turn_id: str,
        *,
        mutate_case: bool,
    ) -> ApprovalCaseState:
        accepted = list(state.accepted_evidence)
        rejected = list(state.rejected_evidence)
        if mutate_case:
            accepted = _merge_accepted(accepted, patch.accepted_evidence)
            rejected = _merge_rejected(rejected, patch.rejected_evidence)
        return state.model_copy(
            update={
                "stage": _stage_from_review(review),
                "updated_at": now,
                "turn_count": state.turn_count + 1,
                "accepted_evidence": accepted,
                "rejected_evidence": rejected,
                "evidence_requirements": review.evidence_requirements,
                "claims": review.evidence_claims,
                "contradictions": review.contradictions,
                "evidence_sufficiency": review.evidence_sufficiency,
                "control_matrix": review.control_matrix,
                "recommendation": review.recommendation,
                "reviewer_memo": review.reviewer_memo,
                "missing_items": list(review.evidence_sufficiency.get("blocking_gaps") or []),
                "next_questions": list(review.evidence_sufficiency.get("next_questions") or []),
                "last_valid_turn_id": turn_id if mutate_case else state.last_valid_turn_id,
                "non_action_statement": CASE_HARNESS_NON_ACTION_STATEMENT,
            }
        )


def classify_case_turn(user_message: str, *, has_case: bool, has_evidence: bool) -> CaseTurnIntent:
    text = user_message.lower()
    if _looks_off_topic(text):
        return "off_topic"
    if has_evidence:
        return "submit_evidence"
    if any(term in text for term in ("需要什么", "哪些材料", "什么材料", "交什么", "缺什么", "材料清单", "必备材料", "required material", "required materials", "required evidence", "what materials", "materials are required")) or ("需要" in text and "材料" in text):
        return "ask_required_materials"
    if any(term in text for term in ("撤回", "withdraw", "更正", "correct", "修正")):
        return "correct_previous_evidence"
    if not has_case:
        return "create_case"
    if any(term in text for term in ("最终", "final", "memo", "报告", "提交人工", "reviewer memo")):
        return "request_final_memo"
    if _looks_like_evidence_submission(text):
        return "submit_evidence"
    if any(term in text for term in ("状态", "进度", "还差", "status")):
        return "ask_status"
    return "ask_status"


def infer_case_evidence_record_type(record_type: str, title: str, content: str) -> str:
    explicit = re.sub(r"[^a-z0-9_]+", "_", str(record_type or "").strip().lower()).strip("_")
    if explicit:
        return explicit
    text = f"{title}\n{content}".lower()
    patterns: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("purchase_order", ("purchase order", "po-", " po ", "采购订单")),
        ("goods_receipt", ("goods receipt", "grn", "收货", "入库")),
        ("invoice", ("invoice", "发票")),
        ("receipt", ("receipt", "收据", "小票")),
        ("quote", ("quote", "quotation", "报价", "比价")),
        ("budget", ("budget", "预算")),
        ("vendor", ("vendor", "supplier", "供应商", "准入")),
        ("sanctions_check", ("sanctions", "制裁")),
        ("bank_info", ("bank", "银行")),
        ("tax_info", ("tax", "税务", "税号")),
        ("contract", ("contract", "合同", "框架协议")),
        ("policy", ("policy", "政策", "制度", "矩阵")),
        ("approval_request", ("approval request", "purchase requisition", "pr-", "审批单", "采购申请")),
        ("payment_terms", ("payment terms", "付款条款")),
        ("duplicate_check", ("duplicate", "重复")),
        ("limit_check", ("limit", "限额")),
    )
    for candidate, needles in patterns:
        if any(needle in text for needle in needles):
            return candidate
    return "local_note"


def render_case_dossier(state: ApprovalCaseState, review: CaseReviewResponse, patch: CasePatch) -> str:
    lines = [
        f"# {state.case_id} 审批案卷",
        "",
        "## 案卷状态",
        "",
        f"- 阶段：{state.stage}",
        f"- 审批类型：{APPROVAL_TYPE_CN.get(state.approval_type, state.approval_type)}",
        f"- 审批单号：{state.approval_id or '未识别'}",
        f"- 当前轮次：{state.turn_count}",
        f"- 案卷版本：{state.dossier_version + 1}",
        f"- 本轮 patch：{patch.patch_type} / {patch.evidence_decision}",
        "",
        "## 已接受证据",
        "",
    ]
    if state.accepted_evidence or patch.accepted_evidence:
        for item in _merge_accepted(state.accepted_evidence, patch.accepted_evidence):
            lines.append(f"- `{item.source_id}` {item.title or item.record_type} -> claims: {', '.join(item.claim_ids) if item.claim_ids else '无'}")
    else:
        lines.append("- 暂无。")
    lines.extend(["", "## 被拒绝材料", ""])
    if state.rejected_evidence or patch.rejected_evidence:
        for item in _merge_rejected(state.rejected_evidence, patch.rejected_evidence):
            lines.append(f"- `{item.source_id}` {item.title or item.record_type}: {'; '.join(item.reasons) if item.reasons else '未说明'}")
    else:
        lines.append("- 暂无。")
    lines.extend(["", "## 当前审查 Memo", "", review.reviewer_memo, "", "## 非执行边界", "", "- No ERP write action was executed."])
    return "\n".join(lines).strip() + "\n"


def _normalize_evidence_input(item: CaseReviewEvidenceInput, case_id: str, turn_id: str, index: int) -> CaseReviewEvidenceInput:
    record_type = infer_case_evidence_record_type(item.record_type, item.title, item.content)
    source_id = item.source_id.strip() or f"local_evidence://{record_type}/{_source_slug(case_id)}/{turn_id}-{index}"
    metadata = dict(item.metadata or {})
    metadata.setdefault("case_id", case_id)
    metadata.setdefault("turn_id", turn_id)
    metadata.setdefault("read_only", True)
    return item.model_copy(update={"record_type": record_type, "source_id": source_id, "metadata": metadata})


def _rejected(item: CaseReviewEvidenceInput, now: str, reasons: list[str]) -> CaseRejectedEvidence:
    return CaseRejectedEvidence(
        source_id=item.source_id,
        title=item.title,
        record_type=item.record_type,
        content_preview=item.content[:600],
        rejected_at=now,
        reasons=reasons,
        metadata=dict(item.metadata or {}),
    )


def _stage_from_review(review: CaseReviewResponse):
    recommendation = review.recommendation or {}
    if recommendation.get("status") == "blocked":
        return "blocked"
    if recommendation.get("status") == "recommend_approve" and review.evidence_sufficiency.get("passed") and review.control_matrix.get("passed"):
        return "ready_for_final_review"
    if recommendation.get("status") == "escalate":
        return "escalation_review"
    return "collecting_evidence"


def _dossier_patch(
    intent: CaseTurnIntent,
    accepted: list[CaseAcceptedEvidence],
    rejected: list[CaseRejectedEvidence],
    review: CaseReviewResponse,
) -> str:
    if accepted:
        return "本轮材料已通过案卷写入门，新增 accepted_evidence：" + ", ".join(item.source_id for item in accepted)
    if rejected:
        return "本轮材料未通过案卷写入门，写入 rejected_evidence：" + "; ".join(reason for item in rejected for reason in item.reasons)
    if intent == "request_final_memo":
        return "用户请求生成 reviewer memo；系统基于当前 case_state 输出非执行审查报告。"
    if intent == "off_topic":
        return "本轮输入与当前审批案件无关，未写入案卷。"
    missing = review.evidence_sufficiency.get("blocking_gaps") or []
    return "本轮未新增证据。当前阻断缺口：" + ("; ".join(missing) if missing else "无")


def _looks_like_evidence_submission(text: str) -> bool:
    if any(
        term in text
        for term in (
            "证明",
            "材料",
            "附件",
            "发票",
            "收据",
            "票据",
            "预算",
            "报价",
            "合同",
            "法务",
            "记录",
            "供应商",
            "准入",
            "制裁",
            "银行",
            "税务",
            "grn",
            "invoice",
            "quote",
            "budget record",
            "vendor record",
        )
    ):
        return True
    return bool(re.search(r"\bpo[-_\s][a-z0-9]{2,}\b|\bpo\d{2,}\b|\bpo\b", text))


def _looks_off_topic(text: str) -> bool:
    off_topic = any(
        term in text
        for term in (
            "营销文案",
            "写首诗",
            "天气",
            "股票",
            "旅行计划",
            "写代码",
            "讲笑话",
            "marketing copy",
            "poem",
            "weather",
            "stock price",
            "travel plan",
            "write code",
            "joke",
        )
    )
    if not off_topic:
        return False
    if any(term in text for term in ("顺便", "同时", "再把", "also", "while you")):
        return True
    return not _looks_like_evidence_submission(text)


def _looks_like_weak_user_statement(item: CaseReviewEvidenceInput) -> bool:
    if item.metadata.get("submitted_via") != "user_message":
        return False
    text = item.content.lower()
    weak_terms = (
        "肯定",
        "问过",
        "老板",
        "同意",
        "就当",
        "口头",
        "丢了",
        "之后补",
        "以后补",
        "下个月会补",
        "暂时没有文件",
        "没有文件",
        "没法上传",
        "相信我",
        "不用",
        "不需要",
        "直接",
        "verbal",
        "lost",
        "pending",
        "no file",
        "no document",
        "will provide later",
        "boss",
        "trust me",
        "already approved",
        "no citation",
    )
    hard_reject_terms = (
        "口头",
        "丢了",
        "之后补",
        "以后补",
        "下个月会补",
        "暂时没有文件",
        "没有文件",
        "没法上传",
        "verbal",
        "lost",
        "pending",
        "no file",
        "no document",
        "will provide later",
    )
    if any(term in text for term in hard_reject_terms):
        return True
    structured_markers = (
        "record",
        "number",
        "available budget",
        "amount",
        "status",
        "quote",
        "quotation",
        "invoice",
        "purchase order",
        "po-",
        "grn",
        "goods receipt",
        "vendor profile",
        "receipt",
        "tax id",
        "bank account",
        "sanctions check",
        "记录",
        "编号",
        "金额",
        "可用预算",
        "状态",
        "报价单",
        "发票号",
        "采购订单",
        "收货记录",
        "供应商档案",
        "税号",
        "银行账号",
        "制裁检查",
    )
    return any(term in text for term in weak_terms) and not any(marker in text for marker in structured_markers)


def _event(turn_id: str, case_id: str, event: str, now: str, details: dict[str, Any]) -> CaseAuditEvent:
    return CaseAuditEvent(turn_id=turn_id, case_id=case_id, event=event, created_at=now, details=details)


def _merge_accepted(existing: list[CaseAcceptedEvidence], new: list[CaseAcceptedEvidence]) -> list[CaseAcceptedEvidence]:
    output = {item.source_id: item for item in existing}
    output.update({item.source_id: item for item in new})
    return list(output.values())


def _merge_rejected(existing: list[CaseRejectedEvidence], new: list[CaseRejectedEvidence]) -> list[CaseRejectedEvidence]:
    output = {f"{item.source_id}:{item.rejected_at}": item for item in existing}
    output.update({f"{item.source_id}:{item.rejected_at}": item for item in new})
    return list(output.values())


def _source_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.:-]+", "-", value or "case").strip("-")[:80]


def _stable_suffix(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output
