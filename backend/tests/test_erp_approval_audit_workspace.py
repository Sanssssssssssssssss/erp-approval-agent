from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.domains.erp_approval.audit_workspace import (
    ReviewerNoteRepository,
    SavedAuditPackageRepository,
    append_reviewer_note,
    build_saved_audit_package_manifest,
)
from src.backend.domains.erp_approval.audit_workspace_models import SavedAuditPackageQuery
from src.backend.domains.erp_approval.proposal_ledger import build_audit_package
from backend.tests.test_erp_approval_audit_package import proposal_record, trace_record


def sample_audit_package():
    return build_audit_package([trace_record()], [proposal_record()], "2026-05-01T00:00:00+00:00")


class ErpApprovalAuditWorkspaceTests(unittest.TestCase):
    def test_build_saved_audit_package_manifest_snapshot_and_stable_hash(self) -> None:
        package = sample_audit_package()

        first = build_saved_audit_package_manifest(package, "May review", "Internal review", "Ava", {"high_risk_only": True}, "2026-05-01T00:00:00+00:00")
        second = build_saved_audit_package_manifest(package, "May review", "Internal review", "Ava", {"high_risk_only": True}, "2026-05-01T00:00:00+00:00")

        self.assertEqual(first.package_hash, second.package_hash)
        self.assertEqual(first.package_snapshot["package_id"], package.package_id)
        self.assertEqual(first.source_filters["high_risk_only"], True)
        self.assertIn("No ERP write action was executed", first.non_action_statement)

    def test_saved_package_upsert_dedupes_and_list_recent_returns_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = SavedAuditPackageRepository(Path(temp_dir) / "audit_packages.jsonl")
            manifest = build_saved_audit_package_manifest(sample_audit_package(), "May review", "", "Ava", {}, "2026-05-01T00:00:00+00:00")

            first = repository.upsert(manifest)
            second = repository.upsert(manifest.model_copy(update={"updated_at": "2026-05-01T00:01:00+00:00"}))
            records = repository.list_recent(SavedAuditPackageQuery(limit=10))

        self.assertTrue(first.success)
        self.assertTrue(first.created)
        self.assertTrue(second.success)
        self.assertFalse(second.created)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].title, "May review")

    def test_export_package_returns_manifest_and_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = SavedAuditPackageRepository(Path(temp_dir) / "audit_packages.jsonl")
            manifest = build_saved_audit_package_manifest(sample_audit_package(), "May review", "", "Ava", {}, "2026-05-01T00:00:00+00:00")
            repository.upsert(manifest)

            exported = repository.export_package(manifest.package_id)

        self.assertIsNotNone(exported)
        self.assertEqual(exported.manifest.package_id, manifest.package_id)
        self.assertEqual(exported.package_snapshot["package_id"], manifest.package_id)

    def test_reviewer_notes_append_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = ReviewerNoteRepository(Path(temp_dir) / "reviewer_notes.jsonl")
            first = append_reviewer_note(package_id="pkg-1", author="Ava", note_type="risk", body="Check budget owner.", now="2026-05-01T00:00:00+00:00")
            second = append_reviewer_note(package_id="pkg-1", author="Ava", note_type="follow_up", body="Follow up next week.", now="2026-05-01T00:01:00+00:00")

            first_result = repository.append(first)
            second_result = repository.append(second)
            notes = repository.list_for_package("pkg-1")

        self.assertTrue(first_result.success)
        self.assertTrue(second_result.success)
        self.assertEqual(len(notes), 2)
        self.assertEqual([note.body for note in notes], ["Follow up next week.", "Check budget owner."])


if __name__ == "__main__":
    unittest.main()
