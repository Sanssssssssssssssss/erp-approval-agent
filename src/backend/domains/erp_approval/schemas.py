from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ApprovalType = Literal[
    "expense",
    "purchase_requisition",
    "invoice_payment",
    "supplier_onboarding",
    "contract_exception",
    "budget_exception",
    "unknown",
]

ApprovalStatus = Literal[
    "recommend_approve",
    "recommend_reject",
    "request_more_info",
    "escalate",
    "blocked",
]

ApprovalNextAction = Literal[
    "none",
    "request_more_info",
    "route_to_manager",
    "route_to_finance",
    "route_to_procurement",
    "route_to_legal",
    "manual_review",
]


class ApprovalRequest(BaseModel):
    approval_type: ApprovalType = "unknown"
    approval_id: str = ""
    requester: str = ""
    department: str = ""
    amount: float | None = None
    currency: str = ""
    vendor: str = ""
    cost_center: str = ""
    business_purpose: str = ""
    raw_request: str = ""


class ApprovalContextRecord(BaseModel):
    source_id: str
    title: str
    record_type: str = "policy"
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApprovalContextBundle(BaseModel):
    request_id: str = ""
    records: list[ApprovalContextRecord] = Field(default_factory=list)


class ApprovalRecommendation(BaseModel):
    status: ApprovalStatus = "request_more_info"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    summary: str = ""
    rationale: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    proposed_next_action: ApprovalNextAction = "request_more_info"
    human_review_required: bool = True


class ApprovalGuardResult(BaseModel):
    passed: bool = True
    downgraded: bool = False
    original_status: str = ""
    final_status: str = ""
    warnings: list[str] = Field(default_factory=list)
    human_review_required: bool = True
