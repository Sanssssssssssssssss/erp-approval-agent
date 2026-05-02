from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from src.backend.domains.erp_approval.action_proposals import build_action_proposals, render_action_proposals, validate_action_proposals
from src.backend.domains.erp_approval.case_review import (
    adversarial_review_case,
    build_case_file_from_request_context,
    draft_recommendation_from_case,
    render_case_analysis,
)
from src.backend.domains.erp_approval.schemas import ApprovalContextBundle, ApprovalContextRecord, ApprovalRequest
from src.backend.domains.erp_approval.service import guard_recommendation, parse_approval_request
from src.backend.domains.erp_approval.strict_case_auditor import audit_case, render_strict_audit_report, summarize_audit_results


def main() -> int:
    parser = argparse.ArgumentParser(description="Run strict local evidence-first ERP approval toy case audit.")
    parser.add_argument("--cases", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--json", required=True)
    args = parser.parse_args()

    cases = load_cases(Path(args.cases))
    observed_items: list[dict[str, Any]] = []
    results = []
    for case in cases:
        observed = run_case(case)
        observed_items.append({"case_id": case.get("case_id"), "observed": observed})
        results.append(audit_case(case, observed))
    summary = summarize_audit_results(results, cases)
    report = _render_report_with_metadata(summary, cases)

    report_path = Path(args.report)
    json_path = Path(args.json)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "summary": summary.model_dump(),
                "cases": cases,
                "observed": observed_items,
                "non_action_statement": "Strict toy audit only. No ERP write action was executed.",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"cases={len(cases)} passed={summary.passed_cases} failed={summary.failed_cases} critical={summary.critical_count} major={summary.major_count}")
    return 0 if summary.critical_count == 0 else 2


def load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases", payload) if isinstance(payload, dict) else payload
    if not isinstance(cases, list):
        raise ValueError("Toy case dataset must be a list or an object with a cases list.")
    return [dict(item) for item in cases if isinstance(item, dict)]


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    request = _request_from_case(case)
    context = _context_from_case(case)
    case_file = build_case_file_from_request_context(request, context)
    recommendation = draft_recommendation_from_case(case_file)
    case_file, recommendation = adversarial_review_case(case_file, recommendation)
    recommendation, guard = guard_recommendation(request, context, recommendation)
    review_status = "requested" if recommendation.human_review_required or guard.human_review_required else "not_required"
    action_bundle = build_action_proposals(request, context, recommendation, guard, review_status)
    action_bundle, action_validation = validate_action_proposals(request, context, action_bundle)
    final_answer = "\n\n".join(
        [
            "No ERP write action was executed.",
            render_case_analysis(case_file, recommendation, guard),
            render_action_proposals(action_bundle, action_validation),
            "No ERP write action was executed.",
        ]
    )
    return {
        "case_file": case_file.model_dump(),
        "evidence_requirements": [item.model_dump() for item in case_file.evidence_requirements],
        "evidence_claims": [item.model_dump() for item in case_file.evidence_claims],
        "evidence_sufficiency": case_file.evidence_sufficiency.model_dump(),
        "contradictions": case_file.contradictions.model_dump(),
        "control_matrix": {
            "passed": not any(check.status in {"fail", "missing", "conflict"} for check in case_file.control_checks),
            "checks": [item.model_dump() for item in case_file.control_checks],
            "failed_check_ids": [check.check_id for check in case_file.control_checks if check.status == "fail"],
            "missing_check_ids": [check.check_id for check in case_file.control_checks if check.status == "missing"],
            "conflict_check_ids": [check.check_id for check in case_file.control_checks if check.status == "conflict"],
        },
        "adversarial_review": case_file.adversarial_review.model_dump(),
        "recommendation": recommendation.model_dump(),
        "guard_result": guard.model_dump(),
        "action_proposals": action_bundle.model_dump(),
        "action_validation": action_validation.model_dump(),
        "final_answer_preview": final_answer[:4000],
        "non_action_statement": "No ERP write action was executed.",
    }


