from __future__ import annotations

import re
from typing import Any

from src.backend.domains.erp_approval.case_review_service import CaseReviewEvidenceInput
from src.backend.domains.erp_approval.p2p_process_models import P2PAmountFacts, P2PProcessReview
from src.backend.domains.erp_approval.schemas import ApprovalContextRecord


P2P_RECORD_TYPES = {
    "invoice",
    "purchase_order",
    "goods_receipt",
    "payment_terms",
    "duplicate_check",
    "process_log",
    "clear_invoice_event",
}


def review_p2p_process_evidence(records: list[Any]) -> P2PProcessReview:
    """Review local P2P process evidence without calling ERP or executing actions."""

    normalized = [_normalize_record(item) for item in records]
    source_ids = _unique([item["source_id"] for item in normalized if item["source_id"]])
    record_types = {item["record_type"] for item in normalized}
    full_text = "\n".join(item["text"] for item in normalized).lower()

    review = P2PProcessReview(source_ids=source_ids)
    review = review.model_copy(update={"amount_facts": _amount_facts(normalized)})
    review = review.model_copy(update={"match_type": _classify_match_type(record_types, full_text, review.amount_facts)})
    review = review.model_copy(update={"sequence_anomalies": _sequence_anomalies(record_types, full_text)})
    review = review.model_copy(update={"process_exceptions": _process_exceptions(full_text)})
    review = review.model_copy(update={"missing_process_evidence": _missing_process_evidence(record_types, review.match_type)})
    return review.model_copy(
        update={
            "p2p_next_questions": _next_questions(review),
            "p2p_reviewer_notes": _reviewer_notes(review),
        }
    )


def p2p_process_fact_extractor(records: list[Any]) -> dict[str, Any]:
    review = review_p2p_process_evidence(records)
    return {
        "source_ids": review.source_ids,
        "amount_facts": review.amount_facts.model_dump(),
        "record_count": len(records),
        "non_action_statement": review.non_action_statement,
    }


def p2p_match_type_classifier(records: list[Any]) -> str:
    return review_p2p_process_evidence(records).match_type


def p2p_sequence_anomaly_reviewer(records: list[Any]) -> list[str]:
    return list(review_p2p_process_evidence(records).sequence_anomalies)


def p2p_amount_consistency_reviewer(records: list[Any]) -> P2PAmountFacts:
    return review_p2p_process_evidence(records).amount_facts


def p2p_exception_reviewer(records: list[Any]) -> list[str]:
    return list(review_p2p_process_evidence(records).process_exceptions)


def render_p2p_review_notes(review: P2PProcessReview) -> str:
    lines = [
        "P2P specialist review:",
        f"- Match type: {review.match_type}",
        f"- Sequence anomalies: {', '.join(review.sequence_anomalies) if review.sequence_anomalies else 'none detected'}",
        f"- Amount risk: {review.amount_facts.amount_variation_risk}",
    ]
    if review.amount_facts.po_amount is not None:
        lines.append(f"- PO amount: {review.amount_facts.po_amount:g}")
    if review.amount_facts.invoice_amount is not None:
        lines.append(f"- Invoice amount: {review.amount_facts.invoice_amount:g}")
    if review.amount_facts.goods_receipt_amount is not None:
        lines.append(f"- Goods receipt amount: {review.amount_facts.goods_receipt_amount:g}")
    if review.process_exceptions:
        lines.append("- Process exceptions: " + "; ".join(review.process_exceptions))
    if review.missing_process_evidence:
        lines.append("- Missing P2P evidence: " + "; ".join(review.missing_process_evidence))
    if review.p2p_next_questions:
        lines.append("- Next P2P questions: " + "; ".join(review.p2p_next_questions))
    lines.append("- Clear Invoice, if present, is treated as a historical process event only, not a payment action by this agent.")
    lines.append("- No ERP write action was executed.")
    return "\n".join(lines)


