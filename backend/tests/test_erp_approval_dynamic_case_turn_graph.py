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

    def test_client_intent_routes_quick_status_without_polluting_context_audit(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            client = self._client(Path(temp_dir))
            created = client.post("/api/erp-approval/cases/turn", json={"user_message": "Review purchase requisition PR-DYN-CLIENT."}).json()
            response = client.post(
                "/api/erp-approval/cases/turn",
                json={
                    "case_id": created["case_state"]["case_id"],
                    "user_message": "请列出材料清单，但这个按钮语义是当前还缺什么。",
                    "client_intent": "ask_status",
                },
            ).json()
            steps = response["harness_run"]["graph_steps"]
            turn_received = next(event for event in response["audit_events"] if event["event"] == "turn_received")

            self.assertIn("case_status_summary_node", steps)
            self.assertEqual(response["operation_scope"], "read_only_case_turn")
            self.assertEqual(turn_received["details"]["client_intent"], "ask_missing_requirements")
            self.assertIn("context_summary", turn_received["details"])
            self.assertNotIn("context_pack", turn_received["details"])
            self.assertIn("requirement_count", turn_received["details"]["context_summary"])

    def test_client_ask_status_without_existing_case_is_not_ephemeral_read_only_case(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            client = self._client(Path(temp_dir))
            response = client.post(
                "/api/erp-approval/cases/turn",
                json={
                    "user_message": "What is missing?",
                    "client_intent": "ask_status",
                },
            ).json()
            turn_received = next(event for event in response["audit_events"] if event["event"] == "turn_received")

            self.assertNotEqual(response["operation_scope"], "read_only_case_turn")
            self.assertEqual(response["case_state"]["turn_count"], 1)
            self.assertIn("persist_case_state_dossier_audit", response["harness_run"]["graph_steps"])
            self.assertEqual(turn_received["details"]["client_intent"], "")
            self.assertNotIn("context_pack", turn_received["details"])

    def test_ask_how_to_prepare_uses_policy_rag_without_persisting_new_case(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            client = self._client(Path(temp_dir))
            response = client.post(
                "/api/erp-approval/cases/turn",
                json={
                    "user_message": "我要创建采购申请，需要准备什么材料？",
                    "client_intent": "ask_how_to_prepare",
                },
            ).json()

            self.assertEqual(response["operation_scope"], "read_only_case_turn")
            self.assertIn("materials_guidance_node", response["harness_run"]["graph_steps"])
            self.assertIn("policy_rag", response["patch"]["model_review"])
            self.assertTrue(response["patch"]["model_review"]["policy_rag"]["guidance"]["items"])
            self.assertFalse(Path(response["storage_paths"]["case_state"]).exists())

    def test_ask_how_to_prepare_uses_stage_model_policy_guidance_when_configured(self) -> None:
        model_json = """
        {
          "rendered_guidance": "模型材料清单：请准备预算证明、供应商准入记录、报价或合同依据、审批矩阵。每项材料都必须可追溯到 source_id。",
          "warnings": [],
          "confidence": 0.91,
          "non_action_statement": "This is a local approval case state update. No ERP write action was executed."
        }
        """
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            harness = CaseHarness(Path(temp_dir), stage_model=CaseStageModelReviewer(_FakeModel(model_json)))
            graph_state = run_case_turn_graph_state_sync(
                harness,
                CaseTurnRequest(user_message="I need to prepare a purchase requisition case. Please tell me the required materials first."),
            )
            response = graph_state["response"]
            model_review = response.patch.model_review

            self.assertEqual(response.operation_scope, "read_only_case_turn")
            self.assertEqual(response.patch.turn_intent, "ask_how_to_prepare")
            self.assertIn("materials_guidance_node", graph_state["graph_steps"])
            self.assertTrue(model_review["used"])
            self.assertTrue(model_review["policy_rag"]["used"])
            self.assertIn("模型材料清单", model_review["policy_rag"]["rendered_guidance"])
            self.assertFalse(Path(response.storage_paths["case_state"]).exists())

    def test_prepare_template_with_case_review_words_stays_read_only_guidance(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            client = self._client(Path(temp_dir))
            response = client.post(
                "/api/erp-approval/cases/turn",
                json={
                    "user_message": (
                        "我有一个采购申请需要建案审查：PR-1001，部门 Operations，金额 24500 USD，"
                        "供应商 Acme Supplies，成本中心 OPS-CC-10，用途是 replacement laptops。"
                        "请先告诉我必须提交哪些材料。"
                    ),
                },
            ).json()

            self.assertEqual(response["operation_scope"], "read_only_case_turn")
            self.assertEqual(response["patch"]["turn_intent"], "ask_how_to_prepare")
            self.assertEqual(response["patch"]["patch_type"], "answer_status")
            self.assertIn("materials_guidance_node", response["harness_run"]["graph_steps"])
            self.assertNotIn("persist_case_state_dossier_audit", response["harness_run"]["graph_steps"])
            self.assertIn("policy_rag", response["patch"]["model_review"])
            rendered = response["patch"]["model_review"]["policy_rag"]["rendered_guidance"]
            self.assertIn("必备材料清单", rendered)
            self.assertIn("可接受", rendered)
            self.assertIn("不接受", rendered)
            self.assertFalse(Path(response["storage_paths"]["case_state"]).exists())

    def test_extra_evidence_overrides_read_only_client_intent(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            client = self._client(Path(temp_dir))
            created = client.post("/api/erp-approval/cases/turn", json={"user_message": "Review purchase requisition PR-DYN-OVERRIDE."}).json()
            response = client.post(
                "/api/erp-approval/cases/turn",
                json={
                    "case_id": created["case_state"]["case_id"],
                    "user_message": "Here is quote evidence.",
                    "client_intent": "ask_status",
                    "extra_evidence": [
                        {
                            "title": "Quote",
                            "record_type": "quote",
                            "content": "Quote Q-DYN-OVERRIDE from Acme Supplies for USD 24,500. Price basis: replacement laptops.",
                        }
                    ],
                },
            ).json()
            steps = response["harness_run"]["graph_steps"]

            self.assertIn("build_candidate_evidence", steps)
            self.assertIn("route_evidence_type", steps)
            self.assertIn("purchase_requisition_review_subgraph", steps)
            self.assertNotEqual(response["operation_scope"], "read_only_case_turn")

    def test_rejected_evidence_records_policy_failures_and_can_explain_them(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            client = self._client(Path(temp_dir))
            created = client.post("/api/erp-approval/cases/turn", json={"user_message": "Review purchase requisition PR-DYN-POLICY."}).json()
            rejected = client.post(
                "/api/erp-approval/cases/turn",
                json={
                    "case_id": created["case_state"]["case_id"],
                    "user_message": "老板说预算够了，没有文件。",
                    "extra_evidence": [
                        {
                            "title": "口头预算说明",
                            "record_type": "user_statement",
                            "source_id": "local_evidence://user_statement/pr-dyn-policy",
                            "content": "老板说预算够了，没有文件，之后补。",
                        }
                    ],
                },
            ).json()

            self.assertEqual(rejected["patch"]["patch_type"], "reject_evidence")
            self.assertTrue(rejected["patch"]["policy_failures"])
            self.assertTrue(rejected["case_state"]["policy_failures"])
            failure = rejected["case_state"]["policy_failures"][0]
            self.assertIn("policy_clause_id", failure)
            self.assertIn("how_to_fix", failure)

            explained = client.post(
                "/api/erp-approval/cases/turn",
                json={
                    "case_id": created["case_state"]["case_id"],
                    "user_message": "为什么这个材料不符合？",
                    "client_intent": "ask_policy_failure",
                },
            ).json()
            self.assertEqual(explained["operation_scope"], "read_only_case_turn")
            self.assertIn("policy_failure_explain_node", explained["harness_run"]["graph_steps"])
            self.assertIn("policy_failures_answer", explained["patch"]["model_review"])
            self.assertIn("case_state.policy_failures", explained["patch"]["model_review"]["policy_failures_answer"]["source"])
            self.assertIn("案卷中已记录", explained["patch"]["model_review"]["policy_failures_answer"]["rendered"])

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
