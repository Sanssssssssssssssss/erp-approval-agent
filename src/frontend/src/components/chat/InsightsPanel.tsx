"use client";

import { useEffect, useMemo, useState } from "react";

import { ApiConnectionError, getErpApprovalAnalyticsSummary } from "@/lib/api";
import type { ErpApprovalAnalyticsSummary } from "@/lib/api";

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

export function InsightsPanel() {
  const [summary, setSummary] = useState<ErpApprovalAnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadSummary = () => {
    setLoading(true);
    setError("");
    void getErpApprovalAnalyticsSummary()
      .then(setSummary)
      .catch((caught) => setError(caught instanceof ApiConnectionError ? caught.message : "Unable to load ERP approval insights."))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    void getErpApprovalAnalyticsSummary()
      .then((payload) => {
        if (!cancelled) {
          setSummary(payload);
        }
      })
      .catch((caught) => {
        if (!cancelled) {
          setError(caught instanceof ApiConnectionError ? caught.message : "Unable to load ERP approval insights.");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="panel flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4 pb-4 pt-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="pixel-label">management insights</p>
            <h3 className="pixel-title mt-2 text-[1rem] text-[var(--color-ink)]">
              Read-only ERP approval trace summary
            </h3>
          </div>
          <button className="ui-button" disabled={loading} onClick={loadSummary} type="button">
            {loading ? "Refreshing..." : "Refresh"}
          </button>
        </div>

        {error ? <div className="pixel-card-soft px-4 py-4 text-sm text-[var(--color-danger)]">{error}</div> : null}

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
                <p className="pixel-label">human review</p>
                <p className="pixel-title mt-3 text-[1.6rem] text-[var(--color-ink)]">
                  {summary.human_review_required_count}
                </p>
              </div>
              <div className="pixel-card p-4">
                <p className="pixel-label">guard downgrades</p>
                <p className="pixel-title mt-3 text-[1.6rem] text-[var(--color-ink)]">
                  {summary.guard_downgrade_count}
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
          </>
        )}
      </div>
    </section>
  );
}
