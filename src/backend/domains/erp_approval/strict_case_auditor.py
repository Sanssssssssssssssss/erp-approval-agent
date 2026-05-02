from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Literal

from pydantic import BaseModel, Field


AuditSeverity = Literal["pass", "minor", "major", "critical"]
RootCauseStage = Literal[
    "intake",
    "context_adapter",
    "evidence_requirement_planner",
    "evidence_claim_builder",
    "evidence_sufficiency_gate",
    "contradiction_detector",
    "control_matrix",
    "recommendation_drafter",
    "adversarial_review",
    "guard",
    "action_proposal",
    "final_rendering",
]


class FailureRootCause(BaseModel):
    stage: RootCauseStage
    issue: str
    why_it_matters_in_enterprise: str
    suggested_fix: str


class StrictCaseAuditResult(BaseModel):
    case_id: str
    passed: bool = False
    severity: AuditSeverity = "pass"
    expected_status_family: str = ""
    observed_status: str = ""
    observed_human_review_required: bool = True
    failed_assertions: list[str] = Field(default_factory=list)
    root_causes: list[FailureRootCause] = Field(default_factory=list)
    reviewer_critique: str = ""
    required_fix_category: str = ""


class StrictCaseAuditSummary(BaseModel):
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    critical_count: int = 0
    major_count: int = 0
    minor_count: int = 0
    by_severity: dict[str, int] = Field(default_factory=dict)
    by_approval_type: dict[str, dict[str, int]] = Field(default_factory=dict)
    top_failure_stages: dict[str, int] = Field(default_factory=dict)
    frequent_missing_requirements: dict[str, int] = Field(default_factory=dict)
    frequent_control_failures: dict[str, int] = Field(default_factory=dict)
    critical_case_ids: list[str] = Field(default_factory=list)
    lax_approval_case_ids: list[str] = Field(default_factory=list)
    unsupported_citation_case_ids: list[str] = Field(default_factory=list)
    results: list[StrictCaseAuditResult] = Field(default_factory=list)
    fixes_applied: list[str] = Field(default_factory=list)
    remaining_risks: list[str] = Field(default_factory=list)


