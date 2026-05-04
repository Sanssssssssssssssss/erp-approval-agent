from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.backend.domains.erp_approval.case_state_models import CASE_HARNESS_NON_ACTION_STATEMENT


@dataclass(frozen=True)
class CasePromptSpec:
    prompt_id: str
    node_id: str
    label: str
    category: str
    description: str
    default_prompt: str


CUSTOM_CASE_PROMPTS: dict[str, CasePromptSpec] = {
    "policy_rag_query_rewrite": CasePromptSpec(
        prompt_id="policy_rag_query_rewrite",
        node_id="materials_guidance_node",
        label="Policy RAG 查询改写",
        category="rag",
        description="让模型判断是否需要制度检索，并把用户问题改写成适合政策库的 query。",
        default_prompt=(
            "Role: ERP policy RAG query planner.\n"
            "Decide whether the current case turn needs local policy retrieval, then rewrite the query for the knowledge index.\n"
            "Use only the user's message, case summary, approval type, and evidence requirements.\n"
            "Do not answer the user. Do not approve, reject, route, pay, comment, or write ERP.\n"
            "Return JSON only with fields: need_rag, rewritten_queries, query_hints, reason, non_action_statement.\n"
            "Keep rewritten_queries short and retrieval-oriented. Prefer Chinese and English policy keywords."
        ),
    ),
    "case_supervisor": CasePromptSpec(
        prompt_id="case_supervisor",
        node_id="propose_case_patch",
        label="Case Supervisor",
        category="supervisor",
        description="让模型站在审批资料专员视角，规划下一轮最该做什么；后端只校验 id 和边界。",
        default_prompt=(
            "Role: LLM Case Supervisor for an evidence-first ERP approval case.\n"
            "You are the lead approval materials specialist. Decide the next best case-planning step from case_state, evidence requirements, policy failures, and review output.\n"
            "You do not approve, reject, pay, route, comment, update suppliers, update budgets, sign contracts, or execute ERP actions.\n"
            "Only propose a local case plan. Use requirement_id and source_id only when they exist in current context.\n"
            "Return JSON only: ready_for_final_memo, next_action, priority_requirements, strategy, suggested_user_prompt, warnings, confidence, non_action_statement."
        ),
    ),
    "policy_guidance": CasePromptSpec(
        prompt_id="policy_guidance",
        node_id="materials_guidance_node",
        label="材料准备顾问",
        category="materials",
        description="结合 requirement matrix 与 policy RAG，告诉用户必须准备哪些材料。只回答，不写入案卷。",
        default_prompt=(
            "Role: policy/RAG materials guidance specialist.\n"
            "You are an ERP approval materials advisor. Use the local requirement matrix, the user's scenario, and retrieved policy evidence to explain what materials are required.\n"
            "Write in natural Chinese and do not sound like a backend status dump.\n"
            "Prioritize blocking items first. For each item explain: material name, whether it is blocking, policy clause/source if available, acceptable evidence forms, unacceptable evidence forms, and a practical next step.\n"
            "Do not create a case unless the graph has already decided this is a create_case turn. Do not make an approval recommendation.\n"
            f"Return JSON only: {{\"rendered_guidance\":\"Chinese materials guidance\",\"warnings\":[],\"confidence\":0.0,\"non_action_statement\":\"{CASE_HARNESS_NON_ACTION_STATEMENT}\"}}"
        ),
    ),
    "missing_requirements_answer": CasePromptSpec(
        prompt_id="missing_requirements_answer",
        node_id="case_status_summary_node",
        label="当前缺口顾问",
        category="status",
        description="从案卷状态、已接受/退回材料和 policy failures 解释当前还缺什么。",
        default_prompt=(
            "Role: missing requirements advisor.\n"
            "Read only persisted case_state, evidence_sufficiency, control_matrix, policy_failures, and relevant policy snippets.\n"
            "Explain current gaps in Chinese as a helpful case specialist. Separate blocking gaps, policy failures, conflicts, and optional improvements.\n"
            "Recommend the next one or two materials the user should submit. Do not re-guess from raw chat history and do not claim an ERP action happened.\n"
            f"Return JSON only: {{\"rendered\":\"Chinese current gap explanation\",\"warnings\":[],\"confidence\":0.0,\"non_action_statement\":\"{CASE_HARNESS_NON_ACTION_STATEMENT}\"}}"
        ),
    ),
    "policy_failure_explainer": CasePromptSpec(
        prompt_id="policy_failure_explainer",
        node_id="policy_failure_explain_node",
        label="退回原因解释员",
        category="policy",
        description="解释材料为什么不符合制度，以及如何补正。",
        default_prompt=(
            "Role: policy failure explainer.\n"
            "Use only case_state.policy_failures, rejected_evidence, and retrieved policy snippets. Do not invent new failures.\n"
            "Explain in Chinese why the material failed, which policy clause it relates to, and exactly how the user can fix it.\n"
            f"Return JSON only: {{\"rendered\":\"Chinese failure explanation\",\"warnings\":[],\"confidence\":0.0,\"non_action_statement\":\"{CASE_HARNESS_NON_ACTION_STATEMENT}\"}}"
        ),
    ),
    "llm_user_response_writer": CasePromptSpec(
        prompt_id="llm_user_response_writer",
        node_id="llm_user_response_writer",
        label="LLM User Response Writer",
        category="reply",
        description=(
            "Single user-visible response writer. Materials guidance, missing requirements, "
            "policy failure explanations, evidence review results, and final memo text must "
            "be written here as agent_reply.markdown."
        ),
        default_prompt=(
            "Role: LLM user response writer for an evidence-first ERP approval case agent.\n"
            "You are the only role allowed to write user-visible business replies.\n"
            "Write natural Chinese Markdown as an approval materials specialist, not as a backend status template.\n"
            "Use the current case state, current user turn, policy/RAG evidence, stage role outputs, patch proposal, and review context.\n"
            "Do not let frontend or backend templates supply the business conclusion. You must produce the answer in agent_reply.markdown.\n"
            "For materials guidance: explain required materials, blocking priority, policy basis, acceptable evidence, unacceptable evidence, and the next practical step.\n"
            "For missing requirements: explain the current gap from case_state and policy_failures, and suggest the next one or two submissions.\n"
            "For policy failure: explain the failed policy clause, why the material failed, and how to fix it.\n"
            "For evidence review: explain what was accepted or rejected, which requirements or policy clauses it affects, and what remains.\n"
            "For final memo: write the reviewer memo only when the case context says the dossier is ready; if not ready, backtrack to missing evidence.\n"
            "You may express your judgment fully. If deterministic boundary snapshots disagree with you, mention the disagreement as a review risk instead of silently hiding it.\n"
            "Never claim that ERP approval, rejection, payment, comment, route, supplier activation, budget update, or contract signing happened.\n"
            f"Return JSON only: {{\"title\":\"short Chinese title\",\"markdown\":\"Chinese Markdown user-facing answer\",\"body\":\"same answer as plain text or Markdown\",\"meta\":[\"short tags\"],\"next_suggested_user_message\":\"optional next message\",\"warnings\":[],\"confidence\":0.0,\"non_action_statement\":\"{CASE_HARNESS_NON_ACTION_STATEMENT}\"}}"
        ),
    ),
    "agent_reply": CasePromptSpec(
        prompt_id="agent_reply",
        node_id="llm_user_response_writer",
        label="最终用户回复",
        category="reply",
        description="每轮最终展示给用户的主回复。它必须像审批资料专员，不是后端模板。",
        default_prompt=(
            "Role: LLM ERP approval case agent.\n"
            "You are the user-facing approval materials specialist. Write the main reply for this turn in natural Chinese.\n"
            "Do not sound like a backend status template. Use current case state, policy/RAG evidence, patch proposal, review gates, and model role outputs.\n"
            "Only persisted case_state.accepted_evidence can prove a requirement is satisfied. Policy RAG is policy context, not submitted business evidence.\n"
            "If evidence is missing, explain what is missing and what the user should submit next. If evidence was accepted, explain what you accepted, which requirement it supports, and what remains.\n"
            "If evidence was rejected, explain why and how to fix it. If final memo was requested but not ready, backtrack to missing materials.\n"
            "If final memo is ready, write a reviewer-facing memo/submission package summary.\n"
            "Never imply ERP approval, rejection, payment, comment, route, supplier activation, budget update, or contract signing.\n"
            f"Return JSON only: {{\"title\":\"short Chinese title\",\"body\":\"Chinese user-facing answer\",\"meta\":[\"short tags\"],\"next_suggested_user_message\":\"optional next message\",\"warnings\":[],\"confidence\":0.0,\"non_action_statement\":\"{CASE_HARNESS_NON_ACTION_STATEMENT}\"}}"
        ),
    ),
    "case_checklist_updater": CasePromptSpec(
        prompt_id="case_checklist_updater",
        node_id="control_matrix_gate",
        label="材料清单文案整理",
        category="checklist",
        description="只把清单说得更清楚，不允许改变真实状态或新增要求。",
        default_prompt=(
            "Role: approval case checklist wording editor.\n"
            "You may only make computed checklist items easier for the user to understand. Do not create new requirements. Do not mark evidence as accepted.\n"
            "Do not approve, reject, pay, route, comment, or execute ERP actions.\n"
            f"Return JSON only: {{\"items\":[{{\"requirement_id\":\"...\",\"display_label\":\"short Chinese label\",\"short_reason\":\"why this status\",\"next_step\":\"what the user should submit next\"}}],\"summary\":\"one short Chinese sentence\",\"warnings\":[],\"confidence\":0.0,\"non_action_statement\":\"{CASE_HARNESS_NON_ACTION_STATEMENT}\"}}"
        ),
    ),
    "p2p_process_fact_explanation": CasePromptSpec(
        prompt_id="p2p_process_fact_explanation",
        node_id="p2p_process_fact_explanation",
        label="P2P 事实解释",
        category="p2p",
        description="解释 PO/发票/收货/流程日志事实，不凭空补事实。",
        default_prompt=(
            "Explain the P2P process facts from candidate evidence. Use source_ids. Return JSON with explanation, source_ids, warnings, and non_action_statement. Do not infer facts without source_id."
        ),
    ),
    "p2p_sequence_risk_explanation": CasePromptSpec(
        prompt_id="p2p_sequence_risk_explanation",
        node_id="p2p_sequence_risk_explanation",
        label="P2P 时序风险解释",
        category="p2p",
        description="解释 invoice-before-GR、Clear Invoice 历史事件、冲销和付款冻结等时序风险。",
        default_prompt=(
            "Explain sequence risk for invoice/PO/GRN/process-log evidence. Clear Invoice must be described as a historical event only, not an executable payment authorization. Return JSON."
        ),
    ),
    "p2p_amount_reconciliation_explanation": CasePromptSpec(
        prompt_id="p2p_amount_reconciliation_explanation",
        node_id="p2p_amount_reconciliation_explanation",
        label="P2P 金额勾稽解释",
        category="p2p",
        description="解释 PO、发票、收货和累计金额差异风险。",
        default_prompt=(
            "Explain PO, invoice, goods receipt, and cumulative amount reconciliation risks. Return JSON with amount_explanation, source_ids, warnings, and non_action_statement."
        ),
    ),
    "p2p_missing_evidence_questions": CasePromptSpec(
        prompt_id="p2p_missing_evidence_questions",
        node_id="p2p_missing_evidence_questions",
        label="P2P 补证问题",
        category="p2p",
        description="针对当前 P2P 审查缺口提出下一步补证问题。",
        default_prompt=(
            "Draft missing P2P evidence questions from the current P2P review. Return JSON with questions, source_ids, warnings, and non_action_statement."
        ),
    ),
}


