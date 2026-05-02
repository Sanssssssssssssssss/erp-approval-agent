"use client";

import { memo, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { MessageUsage, RetrievalStep, RunMeta, ToolCall } from "@/lib/api";

/**
 * Returns one human-readable usage label from one usage object input and formats the token summary for a turn.
 */
function formatTokenUsage(usage: MessageUsage) {
  return `输入 ${usage.input_tokens.toLocaleString()} | 输出 ${usage.output_tokens.toLocaleString()} tokens`;
}

const DOODLE_FRAMES = ["[+__+]", "[+o_+]", "[+O_+]", "[+o_+]", "[+__+]", "[+^^+]"];

function runStatusLabel(status: string) {
  const normalized = status.toLowerCase();
  if (normalized === "interrupted") return "等待复核";
  if (normalized === "resumed") return "已恢复";
  if (normalized === "completed" || normalized === "success") return "已完成";
  if (normalized === "running") return "运行中";
  if (normalized === "failed" || normalized === "error") return "失败";
  return status;
}

function StreamingThinking() {
  const [frameIndex, setFrameIndex] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setFrameIndex((value) => (value + 1) % DOODLE_FRAMES.length);
    }, 180);

    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="doodle-thinking" aria-label="思考中">
      <span className="doodle-frame mono">{DOODLE_FRAMES[frameIndex]}</span>
      <span className="mono">思考中...</span>
    </div>
  );
}

function lineValue(content: string, labels: string[]) {
  const line = content
    .split(/\r?\n/)
    .find((item) => labels.some((label) => item.includes(label)));
  if (!line) return "";
  const cleaned = line.replace(/^[-*\s]+/, "");
  const parts = cleaned.split(/[：:]/);
  return parts.length > 1 ? parts.slice(1).join("：").trim() : cleaned.trim();
}

function collectBulletsAfter(content: string, anchor: string, limit = 4) {
  const lines = content.split(/\r?\n/);
  const start = lines.findIndex((line) => line.includes(anchor));
  if (start < 0) return [];
  const bullets: string[] = [];
  for (let index = start + 1; index < lines.length; index += 1) {
    const line = lines[index];
    if (line.startsWith("## ")) break;
    const match = line.match(/^\s*-\s+(.+)/);
    if (match?.[1]) {
      bullets.push(match[1].trim());
    } else if (bullets.length && line.trim() && !line.startsWith(" ")) {
      break;
    }
    if (bullets.length >= limit) break;
  }
  return bullets;
}

function extractEvidenceLinks(content: string) {
  return content
    .split(/\r?\n/)
    .filter((line) => line.includes("证据位置"))
    .map((line) => line.replace(/^[-*\s]+/, "").replace(/^证据位置[：:]\s*/, "").trim())
    .filter(Boolean)
    .slice(0, 4);
}

function isApprovalCaseAnswer(content: string) {
  return (
    /Case overview|Required evidence checklist|Control matrix checks|审批建议|证据充分性/.test(content) &&
    /No ERP write action was executed|未执行任何 ERP/.test(content)
  );
}

