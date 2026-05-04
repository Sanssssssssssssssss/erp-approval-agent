"use client";

import { BrainCircuit, ClipboardList, Database, GitBranch, Network, Save, ShieldCheck, Wrench } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import {
  getErpApprovalCaseGraph,
  saveErpApprovalCasePrompt,
  type ErpApprovalCaseGraphResponse,
  type ErpApprovalCasePrompt,
  type ErpApprovalCaseTurnResponse
} from "@/lib/api";

import { LlmContextLibraryPanel } from "./LlmContextLibraryPanel";
import {
  boolLabel,
  displayLabel,
  list,
  object,
  policyRagEvidences,
  policyRagPlan,
  policyRagTraceFromModelReview,
  records,
  text
} from "./caseInsightUtils";

type PanelProps = {
  turn: ErpApprovalCaseTurnResponse | null;
};

function Section({
  children,
  icon,
  kicker,
  title
}: {
  children: ReactNode;
  icon: ReactNode;
  kicker: string;
  title: string;
}) {
  return (
    <section className="pixel-card p-4">
      <div className="mb-3 flex items-start gap-3">
        <span className="pixel-tag mt-1 inline-flex items-center gap-2">{icon}</span>
        <div>
          <p className="pixel-label">{kicker}</p>
          <h3 className="mt-1 text-[1rem] font-semibold text-[var(--color-ink)]">{title}</h3>
        </div>
      </div>
      {children}
    </section>
  );
}

function EmptyInsights() {
  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="panel flex min-h-0 flex-1 items-center justify-center p-8">
        <div className="max-w-xl text-center">
          <ShieldCheck className="mx-auto mb-4 text-[var(--color-ink-muted)]" size={34} />
          <p className="pixel-label">高级洞察</p>
          <h2 className="mt-2 text-xl font-semibold text-[var(--color-ink)]">还没有可解释的案件轮次</h2>
          <p className="mt-3 text-sm leading-6 text-[var(--color-ink-soft)]">
            先在案件工作台里描述审批案件、询问材料清单或提交证据。Agent 完成一轮审查后，这里会展示本轮解释、制度依据、案卷变化、图路径和 system prompt。
          </p>
          <p className="mt-4 text-xs text-[var(--color-ink-muted)]">No ERP write action was executed.</p>
        </div>
      </div>
    </section>
  );
}

function getModelReview(turn: ErpApprovalCaseTurnResponse) {
  return object(object(turn.patch).model_review);
}

function getPatch(turn: ErpApprovalCaseTurnResponse) {
  return object(turn.patch);
}

