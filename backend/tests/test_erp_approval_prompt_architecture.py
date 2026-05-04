from __future__ import annotations

import inspect
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.domains.erp_approval import case_stage_model
from src.backend.domains.erp_approval.case_prompt_registry import (
    CUSTOM_CASE_PROMPTS,
    build_case_prompt_catalog,
    case_prompt_text,
    custom_case_prompt,
)


class ErpApprovalPromptArchitectureTests(unittest.TestCase):
    def test_role_prompts_have_single_canonical_definition(self) -> None:
        source = inspect.getsource(case_stage_model)

        self.assertNotIn("ROLE_PROMPTS.update", source)
        self.assertNotIn("strict enterprise ERP approval case reviewer", case_stage_model.BASE_STAGE_MODEL_PROMPT)
        self.assertIn("LLM-first ERP approval dossier agent", case_stage_model.BASE_STAGE_MODEL_PROMPT)
        self.assertIn("reviewer_memo", case_stage_model.ROLE_PROMPTS)
        self.assertIn("review synthesizer", case_stage_model.ROLE_PROMPTS["reviewer_memo"].lower())

    def test_agent_reply_is_alias_to_single_user_response_writer(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            base_dir = Path(temp_dir)

            self.assertNotIn("agent_reply", CUSTOM_CASE_PROMPTS)
            self.assertEqual(
                case_prompt_text("agent_reply", "fallback", base_dir),
                case_prompt_text("llm_user_response_writer", "fallback", base_dir),
            )
            self.assertEqual(custom_case_prompt("agent_reply", base_dir), custom_case_prompt("llm_user_response_writer", base_dir))

    def test_observation_prompts_do_not_claim_final_user_reply_ownership(self) -> None:
        prompt_expectations = {
            "policy_guidance": "materials_observation",
            "missing_requirements_answer": "missing_observation",
            "policy_failure_explainer": "failure_observation",
        }

        for prompt_id, expected_field in prompt_expectations.items():
            prompt = CUSTOM_CASE_PROMPTS[prompt_id].default_prompt
            self.assertIn(expected_field, prompt)
            self.assertIn("Do not write the final user-facing answer", prompt)

        writer_prompt = CUSTOM_CASE_PROMPTS["llm_user_response_writer"].default_prompt
        self.assertIn("only role allowed to write user-visible business replies", writer_prompt)
        self.assertIn("agent_reply.markdown", writer_prompt)

    def test_prompt_catalog_exposes_writer_once_and_labels_review_synthesizer(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            catalog = build_case_prompt_catalog(base_dir=Path(temp_dir), role_prompts=case_stage_model.ROLE_PROMPTS)

        prompt_ids = [item["prompt_id"] for item in catalog]
        self.assertEqual(prompt_ids.count("llm_user_response_writer"), 1)
        self.assertNotIn("agent_reply", prompt_ids)

        role_items = {item["prompt_id"]: item for item in catalog if item["prompt_id"].startswith("role:")}
        self.assertEqual(role_items["role:reviewer_memo"]["label"], "Review Synthesizer")
        self.assertEqual(role_items["role:reviewer_memo"]["node_id"], "llm_reviewer_memo")


if __name__ == "__main__":
    unittest.main()