def _normalize_record(item: Any) -> dict[str, str]:
    if isinstance(item, CaseReviewEvidenceInput):
        record_type = item.record_type
        title = item.title
        content = item.content
        source_id = item.source_id
    elif isinstance(item, ApprovalContextRecord):
        record_type = item.record_type
        title = item.title
        content = item.content
        source_id = item.source_id
    elif isinstance(item, dict):
        record_type = str(item.get("record_type", "") or "")
        title = str(item.get("title", "") or "")
        content = str(item.get("content", "") or "")
        source_id = str(item.get("source_id", "") or "")
    else:
        record_type = getattr(item, "record_type", "")
        title = getattr(item, "title", "")
        content = getattr(item, "content", "")
        source_id = getattr(item, "source_id", "")
    return {
        "record_type": _normalize_record_type(record_type, title, content),
        "title": str(title or ""),
        "content": str(content or ""),
        "source_id": str(source_id or ""),
        "text": f"{title}\n{content}",
    }


def _normalize_record_type(record_type: str, title: str, content: str) -> str:
    explicit = re.sub(r"[^a-z0-9_]+", "_", str(record_type or "").strip().lower()).strip("_")
    if explicit:
        return explicit
    text = f"{title}\n{content}".lower()
    if "clear invoice" in text:
        return "clear_invoice_event"
    if "goods receipt" in text or "grn" in text:
        return "goods_receipt"
    if "purchase order" in text or re.search(r"\bpo[-_\s]?\d", text):
        return "purchase_order"
    if "invoice" in text:
        return "invoice"
    if "payment terms" in text:
        return "payment_terms"
    if "duplicate" in text:
        return "duplicate_check"
    if "event" in text or "process" in text:
        return "process_log"
    return "unknown"


def _classify_match_type(record_types: set[str], text: str, amount_facts: P2PAmountFacts) -> str:
    if "case item category is consignment" in text or "item_category=consignment" in text or "item category k" in text:
        return "consignment"
    if "case item category is 2-way match" in text or "item_category=2-way match" in text:
        return "two_way"
    if "case item category is 3-way match, invoice before gr" in text or "item_category=3-way match, invoice before gr" in text:
        return "three_way_invoice_before_gr"
    if "case item category is 3-way match, invoice after gr" in text or "item_category=3-way match, invoice after gr" in text:
        return "three_way_invoice_after_gr"
    has_invoice = "invoice" in record_types or "invoice" in text
    has_po = "purchase_order" in record_types or "purchase order" in text or re.search(r"\bpo[-_\s]?\d", text)
    has_gr = "goods_receipt" in record_types or "goods receipt" in text or "grn" in text
    if has_invoice and has_po and has_gr:
        if _invoice_before_gr(text):
            return "three_way_invoice_before_gr"
        return "three_way_invoice_after_gr"
    if has_invoice and has_po:
        return "two_way"
    if amount_facts.invoice_amount is not None and amount_facts.po_amount is not None and amount_facts.goods_receipt_amount is not None:
        return "three_way_invoice_after_gr"
    return "unknown"


def _sequence_anomalies(record_types: set[str], text: str) -> list[str]:
    anomalies: list[str] = []
    if _invoice_before_gr(text):
        anomalies.append("invoice_before_goods_receipt")
    if "clear invoice" in text:
        anomalies.append("clear_invoice_historical_only")
    if any(term in text for term in ("reversal", "reversed", "cancellation", "cancelled", "canceled", "credit memo")):
        anomalies.append("reversal_or_cancellation")
    if "payment block" in text or "blocked for payment" in text:
        anomalies.append("payment_block_event")
    return _unique(anomalies)


def _process_exceptions(text: str) -> list[str]:
    exceptions: list[str] = []
    if _invoice_before_gr(text):
        exceptions.append("Invoice appears before goods receipt; explain whether this is accepted two-way processing or a sequence exception.")
    if "clear invoice" in text:
        exceptions.append("Clear Invoice is a historical event in the process log, not an action this agent can execute.")
    if any(term in text for term in ("reversal", "reversed", "cancellation", "cancelled", "canceled", "credit memo")):
        exceptions.append("Reversal/cancellation evidence requires manual review before any payment recommendation.")
    if "payment block" in text or "blocked for payment" in text:
        exceptions.append("Payment block event exists; do not form an approve-style payment recommendation.")
    return _unique(exceptions)


