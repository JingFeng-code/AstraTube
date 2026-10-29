"""/settings：讀取與更新使用者設定（金鑰只回遮罩預覽，不外洩完整內容）。"""
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.core import config, languages, messages
from app.models.schemas import SettingsUpdate

router = APIRouter(prefix="/settings", tags=["settings"])

_DEFAULT_FOLDER = "Youtube Card Reader"

# 設定畫面上的金鑰欄位：(API 欄位名, config 欄位名)
_KEY_FIELDS = (
    ("gemini_api_key", "GEMINI_API_KEY"),
    ("opencode_api_key", "OPENCODE_API_KEY"),
    ("deepseek_api_key", "DEEPSEEK_API_KEY"),
    ("openai_api_key", "OPENAI_API_KEY"),
    ("anthropic_api_key", "ANTHROPIC_API_KEY"),
)


def _mask(key: str) -> str:
    """回傳遮罩後的金鑰預覽。"""
    key = key or ""
    if not key:
        return ""
    if len(key) <= 8:
        return "••••"
    return f"{key[:4]}••••{key[-4:]}"


def _public_state() -> dict:
    """對前端公開的設定狀態（不含完整金鑰）。"""
    g = config.get("GEMINI_API_KEY")
    g_keys = [k for k in re.split(r"[,\s]+", (g or "").strip()) if k]
    vault = config.get("OBSIDIAN_VAULT_PATH")
    folder = config.get("OBSIDIAN_NOTES_FOLDER") or _DEFAULT_FOLDER

    state: dict = {
        # Gemini 支援多把金鑰，預覽文字要反映把數
        "gemini_key_count": len(g_keys),
        # Obsidian 路徑非機密，完整回傳以便設定畫面預填
        "obsidian_vault_path": vault,
        "obsidian_notes_folder": folder,
        "obsidian_set": bool(vault),
        "obsidian_exists": bool(vault) and Path(vault).expanduser().exists(),
        "output_language": config.get("OUTPUT_LANGUAGE") or languages.DEFAULT,
        "ui_language": config.get("UI_LANGUAGE") or "zh-Hant",
        "languages": languages.codes(),
    }
    for api_field, cfg_field in _KEY_FIELDS:
        name = api_field.removesuffix("_api_key")
        raw = config.get(cfg_field)
        state[f"{name}_set"] = bool(raw)
        state[f"{name}_preview"] = (messages.t("settings.key_count", count=len(g_keys))
                                    if name == "gemini" and len(g_keys) > 1 else _mask(raw))
    # 一把金鑰都沒有時顯示導引畫面（OpenCode 免費模型其實不需金鑰，但仍值得提示一次）
    state["configured"] = any(state[f"{f.removesuffix('_api_key')}_set"] for f, _ in _KEY_FIELDS)
    return state


@router.get("")
def get_settings() -> dict:
    return _public_state()


@router.post("")
def update_settings(req: SettingsUpdate) -> dict:
    """只更新有提供的欄位；金鑰缺席代表維持原值。"""
    updates: dict[str, str] = {}
    for api_field, cfg_field in _KEY_FIELDS:
        value = getattr(req, api_field, None)
        if value is not None:
            updates[cfg_field] = value.strip()
    if req.obsidian_vault_path is not None:
        updates["OBSIDIAN_VAULT_PATH"] = req.obsidian_vault_path.strip()
    if req.obsidian_notes_folder is not None:
        updates["OBSIDIAN_NOTES_FOLDER"] = req.obsidian_notes_folder.strip()
    if req.output_language is not None:
        # 不認得的語言代碼一律回退預設，避免前端送錯值就讓 prompt 壞掉
        updates["OUTPUT_LANGUAGE"] = languages.get(req.output_language).code
    if req.ui_language is not None:
        # 介面語言只有兩種；認不出來就當繁中，config 那層也會再擋一次
        updates["UI_LANGUAGE"] = req.ui_language if req.ui_language in ("zh-Hant", "en") else "zh-Hant"
    try:
        config.save(updates)
    except RuntimeError as e:
        raise HTTPException(500, messages.t("settings.save_failed", error=e))
    return _public_state()
