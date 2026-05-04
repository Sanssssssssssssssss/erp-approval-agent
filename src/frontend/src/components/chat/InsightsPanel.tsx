"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiConnectionError,
  appendSavedErpApprovalAuditPackageNote,
  exportErpApprovalTracesCsv,
  exportErpApprovalTracesJson,
  exportSavedErpApprovalAuditPackage,
  getErpApprovalAnalyticsSummary,
  getErpApprovalAuditPackage,
  getErpApprovalTrace,
  getErpApprovalTrendSummary,
  getSavedErpApprovalAuditPackage,
  listSavedErpApprovalAuditPackageNotes,
  listSavedErpApprovalAuditPackages,
  listErpApprovalTraceProposals,
  listErpApprovalTraces,
  runErpApprovalActionSimulation,
  saveErpApprovalAuditPackage
} from "@/lib/api";
import type {
  ErpApprovalReviewerNote,
  ErpApprovalActionProposalRecord,
  ErpApprovalActionSimulationRecord,
  ErpApprovalAnalyticsSummary,
  ErpApprovalTraceQuery,
  ErpApprovalTraceRecord,
  ErpApprovalTrendSummary,
  SavedErpApprovalAuditPackageManifest
} from "@/lib/api";
import { ConnectorDiagnosticsPanel } from "@/components/chat/ConnectorDiagnosticsPanel";
import { LlmContextLibraryPanel } from "@/components/chat/LlmContextLibraryPanel";

type TraceFilters = {
  approval_type: string;
  recommendation_status: string;
  review_status: string;
  text_query: string;
  high_risk_only: boolean;
};

const DEFAULT_FILTERS: TraceFilters = {
  approval_type: "",
  recommendation_status: "",
  review_status: "",
  text_query: "",
  high_risk_only: false
};

const APPROVAL_TYPES = [
  "purchase_requisition",
  "expense",
  "invoice_payment",
  "supplier_onboarding",
  "contract_exception",
  "budget_exception",
  "unknown"
];

const RECOMMENDATION_STATUSES = [
  "recommend_approve",
  "recommend_reject",
  "request_more_info",
  "escalate",
  "blocked"
];

const REVIEW_STATUSES = [
  "not_required",
  "requested",
  "accepted_by_human",
  "rejected_by_human",
  "edited_by_human"
];

const UI_LABELS: Record<string, string> = {
  purchase_requisition: "采购申请",
  expense: "费用报销",
  invoice_payment: "发票付款",
  supplier_onboarding: "供应商准入",
  contract_exception: "合同例外",
  budget_exception: "预算例外",
  unknown: "未知",
  recommend_approve: "建议通过",
  recommend_reject: "建议拒绝",
  request_more_info: "请求补充信息",
  escalate: "升级复核",
  blocked: "已阻断",
  not_required: "无需人工复核",
  requested: "已请求人工复核",
  accepted_by_human: "人工已接受建议",
  rejected_by_human: "人工已拒绝建议",
  edited_by_human: "人工已编辑建议",
  manual_review: "人工复核",
  add_internal_comment: "拟添加内部备注",
  route_to_manager: "拟转交经理",
  route_to_finance: "拟转交财务",
  route_to_procurement: "拟转交采购",
  route_to_legal: "拟转交法务",
  proposed_only: "仅建议",
  rejected_by_validation: "校验拒绝",
  general: "一般备注",
  risk: "风险",
  missing_info: "缺失信息",
  policy_friction: "政策摩擦",
  reviewer_decision: "复核决定",
  follow_up: "后续跟进"
};

function displayLabel(value: string | number | boolean | null | undefined) {
  if (value === null || value === undefined || value === "") {
    return "未知";
  }
  const text = String(value);
  return UI_LABELS[text] ?? text;
}

function CountList({ counts }: { counts: Record<string, number> }) {
  const entries = useMemo(
    () => Object.entries(counts).sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0])),
    [counts]
  );
  if (!entries.length) {
    return <p className="pixel-note mt-3">暂无数据。</p>;
  }
  return (
    <div className="mt-3 space-y-2">
      {entries.map(([label, count]) => (
        <div className="flex items-center justify-between gap-3 text-sm" key={label}>
          <span className="text-[var(--color-ink-soft)]">{displayLabel(label)}</span>
          <span className="pixel-tag">{count}</span>
        </div>
      ))}
    </div>
  );
}

function TopList({ items }: { items: Array<{ item: string; count: number }> }) {
  if (!items.length) {
    return <p className="pixel-note mt-3">暂无数据。</p>;
  }
  return (
    <div className="mt-3 space-y-2">
      {items.map((entry) => (
        <div className="flex items-start justify-between gap-3 text-sm" key={entry.item}>
          <span className="text-[var(--color-ink-soft)]">{entry.item}</span>
          <span className="pixel-tag">{entry.count}</span>
        </div>
      ))}
    </div>
  );
}

function ValueList({ values }: { values: string[] }) {
  if (!values.length) {
    return <span className="text-[var(--color-ink-muted)]">无</span>;
  }
  return (
    <div className="flex flex-wrap gap-2">
      {values.map((value) => (
        <span className="pixel-tag" key={value}>
          {displayLabel(value)}
        </span>
      ))}
    </div>
  );
}

