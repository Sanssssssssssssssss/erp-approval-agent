"use client";

import { AlertTriangle, ClipboardCheck, FilePlus2, FileSearch, ListChecks, RotateCcw, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  type ErpApprovalCaseReviewEvidenceInput,
  type ErpApprovalCaseReviewResponse,
  reviewErpApprovalCase
} from "@/lib/api";

const SAMPLE_REQUEST =
  "请审核采购申请 PR-1001，申请部门 Operations，金额 24500 USD，供应商 Acme Supplies，成本中心 OPS-CC-10，用途是 replacement laptops。请给出证据清单、缺口、风险和 reviewer memo。";

const ONE_SENTENCE_TEST = "帮我直接通过这个采购申请，老板已经同意了，不需要 citation。";

const EVIDENCE_TYPES = [
  ["approval_request", "审批单"],
  ["budget", "预算记录"],
  ["vendor", "供应商记录"],
  ["quote", "报价/比价"],
  ["purchase_order", "PO 采购订单"],
  ["goods_receipt", "GRN 收货记录"],
  ["invoice", "发票"],
  ["receipt", "报销收据"],
  ["policy", "政策/制度"],
  ["sanctions_check", "制裁检查"],
  ["bank_info", "银行信息"],
  ["tax_info", "税务信息"],
  ["contract", "合同/框架协议"],
  ["payment_terms", "付款条款"],
  ["duplicate_check", "重复检查"]
];

const STATUS_LABELS: Record<string, string> = {
  recommend_approve: "建议通过（仅建议）",
  recommend_reject: "建议拒绝",
  request_more_info: "需要补充证据",
  escalate: "升级人工复核",
  blocked: "已阻断"
};

function text(value: unknown, fallback = "未提供") {
  const rendered = String(value ?? "").trim();
  return rendered || fallback;
}

function boolLabel(value: unknown) {
  return value === true || String(value).toLowerCase() === "true" ? "是" : "否";
}

function arrayOfRecords(value: unknown) {
  return Array.isArray(value) ? (value.filter((item) => item && typeof item === "object") as Array<Record<string, unknown>>) : [];
}

function arrayOfText(value: unknown) {
  return Array.isArray(value) ? value.map((item) => String(item ?? "").trim()).filter(Boolean) : [];
}

function statusClass(status: unknown) {
  const value = text(status, "").toLowerCase();
  if (["satisfied", "pass", "recommend_approve"].includes(value)) return "case-chip case-chip-ok";
  if (["conflict", "fail", "blocked", "recommend_reject"].includes(value)) return "case-chip case-chip-danger";
  if (["missing", "partial", "request_more_info", "escalate"].includes(value)) return "case-chip case-chip-warn";
  return "case-chip";
}

function Section({
  title,
  icon,
  children
}: {
  title: string;
  icon?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="case-review-section">
      <h3>
        {icon}
        {title}
      </h3>
      {children}
    </section>
  );
}

function RecommendationHeader({ result }: { result: ErpApprovalCaseReviewResponse }) {
  const recommendation = result.recommendation ?? {};
  const sufficiency = result.evidence_sufficiency ?? {};
  const control = result.control_matrix ?? {};
  const status = text(recommendation.status, "request_more_info");
  const blockingGaps = arrayOfText(sufficiency.blocking_gaps);

  return (
    <div className="case-review-hero">
      <div>
        <p className="pixel-label">本地证据先行审查结论</p>
        <h2>{STATUS_LABELS[status] ?? status}</h2>
        <p>{text(recommendation.summary, "当前没有形成摘要。")}</p>
      </div>
      <div className="case-review-kpis">
        <div>
          <span>证据充分性</span>
          <strong>{boolLabel(sufficiency.passed)}</strong>
          <small>完整度 {text(sufficiency.completeness_score, "0")}</small>
        </div>
        <div>
          <span>控制矩阵</span>
          <strong>{boolLabel(control.passed)}</strong>
          <small>{arrayOfText(control.missing_check_ids).length + arrayOfText(control.failed_check_ids).length} 个缺口</small>
        </div>
        <div>
          <span>人工复核</span>
          <strong>{boolLabel(recommendation.human_review_required)}</strong>
          <small>{blockingGaps.length ? `${blockingGaps.length} 个阻断证据缺口` : "无阻断缺口"}</small>
        </div>
      </div>
    </div>
  );
}

function RequiredEvidence({ result }: { result: ErpApprovalCaseReviewResponse }) {
  return (
    <div className="case-checklist">
      {result.evidence_requirements.map((item) => (
        <div className="case-checklist-row" key={text(item.requirement_id)}>
          <span className={statusClass(item.status)}>{text(item.status)}</span>
          <strong>{text(item.label)}</strong>
          <small>{item.blocking ? "阻断必需" : "参考/条件"} · {text(item.requirement_id)}</small>
        </div>
      ))}
    </div>
  );
}

