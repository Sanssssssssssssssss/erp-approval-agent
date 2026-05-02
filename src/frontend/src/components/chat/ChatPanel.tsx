"use client";

import { ClipboardCheck, FileSearch, ListChecks, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { ChatMessage } from "@/components/chat/ChatMessage";
import { HitlRecommendationReviewCard } from "@/components/chat/HitlRecommendationReviewCard";
import { VirtualizedStack } from "@/components/chat/VirtualizedStack";
import { useChatStore, useSessionStore } from "@/lib/store";

const AUTO_SCROLL_THRESHOLD = 72;
const AUTO_SCROLL_RESTORE_THRESHOLD = 12;
const AUTO_SCROLL_USER_PAUSE_MS = 900;
const CHAT_ITEM_ESTIMATE = 220;
const ERP_RECOMMENDATION_REVIEW_CAPABILITY_ID = "erp_approval_recommendation_review";
const ERP_RECOMMENDATION_REVIEW_TYPE = "erp_recommendation_review";

type ChatRow = {
  id: string;
  message: ReturnType<typeof useChatStore>["messages"][number];
  streaming: boolean;
};

const WELCOME_STEPS = [
  { icon: FileSearch, title: "取证", description: "审批单、发票、PO、GRN、预算、供应商和政策材料" },
  { icon: ListChecks, title: "校验", description: "必需证据、阻断缺口、冲突和控制矩阵" },
  { icon: ClipboardCheck, title: "建议", description: "只生成本地审批建议和下一步草案" },
  { icon: ShieldCheck, title: "复核", description: "HITL 只接受/修改建议，不执行 ERP 写入" }
];

const WELCOME_SAMPLE_PROMPTS = [
  "请审核采购申请 PR-1001，申请部门 Operations，金额 24500 USD，供应商 Acme Supplies。",
  "请审查发票付款 INV-3001，重点看 PO、GRN、Invoice 三单匹配。",
  "只有一句话：帮我直接通过这个采购申请。"
];

function prettyJson(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2);
}

