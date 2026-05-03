from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


P2P_NON_ACTION_STATEMENT = "This is a local P2P evidence review. No ERP write action was executed."

P2PMatchType = Literal[
    "three_way_invoice_after_gr",
    "three_way_invoice_before_gr",
    "two_way",
    "consignment",
    "unknown",
]
P2PSequenceAnomaly = Literal[
    "invoice_before_goods_receipt",
    "clear_invoice_historical_only",
    "reversal_or_cancellation",
    "payment_block_event",
]


class P2PAmountFacts(BaseModel):
    po_amount: float | None = None
    invoice_amount: float | None = None
    goods_receipt_amount: float | None = None
    cumulative_amount_values: list[float] = Field(default_factory=list)
    amount_variation_risk: str = "unknown"


class P2PProcessReview(BaseModel):
    match_type: P2PMatchType = "unknown"
    sequence_anomalies: list[P2PSequenceAnomaly] = Field(default_factory=list)
    amount_facts: P2PAmountFacts = Field(default_factory=P2PAmountFacts)
    process_exceptions: list[str] = Field(default_factory=list)
    missing_process_evidence: list[str] = Field(default_factory=list)
    p2p_next_questions: list[str] = Field(default_factory=list)
    p2p_reviewer_notes: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    non_action_statement: str = P2P_NON_ACTION_STATEMENT