export function AgentInsightSummary({ turn }: PanelProps) {
  if (!turn) return null;
  const patch = getPatch(turn);
  const modelReview = getModelReview(turn);
  const agentReply = object(modelReview.agent_reply);
  const caseState = turn.case_state;
  const accepted = records(patch.accepted_evidence);
  const rejected = records(patch.rejected_evidence);
  const policyFailures = records(patch.policy_failures);
  const wroteCase =
    accepted.length > 0 ||
    rejected.length > 0 ||
    policyFailures.length > 0 ||
    text(patch.patch_type, "") !== "no_case_change";

  return (
    <Section icon={<ClipboardList size={15} />} kicker="本轮解释" title="Agent 这一轮做了什么">
      <div className="grid gap-3 md:grid-cols-2">
        <div className="insight-tile">
          <p className="pixel-label">识别意图</p>
          <p className="mt-1 text-sm text-[var(--color-ink)]">{displayLabel(patch.turn_intent)}</p>
        </div>
        <div className="insight-tile">
          <p className="pixel-label">处理方式</p>
          <p className="mt-1 text-sm text-[var(--color-ink)]">{displayLabel(patch.patch_type)}</p>
        </div>
        <div className="insight-tile">
          <p className="pixel-label">是否写入案卷</p>
          <p className="mt-1 text-sm text-[var(--color-ink)]">{boolLabel(wroteCase)}</p>
        </div>
        <div className="insight-tile">
          <p className="pixel-label">当前阶段</p>
          <p className="mt-1 text-sm text-[var(--color-ink)]">{displayLabel(caseState.stage)}</p>
        </div>
      </div>
      <div className="mt-3 rounded-md border border-[var(--color-border)] bg-[var(--color-surface-muted)] p-3 text-sm leading-6 text-[var(--color-ink-soft)]">
        {text(agentReply.markdown, text(agentReply.body, "模型没有返回 agent_reply.markdown；请查看图路径和模型角色状态。"))}
      </div>
      {caseState.next_questions?.length ? (
        <div className="mt-3">
          <p className="pixel-label mb-2">下一步建议</p>
          <ul className="space-y-1 text-sm text-[var(--color-ink-soft)]">
            {caseState.next_questions.slice(0, 5).map((item) => (
              <li key={item}>- {item}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </Section>
  );
}

export function PolicyEvidencePanel({ turn }: PanelProps) {
  if (!turn) return null;
  const modelReview = getModelReview(turn);
  const trace = policyRagTraceFromModelReview(modelReview);
  const plan = policyRagPlan(trace);
  const evidences = policyRagEvidences(trace);
  const rewrittenQueries = list(plan.rewritten_queries);
  const queryHints = list(plan.query_hints);

  return (
    <Section icon={<Database size={15} />} kicker="制度依据" title="Policy RAG 与制度命中">
      {Object.keys(trace).length === 0 ? (
        <p className="text-sm text-[var(--color-ink-soft)]">本轮没有可展示的制度命中。若你在问材料清单或退回原因，请重新提问一次，Agent 会优先走政策检索。</p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[0.8fr_1.2fr]">
          <div className="space-y-3">
            <div className="insight-tile">
              <p className="pixel-label">RAG 状态</p>
              <p className="mt-1 text-sm text-[var(--color-ink)]">{text(trace.status, "已执行")}</p>
            </div>
            <div className="insight-tile">
              <p className="pixel-label">Query rewrite</p>
              <ul className="mt-2 space-y-1 text-sm text-[var(--color-ink-soft)]">
                {(rewrittenQueries.length ? rewrittenQueries : ["本轮没有 rewrite 结果"]).slice(0, 5).map((item) => (
                  <li key={item}>- {item}</li>
                ))}
              </ul>
            </div>
            <div className="insight-tile">
              <p className="pixel-label">Query hints</p>
              <ul className="mt-2 space-y-1 text-sm text-[var(--color-ink-soft)]">
                {(queryHints.length ? queryHints : ["暂无 hint"]).slice(0, 5).map((item) => (
                  <li key={item}>- {item}</li>
                ))}
              </ul>
            </div>
          </div>
          <div className="space-y-2">
            {evidences.length ? (
              evidences.slice(0, 8).map((item, index) => (
                <article className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-muted)] p-3" key={`${text(item.source_path)}-${index}`}>
                  <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--color-ink-muted)]">
                    <span>{text(item.source_path, "policy source")}</span>
                    <span>{text(item.locator, "locator 未提供")}</span>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-[var(--color-ink-soft)]">{text(item.snippet, "没有 snippet")}</p>
                </article>
              ))
            ) : (
              <p className="text-sm text-[var(--color-ink-soft)]">本轮没有可展示的 policy snippet。</p>
            )}
          </div>
        </div>
      )}
    </Section>
  );
}

export function CaseChangePanel({ turn }: PanelProps) {
  if (!turn) return null;
  const patch = getPatch(turn);
  const state = turn.case_state;
  const accepted = records(patch.accepted_evidence);
  const rejected = records(patch.rejected_evidence);
  const failures = records(patch.policy_failures);

  return (
    <Section icon={<Network size={15} />} kicker="案卷变化" title="本轮写入、退回和案卷版本">
      <div className="mb-4 grid gap-3 md:grid-cols-3">
        <div className="insight-tile">
          <p className="pixel-label">案卷阶段</p>
          <p className="mt-1 text-sm text-[var(--color-ink)]">{displayLabel(state.stage)}</p>
        </div>
        <div className="insight-tile">
          <p className="pixel-label">Dossier 版本</p>
          <p className="mt-1 text-sm text-[var(--color-ink)]">v{state.dossier_version}</p>
        </div>
        <div className="insight-tile">
          <p className="pixel-label">轮次</p>
          <p className="mt-1 text-sm text-[var(--color-ink)]">{state.turn_count}</p>
        </div>
      </div>
      <div className="grid gap-3 lg:grid-cols-3">
        <ChangeList title="接受材料" items={accepted} empty="本轮没有接受新材料" />
        <ChangeList title="退回材料" items={rejected} empty="本轮没有退回材料" />
        <ChangeList title="制度失败" items={failures} empty="本轮没有新的制度失败" />
      </div>
    </Section>
  );
}

function ChangeList({ title, items, empty }: { title: string; items: Array<Record<string, unknown>>; empty: string }) {
  return (
    <div className="insight-tile">
      <p className="pixel-label mb-2">{title}</p>
      {items.length ? (
        <ul className="space-y-2 text-sm text-[var(--color-ink-soft)]">
          {items.slice(0, 8).map((item, index) => (
            <li key={`${title}-${index}`}>
              <span className="font-medium text-[var(--color-ink)]">{text(item.title, text(item.source_id, `第 ${index + 1} 项`))}</span>
              <p className="mt-1 text-xs text-[var(--color-ink-muted)]">{text(item.reason, text(item.why_failed, ""))}</p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-[var(--color-ink-muted)]">{empty}</p>
      )}
    </div>
  );
}

export function GraphTracePanel({ turn }: PanelProps) {
  if (!turn) return null;
  const harnessRun = object(turn.harness_run);
  const modelReview = getModelReview(turn);
  const roleOutputs = records(modelReview.stage_model_role_outputs);
  const steps = list(harnessRun.graph_steps);

  return (
    <Section icon={<GitBranch size={15} />} kicker="图路径与模型" title="本轮经过的节点和 LLM 角色">
      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <p className="pixel-label mb-2">Graph steps</p>
          <div className="flex flex-wrap gap-2">
            {(steps.length ? steps : ["未返回 graph_steps"]).map((step) => (
              <span className="pixel-tag" key={step}>{step}</span>
            ))}
          </div>
        </div>
        <div>
          <p className="pixel-label mb-2">模型角色状态</p>
          {roleOutputs.length ? (
            <div className="space-y-2">
              {roleOutputs.map((role, index) => (
                <div className="flex items-center justify-between rounded-md border border-[var(--color-border)] px-3 py-2 text-sm" key={`${text(role.role)}-${index}`}>
                  <span>{text(role.role, "unknown_role")}</span>
                  <span className="text-[var(--color-ink-muted)]">{text(role.status, "unknown")}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-[var(--color-ink-soft)]">本轮没有返回 LLM role 明细；请检查模型配置或 graph 输出。</p>
          )}
        </div>
      </div>
    </Section>
  );
}

export function PromptGraphPanel({ turn }: PanelProps) {
  const activeSteps = useMemo(() => new Set(list(object(turn?.harness_run).graph_steps)), [turn]);
  const [graph, setGraph] = useState<ErpApprovalCaseGraphResponse | null>(null);
  const [selectedPrompt, setSelectedPrompt] = useState<ErpApprovalCasePrompt | null>(null);
  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    let mounted = true;
    void getErpApprovalCaseGraph()
      .then((response) => {
        if (!mounted) return;
        setGraph(response);
        const first = response.prompts.find((prompt) => prompt.editable) ?? response.prompts[0] ?? null;
        setSelectedPrompt(first);
        setDraft(first?.prompt ?? "");
      })
      .catch((error: unknown) => {
        if (mounted) setStatus(error instanceof Error ? error.message : "加载图谱失败");
      });
    return () => {
      mounted = false;
    };
  }, []);

  const promptByNode = useMemo(() => {
    const map = new Map<string, ErpApprovalCasePrompt[]>();
    for (const prompt of graph?.prompts ?? []) {
      const current = map.get(prompt.node_id) ?? [];
      current.push(prompt);
      map.set(prompt.node_id, current);
    }
    return map;
  }, [graph]);

  async function savePrompt() {
    if (!selectedPrompt) return;
    setStatus("正在保存...");
    try {
      await saveErpApprovalCasePrompt(selectedPrompt.prompt_id, draft);
      setStatus("已保存到本地 prompt override。");
      setGraph((current) =>
        current
          ? {
              ...current,
              prompts: current.prompts.map((prompt) =>
                prompt.prompt_id === selectedPrompt.prompt_id ? { ...prompt, prompt: draft, overridden: true } : prompt
              )
            }
          : current
      );
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "保存失败");
    }
  }

  return (
    <Section icon={<BrainCircuit size={15} />} kicker="Agent 图谱" title="节点 system prompt 可视化与本地编辑">
      {!graph ? (
        <p className="text-sm text-[var(--color-ink-soft)]">{status || "正在加载图谱..."}</p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[0.95fr_1.05fr]">
          <div>
            <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-[var(--color-ink-muted)]">
              <span className="pixel-tag">{graph.graph_name}</span>
              <span>高亮节点表示本轮 graph_steps 经过。</span>
            </div>
            <div className="case-graph-node-grid">
              {graph.nodes.map((node) => {
                const prompts = promptByNode.get(node.node_id) ?? [];
                return (
                  <button
                    className={[
                      "case-graph-node",
                      node.editable ? "is-editable" : "",
                      activeSteps.has(node.node_id) ? "is-active" : ""
                    ].filter(Boolean).join(" ")}
                    key={node.node_id}
                    onClick={() => {
                      const prompt = prompts[0] ?? null;
                      setSelectedPrompt(prompt);
                      setDraft(prompt?.prompt ?? "");
                      setStatus("");
                    }}
                    type="button"
                  >
                    <span>{node.label || node.node_id}</span>
                    <small>{node.node_id}</small>
                  </button>
                );
              })}
            </div>
          </div>
          <div className="case-prompt-editor">
            {selectedPrompt ? (
              <>
                <div className="mb-3 flex items-start justify-between gap-3">
                  <div>
                    <p className="pixel-label">{selectedPrompt.category}</p>
                    <h4 className="mt-1 font-semibold text-[var(--color-ink)]">{selectedPrompt.label}</h4>
                    <p className="mt-1 text-xs leading-5 text-[var(--color-ink-muted)]">{selectedPrompt.description}</p>
                  </div>
                  {selectedPrompt.overridden ? <span className="pixel-tag">已覆盖</span> : null}
                </div>
                <textarea
                  className="pixel-textarea min-h-[320px] font-mono text-xs leading-5"
                  onChange={(event) => setDraft(event.target.value)}
                  value={draft}
                />
                <div className="mt-3 flex items-center justify-between gap-3">
                  <p className="text-xs text-[var(--color-ink-muted)]">{status || "保存只会写入本地 prompt override，不会执行任何 ERP 动作。"}</p>
                  <button className="pixel-button pixel-button-primary" onClick={() => void savePrompt()} type="button">
                    <Save size={15} />
                    保存 prompt
                  </button>
                </div>
              </>
            ) : (
              <p className="text-sm text-[var(--color-ink-soft)]">请选择一个带 prompt 的节点。</p>
            )}
          </div>
        </div>
      )}
    </Section>
  );
}

export function DeveloperDebugPanel() {
  return (
    <Section icon={<Wrench size={15} />} kicker="开发者调试" title="Raw context / Markdown 文件">
      <details>
        <summary className="cursor-pointer text-sm font-medium text-[var(--color-ink)]">展开 LLM Markdown 与当前上下文</summary>
        <div className="mt-4">
          <LlmContextLibraryPanel compact />
        </div>
      </details>
    </Section>
  );
}

export function AdvancedInsightsPanel({ turn }: PanelProps) {
  if (!turn) return <EmptyInsights />;

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="panel min-h-0 flex-1 overflow-y-auto p-4">
        <div className="mb-4">
          <p className="pixel-label">高级洞察</p>
          <h2 className="mt-1 text-xl font-semibold text-[var(--color-ink)]">案件解释、制度依据和 Agent 图谱</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--color-ink-soft)]">
            这里优先展示用户能理解的案件解释。Raw context 和 Markdown 文件被放在开发者调试里，默认折叠。
          </p>
        </div>
        <div className="grid gap-4">
          <AgentInsightSummary turn={turn} />
          <PolicyEvidencePanel turn={turn} />
          <CaseChangePanel turn={turn} />
          <GraphTracePanel turn={turn} />
          <PromptGraphPanel turn={turn} />
          <DeveloperDebugPanel />
        </div>
      </div>
    </section>
  );
}