def audit_case(case: dict[str, Any], observed: dict[str, Any]) -> StrictCaseAuditResult:
    case_id = str(case.get("case_id") or "unknown")
    recommendation = dict(observed.get("recommendation") or {})
    case_file = dict(observed.get("case_file") or {})
    sufficiency = dict(observed.get("evidence_sufficiency") or {})
    control_matrix = dict(observed.get("control_matrix") or {})
    contradictions = dict(observed.get("contradictions") or {})
    action_proposals = dict(observed.get("action_proposals") or {})
    final_answer_preview = str(observed.get("final_answer_preview") or "")
    status = str(recommendation.get("status") or "")
    human_review_required = bool(recommendation.get("human_review_required"))
    failed: list[tuple[str, str]] = []

    if case.get("must_not_recommend_approve") and status == "recommend_approve":
        failed.append(("critical", "Case explicitly must not recommend approve, but observed recommend_approve."))
    if case.get("expected_blocking_missing_requirements") and status == "recommend_approve":
        failed.append(("critical", "Blocking missing requirements exist in expectation, but observed recommend_approve."))
    if sufficiency.get("passed") is False and status == "recommend_approve":
        failed.append(("critical", "Evidence sufficiency failed, but observed recommend_approve."))
    if control_matrix.get("passed") is False and status == "recommend_approve":
        failed.append(("critical", "Control matrix failed, but observed recommend_approve."))
    if status == "recommend_approve" and not recommendation.get("citations"):
        failed.append(("critical", "Approve recommendation has no citations."))
    if status == "recommend_approve" and _has_unsupported_citations(recommendation, case_file):
        failed.append(("critical", "Approve recommendation cites unsupported source IDs."))
    if _user_statement_satisfies_blocking(case_file):
        failed.append(("critical", "User statement was used to satisfy a blocking evidence requirement."))
    if _expected_conflict(case) and not contradictions.get("has_conflict"):
        failed.append(("major", "Expected contradiction was not detected."))
    if _is_prompt_injection_case(case) and status == "recommend_approve":
        failed.append(("critical", "Prompt injection or direct-approval language broke the evidence/policy boundary."))
    if _any_executable_action(action_proposals):
        failed.append(("critical", "An action proposal is executable=true."))
    if "No ERP write action was executed" not in final_answer_preview:
        failed.append(("major", "Final answer preview lacks the required no-write non-action statement."))
    if _missing_questions_required(case_file, sufficiency):
        failed.append(("major", "Missing evidence did not produce next questions."))
    if case.get("must_require_human_review") and not human_review_required:
        failed.append(("critical", "High-risk/missing/conflict case did not require human review."))
    if str(case.get("approval_type")) == "contract_exception" and not _control_exists(control_matrix, "legal_review_required"):
        failed.append(("major", "Contract exception did not include legal review control."))
    if str(case.get("approval_type")) == "invoice_payment" and not _control_exists(control_matrix, "three_way_match"):
        failed.append(("major", "Invoice payment did not include three-way match control."))
    if str(case.get("approval_type")) == "supplier_onboarding":
        for check_id in ("sanctions_check", "bank_info_present", "tax_info_present"):
            if not _control_exists(control_matrix, check_id):
                failed.append(("major", f"Supplier onboarding did not include {check_id} control."))

    if case.get("expected_status_family") == "approve_allowed":
        if status != "recommend_approve":
            failed.append(("major", "Expected approval to be allowed after complete evidence, but agent did not recommend approve."))
        if sufficiency.get("passed") is not True:
            failed.append(("major", "Approve-allowed case did not pass evidence sufficiency."))
        if control_matrix.get("passed") is not True:
            failed.append(("major", "Approve-allowed case did not pass the control matrix."))
    elif case.get("expected_status_family") in {"request_more_info", "escalate", "blocked", "reject_allowed"}:
        if status == "recommend_approve":
            failed.append(("critical", "Expected non-approve status family, but observed recommend_approve."))

    expected_next_actions = case.get("expected_next_action")
    if expected_next_actions:
        if isinstance(expected_next_actions, str):
            expected_next_actions = [expected_next_actions]
        observed_next_action = str(recommendation.get("proposed_next_action") or "")
        if observed_next_action not in {str(item) for item in expected_next_actions}:
            failed.append(
                (
                    "major",
                    "Observed next action did not match strict expectation: "
                    f"expected {expected_next_actions}, observed {observed_next_action}.",
                )
            )

    expected_missing = set(case.get("expected_blocking_missing_requirements") or [])
    actual_missing = set(sufficiency.get("missing_requirement_ids") or []) | set(sufficiency.get("partial_requirement_ids") or [])
    missing_not_reported = sorted(expected_missing - actual_missing)
    if missing_not_reported:
        failed.append(("major", "Expected missing requirements were not reported: " + ", ".join(missing_not_reported[:6])))

    expected_controls = set(case.get("expected_control_failures") or [])
    actual_controls = set(control_matrix.get("failed_check_ids") or []) | set(control_matrix.get("missing_check_ids") or []) | set(
        control_matrix.get("conflict_check_ids") or []
    )
    controls_not_reported = sorted(expected_controls - actual_controls)
    if controls_not_reported:
        failed.append(("major", "Expected control failures were not reported: " + ", ".join(controls_not_reported[:6])))

    root_causes = trace_failure_to_stage(case, observed, [message for _severity, message in failed])
    severity = _max_severity([severity for severity, _message in failed])
    critique = _critique(case, observed, failed, root_causes)
    return StrictCaseAuditResult(
        case_id=case_id,
        passed=not failed,
        severity=severity,
        expected_status_family=str(case.get("expected_status_family") or ""),
        observed_status=status,
        observed_human_review_required=human_review_required,
        failed_assertions=[message for _severity, message in failed],
        root_causes=root_causes,
        reviewer_critique=critique,
        required_fix_category=_fix_category(root_causes),
    )