function riskLabel(value: string | null | undefined) {
  const normalized = (value || "").toLowerCase();
  if (normalized === "high") return "高风险";
  if (normalized === "medium") return "中风险";
  if (normalized === "low") return "低风险";
  return value || "未标记风险";
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

export function ChatPanel() {
  const {
    messages,
    pendingHitl,
    streamingMessages,
    submitHitlDecision,
    isInitializing,
    isSessionLoading,
    isStreaming,
    connectionError,
    retryInitialization
  } = useChatStore();
  const [editedInputText, setEditedInputText] = useState("{}");
  const [editError, setEditError] = useState("");
  const { currentSessionId, sessions } = useSessionStore();
  const isErpRecommendationReview = isErpRecommendationReviewRequest(pendingHitl);
  const approveButtonLabel = isErpRecommendationReview ? "采用建议并继续" : "通过复核";
  const approvingButtonLabel = isErpRecommendationReview ? "正在生成复核回执..." : "正在通过...";
  const rejectButtonLabel = isErpRecommendationReview ? "拒绝这条建议" : "拒绝";
  const hitlReason = isErpRecommendationReview
    ? "请复核 Agent 的 ERP 审批建议。这里的采用、编辑或拒绝只影响本地建议回执，不会执行任何 ERP 写入。"
    : pendingHitl?.reason ?? "";
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const stickToBottomRef = useRef(true);
  const frameRef = useRef<number | null>(null);
  const lastScrollTopRef = useRef(0);
  const programmaticScrollRef = useRef(false);
  const userScrollPauseUntilRef = useRef(0);
  const rowCacheRef = useRef(
    new Map<string, { source: ChatRow["message"]; streaming: boolean; row: ChatRow }>()
  );

  const renderableMessages = useMemo(() => {
    const nextCache = new Map<
      string,
      { source: ChatRow["message"]; streaming: boolean; row: ChatRow }
    >();
    const nextRows: ChatRow[] = [];

    const pushRow = (message: ChatRow["message"], streaming: boolean) => {
      const cached = rowCacheRef.current.get(message.id);
      if (cached && cached.source === message && cached.streaming === streaming) {
        nextCache.set(message.id, cached);
        nextRows.push(cached.row);
        return;
      }

      const row = { id: message.id, message, streaming };
      const entry = { source: message, streaming, row };
      nextCache.set(message.id, entry);
      nextRows.push(row);
    };

    for (const message of messages) {
      pushRow(message, false);
    }

    for (let index = 0; index < streamingMessages.length; index += 1) {
      pushRow(streamingMessages[index], isStreaming && index === streamingMessages.length - 1);
    }

    rowCacheRef.current = nextCache;
    return nextRows;
  }, [isStreaming, messages, streamingMessages]);

  const lastMessage = renderableMessages[renderableMessages.length - 1];
  const recentSessions = useMemo(
    () => sessions.filter((session) => session.id !== currentSessionId).slice(0, 2),
    [currentSessionId, sessions]
  );

  useEffect(() => {
    setEditedInputText(prettyJson(pendingHitl?.proposed_input));
    setEditError("");
  }, [pendingHitl]);

  const cancelScheduledScroll = useCallback(() => {
    if (frameRef.current !== null) {
      window.cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    }
  }, []);

  const getDistanceToBottom = useCallback(() => {
    const container = scrollRef.current;
    if (!container) {
      return Infinity;
    }
    return container.scrollHeight - container.scrollTop - container.clientHeight;
  }, []);

  const pauseAutoStick = useCallback(() => {
    stickToBottomRef.current = false;
    userScrollPauseUntilRef.current = performance.now() + AUTO_SCROLL_USER_PAUSE_MS;
    cancelScheduledScroll();
  }, [cancelScheduledScroll]);

  const syncToBottom = useCallback((defer = true) => {
    const container = scrollRef.current;
    if (
      !container ||
      !stickToBottomRef.current ||
      performance.now() < userScrollPauseUntilRef.current
    ) {
      return;
    }

    const run = () => {
      const nextContainer = scrollRef.current;
      if (
        !nextContainer ||
        !stickToBottomRef.current ||
        performance.now() < userScrollPauseUntilRef.current
      ) {
        return;
      }
      programmaticScrollRef.current = true;
      nextContainer.scrollTop = nextContainer.scrollHeight;
      lastScrollTopRef.current = nextContainer.scrollTop;
    };

    cancelScheduledScroll();

    if (!defer) {
      run();
      return;
    }

    frameRef.current = window.requestAnimationFrame(() => {
      frameRef.current = null;
      run();
    });
  }, [cancelScheduledScroll]);

  useLayoutEffect(() => {
    const container = scrollRef.current;
    if (!container) {
      return;
    }

    const handleScroll = () => {
      const nextScrollTop = container.scrollTop;
      const distanceToBottom =
        container.scrollHeight - nextScrollTop - container.clientHeight;

      if (programmaticScrollRef.current) {
        programmaticScrollRef.current = false;
        lastScrollTopRef.current = nextScrollTop;
        stickToBottomRef.current = distanceToBottom <= AUTO_SCROLL_THRESHOLD;
        return;
      }

      const scrolledUp = nextScrollTop < lastScrollTopRef.current;
      lastScrollTopRef.current = nextScrollTop;

      if (scrolledUp) {
        pauseAutoStick();
      } else if (distanceToBottom <= AUTO_SCROLL_RESTORE_THRESHOLD) {
        stickToBottomRef.current = true;
      }

      if (!stickToBottomRef.current) {
        cancelScheduledScroll();
      }
    };

    const handleWheel = (event: WheelEvent) => {
      if (event.deltaY < 0) {
        pauseAutoStick();
      }
    };

    const handlePointerDown = () => {
      pauseAutoStick();
    };

    handleScroll();
    container.addEventListener("scroll", handleScroll, { passive: true });
    container.addEventListener("wheel", handleWheel, { passive: true });
    container.addEventListener("pointerdown", handlePointerDown, { passive: true });
    return () => {
      container.removeEventListener("scroll", handleScroll);
      container.removeEventListener("wheel", handleWheel);
      container.removeEventListener("pointerdown", handlePointerDown);
    };
  }, [cancelScheduledScroll, pauseAutoStick, syncToBottom]);

  useLayoutEffect(() => {
    if (!renderableMessages.length) {
      return;
    }
    syncToBottom(false);
  }, [renderableMessages.length, syncToBottom]);

  useLayoutEffect(() => {
    stickToBottomRef.current = true;
    syncToBottom(false);
  }, [currentSessionId, syncToBottom]);

  useLayoutEffect(() => {
    if (!lastMessage) {
      return;
    }
    syncToBottom(true);
  }, [isStreaming, lastMessage, syncToBottom]);

  const handleTotalHeightChange = useCallback(() => {
    if (performance.now() < userScrollPauseUntilRef.current) {
      cancelScheduledScroll();
      return;
    }
    const distanceToBottom = getDistanceToBottom();
    if (distanceToBottom > AUTO_SCROLL_THRESHOLD) {
      stickToBottomRef.current = false;
      cancelScheduledScroll();
      return;
    }
    if (stickToBottomRef.current) {
      syncToBottom(false);
    }
  }, [cancelScheduledScroll, getDistanceToBottom, syncToBottom]);

  const handleEditAndContinue = useCallback(() => {
    if (!pendingHitl) return;
    try {
      const parsed = JSON.parse(editedInputText) as Record<string, unknown>;
      setEditError("");
      void submitHitlDecision(pendingHitl.checkpoint_id, "edit", parsed);
    } catch (error) {
      setEditError(error instanceof Error ? `JSON 格式不正确：${error.message}` : "JSON 格式不正确");
    }
  }, [editedInputText, pendingHitl, submitHitlDecision]);

  return (
    <section className="flex h-full min-h-0 flex-1 flex-col overflow-hidden">
      <div className="panel flex min-h-0 flex-1 flex-col overflow-hidden px-4 pb-4 pt-4">
        {connectionError ? (
          <div className="pixel-card-soft mb-4 px-4 py-4 text-sm text-[var(--color-ink)]">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="pixel-label">后端不可用</p>
                <p className="pixel-note mt-2">{connectionError}</p>
              </div>
              <button
                className="ui-button"
                disabled={isInitializing || isStreaming}
                onClick={() => void retryInitialization()}
                type="button"
              >
                {isInitializing ? "正在重试..." : "重试连接"}
              </button>
            </div>
          </div>
        ) : null}

        {pendingHitl && currentSessionId ? (
          isErpRecommendationReview ? (
            <HitlRecommendationReviewCard
              editError={editError}
              editedInputText={editedInputText}
              isStreaming={isStreaming}
              onAccept={() => void submitHitlDecision(pendingHitl.checkpoint_id, "approve")}
              onEditSubmit={handleEditAndContinue}
              onEditTextChange={setEditedInputText}
              onReject={() => void submitHitlDecision(pendingHitl.checkpoint_id, "reject")}
              pendingHitl={pendingHitl}
            />
          ) : (
            <div className="pixel-card-soft mb-4 flex max-h-[52vh] min-h-0 shrink-0 flex-col overflow-y-auto px-4 py-4 sm:max-h-[46vh]">
              <p className="pixel-label">需要人工复核</p>
              <h3 className="pixel-title mt-2 text-[1rem] text-[var(--color-ink)]">
                {pendingHitl.display_name}
              </h3>
              <div className="mt-4 flex flex-wrap gap-3">
                <button
                  className="ui-button ui-button-primary"
                  disabled={isStreaming}
                  onClick={() => void submitHitlDecision(pendingHitl.checkpoint_id, "approve")}
                  type="button"
                >
                  {isStreaming ? approvingButtonLabel : approveButtonLabel}
                </button>
                <button
                  className="ui-button"
                  disabled={isStreaming}
                  onClick={() => void submitHitlDecision(pendingHitl.checkpoint_id, "reject")}
                  type="button"
                >
                  {isStreaming ? "正在拒绝..." : rejectButtonLabel}
                </button>
              </div>
              <p className="pixel-note mt-4">{hitlReason}</p>
              <div className="mt-4 min-h-0 pr-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="pixel-tag">{riskLabel(pendingHitl.risk_level)}</span>
                  {pendingHitl.request_id ? <span className="pixel-tag">请求 {pendingHitl.request_id.slice(0, 8)}</span> : null}
                  <span className="pixel-tag">checkpoint {pendingHitl.checkpoint_id.slice(0, 8)}</span>
                </div>
                <details className="hitl-payload-details mt-4">
                  <summary>查看审查 payload</summary>
                  <pre>{prettyJson(pendingHitl.proposed_input)}</pre>
                </details>
              </div>
            </div>
          )
        ) : null}

        {!renderableMessages.length ? (
          <div className="chat-scroll-area flex-1 overflow-y-auto pr-2" ref={scrollRef}>
            <div className="cli-welcome px-6 py-7">
              <div className="cli-welcome-bar">ERP Approval Agent // 证据先行工作台</div>
              <div className="cli-welcome-grid mt-8">
                <section className="cli-welcome-main">
                  <h3 className="pixel-title text-[2rem] text-[var(--color-ink)]">
                    {isInitializing
                      ? "正在启动工作台"
                      : isSessionLoading
                        ? "正在切换审批线程"
                        : "先建审批案件，再审证据链"}
                  </h3>
                  <p className="mt-4 max-w-[720px] text-[1rem] leading-8 text-[var(--color-ink-soft)]">
                    一句话不会直接给“通过”。系统会先识别审批单，再检查 ERP 记录、政策、附件和控制矩阵；
                    证据不足时只会要求补证或升级人工复核。
                  </p>
                  <div className="approval-workbench-steps mt-6">
                    {WELCOME_STEPS.map(({ icon: Icon, title, description }) => (
                      <div className="approval-workbench-step" key={title}>
                        <Icon size={18} />
                        <strong>{title}</strong>
                        <span>{description}</span>
                      </div>
                    ))}
                  </div>
                  <div className="mt-6 grid gap-3 text-left md:grid-cols-3">
                    {WELCOME_SAMPLE_PROMPTS.map((sample) => (
                      <div className="approval-sample-prompt" key={sample}>
                        {sample}
                      </div>
                    ))}
                  </div>
                </section>

                <section className="cli-welcome-side">
                  <div>
                    <h4 className="pixel-title text-[1rem] text-[var(--color-ink)]">工作台规则</h4>
                    <div className="mono mt-4 space-y-3 text-[1rem] leading-8 text-[var(--color-ink-soft)]">
                      <p>证据材料可在“证据”页查看；审计轨迹可在“审计轨迹”页查看。</p>
                      <p>人工复核按钮只影响 Agent 建议回执，不会执行 ERP 通过、驳回或付款。</p>
                      <p>Ctrl/Cmd + Enter 发送。主页面只滚动审批助理区域。</p>
                    </div>
                  </div>

                  <div className="cli-divider" />

                  <div>
                    <h4 className="pixel-title text-[1rem] text-[var(--color-ink)]">最近活动</h4>
                    <div className="mono mt-4 space-y-2 text-[1rem] text-[var(--color-ink-soft)]">
                      {recentSessions.length ? (
                        recentSessions.map((session) => (
                          <div className="flex flex-wrap items-center justify-between gap-3" key={session.id}>
                            <span className="truncate">{session.title}</span>
                            <span className="text-[var(--color-ink-muted)]">{session.message_count} 条消息</span>
                          </div>
                        ))
                      ) : (
                        <p>还没有更早的会话。</p>
                      )}
                    </div>
                  </div>
                </section>
              </div>
            </div>
          </div>
        ) : (
          <VirtualizedStack
            className="chat-scroll-area flex-1 overflow-y-auto pr-2"
            containerRef={scrollRef}
            estimateHeight={CHAT_ITEM_ESTIMATE}
            getKey={(row) => row.id}
            items={renderableMessages}
            onTotalHeightChange={handleTotalHeightChange}
            renderItem={(row) => (
              <div className="pb-4">
                <ChatMessage
                  content={row.message.content}
                  role={row.message.role}
                  runMeta={row.message.runMeta}
                  streaming={row.streaming}
                  usage={row.message.usage}
                />
              </div>
            )}
          />
        )}
      </div>
    </section>
  );
}
