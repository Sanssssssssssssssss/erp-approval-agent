from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.decision.execution_strategy import ExecutionStrategy
from src.backend.decision.lightweight_router import RoutingDecision
from src.backend.orchestration.edges import branch_after_memory


class ErpApprovalEdgesTests(unittest.TestCase):
    def test_branch_after_memory_routes_erp_approval_to_intake(self) -> None:
        decision = RoutingDecision(
            intent="erp_approval",
            needs_tools=False,
            needs_retrieval=True,
            allowed_tools=(),
            confidence=0.9,
            reason_short="ERP approval request",
            source="rules",
        )

        branch = branch_after_memory(
            {
                "route_decision": decision,
                "execution_strategy": ExecutionStrategy(),
            }
        )

        self.assertEqual(branch, "erp_intake")


if __name__ == "__main__":
    unittest.main()
