"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiConnectionError,
  getErpApprovalConnectorConfig,
  getErpApprovalConnectorHealth,
  listErpApprovalConnectorProfiles,
  listErpApprovalConnectorReplayFixtures,
  replayErpApprovalConnectorFixture
} from "@/lib/api";
import type {
  ErpConnectorConfigResponse,
  ErpConnectorHealthSummary,
  ErpConnectorProviderProfileSummary,
  ErpConnectorReplayFixtureInfo,
  ErpConnectorReplayRecord
} from "@/lib/api";

function apiError(caught: unknown, fallback: string) {
  return caught instanceof ApiConnectionError ? caught.message : fallback;
}

function MiniList({ values }: { values: string[] }) {
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

function configValue(config: ErpConnectorConfigResponse | null, key: string) {
  const value = config?.config?.[key];
  if (value === undefined || value === null || value === "") {
    return "none";
  }
  return String(value);
}

export function ConnectorDiagnosticsPanel() {
  const [config, setConfig] = useState<ErpConnectorConfigResponse | null>(null);
  const [health, setHealth] = useState<ErpConnectorHealthSummary | null>(null);
  const [profiles, setProfiles] = useState<ErpConnectorProviderProfileSummary[]>([]);
  const [fixtures, setFixtures] = useState<ErpConnectorReplayFixtureInfo[]>([]);
  const [selectedFixtureName, setSelectedFixtureName] = useState("");
  const [approvalId, setApprovalId] = useState("PR-1001");
  const [correlationId, setCorrelationId] = useState("ui-connector-replay");
  const [replay, setReplay] = useState<ErpConnectorReplayRecord | null>(null);
  const [loading, setLoading] = useState(false);
  const [replayLoading, setReplayLoading] = useState(false);
  const [error, setError] = useState("");

  const selectedFixture = useMemo(
    () => fixtures.find((fixture) => fixture.fixture_name === selectedFixtureName) ?? fixtures[0] ?? null,
    [fixtures, selectedFixtureName]
  );

  const refreshDiagnostics = useCallback(() => {
    setLoading(true);
    setError("");
    void Promise.all([
      getErpApprovalConnectorConfig(),
      getErpApprovalConnectorHealth(),
      listErpApprovalConnectorProfiles(),
      listErpApprovalConnectorReplayFixtures()
    ])
      .then(([configPayload, healthPayload, profilePayload, fixturePayload]) => {
        setConfig(configPayload);
        setHealth(healthPayload);
        setProfiles(profilePayload);
        setFixtures(fixturePayload);
        setSelectedFixtureName((current) =>
          fixturePayload.some((fixture) => fixture.fixture_name === current) ? current : fixturePayload[0]?.fixture_name ?? ""
        );
      })
      .catch((caught) => setError(apiError(caught, "Unable to load ERP connector diagnostics.")))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => refreshDiagnostics(), [refreshDiagnostics]);

  const replayFixture = () => {
    if (!selectedFixture) {
      setError("Select a local connector fixture.");
      return;
    }
    setReplayLoading(true);
    setError("");
    void replayErpApprovalConnectorFixture({
      provider: selectedFixture.provider,
      operation: selectedFixture.operation,
      fixture_name: selectedFixture.fixture_name,
      approval_id: approvalId,
      correlation_id: correlationId
    })
      .then((payload) => setReplay(payload))
      .catch((caught) => setError(apiError(caught, "Unable to replay local connector fixture.")))
      .finally(() => setReplayLoading(false));
  };

  return (
    <section className="pixel-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="pixel-label">connector diagnostics</p>
          <h3 className="pixel-title mt-2 text-[1rem] text-[var(--color-ink)]">Read-only connector readiness</h3>
          <p className="mt-2 max-w-3xl text-sm text-[var(--color-ink-soft)]">
            Fixture replay is local-only. It does not connect to ERP systems.
          </p>
        </div>
        <button className="ui-button" disabled={loading} onClick={refreshDiagnostics} type="button">
          {loading ? "Refreshing..." : "Refresh diagnostics"}
        </button>
      </div>

      {error ? <div className="pixel-card-soft mt-4 px-4 py-3 text-sm text-[var(--color-danger)]">{error}</div> : null}

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <div className="pixel-card-soft p-4 text-sm">
          <p className="pixel-label">redacted config</p>
          <div className="mt-3 space-y-2 text-[var(--color-ink-soft)]">
            <p>provider {configValue(config, "provider")}</p>
            <p>enabled {configValue(config, "enabled")}</p>
            <p>allow network {configValue(config, "allow_network")}</p>
            <p>auth type {configValue(config, "auth_type")}</p>
            <p className="break-all">auth env var {configValue(config, "auth_env_var")}</p>
            <p>auth env present {configValue(config, "auth_env_var_present")}</p>
            <p className="break-all">base url {configValue(config, "base_url")}</p>
          </div>
        </div>

        <div className="pixel-card-soft p-4 text-sm">
          <p className="pixel-label">health</p>
          <p className="mt-3 text-[var(--color-ink-soft)]">selected {health?.selected_provider ?? "unknown"}</p>
          <div className="mt-3 space-y-3">
            {(health?.diagnostics ?? []).map((diagnostic) => (
              <div className="border-t border-[var(--color-line)] pt-3" key={diagnostic.provider}>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[var(--color-ink)]">{diagnostic.provider}</span>
                  <span className="pixel-tag">{diagnostic.status}</span>
                </div>
                <p className="mt-2 text-[var(--color-ink-soft)]">
                  enabled={String(diagnostic.enabled)} network={String(diagnostic.allow_network)}
                </p>
                {diagnostic.warnings.length ? (
                  <div className="mt-2">
                    <MiniList values={diagnostic.warnings} />
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>

        <div className="pixel-card-soft p-4 text-sm">
          <p className="pixel-label">provider profiles</p>
          <div className="mt-3 space-y-3">
            {profiles.map((profile) => (
              <div className="border-t border-[var(--color-line)] pt-3" key={profile.provider}>
                <p className="text-[var(--color-ink)]">{profile.display_name || profile.provider}</p>
                <p className="mt-1 break-all text-xs text-[var(--color-ink-muted)]">{profile.default_source_id_prefix}</p>
                <p className="mt-2 text-[var(--color-ink-soft)]">{profile.read_only_notes}</p>
                <div className="mt-2">
                  <MiniList values={profile.forbidden_methods} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(300px,0.8fr)_minmax(420px,1.2fr)]">
        <div className="pixel-card-soft p-4">
          <p className="pixel-label">fixture replay</p>
          <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-1">
            <label className="text-sm">
              <span className="pixel-label">fixture</span>
              <select
                className="pixel-field mt-2 px-3 py-2"
                onChange={(event) => setSelectedFixtureName(event.target.value)}
                value={selectedFixture?.fixture_name ?? ""}
              >
                {fixtures.map((fixture) => (
                  <option key={fixture.fixture_name} value={fixture.fixture_name}>
                    {fixture.provider} / {fixture.operation}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm">
              <span className="pixel-label">approval id</span>
              <input className="pixel-field mt-2 px-3 py-2" onChange={(event) => setApprovalId(event.target.value)} value={approvalId} />
            </label>
            <label className="text-sm md:col-span-2 xl:col-span-1">
              <span className="pixel-label">correlation id</span>
              <input
                className="pixel-field mt-2 px-3 py-2"
                onChange={(event) => setCorrelationId(event.target.value)}
                value={correlationId}
              />
            </label>
          </div>
          <button className="ui-button mt-3" disabled={replayLoading || !selectedFixture} onClick={replayFixture} type="button">
            {replayLoading ? "Replaying..." : "Replay local fixture"}
          </button>
        </div>

        <div className="pixel-card-soft p-4 text-sm">
          <p className="pixel-label">replay result</p>
          {replay ? (
            <div className="mt-3 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span className="text-[var(--color-ink)]">
                  {replay.provider} / {replay.operation}
                </span>
                <span className="pixel-tag">{replay.status}</span>
              </div>
              <div className="grid gap-2 md:grid-cols-3">
                <p className="text-[var(--color-ink-soft)]">records {replay.record_count}</p>
                <p className="text-[var(--color-ink-soft)]">validation {String(replay.validation.passed)}</p>
                <p className="text-[var(--color-ink-soft)]">network_accessed={String(replay.network_accessed)}</p>
              </div>
              <div>
                <p className="pixel-label mb-2">source ids</p>
                <MiniList values={replay.source_ids} />
              </div>
              {replay.validation.failed_checks.length ? (
                <div>
                  <p className="pixel-label mb-2">failed checks</p>
                  <MiniList values={replay.validation.failed_checks} />
                </div>
              ) : null}
              {replay.warnings.length || replay.validation.warnings.length ? (
                <div>
                  <p className="pixel-label mb-2">warnings</p>
                  <MiniList values={[...replay.warnings, ...replay.validation.warnings]} />
                </div>
              ) : null}
              <p className="text-[var(--color-ink-soft)]">{replay.non_action_statement}</p>
              <div className="space-y-2">
                {replay.records.map((record) => (
                  <div className="border-t border-[var(--color-line)] pt-3" key={record.source_id}>
                    <p className="text-[var(--color-ink)]">{record.title}</p>
                    <p className="mt-1 break-all text-xs text-[var(--color-ink-muted)]">{record.source_id}</p>
                    <p className="mt-2 text-[var(--color-ink-soft)]">{record.content}</p>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="pixel-note mt-3">No fixture replay has been run yet.</p>
          )}
        </div>
      </div>
    </section>
  );
}
