"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Archive, CheckCircle2, FileText, RefreshCcw, ShieldCheck, TriangleAlert } from "lucide-react";

import { HitlRecommendationReviewCard } from "@/components/chat/HitlRecommendationReviewCard";
import { LlmContextLibraryPanel } from "@/components/chat/LlmContextLibraryPanel";
import type { ErpApprovalCaseTurnResponse } from "@/lib/api";
import { useChatStore, useSessionStore } from "@/lib/store";

import { displayLabel, object, records, text } from "./caseInsightUtils";

const ERP_RECOMMENDATION_REVIEW_CAPABILITY_ID = "erp_approval_recommendation_review";
const ERP_RECOMMENDATION_REVIEW_TYPE = "erp_recommendation_review";

function prettyJson(value: Record<string, unknown> | null | undefined) {
  return JSON.stringify(value ?? {}, null, 2);
}

function isErpRecommendationReviewRequest(
  pendingHitl: ReturnType<typeof useChatStore>["pendingHitl"]
) {
  if (!pendingHitl) return false;
  const proposedInput = pendingHitl.proposed_input as Record<string, unknown> | null | undefined;
  return (
    pendingHitl.capability_id === ERP_RECOMMENDATION_REVIEW_CAPABILITY_ID ||
    proposedInput?.review_type === ERP_RECOMMENDATION_REVIEW_TYPE ||
    pendingHitl.display_name.includes("ERP 审批建议")
  );
}

function EvidenceList({
  empty,
  icon,
  items,
  title
}: {
  empty: string;
  icon: ReactNode;
  items: Array<Record<string, unknown>>;
  title: string;
}) {
  return (
    <section className="pixel-card-soft p-4">
      <div className="mb-3 flex items-center gap-2">
        <span className="pixel-tag">{icon}</span>
        <p className="pixel-label">{title}</p>
      </div>
      {items.length ? (
        <div className="space-y-3">
          {items.slice(0, 16).map((item, index) => (
            <article className="rounded-[10px] border border-[var(--color-line)] px-3 py-3 text-sm" key={`${title}-${text(item.source_id, String(index))}`}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-[var(--color-ink)]">
                  {text(item.title, text(item.source_id, `材料 ${index + 1}`))}
                </span>
                {item.record_type ? <span className="pixel-tag">{String(item.record_type)}</span> : null}
              </div>
              <p className="mt-2 break-all text-xs text-[var(--color-ink-muted)]">
                {text(item.source_id, "没有 source_id")}
              </p>
              {item.reason || item.why_failed ? (
                <p className="mt-2 text-[var(--color-ink-soft)]">{text(item.reason, text(item.why_failed, ""))}</p>
              ) : null}
            </article>
          ))}
        </div>
      ) : (
        <p className="text-sm text-[var(--color-ink-soft)]">{empty}</p>
      )}
    </section>
  );
}

function CaseEvidenceOverview({ turn }: { turn?: ErpApprovalCaseTurnResponse | null }) {
  if (!turn) {
    return (
      <section className="pixel-card p-5 text-center">
        <ShieldCheck className="mx-auto text-[var(--color-ink-muted)]" size={30} />
        <h3 className="mt-3 text-[1rem] font-semibold text-[var(--color-ink)]">等待创建审批案件</h3>
        <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-[var(--color-ink-soft)]">
          在“案件工作台”里像聊天一样描述案件或提交材料。创建后，这里会按案件展示已接受材料、被退回材料、制度失败和案卷预览。
        </p>
      </section>
    );
  }

  const state = turn.case_state;
  const accepted = records(state.accepted_evidence);
  const rejected = records(state.rejected_evidence);
  const failures = records(state.policy_failures);
  const patch = object(turn.patch);
  const latestAccepted = records(patch.accepted_evidence);
  const latestRejected = records(patch.rejected_evidence);
  const latestFailures = records(patch.policy_failures);

  return (
    <>
      <section className="pixel-card p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="pixel-label">当前案卷</p>
            <h3 className="mt-2 text-xl font-semibold text-[var(--color-ink)]">{state.approval_id || state.case_id}</h3>
            <p className="pixel-note mt-2">
              {displayLabel(state.approval_type)} / {displayLabel(state.stage)} / 案卷 v{state.dossier_version} / 第 {state.turn_count} 轮
            </p>
          </div>
          <span className="pixel-tag">{turn.non_action_statement}</span>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-4">
          <div className="insight-tile">
            <p className="pixel-label">已接受</p>
            <p className="mt-1 text-lg font-semibold text-[var(--color-ink)]">{accepted.length}</p>
          </div>
          <div className="insight-tile">
            <p className="pixel-label">被退回</p>
            <p className="mt-1 text-lg font-semibold text-[var(--color-ink)]">{rejected.length}</p>
          </div>
          <div className="insight-tile">
            <p className="pixel-label">制度失败</p>
            <p className="mt-1 text-lg font-semibold text-[var(--color-ink)]">{failures.length}</p>
          </div>
          <div className="insight-tile">
            <p className="pixel-label">缺口</p>
            <p className="mt-1 text-lg font-semibold text-[var(--color-ink)]">{state.missing_items.length}</p>
          </div>
        </div>
      </section>

      <section className="pixel-card p-4">
        <p className="pixel-label">本轮案卷变化</p>
        <div className="mt-3 grid gap-3 lg:grid-cols-3">
          <EvidenceList empty="本轮没有新接受材料。" icon={<CheckCircle2 size={14} />} items={latestAccepted} title="本轮接受" />
          <EvidenceList empty="本轮没有退回材料。" icon={<TriangleAlert size={14} />} items={latestRejected} title="本轮退回" />
          <EvidenceList empty="本轮没有新的制度失败。" icon={<ShieldCheck size={14} />} items={latestFailures} title="本轮制度失败" />
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-2">
        <EvidenceList empty="还没有接受任何材料。" icon={<CheckCircle2 size={14} />} items={accepted} title="已接受材料" />
        <EvidenceList empty="还没有被退回材料。" icon={<TriangleAlert size={14} />} items={rejected} title="被退回材料" />
      </div>

      <EvidenceList empty="暂无制度失败记录。" icon={<ShieldCheck size={14} />} items={failures} title="制度失败 / 退回原因" />

      <section className="pixel-card p-4">
        <div className="mb-3 flex items-center gap-2">
          <span className="pixel-tag"><FileText size={14} /></span>
          <p className="pixel-label">案卷预览</p>
        </div>
        <details className="case-agent-details" open>
          <summary>查看 dossier.md 当前内容</summary>
          <pre className="mt-3 max-h-[460px] overflow-auto whitespace-pre-wrap rounded-[8px] border border-[var(--color-line)] bg-[rgba(10,13,17,0.38)] p-4 text-sm leading-6 text-[var(--color-ink-soft)]">
            {turn.dossier?.trim() || "案卷还没有写入内容。"}
          </pre>
        </details>
      </section>
    </>
  );
}