def _request_from_case(case: dict[str, Any]) -> ApprovalRequest:
    user_message = str(case.get("user_message") or "")
    request = parse_approval_request("", user_message)
    approval_id = str(case.get("approval_id") or request.approval_id or _id_from_message(user_message) or case.get("case_id") or "")
    updates = {
        "approval_type": str(case.get("approval_type") or request.approval_type or "unknown"),
        "approval_id": approval_id,
        "raw_request": user_message,
    }
    for field in ("requester", "department", "amount", "currency", "vendor", "cost_center", "business_purpose"):
        if field in case:
            updates[field] = case[field]
    return request.model_copy(update=updates)


def _context_from_case(case: dict[str, Any]) -> ApprovalContextBundle:
    records: list[ApprovalContextRecord] = []
    for item in case.get("provided_context_records") or []:
        if isinstance(item, dict):
            records.append(ApprovalContextRecord.model_validate(item))
    case_id = str(case.get("case_id") or "case")
    for index, item in enumerate(case.get("provided_attachments") or []):
        if not isinstance(item, dict):
            continue
        records.append(
            ApprovalContextRecord(
                source_id=str(item.get("source_id") or f"toy_attachment://{case_id}/{index}"),
                title=str(item.get("title") or f"Toy attachment {index}"),
                record_type=str(item.get("artifact_type") or item.get("record_type") or "mock_document"),
                content=str(item.get("content") or ""),
                metadata=dict(item.get("metadata") or {}),
            )
        )
    return ApprovalContextBundle(request_id=str(case.get("approval_id") or case_id), records=records)


def _id_from_message(message: str) -> str:
    match = re.search(r"\b(?:PR|EXP|INV|VEND|CON|BUD|ADV)-[A-Z0-9-]+\b", message, re.IGNORECASE)
    return match.group(0) if match else ""


def _render_report_with_metadata(summary, cases: list[dict[str, Any]]) -> str:
    composition = Counter(str(case.get("approval_type") or "unknown") for case in cases)
    tags = Counter(tag for case in cases for tag in case.get("tags") or [])
    base = render_strict_audit_report(summary)
    header = [
        "# Evidence-First ERP Approval Toy Case Audit",
        "",
        "## Dataset Composition",
        "",
        f"- Total toy cases: {len(cases)}",
        f"- By approval type: {dict(sorted(composition.items()))}",
        f"- Top tags: {dict(tags.most_common(20))}",
        "",
        "## What The Agent Did Wrong",
        "",
        "The strict audit records every failed assertion and traces it to a graph/domain stage. A pass means the local deterministic evidence-first pipeline met the expected toy-case boundary; it does not mean production approval correctness.",
        "",
        "## Fixes Applied In This Task",
        "",
        "- Round 1: fixed non-action preview placement, narrowed policy-specific evidence mapping, converted contract records into explicit contract evidence, and routed contract/budget exceptions to legal/finance review instead of `recommend_approve`.",
        "- Round 2: distinguished budget/vendor status fields in contradiction detection, treated blocked vendor profile evidence as conflict, made invoice payment terms and supplier legal documents required evidence, and added supplier risk-clear control coverage.",
        "- Round 3: fixed `_claim_if(False)` so absent fields no longer create supported claims, tightened finance-review policy mapping, made contract payment terms required, and corrected adversarial conflict fixtures without weakening expectations.",
        "- Added strict auditor root-cause tracing, local toy case audit runner, 82 fictional toy cases, generated audit reports, and regression tests.",
        "",
        "## Why This Is Not Production ERP Automation",
        "",
        "No real ERP connector, real network call, real LLM call, capability invocation, or ERP write action is used. Toy cases are fictional regression/self-critique inputs, not benchmark proof.",
        "",
    ]
    return "\n".join(header) + "\n" + base


if __name__ == "__main__":
    raise SystemExit(main())
