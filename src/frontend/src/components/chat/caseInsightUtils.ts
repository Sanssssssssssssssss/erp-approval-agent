export function text(value: unknown, fallback = "未提供") {
  const rendered = String(value ?? "").trim();
  return rendered || fallback;
}

export function list(value: unknown) {
  return Array.isArray(value) ? value.map((item) => String(item ?? "").trim()).filter(Boolean) : [];
}

export function records(value: unknown) {
  return Array.isArray(value) ? (value.filter((item) => item && typeof item === "object") as Array<Record<string, unknown>>) : [];
}

export function object(value: unknown) {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

export function boolLabel(value: unknown) {
  return value ? "是" : "否";
}

export function displayLabel(value: unknown, fallback = "未提供") {
  const labels: Record<string, string> = {
    ask_how_to_prepare: "询问材料准备",
    ask_missing_requirements: "询问当前缺口",
    ask_policy_failure: "询问退回原因",
    submit_evidence: "提交材料",
    request_final_review: "请求生成 memo",
    correct_previous_evidence: "打回后重审",
    withdraw_evidence: "撤回材料",
    off_topic: "与案件无关",
    create_case: "创建案卷",
    accept_evidence: "接受材料",
    reject_evidence: "退回材料",
    answer_status: "状态回复",
    final_memo: "最终 memo",
    no_case_change: "不改案卷",
    read_only_case_turn: "只读回复",
    persistent_case_turn: "写入本地案卷",
    collecting_evidence: "收集材料中",
    ready_for_final_review: "可生成 memo",
    final_memo_ready: "memo 已就绪",
    escalation_review: "需要人工升级复核",
    blocked: "已阻断",
    draft: "草稿"
  };
  const key = text(value, fallback);
  return labels[key] ?? key.replace(/_/g, " ");
}

export function policyRagTraceFromModelReview(modelReview: Record<string, unknown>) {
  const candidates = [
    object(modelReview.policy_rag),
    object(object(modelReview.missing_requirements_answer).policy_rag),
    object(object(modelReview.policy_failures_answer).policy_rag)
  ];
  return candidates.find((candidate) => Object.keys(candidate).length > 0) ?? {};
}

export function policyRagPlan(trace: Record<string, unknown>) {
  return object(trace.query_plan);
}

export function policyRagEvidences(trace: Record<string, unknown>) {
  return records(trace.evidences);
}