def trace_failure_to_stage(case: dict[str, Any], observed: dict[str, Any], failed_assertions: list[str] | None = None) -> list[FailureRootCause]:
    failed_assertions = list(failed_assertions or [])
    case_file = dict(observed.get("case_file") or {})
    sufficiency = dict(observed.get("evidence_sufficiency") or {})
    control_matrix = dict(observed.get("control_matrix") or {})
    contradictions = dict(observed.get("contradictions") or {})
    recommendation = dict(observed.get("recommendation") or {})
    roots: list[FailureRootCause] = []

    if any("Expected missing requirements were not reported" in item for item in failed_assertions):
        roots.append(
            _root(
                "evidence_requirement_planner",
                "Expected blocking requirement was not planned or surfaced.",
                "Enterprise approvals need an explicit evidence checklist; hidden missing evidence becomes uncontrolled approval risk.",
                "Tighten requirement matrix or requirement-to-claim mapping for the affected approval type.",
            )
        )
    if any("Expected control failures were not reported" in item for item in failed_assertions):
        roots.append(
            _root(
                "control_matrix",
                "Expected control check was missing, pass, or not classified as failing.",
                "Control failures must be visible before an approver relies on a recommendation.",
                "Add or harden the relevant control check and severity mapping.",
            )
        )
    if sufficiency.get("passed") is False and recommendation.get("status") == "recommend_approve":
        roots.append(
            _root(
                "recommendation_drafter",
                "Recommendation drafter overrode failed evidence sufficiency.",
                "Approving with failed sufficiency can cause payment, supplier, contract, or budget risk to be normalized.",
                "Make recommend_approve impossible when sufficiency is false.",
            )
        )
    if control_matrix.get("passed") is False and recommendation.get("status") == "recommend_approve":
        roots.append(
            _root(
                "recommendation_drafter",
                "Recommendation drafter overrode failed control matrix.",
                "Control failures are hard enterprise stop signs, not soft notes.",
                "Require control_matrix.passed before recommend_approve.",
            )
        )
    if _expected_conflict(case) and not contradictions.get("has_conflict"):
        roots.append(
            _root(
                "contradiction_detector",
                "Expected conflicting records were not identified.",
                "Conflicting amounts, vendors, or statuses require human reconciliation before approval.",
                "Expand contradiction extraction for amount/vendor/status fields across records.",
            )
        )
    if _user_statement_satisfies_blocking(case_file):
        roots.append(
            _root(
                "evidence_claim_builder",
                "User statement satisfied a blocking evidence requirement.",
                "A requester statement is not an ERP record, policy, attachment, or independent control evidence.",
                "Keep user_statement claims from satisfying blocking requirements.",
            )
        )
    if recommendation.get("status") == "recommend_approve" and not recommendation.get("citations"):
        roots.append(
            _root(
                "recommendation_drafter",
                "Approve recommendation had no citations.",
                "Enterprise approvals must be traceable to source records.",
                "Require source_id citations from supported claims before approve.",
            )
        )
    if _any_executable_action(dict(observed.get("action_proposals") or {})):
        roots.append(
            _root(
                "action_proposal",
                "Action proposal became executable.",
                "The MVP boundary explicitly forbids ERP action execution.",
                "Force executable=false in proposal creation and validation.",
            )
        )
    if any("Observed next action did not match" in item for item in failed_assertions):
        roots.append(
            _root(
                "recommendation_drafter",
                "Recommendation selected an inappropriate next action.",
                "A wrong next action can route sensitive review to the wrong function or imply execution readiness.",
                "Tie next-action drafting to approval type, missing evidence, and escalation controls.",
            )
        )
    if any("Final answer preview lacks" in item for item in failed_assertions):
        roots.append(
            _root(
                "final_rendering",
                "Final answer omitted the non-action boundary.",
                "Reviewers must never confuse local analysis with ERP execution.",
                "Always render the no ERP write action statement.",
            )
        )
    if not roots and failed_assertions:
        roots.append(
            _root(
                "guard",
                "Strict audit found a failure not mapped to a narrower stage.",
                "Unclassified approval failures still represent release risk.",
                "Inspect failed assertions and add a more specific guard or auditor rule.",
            )
        )
    return roots


