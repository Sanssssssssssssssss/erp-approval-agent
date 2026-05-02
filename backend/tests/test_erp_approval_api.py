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
from src.backend.domains.erp_approval.action_simulation_ledger import ApprovalActionSimulationRepository
from src.backend.domains.erp_approval.audit_workspace import ReviewerNoteRepository, SavedAuditPackageRepository
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

    def test_trace_filters_trends_and_exports_do_not_add_destructive_methods(self) -> None:
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
                methods = getattr(route, "methods", set())
                self.assertFalse(methods.intersection({"PUT", "PATCH", "DELETE"}))
                if "POST" in methods:
                    self.assertTrue(
                        "/audit-packages" in getattr(route, "path", "")
                        or getattr(route, "path", "") == "/api/erp-approval/action-simulations"
                        or getattr(route, "path", "") == "/api/erp-approval/case-review"
                    )
                self.assertNotIn("execute", getattr(route, "path", "").lower())

    def test_local_audit_workspace_endpoints_save_notes_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = ApprovalTraceRepository(Path(temp_dir) / "approval_traces.jsonl")
            proposal_repository = ApprovalActionProposalRepository(Path(temp_dir) / "action_proposals.jsonl")
            saved_repository = SavedAuditPackageRepository(Path(temp_dir) / "audit_packages.jsonl")
            note_repository = ReviewerNoteRepository(Path(temp_dir) / "reviewer_notes.jsonl")
            record = build_trace_record_from_state(sample_trace_state(), "2026-05-01T00:00:00+00:00")
            repository.upsert(record)
            proposal_repository.upsert_many(build_proposal_records_from_state(sample_proposal_state(), record.trace_id, "2026-05-01T00:00:00+00:00"))
            app = FastAPI()
            app.include_router(erp_approval_api.router, prefix="/api")
            with (
                patch.object(erp_approval_api, "_repository", return_value=repository),
                patch.object(erp_approval_api, "_proposal_repository", return_value=proposal_repository),
                patch.object(erp_approval_api, "_saved_package_repository", return_value=saved_repository),
                patch.object(erp_approval_api, "_note_repository", return_value=note_repository),
            ):
                client = TestClient(app)
                save_response = client.post(
                    "/api/erp-approval/audit-packages",
                    json={
                        "title": "May approval review",
                        "description": "Local internal review package",
                        "created_by": "Ava",
                        "trace_ids": [record.trace_id],
                        "filters": {"high_risk_only": False},
                    },
                )
                package_id = save_response.json()["package_id"]
                list_response = client.get("/api/erp-approval/audit-packages")
                detail_response = client.get(f"/api/erp-approval/audit-packages/{package_id}")
                empty_note_response = client.post(f"/api/erp-approval/audit-packages/{package_id}/notes", json={"author": "Ava", "body": ""})
                missing_package_response = client.post("/api/erp-approval/audit-packages/missing-package/notes", json={"author": "Ava", "body": "note"})
                note_response = client.post(
                    f"/api/erp-approval/audit-packages/{package_id}/notes",
                    json={"author": "Ava", "note_type": "risk", "body": "Check budget context.", "trace_id": record.trace_id},
                )
                notes_response = client.get(f"/api/erp-approval/audit-packages/{package_id}/notes")
                export_response = client.get(f"/api/erp-approval/audit-packages/{package_id}/export.json")

        self.assertEqual(save_response.status_code, 200)
        self.assertEqual(save_response.json()["title"], "May approval review")
        self.assertIn("package_snapshot", save_response.json())
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 1)
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(empty_note_response.status_code, 400)
        self.assertEqual(missing_package_response.status_code, 404)
        self.assertEqual(note_response.status_code, 200)
        self.assertIn("No ERP write action was executed", note_response.json()["non_action_statement"])
        self.assertEqual(notes_response.status_code, 200)
        self.assertEqual(len(notes_response.json()), 1)
        self.assertEqual(export_response.status_code, 200)
        self.assertEqual(export_response.json()["manifest"]["package_id"], package_id)
        self.assertEqual(len(export_response.json()["notes"]), 1)
        self.assertFalse(any("execute" in getattr(route, "path", "").lower() for route in app.routes))

    def test_local_action_simulation_endpoints_validate_and_persist_dry_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = ApprovalTraceRepository(Path(temp_dir) / "approval_traces.jsonl")
            proposal_repository = ApprovalActionProposalRepository(Path(temp_dir) / "action_proposals.jsonl")
            saved_repository = SavedAuditPackageRepository(Path(temp_dir) / "audit_packages.jsonl")
            note_repository = ReviewerNoteRepository(Path(temp_dir) / "reviewer_notes.jsonl")
            simulation_repository = ApprovalActionSimulationRepository(Path(temp_dir) / "action_simulations.jsonl")
            record = build_trace_record_from_state(sample_trace_state(), "2026-05-01T00:00:00+00:00")
            repository.upsert(record)
            proposal_records = build_proposal_records_from_state(sample_proposal_state(), record.trace_id, "2026-05-01T00:00:00+00:00")
            proposal_repository.upsert_many(proposal_records)
            proposal_id = proposal_records[0].proposal_record_id
            app = FastAPI()
            app.include_router(erp_approval_api.router, prefix="/api")
            with (
                patch.object(erp_approval_api, "_repository", return_value=repository),
                patch.object(erp_approval_api, "_proposal_repository", return_value=proposal_repository),
                patch.object(erp_approval_api, "_saved_package_repository", return_value=saved_repository),
                patch.object(erp_approval_api, "_note_repository", return_value=note_repository),
                patch.object(erp_approval_api, "_simulation_repository", return_value=simulation_repository),
            ):
                client = TestClient(app)
                package_response = client.post(
                    "/api/erp-approval/audit-packages",
                    json={"title": "Simulation package", "created_by": "Ava", "trace_ids": [record.trace_id]},
                )
                package_id = package_response.json()["package_id"]
                missing_proposal_response = client.post(
                    "/api/erp-approval/action-simulations",
                    json={"proposal_record_id": "missing", "package_id": package_id, "requested_by": "Ava", "confirm_no_erp_write": True},
                )
                missing_package_response = client.post(
                    "/api/erp-approval/action-simulations",
                    json={"proposal_record_id": proposal_id, "package_id": "missing-package", "requested_by": "Ava", "confirm_no_erp_write": True},
                )
                no_confirm_response = client.post(
                    "/api/erp-approval/action-simulations",
                    json={"proposal_record_id": proposal_id, "package_id": package_id, "requested_by": "Ava", "confirm_no_erp_write": False},
                )
                empty_package_response = client.post(
                    "/api/erp-approval/audit-packages",
                    json={"title": "Empty package", "created_by": "Ava", "filters": {"text_query": "does-not-match-any-trace"}},
                )
                not_in_package_response = client.post(
                    "/api/erp-approval/action-simulations",
                    json={
                        "proposal_record_id": proposal_id,
                        "package_id": empty_package_response.json()["package_id"],
                        "requested_by": "Ava",
                        "confirm_no_erp_write": True,
                    },
                )
                valid_response = client.post(
                    "/api/erp-approval/action-simulations",
                    json={
                        "proposal_record_id": proposal_id,
                        "package_id": package_id,
                        "requested_by": "Ava",
                        "confirm_no_erp_write": True,
                        "note": "Dry-run only.",
                    },
                )
                simulation_id = valid_response.json()["simulation_id"]
                detail_response = client.get(f"/api/erp-approval/action-simulations/{simulation_id}")
                list_response = client.get("/api/erp-approval/action-simulations")
                by_proposal_response = client.get(f"/api/erp-approval/proposals/{proposal_id}/simulations")

                blocked = proposal_records[0].model_copy(
                    update={
                        "proposal_record_id": "erp-proposal-record:blocked:trace",
                        "proposal_id": "blocked",
                        "status": "blocked",
                        "blocked": True,
                    }
                )
                proposal_repository.upsert_many([blocked])
                valid_manifest = saved_repository.get(package_id)
                self.assertIsNotNone(valid_manifest)
                saved_repository.upsert(valid_manifest.model_copy(update={"package_id": "package-blocked", "proposal_record_ids": [blocked.proposal_record_id]}))
                blocked_response = client.post(
                    "/api/erp-approval/action-simulations",
                    json={
                        "proposal_record_id": blocked.proposal_record_id,
                        "package_id": "package-blocked",
                        "requested_by": "Ava",
                        "confirm_no_erp_write": True,
                    },
                )

        self.assertEqual(missing_proposal_response.status_code, 404)
        self.assertEqual(missing_package_response.status_code, 404)
        self.assertEqual(no_confirm_response.status_code, 400)
        self.assertEqual(not_in_package_response.status_code, 400)
        self.assertEqual(valid_response.status_code, 200)
        self.assertEqual(valid_response.json()["status"], "simulated")
        self.assertTrue(valid_response.json()["simulated_only"])
        self.assertFalse(valid_response.json()["erp_write_executed"])
        self.assertIn("No ERP write action was executed", valid_response.json()["non_action_statement"])
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 1)
        self.assertEqual(by_proposal_response.status_code, 200)
        self.assertEqual(len(by_proposal_response.json()), 1)
        self.assertEqual(blocked_response.status_code, 200)
        self.assertEqual(blocked_response.json()["status"], "blocked")
        self.assertTrue(blocked_response.json()["simulated_only"])
        self.assertFalse(blocked_response.json()["erp_write_executed"])

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
