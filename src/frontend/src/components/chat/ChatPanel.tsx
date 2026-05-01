"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { ChatMessage } from "@/components/chat/ChatMessage";
import { VirtualizedStack } from "@/components/chat/VirtualizedStack";
import { PixelGhostFriend } from "@/components/icons/PixelGhostFriend";
import { useChatStore, useSessionStore } from "@/lib/store";

const AUTO_SCROLL_THRESHOLD = 72;
const AUTO_SCROLL_RESTORE_THRESHOLD = 12;
const AUTO_SCROLL_USER_PAUSE_MS = 900;
const CHAT_ITEM_ESTIMATE = 220;
const ERP_RECOMMENDATION_REVIEW_CAPABILITY_ID = "erp_approval_recommendation_review";

type ChatRow = {
  id: string;
  message: ReturnType<typeof useChatStore>["messages"][number];
  streaming: boolean;
};

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
  const isErpRecommendationReview =
    pendingHitl?.capability_id === ERP_RECOMMENDATION_REVIEW_CAPABILITY_ID;
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
          <div className="pixel-card-soft mb-4 flex max-h-[52vh] min-h-0 shrink-0 flex-col overflow-y-auto px-4 py-4 sm:max-h-[46vh]">
            <p className="pixel-label">
              {isErpRecommendationReview ? "需要人工复核 ERP 建议（不会执行 ERP）" : "需要人工复核"}
            </p>
            <h3 className="pixel-title mt-2 text-[1rem] text-[var(--color-ink)]">
              {isErpRecommendationReview ? "ERP 审批建议复核" : pendingHitl.display_name}
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
            {isErpRecommendationReview ? (
              <p className="pixel-note mt-2">
                普通复核只需要采用或拒绝建议；只有想改结构化建议内容时才使用 JSON 编辑。
              </p>
            ) : null}
            <div className="mt-4 min-h-0 pr-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="pixel-tag">{riskLabel(pendingHitl.risk_level)}</span>
                {pendingHitl.request_id ? <span className="pixel-tag">请求 {pendingHitl.request_id.slice(0, 8)}</span> : null}
                <span className="pixel-tag">checkpoint {pendingHitl.checkpoint_id.slice(0, 8)}</span>
              </div>
              <details className="hitl-payload-details mt-4">
                <summary>高级：查看或编辑结构化建议 JSON</summary>
                <p className="pixel-note mt-3">
                  这里编辑的是 Agent 建议 payload，不是 ERP 单据，也不会触发 ERP 写入。
                </p>
                <pre>{prettyJson(pendingHitl.proposed_input)}</pre>
                <label className="pixel-label mt-4 block">编辑 JSON 后继续（可选）</label>
                <textarea
                  className="mt-2 min-h-[120px] w-full rounded-[8px] border border-[var(--color-line)] bg-[var(--color-bg)] px-3 py-3 font-mono text-sm text-[var(--color-ink)] outline-none"
                  onChange={(event) => setEditedInputText(event.target.value)}
                  value={editedInputText}
                />
                {editError ? <p className="mt-2 text-sm text-[var(--color-danger)]">{editError}</p> : null}
                <button
                  className="ui-button mt-3"
                  disabled={isStreaming}
                  onClick={handleEditAndContinue}
                  type="button"
                >
                  {isStreaming ? "正在提交编辑..." : "保存 JSON 编辑并继续"}
                </button>
              </details>
            </div>
          </div>
        ) : null}

        {!renderableMessages.length ? (
          <div className="chat-scroll-area flex-1 overflow-y-auto pr-2" ref={scrollRef}>
            <div className="cli-welcome px-6 py-7">
              <div className="cli-welcome-bar">ERP Approval Agent // local-first workbench</div>
              <div className="cli-welcome-grid mt-8">
                <section className="cli-welcome-main">
                  <h3 className="pixel-title text-[2.3rem] text-[var(--color-ink)]">
                    {isInitializing
                      ? "正在启动工作台"
                      : isSessionLoading
                        ? "正在切换审批线程"
                        : "带证据审查 ERP 审批"}
                  </h3>
                  <div className="cli-emoji-wrap mt-8">
                    <div className="cli-emoji">
                      <PixelGhostFriend className="h-full w-full" />
                    </div>
                  </div>
                  <div className="mt-8 text-center">
                    <p className="mono text-[1rem] text-[var(--color-ink-soft)]">
                      LLM-first 审批推理 / 政策检索 / Audit Trace
                    </p>
                    <p className="mono mt-2 text-[1rem] text-[var(--color-ink)]">
                      只生成审批建议 / 不执行 ERP 写动作 / HITL 先行
                    </p>
                    <p className="mt-4 text-sm text-[var(--color-ink-muted)]">
                      <a className="underline underline-offset-4" href="https://pxlkit.xyz" rel="noreferrer" target="_blank">
                        Icons by Pxlkit
                      </a>
                    </p>
                  </div>
                </section>

                <section className="cli-welcome-side">
                  <div>
                    <h4 className="pixel-title text-[1rem] text-[var(--color-ink)]">使用提示</h4>
                    <div className="mono mt-4 space-y-3 text-[1rem] leading-8 text-[var(--color-ink-soft)]">
                      <p>Audit Trace 里可以单独看检索、workflow tools、checkpoint 和 HITL 事件。</p>
                      <p>Workflow tools 里可以打开文件、切换运行设置、管理审批会话。</p>
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