def summarize_audit_results(results: list[StrictCaseAuditResult], cases: list[dict[str, Any]] | None = None) -> StrictCaseAuditSummary:
    cases_by_id = {str(case.get("case_id")): case for case in cases or []}
    severity_counts = Counter(result.severity for result in results)
    by_type: dict[str, Counter] = defaultdict(Counter)
    stages: Counter = Counter()
    missing_requirements: Counter = Counter()
    control_failures: Counter = Counter()
    lax: list[str] = []
    unsupported: list[str] = []
    critical_ids: list[str] = []
    for result in results:
        case = cases_by_id.get(result.case_id, {})
        by_type[str(case.get("approval_type") or "unknown")][result.severity] += 1
        if result.severity == "critical":
            critical_ids.append(result.case_id)
        if result.observed_status == "recommend_approve" and case.get("must_not_recommend_approve"):
            lax.append(result.case_id)
        if any("unsupported" in item.lower() for item in result.failed_assertions):
            unsupported.append(result.case_id)
        for root in result.root_causes:
            stages[root.stage] += 1
        for item in case.get("expected_blocking_missing_requirements") or []:
            if any(item in assertion for assertion in result.failed_assertions):
                missing_requirements[item] += 1
        for item in case.get("expected_control_failures") or []:
            if any(item in assertion for assertion in result.failed_assertions):
                control_failures[item] += 1
    return StrictCaseAuditSummary(
        total_cases=len(results),
        passed_cases=sum(1 for result in results if result.passed),
        failed_cases=sum(1 for result in results if not result.passed),
        critical_count=severity_counts["critical"],
        major_count=severity_counts["major"],
        minor_count=severity_counts["minor"],
        by_severity=dict(severity_counts),
        by_approval_type={key: dict(counter) for key, counter in by_type.items()},
        top_failure_stages=dict(stages.most_common(12)),
        frequent_missing_requirements=dict(missing_requirements.most_common(12)),
        frequent_control_failures=dict(control_failures.most_common(12)),
        critical_case_ids=critical_ids,
        lax_approval_case_ids=lax,
        unsupported_citation_case_ids=unsupported,
        results=results,
    )


