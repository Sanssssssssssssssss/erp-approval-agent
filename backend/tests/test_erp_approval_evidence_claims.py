from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.domains.erp_approval.case_models import ApprovalCaseFile, EvidenceClaim
from src.backend.domains.erp_approval.context_adapter import ErpContextQuery, MockErpContextAdapter
from src.backend.domains.erp_approval.evidence_claims import (
    build_evidence_artifacts,
    detect_contradictions,
    extract_claims_from_artifacts,
    link_claims_to_requirements,
)
from src.backend.domains.erp_approval.evidence_requirements import requirement_matrix_for_approval_type
from src.backend.domains.erp_approval.schemas import ApprovalRequest


class ErpApprovalEvidenceClaimTests(unittest.TestCase):
    def test_claims_from_mock_context_have_source_ids_and_link_to_requirements(self) -> None:
        request = ApprovalRequest(
            approval_type="purchase_requisition",
            approval_id="PR-1001",
            requester="Lin Chen",
            amount=24500,
            vendor="Acme Supplies",
            cost_center="OPS-CC-10",
            raw_request="Review PR-1001",
        )
        context = MockErpContextAdapter(base_dir=BACKEND_DIR).fetch_context(ErpContextQuery.from_request(request))
        case_file = ApprovalCaseFile(approval_type=request.approval_type, approval_id=request.approval_id)
        artifacts = build_evidence_artifacts(request, context)
        claims = extract_claims_from_artifacts(case_file, artifacts)
        requirements, claims = link_claims_to_requirements(requirement_matrix_for_approval_type("purchase_requisition"), claims)

        self.assertTrue(all(claim.source_id for claim in claims))
        self.assertTrue(any(claim.claim_type == "budget_available" for claim in claims))
        budget_requirement = next(item for item in requirements if item.requirement_id.endswith(":budget_availability"))
        self.assertEqual(budget_requirement.status, "satisfied")

    def test_user_statement_claim_cannot_satisfy_blocking_requirement(self) -> None:
        request = ApprovalRequest(approval_type="purchase_requisition", raw_request="我说预算够、供应商也没问题。")
        context = MockErpContextAdapter(fixture_path=BACKEND_DIR / "missing-fixture.json").fetch_context(
            ErpContextQuery(approval_type="purchase_requisition")
        )
        case_file = ApprovalCaseFile(approval_type="purchase_requisition")
        artifacts = build_evidence_artifacts(request, context)
        claims = extract_claims_from_artifacts(case_file, artifacts)
        requirements, _claims = link_claims_to_requirements(requirement_matrix_for_approval_type("purchase_requisition"), claims)

        approval_request = next(item for item in requirements if item.requirement_id.endswith(":approval_request"))
        self.assertNotEqual(approval_request.status, "satisfied")

    def test_detect_contradictions_for_conflicting_amounts(self) -> None:
        claims = [
            EvidenceClaim(
                claim_id="c1",
                claim_type="approval_request_present",
                statement="amount 100",
                source_id="mock_erp://approval_request/A",
                normalized_value={"amount": 100, "vendor": "Acme"},
            ),
            EvidenceClaim(
                claim_id="c2",
                claim_type="approval_request_present",
                statement="amount 200",
                source_id="mock_erp://approval_request/B",
                normalized_value={"amount": 200, "vendor": "Acme"},
            ),
        ]

        report = detect_contradictions(claims)

        self.assertTrue(report.has_conflict)
        self.assertEqual(report.severity, "high")


if __name__ == "__main__":
    unittest.main()
