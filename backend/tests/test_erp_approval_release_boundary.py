from __future__ import annotations

import sys
import unittest
from pathlib import Path

from fastapi import FastAPI

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.api import erp_approval as erp_approval_api
from src.backend.orchestration.state import GRAPH_VERSION, create_initial_graph_state


class ErpApprovalReleaseBoundaryTests(unittest.TestCase):
    def test_graph_version_is_final_mvp_phase14(self) -> None:
        state = create_initial_graph_state(
            run_id="run-release-boundary",
            session_id="session-release-boundary",
            thread_id="thread-release-boundary",
            user_message="",
            history=[],
        )

        self.assertEqual(GRAPH_VERSION, "phase14")
        self.assertEqual(state["checkpoint_meta"]["graph_version"], "phase14")

    def test_erp_api_has_no_execution_or_live_connector_routes(self) -> None:
        app = FastAPI()
        app.include_router(erp_approval_api.router, prefix="/api")
        allowed_local_post_paths = {
            "/api/erp-approval/cases/turn",
            "/api/erp-approval/case-graph/prompts/{prompt_id:path}",
            "/api/erp-approval/action-simulations",
            "/api/erp-approval/audit-packages",
            "/api/erp-approval/audit-packages/{package_id}/notes",
        }
        forbidden_segments = {
            "execute",
            "test-live",
            "connect",
            "approve",
            "reject",
            "payment",
            "comment",
            "request-more-info",
            "route",
            "supplier",
            "budget-update",
            "contract-sign",
        }

        for route in app.routes:
            path = str(getattr(route, "path", ""))
            if not path.startswith("/api/erp-approval"):
                continue
            methods = set(getattr(route, "methods", set()))
            self.assertFalse(methods.intersection({"PUT", "PATCH", "DELETE"}), path)
            if "POST" in methods:
                self.assertIn(path, allowed_local_post_paths)
            path_segments = {segment for segment in path.lower().split("/") if segment}
            self.assertFalse(path_segments.intersection(forbidden_segments), path)

    def test_connector_endpoints_remain_get_only(self) -> None:
        app = FastAPI()
        app.include_router(erp_approval_api.router, prefix="/api")

        connector_routes = [
            route
            for route in app.routes
            if str(getattr(route, "path", "")).startswith("/api/erp-approval/connectors")
        ]

        self.assertTrue(connector_routes)
        for route in connector_routes:
            self.assertEqual(set(getattr(route, "methods", set())), {"GET"}, getattr(route, "path", ""))

    def test_no_approval_harness_event_namespace_is_introduced(self) -> None:
        source_root = REPO_ROOT / "src" / "backend"
        offenders: list[str] = []
        for path in source_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if '"approval.' in text or "'approval." in text:
                offenders.append(str(path.relative_to(REPO_ROOT)))

        self.assertEqual(offenders, [])

    def test_final_mvp_docs_exist(self) -> None:
        self.assertTrue((REPO_ROOT / "docs" / "product" / "mvp_acceptance_checklist.md").exists())
        self.assertTrue((REPO_ROOT / "reports" / "phase14_final_mvp_closure.md").exists())


if __name__ == "__main__":
    unittest.main()