function EvidenceClaims({ result }: { result: ErpApprovalCaseReviewResponse }) {
  const claims = result.evidence_claims.slice(0, 28);
  return (
    <div className="case-table">
      {claims.length ? (
        claims.map((claim) => (
          <div className="case-table-row" key={text(claim.claim_id)}>
            <span className={statusClass(claim.verification_status)}>{text(claim.verification_status)}</span>
            <div>
              <strong>{text(claim.claim_type)}</strong>
              <p>{text(claim.statement, "无说明")}</p>
              <code>{text(claim.source_id)}</code>
            </div>
          </div>
        ))
      ) : (
        <p className="case-empty">没有抽取到可用于满足证据要求的 claims。</p>
      )}
    </div>
  );
}

function Sufficiency({ result }: { result: ErpApprovalCaseReviewResponse }) {
  const sufficiency = result.evidence_sufficiency;
  const gaps = arrayOfText(sufficiency.blocking_gaps);
  const questions = arrayOfText(sufficiency.next_questions);
  return (
    <div className="case-two-col">
      <div>
        <p className="pixel-label">阻断缺口</p>
        {gaps.length ? (
          <ul>{gaps.map((gap) => <li key={gap}>{gap}</li>)}</ul>
        ) : (
          <p className="case-empty">没有阻断缺口。</p>
        )}
      </div>
      <div>
        <p className="pixel-label">补证问题</p>
        {questions.length ? (
          <ul>{questions.map((question) => <li key={question}>{question}</li>)}</ul>
        ) : (
          <p className="case-empty">没有补证问题。</p>
        )}
      </div>
    </div>
  );
}

function ControlMatrix({ result }: { result: ErpApprovalCaseReviewResponse }) {
  const checks = arrayOfRecords(result.control_matrix.checks);
  return (
    <div className="case-checklist">
      {checks.map((check) => (
        <div className="case-checklist-row" key={text(check.check_id)}>
          <span className={statusClass(check.status)}>{text(check.status)}</span>
          <strong>{text(check.label)}</strong>
          <small>{text(check.severity)} · {text(check.explanation, "无说明")}</small>
        </div>
      ))}
    </div>
  );
}

function EvidenceArtifacts({ result }: { result: ErpApprovalCaseReviewResponse }) {
  const artifacts = result.evidence_artifacts.filter((item) => text(item.source_id, "").startsWith("user_statement://") === false);
  return (
    <div className="case-artifacts">
      {artifacts.slice(0, 18).map((artifact) => (
        <div className="case-artifact-card" key={text(artifact.artifact_id)}>
          <div>
            <strong>{text(artifact.title)}</strong>
            <span>{text(artifact.record_type)}</span>
          </div>
          <code>{text(artifact.source_id)}</code>
          <p>{text(artifact.content, "").slice(0, 180)}</p>
        </div>
      ))}
    </div>
  );
}

function ReviewerMemo({ result }: { result: ErpApprovalCaseReviewResponse }) {
  return (
    <div className="case-review-memo markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{result.reviewer_memo}</ReactMarkdown>
    </div>
  );
}

