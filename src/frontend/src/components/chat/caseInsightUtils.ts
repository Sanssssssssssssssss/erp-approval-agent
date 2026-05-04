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
  return text(value, fallback).replace(/_/g, " ");
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
  const retrieval = object(trace.retrieval);
  return object(trace.plan || retrieval.plan);
}

export function policyRagEvidences(trace: Record<string, unknown>) {
  const retrieval = object(trace.retrieval);
  const direct = records(trace.evidences);
  return direct.length ? direct : records(retrieval.evidences);
}
