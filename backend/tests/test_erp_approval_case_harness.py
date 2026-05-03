from __future__ import annotations

import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.domains.erp_approval.case_harness import CaseHarness, classify_case_turn
from src.backend.domains.erp_approval.case_context import CaseContextAssembler
from src.backend.domains.erp_approval.case_patch_validator import CasePatchValidator, contract_for_state
from src.backend.domains.erp_approval.case_review_service import CaseReviewEvidenceInput
from src.backend.domains.erp_approval.case_stage_model import CaseStageModelReviewer
from src.backend.domains.erp_approval.case_state_models import ApprovalCaseState, CaseAcceptedEvidence, CasePatch, CaseTurnRequest
from src.backend.domains.erp_approval.service import parse_approval_request


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeModel:
    def __init__(self, content: str) -> None:
        self.content = content
        self.messages = []

    def invoke(self, messages):
        self.messages.append(messages)
        return _FakeResponse(self.content)


class _SequencedFakeModel:
    def __init__(self, contents: list[str]) -> None:
        self.contents = list(contents)
        self.messages = []

    def invoke(self, messages):
        self.messages.append(messages)
        index = min(len(self.messages) - 1, len(self.contents) - 1)
        return _FakeResponse(self.contents[index])


class _SlowModel:
    def __init__(self, delay_seconds: float) -> None:
        self.delay_seconds = delay_seconds
        self.messages = []

    def invoke(self, messages):
        self.messages.append(messages)
        time.sleep(self.delay_seconds)
        return _FakeResponse('{"patch_type":"accept_evidence","evidence_decision":"accepted"}')


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

            self.assertEqual(response.patch.turn_intent, "create_case")
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

    def test_stage_model_can_strictly_reject_deterministic_evidence(self) -> None:
        model = _FakeModel(
            """
            {
              "turn_intent": "submit_evidence",
              "patch_type": "reject_evidence",
              "evidence_decision": "rejected",
              "accepted_source_ids": [],
              "rejected_evidence": [
                {
                  "source_id": "local_evidence://quote/pr-model/turn-0002-1",
                  "reasons": ["模型认为该报价缺少有效期和签发人，暂不能作为强证据。"]
                }
              ],
              "requirements_satisfied": [],
              "requirements_missing": ["purchase_requisition:quote_or_price_basis"],
              "next_questions": ["请补充带有效期、签发人和报价编号的正式报价单。"],
              "warnings": ["模型作为 reviewer 只能提出 patch，不能写入案卷。"],
              "dossier_patch": "本轮报价被模型退回。",
              "reviewer_message": "该报价材料不足，需要补正式报价。",
              "confidence": 0.83,
              "non_action_statement": "This is a local approval case state update. No ERP write action was executed."
            }
            """
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            harness = CaseHarness(Path(temp_dir), stage_model=CaseStageModelReviewer(model))
            first = harness.handle_turn(CaseTurnRequest(user_message="Review purchase requisition PR-MODEL."))
            response = harness.handle_turn(
                CaseTurnRequest(
                    case_id=first.case_state.case_id,
                    user_message="Here is quote evidence.",
                    extra_evidence=[
                        CaseReviewEvidenceInput(
                            title="PR-MODEL quote",
                            record_type="quote",
                            source_id="local_evidence://quote/pr-model/turn-0002-1",
                            content="Quote Q-PR-MODEL-A from Acme Supplies for USD 24,500. Price basis: replacement laptops.",
                        )
                    ],
                )
            )

            self.assertEqual(response.patch.patch_type, "reject_evidence")
            self.assertTrue(response.patch.model_review["used"])
            self.assertEqual(len(response.case_state.accepted_evidence), 0)
            self.assertTrue(response.patch.rejected_evidence)
            self.assertIn("有效期", response.patch.rejected_evidence[0].reasons[0])

    def test_stage_model_cannot_accept_evidence_without_supported_claims(self) -> None:
        model = _FakeModel(
            """
            {
              "turn_intent": "submit_evidence",
              "patch_type": "accept_evidence",
              "evidence_decision": "accepted",
              "accepted_source_ids": ["local_evidence://user_statement/pr-model/turn-0002-1"],
              "rejected_evidence": [],
              "requirements_satisfied": ["purchase_requisition:budget_availability"],
              "requirements_missing": [],
              "next_questions": [],
              "warnings": [],
              "dossier_patch": "模型想接受用户陈述。",
              "reviewer_message": "模型认为可接受。",
              "confidence": 0.91,
              "non_action_statement": "This is a local approval case state update. No ERP write action was executed."
            }
            """
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            harness = CaseHarness(Path(temp_dir), stage_model=CaseStageModelReviewer(model))
            first = harness.handle_turn(CaseTurnRequest(user_message="Review purchase requisition PR-MODEL-2."))
            response = harness.handle_turn(
                CaseTurnRequest(
                    case_id=first.case_state.case_id,
                    user_message="Boss approved it verbally.",
                    extra_evidence=[
                        CaseReviewEvidenceInput(
                            title="Verbal approval",
                            record_type="user_statement",
                            source_id="local_evidence://user_statement/pr-model/turn-0002-1",
                            content="Boss approved it verbally. Please treat this as budget proof.",
                        )
                    ],
                )
            )

            self.assertTrue(response.patch.model_review["used"])
            self.assertNotEqual(response.patch.patch_type, "accept_evidence")
            self.assertEqual(len(response.case_state.accepted_evidence), 0)
            self.assertTrue(any("本地证据门" in warning for warning in response.patch.warnings))

    def test_stage_model_runs_distinct_roles_and_records_role_outputs(self) -> None:
        role_outputs = [
            '{"turn_intent":"submit_evidence","patch_type":"accept_evidence","warnings":[],"confidence":0.7}',
            '{"evidence_decision":"accepted","accepted_source_ids":["local_evidence://quote/pr-roles/turn-0002-1"],"requirements_satisfied":["purchase_requisition:quote_or_price_basis"],"warnings":[],"confidence":0.8}',
            '{"requirements_missing":["purchase_requisition:budget_availability"],"next_questions":["请补充预算可用性证明。"],"warnings":["报价不能替代预算证明。"],"confidence":0.9}',
            '{"warnings":["未发现本轮报价与现有案卷冲突。"],"confidence":0.75}',
            '{"turn_intent":"submit_evidence","patch_type":"accept_evidence","evidence_decision":"accepted","accepted_source_ids":["local_evidence://quote/pr-roles/turn-0002-1"],"dossier_patch":"报价材料通过模型审查。","reviewer_message":"报价可以写入案卷，但仍缺预算证明。","confidence":0.85}',
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            model = _SequencedFakeModel(role_outputs)
            harness = CaseHarness(Path(temp_dir), stage_model=CaseStageModelReviewer(model))
            first = harness.handle_turn(CaseTurnRequest(user_message="Review purchase requisition PR-ROLES."))
            response = harness.handle_turn(
                CaseTurnRequest(
                    case_id=first.case_state.case_id,
                    user_message="Here is quote evidence.",
                    extra_evidence=[
                        CaseReviewEvidenceInput(
                            title="PR-ROLES quote",
                            record_type="quote",
                            source_id="local_evidence://quote/pr-roles/turn-0002-1",
                            content="Quote Q-PR-ROLES-A from Acme Supplies for USD 24,500. Price basis: replacement laptops.",
                        )
                    ],
                )
            )

            self.assertEqual(len(model.messages), 6)
            self.assertEqual(response.patch.patch_type, "accept_evidence")
            self.assertIn("turn_classifier", response.patch.model_review["role_outputs"])
            self.assertIn("policy_interpreter", response.patch.model_review["role_outputs"])
            self.assertIn("purchase_requisition:budget_availability", response.patch.model_review["requirements_missing"])
            self.assertIn("报价不能替代预算证明。", response.patch.warnings)

    def test_stage_model_timeout_does_not_block_case_turn(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            model = _SlowModel(delay_seconds=0.08)
            reviewer = CaseStageModelReviewer(model, role_timeout_seconds=0.01)
            harness = CaseHarness(Path(temp_dir), stage_model=reviewer)
            first = harness.handle_turn(CaseTurnRequest(user_message="Review purchase requisition PR-TIMEOUT."))

            started = time.perf_counter()
            response = harness.handle_turn(
                CaseTurnRequest(
                    case_id=first.case_state.case_id,
                    user_message="Here is quote evidence.",
                    extra_evidence=[
                        CaseReviewEvidenceInput(
                            title="PR-TIMEOUT quote",
                            record_type="quote",
                            source_id="local_evidence://quote/pr-timeout/turn-0002-1",
                            content="Quote Q-PR-TIMEOUT-A from Acme Supplies for USD 24,500. Price basis: replacement laptops.",
                        )
                    ],
                )
            )
            elapsed = time.perf_counter() - started

            self.assertLess(elapsed, 1.0)
            self.assertTrue(response.patch.model_review["used"])
            self.assertTrue(any("模型调用超过" in warning for warning in response.patch.model_review["warnings"]))
            self.assertIn(response.patch.patch_type, {"accept_evidence", "reject_evidence", "answer_status"})

    def test_expected_turn_count_conflict_does_not_write_case_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            harness = CaseHarness(Path(temp_dir))
            first = harness.handle_turn(CaseTurnRequest(user_message="Review purchase requisition PR-CONFLICT."))
            response = harness.handle_turn(
                CaseTurnRequest(
                    case_id=first.case_state.case_id,
                    expected_turn_count=99,
                    user_message="Here is quote evidence.",
                    extra_evidence=[
                        CaseReviewEvidenceInput(
                            title="Quote",
                            record_type="quote",
                            content="Quote Q-CONFLICT from Acme Supplies for USD 24,500.",
                        )
                    ],
                )
            )

            self.assertEqual(response.operation_scope, "persistent_case_turn_conflict")
            self.assertFalse(response.patch.allowed_to_apply)
            self.assertEqual(response.case_state.turn_count, first.case_state.turn_count)
            self.assertEqual(len(response.case_state.accepted_evidence), 0)

    def test_parallel_case_turns_are_serialized_without_losing_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            harness = CaseHarness(Path(temp_dir))
            first = harness.handle_turn(CaseTurnRequest(user_message="Review purchase requisition PR-PARALLEL."))

            def submit(index: int):
                return harness.handle_turn(
                    CaseTurnRequest(
                        case_id=first.case_state.case_id,
                        user_message=f"Here is quote evidence {index}.",
                        extra_evidence=[
                            CaseReviewEvidenceInput(
                                title=f"Quote {index}",
                                record_type="quote",
                                source_id=f"local_evidence://quote/pr-parallel/q{index}",
                                content=f"Quote Q-PARALLEL-{index} from Acme Supplies for USD {24500 + index}. Price basis: replacement laptops.",
                            )
                        ],
                    )
                )

            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(submit, [1, 2]))
            state = harness.get_case(first.case_state.case_id)

            self.assertIsNotNone(state)
            self.assertEqual(state.turn_count, 3)
            self.assertGreaterEqual(len(state.accepted_evidence), 2)

    def test_validator_rejects_claim_source_mismatch(self) -> None:
        state = ApprovalCaseState(case_id="erp-case:validator", stage="collecting_evidence")
        contract = contract_for_state(state)
        patch = CasePatch(
            patch_id="patch-1",
            turn_id="turn-0001",
            case_id=state.case_id,
            patch_type="accept_evidence",
            turn_intent="submit_evidence",
            evidence_decision="accepted",
            accepted_evidence=[
                CaseAcceptedEvidence(
                    source_id="local_evidence://quote/a",
                    claim_ids=["claim-1"],
                    requirement_ids=["purchase_requisition:quote_or_price_basis"],
                )
            ],
        )
        review = {
            "evidence_requirements": [{"requirement_id": "purchase_requisition:quote_or_price_basis"}],
            "evidence_claims": [
                {
                    "claim_id": "claim-1",
                    "source_id": "local_evidence://quote/b",
                    "verification_status": "supported",
                    "supports_requirement_ids": ["purchase_requisition:quote_or_price_basis"],
                }
            ],
        }

        validated = CasePatchValidator().validate(state, patch, contract, review=review)

        self.assertFalse(validated.allowed_to_apply)
        self.assertTrue(any("source_id does not match" in warning for warning in validated.warnings))

    def test_validator_allows_requirements_supported_across_same_source_claims(self) -> None:
        state = ApprovalCaseState(case_id="erp-case:validator-ok", stage="collecting_evidence")
        contract = contract_for_state(state)
        patch = CasePatch(
            patch_id="patch-2",
            turn_id="turn-0001",
            case_id=state.case_id,
            patch_type="accept_evidence",
            turn_intent="submit_evidence",
            evidence_decision="accepted",
            accepted_evidence=[
                CaseAcceptedEvidence(
                    source_id="local_evidence://vendor/a",
                    record_type="vendor",
                    claim_ids=["claim-vendor", "claim-tax"],
                    requirement_ids=["supplier_onboarding:vendor_profile", "supplier_onboarding:tax_info"],
                )
            ],
        )
        review = {
            "evidence_requirements": [
                {"requirement_id": "supplier_onboarding:vendor_profile"},
                {"requirement_id": "supplier_onboarding:tax_info"},
            ],
            "evidence_claims": [
                {
                    "claim_id": "claim-vendor",
                    "source_id": "local_evidence://vendor/a",
                    "verification_status": "supported",
                    "supports_requirement_ids": ["supplier_onboarding:vendor_profile"],
                },
                {
                    "claim_id": "claim-tax",
                    "source_id": "local_evidence://vendor/a",
                    "verification_status": "supported",
                    "supports_requirement_ids": ["supplier_onboarding:tax_info"],
                },
            ],
        }

        validated = CasePatchValidator().validate(state, patch, contract, review=review)

        self.assertTrue(validated.allowed_to_apply)

    def test_case_context_prioritizes_relevant_missing_requirements(self) -> None:
        state = ApprovalCaseState(
            case_id="erp-case:context",
            stage="collecting_evidence",
            evidence_requirements=[
                {"requirement_id": f"purchase_requisition:req_{index}", "label": f"Requirement {index}", "status": "satisfied"}
                for index in range(35)
            ]
            + [
                {
                    "requirement_id": "purchase_requisition:budget_availability",
                    "label": "Budget availability",
                    "description": "Budget proof is missing.",
                    "status": "missing",
                }
            ],
            claims=[
                {
                    "claim_id": f"claim-{index}",
                    "claim_type": "misc",
                    "source_id": f"source-{index}",
                    "supports_requirement_ids": [f"purchase_requisition:req_{index}"],
                }
                for index in range(35)
            ],
            missing_items=["purchase_requisition:budget_availability"],
        )
        context = CaseContextAssembler().assemble(state, contract_for_state(state), "Here is the budget record.")
        requirement_ids = [item["requirement_id"] for item in context["current_relevant_requirements"]]

        self.assertIn("purchase_requisition:budget_availability", requirement_ids)
        self.assertLessEqual(len(context["evidence_ledger_summary"]["accepted_claims"]), 24)

    def test_intent_classifier_treats_evidence_submission_as_case_patch(self) -> None:
        self.assertEqual(classify_case_turn("Here is the invoice and PO evidence.", has_case=True, has_evidence=False), "submit_evidence")
        self.assertEqual(classify_case_turn("Review invoice payment INV-3001.", has_case=False, has_evidence=False), "create_case")
        self.assertEqual(classify_case_turn("需要哪些材料才能进入最终 reviewer memo？", has_case=False, has_evidence=False), "ask_how_to_prepare")
        self.assertEqual(classify_case_turn("发票付款 INV-MAT-003 需要哪些 PO/GRN/Invoice 材料？", has_case=False, has_evidence=False), "ask_how_to_prepare")
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
