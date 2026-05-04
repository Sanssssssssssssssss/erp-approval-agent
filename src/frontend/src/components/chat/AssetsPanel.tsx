"use client";

import { useEffect, useMemo, useState } from "react";

import { HitlRecommendationReviewCard } from "@/components/chat/HitlRecommendationReviewCard";
import { LlmContextLibraryPanel } from "@/components/chat/LlmContextLibraryPanel";
import { useChatStore, useSessionStore } from "@/lib/store";

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

export function AssetsPanel() {
  const {
    checkpoints,
    pendingHitl,
    hitlAudit,
    mcpCapabilities,
    sessionContext,
    selectedContextTurn,
    derivedTurnMemories,
    assetsLoading,
    isStreaming,
    refreshAssets,
    triggerConsolidation,
    resumeCheckpoint,
    submitHitlDecision,
    excludeContextTurn
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
            <p className="pixel-label">证据</p>
            <h3 className="pixel-title mt-2 text-[1rem] text-[var(--color-ink)]">
              案件证据、模型上下文和人工复核材料
            </h3>
            <p className="pixel-note mt-2 max-w-3xl">
              普通用户先看 HITL 和案卷证据；调模型时再展开 LLM Markdown 与当前上下文。不展示任何真实 ERP 写动作。
            </p>
          </div>
          <button className="ui-button" disabled={assetsLoading || isStreaming} onClick={() => void refreshAssets()} type="button">
            {assetsLoading ? "正在刷新..." : "刷新"}
          </button>
        </div>

        {!currentSessionId ? (
          <div className="pixel-card-soft px-4 py-4 text-sm text-[var(--color-ink-soft)]">
            还没有活动审批会话。
          </div>
        ) : null}

        <LlmContextLibraryPanel compact />

        <section className="pixel-card p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="pixel-label">checkpoints</p>
              <p className="pixel-note mt-2">从已有审批线程 checkpoint 恢复。</p>
            </div>
            {latestCheckpoint ? (
              <button
                className="ui-button"
                disabled={isStreaming}
                onClick={() => void resumeCheckpoint(latestCheckpoint.checkpoint_id)}
                type="button"
              >
                恢复最新 checkpoint
              </button>
            ) : null}
          </div>
          <div className="mt-4 space-y-3">
            {checkpoints.length ? (
              checkpoints.map((item) => (
                <div className="pixel-card-soft p-4" key={item.checkpoint_id}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="pixel-tag">{item.state_label}</span>
                    {item.is_latest ? <span className="pixel-tag">最新</span> : null}
                    <span className="mono text-[0.92rem] text-[var(--color-ink-soft)]">{item.checkpoint_id}</span>
                  </div>
                  <div className="mt-3 grid gap-2 text-sm text-[var(--color-ink-soft)] md:grid-cols-2">
                    <p>thread_id: {item.thread_id}</p>
                    <p>session_id: {item.session_id || "-"}</p>
                    <p>run_id: {item.run_id}</p>
                    <p>创建时间: {item.created_at || "-"}</p>
                    <p>恢复来源: {item.source || "-"}</p>
                    <p>当前状态: {item.state_label}</p>
                  </div>
                  {item.resume_eligible ? (
                    <div className="mt-3">
                      <button
                        className="ui-button"
                        disabled={isStreaming}
                        onClick={() => void resumeCheckpoint(item.checkpoint_id)}
                        type="button"
                      >
                        恢复这个 checkpoint
                      </button>
                    </div>
                  ) : null}
                </div>
              ))
            ) : (
              <div className="pixel-card-soft px-4 py-4 text-sm text-[var(--color-ink-soft)]">
                这个审批会话还没有 checkpoint。
              </div>
            )}
          </div>
        </section>

        <section className="pixel-card p-4">
          <p className="pixel-label">HITL</p>
          <p className="pixel-note mt-2">
            {isErpRecommendationReview
              ? "需要复核 ERP 建议。这里只采用、编辑或拒绝 Agent 建议，不执行 ERP 审批动作。"
              : "待复核请求，以及最新请求和决策审计轨迹。"}
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
                <div className="mt-3 grid gap-2 text-sm text-[var(--color-ink-soft)] md:grid-cols-2">
                  <p>checkpoint_id: {pendingHitl.checkpoint_id}</p>
                  <p>请求时间: {pendingHitl.requested_at || "-"}</p>
                </div>
                <details className="hitl-payload-details mt-4">
                  <summary>查看审查 payload</summary>
                  <pre>{prettyJson(pendingHitl.proposed_input)}</pre>
                </details>
                <div className="mt-4 flex flex-wrap gap-3">
                  <button
                    className="ui-button ui-button-primary"
                    disabled={isStreaming}
                    onClick={() => void submitHitlDecision(pendingHitl.checkpoint_id, "approve")}
                    type="button"
                  >
                    通过复核
                  </button>
                  <button
                    className="ui-button"
                    disabled={isStreaming}
                    onClick={() => void submitHitlDecision(pendingHitl.checkpoint_id, "reject")}
                    type="button"
                  >
                    拒绝
                  </button>
                </div>
              </div>
            )
          ) : (
            <div className="pixel-card-soft mt-4 px-4 py-4 text-sm text-[var(--color-ink-soft)]">
              当前没有待处理的 HITL 复核请求。
            </div>
          )}
          <div className="mt-4 space-y-3">
            {hitlAudit.length ? (
              hitlAudit.map((entry) => (
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
                    <p>requested_at: {entry.request.requested_at || "-"}</p>
                    <p>decision_id: {entry.decision?.decision_id || "-"}</p>
                    <p>decision: {entry.decision?.decision || "-"}</p>
                    <p>actor: {entry.decision?.actor_id || "-"}</p>
                  </div>
                </div>
              ))
            ) : null}
          </div>
        </section>

        <section className="pixel-card p-4">
          <p className="pixel-label">approval context memory</p>
          <p className="pixel-note mt-2">Current working memory, episodic summary, and the latest semantic/procedural hits used for approval context assembly.</p>
          {sessionContext ? (
            <div className="mt-4 space-y-3">
              <div className="pixel-card-soft p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="pixel-tag">working memory</span>
                  <span className="mono text-[0.92rem] text-[var(--color-ink-soft)]">{sessionContext.thread_id}</span>
                </div>
                <div className="mt-3 grid gap-2 text-sm text-[var(--color-ink-soft)] md:grid-cols-2">
                  <p>current_goal: {sessionContext.working_memory.current_goal || "-"}</p>
                  <p>latest_user_intent: {sessionContext.working_memory.latest_user_intent || "-"}</p>
                  <p>active_constraints: {(sessionContext.working_memory.active_constraints || []).join(" | ") || "-"}</p>
                  <p>active_entities: {(sessionContext.working_memory.active_entities || []).join(" | ") || "-"}</p>
                  <p>active_artifacts: {(sessionContext.working_memory.active_artifacts || []).join(" | ") || "-"}</p>
                  <p>unresolved_items: {(sessionContext.working_memory.unresolved_items || []).join(" | ") || "-"}</p>
                </div>
              </div>

              <div className="pixel-card-soft p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="pixel-tag">episodic summary</span>
                  <span className="pixel-tag">v{sessionContext.episodic_summary.summary_version}</span>
                </div>
                <div className="mt-3 grid gap-2 text-sm text-[var(--color-ink-soft)] md:grid-cols-2">
                  <p>key_facts: {(sessionContext.episodic_summary.key_facts || []).join(" | ") || "-"}</p>
                  <p>completed_subtasks: {(sessionContext.episodic_summary.completed_subtasks || []).join(" | ") || "-"}</p>
                  <p>rejected_paths: {(sessionContext.episodic_summary.rejected_paths || []).join(" | ") || "-"}</p>
                  <p>open_loops: {(sessionContext.episodic_summary.open_loops || []).join(" | ") || "-"}</p>
                </div>
              </div>

              <div className="grid gap-3 xl:grid-cols-2">
                <div className="pixel-card-soft p-4">
                  <p className="pixel-label">semantic memory hits</p>
                  <div className="mt-3 space-y-3">
                    {sessionContext.semantic_memories.length ? (
                      sessionContext.semantic_memories.map((item) => (
                        <div key={item.memory_id} className="rounded-[10px] border border-[var(--color-line)] px-3 py-3 text-sm text-[var(--color-ink-soft)]">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="pixel-tag">{item.namespace}</span>
                            <span className="mono text-[0.92rem]">{item.memory_id}</span>
                          </div>
                          <p className="mt-2 text-[var(--color-ink)]">{item.title}</p>
                          <p className="mt-2">{item.summary || item.content}</p>
                        </div>
                      ))
                    ) : (
                      <p className="text-sm text-[var(--color-ink-soft)]">No semantic memory hits yet.</p>
                    )}
                  </div>
                </div>
                <div className="pixel-card-soft p-4">
                  <p className="pixel-label">procedural memory hits</p>
                  <div className="mt-3 space-y-3">
                    {sessionContext.procedural_memories.length ? (
                      sessionContext.procedural_memories.map((item) => (
                        <div key={item.memory_id} className="rounded-[10px] border border-[var(--color-line)] px-3 py-3 text-sm text-[var(--color-ink-soft)]">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="pixel-tag">{item.namespace}</span>
                            <span className="mono text-[0.92rem]">{item.memory_id}</span>
                          </div>
                          <p className="mt-2 text-[var(--color-ink)]">{item.title}</p>
                          <p className="mt-2">{item.summary || item.content}</p>
                        </div>
                      ))
                    ) : (
                      <p className="text-sm text-[var(--color-ink-soft)]">No procedural memory hits yet.</p>
                    )}
                  </div>
                </div>
              </div>

              <div className="pixel-card-soft p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="pixel-label">approval memory governance</p>
                    <p className="pixel-note mt-2">Manifest-first recall state, consolidation summary, and lifecycle flags.</p>
                  </div>
                  <button
                    className="ui-button"
                    disabled={assetsLoading || isStreaming}
                    onClick={() => void triggerConsolidation()}
                    type="button"
                  >
                    Run consolidation
                  </button>
                </div>

                <div className="mt-4 grid gap-3 xl:grid-cols-2">
                  <div className="rounded-[10px] border border-[var(--color-line)] px-3 py-3 text-sm text-[var(--color-ink-soft)]">
                    <p className="pixel-label">session memory gates</p>
                    <div className="mt-3 grid gap-2">
                      <p>last_updated_at: {String(sessionContext.session_memory_state?.["last_updated_at"] ?? "-")}</p>
                      <p>last_update_reason: {String(sessionContext.session_memory_state?.["last_update_reason"] ?? "-")}</p>
                      <p>last_decision: {String(sessionContext.session_memory_state?.["last_decision"] ?? "-")}</p>
                      <p>last_skip_reason: {String(sessionContext.session_memory_state?.["last_skip_reason"] ?? "-")}</p>
                      <p>update_count: {String(sessionContext.session_memory_state?.["update_count"] ?? "0")}</p>
                    </div>
                  </div>

                  <div className="rounded-[10px] border border-[var(--color-line)] px-3 py-3 text-sm text-[var(--color-ink-soft)]">
                    <p className="pixel-label">latest consolidation</p>
                    {sessionContext.latest_consolidation ? (
                      <>
                        <div className="mt-3 flex flex-wrap items-center gap-2">
                          <span className="pixel-tag">{sessionContext.latest_consolidation.status}</span>
                          <span className="pixel-tag">{sessionContext.latest_consolidation.trigger}</span>
                          <span className="mono text-[0.92rem]">{sessionContext.latest_consolidation.created_at}</span>
                        </div>
                        <p className="mt-3">
                          promoted: {sessionContext.latest_consolidation.promoted_memory_ids.length} | stale: {sessionContext.latest_consolidation.stale_memory_ids.length} | superseded: {sessionContext.latest_consolidation.superseded_memory_ids.length} | conflicts: {sessionContext.latest_consolidation.conflict_memory_ids.length}
                        </p>
                        <p className="mt-2">{(sessionContext.latest_consolidation.notes || []).join(" | ") || "-"}</p>
                      </>
                    ) : (
                      <p className="mt-3">No consolidation run recorded yet.</p>
                    )}
                  </div>

                  <div className="rounded-[10px] border border-[var(--color-line)] px-3 py-3 text-sm text-[var(--color-ink-soft)]">
                    <p className="pixel-label">conversation recall</p>
                    <div className="mt-3 space-y-2">
                      {sessionContext.conversation_recall.length ? (
                        sessionContext.conversation_recall.slice(0, 4).map((item) => (
                          <div key={item.chunk_id} className="rounded-[8px] border border-[var(--color-line)] px-3 py-2">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="pixel-tag">{item.role}</span>
                              <span className="mono text-[0.92rem]">{item.updated_at}</span>
                            </div>
                            <p className="mt-2">{item.summary || item.snippet}</p>
                          </div>
                        ))
                      ) : (
                        <p>No thread recall chunks yet.</p>
                      )}
                    </div>
                  </div>
                </div>

                <div className="mt-4 grid gap-3 xl:grid-cols-2">
                  <div className="rounded-[10px] border border-[var(--color-line)] px-3 py-3 text-sm text-[var(--color-ink-soft)]">
                    <p className="pixel-label">episodic memories</p>
                    <div className="mt-3 space-y-3">
                      {sessionContext.episodic_memories.length ? (
                        sessionContext.episodic_memories.map((item) => (
                          <div key={item.memory_id} className="rounded-[8px] border border-[var(--color-line)] px-3 py-3">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="pixel-tag">{item.status || "active"}</span>
                              <span className="pixel-tag">{item.freshness || "fresh"}</span>
                              <span className="mono text-[0.92rem]">{item.memory_id}</span>
                            </div>
                            <p className="mt-2 text-[var(--color-ink)]">{item.title}</p>
                            <p className="mt-2">{item.summary || item.content}</p>
                          </div>
                        ))
                      ) : (
                        <p>No episodic memories yet.</p>
                      )}
                    </div>
                  </div>

                  <div className="rounded-[10px] border border-[var(--color-line)] px-3 py-3 text-sm text-[var(--color-ink-soft)]">
                    <p className="pixel-label">memory manifests</p>
                    <div className="mt-3 space-y-3">
                      {sessionContext.manifests.length ? (
                        sessionContext.manifests.slice(0, 10).map((item) => (
                          <div key={item.memory_id} className="rounded-[8px] border border-[var(--color-line)] px-3 py-3">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="pixel-tag">{item.memory_type || item.kind}</span>
                              <span className="pixel-tag">{item.scope || item.namespace}</span>
                              {item.status ? <span className="pixel-tag">{item.status}</span> : null}
                              {item.freshness ? <span className="pixel-tag">{item.freshness}</span> : null}
                              {item.conflict_flag ? <span className="pixel-tag">conflict</span> : null}
                              <span className="mono text-[0.92rem]">{item.memory_id}</span>
                            </div>
                            <p className="mt-2 text-[var(--color-ink)]">{item.title}</p>
                            <p className="mt-2">{item.summary || item.content}</p>
                          </div>
                        ))
                      ) : (
                        <p>No governed manifests yet.</p>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              <div className="pixel-card-soft p-4">
                <p className="pixel-label">recent context assemblies</p>
                <div className="mt-3 space-y-3">
                  {sessionContext.assemblies.length ? (
                    sessionContext.assemblies.map((item) => (
                      <div key={item.assembly_id} className="rounded-[10px] border border-[var(--color-line)] px-3 py-3 text-sm text-[var(--color-ink-soft)]">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="pixel-tag">{item.path_kind}</span>
                          <span className="pixel-tag">{item.call_site}</span>
                          <span className="mono text-[0.92rem]">{item.created_at}</span>
                        </div>
                        <p className="mt-2">
                          selected_memory_ids: {Array.isArray(item.decision?.["selected_memory_ids"]) ? (item.decision["selected_memory_ids"] as string[]).join(" | ") || "-" : "-"}
                        </p>
                        <p className="mt-1">
                          truncation_reason: {typeof item.decision?.["truncation_reason"] === "string" ? (item.decision["truncation_reason"] as string) || "-" : "-"}
                        </p>
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-[var(--color-ink-soft)]">No context assemblies recorded yet.</p>
                  )}
                </div>
              </div>

              <div className="pixel-card-soft p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="pixel-label">context quarantine</p>
                    <p className="pixel-note mt-2">Exclude one polluted turn from future context without deleting the raw session history.</p>
                  </div>
                  {selectedContextTurn ? (
                    <button
                      className="ui-button"
                      disabled={assetsLoading || isStreaming || selectedContextTurn.excluded_from_context}
                      onClick={() => void excludeContextTurn(selectedContextTurn.turn_id)}
                      type="button"
                    >
                      {selectedContextTurn.excluded_from_context ? "Already excluded" : "Exclude from future context"}
                    </button>
                  ) : null}
                </div>
                {selectedContextTurn ? (
                  <div className="mt-4 space-y-3 text-sm text-[var(--color-ink-soft)]">
                    <div className="rounded-[10px] border border-[var(--color-line)] px-3 py-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="pixel-tag">{selectedContextTurn.path_type}</span>
                        <span className="pixel-tag">{selectedContextTurn.run_status || "fresh"}</span>
                        {selectedContextTurn.excluded_from_context ? <span className="pixel-tag">excluded</span> : null}
                        <span className="mono text-[0.92rem]">{selectedContextTurn.turn_id}</span>
                      </div>
                      <p className="mt-2 text-[var(--color-ink)]">{selectedContextTurn.user_query || "No query captured."}</p>
                      {selectedContextTurn.exclusion_reason ? <p className="mt-2">reason: {selectedContextTurn.exclusion_reason}</p> : null}
                    </div>

                    <div className="grid gap-3 xl:grid-cols-2">
                      <div className="rounded-[10px] border border-[var(--color-line)] px-3 py-3">
                        <p className="pixel-label">derived memories</p>
                        <div className="mt-3 space-y-2">
                          {derivedTurnMemories?.memories.length ? (
                            derivedTurnMemories.memories.map((item) => (
                              <div key={item.memory_id} className="rounded-[8px] border border-[var(--color-line)] px-3 py-2">
                                <div className="flex flex-wrap items-center gap-2">
                                  <span className="pixel-tag">{item.memory_type || item.kind}</span>
                                  {item.status ? <span className="pixel-tag">{item.status}</span> : null}
                                  {item.freshness ? <span className="pixel-tag">{item.freshness}</span> : null}
                                  <span className="mono text-[0.92rem]">{item.memory_id}</span>
                                </div>
                                <p className="mt-2 text-[var(--color-ink)]">{item.title}</p>
                                <p className="mt-2">{item.summary || item.content}</p>
                              </div>
                            ))
                          ) : (
                            <p>No derived governed memory found for the selected turn.</p>
                          )}
                        </div>
                      </div>

                      <div className="rounded-[10px] border border-[var(--color-line)] px-3 py-3">
                        <p className="pixel-label">derived conversation recall</p>
                        <div className="mt-3 space-y-2">
                          {derivedTurnMemories?.conversation_recall.length ? (
                            derivedTurnMemories.conversation_recall.map((item) => (
                              <div key={item.chunk_id} className="rounded-[8px] border border-[var(--color-line)] px-3 py-2">
                                <div className="flex flex-wrap items-center gap-2">
                                  <span className="pixel-tag">{item.role}</span>
                                  <span className="pixel-tag">{item.status}</span>
                                  <span className="mono text-[0.92rem]">{item.chunk_id}</span>
                                </div>
                                <p className="mt-2">{item.summary || item.snippet}</p>
                              </div>
                            ))
                          ) : (
                            <p>No derived conversation recall entries found for the selected turn.</p>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="mt-4 rounded-[10px] border border-[var(--color-line)] px-3 py-3 text-sm text-[var(--color-ink-soft)]">
                    Pick a turn in the approval context trace panel to inspect derived memories and exclude it from future context.
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="pixel-card-soft mt-4 px-4 py-4 text-sm text-[var(--color-ink-soft)]">
              No approval context snapshot for this session yet.
            </div>
          )}
        </section>

        <section className="pixel-card p-4">
          <p className="pixel-label">workflow capabilities</p>
          <p className="pixel-note mt-2">Current read-only MCP assets registered in the unified capability system.</p>
          <div className="mt-4 space-y-3">
            {mcpCapabilities.length ? (
              mcpCapabilities.map((item) => (
                <div className="pixel-card-soft p-4" key={item.capability_id}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="pixel-tag">{item.capability_type}</span>
                    <span className="pixel-tag">{item.enabled ? "enabled" : "disabled"}</span>
                    <span className="pixel-tag">risk {item.risk_level}</span>
                  </div>
                  <h4 className="pixel-title mt-3 text-[1rem] text-[var(--color-ink)]">{item.display_name}</h4>
                  <p className="pixel-note mt-2">{item.description}</p>
                  <div className="mt-3 grid gap-2 text-sm text-[var(--color-ink-soft)] md:grid-cols-2">
                    <p>capability_id: {item.capability_id}</p>
                    <p>approval_required: {String(item.approval_required)}</p>
                    <p>timeout_seconds: {item.timeout_seconds}</p>
                    <p>repeated_call_limit: {item.repeated_call_limit}</p>
                  </div>
                </div>
              ))
            ) : (
              <div className="pixel-card-soft px-4 py-4 text-sm text-[var(--color-ink-soft)]">
                No workflow capabilities are registered.
              </div>
            )}
          </div>
        </section>
      </div>
    </section>
  );
}
