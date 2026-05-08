from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(prefix="/project-docs", tags=["project-docs"])

DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[3]
ROOT_DOCUMENTS = ("AGENTS.md", "README.md")
DOCUMENT_DIRECTORIES = ("docs", "notes", "state")


class ProjectDocumentSummary(BaseModel):
    path: str
    title: str
    size_bytes: int
    updated_at: datetime


class ProjectDocumentsResponse(BaseModel):
    items: list[ProjectDocumentSummary]


class ProjectDocumentContent(ProjectDocumentSummary):
    content: str


@router.get("", response_model=ProjectDocumentsResponse)
async def list_project_documents() -> ProjectDocumentsResponse:
    root = _project_root()
    return ProjectDocumentsResponse(
        items=[_document_summary(path, root=root) for path in _iter_document_paths(root)]
    )


@router.get("/{document_path:path}", response_model=ProjectDocumentContent)
async def get_project_document(document_path: str) -> ProjectDocumentContent:
    root = _project_root()
    path = _resolve_document_path(document_path, root=root)
    if path is None:
        raise HTTPException(status_code=404, detail="project document not found")

    return ProjectDocumentContent(
        **_document_summary(path, root=root).model_dump(),
        content=path.read_text(encoding="utf-8"),
    )


def _project_root() -> Path:
    return (get_settings().project_docs_root or DEFAULT_PROJECT_ROOT).resolve()


def _iter_document_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for document_name in ROOT_DOCUMENTS:
        path = root / document_name
        if path.is_file():
            paths.append(path)

    for directory_name in DOCUMENT_DIRECTORIES:
        directory = root / directory_name
        if not directory.is_dir():
            continue
        paths.extend(path for path in directory.rglob("*.md") if path.is_file())

    return sorted(paths, key=lambda path: _relative_path(path, root=root))


def _resolve_document_path(document_path: str, *, root: Path) -> Path | None:
    candidate = (root / document_path).resolve()
    if not candidate.is_file() or not _is_allowed_document(candidate, root=root):
        return None
    return candidate


def _is_allowed_document(path: Path, *, root: Path) -> bool:
    try:
        relative = path.resolve().relative_to(root)
    except ValueError:
        return False

    if any(part.startswith(".") for part in relative.parts):
        return False
    if relative.as_posix() in ROOT_DOCUMENTS:
        return True
    return (
        len(relative.parts) > 1
        and relative.parts[0] in DOCUMENT_DIRECTORIES
        and relative.suffix == ".md"
    )


def _document_summary(path: Path, *, root: Path) -> ProjectDocumentSummary:
    stat = path.stat()
    content = path.read_text(encoding="utf-8")
    return ProjectDocumentSummary(
        path=_relative_path(path, root=root),
        title=_extract_title(content, path),
        size_bytes=stat.st_size,
        updated_at=datetime.fromtimestamp(stat.st_mtime, UTC),
    )


def _extract_title(content: str, path: Path) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or path.name
    return path.stem.replace("-", " ").replace("_", " ").strip().title() or path.name


def _relative_path(path: Path, *, root: Path) -> str:
    return path.resolve().relative_to(root).as_posix()
