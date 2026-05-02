from __future__ import annotations

from typing import Any

from src.backend.domains.erp_approval.case_models import EvidenceRequirement


def _requirement(
    approval_type: str,
    key: str,
    label: str,
    description: str,
    *,
    record_types: list[str] | None = None,
    artifact_types: list[str] | None = None,
    policy_refs: list[str] | None = None,
    required_level: str = "required",
    blocking: bool = True,
) -> EvidenceRequirement:
    return EvidenceRequirement(
        requirement_id=f"{approval_type}:{key}",
        approval_type=approval_type,
        label=label,
        description=description,
        required_level=required_level,  # type: ignore[arg-type]
        blocking=blocking,
        expected_record_types=record_types or [],
        expected_artifact_types=artifact_types or [],
        policy_refs=policy_refs or [],
    )


def requirement_matrix_for_approval_type(approval_type: str, amount: float | None = None) -> list[EvidenceRequirement]:
    approval_type = str(approval_type or "unknown")
    common = [
        _requirement(approval_type, "approval_request", "审批请求记录", "必须有可追溯的 ERP 审批请求或等价案件记录。", record_types=["approval_request"]),
        _requirement(approval_type, "policy", "政策依据", "必须有适用政策或控制依据。", record_types=["policy"], policy_refs=["policy"]),
        _requirement(approval_type, "approval_matrix", "审批矩阵", "必须能判断审批路径和必要复核角色。", record_types=["policy"], policy_refs=["approval_matrix"]),
    ]
    if approval_type == "purchase_requisition":
        return common + [
            _requirement(approval_type, "line_items", "采购明细", "需要物料、数量、单价或等价明细；一句话用途不能替代明细。", artifact_types=["attachment", "mock_document"]),
            _requirement(approval_type, "budget_availability", "预算可用性", "需要预算余额或预算占用证明。", record_types=["budget"], policy_refs=["budget_policy"]),
            _requirement(approval_type, "vendor_onboarding_status", "供应商准入状态", "需要供应商主数据或准入状态。", record_types=["vendor"]),
            _requirement(approval_type, "supplier_risk_status", "供应商风险状态", "需要制裁、风险或准入阻断检查。", record_types=["vendor"]),
            _requirement(approval_type, "quote_or_price_basis", "报价或价格依据", "需要报价、框架价或价格合理性依据。", artifact_types=["attachment", "mock_document"]),
            _requirement(approval_type, "contract_or_framework_agreement", "合同或框架协议", "需要合同、框架协议或说明为何不适用。", record_types=["contract"], required_level="conditional"),
            _requirement(approval_type, "procurement_policy", "采购政策", "需要采购政策依据。", record_types=["policy"], policy_refs=["procurement_policy"]),
            _requirement(approval_type, "cost_center", "成本中心", "需要成本中心归属。", record_types=["approval_request", "budget"]),
            _requirement(approval_type, "requester_identity", "申请人身份", "需要申请人身份和部门归属。", record_types=["approval_request"]),
            _requirement(approval_type, "amount_threshold", "金额阈值", "需要金额和阈值/审批路径判断。", record_types=["approval_request", "policy"]),
            _requirement(approval_type, "split_order_check", "拆单检查", "需要排除拆单规避审批阈值的证据。", artifact_types=["erp_record", "mock_document"]),
        ]
    if approval_type == "expense":
        return common + [
            _requirement(approval_type, "expense_claim", "报销申请", "需要报销申请记录。", record_types=["approval_request"]),
            _requirement(approval_type, "receipt_or_invoice", "收据或发票", "需要收据、发票或附件证明。", artifact_types=["attachment", "mock_document"]),
            _requirement(approval_type, "expense_policy", "费用政策", "需要费用报销政策。", record_types=["policy"], policy_refs=["expense_policy"]),
            _requirement(approval_type, "business_purpose", "业务目的", "需要明确业务目的。", record_types=["approval_request"]),
            _requirement(approval_type, "expense_date", "费用日期", "需要费用发生日期或期间。", artifact_types=["attachment", "mock_document"]),
            _requirement(approval_type, "cost_center", "成本中心", "需要成本中心。", record_types=["approval_request"]),
            _requirement(approval_type, "duplicate_expense_check", "重复报销检查", "需要重复报销检查证据。", artifact_types=["erp_record", "mock_document"]),
            _requirement(approval_type, "manager_approval_path", "经理审批路径", "需要经理审批路径。", record_types=["policy"]),
            _requirement(approval_type, "amount_limit_check", "金额限额检查", "需要金额限额和政策匹配。", record_types=["approval_request", "policy"]),
        ]
    if approval_type == "invoice_payment":
        return common + [
            _requirement(approval_type, "invoice", "发票", "需要发票记录。", record_types=["invoice"]),
            _requirement(approval_type, "purchase_order", "采购订单", "需要 PO 记录。", record_types=["purchase_order"]),
            _requirement(approval_type, "goods_receipt", "收货记录", "需要 GRN/收货记录。", record_types=["goods_receipt"]),
            _requirement(approval_type, "vendor_record", "供应商记录", "需要供应商主数据。", record_types=["vendor"]),
            _requirement(approval_type, "contract_or_payment_terms", "合同或付款条款", "需要合同或付款条款。", record_types=["contract"], required_level="conditional"),
            _requirement(approval_type, "three_way_match", "三单匹配", "需要 PO/GRN/Invoice 三单匹配证据。", record_types=["purchase_order", "goods_receipt", "invoice"]),
            _requirement(approval_type, "duplicate_payment_check", "重复付款检查", "需要重复付款排查。", artifact_types=["erp_record", "mock_document"]),
            _requirement(approval_type, "invoice_payment_policy", "发票付款政策", "需要付款政策。", record_types=["policy"], policy_refs=["invoice_payment_policy"]),
        ]
    if approval_type == "supplier_onboarding":
        return common + [
            _requirement(approval_type, "vendor_profile", "供应商档案", "需要供应商档案。", record_types=["vendor", "approval_request"]),
            _requirement(approval_type, "tax_info", "税务信息", "需要税务信息。", record_types=["vendor"], artifact_types=["attachment"]),
            _requirement(approval_type, "bank_info", "银行信息", "需要银行账户信息。", record_types=["vendor"], artifact_types=["attachment"]),
            _requirement(approval_type, "sanctions_check", "制裁检查", "需要制裁筛查结果。", record_types=["vendor"], artifact_types=["mock_document"]),
            _requirement(approval_type, "beneficial_owner_check", "受益所有人检查", "需要所有权/受益人尽调。", artifact_types=["mock_document"]),
            _requirement(approval_type, "procurement_due_diligence", "采购尽调", "需要采购尽调记录。", artifact_types=["mock_document"]),
            _requirement(approval_type, "contract_or_nda_or_dpa", "合同/NDA/DPA", "需要合同、NDA 或 DPA 等文件。", record_types=["contract"], required_level="conditional"),
            _requirement(approval_type, "supplier_onboarding_policy", "供应商准入政策", "需要准入政策。", record_types=["policy"], policy_refs=["supplier_onboarding_policy"]),
        ]
    if approval_type == "contract_exception":
        return common + [
            _requirement(approval_type, "contract_text", "合同文本", "需要合同文本。", record_types=["contract"]),
            _requirement(approval_type, "redline_or_exception_clause", "红线或例外条款", "需要例外条款或 redline。", record_types=["contract"], artifact_types=["attachment"]),
            _requirement(approval_type, "standard_terms", "标准条款", "需要标准条款作为对照。", artifact_types=["policy_record", "mock_document"], record_types=["policy"]),
            _requirement(approval_type, "legal_policy", "法务政策", "需要法务/合同政策。", record_types=["policy"], policy_refs=["legal_policy"]),
            _requirement(approval_type, "liability_clause", "责任条款", "需要责任上限条款。", record_types=["contract"]),
            _requirement(approval_type, "payment_terms", "付款条款", "需要付款条款影响分析。", record_types=["contract"], required_level="conditional"),
            _requirement(approval_type, "termination_clause", "终止条款", "需要终止条款影响分析。", record_types=["contract"]),
            _requirement(approval_type, "legal_review_required", "法务复核要求", "合同例外必须法务复核。", record_types=["policy", "contract"]),
        ]
    if approval_type == "budget_exception":
        return common + [
            _requirement(approval_type, "budget_record", "预算记录", "需要预算记录。", record_types=["budget"]),
            _requirement(approval_type, "budget_owner", "预算负责人", "需要预算负责人。", artifact_types=["erp_record", "mock_document"]),
            _requirement(approval_type, "available_budget", "可用预算", "需要可用预算或资金不足证明。", record_types=["budget"]),
            _requirement(approval_type, "exception_reason", "例外原因", "需要预算例外理由。", record_types=["approval_request"]),
            _requirement(approval_type, "finance_policy", "财务政策", "需要财务/预算政策。", record_types=["policy"], policy_refs=["budget_policy"]),
            _requirement(approval_type, "finance_approval_matrix", "财务审批矩阵", "需要财务审批路径。", record_types=["policy"], policy_refs=["approval_matrix"]),
        ]
    return [
        _requirement("unknown", "approval_request", "审批请求记录", "未知审批类型至少需要审批请求记录。", record_types=["approval_request"]),
        _requirement("unknown", "policy", "政策依据", "未知审批类型至少需要政策依据。", record_types=["policy"]),
        _requirement("unknown", "approval_matrix", "审批矩阵", "未知审批类型至少需要审批矩阵。", record_types=["policy"], policy_refs=["approval_matrix"]),
        _requirement("unknown", "manual_review", "人工复核", "未知审批类型必须人工复核。", artifact_types=["user_statement"]),
    ]


def build_evidence_requirements(case_file_or_request: Any) -> list[EvidenceRequirement]:
    approval_type = str(getattr(case_file_or_request, "approval_type", "") or "unknown")
    amount = getattr(case_file_or_request, "amount", None)
    if isinstance(case_file_or_request, dict):
        approval_type = str(case_file_or_request.get("approval_type", "") or "unknown")
        amount = case_file_or_request.get("amount")
    try:
        normalized_amount = float(amount) if amount is not None else None
    except (TypeError, ValueError):
        normalized_amount = None
    return requirement_matrix_for_approval_type(approval_type, normalized_amount)
