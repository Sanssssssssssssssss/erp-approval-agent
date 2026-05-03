"use client";

import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  FilePlus2,
  FileSearch,
  ListChecks,
  MessageSquareText,
  RotateCcw,
  SendHorizontal,
  ShieldCheck
} from "lucide-react";
import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  applyErpApprovalCaseTurn,
  type ErpApprovalCaseReviewEvidenceInput,
  type ErpApprovalCaseReviewResponse,
  type ErpApprovalCaseTurnResponse
} from "@/lib/api";

const SAMPLE_REQUEST =
  "请审核采购申请 PR-1001，申请部门 Operations，金额 24500 USD，供应商 Acme Supplies，成本中心 OPS-CC-10，用途是 replacement laptops。请给出证据清单、缺口、风险和 reviewer memo。";

const ONE_SENTENCE_TEST = "帮我直接通过这个采购申请，老板已经同意了，不需要 citation。";

const ASK_STATUS_MESSAGE = "请告诉我当前案卷状态：已经接受了哪些材料，还缺哪些阻断证据，下一步最应该提交什么。";

const ASK_MATERIALS_MESSAGE = "请按当前审批类型列出必备材料清单，并说明每项材料为什么需要、什么样的材料才会被接受。";

const REQUEST_FINAL_MEMO_MESSAGE =
  "请尝试生成最终 reviewer memo。如果证据不足，请不要生成通过建议，只说明阻断缺口、风险和下一步补证问题。";

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

const STAGE_LABELS: Record<string, string> = {
  draft: "草稿",
  collecting_evidence: "收集中",
  escalation_review: "升级复核",
  ready_for_final_review: "可生成最终 memo",
  final_memo_ready: "memo 已生成",
  blocked: "已阻断"
};

const PATCH_LABELS: Record<string, string> = {
  create_case: "创建案卷",
  accept_evidence: "接受证据",
  reject_evidence: "退回材料",
  answer_status: "答复状态",
  final_memo: "最终 memo",
  no_case_change: "未改案卷"
};

const EVIDENCE_DECISION_LABELS: Record<string, string> = {
  accepted: "证据通过",
  rejected: "证据退回",
  needs_clarification: "需要澄清",
  not_evidence: "非证据输入"
};

const REQUIREMENT_STATUS_LABELS: Record<string, string> = {
  satisfied: "已满足",
  missing: "缺失",
  partial: "部分满足",
  conflict: "冲突",
  not_applicable: "不适用"
};

const CONTROL_STATUS_LABELS: Record<string, string> = {
  pass: "通过",
  fail: "失败",
  missing: "缺失",
  conflict: "冲突",
  not_applicable: "不适用"
};

const SAMPLE_EVIDENCE_BY_TYPE: Record<string, string> = {
  budget:
    "预算记录 BUD-OPS-2026-04：成本中心 OPS-CC-10，可用预算 USD 31,000；本次 PR-1001 申请金额 USD 24,500；预算负责人 Fiona Chen；记录状态 active。",
  vendor:
    "供应商准入记录 VEND-ACME-2026：供应商 Acme Supplies，状态 active；风险等级 low；制裁检查 clear；银行信息已验证；税务信息已验证。",
  quote:
    "报价单 Q-PR-1001-A：Acme Supplies 提供 replacement laptops 报价 USD 24,500；报价日期 2026-04-18；报价有效期 30 天；对应 PR-1001。",
  approval_request:
    "审批单 PR-1001：申请部门 Operations，申请人 Jordan Lee，成本中心 OPS-CC-10，采购 replacement laptops，金额 USD 24,500，业务目的为替换老旧办公电脑。",
  invoice:
    "发票 INV-3001：供应商 Acme Supplies，金额 USD 24,500，对应 PO-7788，发票日期 2026-04-24，付款条款 Net 30。",
  purchase_order:
    "采购订单 PO-7788：供应商 Acme Supplies，金额 USD 24,500，对应 PR-1001，采购 replacement laptops，状态 approved for receipt。",
  goods_receipt:
    "收货记录 GRN-8899：对应 PO-7788，已收货 replacement laptops，收货金额 USD 24,500，收货日期 2026-04-25。"
};

function text(value: unknown, fallback = "未提供") {
  const rendered = String(value ?? "").trim();
  return rendered || fallback;
}

const TEXT_FILE_EXTENSIONS = [".txt", ".md", ".json", ".csv", ".tsv", ".xml", ".log"];

