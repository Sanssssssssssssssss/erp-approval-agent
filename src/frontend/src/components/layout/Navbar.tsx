"use client";

import { Database, FileText, Menu, Monitor, Pencil, Plus, Search, Wrench } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useRuntimeStore, useSessionStore } from "@/lib/store";

export function Navbar({
  onOpenSessions,
  onOpenFiles
}: {
  onOpenSessions: () => void;
  onOpenFiles: () => void;
}) {
  const { currentSessionTitle, createNewSession, renameCurrentSession, compressCurrentSession } =
    useSessionStore();
  const {
    ragMode,
    toggleRagMode,
    skillRetrievalEnabled,
    toggleSkillRetrieval,
    executionPlatform,
    updateExecutionPlatform,
    knowledgeIndexStatus,
    rebuildKnowledgeIndex,
    runtimeLoading
  } = useRuntimeStore();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!menuOpen) {
      return;
    }

    const onPointerDown = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };

    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [menuOpen]);

  const knowledgeLabel = knowledgeIndexStatus?.building
    ? "索引重建中"
    : knowledgeIndexStatus?.ready
      ? `已索引 ${knowledgeIndexStatus.indexed_files} 个文件`
      : "索引离线";

  return (
    <header className="panel workspace-topbar">
      <button aria-label="打开审批线程" className="ui-button" onClick={onOpenSessions} type="button">
        <Menu size={16} />
        审批线程
      </button>

      <div className="workspace-title-wrap">
        <p className="workspace-title-label">当前审批会话</p>
        <h1 className="workspace-title-text" title={currentSessionTitle}>
          {currentSessionTitle}
        </h1>
      </div>

      <div className="relative" ref={menuRef}>
        <button
          aria-label="打开 Workflow tools"
          className="ui-button"
          onClick={() => setMenuOpen((value) => !value)}
          type="button"
        >
          <Wrench size={16} />
          Workflow tools
        </button>

        {menuOpen ? (
          <div className="menu-popover absolute right-0 top-[calc(100%+0.75rem)] z-40 w-[420px] p-3">
            <div className="menu-section">
              <p className="menu-label">审批会话</p>
              <div className="grid gap-2">
                <button
                  className="menu-card"
                  onClick={() => {
                    void createNewSession();
                    setMenuOpen(false);
                  }}
                  type="button"
                >
                  <div>
                    <div className="menu-card-title">新建审批会话</div>
                    <div className="menu-card-copy">开始一个新的审批线程</div>
                  </div>
                  <Plus size={16} />
                </button>
                <button
                  className="menu-card"
                  onClick={() => {
                    const nextTitle = window.prompt("重命名当前审批会话", currentSessionTitle);
                    if (nextTitle) {
                      void renameCurrentSession(nextTitle);
                    }
                    setMenuOpen(false);
                  }}
                  type="button"
                >
                  <div>
                    <div className="menu-card-title">重命名审批会话</div>
                    <div className="menu-card-copy">{currentSessionTitle}</div>
                  </div>
                  <Pencil size={16} />
                </button>
                <button
                  className="menu-card"
                  onClick={() => {
                    void compressCurrentSession();
                    setMenuOpen(false);
                  }}
                  type="button"
                >
                  <div>
                    <div className="menu-card-title">压缩审批上下文</div>
                    <div className="menu-card-copy">总结较早的审批上下文</div>
                  </div>
                  <Wrench size={16} />
                </button>
                <button
                  className="menu-card"
                  onClick={() => {
                    onOpenFiles();
                    setMenuOpen(false);
                  }}
                  type="button"
                >
                  <div>
                    <div className="menu-card-title">打开文件</div>
                    <div className="menu-card-copy">浏览和编辑 workspace 文件</div>
                  </div>
                  <FileText size={16} />
                </button>
              </div>
            </div>

            <div className="menu-section">
              <p className="menu-label">Workflow runtime</p>
              <div className="grid gap-2 sm:grid-cols-2">
                <button
                  className="menu-card"
                  disabled={runtimeLoading}
                  onClick={() => void toggleRagMode()}
                  type="button"
                >
                  <div>
                    <div className="menu-card-title">政策检索</div>
                    <div className="menu-card-copy">{ragMode ? "已开启" : "已关闭"}</div>
                  </div>
                  <Search size={16} />
                </button>
                <button
                  className="menu-card"
                  disabled={runtimeLoading}
                  onClick={() => void toggleSkillRetrieval()}
                  type="button"
                >
                  <div>
                    <div className="menu-card-title">能力检索</div>
                    <div className="menu-card-copy">
                      {skillRetrievalEnabled ? "已开启" : "已关闭"}
                    </div>
                  </div>
                  <Search size={16} />
                </button>
              </div>
              <div className="menu-inline">
                <span className="menu-inline-label">
                  <Monitor size={14} />
                  Shell
                </span>
                <button
                  className={executionPlatform === "windows" ? "ui-button ui-button-primary" : "ui-button"}
                  onClick={() => void updateExecutionPlatform("windows")}
                  type="button"
                >
                  Windows
                </button>
                <button
                  className={executionPlatform === "linux" ? "ui-button ui-button-primary" : "ui-button"}
                  onClick={() => void updateExecutionPlatform("linux")}
                  type="button"
                >
                  Linux
                </button>
              </div>
            </div>

            <div className="menu-section">
              <p className="menu-label">政策 / 证据索引</p>
              <div className="menu-note">{knowledgeLabel}</div>
              <button
                className="menu-card"
                disabled={Boolean(knowledgeIndexStatus?.building)}
                onClick={() => void rebuildKnowledgeIndex()}
                type="button"
              >
                <div>
                  <div className="menu-card-title">重建索引</div>
                  <div className="menu-card-copy">刷新当前政策与证据目录</div>
                </div>
                <Database size={16} />
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </header>
  );
}