function queryFromFilters(filters: TraceFilters): ErpApprovalTraceQuery {
  return {
    limit: 100,
    approval_type: filters.approval_type || undefined,
    recommendation_status: filters.recommendation_status || undefined,
    review_status: filters.review_status || undefined,
    high_risk_only: filters.high_risk_only || undefined,
    text_query: filters.text_query.trim() || undefined
  };
}

function downloadText(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function isApiError(caught: unknown, fallback: string) {
  return caught instanceof ApiConnectionError ? caught.message : fallback;
}

function ProposalRecords({ proposals }: { proposals: ErpApprovalActionProposalRecord[] }) {
  if (!proposals.length) {
    return <p className="pixel-note mt-3">这个 trace 暂无 action proposal 记录。</p>;
  }
  return (
    <div className="mt-3 space-y-3">
      {proposals.map((proposal) => (
        <div className="border-t border-[var(--color-line)] pt-3 text-sm" key={proposal.proposal_record_id}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-[var(--color-ink)]">{proposal.title || proposal.action_type}</p>
              <p className="mt-1 text-xs text-[var(--color-ink-muted)]">{proposal.proposal_record_id}</p>
            </div>
            <span className="pixel-tag">可执行={String(proposal.executable)}</span>
          </div>
          <p className="mt-2 text-[var(--color-ink-soft)]">{proposal.summary || "没有摘要。"}</p>
          <div className="mt-3 grid gap-2 md:grid-cols-2">
            <p className="text-[var(--color-ink-soft)]">动作类型 {displayLabel(proposal.action_type || "unknown")}</p>
            <p className="text-[var(--color-ink-soft)]">风险 {displayLabel(proposal.risk_level || "unknown")}</p>
            <p className="break-all text-[var(--color-ink-soft)] md:col-span-2">
              幂等键 {proposal.idempotency_key || "缺失"}
            </p>
          </div>
          {proposal.validation_warnings.length ? (
            <div className="mt-3">
              <p className="pixel-label mb-2">校验警告</p>
              <ValueList values={proposal.validation_warnings} />
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function TraceDetail({
  trace,
  proposals,
  auditLoading,
  onDownloadAuditPackage
}: {
  trace: ErpApprovalTraceRecord | null;
  proposals: ErpApprovalActionProposalRecord[];
  auditLoading: boolean;
  onDownloadAuditPackage: () => void;
}) {
  if (!trace) {
    return (
      <div className="pixel-card p-4 text-sm text-[var(--color-ink-soft)]">
        尚未选择 trace。
      </div>
    );
  }
  return (
    <div className="pixel-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="pixel-label">trace 详情</p>
          <h3 className="pixel-title mt-2 text-[1rem] text-[var(--color-ink)]">{trace.approval_id || trace.trace_id}</h3>
          <p className="mt-1 text-xs text-[var(--color-ink-muted)]">{trace.trace_id}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <span className="pixel-tag">{displayLabel(trace.approval_type || "unknown")}</span>
          <button className="ui-button" disabled={auditLoading} onClick={onDownloadAuditPackage} type="button">
            {auditLoading ? "正在准备审计包..." : "下载审计包"}
          </button>
        </div>
      </div>

      <div className="mt-4 grid gap-3 text-sm md:grid-cols-2">
        <div>
          <p className="pixel-label">审批请求</p>
          <p className="mt-2 text-[var(--color-ink-soft)]">
            {trace.requester || "未知申请人"} / {trace.department || "未知部门"}
          </p>
          <p className="text-[var(--color-ink-soft)]">
            {trace.vendor || "未知供应商"} / {trace.cost_center || "未知成本中心"}
          </p>
          <p className="text-[var(--color-ink-soft)]">
            {trace.amount ?? "未知金额"} {trace.currency || ""}
          </p>
        </div>
        <div>
          <p className="pixel-label">审批建议</p>
          <p className="mt-2 text-[var(--color-ink-soft)]">{displayLabel(trace.recommendation_status || "unknown")}</p>
          <p className="text-[var(--color-ink-soft)]">置信度 {trace.recommendation_confidence.toFixed(2)}</p>
          <p className="text-[var(--color-ink-soft)]">复核状态 {displayLabel(trace.review_status || "unknown")}</p>
        </div>
      </div>

      <div className="mt-4 space-y-4 text-sm">
        <div>
          <p className="pixel-label mb-2">缺失信息</p>
          <ValueList values={trace.missing_information} />
        </div>
        <div>
          <p className="pixel-label mb-2">风险标记</p>
          <ValueList values={trace.risk_flags} />
        </div>
        <div>
          <p className="pixel-label mb-2">Guard 警告</p>
          <ValueList values={trace.guard_warnings} />
        </div>
        <div>
          <p className="pixel-label mb-2">Proposal 动作类型</p>
          <ValueList values={trace.proposal_action_types} />
        </div>
        <div>
          <p className="pixel-label mb-2">Proposal 状态</p>
          <ValueList values={trace.proposal_statuses} />
        </div>
        <div>
          <p className="pixel-label mb-2">被阻断的 proposal IDs</p>
          <ValueList values={trace.blocked_proposal_ids} />
        </div>
        <div>
          <p className="pixel-label mb-2">被校验拒绝的 proposal IDs</p>
          <ValueList values={trace.rejected_proposal_ids} />
        </div>
        <div>
          <p className="pixel-label mb-2">上下文 source IDs</p>
          <ValueList values={trace.context_source_ids} />
        </div>
        <div>
          <p className="pixel-label mb-2">Action proposal 记录</p>
          <ProposalRecords proposals={proposals} />
        </div>
      </div>
    </div>
  );
}

function AuditWorkspace({
  createdBy,
  description,
  noteAuthor,
  noteBody,
  noteType,
  packages,
  selectedPackage,
  simulationConfirmNoWrite,
  simulationNote,
  simulationProposalId,
  simulationRecord,
  simulationRequestedBy,
  notes,
  saving,
  title,
  onAppendNote,
  onCreatedByChange,
  onDescriptionChange,
  onDownloadPackage,
  onLoadPackage,
  onNoteAuthorChange,
  onNoteBodyChange,
  onNoteTypeChange,
  onRunSimulation,
  onSaveFiltered,
  onSaveSelected,
  onSimulationConfirmNoWriteChange,
  onSimulationNoteChange,
  onSimulationProposalIdChange,
  onSimulationRequestedByChange,
  onTitleChange
}: {
  createdBy: string;
  description: string;
  noteAuthor: string;
  noteBody: string;
  noteType: string;
  packages: SavedErpApprovalAuditPackageManifest[];
  selectedPackage: SavedErpApprovalAuditPackageManifest | null;
  simulationConfirmNoWrite: boolean;
  simulationNote: string;
  simulationProposalId: string;
  simulationRecord: ErpApprovalActionSimulationRecord | null;
  simulationRequestedBy: string;
  notes: ErpApprovalReviewerNote[];
  saving: boolean;
  title: string;
  onAppendNote: () => void;
  onCreatedByChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onDownloadPackage: () => void;
  onLoadPackage: (manifest: SavedErpApprovalAuditPackageManifest) => void;
  onNoteAuthorChange: (value: string) => void;
  onNoteBodyChange: (value: string) => void;
  onNoteTypeChange: (value: string) => void;
  onRunSimulation: () => void;
  onSaveFiltered: () => void;
  onSaveSelected: () => void;
  onSimulationConfirmNoWriteChange: (value: boolean) => void;
  onSimulationNoteChange: (value: string) => void;
  onSimulationProposalIdChange: (value: string) => void;
  onSimulationRequestedByChange: (value: string) => void;
  onTitleChange: (value: string) => void;
}) {
  return (
    <section className="pixel-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="pixel-label">本地审计 workspace</p>
          <h3 className="pixel-title mt-2 text-[1rem] text-[var(--color-ink)]">已保存审计包</h3>
          <p className="mt-2 max-w-3xl text-sm text-[var(--color-ink-soft)]">
            保存的审计包和 reviewer notes 都是本地复核材料，不会执行 ERP 动作。
          </p>
        </div>
        <button className="ui-button" disabled={!selectedPackage || saving} onClick={onDownloadPackage} type="button">
          下载已保存审计包
        </button>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <label className="text-sm">
          <span className="pixel-label">标题</span>
          <input className="pixel-field mt-2 px-3 py-2" onChange={(event) => onTitleChange(event.target.value)} value={title} />
        </label>
        <label className="text-sm">
          <span className="pixel-label">创建人</span>
          <input className="pixel-field mt-2 px-3 py-2" onChange={(event) => onCreatedByChange(event.target.value)} value={createdBy} />
        </label>
        <label className="text-sm">
          <span className="pixel-label">说明</span>
          <input className="pixel-field mt-2 px-3 py-2" onChange={(event) => onDescriptionChange(event.target.value)} value={description} />
        </label>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <button className="ui-button" disabled={saving} onClick={onSaveSelected} type="button">
          保存当前 trace 审计包
        </button>
        <button className="ui-button" disabled={saving} onClick={onSaveFiltered} type="button">
          保存过滤结果审计包
        </button>
      </div>

      <div className="mt-5 grid gap-4 xl:grid-cols-[minmax(280px,0.8fr)_minmax(420px,1.2fr)]">
        <div>
          <p className="pixel-label">已保存审计包</p>
          <div className="mt-3 space-y-2">
            {packages.length ? (
              packages.map((item) => (
                <button
                  className={
                    selectedPackage?.package_id === item.package_id
                      ? "w-full border-t border-[var(--color-accent-line)] py-3 text-left"
                      : "w-full border-t border-[var(--color-line)] py-3 text-left"
                  }
                  key={item.package_id}
                  onClick={() => onLoadPackage(item)}
                  type="button"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm text-[var(--color-ink)]">{item.title || item.package_id}</p>
                      <p className="mt-1 text-xs text-[var(--color-ink-muted)]">{item.created_at || "未知日期"}</p>
                    </div>
                    <span className="pixel-tag">{item.note_count} 条备注</span>
                  </div>
                </button>
              ))
            ) : (
              <p className="pixel-note">还没有保存的审计包。</p>
            )}
          </div>
        </div>

        <div className="pixel-card-soft p-4">
          {selectedPackage ? (
            <>
              <p className="pixel-label">审计包详情</p>
              <h4 className="pixel-title mt-2 text-[0.95rem]">{selectedPackage.title}</h4>
              <p className="mt-2 break-all text-xs text-[var(--color-ink-muted)]">{selectedPackage.package_id}</p>
              <p className="mt-3 text-sm text-[var(--color-ink-soft)]">{selectedPackage.description || "没有说明。"}</p>
              <div className="mt-3 grid gap-2 text-sm md:grid-cols-2">
                <p className="text-[var(--color-ink-soft)]">traces {selectedPackage.trace_ids.length}</p>
                <p className="text-[var(--color-ink-soft)]">proposals {selectedPackage.proposal_record_ids.length}</p>
                <p className="break-all text-[var(--color-ink-soft)] md:col-span-2">hash {selectedPackage.package_hash}</p>
              </div>

              <div className="mt-5">
                <p className="pixel-label">Reviewer notes</p>
                <div className="mt-3 space-y-2">
                  {notes.length ? (
                    notes.map((note) => (
                      <div className="border-t border-[var(--color-line)] pt-3 text-sm" key={note.note_id}>
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="text-[var(--color-ink)]">{note.author || "local_reviewer"}</span>
                          <span className="pixel-tag">{displayLabel(note.note_type)}</span>
                        </div>
                        <p className="mt-2 text-[var(--color-ink-soft)]">{note.body}</p>
                      </div>
                    ))
                  ) : (
                    <p className="pixel-note">还没有 reviewer notes。</p>
                  )}
                </div>
              </div>

              <div className="mt-5 grid gap-3 md:grid-cols-[minmax(120px,0.4fr)_minmax(120px,0.4fr)_minmax(220px,1fr)]">
                <input className="pixel-field px-3 py-2" onChange={(event) => onNoteAuthorChange(event.target.value)} placeholder="作者" value={noteAuthor} />
                <select className="pixel-field px-3 py-2" onChange={(event) => onNoteTypeChange(event.target.value)} value={noteType}>
                  <option value="general">一般备注</option>
                  <option value="risk">风险</option>
                  <option value="missing_info">缺失信息</option>
                  <option value="policy_friction">政策摩擦</option>
                  <option value="reviewer_decision">复核决定</option>
                  <option value="follow_up">后续跟进</option>
                </select>
                <input className="pixel-field px-3 py-2" onChange={(event) => onNoteBodyChange(event.target.value)} placeholder="本地 reviewer note" value={noteBody} />
              </div>
              <button className="ui-button mt-3" disabled={saving || !noteBody.trim()} onClick={onAppendNote} type="button">
                添加本地备注
              </button>

              <div className="mt-6 border-t border-[var(--color-line)] pt-5">
                <p className="pixel-label">本地 simulation sandbox</p>
                <p className="mt-2 text-sm text-[var(--color-ink-soft)]">
                  这里只做本地 simulation，不执行任何 ERP action。
                </p>
                <div className="mt-4 grid gap-3 md:grid-cols-[minmax(220px,1fr)_minmax(140px,0.5fr)_minmax(220px,1fr)]">
                  <select
                    className="pixel-field px-3 py-2"
                    onChange={(event) => onSimulationProposalIdChange(event.target.value)}
                    value={simulationProposalId}
                  >
                    <option value="">选择 proposal record</option>
                    {selectedPackage.proposal_record_ids.map((proposalId) => (
                      <option key={proposalId} value={proposalId}>
                        {proposalId}
                      </option>
                    ))}
                  </select>
                  <input
                    className="pixel-field px-3 py-2"
                    onChange={(event) => onSimulationRequestedByChange(event.target.value)}
                    placeholder="请求人"
                    value={simulationRequestedBy}
                  />
                  <input
                    className="pixel-field px-3 py-2"
                    onChange={(event) => onSimulationNoteChange(event.target.value)}
                    placeholder="Simulation 备注"
                    value={simulationNote}
                  />
                </div>
                <label className="mt-3 flex items-center gap-2 text-sm text-[var(--color-ink-soft)]">
                  <input
                    checked={simulationConfirmNoWrite}
                    onChange={(event) => onSimulationConfirmNoWriteChange(event.target.checked)}
                    type="checkbox"
                  />
                  我确认这里只做本地 dry-run，不会尝试 ERP 写入。
                </label>
                <button
                  className="ui-button mt-3"
                  disabled={saving || !selectedPackage.proposal_record_ids.length || !simulationProposalId || !simulationConfirmNoWrite}
                  onClick={onRunSimulation}
                  type="button"
                >
                  运行本地 simulation
                </button>

                {simulationRecord ? (
                  <div className="pixel-card-soft mt-4 p-3 text-sm">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-[var(--color-ink)]">{simulationRecord.status}</p>
                        <p className="mt-1 break-all text-xs text-[var(--color-ink-muted)]">{simulationRecord.simulation_id}</p>
                      </div>
                      <span className="pixel-tag">仅 simulation={String(simulationRecord.simulated_only)}</span>
                      <span className="pixel-tag">ERP 写入已执行={String(simulationRecord.erp_write_executed)}</span>
                    </div>
                    <pre className="mt-3 overflow-auto whitespace-pre-wrap text-xs text-[var(--color-ink-soft)]">
                      {JSON.stringify(simulationRecord.output_preview, null, 2)}
                    </pre>
                    {simulationRecord.validation_warnings.length ? (
                      <div className="mt-3">
                        <p className="pixel-label mb-2">校验警告</p>
                        <ValueList values={simulationRecord.validation_warnings} />
                      </div>
                    ) : null}
                    {simulationRecord.blocked_reasons.length ? (
                      <div className="mt-3">
                        <p className="pixel-label mb-2">阻断原因</p>
                        <ValueList values={simulationRecord.blocked_reasons} />
                      </div>
                    ) : null}
                    <p className="mt-3 text-[var(--color-ink-soft)]">{simulationRecord.non_action_statement}</p>
                  </div>
                ) : null}
              </div>
            </>
          ) : (
            <p className="pixel-note">请选择一个已保存审计包，用于查看备注和导出快照。</p>
          )}
        </div>
      </div>
    </section>
  );
}

export function InsightsPanel() {
  const [summary, setSummary] = useState<ErpApprovalAnalyticsSummary | null>(null);
  const [trends, setTrends] = useState<ErpApprovalTrendSummary | null>(null);
  const [traces, setTraces] = useState<ErpApprovalTraceRecord[]>([]);
  const [selectedTrace, setSelectedTrace] = useState<ErpApprovalTraceRecord | null>(null);
  const [selectedProposals, setSelectedProposals] = useState<ErpApprovalActionProposalRecord[]>([]);
  const [savedPackages, setSavedPackages] = useState<SavedErpApprovalAuditPackageManifest[]>([]);
  const [selectedPackage, setSelectedPackage] = useState<SavedErpApprovalAuditPackageManifest | null>(null);
  const [packageNotes, setPackageNotes] = useState<ErpApprovalReviewerNote[]>([]);
  const [packageTitle, setPackageTitle] = useState("ERP 审批审计包");
  const [packageDescription, setPackageDescription] = useState("");
  const [packageCreatedBy, setPackageCreatedBy] = useState("local_reviewer");
  const [noteAuthor, setNoteAuthor] = useState("local_reviewer");
  const [noteType, setNoteType] = useState("general");
  const [noteBody, setNoteBody] = useState("");
  const [simulationProposalId, setSimulationProposalId] = useState("");
  const [simulationRequestedBy, setSimulationRequestedBy] = useState("local_reviewer");
  const [simulationNote, setSimulationNote] = useState("");
  const [simulationConfirmNoWrite, setSimulationConfirmNoWrite] = useState(false);
  const [simulationRecord, setSimulationRecord] = useState<ErpApprovalActionSimulationRecord | null>(null);
  const [filters, setFilters] = useState<TraceFilters>(DEFAULT_FILTERS);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [auditLoading, setAuditLoading] = useState(false);
  const [workspaceSaving, setWorkspaceSaving] = useState(false);
  const [error, setError] = useState("");

  const query = useMemo(() => queryFromFilters(filters), [filters]);

  const loadDashboard = useCallback(() => {
    let active = true;
    setLoading(true);
    setError("");
    void Promise.all([
      getErpApprovalAnalyticsSummary(),
      listErpApprovalTraces(query),
      getErpApprovalTrendSummary({ ...query, limit: 500 })
    ])
      .then(([summaryPayload, tracePayload, trendPayload]) => {
        if (!active) {
          return;
        }
        setSummary(summaryPayload);
        setTraces(tracePayload);
        setTrends(trendPayload);
        setSelectedTrace((current) => tracePayload.find((trace) => trace.trace_id === current?.trace_id) ?? tracePayload[0] ?? null);
        if (!tracePayload.length) {
          setSelectedProposals([]);
        }
      })
      .catch((caught) => {
        if (active) {
          setError(isApiError(caught, "无法加载 ERP 审批管理洞察。"));
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [query]);

  useEffect(() => loadDashboard(), [loadDashboard]);

  const loadSavedPackages = useCallback(() => {
    void listSavedErpApprovalAuditPackages()
      .then((payload) => {
        setSavedPackages(payload);
        setSelectedPackage((current) => payload.find((item) => item.package_id === current?.package_id) ?? current);
      })
      .catch((caught) => setError(isApiError(caught, "无法加载已保存的 ERP 审批审计包。")));
  }, []);

  useEffect(() => loadSavedPackages(), [loadSavedPackages]);

  const updateFilter = <Key extends keyof TraceFilters>(key: Key, value: TraceFilters[Key]) => {
    setFilters((current) => ({ ...current, [key]: value }));
  };

  const selectTrace = (trace: ErpApprovalTraceRecord) => {
    setSelectedTrace(trace);
    setDetailLoading(true);
    void Promise.all([getErpApprovalTrace(trace.trace_id), listErpApprovalTraceProposals(trace.trace_id)])
      .then(([tracePayload, proposalPayload]) => {
        setSelectedTrace(tracePayload);
        setSelectedProposals(proposalPayload);
      })
      .catch((caught) => setError(isApiError(caught, "无法加载 ERP 审批 trace 详情。")))
      .finally(() => setDetailLoading(false));
  };

  useEffect(() => {
    if (!selectedTrace?.trace_id) {
      setSelectedProposals([]);
      return;
    }
    let active = true;
    void listErpApprovalTraceProposals(selectedTrace.trace_id)
      .then((payload) => {
        if (active) {
          setSelectedProposals(payload);
        }
      })
      .catch((caught) => {
        if (active) {
          setError(isApiError(caught, "无法加载 ERP 审批 action proposal 记录。"));
        }
      });
    return () => {
      active = false;
    };
  }, [selectedTrace?.trace_id]);

  const exportJson = () => {
    setExporting(true);
    setError("");
    void exportErpApprovalTracesJson({ ...query, limit: 500 })
      .then((payload) => downloadText("erp-approval-traces.json", JSON.stringify(payload, null, 2), "application/json"))
      .catch((caught) => setError(isApiError(caught, "无法导出 ERP 审批 traces JSON。")))
      .finally(() => setExporting(false));
  };

  const exportCsv = () => {
    setExporting(true);
    setError("");
    void exportErpApprovalTracesCsv({ ...query, limit: 500 })
      .then((payload) => downloadText("erp-approval-traces.csv", payload, "text/csv"))
      .catch((caught) => setError(isApiError(caught, "无法导出 ERP 审批 traces CSV。")))
      .finally(() => setExporting(false));
  };

  const downloadAuditPackage = () => {
    if (!selectedTrace?.trace_id) {
      return;
    }
    setAuditLoading(true);
    setError("");
    void getErpApprovalAuditPackage([selectedTrace.trace_id])
      .then((payload) => downloadText(`${selectedTrace.approval_id || "erp-approval"}-audit-package.json`, JSON.stringify(payload, null, 2), "application/json"))
      .catch((caught) => setError(isApiError(caught, "无法下载 ERP 审批审计包。")))
      .finally(() => setAuditLoading(false));
  };

  const loadSavedPackage = (manifest: SavedErpApprovalAuditPackageManifest) => {
    setSelectedPackage(manifest);
    setWorkspaceSaving(true);
    void Promise.all([getSavedErpApprovalAuditPackage(manifest.package_id), listSavedErpApprovalAuditPackageNotes(manifest.package_id)])
      .then(([packagePayload, notesPayload]) => {
        setSelectedPackage(packagePayload);
        setPackageNotes(notesPayload);
        setSimulationProposalId((current) =>
          packagePayload.proposal_record_ids.includes(current) ? current : packagePayload.proposal_record_ids[0] ?? ""
        );
        setSimulationRecord(null);
      })
      .catch((caught) => setError(isApiError(caught, "无法加载已保存审计包。")))
      .finally(() => setWorkspaceSaving(false));
  };

  const saveAuditWorkspacePackage = (traceIds: string[]) => {
    if (!traceIds.length) {
      setError("没有选择可保存到本地审计包的 ERP approval traces。");
      return;
    }
    setWorkspaceSaving(true);
    setError("");
    void saveErpApprovalAuditPackage({
      title: packageTitle,
      description: packageDescription,
      created_by: packageCreatedBy,
      trace_ids: traceIds,
      filters: query
    })
      .then((manifest) => {
        setSelectedPackage(manifest);
        setPackageNotes([]);
        setSimulationProposalId(manifest.proposal_record_ids[0] ?? "");
        setSimulationRecord(null);
        loadSavedPackages();
      })
      .catch((caught) => setError(isApiError(caught, "无法保存本地审计包。")))
      .finally(() => setWorkspaceSaving(false));
  };

  const saveSelectedTracePackage = () => saveAuditWorkspacePackage(selectedTrace?.trace_id ? [selectedTrace.trace_id] : []);

  const saveFilteredTracePackage = () => saveAuditWorkspacePackage(traces.map((trace) => trace.trace_id));

  const appendReviewerNote = () => {
    if (!selectedPackage?.package_id || !noteBody.trim()) {
      return;
    }
    const packageId = selectedPackage.package_id;
    setWorkspaceSaving(true);
    setError("");
    void appendSavedErpApprovalAuditPackageNote(packageId, {
      author: noteAuthor,
      note_type: noteType,
      body: noteBody,
      trace_id: selectedTrace?.trace_id ?? ""
    })
      .then(() => Promise.all([listSavedErpApprovalAuditPackageNotes(packageId), listSavedErpApprovalAuditPackages()]))
      .then(([notesPayload, packagePayload]) => {
        setPackageNotes(notesPayload);
        setSavedPackages(packagePayload);
        setSelectedPackage((current) => packagePayload.find((item) => item.package_id === current?.package_id) ?? current);
        setNoteBody("");
      })
      .catch((caught) => setError(isApiError(caught, "无法保存本地 reviewer note。")))
      .finally(() => setWorkspaceSaving(false));
  };

  const downloadSavedAuditPackage = () => {
    if (!selectedPackage?.package_id) {
      return;
    }
    const packageId = selectedPackage.package_id;
    const filename = selectedPackage.title || "erp-approval";
    setWorkspaceSaving(true);
    setError("");
    void exportSavedErpApprovalAuditPackage(packageId)
      .then((payload) => downloadText(`${filename}-saved-audit-package.json`, JSON.stringify(payload, null, 2), "application/json"))
      .catch((caught) => setError(isApiError(caught, "无法下载已保存审计包。")))
      .finally(() => setWorkspaceSaving(false));
  };

  const runLocalSimulation = () => {
    if (!selectedPackage?.package_id || !simulationProposalId || !simulationConfirmNoWrite) {
      setError("请选择 proposal record，并确认这里只做本地 simulation。");
      return;
    }
    setWorkspaceSaving(true);
    setError("");
    void runErpApprovalActionSimulation({
      proposal_record_id: simulationProposalId,
      package_id: selectedPackage.package_id,
      requested_by: simulationRequestedBy,
      confirm_no_erp_write: simulationConfirmNoWrite,
      note: simulationNote
    })
      .then((payload) => setSimulationRecord(payload))
      .catch((caught) => setError(isApiError(caught, "无法运行本地 ERP approval action simulation。")))
      .finally(() => setWorkspaceSaving(false));
  };

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="panel flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4 pb-4 pt-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="pixel-label">管理洞察</p>
            <h3 className="pixel-title mt-2 text-[1rem] text-[var(--color-ink)]">
              管理视图、Trace Explorer 和模型调试
            </h3>
            <p className="pixel-note mt-2 max-w-3xl">
              默认展示管理者能看懂的风险、缺口和 trace；连接器、RAG、prompt 上下文都放在调试区，避免和案件操作混在一起。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="ui-button" disabled={loading} onClick={loadDashboard} type="button">
              {loading ? "正在刷新..." : "刷新"}
            </button>
            <button className="ui-button" disabled={exporting} onClick={exportJson} type="button">
              导出 JSON
            </button>
            <button className="ui-button" disabled={exporting} onClick={exportCsv} type="button">
              导出 CSV
            </button>
          </div>
        </div>

        {error ? <div className="pixel-card-soft px-4 py-4 text-sm text-[var(--color-danger)]">{error}</div> : null}

        <section className="grid gap-4 md:grid-cols-3">
          <div className="pixel-card-soft p-4">
            <p className="pixel-label">1. 管理摘要</p>
            <p className="mt-3 text-sm leading-6 text-[var(--color-ink-soft)]">
              看 trace 数量、人工复核、被阻断 proposal 和高风险案件，判断流程是否顺畅。
            </p>
          </div>
          <div className="pixel-card-soft p-4">
            <p className="pixel-label">2. Trace drill-down</p>
            <p className="mt-3 text-sm leading-6 text-[var(--color-ink-soft)]">
              选中单个 trace，查看缺失材料、风险、proposal、审计包和 reviewer notes。
            </p>
          </div>
          <div className="pixel-card-soft p-4">
            <p className="pixel-label">3. 模型调试</p>
            <p className="mt-3 text-sm leading-6 text-[var(--color-ink-soft)]">
              查看 policy RAG、connector replay、LLM Markdown 文件和当前上下文，定位模型为什么这么判断。
            </p>
          </div>
        </section>

        <section className="pixel-card-soft grid gap-3 p-4 md:grid-cols-5">
          <label className="text-sm">
            <span className="pixel-label">审批类型</span>
            <select
              className="pixel-field mt-2 px-3 py-2"
              onChange={(event) => updateFilter("approval_type", event.target.value)}
              value={filters.approval_type}
            >
              <option value="">全部</option>
              {APPROVAL_TYPES.map((option) => (
                <option key={option} value={option}>
                  {displayLabel(option)}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="pixel-label">审批建议</span>
            <select
              className="pixel-field mt-2 px-3 py-2"
              onChange={(event) => updateFilter("recommendation_status", event.target.value)}
              value={filters.recommendation_status}
            >
              <option value="">全部</option>
              {RECOMMENDATION_STATUSES.map((option) => (
                <option key={option} value={option}>
                  {displayLabel(option)}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="pixel-label">复核状态</span>
            <select
              className="pixel-field mt-2 px-3 py-2"
              onChange={(event) => updateFilter("review_status", event.target.value)}
              value={filters.review_status}
            >
              <option value="">全部</option>
              {REVIEW_STATUSES.map((option) => (
                <option key={option} value={option}>
                  {displayLabel(option)}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm md:col-span-2">
            <span className="pixel-label">文本搜索</span>
            <input
              className="pixel-field mt-2 px-3 py-2"
              onChange={(event) => updateFilter("text_query", event.target.value)}
              placeholder="搜索 approval_id、申请人、供应商、成本中心或 trace_id"
              value={filters.text_query}
            />
          </label>
          <label className="flex items-center gap-2 text-sm text-[var(--color-ink-soft)]">
            <input
              checked={filters.high_risk_only}
              onChange={(event) => updateFilter("high_risk_only", event.target.checked)}
              type="checkbox"
            />
            只看高风险
          </label>
          <button className="ui-button md:col-span-4 md:justify-self-start" onClick={() => setFilters(DEFAULT_FILTERS)} type="button">
            清除过滤
          </button>
        </section>

        <ConnectorDiagnosticsPanel />

        <LlmContextLibraryPanel compact />

        {!summary || loading ? (
          <div className="pixel-card-soft px-4 py-4 text-sm text-[var(--color-ink-soft)]">
            {loading ? "正在加载 ERP 审批洞察..." : "还没有 ERP approval traces。"}
          </div>
        ) : summary.total_traces <= 0 ? (
          <div className="pixel-card-soft px-4 py-4 text-sm text-[var(--color-ink-soft)]">
            还没有 ERP approval traces。
          </div>
        ) : (
          <>
            <section className="grid gap-4 md:grid-cols-4">
              <div className="pixel-card p-4">
                <p className="pixel-label">Trace 总数</p>
                <p className="pixel-title mt-3 text-[1.6rem] text-[var(--color-ink)]">{summary.total_traces}</p>
              </div>
              <div className="pixel-card p-4">
                <p className="pixel-label">过滤后 traces</p>
                <p className="pixel-title mt-3 text-[1.6rem] text-[var(--color-ink)]">{traces.length}</p>
              </div>
              <div className="pixel-card p-4">
                <p className="pixel-label">需要人工复核</p>
                <p className="pixel-title mt-3 text-[1.6rem] text-[var(--color-ink)]">
                  {summary.human_review_required_count}
                </p>
              </div>
              <div className="pixel-card p-4">
                <p className="pixel-label">被阻断/拒绝 proposals</p>
                <p className="pixel-title mt-3 text-[1.6rem] text-[var(--color-ink)]">
                  {summary.blocked_proposal_count + summary.rejected_proposal_count}
                </p>
              </div>
            </section>

            <section className="grid gap-4 lg:grid-cols-2">
              <div className="pixel-card p-4">
                <p className="pixel-label">建议状态</p>
                <CountList counts={summary.by_recommendation_status} />
              </div>
              <div className="pixel-card p-4">
                <p className="pixel-label">复核状态</p>
                <CountList counts={summary.by_review_status} />
              </div>
              <div className="pixel-card p-4">
                <p className="pixel-label">缺失信息</p>
                <TopList items={summary.top_missing_information} />
              </div>
              <div className="pixel-card p-4">
                <p className="pixel-label">Proposal 动作类型</p>
                <CountList counts={summary.proposal_action_type_counts} />
              </div>
            </section>

            <section>
              <p className="pixel-label">趋势分桶</p>
              <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {(trends?.buckets ?? []).length ? (
                  trends?.buckets.map((bucket) => (
                    <div className="pixel-card p-3 text-sm" key={bucket.bucket}>
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-[var(--color-ink)]">{bucket.bucket}</span>
                        <span className="pixel-tag">{bucket.total_traces}</span>
                      </div>
                      <p className="mt-2 text-[var(--color-ink-soft)]">
                        人工复核 {bucket.human_review_required_count} / guard 降级 {bucket.guard_downgrade_count}
                      </p>
                    </div>
                  ))
                ) : (
                  <p className="pixel-note">暂无趋势分桶。</p>
                )}
              </div>
            </section>

            <section className="grid gap-4 xl:grid-cols-[minmax(320px,0.8fr)_minmax(420px,1.2fr)]">
              <div className="pixel-card p-4">
                <p className="pixel-label">Trace 列表</p>
                <div className="mt-3 space-y-2">
                  {traces.length ? (
                    traces.map((trace) => (
                      <button
                        className={
                          selectedTrace?.trace_id === trace.trace_id
                            ? "w-full border-t border-[var(--color-accent-line)] py-3 text-left"
                            : "w-full border-t border-[var(--color-line)] py-3 text-left"
                        }
                        key={trace.trace_id}
                        onClick={() => selectTrace(trace)}
                        type="button"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="text-sm text-[var(--color-ink)]">{trace.approval_id || trace.trace_id}</p>
                            <p className="mt-1 text-xs text-[var(--color-ink-muted)]">{trace.created_at || "未知日期"}</p>
                          </div>
                          <span className="pixel-tag">{displayLabel(trace.recommendation_status || "unknown")}</span>
                        </div>
                        <p className="mt-2 text-xs text-[var(--color-ink-soft)]">
                          {trace.vendor || "未知供应商"} / {displayLabel(trace.review_status || "unknown")}
                        </p>
                      </button>
                    ))
                  ) : (
                    <p className="pixel-note">当前过滤条件下没有 ERP approval traces。</p>
                  )}
                </div>
              </div>

              <div className="relative">
                {detailLoading ? (
                  <div className="absolute right-3 top-3 z-10 pixel-tag">正在加载详情</div>
                ) : null}
                <TraceDetail
                  auditLoading={auditLoading}
                  onDownloadAuditPackage={downloadAuditPackage}
                  proposals={selectedProposals}
                  trace={selectedTrace}
                />
              </div>
            </section>

            <AuditWorkspace
              createdBy={packageCreatedBy}
              description={packageDescription}
              noteAuthor={noteAuthor}
              noteBody={noteBody}
              noteType={noteType}
              notes={packageNotes}
              onAppendNote={appendReviewerNote}
              onCreatedByChange={setPackageCreatedBy}
              onDescriptionChange={setPackageDescription}
              onDownloadPackage={downloadSavedAuditPackage}
              onLoadPackage={loadSavedPackage}
              onNoteAuthorChange={setNoteAuthor}
              onNoteBodyChange={setNoteBody}
              onNoteTypeChange={setNoteType}
              onRunSimulation={runLocalSimulation}
              onSaveFiltered={saveFilteredTracePackage}
              onSaveSelected={saveSelectedTracePackage}
              onSimulationConfirmNoWriteChange={setSimulationConfirmNoWrite}
              onSimulationNoteChange={setSimulationNote}
              onSimulationProposalIdChange={setSimulationProposalId}
              onSimulationRequestedByChange={setSimulationRequestedBy}
              onTitleChange={setPackageTitle}
              packages={savedPackages}
              saving={workspaceSaving}
              selectedPackage={selectedPackage}
              simulationConfirmNoWrite={simulationConfirmNoWrite}
              simulationNote={simulationNote}
              simulationProposalId={simulationProposalId}
              simulationRecord={simulationRecord}
              simulationRequestedBy={simulationRequestedBy}
              title={packageTitle}
            />
          </>
        )}
      </div>
    </section>
  );
}