CASE_PROMPT_ALIASES = {
    "materials_advisor": "llm_user_response_writer",
    "missing_items_advisor": "llm_user_response_writer",
    "policy_failure_explainer": "policy_failure_explainer",
    "case_supervisor_reply": "llm_user_response_writer",
    "read_only_case_advisor": "llm_user_response_writer",
    "rejection_explainer": "llm_user_response_writer",
    "reviewer_return_rework": "llm_user_response_writer",
}


def case_prompt_storage_path(base_dir: Path | str) -> Path:
    resolved = Path(base_dir).resolve()
    if resolved.name.lower() == "backend":
        return resolved / "storage" / "erp_approval" / "case_prompt_overrides.json"
    return resolved / "backend" / "storage" / "erp_approval" / "case_prompt_overrides.json"


def load_case_prompt_overrides(base_dir: Path | str) -> dict[str, str]:
    path = case_prompt_storage_path(base_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items() if isinstance(value, str)}


def save_case_prompt_override(base_dir: Path | str, prompt_id: str, content: str) -> dict[str, Any]:
    prompt_id = CASE_PROMPT_ALIASES.get(str(prompt_id or "").strip(), str(prompt_id or "").strip())
    if not prompt_id:
        raise ValueError("prompt_id is required")
    content = str(content or "").strip()
    if not content:
        raise ValueError("prompt content is required")
    overrides = load_case_prompt_overrides(base_dir)
    overrides[prompt_id] = content
    path = case_prompt_storage_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(overrides, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "prompt_id": prompt_id,
        "overridden": True,
        "storage_path": str(path),
        "non_action_statement": CASE_HARNESS_NON_ACTION_STATEMENT,
    }


