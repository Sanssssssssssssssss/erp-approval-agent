"use client";

import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  ClipboardCheck,
  FileSearch,
  ListChecks,
  ShieldCheck,
  ShieldX
} from "lucide-react";

import type { PendingHitlInterrupt } from "@/lib/api";

type Props = {
  pendingHitl: PendingHitlInterrupt;
  isStreaming: boolean;
  editedInputText: string;
  editError: string;
  onEditTextChange: (value: string) => void;
  onAccept: () => void;
  onReject: () => void;
  onEditSubmit: () => void;
  className?: string;
};

type EvidenceRequirementPreview = {
  requirementId: string;
  label: string;
  status: string;
  blocking: boolean;
};

type EvidenceArtifactPreview = {
  sourceId: string;
  title: string;
  recordType: string;
  links: string[];
  contentPreview: string;
};

type ControlCheckPreview = {
  checkId: string;
  label: string;
  status: string;
  severity: string;
  explanation: string;
};

type CaseEvidencePreview = {
  passed: boolean;
  completenessScore: string;
  blockingGaps: string[];
  nextQuestions: string[];
  requirements: EvidenceRequirementPreview[];
  artifacts: EvidenceArtifactPreview[];
  problemChecks: ControlCheckPreview[];
  controlPassed: boolean;
  highRisk: boolean;
  contradictionText: string;
  riskLevel: string;
};

type RecommendationPreview = {
  approvalId: string;
  approvalType: string;
  requester: string;
  department: string;
  amountLabel: string;
  vendor: string;
  costCenter: string;
  businessPurpose: string;
  statusKey: string;
  status: string;
  confidence: string;
  nextAction: string;
  summary: string;
  rationale: string[];
  missingInformation: string[];
  riskFlags: string[];
  citations: string[];
  guardWarnings: string[];
  contextSourceIds: string[];
  caseEvidence: CaseEvidencePreview | null;
};

const STATUS_LABELS: Record<string, string> = {
  recommend_approve: "建议通过（仅建议）",
  recommend_reject: "建议拒绝",
  request_more_info: "需要补充证据",
  escalate: "升级人工复核",
  blocked: "已阻断"
};

const NEXT_ACTION_LABELS: Record<string, string> = {
  none: "暂无后续动作草案",
  request_more_info: "补充材料后再审",
  route_to_manager: "建议经理复核",
  route_to_finance: "建议财务复核",
  route_to_procurement: "建议采购复核",
  route_to_legal: "建议法务复核",
  manual_review: "人工复核"
};

const APPROVAL_TYPE_LABELS: Record<string, string> = {
  expense: "费用报销",
  purchase_requisition: "采购申请",
  invoice_payment: "发票付款",
  supplier_onboarding: "供应商准入",
  contract_exception: "合同例外",
  budget_exception: "预算例外",
  unknown: "未知类型"
};

