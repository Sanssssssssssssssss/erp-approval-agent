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
from src.backend.domains.erp_approval.trace_store import ApprovalTraceRepository, build_trace_record_from_state
from backend.tests.test_erp_approval_trace_store import sample_trace_state


class ErpApprovalApiTests(unittest.TestCase):
    def test_trace_and_analytics_endpoints_are_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = ApprovalTraceRepository(Path(temp_dir) / "approval_traces.jsonl")
            record = build_trace_record_from_state(sample_trace_state(), "2026-05-01T00:00:00+00:00")
            repository.upsert(record)
            app = FastAPI()
            app.include_router(erp_approval_api.router, prefix="/api")
            with patch.object(erp_approval_api, "_repository", return_value=repository):
                client = TestClient(app)
                traces_response = client.get("/api/erp-approval/traces?limit=10")
                trace_response = client.get(f"/api/erp-approval/traces/{record.trace_id}")
                summary_response = client.get("/api/erp-approval/analytics/summary?limit=10")

        self.assertEqual(traces_response.status_code, 200)
        self.assertEqual(len(traces_response.json()), 1)
        self.assertEqual(trace_response.status_code, 200)
        self.assertEqual(trace_response.json()["trace_id"], record.trace_id)
        self.assertEqual(summary_response.status_code, 200)
        self.assertEqual(summary_response.json()["total_traces"], 1)

    def test_empty_summary_returns_zero(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = ApprovalTraceRepository(Path(temp_dir) / "approval_traces.jsonl")
            app = FastAPI()
            app.include_router(erp_approval_api.router, prefix="/api")
            with patch.object(erp_approval_api, "_repository", return_value=repository):
                response = TestClient(app).get("/api/erp-approval/analytics/summary")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total_traces"], 0)


if __name__ == "__main__":
    unittest.main()
