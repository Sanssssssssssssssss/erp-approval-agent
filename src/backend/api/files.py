from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.backend.capabilities.skills_scanner import refresh_snapshot, scan_skills
from src.backend.knowledge.memory_indexer import memory_indexer
from src.backend.runtime.agent_manager import agent_manager

router = APIRouter()

ALLOWED_PREFIXES = ("workspace/", "memory/", "skills/", "knowledge/")
ALLOWED_ROOT_FILES = {"SKILLS_SNAPSHOT.md"}


class SaveFileRequest(BaseModel):
    path: str = Field(..., min_length=1)
    content: str


def _base_dir() -> Path:
    if agent_manager.base_dir is None:
        raise HTTPException(status_code=503, detail="Agent manager is not initialized")
    return agent_manager.base_dir.resolve()


def _resolve_path(relative_path: str) -> Path:
    normalized = relative_path.replace("\\", "/").strip("/")
    if normalized not in ALLOWED_ROOT_FILES and not normalized.startswith(ALLOWED_PREFIXES):
        raise HTTPException(status_code=400, detail="Path is not in the editable whitelist")

    base_dir = _base_dir()
    candidate = (base_dir / normalized).resolve()
    if base_dir not in candidate.parents and candidate != base_dir:
        raise HTTPException(status_code=400, detail="Path traversal detected")
    return candidate


@router.get("/files/catalog")
async def list_file_catalog() -> list[dict[str, Any]]:
    base_dir = _base_dir()
    catalog: list[dict[str, Any]] = []

    for root_file in sorted(ALLOWED_ROOT_FILES):
        path = base_dir / root_file
        if path.exists() and path.is_file():
            catalog.append(_file_catalog_item(base_dir, path))

    for prefix in ALLOWED_PREFIXES:
        root = base_dir / prefix
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.md")):
            if path.is_file():
                catalog.append(_file_catalog_item(base_dir, path))

    deduped: dict[str, dict[str, Any]] = {}
    for item in catalog:
        deduped[str(item["path"])] = item
    return list(deduped.values())


@router.get("/files")
async def read_file(path: str = Query(..., min_length=1)) -> dict[str, str]:
    file_path = _resolve_path(path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return {
        "path": path.replace("\\", "/"),
        "content": file_path.read_text(encoding="utf-8"),
    }


@router.post("/files")
async def save_file(payload: SaveFileRequest) -> dict[str, Any]:
    file_path = _resolve_path(payload.path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(payload.content, encoding="utf-8")

    normalized = payload.path.replace("\\", "/")
    if normalized == "memory/MEMORY.md":
        memory_indexer.rebuild_index()
    if normalized.startswith("skills/"):
        refresh_snapshot(agent_manager.base_dir)

    return {"ok": True, "path": normalized}


@router.get("/skills")
async def list_skills() -> list[dict[str, str]]:
    if agent_manager.base_dir is None:
        raise HTTPException(status_code=503, detail="Agent manager is not initialized")
    return [skill.__dict__ for skill in scan_skills(agent_manager.base_dir)]


def _file_catalog_item(base_dir: Path, path: Path) -> dict[str, Any]:
    stat = path.stat()
    relative = path.relative_to(base_dir).as_posix()
    return {
        "path": relative,
        "name": path.name,
        "category": _file_category(relative),
        "size_bytes": stat.st_size,
        "updated_at": stat.st_mtime,
        "read_only": False,
    }


def _file_category(relative_path: str) -> str:
    if relative_path.startswith("workspace/"):
        return "核心身份 / 系统提示"
    if relative_path.startswith("memory/"):
        return "长期记忆"
    if relative_path.startswith("knowledge/ERP Approval/"):
        return "审批政策 / RAG"
    if relative_path.startswith("knowledge/"):
        return "知识库"
    if relative_path.startswith("skills/"):
        return "技能说明"
    return "运行清单"
