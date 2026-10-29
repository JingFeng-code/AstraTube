"""/notes：列出 Obsidian vault 內的資料夾與筆記，並把摘要存成 .md。"""
import os
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.core import config, messages
from app.models.schemas import SaveNoteRequest

router = APIRouter(prefix="/notes", tags=["notes"])

# 略過的系統/隱藏資料夾
_SKIP_DIRS = {".obsidian", ".trash", ".git", "node_modules"}


def _notes_folder() -> str:
    return config.get("OBSIDIAN_NOTES_FOLDER") or "Youtube Card Reader"


def _vault_root():
    p = config.get("OBSIDIAN_VAULT_PATH")
    if not p:
        return None
    return Path(p)


def _safe_relpath(rel: str) -> Path:
    """把使用者給的相對資料夾路徑清乾淨，移除 .. 與非法字元，避免跳出 vault。"""
    rel = (rel or "").replace("\\", "/")
    parts = []
    for seg in rel.split("/"):
        seg = re.sub(r'[:*?"<>|]', "", seg).strip().strip(".")
        if seg and seg not in ("", ".", ".."):
            parts.append(seg)
    return Path(*parts) if parts else Path()


def _safe_name(name: str) -> str:
    """新筆記檔名（不含副檔名）。"""
    name = re.sub(r'[\\/:*?"<>|]', "", name or "").strip()
    return name[:120] or datetime.now().strftime(messages.t("notes.default_filename"))


def _safe_filename(name: str) -> str:
    """現有筆記檔名（保留 .md），只取最後一段，防止路徑跳脫。"""
    name = os.path.basename((name or "").replace("\\", "/"))
    name = re.sub(r'[:*?"<>|]', "", name).strip()
    if not name.lower().endswith(".md"):
        name += ".md"
    return name


def _ensure_within(root: Path, target: Path) -> Path:
    """確認 target 確實在 vault 內，否則拒絕。"""
    root_r = root.resolve()
    target_r = target.resolve()
    if target_r != root_r and root_r not in target_r.parents:
        raise HTTPException(400, messages.t("notes.path_outside_vault"))
    return target_r


@router.get("/status")
def status():
    folder = _notes_folder()
    root = _vault_root()
    if root is None:
        return {"configured": False, "path": None, "exists": False, "default_folder": folder}
    note_dir = root / _safe_relpath(folder)
    return {
        "configured": True,
        "path": str(note_dir),
        "exists": root.exists(),
        "default_folder": folder,
    }


@router.get("/folders")
def folders():
    """列出 vault 內所有可用資料夾（相對路徑，"" 代表 vault 根目錄）。"""
    root = _vault_root()
    if root is None or not root.exists():
        return {"folders": [], "default": _notes_folder()}
    result = []
    for dirpath, dirnames, _ in os.walk(root):
        # 原地修改 dirnames 以剪枝，跳過隱藏與系統資料夾
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in _SKIP_DIRS]
        rel = os.path.relpath(dirpath, root)
        result.append("" if rel == "." else rel.replace("\\", "/"))
    # 確保預設資料夾一定在清單中
    default_rel = str(_safe_relpath(_notes_folder())).replace("\\", "/")
    if default_rel and default_rel not in result:
        result.append(default_rel)
    return {"folders": sorted(set(result), key=lambda s: (s != default_rel, s.lower())), "default": default_rel}


@router.get("/files")
def files(folder: str = ""):
    """列出指定資料夾內的 .md 筆記檔名。"""
    root = _vault_root()
    if root is None or not root.exists():
        return {"files": []}
    d = root / _safe_relpath(folder)  # folder="" 代表 vault 根目錄
    if not d.exists() or not d.is_dir():
        return {"files": []}
    fs = sorted(
        (p.name for p in d.iterdir() if p.is_file() and p.suffix.lower() == ".md"),
        key=str.lower,
    )
    return {"files": fs}


@router.post("/save")
def save(req: SaveNoteRequest):
    root = _vault_root()
    if root is None:
        raise HTTPException(400, messages.t("notes.vault_not_set"))
    if not root.exists():
        raise HTTPException(400, messages.t("notes.vault_missing"))

    folder_dir = root / _safe_relpath(req.folder)  # folder="" 代表 vault 根目錄
    _ensure_within(root, folder_dir)

    if req.mode == "append" and req.target_file:
        path = folder_dir / _safe_filename(req.target_file)
        _ensure_within(root, path)
        if not path.exists():
            raise HTTPException(400, messages.t("notes.target_missing"))
        with path.open("a", encoding="utf-8") as f:
            f.write("\n\n" + req.content.rstrip() + "\n")
        return {"ok": True, "saved_to": str(path), "mode": "append"}

    # 新增筆記（自動避開同名檔）
    folder_dir.mkdir(parents=True, exist_ok=True)
    base = _safe_name(req.filename)
    path = folder_dir / f"{base}.md"
    _ensure_within(root, path)
    i = 2
    while path.exists():
        path = folder_dir / f"{base} {i}.md"
        i += 1
    path.write_text(req.content.rstrip() + "\n", encoding="utf-8")
    return {"ok": True, "saved_to": str(path), "mode": "new"}