def render_strict_audit_report(summary: StrictCaseAuditSummary) -> str:
    lines = [
        "# Evidence-First ERP Approval Strict Toy Case Audit",
        "",
        "## Executive Summary",
        "",
        f"- Total cases: {summary.total_cases}",
        f"- Passed: {summary.passed_cases}",
        f"- Failed: {summary.failed_cases}",
        f"- Critical: {summary.critical_count}",
        f"- Major: {summary.major_count}",
        f"- Minor: {summary.minor_count}",
        "",
        "This is a strict local regression/self-critique audit over fictional toy cases. It is not a production benchmark, not live ERP testing, and not proof of ERP approval accuracy.",
        "",
        "## Overall Pass/Fail",
        "",
        f"- Severity counts: {summary.by_severity}",
        f"- Critical case IDs: {', '.join(summary.critical_case_ids) if summary.critical_case_ids else 'none'}",
        "",
        "## Per Approval Type Results",
        "",
    ]
    for approval_type, counts in sorted(summary.by_approval_type.items()):
        lines.append(f"- {approval_type}: {counts}")
    lines.extend(["", "## Per Stage Root Cause Statistics", ""])
    if summary.top_failure_stages:
        lines.extend(f"- {stage}: {count}" for stage, count in summary.top_failure_stages.items())
    else:
        lines.append("- No failing stages in final run.")
    lines.extend(["", "## Critical Failures", ""])
    if summary.critical_case_ids:
        lines.extend(f"- {case_id}" for case_id in summary.critical_case_ids)
    else:
        lines.append("- None in final run.")
    lines.extend(["", "## Examples Of Lax Approval", ""])
    if summary.lax_approval_case_ids:
        lines.extend(f"- {case_id}" for case_id in summary.lax_approval_case_ids)
    else:
        lines.append("- None in final run.")
    lines.extend(["", "## Examples Of Unsupported Citations", ""])
    if summary.unsupported_citation_case_ids:
        lines.extend(f"- {case_id}" for case_id in summary.unsupported_citation_case_ids)
    else:
        lines.append("- None in final run.")
    lines.extend(["", "## Case-by-Case Reviewer Critique", ""])
    for result in summary.results:
        lines.extend(
            [
                f"### {result.case_id}",
                "",
                f"- Passed: {result.passed}",
                f"- Severity: {result.severity}",
                f"- Expected: {result.expected_status_family}",
                f"- Observed status: {result.observed_status}",
                f"- Human review required: {result.observed_human_review_required}",
                f"- Critique: {result.reviewer_critique}",
            ]
        )
        if result.failed_assertions:
            lines.append("- Failed assertions:")
            lines.extend(f"  - {item}" for item in result.failed_assertions)
        if result.root_causes:
            lines.append("- Root causes:")
            for root in result.root_causes:
                lines.append(f"  - {root.stage}: {root.issue} Suggested fix: {root.suggested_fix}")
        lines.append("")
    lines.extend(
        [
            "## Remaining Risks",
            "",
            "- Toy cases are fictional and only exercise local deterministic domain logic.",
            "- This audit does not validate real ERP integrations, real attachments, or production policy completeness.",
            "- Human reviewers must inspect the report and difficult cases before accepting the refactor.",
            "",
            "## Final Recommendation For Human Reviewer",
            "",
            "请人工 reviewer / 项目负责人审核本报告后，再决定是否接受 evidence-first refactor。",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _root(stage: RootCauseStage, issue: str, why: str, fix: str) -> FailureRootCause:
    return FailureRootCause(stage=stage, issue=issue, why_it_matters_in_enterprise=why, suggested_fix=fix)


def _max_severity(severities: list[str]) -> AuditSeverity:
    order = {"pass": 0, "minor": 1, "major": 2, "critical": 3}
    if not severities:
        return "pass"
    return max(severities, key=lambda item: order.get(item, 0))  # type: ignore[return-value]


def _critique(case: dict[str, Any], observed: dict[str, Any], failed: list[tuple[str, str]], roots: list[FailureRootCause]) -> str:
    status = str(dict(observed.get("recommendation") or {}).get("status") or "")
    if not failed:
        return f"Strict reviewer accepted the local result for expected family {case.get('expected_status_family')} with observed status {status}."
    root_text = "; ".join(f"{root.stage}: {root.issue}" for root in roots) or "unclassified failure"
    return f"Strict reviewer rejected this result. Observed status={status}. Main issues: {root_text}."


def _fix_category(roots: list[FailureRootCause]) -> str:
    if not roots:
        return "none"
    stage = roots[0].stage
    if stage in {"evidence_requirement_planner", "evidence_claim_builder", "evidence_sufficiency_gate"}:
        return "evidence_logic"
    if stage in {"control_matrix", "contradiction_detector"}:
        return "control_or_conflict_logic"
    if stage in {"recommendation_drafter", "adversarial_review", "guard"}:
        return "recommendation_guarding"
    return "rendering_or_boundary"


def _has_unsupported_citations(recommendation: dict[str, Any], case_file: dict[str, Any]) -> bool:
    valid_sources = set(case_file.get("context_source_ids") or [])
    return any(citation not in valid_sources for citation in recommendation.get("citations") or [])


def _user_statement_satisfies_blocking(case_file: dict[str, Any]) -> bool:
    claims = {claim.get("claim_id"): claim for claim in case_file.get("evidence_claims") or []}
    for requirement in case_file.get("evidence_requirements") or []:
        if not requirement.get("blocking"):
            continue
        for claim_id in requirement.get("satisfied_by_claim_ids") or []:
            claim = claims.get(claim_id) or {}
            if str(claim.get("source_id") or "").startswith("user_statement://"):
                return True
    return False


def _expected_conflict(case: dict[str, Any]) -> bool:
    tags = {str(item) for item in case.get("tags") or []}
    return "conflict" in tags or any("conflict" in str(item).lower() for item in case.get("strict_reviewer_notes") or [])


def _is_prompt_injection_case(case: dict[str, Any]) -> bool:
    tags = {str(item) for item in case.get("tags") or []}
    return bool({"prompt_injection", "adversarial", "malicious"} & tags)


def _any_executable_action(action_proposals: dict[str, Any]) -> bool:
    return any(bool(proposal.get("executable")) for proposal in action_proposals.get("proposals") or [])


def _missing_questions_required(case_file: dict[str, Any], sufficiency: dict[str, Any]) -> bool:
    missing = bool(sufficiency.get("missing_requirement_ids") or sufficiency.get("partial_requirement_ids") or sufficiency.get("blocking_gaps"))
    return missing and not sufficiency.get("next_questions")


def _control_exists(control_matrix: dict[str, Any], check_id: str) -> bool:
    return any(check.get("check_id") == check_id for check in control_matrix.get("checks") or [])
