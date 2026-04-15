from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from benchmarks.evaluator import evaluate_case


class BenchmarkEvaluatorTests(unittest.TestCase):
    def test_pdf_and_extracted_txt_are_treated_as_same_source_family(self) -> None:
        case = {
            "id": "rag_pdf_family_case",
            "module": "rag",
            "subtype": "retrieval",
            "question_type": "direct_fact",
            "input": "test",
            "gold_sources": ["Financial Report Data/上汽集团 2025 Q3.pdf"],
            "required_source_types": ["pdf"],
            "should_have_final_answer": True,
        }
        trace = {
            "detected_route": "knowledge",
            "called_tools": [],
            "retrieval_sources": [
                "knowledge/Financial Report Data/上汽集团_2025_Q3_extracted.txt",
            ],
            "knowledge_used": True,
            "final_answer": "来源为上汽集团财报抽取文本。",
            "error_message": "",
        }

        result = evaluate_case(case, trace, {"pdf", "txt", "md", "json", "xlsx"})

        self.assertTrue(result["checks"]["retrieval_pass"])
        self.assertEqual(
            result["gold_source_families"],
            ["knowledge/Financial Report Data/上汽集团 2025 Q3.pdf"],
        )
        self.assertEqual(
            result["retrieval_source_families"],
            ["knowledge/Financial Report Data/上汽集团 2025 Q3.pdf"],
        )

    def test_report_txt_companion_maps_to_pdf_source_family(self) -> None:
        case = {
            "id": "rag_pdf_txt_family_case",
            "module": "rag",
            "subtype": "retrieval",
            "question_type": "direct_fact",
            "input": "test",
            "gold_sources": ["Financial Report Data/航天动力 2025 Q3.pdf"],
            "required_source_types": ["pdf"],
            "should_have_final_answer": True,
        }
        trace = {
            "detected_route": "knowledge",
            "called_tools": [],
            "retrieval_sources": [
                "knowledge/Financial Report Data/航天动力_2025_Q3.txt",
            ],
            "knowledge_used": True,
            "final_answer": "来源为航天动力财报文本副本。",
            "error_message": "",
        }

        result = evaluate_case(case, trace, {"pdf", "txt"})

        self.assertTrue(result["checks"]["retrieval_pass"])
        self.assertEqual(
            result["retrieval_source_families"],
            ["knowledge/Financial Report Data/航天动力 2025 Q3.pdf"],
        )

    def test_cross_file_coverage_uses_source_family_matching(self) -> None:
        case = {
            "id": "rag_cross_file_family_case",
            "module": "rag",
            "subtype": "retrieval",
            "question_type": "cross_file_aggregation",
            "input": "test",
            "gold_sources": [
                "Financial Report Data/上汽集团 2025 Q3.pdf",
                "Financial Report Data/航天动力 2025 Q3.pdf",
            ],
            "required_source_types": ["pdf"],
        }
        trace = {
            "detected_route": "knowledge",
            "called_tools": [],
            "retrieval_sources": [
                "knowledge/Financial Report Data/上汽集团_2025_Q3_extracted.txt",
                "knowledge/Financial Report Data/航天动力_2025_Q3.txt",
            ],
            "knowledge_used": True,
            "final_answer": "test",
            "error_message": "",
        }

        result = evaluate_case(case, trace, {"pdf", "txt"})

        self.assertEqual(result["source_coverage"], 1.0)
        self.assertTrue(result["checks"]["retrieval_pass"])

    def test_gold_evidence_ids_drive_citation_metrics_when_available(self) -> None:
        case = {
            "id": "rag_evidence_id_case",
            "module": "rag",
            "subtype": "rfp_security",
            "question_type": "direct_fact",
            "input": "test",
            "gold_sources": ["RFP Security/security_controls.md"],
            "gold_evidence_ids": ["RFP Security/security_controls.md"],
            "required_source_types": ["md"],
            "should_have_final_answer": True,
        }
        trace = {
            "detected_route": "knowledge",
            "called_tools": [],
            "retrieval_sources": ["knowledge/RFP Security/security_controls.md"],
            "knowledge_used": True,
            "final_answer": "Supported by the control sheet.",
            "error_message": "",
            "final_evidence_results": [
                {
                    "source_path": "knowledge/RFP Security/security_controls.md",
                    "locator": "Identity and access management / paragraph 1",
                    "snippet": "The service supports SAML 2.0 and OpenID Connect single sign-on.",
                    "source_type": "md",
                }
            ],
        }

        result = evaluate_case(case, trace, {"md"})

        self.assertEqual(result["gold_evidence_ids"], ["knowledge/RFP Security/security_controls.md"])
        self.assertEqual(result["citation_precision"], 0.5)
        self.assertEqual(result["citation_recall"], 1.0)


if __name__ == "__main__":
    unittest.main()