function ApprovalAnswerSummary({ content }: { content: string }) {
  if (!isApprovalCaseAnswer(content)) return null;

  const approvalId = lineValue(content, ["审批单号", "审批单"]);
  const approvalType = lineValue(content, ["审批类型"]);
  const recommendation = lineValue(content, ["当前建议"]) || "未识别";
  const nextAction = lineValue(content, ["下一步"]) || "人工复核";
  const sufficiencyPassed = lineValue(content, ["passed"]) || "false";
  const completeness = lineValue(content, ["completeness_score"]) || "0.00";
  const gaps = collectBulletsAfter(content, "blocking gaps", 4);
  const questions = collectBulletsAfter(content, "建议补证问题", 3);
  const links = extractEvidenceLinks(content);
  const evidenceEnough = sufficiencyPassed.toLowerCase().includes("true");
  const approveLike = recommendation.includes("通过");

  return (
    <aside className="approval-answer-summary">
      <div className="approval-answer-head">
        <div>
          <p className="pixel-label">审批案件速览</p>
          <h3>{recommendation}</h3>
        </div>
        <span className={approveLike ? "approval-status approval-status-ok" : "approval-status approval-status-warn"}>
          {nextAction}
        </span>
      </div>

      <div className="approval-summary-grid">
        <div>
          <p>审批单</p>
          <strong>{approvalType || "未知类型"} / {approvalId || "未识别"}</strong>
        </div>
        <div>
          <p>证据充分性</p>
          <strong>{evidenceEnough ? "通过" : "不足"}</strong>
          <span>完整度 {completeness}</span>
        </div>
        <div>
          <p>缺口</p>
          <strong>{gaps.length ? `${gaps.length} 项阻断` : "无阻断缺口"}</strong>
          <span>{questions.length ? "已生成补证问题" : "无补证问题"}</span>
        </div>
        <div>
          <p>边界</p>
          <strong>不执行 ERP</strong>
          <span>只形成本地审查建议</span>
        </div>
      </div>

      {gaps.length ? (
        <div className="approval-summary-block">
          <p className="pixel-label">关键阻断缺口</p>
          <ul>
            {gaps.map((gap) => (
              <li key={gap}>{gap}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {links.length ? (
        <div className="approval-summary-block">
          <p className="pixel-label">证据材料</p>
          <div className="approval-evidence-links">
            {links.map((link) => (
              <code key={link}>{link}</code>
            ))}
          </div>
        </div>
      ) : null}
    </aside>
  );
}

/**
 * Returns one rendered chat message from role, content, and usage inputs and keeps the main chat lightweight.
 */
export const ChatMessage = memo(function ChatMessage({
  role,
  content,
  usage,
  runMeta,
  streaming = false
}: {
  role: "user" | "assistant";
  content: string;
  toolCalls?: ToolCall[];
  retrievalSteps?: RetrievalStep[];
  usage: MessageUsage | null;
  runMeta?: RunMeta | null;
  streaming?: boolean;
}) {
  const isUser = role === "user";
  const articleRef = useRef<HTMLElement | null>(null);
  const [canRenderMarkdown, setCanRenderMarkdown] = useState(isUser || streaming);

  useEffect(() => {
    if (isUser || streaming || canRenderMarkdown) {
      return;
    }

    const node = articleRef.current;
    if (!node || typeof IntersectionObserver === "undefined") {
      setCanRenderMarkdown(true);
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setCanRenderMarkdown(true);
          observer.disconnect();
        }
      },
      {
        root: null,
        rootMargin: "320px 0px"
      }
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, [canRenderMarkdown, isUser, streaming]);

  const shouldRenderPlainText = isUser || streaming || !canRenderMarkdown;

  return (
    <article
      className={`message-card max-w-[92%] px-4 py-3 ${
        isUser
          ? "pixel-card-soft ml-auto text-[var(--color-ink)]"
          : "pixel-card mr-auto text-[var(--color-ink)]"
      }`}
      ref={articleRef}
    >
      {!isUser && runMeta ? (
        <div className="mb-3 flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-[var(--color-ink-muted)]">
          <span className="pixel-tag">
            {runStatusLabel(runMeta.status)}
          </span>
          {runMeta.orchestration_engine ? (
            <span className="pixel-tag">{runMeta.orchestration_engine}</span>
          ) : null}
          {runMeta.trace_available ? (
            <span className="pixel-tag">trace</span>
          ) : null}
          {runMeta.studio_debuggable ? (
            <span className="pixel-tag">studio</span>
          ) : null}
          {runMeta.checkpoint_id ? (
            <span className="mono rounded-[4px] border border-[var(--color-line)] bg-[var(--color-bg)] px-2 py-1 text-[0.84rem] normal-case tracking-normal text-[var(--color-ink-soft)]">
              checkpoint {runMeta.checkpoint_id.slice(0, 8)}
            </span>
          ) : null}
        </div>
      ) : null}
      <div
        className={
          shouldRenderPlainText
            ? "whitespace-pre-wrap text-[0.98rem] leading-7 text-[var(--color-ink)]"
            : "markdown"
        }
      >
        {shouldRenderPlainText ? (
          content ||
          (runMeta?.status === "interrupted"
            ? "执行前需要人工复核。"
            : streaming
              ? <StreamingThinking />
              : "")
        ) : (
          <>
            <ApprovalAnswerSummary content={content} />
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {content || (runMeta?.status === "interrupted" ? "执行前需要人工复核。" : "思考中...")}
            </ReactMarkdown>
          </>
        )}
      </div>
      {!isUser && usage && (
        <div className="mono mt-4 border-t border-solid border-[var(--color-line)] pt-3 text-[0.9rem] text-[var(--color-ink-soft)]">
          {formatTokenUsage(usage)}
        </div>
      )}
    </article>
  );
});
