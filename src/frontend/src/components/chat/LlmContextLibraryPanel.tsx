"use client";

import { BookOpenText, BrainCircuit, FileText, RefreshCcw, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { listWorkspaceMarkdownFiles, loadFile, type WorkspaceMarkdownFile } from "@/lib/api";
import { useChatStore } from "@/lib/store";

function formatSize(bytes: number) {
  if (!Number.isFinite(bytes)) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function shortContent(value: string, max = 2600) {
  const trimmed = value.trim();
  if (trimmed.length <= max) return trimmed;
  return `${trimmed.slice(0, max).trimEnd()}\n\n... 已截断，打开 Workspace 编辑器可看完整文件。`;
}

function contextBlockTitle(key: string) {
  const labels: Record<string, string> = {
    system_block: "System prompt / 不可变规则",
    history_block: "最近对话历史",
    working_memory_block: "Working memory",
    episodic_block: "案卷阶段摘要",
    semantic_block: "语义记忆命中",
    procedural_block: "流程/技能记忆命中",
    conversation_block: "会话召回",
    artifact_block: "工具/附件/产物",
    evidence_block: "RAG / 政策 / 证据片段"
  };
  return labels[key] ?? key;
}

export function LlmContextLibraryPanel({ compact = false }: { compact?: boolean }) {
  const { selectedContextCall, selectedContextTurn, contextTurnsLoading, refreshAssets } = useChatStore();
  const [mode, setMode] = useState<"context" | "files">("context");
  const [files, setFiles] = useState<WorkspaceMarkdownFile[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [selectedPath, setSelectedPath] = useState("");
  const [selectedContent, setSelectedContent] = useState("");
  const [fileQuery, setFileQuery] = useState("");
  const [error, setError] = useState("");

  const envelope = selectedContextCall?.context_envelope ?? selectedContextTurn?.context_envelope ?? null;
  const contextBlocks = useMemo(() => {
    if (!envelope) return [];
    return Object.entries(envelope)
      .filter(([key, value]) => key.endsWith("_block") && typeof value === "string" && value.trim())
      .map(([key, value]) => ({ key, title: contextBlockTitle(key), content: String(value) }));
  }, [envelope]);

  const loadCatalog = async () => {
    setFilesLoading(true);
    setError("");
    try {
      const payload = await listWorkspaceMarkdownFiles();
      const sorted = [...payload].sort((a, b) => a.category.localeCompare(b.category) || a.path.localeCompare(b.path));
      setFiles(sorted);
      const nextPath = selectedPath || sorted[0]?.path || "";
      if (nextPath) {
        setSelectedPath(nextPath);
        const file = await loadFile(nextPath);
        setSelectedContent(file.content);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "加载 Markdown 文件失败");
    } finally {
      setFilesLoading(false);
    }
  };

  useEffect(() => {
    if (mode === "files" && !files.length && !filesLoading) {
      void loadCatalog();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  const filteredFiles = useMemo(() => {
    const query = fileQuery.trim().toLowerCase();
    if (!query) return files;
    return files.filter((file) => `${file.path} ${file.category}`.toLowerCase().includes(query));
  }, [fileQuery, files]);

  const groupedFiles = useMemo(() => {
    const groups = new Map<string, WorkspaceMarkdownFile[]>();
    for (const file of filteredFiles) {
      const current = groups.get(file.category) ?? [];
      current.push(file);
      groups.set(file.category, current);
    }
    return Array.from(groups.entries());
  }, [filteredFiles]);

  const selectFile = async (path: string) => {
    setSelectedPath(path);
    setSelectedContent("");
    setError("");
    try {
      const file = await loadFile(path);
      setSelectedContent(file.content);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "加载文件失败");
    }
  };

  return (
    <section className={compact ? "pixel-card-soft p-4" : "pixel-card p-4"}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="pixel-label">LLM 调试视图</p>
          <h3 className="pixel-title mt-2 text-[1rem] text-[var(--color-ink)]">
            当前上下文与 Markdown 知识文件
          </h3>
          <p className="pixel-note mt-2 max-w-3xl">
            这里展示模型本轮真正可见的上下文块，以及 workspace / memory / skills / knowledge 下会进入提示或 RAG 的 Markdown 文件。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className={`ui-button ${mode === "context" ? "ui-button-primary" : ""}`} onClick={() => setMode("context")} type="button">
            <BrainCircuit size={15} />
            当前上下文
          </button>
          <button className={`ui-button ${mode === "files" ? "ui-button-primary" : ""}`} onClick={() => setMode("files")} type="button">
            <BookOpenText size={15} />
            Markdown 文件
          </button>
          <button
            className="ui-button"
            disabled={filesLoading || contextTurnsLoading}
            onClick={() => (mode === "files" ? void loadCatalog() : void refreshAssets())}
            type="button"
          >
            <RefreshCcw size={15} />
            刷新
          </button>
        </div>
      </div>

      {error ? <div className="mt-4 pixel-card-soft px-4 py-3 text-sm text-[var(--color-danger)]">{error}</div> : null}

      {mode === "context" ? (
        <div className="mt-4 grid gap-4 xl:grid-cols-[280px_minmax(0,1fr)]">
          <div className="pixel-card-soft p-3">
            <p className="pixel-label">上下文块</p>
            <div className="mt-3 space-y-2">
              {contextBlocks.length ? (
                contextBlocks.map((block) => (
                  <div className="rounded-[8px] border border-[var(--color-line)] px-3 py-2 text-sm" key={block.key}>
                    <p className="text-[var(--color-ink)]">{block.title}</p>
                    <p className="mt-1 text-xs text-[var(--color-ink-muted)]">{block.content.length.toLocaleString()} chars</p>
                  </div>
                ))
              ) : (
                <p className="pixel-note">还没有可展示的模型上下文。先完成一轮 Agent 回复后再看这里。</p>
              )}
            </div>
          </div>
          <div className="grid gap-3">
            {contextBlocks.length ? (
              contextBlocks.map((block) => (
                <details className="case-agent-details pixel-card-soft p-4" key={block.key} open={block.key === "system_block" || block.key === "evidence_block"}>
                  <summary>{block.title}</summary>
                  <pre className="mt-3 max-h-[360px] overflow-auto whitespace-pre-wrap text-sm leading-6 text-[var(--color-ink-soft)]">
                    {shortContent(block.content)}
                  </pre>
                </details>
              ))
            ) : (
              <div className="pixel-card-soft px-4 py-6 text-sm text-[var(--color-ink-soft)]">
                暂无上下文快照。
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="mt-4 grid min-h-[520px] gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
          <aside className="pixel-card-soft min-h-0 p-3">
            <label className="relative block">
              <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-ink-muted)]" size={16} />
              <input
                className="pixel-field py-2 pl-10 pr-4 text-sm"
                onChange={(event) => setFileQuery(event.target.value)}
                placeholder="过滤 Markdown 文件"
                value={fileQuery}
              />
            </label>
            <div className="mt-3 max-h-[480px] overflow-y-auto pr-1">
              {filesLoading && !files.length ? (
                <p className="pixel-note px-2 py-3">正在加载 Markdown 文件...</p>
              ) : groupedFiles.length ? (
                groupedFiles.map(([category, group]) => (
                  <div className="mb-4" key={category}>
                    <p className="pixel-label mb-2">{category}</p>
                    <div className="space-y-2">
                      {group.map((file) => (
                        <button
                          className={file.path === selectedPath ? "llm-md-file-row is-active" : "llm-md-file-row"}
                          key={file.path}
                          onClick={() => void selectFile(file.path)}
                          type="button"
                        >
                          <FileText size={14} />
                          <span>{file.path}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                ))
              ) : (
                <p className="pixel-note px-2 py-3">没有匹配的 Markdown 文件。</p>
              )}
            </div>
          </aside>
          <section className="pixel-card-soft min-w-0 p-4">
            {selectedPath ? (
              <>
                <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="pixel-label">文件预览</p>
                    <h4 className="mt-2 break-all text-[var(--color-ink)]">{selectedPath}</h4>
                  </div>
                  <span className="pixel-tag">
                    {formatSize(files.find((file) => file.path === selectedPath)?.size_bytes ?? 0)}
                  </span>
                </div>
                <pre className="max-h-[520px] overflow-auto whitespace-pre-wrap rounded-[8px] border border-[var(--color-line)] bg-[rgba(10,13,17,0.38)] p-4 text-sm leading-6 text-[var(--color-ink-soft)]">
                  {shortContent(selectedContent, 7000) || "文件为空。"}
                </pre>
              </>
            ) : (
              <div className="flex min-h-[360px] items-center justify-center text-center text-sm text-[var(--color-ink-soft)]">
                选择左侧 Markdown 文件后预览内容。
              </div>
            )}
          </section>
        </div>
      )}
    </section>
  );
}
