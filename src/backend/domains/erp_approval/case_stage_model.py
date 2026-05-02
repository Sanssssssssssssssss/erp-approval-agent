from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from src.backend.domains.erp_approval.case_review_service import CaseReviewEvidenceInput, CaseReviewResponse
from src.backend.domains.erp_approval.case_state_models import CASE_HARNESS_NON_ACTION_STATEMENT
from src.backend.domains.erp_approval.service import extract_json_object


CASE_STAGE_MODEL_SYSTEM_PROMPT = """你是企业 ERP 审批案卷的 evidence reviewer。

你不是聊天助手，也不是审批执行人。你只能对“本轮用户输入/材料”提出结构化 CasePatch 建议。

硬边界：
- 只输出 JSON，不要 markdown。
- 不得说已经批准、驳回、付款、路由、激活供应商、更新预算或签署合同。
- 用户陈述不能当作强证据。
- 没有 source_id、没有可支持 requirement 的 claim，不得建议 accepted。
- 证据不足时必须 request_more_info / needs_clarification / rejected，而不是 recommend_approve。
- 专有字段名和枚举值保留英文，其余 explanation 使用中文。

你需要扮演严格企业审批 reviewer，判断本轮输入：
- turn_intent 是否正确。
- 哪些 source_id 可以作为案卷证据。
- 哪些 source_id 应退回，以及为什么。
- 哪些 requirement 可能被支持。
- 当前还应该向用户追问什么。

输出 JSON schema：
{
  "turn_intent": "create_case|ask_required_materials|submit_evidence|correct_previous_evidence|withdraw_evidence|ask_status|request_final_memo|off_topic",
  "patch_type": "create_case|accept_evidence|reject_evidence|answer_status|final_memo|no_case_change",
  "evidence_decision": "accepted|rejected|needs_clarification|not_evidence",
  "accepted_source_ids": ["..."],
  "rejected_evidence": [{"source_id": "...", "reasons": ["中文原因"]}],
  "requirements_satisfied": ["..."],
  "requirements_missing": ["..."],
  "next_questions": ["中文补证问题"],
  "warnings": ["中文风险或越界提醒"],
  "dossier_patch": "中文案卷补丁摘要",
  "reviewer_message": "中文给用户看的本轮审核结论",
  "confidence": 0.0,
  "non_action_statement": "This is a local approval case state update. No ERP write action was executed."
}
"""


class ModelRejectedEvidence(BaseModel):
    source_id: str = ""
    reasons: list[str] = Field(default_factory=list)


class CaseStageModelDecision(BaseModel):
    turn_intent: str = ""
    patch_type: str = ""
    evidence_decision: str = "not_evidence"
    accepted_source_ids: list[str] = Field(default_factory=list)
    rejected_evidence: list[ModelRejectedEvidence] = Field(default_factory=list)
    requirements_satisfied: list[str] = Field(default_factory=list)
    requirements_missing: list[str] = Field(default_factory=list)
    next_questions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    dossier_patch: str = ""
    reviewer_message: str = ""
    confidence: float = 0.0
    non_action_statement: str = CASE_HARNESS_NON_ACTION_STATEMENT

    def to_patch_metadata(self, *, used: bool, error: str = "") -> dict[str, Any]:
        return {
            "used": used,
            "error": error,
            "turn_intent": self.turn_intent,
            "patch_type": self.patch_type,
            "evidence_decision": self.evidence_decision,
            "accepted_source_ids": list(self.accepted_source_ids),
            "rejected_evidence": [item.model_dump() for item in self.rejected_evidence],
            "requirements_satisfied": list(self.requirements_satisfied),
            "requirements_missing": list(self.requirements_missing),
            "next_questions": list(self.next_questions),
            "warnings": list(self.warnings),
            "dossier_patch": self.dossier_patch,
            "reviewer_message": self.reviewer_message,
            "confidence": self.confidence,
            "non_action_statement": self.non_action_statement,
        }


class CaseStageModelReviewer:
    """Asks a bounded LLM role to propose a CasePatch, never to write case state."""

    def __init__(self, model: Any) -> None:
        self.model = model

    def review_turn(
        self,
        *,
        context_pack: dict[str, Any],
        candidates: list[CaseReviewEvidenceInput],
        review: CaseReviewResponse,
        deterministic_intent: str,
    ) -> CaseStageModelDecision:
        payload = {
            "deterministic_intent": deterministic_intent,
            "case_context_pack": context_pack,
            "candidate_evidence": [
                {
                    "source_id": item.source_id,
                    "title": item.title,
                    "record_type": item.record_type,
                    "content_preview": item.content[:1600],
                    "metadata": dict(item.metadata or {}),
                }
                for item in candidates
            ],
            "evidence_requirements": review.evidence_requirements,
            "candidate_claims": review.evidence_claims,
            "evidence_sufficiency": review.evidence_sufficiency,
            "contradictions": review.contradictions,
            "control_matrix": review.control_matrix,
            "current_recommendation": review.recommendation,
            "non_action_statement": CASE_HARNESS_NON_ACTION_STATEMENT,
        }
        response = self.model.invoke(
            [
                {"role": "system", "content": CASE_STAGE_MODEL_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
            ]
        )
        content = _stringify_content(getattr(response, "content", response))
        try:
            return CaseStageModelDecision.model_validate(extract_json_object(content))
        except (TypeError, ValueError, ValidationError) as exc:
            return CaseStageModelDecision(
                warnings=["模型没有输出有效 CasePatch JSON，已退回 deterministic fallback。"],
                reviewer_message="模型输出无法解析，本轮不让模型写入案卷。",
            ).model_copy(update={"non_action_statement": CASE_HARNESS_NON_ACTION_STATEMENT, "confidence": 0.0, "dossier_patch": "", "turn_intent": "", "patch_type": "", "evidence_decision": "not_evidence"})


def _stringify_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content or "")
