from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.domains.erp_approval.case_review import build_case_file_from_request_context, render_case_analysis
from src.backend.domains.erp_approval.context_adapter import ErpContextQuery, MockErpContextAdapter
from src.backend.domains.erp_approval.schemas import ApprovalGuardResult, ApprovalRecommendation, ApprovalRequest


class ErpApprovalCaseFileTests(unittest.TestCase):
    def test_one_sentence_creates_case_but_not_sufficient_evidence(self) -> None:
        request = ApprovalRequest(
            approval_type="purchase_requisition",
            approval_id="",
            raw_request="请审核采购申请，预算够，供应商没问题。",
        )
        context = MockErpContextAdapter(fixture_path=BACKEND_DIR / "missing-fixture.json").fetch_context(
            ErpContextQuery(approval_type="purchase_requisition")
        )

        case_file = build_case_file_from_request_context(request, context)

        self.assertFalse(case_file.evidence_sufficiency.passed)
        self.assertTrue(case_file.evidence_sufficiency.blocking_gaps)
        self.assertTrue(any(req.status == "missing" for req in case_file.evidence_requirements if req.blocking))

    def test_render_case_analysis_contains_required_sections_and_boundary(self) -> None:
        request = ApprovalRequest(approval_type="purchase_requisition", approval_id="PR-1001", raw_request="Review PR-1001")
        context = MockErpContextAdapter(base_dir=BACKEND_DIR).fetch_context(ErpContextQuery.from_request(request))
        case_file = build_case_file_from_request_context(request, context)
        recommendation = ApprovalRecommendation(status="request_more_info", summary="Need more evidence.")

        rendered = render_case_analysis(case_file, recommendation, ApprovalGuardResult())

        self.assertIn("必需证据清单", rendered)
        self.assertIn("控制矩阵检查", rendered)
        self.assertIn("No ERP write action was executed", rendered)


if __name__ == "__main__":
    unittest.main()
