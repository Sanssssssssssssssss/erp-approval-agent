from __future__ import annotations

from src.backend.domains.erp_approval.context_adapter import ErpContextQuery, MockErpContextAdapter
from src.backend.domains.erp_approval.schemas import ApprovalContextBundle, ApprovalRequest


def build_mock_context(request: ApprovalRequest) -> ApprovalContextBundle:
    return MockErpContextAdapter().fetch_context(ErpContextQuery.from_request(request))
