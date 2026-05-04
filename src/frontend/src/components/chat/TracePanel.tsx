"use client";

import { memo, useMemo, useRef, useState } from "react";
import { MessageSquareText, Route, Sparkles } from "lucide-react";

import { ContextTracePanel } from "@/components/chat/ContextTracePanel";
import { LlmContextLibraryPanel } from "@/components/chat/LlmContextLibraryPanel";
import { RetrievalCard } from "@/components/chat/RetrievalCard";
import { ThoughtChain } from "@/components/chat/ThoughtChain";
import { VirtualizedStack } from "@/components/chat/VirtualizedStack";
import type { ErpApprovalCaseTurnResponse } from "@/lib/api";
import { useChatStore } from "@/lib/store";

import { displayLabel, list, object, records, text } from "./caseInsightUtils";

const TRACE_ITEM_ESTIMATE = 720;

type TraceTurn = {
  id: string;
  prompt: string | null;
  answer: string;
  toolCalls: ReturnType<typeof useChatStore>["messages"][number]["toolCalls"];
  retrievalSteps: ReturnType<typeof useChatStore>["messages"][number]["retrievalSteps"];
  usage: ReturnType<typeof useChatStore>["messages"][number]["usage"];
  runMeta: ReturnType<typeof useChatStore>["messages"][number]["runMeta"];
  checkpointEvents: ReturnType<typeof useChatStore>["messages"][number]["checkpointEvents"];
  hitlEvents: ReturnType<typeof useChatStore>["messages"][number]["hitlEvents"];
  streaming: boolean;
};