export function AssetsPanel({ turn }: { turn?: ErpApprovalCaseTurnResponse | null }) {
  const {
    checkpoints,
    pendingHitl,
    hitlAudit,
    assetsLoading,
    isStreaming,
    refreshAssets,
    resumeCheckpoint,
    submitHitlDecision
  } = useChatStore();
  const { currentSessionId } = useSessionStore();
  const isErpRecommendationReview = isErpRecommendationReviewRequest(pendingHitl);
  const hitlReason = isErpRecommendationReview
    ? "请复核 Agent 的 ERP 审批建议。接受这个 HITL 请求只代表接受或编辑建议，不会执行任何 ERP 动作。"
    : pendingHitl?.reason ?? "";
  const [editedInputText, setEditedInputText] = useState("{}");
  const [editError, setEditError] = useState("");

  useEffect(() => {
    setEditedInputText(prettyJson(pendingHitl?.proposed_input));
    setEditError("");
  }, [pendingHitl]);

  const latestCheckpoint = useMemo(
    () => checkpoints.find((item) => item.resume_eligible) ?? null,
    [checkpoints]
  );
  const showSessionArtifacts = Boolean(turn);

  const handleEditAndContinue = async () => {
    if (!pendingHitl) return;
    try {
      const parsed = JSON.parse(editedInputText) as Record<string, unknown>;
      setEditError("");
      await submitHitlDecision(pendingHitl.checkpoint_id, "edit", parsed);
    } catch (error) {
      setEditError(error instanceof Error ? `JSON 格式不正确：${error.message}` : "JSON 格式不正确");
    }
  };

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="panel flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4 pb-4 pt-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="pixel-label">证据库</p>
            <h3 className="pixel-title mt-2 text-[1rem] text-[var(--color-ink)]">
              案卷材料、退回原因和人工复核
            </h3>
            <p className="pixel-note mt-2 max-w-3xl">
              这里按当前案卷组织材料。模型上下文和 Markdown 文件只放在底部“开发者调试”，避免普通用户一进来就看到调试噪音。
            </p>
          </div>
          <button className="ui-button" disabled={assetsLoading || isStreaming} onClick={() => void refreshAssets()} type="button">
            <RefreshCcw size={15} />
            {assetsLoading ? "正在刷新..." : "刷新"}
          </button>
        </div>

        {!currentSessionId ? (
          <div className="pixel-card-soft px-4 py-4 text-sm text-[var(--color-ink-soft)]">
            还没有活动审批会话。
          </div>
        ) : null}

        <CaseEvidenceOverview turn={turn} />

        {showSessionArtifacts ? (
        <section className="pixel-card p-4">
          <p className="pixel-label">人工复核</p>
          <p className="pixel-note mt-2">
            这里只处理本地 reviewer 对 Agent memo/建议的接受、编辑或打回，不会通过、驳回、付款或路由任何 ERP 单据。
          </p>
          {pendingHitl ? (
            isErpRecommendationReview ? (
              <HitlRecommendationReviewCard
                className="mt-4 mb-0 max-h-none"
                editError={editError}
                editedInputText={editedInputText}
                isStreaming={isStreaming}
                onAccept={() => void submitHitlDecision(pendingHitl.checkpoint_id, "approve")}
                onEditSubmit={() => void handleEditAndContinue()}
                onEditTextChange={setEditedInputText}
                onReject={() => void submitHitlDecision(pendingHitl.checkpoint_id, "reject")}
                pendingHitl={pendingHitl}
              />
            ) : (
              <div className="pixel-card-soft mt-4 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="pixel-tag">待处理</span>
                  <span className="pixel-tag">风险 {pendingHitl.risk_level}</span>
                  <span className="mono text-[0.92rem] text-[var(--color-ink-soft)]">
                    请求 {pendingHitl.request_id || "-"}
                  </span>
                </div>
                <h4 className="pixel-title mt-3 text-[1rem] text-[var(--color-ink)]">
                  {pendingHitl.display_name}
                </h4>
                <p className="pixel-note mt-2">{hitlReason}</p>
                <div className="mt-4 flex flex-wrap gap-3">
                  <button
                    className="ui-button ui-button-primary"
                    disabled={isStreaming}
                    onClick={() => void submitHitlDecision(pendingHitl.checkpoint_id, "approve")}
                    type="button"
                  >
                    通过本地复核
                  </button>
                  <button
                    className="ui-button"
                    disabled={isStreaming}
                    onClick={() => void submitHitlDecision(pendingHitl.checkpoint_id, "reject")}
                    type="button"
                  >
                    打回
                  </button>
                </div>
              </div>
            )
          ) : (
            <div className="pixel-card-soft mt-4 px-4 py-4 text-sm text-[var(--color-ink-soft)]">
              当前没有待处理的 HITL 复核请求。
            </div>
          )}

          {hitlAudit.length ? (
            <details className="case-agent-details mt-4">
              <summary>查看历史人工复核记录</summary>
              <div className="mt-3 space-y-3">
                {hitlAudit.map((entry) => (
                  <div className="pixel-card-soft p-4" key={entry.request.request_id || entry.request.checkpoint_id}>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="pixel-tag">{entry.request.status || "pending"}</span>
                      <span className="pixel-tag">{entry.request.capability_id}</span>
                      <span className="mono text-[0.92rem] text-[var(--color-ink-soft)]">
                        checkpoint {entry.request.checkpoint_id}
                      </span>
                    </div>
                    <div className="mt-3 grid gap-2 text-sm text-[var(--color-ink-soft)] md:grid-cols-2">
                      <p>request_id: {entry.request.request_id || "-"}</p>
                      <p>risk_level: {entry.request.risk_level}</p>
                      <p>decision: {entry.decision?.decision || "-"}</p>
                      <p>actor: {entry.decision?.actor_id || "-"}</p>
                    </div>
                  </div>
                ))}
              </div>
            </details>
          ) : null}
        </section>
        ) : null}

        {showSessionArtifacts ? (
        <section className="pixel-card p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="pixel-label">恢复点</p>
              <p className="pixel-note mt-2">Checkpoint 只用于恢复本地审批线程，不代表 ERP 动作。</p>
            </div>
            {latestCheckpoint ? (
              <button
                className="ui-button"
                disabled={isStreaming}
                onClick={() => void resumeCheckpoint(latestCheckpoint.checkpoint_id)}
                type="button"
              >
                <Archive size={15} />
                恢复最新 checkpoint
              </button>
            ) : null}
          </div>
          <details className="case-agent-details mt-4">
            <summary>查看 checkpoint 列表</summary>
            <div className="mt-3 space-y-3">
              {checkpoints.length ? (
                checkpoints.map((item) => (
                  <div className="pixel-card-soft p-4" key={item.checkpoint_id}>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="pixel-tag">{item.state_label}</span>
                      {item.is_latest ? <span className="pixel-tag">最新</span> : null}
                      <span className="mono text-[0.92rem] text-[var(--color-ink-soft)]">{item.checkpoint_id}</span>
                    </div>
                    {item.resume_eligible ? (
                      <button
                        className="ui-button mt-3"
                        disabled={isStreaming}
                        onClick={() => void resumeCheckpoint(item.checkpoint_id)}
                        type="button"
                      >
                        恢复这个 checkpoint
                      </button>
                    ) : null}
                  </div>
                ))
              ) : (
                <div className="pixel-card-soft px-4 py-4 text-sm text-[var(--color-ink-soft)]">
                  这个审批会话还没有 checkpoint。
                </div>
              )}
            </div>
          </details>
        </section>
        ) : null}

        <section className="pixel-card p-4">
          <details className="case-agent-details">
            <summary>开发者调试：LLM Markdown 与当前上下文</summary>
            <div className="mt-4">
              <LlmContextLibraryPanel compact />
            </div>
          </details>
        </section>
      </div>
    </section>
  );
}
