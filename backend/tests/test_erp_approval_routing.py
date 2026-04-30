from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.decision.execution_strategy import parse_execution_strategy
from src.backend.decision.lightweight_router import deterministic_route


class ErpApprovalRoutingTests(unittest.TestCase):
    def test_deterministic_route_detects_chinese_procurement_approval(self) -> None:
        message = "请帮我审核这个采购申请审批，金额5000元，供应商是Acme。"
        decision = deterministic_route(
            message=message,
            strategy=parse_execution_strategy(message),
            tool_names=("fetch_url", "python_repl", "read_file", "terminal"),
            is_knowledge_query=False,
            prefer_tool_agent=False,
        )

        self.assertIsNotNone(decision)
        self.assertEqual(decision.intent, "erp_approval")
        self.assertFalse(decision.needs_tools)
        self.assertTrue(decision.needs_retrieval)

    def test_deterministic_route_does_not_hijack_workspace_file_request(self) -> None:
        message = "请在 backend/ 里查找采购申请审批相关文件。"
        decision = deterministic_route(
            message=message,
            strategy=parse_execution_strategy(message),
            tool_names=("fetch_url", "python_repl", "read_file", "terminal"),
            is_knowledge_query=False,
            prefer_tool_agent=True,
        )

        self.assertIsNotNone(decision)
        self.assertEqual(decision.intent, "workspace_file_ops")
        self.assertEqual(decision.allowed_tools, ("terminal",))


if __name__ == "__main__":
    unittest.main()