const TraceTurnCard = memo(function TraceTurnCard({ turn }: { turn: TraceTurn }) {
  const hasTrace =
    turn.toolCalls.length > 0 ||
    turn.retrievalSteps.length > 0 ||
    turn.checkpointEvents.length > 0 ||
    turn.hitlEvents.length > 0;

  return (
    <article className="pixel-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="ui-pill">
          <Route size={14} />
          {turn.streaming ? "实时 Audit Trace" : "Audit Trace"}
        </div>
        {turn.usage ? (
          <div className="mono text-sm text-[var(--color-ink-soft)]">
            {`${turn.usage.input_tokens.toLocaleString()} 输入 / ${turn.usage.output_tokens.toLocaleString()} 输出`}
          </div>
        ) : null}
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <section className="pixel-card-soft p-4">
          <div className="pixel-label mb-3 flex items-center gap-2">
            <MessageSquareText size={14} />
            审批问题
          </div>
          <div className="whitespace-pre-wrap text-[0.98rem] leading-7 text-[var(--color-ink)]">
            {turn.prompt?.trim() || "这一轮没有捕获到直接用户问题。"}
          </div>
        </section>

        <section className="pixel-card-soft p-4">
          <div className="pixel-label mb-3 flex items-center gap-2">
            <Sparkles size={14} />
            建议草案
          </div>
          <div className="whitespace-pre-wrap text-[0.98rem] leading-7 text-[var(--color-ink-soft)]">
            {turn.answer?.trim() || (turn.streaming ? "正在生成回复..." : "没有文本回复。")}
          </div>
        </section>
      </div>

      {turn.runMeta ? (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="pixel-tag">{turn.runMeta.status}</span>
          <span className="pixel-tag">{turn.runMeta.orchestration_engine || "langgraph"}</span>
          {turn.runMeta.thread_id ? (
            <span className="mono text-[0.92rem] text-[var(--color-ink-soft)]">
              thread {turn.runMeta.thread_id}
            </span>
          ) : null}
        </div>
      ) : null}

      <div className="mt-4">
        {turn.hitlEvents.length ? (
          <div className="pixel-card-soft mb-4 px-4 py-3 text-sm text-[var(--color-ink-soft)]">
            <p className="pixel-label mb-3">HITL 复核轨迹</p>
            <div className="space-y-2">
              {turn.hitlEvents.map((item, index) => (
                <div key={`${item.type}-${item.checkpoint_id}-${index}`} className="flex flex-wrap items-center gap-2">
                  <span className="pixel-tag">{item.type}</span>
                  <span>{item.display_name}</span>
                  <span className="pixel-tag">{item.risk_level}</span>
                  {item.request_id ? (
                    <span className="mono text-[0.92rem] text-[var(--color-ink-soft)]">
                      请求 {item.request_id}
                    </span>
                  ) : null}
                  {item.decision_id ? (
                    <span className="mono text-[0.92rem] text-[var(--color-ink-soft)]">
                      决策 {item.decision_id}
                    </span>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {turn.checkpointEvents.length ? (
          <div className="pixel-card-soft mb-4 px-4 py-3 text-sm text-[var(--color-ink-soft)]">
            <p className="pixel-label mb-3">checkpoint 轨迹</p>
            <div className="space-y-2">
              {turn.checkpointEvents.map((item, index) => (
                <div key={`${item.type}-${item.checkpoint_id}-${index}`} className="flex flex-wrap items-center gap-2">
                  <span className="pixel-tag">{item.type}</span>
                  <span className="mono text-[0.92rem] text-[var(--color-ink-soft)]">
                    {item.checkpoint_id || "等待中的 checkpoint"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {turn.retrievalSteps.length ? <RetrievalCard steps={turn.retrievalSteps} /> : null}
        {turn.toolCalls.length ? <ThoughtChain toolCalls={turn.toolCalls} /> : null}
        {!hasTrace ? (
          <div className="pixel-card-soft px-4 py-3 text-sm text-[var(--color-ink-soft)]">
            这一轮没有产生检索或 workflow 轨迹。
          </div>
        ) : null}
      </div>
    </article>
  );
});

function CaseTurnTraceSummary({ turn }: { turn: ErpApprovalCaseTurnResponse | null | undefined }) {
  if (!turn) {
    return (
      <div className="pixel-card-soft px-6 py-8">
        <p className="pixel-label">案件运行轨迹</p>
        <h3 className="pixel-title mt-3 text-[1rem] text-[var(--color-ink)]">还没有案件 turn</h3>
        <p className="pixel-note mt-4 max-w-3xl">
          在“案件工作台”里和 Agent 完成一轮交互后，这里会展示本轮经过的 LangGraph 节点、模型角色和案卷写入事件。
        </p>
      </div>
    );
  }

  const patch = object(turn.patch);
  const modelReview = object(patch.model_review);
  const harnessRun = object(turn.harness_run);
  const graphSteps = list(harnessRun.graph_steps);
  const roleOutputs = records(modelReview.stage_model_role_outputs);
  const auditEvents = records(turn.audit_events);

  return (
    <div className="trace-scroll-area flex-1 overflow-y-auto pr-2">
      <section className="pixel-card p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="pixel-label">案件本轮路径</p>
            <h3 className="pixel-title mt-2 text-[1rem] text-[var(--color-ink)]">
              {turn.case_state.approval_id || turn.case_state.case_id}
            </h3>
            <p className="pixel-note mt-2">
              {displayLabel(patch.turn_intent)} / {displayLabel(patch.patch_type)} / 案卷 v{turn.case_state.dossier_version}
            </p>
          </div>
          <span className="pixel-tag">{text(turn.operation_scope, "local case turn")}</span>
        </div>

        <div className="mt-4 grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          <section className="pixel-card-soft p-4">
            <p className="pixel-label mb-3">LangGraph steps</p>
            <div className="flex flex-wrap gap-2">
              {(graphSteps.length ? graphSteps : ["未返回 graph_steps"]).map((step) => (
                <span className="pixel-tag" key={step}>{step}</span>
              ))}
            </div>
          </section>

          <section className="pixel-card-soft p-4">
            <p className="pixel-label mb-3">LLM 角色状态</p>
            {roleOutputs.length ? (
              <div className="space-y-2">
                {roleOutputs.map((role, index) => (
                  <div className="flex items-center justify-between gap-3 rounded-[8px] border border-[var(--color-line)] px-3 py-2 text-sm" key={`${text(role.role)}-${index}`}>
                    <span className="text-[var(--color-ink)]">{text(role.role, "unknown_role")}</span>
                    <span className="text-[var(--color-ink-muted)]">{text(role.status, "unknown")}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-[var(--color-ink-soft)]">本轮没有返回 LLM 角色明细。</p>
            )}
          </section>
        </div>

        <section className="pixel-card-soft mt-4 p-4">
          <p className="pixel-label mb-3">案卷审计事件</p>
          {auditEvents.length ? (
            <div className="space-y-2">
              {auditEvents.slice(0, 24).map((event, index) => (
                <div className="rounded-[8px] border border-[var(--color-line)] px-3 py-2 text-sm text-[var(--color-ink-soft)]" key={`${text(event.event)}-${index}`}>
                  <span className="pixel-tag mr-2">{text(event.event, text(event.event_type, "event"))}</span>
                  <span>{text(event.message, text(event.reason, text(event.turn_intent, "")))}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-[var(--color-ink-soft)]">本轮没有返回案卷审计事件。</p>
          )}
        </section>

        <p className="mt-4 text-xs text-[var(--color-ink-muted)]">{turn.non_action_statement}</p>
      </section>
    </div>
  );
}

export function TracePanel({ turn }: { turn?: ErpApprovalCaseTurnResponse | null }) {
  const { messages, streamingMessages, isStreaming } = useChatStore();
  const [view, setView] = useState<"case" | "execution" | "context" | "llm">("case");
  const turnCacheRef = useRef(
    new Map<
      string,
      {
        source: ReturnType<typeof useChatStore>["messages"][number];
        prompt: string | null;
        streaming: boolean;
        turn: TraceTurn;
      }
    >()
  );

  const turns = useMemo(() => {
    const combined = [...messages, ...streamingMessages];
    const streamingIds = new Set(streamingMessages.map((item) => item.id));
    const nextCache = new Map<
      string,
      {
        source: ReturnType<typeof useChatStore>["messages"][number];
        prompt: string | null;
        streaming: boolean;
        turn: TraceTurn;
      }
    >();
    const nextTurns: TraceTurn[] = [];
    let lastUserPrompt: string | null = null;

    for (const message of combined) {
      if (message.role === "user") {
        lastUserPrompt = message.content;
        continue;
      }

      const streaming = isStreaming && streamingIds.has(message.id);
      const cached = turnCacheRef.current.get(message.id);

      if (cached && cached.source === message && cached.prompt === lastUserPrompt && cached.streaming === streaming) {
        nextCache.set(message.id, cached);
        nextTurns.push(cached.turn);
        continue;
      }

      const turn: TraceTurn = {
        id: message.id,
        prompt: lastUserPrompt,
        answer: message.content,
        toolCalls: message.toolCalls,
        retrievalSteps: message.retrievalSteps,
        usage: message.usage,
        runMeta: message.runMeta,
        checkpointEvents: message.checkpointEvents,
        hitlEvents: message.hitlEvents,
        streaming
      };

      nextCache.set(message.id, { source: message, prompt: lastUserPrompt, streaming, turn });
      nextTurns.push(turn);
    }

    turnCacheRef.current = nextCache;
    return nextTurns.reverse();
  }, [isStreaming, messages, streamingMessages]);

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      <div className="panel flex min-h-0 flex-1 flex-col px-4 pb-4 pt-4">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="pixel-label">审计轨迹</p>
            <h3 className="pixel-title mt-2 text-[1rem] text-[var(--color-ink)]">案件运行路径、模型角色和审计事件</h3>
            <p className="pixel-note mt-2 max-w-3xl">
              默认展示用户能理解的本轮案卷轨迹；模型上下文和 Markdown 文件保留在调试入口里，需要时再展开。
            </p>
          </div>
        </div>
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <button
            className={`pixel-button px-4 py-2 text-sm ${view === "case" ? "is-active" : ""}`}
            onClick={() => setView("case")}
            type="button"
          >
            案件本轮路径
          </button>
          <button
            className={`pixel-button px-4 py-2 text-sm ${view === "execution" ? "is-active" : ""}`}
            onClick={() => setView("execution")}
            type="button"
          >
            聊天运行事件
          </button>
          <button
            className={`pixel-button px-4 py-2 text-sm ${view === "context" ? "is-active" : ""}`}
            onClick={() => setView("context")}
            type="button"
          >
            上下文调试
          </button>
          <button
            className={`pixel-button px-4 py-2 text-sm ${view === "llm" ? "is-active" : ""}`}
            onClick={() => setView("llm")}
            type="button"
          >
            Markdown 调试
          </button>
        </div>

        {view === "case" ? (
          <CaseTurnTraceSummary turn={turn} />
        ) : view === "llm" ? (
          <div className="trace-scroll-area flex-1 overflow-y-auto pr-2">
            <LlmContextLibraryPanel />
          </div>
        ) : view === "context" ? (
          <div className="trace-scroll-area flex-1 overflow-y-auto pr-2">
            <ContextTracePanel />
          </div>
        ) : !turns.length ? (
          <div className="trace-scroll-area flex-1 overflow-y-auto pr-2">
            <div className="pixel-card-soft px-6 py-8">
              <p className="pixel-label">ready</p>
              <h3 className="pixel-title mt-3 text-[1rem] text-[var(--color-ink)]">
                需要时再打开 Audit Trace
              </h3>
              <p className="pixel-note mt-4 max-w-3xl">
                检索、workflow tools、checkpoint 事件和 HITL 都集中在这里，不会挤占默认案件工作台。
              </p>
            </div>
          </div>
        ) : (
          <VirtualizedStack
            className="trace-scroll-area flex-1 overflow-y-auto pr-2"
            estimateHeight={TRACE_ITEM_ESTIMATE}
            getKey={(turn) => turn.id}
            items={turns}
            renderItem={(turn) => (
              <div className="pb-4">
                <TraceTurnCard turn={turn} />
              </div>
            )}
          />
        )}
      </div>
    </section>
  );
}