const REQUIREMENT_STATUS_LABELS: Record<string, string> = {
  satisfied: "已满足",
  missing: "缺失",
  partial: "部分",
  conflict: "冲突",
  not_applicable: "不适用",
  pass: "通过",
  fail: "失败"
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function text(value: unknown, fallback = "未提供") {
  const rendered = String(value ?? "").trim();
  return rendered || fallback;
}

function textArray(value: unknown) {
  return Array.isArray(value)
    ? value.map((item) => String(item ?? "").trim()).filter(Boolean)
    : [];
}

function recordArray(value: unknown) {
  return Array.isArray(value) ? value.map(asRecord) : [];
}

function normalizeApprovalReferences(value: string, approvalId: string) {
  const match = approvalId.match(/^([A-Za-z]+)-(\d{3,})$/);
  if (!match) return value;
  const [, prefix, digits] = match;
  const truncated = `${prefix}-${digits.slice(0, -1)}`;
  return value.replace(new RegExp(`\\b${truncated}\\b(?!\\d)`, "gi"), approvalId);
}

function friendlyWarning(value: string) {
  return value
    .replace("Unknown citation source_id values:", "模型引用了不属于当前上下文的 citation：")
    .replace("recommend_approve downgraded because citations are outside the current context bundle.", "由于 citation 不属于当前上下文，系统已把“建议通过”降级为人工复核。")
    .replace("recommend_approve downgraded because missing_information is present.", "由于仍有缺失信息，系统已把“建议通过”降级为补充信息。")
    .replace("recommend_approve downgraded because confidence is below 0.72.", "由于置信度低于阈值，系统已把“建议通过”降级为人工复核。");
}

function amountLabel(request: Record<string, unknown>) {
  const amount = request.amount;
  const currency = text(request.currency, "");
  if (typeof amount === "number") {
    return `${amount.toLocaleString()}${currency ? ` ${currency}` : ""}`;
  }
  if (typeof amount === "string" && amount.trim()) {
    return `${amount.trim()}${currency ? ` ${currency}` : ""}`;
  }
  return "未提供";
}

function cleanBusinessPurpose(value: unknown) {
  const rendered = text(value);
  const purposeMatch = rendered.match(/(?:用途是|用途|business purpose)\s*[:：]?\s*([^,，。；;]+)/i);
  if (purposeMatch?.[1]) {
    return purposeMatch[1].trim();
  }
  return rendered.length > 90 ? `${rendered.slice(0, 90)}...` : rendered;
}

function localizedStatus(value: unknown) {
  const key = String(value ?? "").trim();
  return STATUS_LABELS[key] ?? (key || "未知建议");
}

function localizedNextAction(value: unknown) {
  const key = String(value ?? "").trim();
  return NEXT_ACTION_LABELS[key] ?? (key || "未提供");
}

function localizedApprovalType(value: unknown) {
  const key = String(value ?? "").trim();
  return APPROVAL_TYPE_LABELS[key] ?? (key || "未知类型");
}

function localizedRequirementStatus(value: string) {
  return REQUIREMENT_STATUS_LABELS[value] ?? value;
}

function parseCaseEvidence(proposed: Record<string, unknown>): CaseEvidencePreview | null {
  const casePayload = asRecord(proposed.case_evidence_summary);
  if (!Object.keys(casePayload).length) return null;

  const sufficiency = asRecord(casePayload.evidence_sufficiency);
  const controlMatrix = asRecord(casePayload.control_matrix);
  const contradictions = asRecord(casePayload.contradictions);
  const riskAssessment = asRecord(casePayload.risk_assessment);
  const problemChecks = recordArray(controlMatrix.checks)
    .map((check) => ({
      checkId: text(check.check_id, "unknown_check"),
      label: text(check.label, "未命名控制项"),
      status: text(check.status, "missing"),
      severity: text(check.severity, "medium"),
      explanation: text(check.explanation, "")
    }))
    .filter((check) => !["pass", "not_applicable"].includes(check.status));

  return {
    passed: Boolean(sufficiency.passed),
    completenessScore: typeof sufficiency.completeness_score === "number"
      ? sufficiency.completeness_score.toFixed(2)
      : text(sufficiency.completeness_score, "0.00"),
    blockingGaps: textArray(sufficiency.blocking_gaps),
    nextQuestions: textArray(sufficiency.next_questions),
    requirements: recordArray(casePayload.required_evidence).map((item) => ({
      requirementId: text(item.requirement_id, "unknown_requirement"),
      label: text(item.label, "未命名证据"),
      status: text(item.status, "missing"),
      blocking: Boolean(item.blocking)
    })),
    artifacts: recordArray(casePayload.evidence_artifacts).map((item) => ({
      sourceId: text(item.source_id, "missing_source"),
      title: text(item.title, "未命名证据材料"),
      recordType: text(item.record_type, "unknown"),
      links: textArray(item.evidence_links),
      contentPreview: text(item.content_preview, "")
    })),
    problemChecks,
    controlPassed: Boolean(controlMatrix.passed),
    highRisk: Boolean(controlMatrix.high_risk),
    contradictionText: Boolean(contradictions.has_conflict)
      ? text(contradictions.explanation, "发现结构化证据冲突。")
      : "未发现明确结构化冲突",
    riskLevel: text(riskAssessment.risk_level, "medium")
  };
}

function parsePreview(pendingHitl: PendingHitlInterrupt): RecommendationPreview {
  const proposed = asRecord(pendingHitl.proposed_input);
  const request = asRecord(proposed.approval_request);
  const recommendation = asRecord(proposed.recommendation);
  const guard = asRecord(proposed.guard_result);
  const confidence = typeof recommendation.confidence === "number"
    ? recommendation.confidence.toFixed(2)
    : text(recommendation.confidence, "未提供");

  const approvalId = text(request.approval_id, "未识别");
  const normalize = (value: string) => normalizeApprovalReferences(value, approvalId);
  const statusKey = String(recommendation.status ?? "").trim();

  return {
    approvalId,
    approvalType: localizedApprovalType(request.approval_type),
    requester: text(request.requester),
    department: text(request.department),
    amountLabel: amountLabel(request),
    vendor: text(request.vendor),
    costCenter: text(request.cost_center),
    businessPurpose: cleanBusinessPurpose(request.business_purpose),
    statusKey,
    status: localizedStatus(recommendation.status),
    confidence,
    nextAction: localizedNextAction(recommendation.proposed_next_action),
    summary: normalize(text(recommendation.summary, "Agent 没有返回摘要，建议查看结构化 JSON。")),
    rationale: textArray(recommendation.rationale).map(normalize),
    missingInformation: textArray(recommendation.missing_information).map(normalize),
    riskFlags: textArray(recommendation.risk_flags).map(normalize),
    citations: textArray(recommendation.citations),
    guardWarnings: textArray(guard.warnings).map(friendlyWarning),
    contextSourceIds: textArray(proposed.context_source_ids),
    caseEvidence: parseCaseEvidence(proposed)
  };
}

function PreviewList({ empty, items, limit = 5 }: { empty: string; items: string[]; limit?: number }) {
  const visible = items.slice(0, limit);
  if (!visible.length) {
    return <p className="mt-2 text-sm leading-6 text-[var(--color-ink-soft)]">{empty}</p>;
  }
  return (
    <ul className="mt-2 space-y-2 text-sm leading-6 text-[var(--color-ink)]">
      {visible.map((item, index) => (
        <li className="flex gap-2" key={`${item}-${index}`}>
          <span className="mt-[0.65rem] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-accent-strong)]" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

function RequirementPill({ item }: { item: EvidenceRequirementPreview }) {
  const problem = item.blocking && !["satisfied", "not_applicable"].includes(item.status);
  return (
    <span className={problem ? "approval-pill approval-pill-warning" : "approval-pill"}>
      {item.blocking ? "阻断" : "参考"} · {localizedRequirementStatus(item.status)} · {item.label}
    </span>
  );
}

function EvidenceCaseSection({ preview }: { preview: RecommendationPreview }) {
  const evidence = preview.caseEvidence;
  if (!evidence) {
    return (
      <section className="approval-review-section">
        <p className="pixel-label flex items-center gap-2">
          <FileSearch size={15} /> 证据案件
        </p>
        <p className="mt-2 text-sm leading-6 text-[var(--color-ink-soft)]">
          当前 HITL payload 没有携带 evidence case 摘要。请查看完整回答或高级 JSON。
        </p>
      </section>
    );
  }

  const visibleRequirements = evidence.requirements.slice(0, 14);
  const visibleArtifacts = evidence.artifacts.slice(0, 8);
  const visibleChecks = evidence.problemChecks.slice(0, 8);

  return (
    <section className="approval-review-section">
      <div className="grid gap-3 lg:grid-cols-4">
        <div className={evidence.passed ? "approval-kpi approval-kpi-ok" : "approval-kpi approval-kpi-warn"}>
          <p className="pixel-label">证据充分性</p>
          <strong>{evidence.passed ? "已通过" : "证据不足"}</strong>
          <span>完整度 {evidence.completenessScore}</span>
        </div>
        <div className={evidence.controlPassed ? "approval-kpi approval-kpi-ok" : "approval-kpi approval-kpi-warn"}>
          <p className="pixel-label">控制矩阵</p>
          <strong>{evidence.controlPassed ? "已通过" : "存在缺口"}</strong>
          <span>{evidence.problemChecks.length} 个待处理控制项</span>
        </div>
        <div className={evidence.highRisk ? "approval-kpi approval-kpi-danger" : "approval-kpi"}>
          <p className="pixel-label">风险等级</p>
          <strong>{evidence.riskLevel}</strong>
          <span>{evidence.highRisk ? "需要重点复核" : "按证据继续审查"}</span>
        </div>
        <div className="approval-kpi">
          <p className="pixel-label">冲突检测</p>
          <strong>{evidence.contradictionText.includes("未发现") ? "未发现冲突" : "存在冲突"}</strong>
          <span>{evidence.contradictionText}</span>
        </div>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <div>
          <p className="pixel-label flex items-center gap-2">
            <ListChecks size={15} /> 必需证据清单
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {visibleRequirements.length ? (
              visibleRequirements.map((item) => (
                <RequirementPill item={item} key={item.requirementId} />
              ))
            ) : (
              <span className="text-sm text-[var(--color-ink-soft)]">没有可展示的证据要求。</span>
            )}
          </div>
        </div>

        <div>
          <p className="pixel-label flex items-center gap-2">
            <AlertTriangle size={15} /> 阻断缺口
          </p>
          <PreviewList empty="没有阻断缺口。" items={evidence.blockingGaps} limit={5} />
        </div>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <div>
          <p className="pixel-label flex items-center gap-2">
            <FileSearch size={15} /> 证据材料
          </p>
          <div className="mt-3 space-y-2">
            {visibleArtifacts.length ? (
              visibleArtifacts.map((artifact) => (
                <div className="approval-artifact" key={artifact.sourceId}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <strong>{artifact.title}</strong>
                    <span>{artifact.recordType}</span>
                  </div>
                  <code>{artifact.sourceId}</code>
                  {artifact.links.length ? (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {artifact.links.slice(0, 3).map((link) => (
                        <span className="approval-link-chip" key={link}>{link}</span>
                      ))}
                    </div>
                  ) : null}
                </div>
              ))
            ) : (
              <p className="text-sm leading-6 text-[var(--color-ink-soft)]">没有可展示的 ERP、政策、附件或 mock document 证据。</p>
            )}
          </div>
        </div>

        <div>
          <p className="pixel-label flex items-center gap-2">
            <ClipboardCheck size={15} /> 未通过控制项
          </p>
          <div className="mt-3 space-y-2">
            {visibleChecks.length ? (
              visibleChecks.map((check) => (
                <div className="approval-control-row" key={check.checkId}>
                  <div className="flex flex-wrap items-center gap-2">
                    <strong>{check.label}</strong>
                    <span>{localizedRequirementStatus(check.status)} / {check.severity}</span>
                  </div>
                  <p>{check.explanation || "需要人工复核该控制项。"}</p>
                </div>
              ))
            ) : (
              <p className="text-sm leading-6 text-[var(--color-ink-soft)]">没有失败、缺失或冲突的控制项。</p>
            )}
          </div>
        </div>
      </div>

      {evidence.nextQuestions.length ? (
        <div className="mt-4">
          <p className="pixel-label">建议补证问题</p>
          <PreviewList empty="没有补证问题。" items={evidence.nextQuestions} limit={5} />
        </div>
      ) : null}
    </section>
  );
}

export function HitlRecommendationReviewCard({
  pendingHitl,
  isStreaming,
  editedInputText,
  editError,
  onEditTextChange,
  onAccept,
  onReject,
  onEditSubmit,
  className = ""
}: Props) {
  const preview = parsePreview(pendingHitl);
  const isApproveLike = preview.statusKey === "recommend_approve";

  return (
    <div className={`approval-review-card mb-4 max-h-[72vh] min-h-0 shrink-0 overflow-y-auto px-4 py-4 ${className}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="pixel-label">需要人工复核 Agent 建议（不会执行 ERP）</p>
          <h3 className="pixel-title mt-2 text-[1.16rem] text-[var(--color-ink)]">
            这是“是否采用本地建议”的复核，不是 ERP 单据审批
          </h3>
        </div>
        <div className="flex flex-wrap gap-2">
          <span className="pixel-tag">风险 {pendingHitl.risk_level || "未标记"}</span>
          <span className="pixel-tag">checkpoint {pendingHitl.checkpoint_id.slice(0, 8)}</span>
        </div>
      </div>

      <section className={isApproveLike ? "approval-decision approval-decision-ok" : "approval-decision approval-decision-warn"}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="pixel-label">Agent 当前建议</p>
            <h4 className="pixel-title mt-2 text-[1.5rem] text-[var(--color-ink)]">
              {preview.status}
            </h4>
          </div>
          <div className="flex flex-wrap gap-2">
            <span className="pixel-tag">置信度 {preview.confidence}</span>
            <span className="pixel-tag">下一步：{preview.nextAction}</span>
          </div>
        </div>
        <p className="mt-3 text-[1rem] leading-7 text-[var(--color-ink)]">{preview.summary}</p>
        <p className="mt-3 flex items-start gap-2 text-sm leading-6 text-[var(--color-ink-soft)]">
          {isApproveLike ? (
            <ShieldCheck className="mt-1 h-4 w-4 shrink-0 text-[var(--color-success)]" />
          ) : (
            <ShieldX className="mt-1 h-4 w-4 shrink-0 text-[var(--color-warning)]" />
          )}
          <span>点击“采用建议”只会接受这份本地建议回执；不会通过、驳回、付款、发送消息、路由或更新任何 ERP 对象。</span>
        </p>
      </section>

      <section className="mt-4 grid gap-3 md:grid-cols-4">
        {[
          ["审批单", `${preview.approvalType} / ${preview.approvalId}`],
          ["申请部门", preview.department],
          ["金额", preview.amountLabel],
          ["供应商", preview.vendor],
          ["申请人", preview.requester],
          ["成本中心", preview.costCenter],
          ["用途", preview.businessPurpose],
          ["边界", "只复核建议，不执行 ERP"]
        ].map(([label, value]) => (
          <div className="approval-fact" key={label}>
            <p className="pixel-label">{label}</p>
            <p>{value}</p>
          </div>
        ))}
      </section>

      <EvidenceCaseSection preview={preview} />

      <section className="mt-4 grid gap-4 xl:grid-cols-3">
        <div className="approval-review-section">
          <p className="pixel-label">推理依据</p>
          <PreviewList empty="暂无推理依据。" items={preview.rationale} limit={3} />
        </div>
        <div className="approval-review-section approval-review-section-warning">
          <p className="pixel-label">需要补充的信息</p>
          <PreviewList empty="Agent 没有列出缺失信息。" items={preview.missingInformation} />
        </div>
        <div className="approval-review-section approval-review-section-danger">
          <p className="pixel-label">风险点</p>
          <PreviewList empty="Agent 没有列出风险点。" items={preview.riskFlags} />
        </div>
      </section>

      {preview.guardWarnings.length ? (
        <section className="approval-review-section approval-review-section-warning mt-4">
          <p className="pixel-label">系统 guard 提醒</p>
          <PreviewList empty="暂无 guard 提醒。" items={preview.guardWarnings} />
        </section>
      ) : null}

      <section className="approval-review-section mt-4">
        <p className="pixel-label">模型 citation / 上下文来源</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {(preview.citations.length ? preview.citations : preview.contextSourceIds).slice(0, 10).map((sourceId) => (
            <span className="pixel-tag break-all" key={sourceId}>
              {sourceId}
            </span>
          ))}
          {!preview.citations.length && !preview.contextSourceIds.length ? (
            <span className="text-sm text-[var(--color-ink-soft)]">暂无可展示证据来源。</span>
          ) : null}
        </div>
      </section>

      <div className="mt-4 flex flex-wrap gap-3">
        <button className="ui-button ui-button-primary" disabled={isStreaming} onClick={onAccept} type="button">
          <CheckCircle2 size={16} />
          {isStreaming ? "正在生成复核回执..." : "采用建议并继续（不执行 ERP）"}
        </button>
        <button className="ui-button ui-button-danger" disabled={isStreaming} onClick={onReject} type="button">
          <Ban size={16} />
          {isStreaming ? "正在拒绝..." : "拒绝这条建议"}
        </button>
      </div>

      <details className="hitl-payload-details mt-4">
        <summary>高级：查看或编辑结构化建议 JSON</summary>
        <p className="pixel-note mt-3">这里编辑的是 Agent 建议 payload，不是 ERP 单据，也不会触发 ERP 写入。</p>
        <pre>{JSON.stringify(pendingHitl.proposed_input ?? {}, null, 2)}</pre>
        <label className="pixel-label mt-4 block">编辑 JSON 后继续（可选）</label>
        <textarea
          className="mt-2 min-h-[150px] w-full rounded-[8px] border border-[var(--color-line)] bg-[var(--color-bg)] px-3 py-3 font-mono text-sm text-[var(--color-ink)] outline-none"
          onChange={(event) => onEditTextChange(event.target.value)}
          value={editedInputText}
        />
        {editError ? <p className="mt-2 text-sm text-[var(--color-danger)]">{editError}</p> : null}
        <button className="ui-button mt-3" disabled={isStreaming} onClick={onEditSubmit} type="button">
          {isStreaming ? "正在提交编辑..." : "保存 JSON 编辑并继续"}
        </button>
      </details>
    </div>
  );
}
