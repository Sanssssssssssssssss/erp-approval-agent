from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.decision.execution_strategy import parse_execution_strategy
from src.backend.decision.lightweight_router import RoutingDecision, deterministic_route
from src.backend.runtime.agent_manager import AgentManager


class ErpApprovalRoutingTests(unittest.TestCase):
    def test_deterministic_route_detects_chinese_procurement_approval(self) -> None:
        message = "\u8bf7\u5e2e\u6211\u5ba1\u6838\u8fd9\u4e2a\u91c7\u8d2d\u7533\u8bf7\u5ba1\u6279\uff0c\u91d1\u989d5000\u5143\uff0c\u4f9b\u5e94\u5546\u662fAcme\u3002"
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
        message = "\u8bf7\u5728 backend/ \u91cc\u67e5\u627e\u91c7\u8d2d\u7533\u8bf7\u5ba1\u6279\u76f8\u5173\u6587\u4ef6\u3002"
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

    def test_deterministic_route_respects_no_retrieval_constraint(self) -> None:
        message = "\u8bf7\u5ba1\u6838\u91c7\u8d2d\u7533\u8bf7\uff0c\u4f46\u4e0d\u8981\u68c0\u7d22\u3002"
        decision = deterministic_route(
            message=message,
            strategy=parse_execution_strategy(message),
            tool_names=("fetch_url", "python_repl", "read_file", "terminal"),
            is_knowledge_query=False,
            prefer_tool_agent=False,
        )

        self.assertIsNone(decision)

    def test_deterministic_route_respects_no_knowledge_constraint(self) -> None:
        message = "\u8bf7\u5ba1\u6838\u91c7\u8d2d\u7533\u8bf7\uff0c\u4f46\u4e0d\u8981\u4f7f\u7528\u77e5\u8bc6\u5e93\u3002"
        decision = deterministic_route(
            message=message,
            strategy=parse_execution_strategy(message),
            tool_names=("fetch_url", "python_repl", "read_file", "terminal"),
            is_knowledge_query=False,
            prefer_tool_agent=False,
        )

        self.assertIsNone(decision)

    def test_agent_manager_constraints_downgrade_erp_when_retrieval_disallowed(self) -> None:
        manager = AgentManager()
        decision = RoutingDecision(
            intent="erp_approval",
            needs_tools=False,
            needs_retrieval=True,
            allowed_tools=(),
            confidence=0.9,
            reason_short="llm chose erp approval",
            source="llm_router",
        )

        constrained = manager._apply_routing_constraints(
            decision,
            parse_execution_strategy("\u8bf7\u5ba1\u6838\u91c7\u8d2d\u7533\u8bf7\uff0c\u4f46\u4e0d\u8981\u68c0\u7d22\u3002"),
        )

        self.assertEqual(constrained.intent, "direct_answer")
        self.assertFalse(constrained.needs_retrieval)


if __name__ == "__main__":
    unittest.main()
