from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.domains.erp_approval.case_models import ContradictionReport, EvidenceClaim
from src.backend.domains.erp_approval.evidence_requirements import requirement_matrix_for_approval_type
from src.backend.domains.erp_approval.evidence_sufficiency import evaluate_evidence_sufficiency


class ErpApprovalEvidenceSufficiencyTests(unittest.TestCase):
    def test_blocking_missing_evidence_fails_and_generates_questions(self) -> None:
        requirements = requirement_matrix_for_approval_type("invoice_payment")

        report = evaluate_evidence_sufficiency(requirements, [], ContradictionReport())

        self.assertFalse(report.passed)
        self.assertIn("invoice_payment:invoice", report.missing_requirement_ids)
        self.assertTrue(any("PO/GRN/Invoice" in question for question in report.next_questions))

    def test_only_user_statement_fails_even_with_supported_claim(self) -> None:
        requirements = requirement_matrix_for_approval_type("purchase_requisition")
        requirements[0] = requirements[0].model_copy(
            update={
                "status": "satisfied",
                "satisfied_by_claim_ids": ["claim:user"],
            }
        )
        claim = EvidenceClaim(
            claim_id="claim:user",
            claim_type="approval_request_present",
            statement="user says it is approved",
            source_id="user_statement://current_request",
            supports_requirement_ids=[requirements[0].requirement_id],
        )

        report = evaluate_evidence_sufficiency(requirements, [claim], ContradictionReport())

        self.assertFalse(report.passed)
        self.assertTrue(any("用户陈述" in warning for warning in report.warnings))

    def test_conflict_requirement_fails(self) -> None:
        requirements = requirement_matrix_for_approval_type("expense")
        requirements[0] = requirements[0].model_copy(update={"status": "conflict"})

        report = evaluate_evidence_sufficiency(requirements, [], ContradictionReport(has_conflict=True))

        self.assertFalse(report.passed)
        self.assertIn(requirements[0].requirement_id, report.conflict_requirement_ids)


if __name__ == "__main__":
    unittest.main()