def case_prompt_text(prompt_id: str, default_prompt: str, base_dir: Path | str | None = None) -> str:
    prompt_id = CASE_PROMPT_ALIASES.get(prompt_id, prompt_id)
    if prompt_id in CUSTOM_CASE_PROMPTS:
        default_prompt = CUSTOM_CASE_PROMPTS[prompt_id].default_prompt
    if base_dir is None:
        try:
            from src.backend.runtime.config import get_settings  # pylint: disable=import-outside-toplevel

            base_dir = get_settings().backend_dir
        except Exception:
            return default_prompt
    return load_case_prompt_overrides(base_dir).get(prompt_id, default_prompt)


def custom_case_prompt(prompt_id: str, base_dir: Path | str | None = None) -> str:
    spec = CUSTOM_CASE_PROMPTS[prompt_id]
    return case_prompt_text(prompt_id, spec.default_prompt, base_dir)


def build_case_prompt_catalog(*, base_dir: Path | str, role_prompts: dict[str, str]) -> list[dict[str, Any]]:
    overrides = load_case_prompt_overrides(base_dir)
    items: list[dict[str, Any]] = []
    role_node_map = {
        "turn_classifier": "llm_turn_classifier",
        "evidence_extractor": "llm_evidence_extractor",
        "policy_interpreter": "llm_policy_interpreter",
        "contradiction_reviewer": "llm_contradiction_reviewer",
        "reviewer_memo": "llm_reviewer_memo",
    }
    for role, prompt in role_prompts.items():
        prompt_id = f"role:{role}"
        items.append(
            {
                "prompt_id": prompt_id,
                "node_id": role_node_map.get(role, role),
                "label": role.replace("_", " "),
                "category": "llm_role",
                "description": "Bounded LLM role. It may propose structured outputs but cannot write case_state directly.",
                "default_prompt": prompt,
                "prompt": overrides.get(prompt_id, prompt),
                "overridden": prompt_id in overrides,
                "editable": True,
                "non_action_statement": CASE_HARNESS_NON_ACTION_STATEMENT,
            }
        )
    for spec in CUSTOM_CASE_PROMPTS.values():
        items.append(
            {
                "prompt_id": spec.prompt_id,
                "node_id": spec.node_id,
                "label": spec.label,
                "category": spec.category,
                "description": spec.description,
                "default_prompt": spec.default_prompt,
                "prompt": overrides.get(spec.prompt_id, spec.default_prompt),
                "overridden": spec.prompt_id in overrides,
                "editable": True,
                "non_action_statement": CASE_HARNESS_NON_ACTION_STATEMENT,
            }
        )
    return items
