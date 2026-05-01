from __future__ import annotations

from collections import Counter

from src.backend.domains.erp_approval.trace_models import (
    ApprovalAnalyticsSummary,
    ApprovalTraceRecord,
    ApprovalTrendBucket,
    ApprovalTrendSummary,
)


def summarize_traces(records: list[ApprovalTraceRecord]) -> ApprovalAnalyticsSummary:
    if not records:
        return ApprovalAnalyticsSummary(total_traces=0)

    by_approval_type: Counter[str] = Counter()
    by_recommendation_status: Counter[str] = Counter()
    by_review_status: Counter[str] = Counter()
    missing: Counter[str] = Counter()
    risk_flags: Counter[str] = Counter()
    guard_warnings: Counter[str] = Counter()
    proposal_actions: Counter[str] = Counter()
    high_risk_trace_ids: list[str] = []
    human_review_required_count = 0
    guard_downgrade_count = 0
    blocked_proposal_count = 0
    rejected_proposal_count = 0

    for record in records:
        by_approval_type[record.approval_type or "unknown"] += 1
        by_recommendation_status[record.recommendation_status or "unknown"] += 1
        by_review_status[record.review_status or "unknown"] += 1
        if record.human_review_required:
            human_review_required_count += 1
        if record.guard_downgraded:
            guard_downgrade_count += 1
        missing.update(item for item in record.missing_information if item)
        risk_flags.update(item for item in record.risk_flags if item)
        guard_warnings.update(item for item in record.guard_warnings if item)
        proposal_actions.update(item for item in record.proposal_action_types if item)
        blocked_proposal_count += len(record.blocked_proposal_ids)
        rejected_proposal_count += len(record.rejected_proposal_ids)
        if record.risk_flags or record.guard_warnings or record.blocked_proposal_ids or record.recommendation_status in {"blocked", "recommend_reject", "escalate"}:
            high_risk_trace_ids.append(record.trace_id)

    return ApprovalAnalyticsSummary(
        total_traces=len(records),
        by_approval_type=dict(sorted(by_approval_type.items())),
        by_recommendation_status=dict(sorted(by_recommendation_status.items())),
        by_review_status=dict(sorted(by_review_status.items())),
        human_review_required_count=human_review_required_count,
        guard_downgrade_count=guard_downgrade_count,
        top_missing_information=_top_counter(missing),
        top_risk_flags=_top_counter(risk_flags),
        top_guard_warnings=_top_counter(guard_warnings),
        proposal_action_type_counts=dict(sorted(proposal_actions.items())),
        blocked_proposal_count=blocked_proposal_count,
        rejected_proposal_count=rejected_proposal_count,
        high_risk_trace_ids=high_risk_trace_ids[:50],
    )


def summarize_trace_trends(records: list[ApprovalTraceRecord]) -> ApprovalTrendSummary:
    grouped: dict[str, list[ApprovalTraceRecord]] = {}
    for record in records:
        bucket = (record.created_at or "unknown")[:10] or "unknown"
        grouped.setdefault(bucket, []).append(record)

    buckets: list[ApprovalTrendBucket] = []
    for bucket, bucket_records in sorted(grouped.items()):
        recommendation_status: Counter[str] = Counter()
        review_status: Counter[str] = Counter()
        human_review_required_count = 0
        guard_downgrade_count = 0
        blocked_proposal_count = 0
        rejected_proposal_count = 0
        for record in bucket_records:
            recommendation_status[record.recommendation_status or "unknown"] += 1
            review_status[record.review_status or "unknown"] += 1
            if record.human_review_required:
                human_review_required_count += 1
            if record.guard_downgraded:
                guard_downgrade_count += 1
            blocked_proposal_count += len(record.blocked_proposal_ids)
            rejected_proposal_count += len(record.rejected_proposal_ids)
        buckets.append(
            ApprovalTrendBucket(
                bucket=bucket,
                total_traces=len(bucket_records),
                human_review_required_count=human_review_required_count,
                guard_downgrade_count=guard_downgrade_count,
                blocked_proposal_count=blocked_proposal_count,
                rejected_proposal_count=rejected_proposal_count,
                by_recommendation_status=dict(sorted(recommendation_status.items())),
                by_review_status=dict(sorted(review_status.items())),
            )
        )
    return ApprovalTrendSummary(buckets=buckets)


def _top_counter(counter: Counter[str], *, limit: int = 10) -> list[dict[str, int | str]]:
    return [{"item": item, "count": count} for item, count in counter.most_common(limit)]
