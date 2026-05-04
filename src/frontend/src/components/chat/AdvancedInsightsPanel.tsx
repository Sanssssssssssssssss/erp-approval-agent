"use client";

import { BrainCircuit, ClipboardList, Database, GitBranch, ShieldCheck, Wrench } from "lucide-react";
import type { ReactNode } from "react";

import type { ErpApprovalCaseTurnResponse } from "@/lib/api";

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
            先在“案件工作台”里描述审批案件或提交材料。Agent 完成一轮审查后，这里会展示本轮解释、制度依据、案卷变化、图路径和模型状态。
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

function getHarnessRun(turn: ErpApprovalCaseTurnResponse) {
  return object(turn.harness_run);
}

function getNextSuggestions(turn: ErpApprovalCaseTurnResponse) {
  const patch = getPatch(turn);
  const modelReview = getModelReview(turn);
  const casePlan = object(modelReview.case_supervisor_plan || turn.case_state.case_plan);
  return [
    ...list(patch.next_questions),
    ...list(turn.case_state.next_questions),
    ...list(casePlan.next_actions),
    ...list(casePlan.next_questions)
  ].slice(0, 5);
}

export function AgentInsightSummary({ turn }: { turn: ErpApprovalCaseTurnResponse }) {
  const patch = getPatch(turn);
  const modelReview = getModelReview(turn);
  const intent = text(patch.turn_intent || modelReview.turn_intent, "未识别");
  const patchType = text(patch.patch_type, "no_case_change");
  const writeApplied = Boolean(patch.applied || patch.case_written || patch.persisted || patchType === "accept_evidence");
  const status = text(turn.review.recommendation?.status || turn.case_state.recommendation?.status || patch.status, "继续收集材料");
  const suggestions = getNextSuggestions(turn);

  return (
    <Section icon={<ClipboardList size={14} />} kicker="1. 本轮解释" title="Agent 本轮做了什么">
      <div className="grid gap-3 md:grid-cols-2">
        <div className="pixel-card-soft p-3">
          <p className="pixel-label">用户意图</p>
          <p className="mt-2 text-sm text-[var(--color-ink)]">{displayLabel(intent)}</p>
        </div>
        <div className="pixel-card-soft p-3">
          <p className="pixel-label">处理方式</p>
          <p className="mt-2 text-sm text-[var(--color-ink)]">{displayLabel(patchType)}</p>
        </div>
        <div className="pixel-card-soft p-3">
          <p className="pixel-label">是否写入案卷</p>
          <p className="mt-2 text-sm text-[var(--color-ink)]">{boolLabel(writeApplied)}</p>
        </div>
        <div className="pixel-card-soft p-3">
          <p className="pixel-label">当前结果</p>
          <p className="mt-2 text-sm text-[var(--color-ink)]">{displayLabel(status)}</p>
        </div>
      </div>
      <div className="mt-4">
        <p className="pixel-label">下一步建议</p>
        {suggestions.length ? (
          <ul className="case-agent-list mt-2">
            {suggestions.map((item, index) => (
              <li key={`${item}-${index}`}>{item}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-[var(--color-ink-soft)]">本轮没有新的补证建议。可以查看右侧案卷清单或请求生成 reviewer memo。</p>
        )}
      </div>
    </Section>
  );
}

function requirementLabelsForPolicy(turn: ErpApprovalCaseTurnResponse, evidence: Record<string, unknown>) {
  const source = text(evidence.source_path || evidence.source_id, "");
  const requirements = records(turn.case_state.evidence_requirements);
  const matched = requirements
    .filter((requirement) => {
      const refs = list(requirement.policy_refs);
      return source && refs.some((ref) => source.includes(ref) || ref.includes(source));
    })
    .map((requirement) => text(requirement.label || requirement.requirement_id));
  return matched.length ? matched : ["用于核对本轮材料要求与制度条款"];
}

export function PolicyEvidencePanel({ turn }: { turn: ErpApprovalCaseTurnResponse }) {
  const modelReview = getModelReview(turn);
  const policyTrace = policyRagTraceFromModelReview(modelReview);
  const policyPlan = policyRagPlan(policyTrace);
  const policyEvidences = policyRagEvidences(policyTrace);
  const rewrittenQueries = list(policyPlan.rewritten_queries || policyTrace.query_rewrite || policyTrace.rewritten_queries);
  const queryHints = list(policyPlan.query_hints || policyTrace.query_hints);
  const plannerStatus = text(policyTrace.planner_status || policyPlan.planner_status || policyTrace.model_status, "未触发");
  const retrievalStatus = text(policyTrace.retrieval_status || policyTrace.status, "未检索");

  return (
    <Section icon={<Database size={14} />} kicker="2. 制度依据" title="Policy RAG 与制度命中">
      <div className="grid gap-3 md:grid-cols-3">
        <div className="pixel-card-soft p-3">
          <p className="pixel-label">RAG 状态</p>
          <p className="mt-2 text-sm text-[var(--color-ink)]">{retrievalStatus}</p>
        </div>
        <div className="pixel-card-soft p-3">
          <p className="pixel-label">Query rewrite</p>
          <p className="mt-2 text-sm text-[var(--color-ink)]">{plannerStatus}</p>
        </div>
        <div className="pixel-card-soft p-3">
          <p className="pixel-label">命中条款</p>
          <p className="mt-2 text-sm text-[var(--color-ink)]">{policyEvidences.length} 条</p>
        </div>
      </div>

      {rewrittenQueries.length ? (
        <div className="mt-4">
          <p className="pixel-label">模型改写后的查询</p>
          <ul className="case-agent-list mt-2">
            {rewrittenQueries.slice(0, 5).map((query) => (
              <li key={query}>{query}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {queryHints.length ? (
        <div className="mt-4">
          <p className="pixel-label">查询提示词</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {queryHints.slice(0, 10).map((hint) => (
              <span className="pixel-tag" key={hint}>
                {hint}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      <div className="mt-4">
        <p className="pixel-label">制度片段</p>
        {policyEvidences.length ? (
          <div className="mt-3 grid gap-3 lg:grid-cols-2">
            {policyEvidences.slice(0, 6).map((evidence, index) => (
              <article className="pixel-card-soft p-3" key={`${text(evidence.source_path)}-${text(evidence.locator)}-${index}`}>
                <p className="text-sm font-semibold text-[var(--color-ink)]">{text(evidence.title || evidence.source_path, "制度片段")}</p>
                <p className="mt-1 text-xs text-[var(--color-ink-muted)]">
                  {text(evidence.source_path, "unknown")} · {text(evidence.locator, "unknown")}
                </p>
                <p className="mt-3 text-sm leading-6 text-[var(--color-ink-soft)]">{text(evidence.snippet, "没有 snippet")}</p>
                <p className="mt-3 text-xs text-[var(--color-ink-muted)]">
                  支持材料要求：{requirementLabelsForPolicy(turn, evidence).join(" / ")}
                </p>
              </article>
            ))}
          </div>
        ) : (
          <p className="mt-2 text-sm text-[var(--color-ink-soft)]">
            本轮没有可展示的制度命中。这里不会展示 raw 错误；请查看图路径与模型状态，或补充更明确的材料/制度线索。
          </p>
        )}
      </div>
    </Section>
  );
}

export function CaseChangePanel({ turn }: { turn: ErpApprovalCaseTurnResponse }) {
  const patch = getPatch(turn);
  const accepted = records(patch.accepted_evidence).length ? records(patch.accepted_evidence) : records(turn.case_state.accepted_evidence).slice(-6);
  const rejected = records(patch.rejected_evidence).length ? records(patch.rejected_evidence) : records(turn.case_state.rejected_evidence).slice(-6);
  const policyFailures = records(patch.policy_failures).length ? records(patch.policy_failures) : records(turn.case_state.policy_failures).slice(-6);

  return (
    <Section icon={<ShieldCheck size={14} />} kicker="3. 案卷变化" title="本轮写入、退回与状态变化">
      <div className="grid gap-3 md:grid-cols-3">
        <div className="pixel-card-soft p-3">
          <p className="pixel-label">案卷阶段</p>
          <p className="mt-2 text-sm text-[var(--color-ink)]">{displayLabel(turn.case_state.stage)}</p>
        </div>
        <div className="pixel-card-soft p-3">
          <p className="pixel-label">Dossier version</p>
          <p className="mt-2 text-sm text-[var(--color-ink)]">v{turn.case_state.dossier_version}</p>
        </div>
        <div className="pixel-card-soft p-3">
          <p className="pixel-label">Case turn</p>
          <p className="mt-2 text-sm text-[var(--color-ink)]">{turn.case_state.turn_count} 轮</p>
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <div>
          <p className="pixel-label">本轮接受的材料</p>
          {accepted.length ? (
            <ul className="case-agent-list mt-2">
              {accepted.map((item, index) => (
                <li key={`${text(item.source_id || item.title)}-${index}`}>{text(item.title || item.source_id || item.evidence_id, "已接受材料")}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-[var(--color-ink-soft)]">本轮没有新增接受材料。</p>
          )}
        </div>
        <div>
          <p className="pixel-label">本轮退回的材料</p>
          {rejected.length ? (
            <ul className="case-agent-list mt-2">
              {rejected.map((item, index) => (
                <li key={`${text(item.source_id || item.title)}-${index}`}>{text(item.title || item.source_id || item.reason, "被退回材料")}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-[var(--color-ink-soft)]">本轮没有退回材料。</p>
          )}
        </div>
        <div>
          <p className="pixel-label">制度不符合项</p>
          {policyFailures.length ? (
            <ul className="case-agent-list mt-2">
              {policyFailures.map((item, index) => (
                <li key={`${text(item.requirement_id)}-${index}`}>
                  {text(item.requirement_id, "制度要求")}：{text(item.why_failed || item.how_to_fix, "需要补充制度可追溯材料")}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-[var(--color-ink-soft)]">暂无未解决的制度失败项。</p>
          )}
        </div>
      </div>
    </Section>
  );
}

function roleOutputs(modelReview: Record<string, unknown>) {
  const candidates = [
    records(modelReview.stage_model_role_outputs),
    records(modelReview.llm_role_outputs),
    records(modelReview.role_outputs),
    records(modelReview.stage_outputs)
  ];
  return candidates.find((items) => items.length > 0) ?? [];
}

export function GraphTracePanel({ turn }: { turn: ErpApprovalCaseTurnResponse }) {
  const patch = getPatch(turn);
  const modelReview = getModelReview(turn);
  const harnessRun = getHarnessRun(turn);
  const graphName = text(harnessRun.graph_name || harnessRun.graph || "erp_approval_dynamic_case_turn_graph");
  const graphSteps = list(harnessRun.graph_steps || modelReview.graph_steps || patch.graph_steps);
  const roles = roleOutputs(modelReview);
  const modelStatus = text(modelReview.stage_model_status || modelReview.model_status || modelReview.status, "未报告");

  return (
    <Section icon={<GitBranch size={14} />} kicker="4. 图路径与模型" title="LangGraph 路径和 LLM 角色状态">
      <div className="grid gap-3 md:grid-cols-2">
        <div className="pixel-card-soft p-3">
          <p className="pixel-label">Graph</p>
          <p className="mt-2 text-sm text-[var(--color-ink)]">{graphName}</p>
        </div>
        <div className="pixel-card-soft p-3">
          <p className="pixel-label">模型状态</p>
          <p className="mt-2 text-sm text-[var(--color-ink)]">{modelStatus}</p>
        </div>
      </div>

      <div className="mt-4">
        <p className="pixel-label">本轮图路径</p>
        {graphSteps.length ? (
          <div className="mt-2 flex flex-wrap gap-2">
            {graphSteps.map((step, index) => (
              <span className="pixel-tag" key={`${step}-${index}`}>
                {step}
              </span>
            ))}
          </div>
        ) : (
          <p className="mt-2 text-sm text-[var(--color-ink-soft)]">本轮没有返回 graph_steps。</p>
        )}
      </div>

      <div className="mt-4">
        <p className="pixel-label">LLM 角色</p>
        {roles.length ? (
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            {roles.map((role, index) => (
              <div className="pixel-card-soft p-3" key={`${text(role.role || role.name, "role")}-${index}`}>
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-semibold text-[var(--color-ink)]">{text(role.role || role.name, "LLM role")}</p>
                  <span className="pixel-tag">{text(role.status || role.model_status || role.result_status, "unknown")}</span>
                </div>
                <p className="mt-2 text-xs leading-5 text-[var(--color-ink-soft)]">
                  {text(role.summary || role.reason || role.error || role.output_summary, "没有返回摘要")}
                </p>
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-2 text-sm text-[var(--color-ink-soft)]">
            本轮没有可展示的 LLM role 明细。若模型被跳过或超时，本轮不会展示由模板拼出的业务审查结论。
          </p>
        )}
      </div>
    </Section>
  );
}

export function DeveloperDebugPanel() {
  return (
    <Section icon={<Wrench size={14} />} kicker="5. 开发者调试" title="原始上下文和 Markdown 文件">
      <details className="case-agent-details">
        <summary>展开开发者调试视图</summary>
        <div className="mt-3">
          <LlmContextLibraryPanel compact />
        </div>
      </details>
    </Section>
  );
}

export function AdvancedInsightsPanel({ turn }: PanelProps) {
  if (!turn) {
    return <EmptyInsights />;
  }

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="panel flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4">
        <header className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="pixel-label">高级洞察</p>
            <h2 className="mt-2 text-xl font-semibold text-[var(--color-ink)]">案件解释面板</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--color-ink-soft)]">
              这里按业务语言解释 Agent 本轮如何理解请求、使用了哪些制度依据、案卷发生了什么变化，以及模型和图路径是否正常。
            </p>
          </div>
          <div className="pixel-tag inline-flex items-center gap-2">
            <BrainCircuit size={14} />
            {turn.case_state.case_id || "当前案件"}
          </div>
        </header>

        <AgentInsightSummary turn={turn} />
        <PolicyEvidencePanel turn={turn} />
        <CaseChangePanel turn={turn} />
        <GraphTracePanel turn={turn} />
        <DeveloperDebugPanel />
      </div>
    </section>
  );
}