export function CaseReviewPanel() {
  const [message, setMessage] = useState(SAMPLE_REQUEST);
  const [evidenceTitle, setEvidenceTitle] = useState("");
  const [evidenceType, setEvidenceType] = useState("quote");
  const [evidenceContent, setEvidenceContent] = useState("");
  const [extraEvidence, setExtraEvidence] = useState<ErpApprovalCaseReviewEvidenceInput[]>([]);
  const [result, setResult] = useState<ErpApprovalCaseReviewResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const canSubmit = message.trim().length > 0 && !loading;
  const requestSummary = useMemo(() => result?.approval_request ?? {}, [result]);

  const addEvidence = () => {
    if (!evidenceContent.trim()) return;
    setExtraEvidence((items) => [
      ...items,
      {
        title: evidenceTitle.trim() || EVIDENCE_TYPES.find(([value]) => value === evidenceType)?.[1] || "本地文本证据",
        record_type: evidenceType,
        content: evidenceContent.trim()
      }
    ]);
    setEvidenceTitle("");
    setEvidenceContent("");
  };

  const runReview = async () => {
    if (!message.trim()) return;
    setLoading(true);
    setError("");
    try {
      const response = await reviewErpApprovalCase({
        user_message: message,
        extra_evidence: extraEvidence
      });
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "本地 case review 失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="case-review-page">
      <div className="case-review-layout">
        <aside className="case-review-input panel">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="pixel-label">案件审查默认入口</p>
              <h2>证据先行审批案件</h2>
            </div>
            <ShieldCheck className="text-[var(--color-success)]" size={22} />
          </div>
          <p className="mt-3 text-sm leading-6 text-[var(--color-ink-soft)]">
            提交审批案件后，系统先检查必需证据、claims、充分性、冲突和控制矩阵。证据不足时不能建议通过。
          </p>

          <label className="pixel-label mt-5 block">审批请求</label>
          <textarea
            className="case-review-textarea"
            onChange={(event) => setMessage(event.target.value)}
            value={message}
          />
          <div className="mt-3 flex flex-wrap gap-2">
            <button className="ui-button" onClick={() => setMessage(SAMPLE_REQUEST)} type="button">
              PR-1001 示例
            </button>
            <button className="ui-button" onClick={() => setMessage(ONE_SENTENCE_TEST)} type="button">
              一句话防线测试
            </button>
          </div>

          <div className="case-evidence-builder">
            <p className="pixel-label">补充本地文本证据</p>
            <input
              className="case-review-input-field"
              onChange={(event) => setEvidenceTitle(event.target.value)}
              placeholder="证据标题，例如：PR-1001 报价单"
              value={evidenceTitle}
            />
            <select
              className="case-review-input-field"
              onChange={(event) => setEvidenceType(event.target.value)}
              value={evidenceType}
            >
              {EVIDENCE_TYPES.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <textarea
              className="case-review-textarea case-review-textarea-small"
              onChange={(event) => setEvidenceContent(event.target.value)}
              placeholder="粘贴本地证据文本。示例：Quote Q-PR-1001-A from Acme Supplies for USD 24,500..."
              value={evidenceContent}
            />
            <button className="ui-button" onClick={addEvidence} type="button">
              <FilePlus2 size={15} />
              加入证据
            </button>
          </div>

          {extraEvidence.length ? (
            <div className="case-local-evidence-list">
              {extraEvidence.map((item, index) => (
                <div key={`${item.record_type}-${index}`}>
                  <strong>{item.title || "本地证据"}</strong>
                  <span>{item.record_type}</span>
                  <button
                    aria-label="移除证据"
                    onClick={() => setExtraEvidence((items) => items.filter((_, itemIndex) => itemIndex !== index))}
                    type="button"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          ) : null}

          {error ? <p className="case-error">{error}</p> : null}
          <button className="ui-button ui-button-primary mt-4 w-full" disabled={!canSubmit} onClick={() => void runReview()} type="button">
            <RotateCcw size={16} />
            {loading ? "正在本地审查..." : "开始本地证据审查"}
          </button>
          <p className="mt-3 text-xs leading-5 text-[var(--color-ink-muted)]">
            No ERP write action was executed. 本视图不会连接真实 ERP，不会执行通过、驳回、付款、路由或评论。
          </p>
        </aside>

        <div className="case-review-output">
          {!result ? (
            <div className="case-review-empty panel">
              <FileSearch size={32} />
              <h2>等待提交审批案件</h2>
              <p>提交后会生成案件概览、必备证据清单、证据 Claims、证据充分性、控制矩阵、冲突检测、建议和 reviewer memo。</p>
            </div>
          ) : (
            <>
              <RecommendationHeader result={result} />

              <div className="case-review-request-strip">
                <span>审批类型：{text(requestSummary.approval_type)}</span>
                <span>审批单：{text(requestSummary.approval_id, "未识别")}</span>
                <span>供应商：{text(requestSummary.vendor)}</span>
                <span>金额：{text(requestSummary.amount)} {text(requestSummary.currency, "")}</span>
              </div>

              <Section icon={<ListChecks size={18} />} title="必备证据清单">
                <RequiredEvidence result={result} />
              </Section>

              <Section icon={<FileSearch size={18} />} title="证据材料">
                <EvidenceArtifacts result={result} />
              </Section>

              <Section icon={<FileSearch size={18} />} title="证据 Claims">
                <EvidenceClaims result={result} />
              </Section>

              <Section icon={<AlertTriangle size={18} />} title="证据充分性">
                <Sufficiency result={result} />
              </Section>

              <Section icon={<ListChecks size={18} />} title="控制矩阵">
                <ControlMatrix result={result} />
              </Section>

              <Section icon={<AlertTriangle size={18} />} title="冲突检测">
                <p className={Boolean(result.contradictions.has_conflict) ? "case-conflict case-conflict-danger" : "case-conflict"}>
                  {text(result.contradictions.explanation, "未发现明确结构化冲突。")}
                </p>
              </Section>

              <Section icon={<ClipboardCheck size={18} />} title="建议 / Reviewer memo">
                <ReviewerMemo result={result} />
              </Section>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
