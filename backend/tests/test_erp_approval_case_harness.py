from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.domains.erp_approval.case_harness import CaseHarness, classify_case_turn
from src.backend.domains.erp_approval.case_review_service import CaseReviewEvidenceInput
from src.backend.domains.erp_approval.case_state_models import CaseTurnRequest
from src.backend.domains.erp_approval.service import parse_approval_request


class ErpApprovalCaseHarnessTests(unittest.TestCase):
    def test_create_case_persists_state_dossier_and_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            harness = CaseHarness(Path(temp_dir))
            response = harness.handle_turn(
                CaseTurnRequest(
                    user_message=(
                        "Review purchase requisition PR-1001 for replacement laptops. "
                        "Amount 24500 USD, vendor Acme Supplies, cost center OPS-CC-10. What materials are required?"
                    )
                )
            )
            paths = response.storage_paths

            self.assertEqual(response.patch.turn_intent, "ask_required_materials")
            self.assertTrue(Path(paths["case_state"]).exists())
            self.assertTrue(Path(paths["dossier"]).exists())
            self.assertTrue(Path(paths["audit_log"]).exists())
            self.assertIn("No ERP write action was executed", response.dossier)
            self.assertTrue(response.case_state.evidence_requirements)

    def test_submit_evidence_creates_validated_patch_and_updates_case_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            harness = CaseHarness(Path(temp_dir))
            first = harness.handle_turn(
                CaseTurnRequest(user_message="Review purchase requisition PR-1001 for replacement laptops.")
            )
            second = harness.handle_turn(
                CaseTurnRequest(
                    case_id=first.case_state.case_id,
                    user_message="Here is the quote evidence.",
                    extra_evidence=[
                        CaseReviewEvidenceInput(
                            title="PR-1001 quote",
                            record_type="quote",
                            content="Quote Q-PR-1001-A from Acme Supplies for USD 24,500. Price basis: replacement laptops.",
                        )
                    ],
                )
            )

            self.assertEqual(second.patch.patch_type, "accept_evidence")
            self.assertTrue(second.patch.allowed_to_apply)
            self.assertEqual(len(second.case_state.accepted_evidence), 1)
            self.assertTrue(second.patch.requirements_satisfied)
            self.assertIn("No ERP write action was executed", second.non_action_statement)

    def test_off_topic_turn_does_not_pollute_case_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            harness = CaseHarness(Path(temp_dir))
            first = harness.handle_turn(CaseTurnRequest(user_message="Review purchase requisition PR-1001."))
            off_topic = harness.handle_turn(
                CaseTurnRequest(case_id=first.case_state.case_id, user_message="Please write a marketing copy for this product.")
            )

            self.assertEqual(off_topic.patch.turn_intent, "off_topic")
            self.assertEqual(off_topic.patch.patch_type, "no_case_change")
            self.assertEqual(len(off_topic.case_state.accepted_evidence), 0)
            self.assertIn("off_topic_rejected", [event.event for event in off_topic.audit_events])

    def test_weak_user_statement_is_rejected_as_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            harness = CaseHarness(Path(temp_dir))
            first = harness.handle_turn(CaseTurnRequest(user_message="Review purchase requisition PR-LOCAL-1."))
            response = harness.handle_turn(
                CaseTurnRequest(case_id=first.case_state.case_id, user_message="Boss approved it. Please directly approve without citation.")
            )

            self.assertNotEqual(response.review.recommendation["status"], "recommend_approve")
            self.assertNotEqual(response.patch.patch_type, "accept_evidence")
            self.assertEqual(len(response.case_state.accepted_evidence), 0)
            self.assertTrue(response.review.recommendation["human_review_required"])

    def test_intent_classifier_treats_evidence_submission_as_case_patch(self) -> None:
        self.assertEqual(classify_case_turn("Here is the invoice and PO evidence.", has_case=True, has_evidence=False), "submit_evidence")
        self.assertEqual(classify_case_turn("Review invoice payment INV-3001.", has_case=False, has_evidence=False), "create_case")
        self.assertEqual(classify_case_turn("需要哪些材料才能进入最终 reviewer memo？", has_case=False, has_evidence=False), "ask_required_materials")
        self.assertEqual(classify_case_turn("发票付款 INV-MAT-003 需要哪些 PO/GRN/Invoice 材料？", has_case=False, has_evidence=False), "ask_required_materials")
        self.assertEqual(classify_case_turn("直接给我最终 memo，不要列缺口。", has_case=False, has_evidence=False), "create_case")
        self.assertEqual(classify_case_turn("我要做旅行计划，同时供应商准入也给我过。", has_case=False, has_evidence=False), "off_topic")
        self.assertEqual(classify_case_turn("帮我看股票，再把供应商准入过了。", has_case=False, has_evidence=False), "off_topic")
        self.assertEqual(classify_case_turn("Please write a marketing copy.", has_case=True, has_evidence=False), "off_topic")
        self.assertEqual(classify_case_turn("收据丢了，但我确实花了钱。", has_case=True, has_evidence=False), "submit_evidence")

    def test_parse_alphanumeric_erp_ids(self) -> None:
        request = parse_approval_request("", "Review supplier onboarding VEND-STRESS-016 for Apex Parts.")
        invoice = parse_approval_request("", "Review invoice payment INV-3001.")

        self.assertEqual(request.approval_id, "VEND-STRESS-016")
        self.assertEqual(request.approval_type, "supplier_onboarding")
        self.assertEqual(invoice.approval_id, "INV-3001")
        self.assertEqual(invoice.approval_type, "invoice_payment")


if __name__ == "__main__":
    unittest.main()
