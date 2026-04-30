from __future__ import annotations

from src.backend.domains.erp_approval.schemas import ApprovalContextBundle, ApprovalContextRecord, ApprovalRequest


def build_mock_context(request: ApprovalRequest) -> ApprovalContextBundle:
    request_id = request.approval_id or "unidentified"
    records = [
        ApprovalContextRecord(
            source_id=f"mock_erp://approval_request/{request_id}",
            title="Submitted approval request",
            record_type="approval_request",
            content=(
                "Mock approval request record assembled from the current user message. "
                "It is not read from a real ERP system."
            ),
            metadata={
                "approval_type": request.approval_type,
                "requester": request.requester,
                "department": request.department,
                "amount": request.amount,
                "currency": request.currency,
                "vendor": request.vendor,
                "cost_center": request.cost_center,
                "business_purpose": request.business_purpose,
            },
        ),
        ApprovalContextRecord(
            source_id="mock_policy://approval_matrix",
            title="Approval matrix",
            record_type="policy",
            content=(
                "Mock approval matrix: low-value requests may be manager-reviewed; "
                "finance review is expected for material budget impact; legal review is expected for contract exceptions."
            ),
        ),
        ApprovalContextRecord(
            source_id="mock_policy://procurement_policy",
            title="Procurement policy",
            record_type="policy",
            content=(
                "Mock procurement policy: purchase requisitions should include vendor, amount, cost center, "
                "business purpose, and evidence that the vendor and budget are acceptable."
            ),
        ),
        ApprovalContextRecord(
            source_id="mock_policy://expense_policy",
            title="Expense policy",
            record_type="policy",
            content=(
                "Mock expense policy: expense approvals should include receipts, business purpose, amount, "
                "department, requester, and manager review for exceptions."
            ),
        ),
        ApprovalContextRecord(
            source_id="mock_policy://supplier_onboarding_policy",
            title="Supplier onboarding policy",
            record_type="policy",
            content=(
                "Mock supplier onboarding policy: onboarding should verify tax, sanctions, banking, ownership, "
                "and required procurement due diligence before any operational use."
            ),
        ),
        ApprovalContextRecord(
            source_id="mock_policy://invoice_payment_policy",
            title="Invoice/payment policy",
            record_type="policy",
            content=(
                "Mock invoice/payment policy: invoice or payment review should compare purchase order, receipt, "
                "invoice amount, vendor identity, payment terms, and approval authority."
            ),
        ),
        ApprovalContextRecord(
            source_id="mock_policy://budget_policy",
            title="Generic budget policy",
            record_type="policy",
            content=(
                "Mock budget policy: budget exceptions or unclear funding require finance review and cannot be "
                "treated as final approval without human confirmation."
            ),
        ),
    ]
    return ApprovalContextBundle(request_id=request_id, records=records)
