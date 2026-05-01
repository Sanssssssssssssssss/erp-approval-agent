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

function CountList({ counts }: { counts: Record<string, number> }) {
  const entries = useMemo(
    () => Object.entries(counts).sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0])),
    [counts]
  );
  if (!entries.length) {
    return <p className="pixel-note mt-3">No data yet.</p>;
  }
  return (
    <div className="mt-3 space-y-2">
      {entries.map(([label, count]) => (
        <div className="flex items-center justify-between gap-3 text-sm" key={label}>
          <span className="text-[var(--color-ink-soft)]">{label}</span>
          <span className="pixel-tag">{count}</span>
        </div>
      ))}
    </div>
  );
}

function TopList({ items }: { items: Array<{ item: string; count: number }> }) {
  if (!items.length) {
    return <p className="pixel-note mt-3">No data yet.</p>;
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
    return <span className="text-[var(--color-ink-muted)]">none</span>;
  }
  return (
    <div className="flex flex-wrap gap-2">
      {values.map((value) => (
        <span className="pixel-tag" key={value}>
          {value}
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
    return <p className="pixel-note mt-3">No action proposal records for this trace.</p>;
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
            <span className="pixel-tag">executable={String(proposal.executable)}</span>
          </div>
          <p className="mt-2 text-[var(--color-ink-soft)]">{proposal.summary || "No summary provided."}</p>
          <div className="mt-3 grid gap-2 md:grid-cols-2">
            <p className="text-[var(--color-ink-soft)]">action {proposal.action_type || "unknown"}</p>
            <p className="text-[var(--color-ink-soft)]">risk {proposal.risk_level || "unknown"}</p>
            <p className="break-all text-[var(--color-ink-soft)] md:col-span-2">
              idempotency {proposal.idempotency_key || "missing"}
            </p>
          </div>
          {proposal.validation_warnings.length ? (
            <div className="mt-3">
              <p className="pixel-label mb-2">validation warnings</p>
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
        No trace selected.
      </div>
    );
  }
  return (
    <div className="pixel-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="pixel-label">trace detail</p>
          <h3 className="pixel-title mt-2 text-[1rem] text-[var(--color-ink)]">{trace.approval_id || trace.trace_id}</h3>
          <p className="mt-1 text-xs text-[var(--color-ink-muted)]">{trace.trace_id}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <span className="pixel-tag">{trace.approval_type || "unknown"}</span>
          <button className="ui-button" disabled={auditLoading} onClick={onDownloadAuditPackage} type="button">
            {auditLoading ? "Preparing audit package..." : "Download audit package"}
          </button>
        </div>
      </div>

      <div className="mt-4 grid gap-3 text-sm md:grid-cols-2">
        <div>
          <p className="pixel-label">request</p>
          <p className="mt-2 text-[var(--color-ink-soft)]">
            {trace.requester || "unknown"} / {trace.department || "unknown"}
          </p>
          <p className="text-[var(--color-ink-soft)]">
            {trace.vendor || "unknown vendor"} / {trace.cost_center || "unknown cost center"}
          </p>
          <p className="text-[var(--color-ink-soft)]">
            {trace.amount ?? "unknown"} {trace.currency || ""}
          </p>
        </div>
        <div>
          <p className="pixel-label">recommendation</p>
          <p className="mt-2 text-[var(--color-ink-soft)]">{trace.recommendation_status || "unknown"}</p>
          <p className="text-[var(--color-ink-soft)]">confidence {trace.recommendation_confidence.toFixed(2)}</p>
          <p className="text-[var(--color-ink-soft)]">review {trace.review_status || "unknown"}</p>
        </div>
      </div>

      <div className="mt-4 space-y-4 text-sm">
        <div>
          <p className="pixel-label mb-2">missing information</p>
          <ValueList values={trace.missing_information} />
        </div>
        <div>
          <p className="pixel-label mb-2">risk flags</p>
          <ValueList values={trace.risk_flags} />
        </div>
        <div>
          <p className="pixel-label mb-2">guard warnings</p>
          <ValueList values={trace.guard_warnings} />
        </div>
        <div>
          <p className="pixel-label mb-2">proposal action types</p>
          <ValueList values={trace.proposal_action_types} />
        </div>
        <div>
          <p className="pixel-label mb-2">proposal statuses</p>
          <ValueList values={trace.proposal_statuses} />
        </div>
        <div>
          <p className="pixel-label mb-2">blocked proposal ids</p>
          <ValueList values={trace.blocked_proposal_ids} />
        </div>
        <div>
          <p className="pixel-label mb-2">rejected proposal ids</p>
          <ValueList values={trace.rejected_proposal_ids} />
        </div>
        <div>
          <p className="pixel-label mb-2">context source ids</p>
          <ValueList values={trace.context_source_ids} />
        </div>
        <div>
          <p className="pixel-label mb-2">action proposal records</p>
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
          <p className="pixel-label">local audit workspace</p>
          <h3 className="pixel-title mt-2 text-[1rem] text-[var(--color-ink)]">Saved audit packages</h3>
          <p className="mt-2 max-w-3xl text-sm text-[var(--color-ink-soft)]">
            Saved audit packages and reviewer notes are local review artifacts. They do not execute ERP actions.
          </p>
        </div>
        <button className="ui-button" disabled={!selectedPackage || saving} onClick={onDownloadPackage} type="button">
          Download saved package
        </button>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <label className="text-sm">
          <span className="pixel-label">title</span>
          <input className="pixel-field mt-2 px-3 py-2" onChange={(event) => onTitleChange(event.target.value)} value={title} />
        </label>
        <label className="text-sm">
          <span className="pixel-label">created by</span>
          <input className="pixel-field mt-2 px-3 py-2" onChange={(event) => onCreatedByChange(event.target.value)} value={createdBy} />
        </label>
        <label className="text-sm">
          <span className="pixel-label">description</span>
          <input className="pixel-field mt-2 px-3 py-2" onChange={(event) => onDescriptionChange(event.target.value)} value={description} />
        </label>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <button className="ui-button" disabled={saving} onClick={onSaveSelected} type="button">
          Save selected trace package
        </button>
        <button className="ui-button" disabled={saving} onClick={onSaveFiltered} type="button">
          Save filtered package
        </button>
      </div>

      <div className="mt-5 grid gap-4 xl:grid-cols-[minmax(280px,0.8fr)_minmax(420px,1.2fr)]">
        <div>
          <p className="pixel-label">saved packages</p>
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
                      <p className="mt-1 text-xs text-[var(--color-ink-muted)]">{item.created_at || "unknown date"}</p>
                    </div>
                    <span className="pixel-tag">{item.note_count} notes</span>
                  </div>
                </button>
              ))
            ) : (
              <p className="pixel-note">No saved audit packages yet.</p>
            )}
          </div>
        </div>

        <div className="pixel-card-soft p-4">
          {selectedPackage ? (
            <>
              <p className="pixel-label">package detail</p>
              <h4 className="pixel-title mt-2 text-[0.95rem]">{selectedPackage.title}</h4>
              <p className="mt-2 break-all text-xs text-[var(--color-ink-muted)]">{selectedPackage.package_id}</p>
              <p className="mt-3 text-sm text-[var(--color-ink-soft)]">{selectedPackage.description || "No description."}</p>
              <div className="mt-3 grid gap-2 text-sm md:grid-cols-2">
                <p className="text-[var(--color-ink-soft)]">traces {selectedPackage.trace_ids.length}</p>
                <p className="text-[var(--color-ink-soft)]">proposals {selectedPackage.proposal_record_ids.length}</p>
                <p className="break-all text-[var(--color-ink-soft)] md:col-span-2">hash {selectedPackage.package_hash}</p>
              </div>

              <div className="mt-5">
                <p className="pixel-label">reviewer notes</p>
                <div className="mt-3 space-y-2">
                  {notes.length ? (
                    notes.map((note) => (
                      <div className="border-t border-[var(--color-line)] pt-3 text-sm" key={note.note_id}>
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="text-[var(--color-ink)]">{note.author || "local_reviewer"}</span>
                          <span className="pixel-tag">{note.note_type}</span>
                        </div>
                        <p className="mt-2 text-[var(--color-ink-soft)]">{note.body}</p>
                      </div>
                    ))
                  ) : (
                    <p className="pixel-note">No reviewer notes yet.</p>
                  )}
                </div>
              </div>

              <div className="mt-5 grid gap-3 md:grid-cols-[minmax(120px,0.4fr)_minmax(120px,0.4fr)_minmax(220px,1fr)]">
                <input className="pixel-field px-3 py-2" onChange={(event) => onNoteAuthorChange(event.target.value)} placeholder="Author" value={noteAuthor} />
                <select className="pixel-field px-3 py-2" onChange={(event) => onNoteTypeChange(event.target.value)} value={noteType}>
                  <option value="general">general</option>
                  <option value="risk">risk</option>
                  <option value="missing_info">missing_info</option>
                  <option value="policy_friction">policy_friction</option>
                  <option value="reviewer_decision">reviewer_decision</option>
                  <option value="follow_up">follow_up</option>
                </select>
                <input className="pixel-field px-3 py-2" onChange={(event) => onNoteBodyChange(event.target.value)} placeholder="Local reviewer note" value={noteBody} />
              </div>
              <button className="ui-button mt-3" disabled={saving || !noteBody.trim()} onClick={onAppendNote} type="button">
                Add local note
              </button>

              <div className="mt-6 border-t border-[var(--color-line)] pt-5">
                <p className="pixel-label">local simulation sandbox</p>
                <p className="mt-2 text-sm text-[var(--color-ink-soft)]">
                  This is a local simulation only. It does not execute an ERP action.
                </p>
                <div className="mt-4 grid gap-3 md:grid-cols-[minmax(220px,1fr)_minmax(140px,0.5fr)_minmax(220px,1fr)]">
                  <select
                    className="pixel-field px-3 py-2"
                    onChange={(event) => onSimulationProposalIdChange(event.target.value)}
                    value={simulationProposalId}
                  >
                    <option value="">Select proposal record</option>
                    {selectedPackage.proposal_record_ids.map((proposalId) => (
                      <option key={proposalId} value={proposalId}>
                        {proposalId}
                      </option>
                    ))}
                  </select>
                  <input
                    className="pixel-field px-3 py-2"
                    onChange={(event) => onSimulationRequestedByChange(event.target.value)}
                    placeholder="Requested by"
                    value={simulationRequestedBy}
                  />
                  <input
                    className="pixel-field px-3 py-2"
                    onChange={(event) => onSimulationNoteChange(event.target.value)}
                    placeholder="Simulation note"
                    value={simulationNote}
                  />
                </div>
                <label className="mt-3 flex items-center gap-2 text-sm text-[var(--color-ink-soft)]">
                  <input
                    checked={simulationConfirmNoWrite}
                    onChange={(event) => onSimulationConfirmNoWriteChange(event.target.checked)}
                    type="checkbox"
                  />
                  Confirm this is local dry-run only and no ERP write will be attempted.
                </label>
                <button
                  className="ui-button mt-3"
                  disabled={saving || !selectedPackage.proposal_record_ids.length || !simulationProposalId || !simulationConfirmNoWrite}
                  onClick={onRunSimulation}
                  type="button"
                >
                  Run local simulation
                </button>

                {simulationRecord ? (
                  <div className="pixel-card-soft mt-4 p-3 text-sm">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-[var(--color-ink)]">{simulationRecord.status}</p>
                        <p className="mt-1 break-all text-xs text-[var(--color-ink-muted)]">{simulationRecord.simulation_id}</p>
                      </div>
                      <span className="pixel-tag">simulated_only={String(simulationRecord.simulated_only)}</span>
                      <span className="pixel-tag">erp_write_executed={String(simulationRecord.erp_write_executed)}</span>
                    </div>
                    <pre className="mt-3 overflow-auto whitespace-pre-wrap text-xs text-[var(--color-ink-soft)]">
                      {JSON.stringify(simulationRecord.output_preview, null, 2)}
                    </pre>
                    {simulationRecord.validation_warnings.length ? (
                      <div className="mt-3">
                        <p className="pixel-label mb-2">validation warnings</p>
                        <ValueList values={simulationRecord.validation_warnings} />
                      </div>
                    ) : null}
                    {simulationRecord.blocked_reasons.length ? (
                      <div className="mt-3">
                        <p className="pixel-label mb-2">blocked reasons</p>
                        <ValueList values={simulationRecord.blocked_reasons} />
                      </div>
                    ) : null}
                    <p className="mt-3 text-[var(--color-ink-soft)]">{simulationRecord.non_action_statement}</p>
                  </div>
                ) : null}
              </div>
            </>
          ) : (
            <p className="pixel-note">Select a saved package to review notes and export the saved snapshot.</p>
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
  const [packageTitle, setPackageTitle] = useState("ERP approval audit package");
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
          setError(isApiError(caught, "Unable to load ERP approval insights."));
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
      .catch((caught) => setError(isApiError(caught, "Unable to load saved ERP approval audit packages.")));
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
      .catch((caught) => setError(isApiError(caught, "Unable to load ERP approval trace detail.")))
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
          setError(isApiError(caught, "Unable to load ERP approval action proposal records."));
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
      .catch((caught) => setError(isApiError(caught, "Unable to export ERP approval traces as JSON.")))
      .finally(() => setExporting(false));
  };

  const exportCsv = () => {
    setExporting(true);
    setError("");
    void exportErpApprovalTracesCsv({ ...query, limit: 500 })
      .then((payload) => downloadText("erp-approval-traces.csv", payload, "text/csv"))
      .catch((caught) => setError(isApiError(caught, "Unable to export ERP approval traces as CSV.")))
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
      .catch((caught) => setError(isApiError(caught, "Unable to download ERP approval audit package.")))
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
      .catch((caught) => setError(isApiError(caught, "Unable to load saved audit package.")))
      .finally(() => setWorkspaceSaving(false));
  };

  const saveAuditWorkspacePackage = (traceIds: string[]) => {
    if (!traceIds.length) {
      setError("No ERP approval traces are selected for the local audit package.");
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
      .catch((caught) => setError(isApiError(caught, "Unable to save local audit package.")))
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
      .catch((caught) => setError(isApiError(caught, "Unable to save local reviewer note.")))
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
      .catch((caught) => setError(isApiError(caught, "Unable to download saved audit package.")))
      .finally(() => setWorkspaceSaving(false));
  };

  const runLocalSimulation = () => {
    if (!selectedPackage?.package_id || !simulationProposalId || !simulationConfirmNoWrite) {
      setError("Select a proposal record and confirm that this is local simulation only.");
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
      .catch((caught) => setError(isApiError(caught, "Unable to run local ERP approval action simulation.")))
      .finally(() => setWorkspaceSaving(false));
  };

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="panel flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4 pb-4 pt-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="pixel-label">management insights</p>
            <h3 className="pixel-title mt-2 text-[1rem] text-[var(--color-ink)]">
              Read-only ERP approval trace explorer
            </h3>
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="ui-button" disabled={loading} onClick={loadDashboard} type="button">
              {loading ? "Refreshing..." : "Refresh"}
            </button>
            <button className="ui-button" disabled={exporting} onClick={exportJson} type="button">
              Export JSON
            </button>
            <button className="ui-button" disabled={exporting} onClick={exportCsv} type="button">
              Export CSV
            </button>
          </div>
        </div>

        {error ? <div className="pixel-card-soft px-4 py-4 text-sm text-[var(--color-danger)]">{error}</div> : null}

        <section className="pixel-card-soft grid gap-3 p-4 md:grid-cols-5">
          <label className="text-sm">
            <span className="pixel-label">approval type</span>
            <select
              className="pixel-field mt-2 px-3 py-2"
              onChange={(event) => updateFilter("approval_type", event.target.value)}
              value={filters.approval_type}
            >
              <option value="">All</option>
              {APPROVAL_TYPES.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="pixel-label">recommendation</span>
            <select
              className="pixel-field mt-2 px-3 py-2"
              onChange={(event) => updateFilter("recommendation_status", event.target.value)}
              value={filters.recommendation_status}
            >
              <option value="">All</option>
              {RECOMMENDATION_STATUSES.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="pixel-label">review</span>
            <select
              className="pixel-field mt-2 px-3 py-2"
              onChange={(event) => updateFilter("review_status", event.target.value)}
              value={filters.review_status}
            >
              <option value="">All</option>
              {REVIEW_STATUSES.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm md:col-span-2">
            <span className="pixel-label">text query</span>
            <input
              className="pixel-field mt-2 px-3 py-2"
              onChange={(event) => updateFilter("text_query", event.target.value)}
              placeholder="Search traces"
              value={filters.text_query}
            />
          </label>
          <label className="flex items-center gap-2 text-sm text-[var(--color-ink-soft)]">
            <input
              checked={filters.high_risk_only}
              onChange={(event) => updateFilter("high_risk_only", event.target.checked)}
              type="checkbox"
            />
            High risk only
          </label>
          <button className="ui-button md:col-span-4 md:justify-self-start" onClick={() => setFilters(DEFAULT_FILTERS)} type="button">
            Clear filters
          </button>
        </section>

        <ConnectorDiagnosticsPanel />

        {!summary || loading ? (
          <div className="pixel-card-soft px-4 py-4 text-sm text-[var(--color-ink-soft)]">
            {loading ? "Loading ERP approval insights..." : "No ERP approval traces yet."}
          </div>
        ) : summary.total_traces <= 0 ? (
          <div className="pixel-card-soft px-4 py-4 text-sm text-[var(--color-ink-soft)]">
            No ERP approval traces yet.
          </div>
        ) : (
          <>
            <section className="grid gap-4 md:grid-cols-4">
              <div className="pixel-card p-4">
                <p className="pixel-label">total traces</p>
                <p className="pixel-title mt-3 text-[1.6rem] text-[var(--color-ink)]">{summary.total_traces}</p>
              </div>
              <div className="pixel-card p-4">
                <p className="pixel-label">filtered traces</p>
                <p className="pixel-title mt-3 text-[1.6rem] text-[var(--color-ink)]">{traces.length}</p>
              </div>
              <div className="pixel-card p-4">
                <p className="pixel-label">human review</p>
                <p className="pixel-title mt-3 text-[1.6rem] text-[var(--color-ink)]">
                  {summary.human_review_required_count}
                </p>
              </div>
              <div className="pixel-card p-4">
                <p className="pixel-label">blocked / rejected proposals</p>
                <p className="pixel-title mt-3 text-[1.6rem] text-[var(--color-ink)]">
                  {summary.blocked_proposal_count + summary.rejected_proposal_count}
                </p>
              </div>
            </section>

            <section className="grid gap-4 lg:grid-cols-2">
              <div className="pixel-card p-4">
                <p className="pixel-label">recommendation status</p>
                <CountList counts={summary.by_recommendation_status} />
              </div>
              <div className="pixel-card p-4">
                <p className="pixel-label">review status</p>
                <CountList counts={summary.by_review_status} />
              </div>
              <div className="pixel-card p-4">
                <p className="pixel-label">missing information</p>
                <TopList items={summary.top_missing_information} />
              </div>
              <div className="pixel-card p-4">
                <p className="pixel-label">proposal action types</p>
                <CountList counts={summary.proposal_action_type_counts} />
              </div>
            </section>

            <section>
              <p className="pixel-label">trend buckets</p>
              <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {(trends?.buckets ?? []).length ? (
                  trends?.buckets.map((bucket) => (
                    <div className="pixel-card p-3 text-sm" key={bucket.bucket}>
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-[var(--color-ink)]">{bucket.bucket}</span>
                        <span className="pixel-tag">{bucket.total_traces}</span>
                      </div>
                      <p className="mt-2 text-[var(--color-ink-soft)]">
                        human review {bucket.human_review_required_count} / guard downgrades {bucket.guard_downgrade_count}
                      </p>
                    </div>
                  ))
                ) : (
                  <p className="pixel-note">No trend buckets yet.</p>
                )}
              </div>
            </section>

            <section className="grid gap-4 xl:grid-cols-[minmax(320px,0.8fr)_minmax(420px,1.2fr)]">
              <div className="pixel-card p-4">
                <p className="pixel-label">trace list</p>
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
                            <p className="mt-1 text-xs text-[var(--color-ink-muted)]">{trace.created_at || "unknown date"}</p>
                          </div>
                          <span className="pixel-tag">{trace.recommendation_status || "unknown"}</span>
                        </div>
                        <p className="mt-2 text-xs text-[var(--color-ink-soft)]">
                          {trace.vendor || "unknown vendor"} / {trace.review_status || "unknown review"}
                        </p>
                      </button>
                    ))
                  ) : (
                    <p className="pixel-note">No ERP approval traces match the current filters.</p>
                  )}
                </div>
              </div>

              <div className="relative">
                {detailLoading ? (
                  <div className="absolute right-3 top-3 z-10 pixel-tag">Loading detail</div>
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