function fileExtension(name: string) {
  const index = name.lastIndexOf(".");
  return index >= 0 ? name.slice(index).toLowerCase() : "";
}

function isTextEvidenceFile(file: File) {
  return file.type.startsWith("text/") || TEXT_FILE_EXTENSIONS.includes(fileExtension(file.name));
}

async function sha256File(file: File) {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest))
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
}

function sourceSlug(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9_.-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80) || "file";
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

function WorkspaceGroup({
  eyebrow,
  title,
  children
}: {
  eyebrow: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="case-workspace-group">
      <div className="case-workspace-group-header">
        <span>{eyebrow}</span>
        <h2>{title}</h2>
      </div>
      <div className="case-workspace-group-body">{children}</div>
    </div>
  );
}

function InputGroup({
  step,
  title,
  children
}: {
  step: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="case-input-group">
      <div className="case-input-group-title">
        <span>{step}</span>
        <strong>{title}</strong>
      </div>
      {children}
    </div>
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

function NextStepCard({
  result,
  turn,
  loading,
  onAskStatus,
  onAskMaterials,
  onRequestFinalMemo
}: {
  result: ErpApprovalCaseReviewResponse | null;
  turn: ErpApprovalCaseTurnResponse | null;
  loading: boolean;
  onAskStatus: () => void;
  onAskMaterials: () => void;
  onRequestFinalMemo: () => void;
}) {
  const sufficiency = result?.evidence_sufficiency ?? {};
  const control = result?.control_matrix ?? {};
  const recommendation = result?.recommendation ?? {};
  const blockingGaps = arrayOfText(sufficiency.blocking_gaps);
  const questions = arrayOfText(sufficiency.next_questions).concat(turn?.case_state.next_questions ?? []);
  const missingItems = turn?.case_state.missing_items ?? [];
  const readyForMemo = sufficiency.passed === true && control.passed === true;
  const status = text(recommendation.status, "request_more_info");

  if (!result) {
    return (
      <section className="case-next-step panel">
        <div>
          <p className="pixel-label">从这里开始</p>
          <h2>先创建审批案卷，再一轮一轮补材料</h2>
          <p>你可以只描述审批事项，Agent 会先列材料清单；也可以直接粘贴第一份预算、供应商、报价、发票、PO 或 GRN 材料。</p>
        </div>
        <div className="case-guided-actions">
          <button className="ui-button ui-button-primary" disabled={loading} onClick={onAskMaterials} type="button">
            <ListChecks size={16} />
            先问需要哪些材料
          </button>
          <button className="ui-button" disabled={loading} onClick={onAskStatus} type="button">
            <MessageSquareText size={16} />
            当前状态怎么判断
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className={readyForMemo ? "case-next-step case-next-step-ready panel" : "case-next-step panel"}>
      <div>
        <p className="pixel-label">下一步</p>
        <h2>{readyForMemo ? "证据和控制检查基本齐全，可以准备 reviewer memo" : "当前还不能形成通过建议"}</h2>
        <p>
          {readyForMemo
            ? "系统会继续保留 No ERP write action 边界；最终 memo 只是给人工 reviewer 的审查材料。"
            : STATUS_LABELS[status] ?? "需要继续补证。"}
        </p>
      </div>

      {!readyForMemo ? (
        <div className="case-next-step-body">
          <div>
            <strong>最关键缺口</strong>
            {blockingGaps.length || missingItems.length ? (
              <ul>
                {[...blockingGaps, ...missingItems].slice(0, 5).map((item, index) => (
                  <li key={`${item}-${index}`}>{item}</li>
                ))}
              </ul>
            ) : (
              <p>请继续提交能证明审批事实的材料，用户口头说明不会被当作强证据。</p>
            )}
          </div>
          <div>
            <strong>可以直接问 Agent</strong>
            {questions.length ? (
              <ul>
                {Array.from(new Set(questions)).slice(0, 4).map((item, index) => (
                  <li key={`${item}-${index}`}>{item}</li>
                ))}
              </ul>
            ) : (
              <p>让 Agent 汇总当前状态，或重新列出必备材料。</p>
            )}
          </div>
        </div>
      ) : null}

      <div className="case-guided-actions">
        <button className="ui-button ui-button-primary" disabled={loading} onClick={onAskStatus} type="button">
          <MessageSquareText size={16} />
          问当前还缺什么
        </button>
        <button className="ui-button" disabled={loading} onClick={onAskMaterials} type="button">
          <ListChecks size={16} />
          查看材料清单
        </button>
        <button className="ui-button" disabled={loading} onClick={onRequestFinalMemo} type="button">
          <ClipboardCheck size={16} />
          生成审查 memo
        </button>
      </div>
    </section>
  );
}

function CaseProgressPanel({ turn }: { turn: ErpApprovalCaseTurnResponse | null }) {
  if (!turn) return null;
  const state = turn.case_state;
  const patch = turn.patch ?? {};
  const accepted = state.accepted_evidence ?? [];
  const rejected = state.rejected_evidence ?? [];
  return (
    <section className="case-review-section case-progress-panel">
      <h3>
        <ClipboardCheck size={18} />
        案卷概览
      </h3>
      <div className="case-state-grid">
        <div>
          <span>案件编号</span>
          <strong>{state.case_id}</strong>
        </div>
        <div>
          <span>当前阶段</span>
          <strong>{STAGE_LABELS[state.stage] ?? state.stage}</strong>
        </div>
        <div>
          <span>已处理轮次 / 版本</span>
          <strong>{state.turn_count} / {state.dossier_version}</strong>
        </div>
        <div>
          <span>本轮处理结果</span>
          <strong>
            {PATCH_LABELS[text(patch.patch_type, "")] ?? text(patch.patch_type)} /{" "}
            {EVIDENCE_DECISION_LABELS[text(patch.evidence_decision, "")] ?? text(patch.evidence_decision)}
          </strong>
        </div>
      </div>
      <div className="case-two-col mt-3">
        <div>
          <p className="pixel-label">已接受证据</p>
          {accepted.length ? (
            <ul>{accepted.slice(-6).map((item) => <li key={text(item.source_id)}>{text(item.title || item.source_id)}</li>)}</ul>
          ) : (
            <p className="case-empty">暂无已接受证据。</p>
          )}
        </div>
        <div>
          <p className="pixel-label">被拒绝材料</p>
          {rejected.length ? (
            <ul>{rejected.slice(-6).map((item) => <li key={`${text(item.source_id)}-${text(item.rejected_at)}`}>{text(item.title || item.source_id)}</li>)}</ul>
          ) : (
            <p className="case-empty">暂无被拒绝材料。</p>
          )}
        </div>
      </div>
      {arrayOfText(patch.warnings).length ? (
        <div className="case-warning-list">
          {arrayOfText(patch.warnings).map((warning) => <p key={warning}>{warning}</p>)}
        </div>
      ) : null}
      <details className="case-technical-details">
        <summary>技术细节（调试时查看）</summary>
        <pre>{JSON.stringify({ patch, storage_paths: turn.storage_paths, audit_events: turn.audit_events }, null, 2)}</pre>
      </details>
    </section>
  );
}

function RequiredEvidence({ result }: { result: ErpApprovalCaseReviewResponse }) {
  return (
    <div className="case-checklist">
      {result.evidence_requirements.map((item) => (
        <div className="case-checklist-row" key={text(item.requirement_id)}>
          <span className={statusClass(item.status)}>{REQUIREMENT_STATUS_LABELS[text(item.status, "")] ?? text(item.status)}</span>
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
          <span className={statusClass(check.status)}>{CONTROL_STATUS_LABELS[text(check.status, "")] ?? text(check.status)}</span>
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
  const [fileEvidenceStatus, setFileEvidenceStatus] = useState("");
  const [result, setResult] = useState<ErpApprovalCaseReviewResponse | null>(null);
  const [caseTurn, setCaseTurn] = useState<ErpApprovalCaseTurnResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const canSubmit = (message.trim().length > 0 || extraEvidence.length > 0) && !loading;
  const requestSummary = useMemo(() => result?.approval_request ?? {}, [result]);

  const resetCaseWorkspace = () => {
    setResult(null);
    setCaseTurn(null);
    setExtraEvidence([]);
    setEvidenceTitle("");
    setEvidenceContent("");
    setFileEvidenceStatus("");
    setError("");
  };

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

  const insertSampleEvidence = () => {
    setEvidenceContent(SAMPLE_EVIDENCE_BY_TYPE[evidenceType] ?? "");
    setEvidenceTitle(EVIDENCE_TYPES.find(([value]) => value === evidenceType)?.[1] ?? "本地证据");
  };

  const addEvidenceFiles = async (files: FileList | null) => {
    const selected = Array.from(files ?? []);
    if (!selected.length) return;
    setFileEvidenceStatus("正在读取本地文件证据...");
    try {
      const fileEvidence = await Promise.all(
        selected.map(async (file) => {
          const sha256 = await sha256File(file);
          const canReadText = isTextEvidenceFile(file);
          const extractedText = canReadText ? await file.text() : "";
          const content = canReadText
            ? [
                `Local file evidence: ${file.name}`,
                `File type: ${file.type || "unknown"}`,
                `File size: ${file.size} bytes`,
                `SHA-256: ${sha256}`,
                "",
                extractedText
              ].join("\n")
            : [
                `Local file evidence: ${file.name}`,
                `File type: ${file.type || "unknown"}`,
                `File size: ${file.size} bytes`,
                `SHA-256: ${sha256}`,
                "",
                "This local file was registered as evidence metadata only. PDF/image OCR or signature validation has not been performed in this workspace yet, so this file cannot satisfy blocking evidence until text is extracted and reviewed."
              ].join("\n");
          return {
            title: file.name,
            record_type: canReadText ? evidenceType : "attachment",
            content,
            source_id: `local_file://${sourceSlug(file.name)}/${sha256.slice(0, 12)}`,
            metadata: {
              file_name: file.name,
              file_type: file.type || "unknown",
              file_size: file.size,
              sha256,
              extraction_mode: canReadText ? "browser_text_read" : "metadata_only_requires_pdf_or_ocr_extraction",
              authenticity_check: "sha256_recorded_only_not_full_forgery_detection"
            }
          };
        })
      );
      setExtraEvidence((items) => [...items, ...fileEvidence]);
      setFileEvidenceStatus(
        `${fileEvidence.length} 个文件已加入本轮证据；PDF/图片目前只登记哈希和元数据，不会假装已经 OCR 或验真。`
      );
    } catch (err) {
      setFileEvidenceStatus(err instanceof Error ? err.message : "读取本地文件失败");
    }
  };

  const submitCaseTurn = async (overrideMessage?: string, includePendingEvidence = true) => {
    const turnMessage =
      (overrideMessage ?? message).trim() ||
      (includePendingEvidence && extraEvidence.length ? "这是本轮补充材料，请审核是否可以写入当前审批案卷。" : "");
    if (!turnMessage) return;
    setLoading(true);
    setError("");
    try {
      const response = await applyErpApprovalCaseTurn({
        case_id: caseTurn?.case_state.case_id ?? "",
        user_message: turnMessage,
        extra_evidence: includePendingEvidence ? extraEvidence : []
      });
      setCaseTurn(response);
      setResult(response.review);
      if (includePendingEvidence) {
        setExtraEvidence([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "本地案卷状态更新失败");
    } finally {
      setLoading(false);
    }
  };

  const promptWithCurrentDraft = (instruction: string) => {
    if (caseTurn?.case_state.case_id) return instruction;
    return message.trim() ? `${message.trim()}\n\n${instruction}` : instruction;
  };

  const quickAskStatus = () => void submitCaseTurn(promptWithCurrentDraft(ASK_STATUS_MESSAGE), false);
  const quickAskMaterials = () => void submitCaseTurn(promptWithCurrentDraft(ASK_MATERIALS_MESSAGE), false);
  const quickRequestFinalMemo = () => void submitCaseTurn(promptWithCurrentDraft(REQUEST_FINAL_MEMO_MESSAGE), false);

  return (
    <section className="case-review-page">
      <div className="case-review-layout">
        <aside className="case-review-input panel">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="pixel-label">默认工作台</p>
              <h2>审批材料助手</h2>
            </div>
            <ShieldCheck className="text-[var(--color-success)]" size={22} />
          </div>
          <p className="mt-3 text-sm leading-6 text-[var(--color-ink-soft)]">
            目标不是一句话给审批结论，而是帮你把审批材料补齐：先建案卷，再逐轮审材料、抽证据、列缺口，最后生成给人工 reviewer 的 memo。
          </p>

          <div className="case-guided-actions case-guided-actions-vertical mt-4">
            <button className="ui-button ui-button-primary" disabled={loading} onClick={quickAskStatus} type="button">
              <MessageSquareText size={16} />
              问当前还缺什么
            </button>
            <button className="ui-button" disabled={loading} onClick={quickAskMaterials} type="button">
              <ListChecks size={16} />
              要必备材料清单
            </button>
            <button className="ui-button" disabled={loading} onClick={quickRequestFinalMemo} type="button">
              <ClipboardCheck size={16} />
              尝试生成审查 memo
            </button>
          </div>

          <InputGroup step="01" title="描述案件或直接问 Agent">
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
              <button className="ui-button" onClick={resetCaseWorkspace} type="button">
                新建案卷
              </button>
            </div>
          </InputGroup>

          <InputGroup step="02" title="提交本轮材料">
            <div className="case-evidence-builder">
              <p className="pixel-label">材料会先被审核，不能用的会退回</p>
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
              <div className="flex flex-wrap gap-2">
                <button className="ui-button" onClick={insertSampleEvidence} type="button">
                  插入该类型示例
                </button>
                <button className="ui-button ui-button-primary" onClick={addEvidence} type="button">
                  <FilePlus2 size={15} />
                  加入本轮材料
                </button>
              </div>
            </div>

            <div className="mt-3 space-y-2">
              <label className="ui-button cursor-pointer">
                <FilePlus2 size={15} />
                上传本地文件证据
                <input
                  className="sr-only"
                  multiple
                  onChange={(event) => void addEvidenceFiles(event.target.files)}
                  type="file"
                />
              </label>
              <p className="text-xs leading-5 text-[var(--color-ink-muted)]">
                文本、Markdown、JSON、CSV 会读取正文；PDF 或图片先登记文件名、大小和 SHA-256，暂不冒充 OCR 或真伪鉴定。
              </p>
              {fileEvidenceStatus ? (
                <p className="text-xs leading-5 text-[var(--color-ink-soft)]">{fileEvidenceStatus}</p>
              ) : null}
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
          </InputGroup>

          <InputGroup step="03" title="更新案卷">
            {error ? <p className="case-error">{error}</p> : null}
            <button className="ui-button ui-button-primary w-full" disabled={!canSubmit} onClick={() => void submitCaseTurn()} type="button">
              {loading ? <RotateCcw size={16} /> : <SendHorizontal size={16} />}
              {loading ? "正在审核本轮输入..." : "提交给 Agent 审核并更新案卷"}
            </button>
            <p className="mt-3 text-xs leading-5 text-[var(--color-ink-muted)]">
              No ERP write action was executed. 本视图不会连接真实 ERP，不会执行通过、驳回、付款、路由或评论。
            </p>
          </InputGroup>
        </aside>

        <div className="case-review-output">
          <NextStepCard
            loading={loading}
            onAskMaterials={quickAskMaterials}
            onAskStatus={quickAskStatus}
            onRequestFinalMemo={quickRequestFinalMemo}
            result={result}
            turn={caseTurn}
          />

          {!result ? (
            <div className="case-review-empty panel">
              <FileSearch size={32} />
              <h2>等待第一轮材料或案件描述</h2>
              <p>
                你不需要理解 trace 或 graph。只要告诉 Agent 这是采购、报销、发票付款、供应商准入、合同例外或预算例外，
                它会先告诉你要交哪些材料；之后每交一份材料，Agent 都会说明“能不能用、支持了哪项要求、还缺什么”。
              </p>
            </div>
          ) : (
            <>
              <WorkspaceGroup eyebrow="01" title="案件概览">
                <CaseProgressPanel turn={caseTurn} />
                <RecommendationHeader result={result} />

                <div className="case-review-request-strip">
                  <span>审批类型：{text(requestSummary.approval_type)}</span>
                  <span>审批单：{text(requestSummary.approval_id, "未识别")}</span>
                  <span>供应商：{text(requestSummary.vendor)}</span>
                  <span>金额：{text(requestSummary.amount)} {text(requestSummary.currency, "")}</span>
                </div>
              </WorkspaceGroup>

              <WorkspaceGroup eyebrow="02" title="还缺什么材料">
                <Section icon={<ListChecks size={18} />} title="必备材料清单">
                  <RequiredEvidence result={result} />
                </Section>

                <Section icon={<AlertTriangle size={18} />} title="证据充分性">
                  <Sufficiency result={result} />
                </Section>
              </WorkspaceGroup>

              <WorkspaceGroup eyebrow="03" title="Agent 已读到的证据">
                <Section icon={<FileSearch size={18} />} title="已登记材料">
                  <EvidenceArtifacts result={result} />
                </Section>

                <Section icon={<CheckCircle2 size={18} />} title="从材料中抽取的 claims">
                  <EvidenceClaims result={result} />
                </Section>
              </WorkspaceGroup>

              <WorkspaceGroup eyebrow="04" title="控制与 memo">
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
              </WorkspaceGroup>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
