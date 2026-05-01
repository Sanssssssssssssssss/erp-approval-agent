"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiConnectionError,
  getErpApprovalConnectorConfig,
  getErpApprovalConnectorHealth,
  getErpApprovalConnectorReplayCoverage,
  listErpApprovalConnectorProfiles,
  listErpApprovalConnectorReplayFixtures,
  replayErpApprovalConnectorFixture
} from "@/lib/api";
import type {
  ErpConnectorConfigResponse,
  ErpConnectorHealthSummary,
  ErpConnectorProviderProfileSummary,
  ErpConnectorReplayCoverageSummary,
  ErpConnectorReplayFixtureInfo,
  ErpConnectorReplayRecord
} from "@/lib/api";

function apiError(caught: unknown, fallback: string) {
  return caught instanceof ApiConnectionError ? caught.message : fallback;
}

function MiniList({ values }: { values: string[] }) {
  if (!values.length) {
    return <span className="text-[var(--color-ink-muted)]">无</span>;
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

function CountList({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts);
  if (!entries.length) {
    return <span className="text-[var(--color-ink-muted)]">无</span>;
  }
  return (
    <div className="flex flex-wrap gap-2">
      {entries.map(([label, count]) => (
        <span className="pixel-tag" key={label}>
          {label} {count}
        </span>
      ))}
    </div>
  );
}

function configValue(config: ErpConnectorConfigResponse | null, key: string) {
  const value = config?.config?.[key];
  if (value === undefined || value === null || value === "") {
    return "无";
  }
  return String(value);
}

export function ConnectorDiagnosticsPanel() {
  const [config, setConfig] = useState<ErpConnectorConfigResponse | null>(null);
  const [health, setHealth] = useState<ErpConnectorHealthSummary | null>(null);
  const [profiles, setProfiles] = useState<ErpConnectorProviderProfileSummary[]>([]);
  const [fixtures, setFixtures] = useState<ErpConnectorReplayFixtureInfo[]>([]);
  const [coverage, setCoverage] = useState<ErpConnectorReplayCoverageSummary | null>(null);
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
      listErpApprovalConnectorReplayFixtures(),
      getErpApprovalConnectorReplayCoverage()
    ])
      .then(([configPayload, healthPayload, profilePayload, fixturePayload, coveragePayload]) => {
        setConfig(configPayload);
        setHealth(healthPayload);
        setProfiles(profilePayload);
        setFixtures(fixturePayload);
        setCoverage(coveragePayload);
        setSelectedFixtureName((current) =>
          fixturePayload.some((fixture) => fixture.fixture_name === current) ? current : fixturePayload[0]?.fixture_name ?? ""
        );
      })
      .catch((caught) => setError(apiError(caught, "无法加载 ERP connector 诊断信息。")))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => refreshDiagnostics(), [refreshDiagnostics]);

  const replayFixture = () => {
    if (!selectedFixture) {
      setError("请选择一个本地 connector fixture。");
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
      .catch((caught) => setError(apiError(caught, "无法回放本地 connector fixture。")))
      .finally(() => setReplayLoading(false));
  };

  return (
    <section className="pixel-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="pixel-label">connector 诊断</p>
          <h3 className="pixel-title mt-2 text-[1rem] text-[var(--color-ink)]">只读 connector 就绪情况</h3>
          <p className="mt-2 max-w-3xl text-sm text-[var(--color-ink-soft)]">
            Fixture replay 只在本地回放映射，不连接 ERP 系统。
          </p>
        </div>
        <button className="ui-button" disabled={loading} onClick={refreshDiagnostics} type="button">
          {loading ? "正在刷新..." : "刷新诊断"}
        </button>
      </div>

      {error ? <div className="pixel-card-soft mt-4 px-4 py-3 text-sm text-[var(--color-danger)]">{error}</div> : null}

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <div className="pixel-card-soft p-4 text-sm">
          <p className="pixel-label">脱敏配置</p>
          <div className="mt-3 space-y-2 text-[var(--color-ink-soft)]">
            <p>provider {configValue(config, "provider")}</p>
            <p>已启用 {configValue(config, "enabled")}</p>
            <p>允许网络 {configValue(config, "allow_network")}</p>
            <p>认证类型 {configValue(config, "auth_type")}</p>
            <p className="break-all">认证环境变量 {configValue(config, "auth_env_var")}</p>
            <p>认证变量存在 {configValue(config, "auth_env_var_present")}</p>
            <p className="break-all">base URL {configValue(config, "base_url")}</p>
          </div>
        </div>

        <div className="pixel-card-soft p-4 text-sm">
          <p className="pixel-label">健康检查</p>
          <p className="mt-3 text-[var(--color-ink-soft)]">当前选择 {health?.selected_provider ?? "未知"}</p>
          <div className="mt-3 space-y-3">
            {(health?.diagnostics ?? []).map((diagnostic) => (
              <div className="border-t border-[var(--color-line)] pt-3" key={diagnostic.provider}>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[var(--color-ink)]">{diagnostic.provider}</span>
                  <span className="pixel-tag">{diagnostic.status}</span>
                </div>
                <p className="mt-2 text-[var(--color-ink-soft)]">
                  已启用={String(diagnostic.enabled)} 网络={String(diagnostic.allow_network)}
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

      <div className="pixel-card-soft mt-4 p-4 text-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="pixel-label">replay coverage matrix</p>
            <p className="mt-2 text-[var(--color-ink-soft)]">
              Coverage 只是本地 fixture replay，不是 live ERP integration test。
            </p>
          </div>
          <div className="grid grid-cols-3 gap-2 text-right">
            <div>
              <p className="pixel-label">总数</p>
              <p className="text-[var(--color-ink)]">{coverage?.total_items ?? 0}</p>
            </div>
            <div>
              <p className="pixel-label">通过</p>
              <p className="text-[var(--color-ink)]">{coverage?.passed_items ?? 0}</p>
            </div>
            <div>
              <p className="pixel-label">失败</p>
              <p className="text-[var(--color-ink)]">{coverage?.failed_items ?? 0}</p>
            </div>
          </div>
        </div>
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <div>
            <p className="pixel-label mb-2">按 provider</p>
            <CountList counts={coverage?.by_provider ?? {}} />
          </div>
          <div>
            <p className="pixel-label mb-2">按 operation</p>
            <CountList counts={coverage?.by_operation ?? {}} />
          </div>
        </div>
        <div className="mt-4 max-h-72 space-y-2 overflow-auto pr-2">
          {(coverage?.items ?? []).map((item) => (
            <div className="border-t border-[var(--color-line)] pt-3" key={`${item.provider}-${item.fixture_name}`}>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span className="text-[var(--color-ink)]">
                  {item.provider} / {item.operation}
                </span>
                <span className="pixel-tag">
                  {item.replay_status} / validation={String(item.validation_passed)}
                </span>
              </div>
              <p className="mt-1 break-all text-xs text-[var(--color-ink-muted)]">{item.fixture_name}</p>
              <p className="mt-2 text-[var(--color-ink-soft)]">记录数 {item.record_count}</p>
              {item.failed_checks.length ? (
                <div className="mt-2">
                  <p className="pixel-label mb-2">失败检查</p>
                  <MiniList values={item.failed_checks} />
                </div>
              ) : null}
              {item.warnings.length ? (
                <div className="mt-2">
                  <p className="pixel-label mb-2">警告</p>
                  <MiniList values={item.warnings} />
                </div>
              ) : null}
            </div>
          ))}
          {coverage && !coverage.items.length ? <p className="pixel-note">没有找到 connector replay fixtures。</p> : null}
        </div>
        {coverage?.non_action_statement ? (
          <p className="mt-3 text-[var(--color-ink-soft)]">{coverage.non_action_statement}</p>
        ) : null}
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
              <span className="pixel-label">审批 ID</span>
              <input className="pixel-field mt-2 px-3 py-2" onChange={(event) => setApprovalId(event.target.value)} value={approvalId} />
            </label>
            <label className="text-sm md:col-span-2 xl:col-span-1">
              <span className="pixel-label">correlation ID</span>
              <input
                className="pixel-field mt-2 px-3 py-2"
                onChange={(event) => setCorrelationId(event.target.value)}
                value={correlationId}
              />
            </label>
          </div>
          <button className="ui-button mt-3" disabled={replayLoading || !selectedFixture} onClick={replayFixture} type="button">
            {replayLoading ? "正在回放..." : "回放本地 fixture"}
          </button>
        </div>

        <div className="pixel-card-soft p-4 text-sm">
          <p className="pixel-label">回放结果</p>
          {replay ? (
            <div className="mt-3 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span className="text-[var(--color-ink)]">
                  {replay.provider} / {replay.operation}
                </span>
                <span className="pixel-tag">{replay.status}</span>
              </div>
              <div className="grid gap-2 md:grid-cols-3">
                <p className="text-[var(--color-ink-soft)]">记录数 {replay.record_count}</p>
                <p className="text-[var(--color-ink-soft)]">校验 {String(replay.validation.passed)}</p>
                <p className="text-[var(--color-ink-soft)]">network_accessed={String(replay.network_accessed)}</p>
              </div>
              <div>
                <p className="pixel-label mb-2">source IDs</p>
                <MiniList values={replay.source_ids} />
              </div>
              {replay.validation.failed_checks.length ? (
                <div>
                  <p className="pixel-label mb-2">失败检查</p>
                  <MiniList values={replay.validation.failed_checks} />
                </div>
              ) : null}
              {replay.warnings.length || replay.validation.warnings.length ? (
                <div>
                  <p className="pixel-label mb-2">警告</p>
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
            <p className="pixel-note mt-3">还没有运行 fixture replay。</p>
          )}
        </div>
      </div>
    </section>
  );
}
