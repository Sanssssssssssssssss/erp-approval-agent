from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.domains.erp_approval.action_simulation import (
    build_simulation_record,
    validate_simulation_request,
)
from src.backend.domains.erp_approval.action_simulation_ledger import ApprovalActionSimulationRepository
from src.backend.domains.erp_approval.action_simulation_models import (
    ACTION_SIMULATION_NON_ACTION_STATEMENT,
    ApprovalActionSimulationQuery,
    ApprovalActionSimulationRequest,
)
from src.backend.domains.erp_approval.audit_workspace import build_saved_audit_package_manifest
from src.backend.domains.erp_approval.proposal_ledger import build_audit_package
from backend.tests.test_erp_approval_audit_package import proposal_record, trace_record


FORBIDDEN_OUTPUT_TERMS = ["sent", "posted", "routed", "approved", "rejected", "paid", "executed"]


def saved_package(proposal=None):
    proposal = proposal or proposal_record()
    audit_package = build_audit_package([trace_record()], [proposal], "2026-05-01T00:00:00+00:00")
    return build_saved_audit_package_manifest(audit_package, "Simulation package", "", "Ava", {}, "2026-05-01T00:00:00+00:00")


def simulation_request(**updates) -> ApprovalActionSimulationRequest:
    base = ApprovalActionSimulationRequest(
        proposal_record_id="erp-proposal-record:proposal-audit:trace-audit",
        package_id="erp-audit-package:3dec361714317907",
        requested_by="Ava",
        confirm_no_erp_write=True,
        note="Dry-run the next local review step.",
    )
    return base.model_copy(update=updates)


class ErpApprovalActionSimulationTests(unittest.TestCase):
    def test_validate_requires_confirm_no_erp_write(self) -> None:
        proposal = proposal_record()
        package = saved_package(proposal)
        request = simulation_request(package_id=package.package_id, confirm_no_erp_write=False)

        validation = validate_simulation_request(request, proposal, package)

        self.assertFalse(validation.passed)
        self.assertIn("confirm_no_erp_write", " ".join(validation.blocked_reasons))
        self.assertEqual(validation.non_action_statement, ACTION_SIMULATION_NON_ACTION_STATEMENT)

    def test_valid_request_more_info_generates_simulated_record(self) -> None:
        proposal = proposal_record()
        package = saved_package(proposal)
        request = simulation_request(package_id=package.package_id)
        validation = validate_simulation_request(request, proposal, package)

        record = build_simulation_record(request, proposal, package, validation, "2026-05-01T00:00:00+00:00")

        self.assertTrue(validation.passed)
        self.assertEqual(record.status, "simulated")
        self.assertTrue(record.simulated_only)
        self.assertFalse(record.erp_write_executed)
        self.assertEqual(record.output_preview["preview_type"], "would_prepare_local_request_more_info_draft")
        output_text = json.dumps(record.output_preview, sort_keys=True).lower()
        self.assertFalse(any(term in output_text for term in FORBIDDEN_OUTPUT_TERMS))

    def test_blocked_and_rejected_proposals_do_not_simulate(self) -> None:
        blocked = proposal_record(blocked=True, status="blocked")
        rejected = proposal_record(rejected_by_validation=True, status="rejected_by_validation")

        blocked_package = saved_package(blocked)
        rejected_package = saved_package(rejected)
        blocked_validation = validate_simulation_request(simulation_request(package_id=blocked_package.package_id), blocked, blocked_package)
        rejected_validation = validate_simulation_request(simulation_request(package_id=rejected_package.package_id), rejected, rejected_package)

        blocked_record = build_simulation_record(simulation_request(package_id=blocked_package.package_id), blocked, blocked_package, blocked_validation, "2026-05-01T00:00:00+00:00")
        rejected_record = build_simulation_record(simulation_request(package_id=rejected_package.package_id), rejected, rejected_package, rejected_validation, "2026-05-01T00:00:00+00:00")

        self.assertEqual(blocked_record.status, "blocked")
        self.assertEqual(rejected_record.status, "rejected_by_validation")
        self.assertFalse(blocked_validation.passed)
        self.assertFalse(rejected_validation.passed)
        self.assertTrue(blocked_record.simulated_only)
        self.assertFalse(blocked_record.erp_write_executed)

    def test_stable_simulation_id_and_repository_upsert_dedupes(self) -> None:
        proposal = proposal_record()
        package = saved_package(proposal)
        request = simulation_request(package_id=package.package_id)
        validation = validate_simulation_request(request, proposal, package)
        first = build_simulation_record(request, proposal, package, validation, "2026-05-01T00:00:00+00:00")
        second = build_simulation_record(request, proposal, package, validation, "2026-05-01T00:01:00+00:00")

        self.assertEqual(first.simulation_id, second.simulation_id)
        self.assertEqual(first.idempotency_fingerprint, second.idempotency_fingerprint)

        with tempfile.TemporaryDirectory() as temp_dir:
            repository = ApprovalActionSimulationRepository(Path(temp_dir) / "action_simulations.jsonl")
            first_result = repository.upsert(first)
            second_result = repository.upsert(second)
            recent = repository.list_recent(ApprovalActionSimulationQuery(limit=10))
            detail = repository.get(first.simulation_id)
            by_proposal = repository.by_proposal_record_id(proposal.proposal_record_id)

        self.assertTrue(first_result.created)
        self.assertFalse(second_result.created)
        self.assertEqual(len(recent), 1)
        self.assertIsNotNone(detail)
        self.assertEqual([record.simulation_id for record in by_proposal], [first.simulation_id])


if __name__ == "__main__":
    unittest.main()
