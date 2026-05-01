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
from src.backend.domains.erp_approval.proposal_ledger import (
    ApprovalActionProposalRepository,
    build_proposal_records_from_state,
)
from src.backend.domains.erp_approval.trace_store import ApprovalTraceRepository, build_trace_record_from_state
from backend.tests.test_erp_approval_proposal_ledger import sample_proposal_state
from backend.tests.test_erp_approval_trace_store import sample_record, sample_trace_state


class ErpApprovalApiTests(unittest.TestCase):
    def test_trace_and_analytics_endpoints_are_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = ApprovalTraceRepository(Path(temp_dir) / "approval_traces.jsonl")
            proposal_repository = ApprovalActionProposalRepository(Path(temp_dir) / "action_proposals.jsonl")
            record = build_trace_record_from_state(sample_trace_state(), "2026-05-01T00:00:00+00:00")
            repository.upsert(record)
            proposal_state = sample_proposal_state()
            proposal_repository.upsert_many(build_proposal_records_from_state(proposal_state, record.trace_id, "2026-05-01T00:00:00+00:00"))
            app = FastAPI()
            app.include_router(erp_approval_api.router, prefix="/api")
            with (
                patch.object(erp_approval_api, "_repository", return_value=repository),
                patch.object(erp_approval_api, "_proposal_repository", return_value=proposal_repository),
            ):
                client = TestClient(app)
                traces_response = client.get("/api/erp-approval/traces?limit=10")
                trace_response = client.get(f"/api/erp-approval/traces/{record.trace_id}")
                proposals_response = client.get(f"/api/erp-approval/traces/{record.trace_id}/proposals")
                audit_response = client.get(f"/api/erp-approval/audit-package?trace_ids={record.trace_id}")
                summary_response = client.get("/api/erp-approval/analytics/summary?limit=10")

        self.assertEqual(traces_response.status_code, 200)
        self.assertEqual(len(traces_response.json()), 1)
        self.assertEqual(trace_response.status_code, 200)
        self.assertEqual(trace_response.json()["trace_id"], record.trace_id)
        self.assertEqual(proposals_response.status_code, 200)
        self.assertEqual(len(proposals_response.json()), 1)
        self.assertEqual(audit_response.status_code, 200)
        self.assertEqual(audit_response.json()["trace_ids"], [record.trace_id])
        self.assertTrue(audit_response.json()["completeness_checks"])
        self.assertEqual(summary_response.status_code, 200)
        self.assertEqual(summary_response.json()["total_traces"], 1)

    def test_trace_filters_trends_and_exports_are_get_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = ApprovalTraceRepository(Path(temp_dir) / "approval_traces.jsonl")
            proposal_repository = ApprovalActionProposalRepository(Path(temp_dir) / "action_proposals.jsonl")
            repository.upsert(sample_record("trace-pr", approval_type="purchase_requisition", proposal_action_types=["request_more_info"]))
            repository.upsert(
                sample_record(
                    "trace-exp",
                    approval_id="EXP-2001",
                    approval_type="expense",
                    recommendation_status="recommend_approve",
                    review_status="not_required",
                    proposal_action_types=["add_internal_comment"],
                    human_review_required=False,
                )
            )
            app = FastAPI()
            app.include_router(erp_approval_api.router, prefix="/api")
            proposal_repository.upsert_many(build_proposal_records_from_state(sample_proposal_state(), "trace-pr", "2026-05-01T00:00:00+00:00"))
            with (
                patch.object(erp_approval_api, "_repository", return_value=repository),
                patch.object(erp_approval_api, "_proposal_repository", return_value=proposal_repository),
            ):
                client = TestClient(app)
                traces_response = client.get("/api/erp-approval/traces?approval_type=expense")
                proposals_response = client.get("/api/erp-approval/proposals?action_type=request_more_info")
                proposal_detail_response = client.get(f"/api/erp-approval/proposals/{proposals_response.json()[0]['proposal_record_id']}")
                trends_response = client.get("/api/erp-approval/analytics/trends?limit=10")
                json_response = client.get("/api/erp-approval/export.json?recommendation_status=recommend_approve")
                csv_response = client.get("/api/erp-approval/export.csv?proposal_action_type=request_more_info")

        self.assertEqual(traces_response.status_code, 200)
        self.assertEqual([item["trace_id"] for item in traces_response.json()], ["trace-exp"])
        self.assertEqual(proposals_response.status_code, 200)
        self.assertEqual(len(proposals_response.json()), 1)
        self.assertEqual(proposal_detail_response.status_code, 200)
        self.assertEqual(proposal_detail_response.json()["action_type"], "request_more_info")
        self.assertEqual(trends_response.status_code, 200)
        self.assertEqual(trends_response.json()["bucket_field"], "created_at_date")
        self.assertEqual(json_response.status_code, 200)
        self.assertEqual(json_response.json()["total"], 1)
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn("trace_id,created_at,approval_id", csv_response.text.splitlines()[0])

        for route in app.routes:
            if getattr(route, "path", "").startswith("/api/erp-approval"):
                self.assertEqual(getattr(route, "methods", set()), {"GET"})

    def test_empty_summary_returns_zero(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = ApprovalTraceRepository(Path(temp_dir) / "approval_traces.jsonl")
            proposal_repository = ApprovalActionProposalRepository(Path(temp_dir) / "action_proposals.jsonl")
            app = FastAPI()
            app.include_router(erp_approval_api.router, prefix="/api")
            with (
                patch.object(erp_approval_api, "_repository", return_value=repository),
                patch.object(erp_approval_api, "_proposal_repository", return_value=proposal_repository),
            ):
                client = TestClient(app)
                summary_response = client.get("/api/erp-approval/analytics/summary")
                trends_response = client.get("/api/erp-approval/analytics/trends")
                json_response = client.get("/api/erp-approval/export.json")
                csv_response = client.get("/api/erp-approval/export.csv")
                proposals_response = client.get("/api/erp-approval/proposals")
                audit_response = client.get("/api/erp-approval/audit-package")

        self.assertEqual(summary_response.status_code, 200)
        self.assertEqual(summary_response.json()["total_traces"], 0)
        self.assertEqual(trends_response.status_code, 200)
        self.assertEqual(trends_response.json()["buckets"], [])
        self.assertEqual(json_response.status_code, 200)
        self.assertEqual(json_response.json()["records"], [])
        self.assertEqual(proposals_response.status_code, 200)
        self.assertEqual(proposals_response.json(), [])
        self.assertEqual(audit_response.status_code, 200)
        self.assertEqual(audit_response.json()["traces"], [])
        self.assertEqual(audit_response.json()["proposals"], [])
        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(
            csv_response.text.splitlines()[0],
            "trace_id,created_at,approval_id,approval_type,recommendation_status,review_status,human_review_required,guard_downgraded,proposal_action_types,blocked_proposal_ids,rejected_proposal_ids",
        )


if __name__ == "__main__":
    unittest.main()
