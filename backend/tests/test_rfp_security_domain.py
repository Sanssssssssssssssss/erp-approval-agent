from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.domains.rfp_security.exports import build_section_level_draft
from src.backend.domains.rfp_security.normalizers import normalize_rfp_security_query
from src.backend.domains.rfp_security.policies import evaluate_policy_decision
from src.backend.knowledge.types import Evidence


class RfpSecurityDomainTests(unittest.TestCase):
    def test_normalizer_marks_critical_reference_requests_for_approval(self) -> None:
        question = normalize_rfp_security_query(
            "Provide three named customer references.",
            tags=["requires_approval"],
            risk_level="critical",
            required_points=["named customer references require customer approval"],
        )

        self.assertEqual(question.question_kind, "approval_review")
        self.assertIn("named customer references require customer approval", question.required_points)
        self.assertEqual(question.answer_template_kind, "policy_process")
        self.assertIn("Focus points:", question.normalized_query)

    def test_policy_detects_conflicting_notification_windows(self) -> None:
        question = normalize_rfp_security_query(
            "Resolve the incident notification timeline.",
            tags=["conflicting_evidence"],
            risk_level="high",
            required_points=["24 hours"],
        )
        evidences = [
            Evidence(
                source_path="knowledge/RFP Security/incident_response.md",
                source_type="md",
                locator="Notification / paragraph 1",
                snippet="Security incidents involving customer data are notified within 24 hours.",
                channel="vector",
            ),
            Evidence(
                source_path="knowledge/RFP Security/legacy_answers.txt",
                source_type="txt",
                locator="legacy_answers / paragraph 1",
                snippet="Older draft answer said incidents would be notified within 72 hours.",
                channel="bm25",
            ),
        ]

        decision = evaluate_policy_decision(question, evidences)

        self.assertTrue(decision.has_conflict)
        self.assertEqual(decision.status, "conflict")
        self.assertTrue(decision.evidence_plan.items)

    def test_export_surfaces_missing_evidence_and_approval(self) -> None:
        question = normalize_rfp_security_query(
            "Attach the latest penetration test report.",
            tags=["requires_approval"],
            risk_level="critical",
            required_points=["penetration test reports require security approval"],
        )
        evidence = Evidence(
            source_path="knowledge/RFP Security/approval_policy.md",
            source_type="md",
            locator="High-sensitivity statements / paragraph 2",
            snippet="Penetration test reports require security approval before disclosure.",
            channel="vector",
        )
        decision = evaluate_policy_decision(question, [evidence])
        draft = build_section_level_draft(question, [evidence], decision)

        self.assertIn("requires_approval:", draft.answer)
        self.assertIn("penetration test reports require security approval", draft.answer)
        self.assertGreaterEqual(draft.groundedness, 0.5)
        self.assertEqual(
            draft.selected_evidence_ids,
            ("knowledge/RFP Security/approval_policy.md|High-sensitivity statements / paragraph 2",),
        )
