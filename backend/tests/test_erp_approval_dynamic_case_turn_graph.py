from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.api import erp_approval as erp_approval_api
from src.backend.domains.erp_approval.case_harness import CaseHarness
from src.backend.domains.erp_approval.case_review_service import CaseReviewEvidenceInput
from src.backend.domains.erp_approval.case_stage_model import CaseStageModelReviewer
from src.backend.domains.erp_approval.case_state_models import CaseTurnRequest
from src.backend.domains.erp_approval.case_turn_graph import run_case_turn_graph_state_sync


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeModel:
    def __init__(self, content: str) -> None:
        self.content = content

    def invoke(self, messages):
        del messages
        return _FakeResponse(self.content)


class DynamicCaseTurnGraphTests(unittest.TestCase):
    def _client(self, base_dir: Path) -> TestClient:
        app = FastAPI()
        app.include_router(erp_approval_api.router, prefix="/api")
        base_dir_patcher = patch.object(erp_approval_api, "_case_review_base_dir", return_value=base_dir)
        stage_model_patcher = patch.object(erp_approval_api, "_case_stage_model_reviewer", return_value=None)
        self.addCleanup(base_dir_patcher.stop)
        self.addCleanup(stage_model_patcher.stop)
        base_dir_patcher.start()
        stage_model_patcher.start()
        return TestClient(app)

    def test_off_topic_routes_to_off_topic_reject_node(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            client = self._client(Path(temp_dir))
            created = client.post("/api/erp-approval/cases/turn", json={"user_message": "Review purchase requisition PR-DYN-OFF."}).json()
            response = client.post(
                "/api/erp-approval/cases/turn",
                json={"case_id": created["case_state"]["case_id"], "user_message": "Please write a marketing copy."},
            ).json()
            steps = response["harness_run"]["graph_steps"]

            self.assertIn("off_topic_reject_node", steps)
            self.assertNotIn("route_evidence_type", steps)
            self.assertNotIn("purchase_requisition_review_subgraph", steps)
            self.assertEqual(response["case_state"]["accepted_evidence"], [])

    def test_ask_status_routes_to_status_summary(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            client = self._client(Path(temp_dir))
            created = client.post("/api/erp-approval/cases/turn", json={"user_message": "Review purchase requisition PR-DYN-STATUS."}).json()
            response = client.post(
                "/api/erp-approval/cases/turn",
                json={"case_id": created["case_state"]["case_id"], "user_message": "What is still missing?"},
            ).json()
            steps = response["harness_run"]["graph_steps"]

            self.assertIn("case_status_summary_node", steps)
            self.assertNotIn("p2p_process_fact_extractor", steps)
            self.assertEqual(response["operation_scope"], "read_only_case_turn")
            self.assertIn("read_only_case_response", steps)
            self.assertIn("append_audit_only", steps)
            self.assertNotIn("persist_case_state_dossier_audit", steps)
            self.assertEqual(response["case_state"]["dossier_version"], created["case_state"]["dossier_version"])

    def test_llm_turn_classifier_runs_before_first_route(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            harness = CaseHarness(Path(temp_dir), stage_model=CaseStageModelReviewer(_FakeModel('{"turn_intent":"ask_required_materials","confidence":0.9}')))
            first = harness.handle_turn(CaseTurnRequest(user_message="Review purchase requisition PR-DYN-CLASSIFIER."))
            graph_state = run_case_turn_graph_state_sync(
                harness,
                CaseTurnRequest(case_id=first.case_state.case_id, user_message="Status?"),
            )
            steps = graph_state["graph_steps"]

            self.assertLess(steps.index("llm_turn_classifier"), steps.index("route_turn_intent"))
            self.assertLess(steps.index("deterministic_classifier_guard"), steps.index("route_turn_intent"))
            self.assertIn("materials_guidance_node", steps)
            self.assertNotIn("case_status_summary_node", steps)

    def test_quote_evidence_routes_to_purchase_requisition_subgraph(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            client = self._client(Path(temp_dir))
            created = client.post("/api/erp-approval/cases/turn", json={"user_message": "Review purchase requisition PR-DYN-QUOTE."}).json()
            response = client.post(
                "/api/erp-approval/cases/turn",
                json={
                    "case_id": created["case_state"]["case_id"],
                    "user_message": "Here is quote evidence.",
                    "extra_evidence": [
                        {
                            "title": "Quote",
                            "record_type": "quote",
                            "content": "Quote Q-DYN-QUOTE from Acme Supplies for USD 24,500. Price basis: replacement laptops.",
                        }
                    ],
                },
            ).json()
            steps = response["harness_run"]["graph_steps"]

            self.assertIn("route_evidence_type", steps)
            self.assertIn("purchase_requisition_review_subgraph", steps)
            self.assertIn("merge_review_outputs", steps)

    def test_p2p_evidence_routes_through_visible_p2p_specialist_nodes(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            client = self._client(Path(temp_dir))
            created = client.post("/api/erp-approval/cases/turn", json={"user_message": "Review invoice payment INV-DYN-P2P."}).json()
            response = client.post(
                "/api/erp-approval/cases/turn",
                json={
                    "case_id": created["case_state"]["case_id"],
                    "user_message": "Here are invoice, PO, GRN and process log evidence.",
                    "extra_evidence": [
                        {"title": "PO", "record_type": "purchase_order", "content": "Purchase Order PO-DYN amount EUR 1000."},
                        {"title": "Invoice", "record_type": "invoice", "content": "Invoice INV-DYN date 2024-01-01 amount EUR 1000."},
                        {"title": "GRN", "record_type": "goods_receipt", "content": "Goods Receipt GRN-DYN date 2024-01-05 amount EUR 1000."},
                        {"title": "Process log", "record_type": "process_log", "content": "Event log: Invoice before goods receipt. Clear Invoice happened later as historical event only."},
                    ],
                },
            ).json()
            steps = response["harness_run"]["graph_steps"]

            self.assertIn("p2p_process_fact_extractor", steps)
            self.assertIn("p2p_match_type_classifier", steps)
            self.assertIn("p2p_sequence_anomaly_reviewer", steps)
            self.assertIn("p2p_amount_consistency_reviewer", steps)
            self.assertIn("p2p_exception_reviewer", steps)
            self.assertIn("p2p_process_fact_explanation", steps)
            self.assertIn("p2p_sequence_risk_explanation", steps)
            self.assertIn("p2p_amount_reconciliation_explanation", steps)
            self.assertIn("p2p_missing_evidence_questions", steps)
            self.assertIn("p2p_process_patch_validator", steps)
            self.assertIn("llm_turn_classifier", steps)
            self.assertIn("llm_evidence_extractor", steps)
            self.assertIn("llm_policy_interpreter", steps)
            self.assertIn("llm_contradiction_reviewer", steps)
            self.assertIn("llm_reviewer_memo", steps)
            self.assertIn("aggregate_llm_stage_outputs", steps)
            self.assertIn("No ERP write action was executed", response["non_action_statement"])

    def test_final_memo_gate_blocks_approve_style_memo_when_evidence_missing(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            client = self._client(Path(temp_dir))
            created = client.post("/api/erp-approval/cases/turn", json={"user_message": "Review purchase requisition PR-DYN-MEMO."}).json()
            response = client.post(
                "/api/erp-approval/cases/turn",
                json={"case_id": created["case_state"]["case_id"], "user_message": "Generate the final reviewer memo now."},
            ).json()

            self.assertIn("final_memo_gate", response["harness_run"]["graph_steps"])
            self.assertIn("merge_review_outputs", response["harness_run"]["graph_steps"])
            self.assertIn("evidence_sufficiency_gate", response["harness_run"]["graph_steps"])
            self.assertIn("contradiction_gate", response["harness_run"]["graph_steps"])
            self.assertIn("control_matrix_gate", response["harness_run"]["graph_steps"])
            self.assertNotEqual(response["review"]["recommendation"]["status"], "recommend_approve")
            self.assertTrue(response["review"]["evidence_sufficiency"]["blocking_gaps"])

    def test_bad_model_json_falls_back_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            harness = CaseHarness(Path(temp_dir), stage_model=CaseStageModelReviewer(_FakeModel("not-json")))
            first = harness.handle_turn(CaseTurnRequest(user_message="Review purchase requisition PR-DYN-BADJSON."))
            graph_state = run_case_turn_graph_state_sync(
                harness,
                CaseTurnRequest(
                    case_id=first.case_state.case_id,
                    user_message="Here is quote evidence.",
                    extra_evidence=[
                        CaseReviewEvidenceInput(
                            title="Quote",
                            record_type="quote",
                            content="Quote Q-DYN-BADJSON from Acme Supplies for USD 24,500.",
                        )
                    ],
                ),
            )

            self.assertIn("purchase_requisition_review_subgraph", graph_state["graph_steps"])
            self.assertIn("llm_turn_classifier", graph_state["graph_steps"])
            self.assertIn("llm_reviewer_memo", graph_state["graph_steps"])
            self.assertIn("aggregate_llm_stage_outputs", graph_state["graph_steps"])
            self.assertIn(graph_state["response"].patch.patch_type, {"accept_evidence", "reject_evidence", "answer_status"})
            self.assertIn("No ERP write action was executed", graph_state["response"].non_action_statement)

    def test_llm_role_outputs_are_visible_in_patch_model_review(self) -> None:
        role_json = """
        {
          "turn_intent": "submit_evidence",
          "patch_type": "accept_evidence",
          "evidence_decision": "accepted",
          "accepted_source_ids": ["local_evidence://quote/pr-dyn-llm/turn-0002-1"],
          "warnings": [],
          "confidence": 0.8,
          "non_action_statement": "This is a local approval case state update. No ERP write action was executed."
        }
        """
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            harness = CaseHarness(Path(temp_dir), stage_model=CaseStageModelReviewer(_FakeModel(role_json)))
            first = harness.handle_turn(CaseTurnRequest(user_message="Review purchase requisition PR-DYN-LLM."))
            graph_state = run_case_turn_graph_state_sync(
                harness,
                CaseTurnRequest(
                    case_id=first.case_state.case_id,
                    user_message="Here is quote evidence.",
                    extra_evidence=[
                        CaseReviewEvidenceInput(
                            title="Quote",
                            record_type="quote",
                            source_id="local_evidence://quote/pr-dyn-llm/turn-0002-1",
                            content="Quote Q-DYN-LLM from Acme Supplies for USD 24,500. Price basis: replacement laptops.",
                        )
                    ],
                ),
            )
            model_review = graph_state["response"].patch.model_review

            self.assertTrue(model_review["used"])
            self.assertIn("turn_classifier", model_review["role_outputs"])
            self.assertIn("evidence_extractor", model_review["role_outputs"])
            self.assertIn("policy_interpreter", model_review["role_outputs"])
            self.assertIn("contradiction_reviewer", model_review["role_outputs"])
            self.assertIn("reviewer_memo", model_review["role_outputs"])


if __name__ == "__main__":
    unittest.main()