def _missing_process_evidence(record_types: set[str], match_type: str) -> list[str]:
    missing: list[str] = []
    if match_type.startswith("three_way"):
        for required in ("purchase_order", "invoice", "goods_receipt"):
            if required not in record_types:
                missing.append(required)
    elif match_type == "two_way":
        for required in ("purchase_order", "invoice"):
            if required not in record_types:
                missing.append(required)
        missing.append("goods_receipt or documented two-way policy basis")
    elif match_type == "unknown":
        missing.extend(["purchase_order", "invoice", "goods_receipt or two-way policy basis"])
    if "payment_terms" not in record_types:
        missing.append("payment_terms")
    if "duplicate_check" not in record_types:
        missing.append("duplicate_payment_check")
    return _unique(missing)


def _next_questions(review: P2PProcessReview) -> list[str]:
    questions = [f"Please provide or verify {item} evidence." for item in review.missing_process_evidence]
    if "invoice_before_goods_receipt" in review.sequence_anomalies:
        questions.append("Please explain why invoice evidence predates goods receipt and whether policy permits this sequence.")
    if review.amount_facts.amount_variation_risk != "low":
        questions.append("Please provide amount reconciliation across PO, invoice, goods receipt, and cumulative net worth.")
    return _unique(questions)


def _reviewer_notes(review: P2PProcessReview) -> list[str]:
    notes = [
        f"Match type classified as {review.match_type}.",
        f"Amount consistency risk is {review.amount_facts.amount_variation_risk}.",
    ]
    if review.sequence_anomalies:
        notes.append("Sequence anomalies: " + ", ".join(review.sequence_anomalies) + ".")
    if review.process_exceptions:
        notes.extend(review.process_exceptions)
    return _unique(notes)


def _amount_facts(records: list[dict[str, str]]) -> P2PAmountFacts:
    values_by_type: dict[str, list[float]] = {"purchase_order": [], "invoice": [], "goods_receipt": [], "all": []}
    for item in records:
        values = _amount_values(item["text"])
        values_by_type["all"].extend(values)
        if item["record_type"] in values_by_type:
            values_by_type[item["record_type"]].extend(values)
    po = _first(values_by_type["purchase_order"])
    invoice = _first(values_by_type["invoice"])
    gr = _first(values_by_type["goods_receipt"])
    cumulative = _unique_floats(values_by_type["all"])
    risk = "unknown"
    comparable = [value for value in (po, invoice, gr) if value is not None]
    if len(comparable) >= 2:
        highest = max(comparable)
        lowest = min(comparable)
        if highest == 0:
            risk = "low"
        elif abs(highest - lowest) / highest <= 0.01:
            risk = "low"
        elif abs(highest - lowest) / highest <= 0.05:
            risk = "medium"
        else:
            risk = "high"
    elif cumulative:
        risk = "needs_reconciliation"
    return P2PAmountFacts(
        po_amount=po,
        invoice_amount=invoice,
        goods_receipt_amount=gr,
        cumulative_amount_values=cumulative,
        amount_variation_risk=risk,
    )


def _amount_values(text: str) -> list[float]:
    output: list[float] = []
    patterns = (
        r"(?:eur|usd|gbp|cny|rmb)\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
        r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:eur|usd|gbp|cny|rmb)",
        r"(?:amount|net worth|net_worth|value|total|gross|cumulative|cumulative_net_worth_values|cumulative_values)\s*[:=\[]+\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text.lower()):
            try:
                value = float(match.group(1).replace(",", ""))
            except ValueError:
                continue
            if 1 <= value <= 1_000_000_000:
                output.append(value)
    return output[:12]


def _invoice_before_gr(text: str) -> bool:
    if "invoice before goods receipt" in text or "invoice before gr" in text:
        return True
    invoice_match = re.search(r"invoice[^0-9]{0,25}(20\d{2}-\d{2}-\d{2})", text)
    gr_match = re.search(r"(?:goods receipt|grn)[^0-9]{0,25}(20\d{2}-\d{2}-\d{2})", text)
    return bool(invoice_match and gr_match and invoice_match.group(1) < gr_match.group(1))


def _first(values: list[float]) -> float | None:
    return values[0] if values else None


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output


def _unique_floats(values: list[float]) -> list[float]:
    output: list[float] = []
    for value in values:
        rounded = round(float(value), 2)
        if rounded not in output:
            output.append(rounded)
    return output
