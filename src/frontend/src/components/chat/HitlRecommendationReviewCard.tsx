"use client";

import { AlertTriangle, Ban, CheckCircle2, FilePenLine, ShieldCheck } from "lucide-react";

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

type RecommendationPreview = {
  approvalId: string;
  approvalType: string;
  requester: string;
  department: string;
  amountLabel: string;
  vendor: string;
  costCenter: string;
  businessPurpose: string;
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
};

const STATUS_LABELS: Record<string, string> = {
  recommend_approve: "建议通过",
  recommend_reject: "建议拒绝",
  request_more_info: "需要补充信息",
  escalate: "升级人工复核",
  blocked: "已阻断"
};

const NEXT_ACTION_LABELS: Record<string, string> = {
  none: "暂无后续动作草案",
  request_more_info: "请求补充信息",
  route_to_manager: "转交经理复核",
  route_to_finance: "转交财务复核",
  route_to_procurement: "转交采购复核",
  route_to_legal: "转交法务复核",
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
    .replace("recommend_approve downgraded because citations are outside the current context bundle.", "由于 citation 不属于当前上下文，系统已把“建议通过”降级为需要人工复核。")
    .replace("recommend_approve downgraded because missing_information is not empty.", "由于仍有缺失信息，系统已把“建议通过”降级为补充信息。")
    .replace("recommend_approve downgraded because confidence is below threshold.", "由于置信度低于阈值，系统已把“建议通过”降级为人工复核。");
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

  return {
    approvalId,
    approvalType: localizedApprovalType(request.approval_type),
    requester: text(request.requester),
    department: text(request.department),
    amountLabel: amountLabel(request),
    vendor: text(request.vendor),
    costCenter: text(request.cost_center),
    businessPurpose: cleanBusinessPurpose(request.business_purpose),
    status: localizedStatus(recommendation.status),
    confidence,
    nextAction: localizedNextAction(recommendation.proposed_next_action),
    summary: normalize(text(recommendation.summary, "Agent 没有返回摘要，建议查看高级 JSON。")),
    rationale: textArray(recommendation.rationale).map(normalize),
    missingInformation: textArray(recommendation.missing_information).map(normalize),
    riskFlags: textArray(recommendation.risk_flags).map(normalize),
    citations: textArray(recommendation.citations),
    guardWarnings: textArray(guard.warnings).map(friendlyWarning),
    contextSourceIds: textArray(proposed.context_source_ids)
  };
}

function PreviewList({ empty, items, limit = 4 }: { empty: string; items: string[]; limit?: number }) {
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

  return (
    <div className={`pixel-card-soft mb-4 max-h-[58vh] min-h-0 shrink-0 overflow-y-auto px-4 py-4 ${className}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="pixel-label">需要人工复核 ERP 建议（不会执行 ERP）</p>
          <h3 className="pixel-title mt-2 text-[1.08rem] text-[var(--color-ink)]">
            先看清建议，再决定是否采用
          </h3>
        </div>
        <div className="flex flex-wrap gap-2">
          <span className="pixel-tag">风险 {pendingHitl.risk_level || "未标记"}</span>
          <span className="pixel-tag">checkpoint {pendingHitl.checkpoint_id.slice(0, 8)}</span>
        </div>
      </div>

      <section className="mt-4 rounded-[8px] border border-[var(--color-accent-line)] bg-[rgba(47,129,247,0.08)] p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold text-[var(--color-ink-soft)]">Agent 当前建议</p>
            <h4 className="pixel-title mt-2 text-[1.35rem] text-[var(--color-ink)]">
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
          <ShieldCheck className="mt-1 h-4 w-4 shrink-0 text-[var(--color-success)]" />
          <span>点击“采用建议”只代表接受这份本地建议回执，不代表 ERP 通过、驳回、付款或路由。</span>
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
          ["安全边界", "只复核建议，不执行 ERP"]
        ].map(([label, value]) => (
          <div className="rounded-[8px] border border-[var(--color-line)] bg-[rgba(15,19,24,0.36)] p-3" key={label}>
            <p className="pixel-label">{label}</p>
            <p className="mt-2 break-words text-sm leading-6 text-[var(--color-ink)]">{value}</p>
          </div>
        ))}
      </section>

      <section className="mt-4 grid gap-4 xl:grid-cols-3">
        <div className="rounded-[8px] border border-[var(--color-line)] bg-[rgba(15,19,24,0.28)] p-4">
          <p className="pixel-label flex items-center gap-2">
            <FilePenLine size={15} /> 推理依据
          </p>
          <PreviewList empty="暂无推理依据。" items={preview.rationale} limit={3} />
        </div>
        <div className="rounded-[8px] border border-[var(--color-warning)]/40 bg-[rgba(246,182,85,0.07)] p-4">
          <p className="pixel-label flex items-center gap-2">
            <AlertTriangle size={15} /> 需要补充的信息
          </p>
          <PreviewList empty="Agent 没有列出缺失信息。" items={preview.missingInformation} />
        </div>
        <div className="rounded-[8px] border border-[var(--color-danger)]/40 bg-[rgba(255,107,107,0.07)] p-4">
          <p className="pixel-label flex items-center gap-2">
            <AlertTriangle size={15} /> 风险点
          </p>
          <PreviewList empty="Agent 没有列出风险点。" items={preview.riskFlags} />
        </div>
      </section>

      {preview.guardWarnings.length ? (
        <section className="mt-4 rounded-[8px] border border-[var(--color-warning)]/40 bg-[rgba(246,182,85,0.07)] p-4">
          <p className="pixel-label">系统 guard 提醒</p>
          <PreviewList empty="暂无 guard 提醒。" items={preview.guardWarnings} />
        </section>
      ) : null}

      <section className="mt-4 rounded-[8px] border border-[var(--color-line)] bg-[rgba(15,19,24,0.28)] p-4">
        <p className="pixel-label">证据来源</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {(preview.citations.length ? preview.citations : preview.contextSourceIds).slice(0, 8).map((sourceId) => (
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
          {isStreaming ? "正在生成复核回执..." : "采用这条建议并继续"}
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
