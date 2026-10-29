"""執行期可變更的設定。

設定值優先順序：
  1. 專案根目錄的 settings.json（使用者在 App 設定畫面輸入並儲存的內容）
  2. 專案根目錄的 .env（首次啟動時的預設／開發用）

所以使用者可在 App 內隨時更改金鑰與 Obsidian 路徑，存進 settings.json，
不需要重啟也不需要手動編輯任何檔案。
"""
import json
import os
from pathlib import Path

from dotenv import load_dotenv

# config.py 位於 backend/app/core/，往上三層即專案根
_ROOT = Path(__file__).resolve().parents[3]
_ENV_PATH = _ROOT / ".env"
_SETTINGS_PATH = _ROOT / "settings.json"

load_dotenv(_ENV_PATH)

# 使用者可編輯的設定鍵（settings.json 內其他欄位一律忽略並保留）
_FIELDS: tuple[str, ...] = (
    "GEMINI_API_KEY",
    "OPENCODE_API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OUTPUT_LANGUAGE",
    "OBSIDIAN_VAULT_PATH",
    "OBSIDIAN_NOTES_FOLDER",
    "OUTPUT_DIR",
    "AUTO_RUN_CLI",
    "UI_LANGUAGE",
    "CLI_EFFORT",
)

_DEFAULT_FOLDER = "Youtube Card Reader"
_DEFAULT_LANGUAGE = "zh-Hant"
# 實作產出的落腳處。預設放家目錄下，不寫進專案目錄（產出是使用者的東西，不是專案的）
_DEFAULT_OUTPUT_DIR = str(Path.home() / "Documents" / "YCR 實作產出")


def _defaults() -> dict[str, str]:
    """從環境變數（.env）取得初始值。"""
    return {
        "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY", "").strip(),
        "OPENCODE_API_KEY": os.getenv("OPENCODE_API_KEY", "").strip(),
        "DEEPSEEK_API_KEY": os.getenv("DEEPSEEK_API_KEY", "").strip(),
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", "").strip(),
        "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY", "").strip(),
        "OUTPUT_LANGUAGE": os.getenv("OUTPUT_LANGUAGE", _DEFAULT_LANGUAGE).strip() or _DEFAULT_LANGUAGE,
        "OBSIDIAN_VAULT_PATH": os.getenv("OBSIDIAN_VAULT_PATH", "").strip().strip('"'),
        "OBSIDIAN_NOTES_FOLDER": os.getenv("OBSIDIAN_NOTES_FOLDER", _DEFAULT_FOLDER).strip() or _DEFAULT_FOLDER,
        "OUTPUT_DIR": os.getenv("OUTPUT_DIR", _DEFAULT_OUTPUT_DIR).strip().strip('"') or _DEFAULT_OUTPUT_DIR,
        # "1"／"0"：偵測到 CLI 時要不要直接跑。關掉就只產任務包讓使用者自己貼進終端機
        "AUTO_RUN_CLI": os.getenv("AUTO_RUN_CLI", "1").strip() or "1",
        # 介面語言（zh-Hant／en）。與 OUTPUT_LANGUAGE 分開：介面是誰在用，輸出是要寫成什麼語言。
        # 後端回給前端的錯誤訊息也跟著這個走，否則外國使用者會看到中文錯誤。
        "UI_LANGUAGE": os.getenv("UI_LANGUAGE", "zh-Hant").strip() or "zh-Hant",
        # Codex 的思考強度。實測同一份任務 xhigh 13.9 分鐘、medium 3.8 分鐘，
        # 而且題數與結構相同——這種「照著素材寫檔案」的任務不需要更深的思考。
        # 不放進 UI：多一個選項換不到多少價值。要改的人動這裡。
        "CLI_EFFORT": os.getenv("CLI_EFFORT", "medium").strip() or "medium",
    }


def _read_settings_file() -> dict:
    """讀取 settings.json 原始內容（讀不到或壞掉都回空 dict）。"""
    if not _SETTINGS_PATH.exists():
        return {}
    try:
        data = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _load() -> dict[str, str]:
    """合併 .env 與 settings.json，得到目前生效的設定。"""
    data = _defaults()
    saved = _read_settings_file()
    for k in _FIELDS:
        if saved.get(k) is not None:
            data[k] = str(saved[k]).strip()
    if not data.get("OBSIDIAN_NOTES_FOLDER"):
        data["OBSIDIAN_NOTES_FOLDER"] = _DEFAULT_FOLDER
    if not data.get("OUTPUT_LANGUAGE"):
        data["OUTPUT_LANGUAGE"] = _DEFAULT_LANGUAGE
    if not data.get("OUTPUT_DIR"):
        data["OUTPUT_DIR"] = _DEFAULT_OUTPUT_DIR
    if data.get("UI_LANGUAGE") not in ("zh-Hant", "en"):
        data["UI_LANGUAGE"] = "zh-Hant"
    return data


_cache: dict[str, str] = _load()


def get(key: str) -> str:
    """取得目前設定值（即時，反映最新一次儲存）。"""
    return _cache.get(key, "")


def all_settings() -> dict[str, str]:
    """回傳目前所有設定的複本。"""
    return dict(_cache)


def save(updates: dict) -> dict[str, str]:
    """更新並持久化設定。只更新有提供（非 None）的欄位；空字串代表清除。

    寫檔時保留 settings.json 內本程式不認得的欄位，避免覆寫使用者的其他資料。
    """
    for k, v in (updates or {}).items():
        if k in _FIELDS:
            _cache[k] = "" if v is None else str(v).strip()
    if not _cache.get("OBSIDIAN_NOTES_FOLDER"):
        _cache["OBSIDIAN_NOTES_FOLDER"] = _DEFAULT_FOLDER
    if not _cache.get("OUTPUT_LANGUAGE"):
        _cache["OUTPUT_LANGUAGE"] = _DEFAULT_LANGUAGE
    if not _cache.get("OUTPUT_DIR"):
        _cache["OUTPUT_DIR"] = _DEFAULT_OUTPUT_DIR
    if _cache.get("UI_LANGUAGE") not in ("zh-Hant", "en"):
        _cache["UI_LANGUAGE"] = "zh-Hant"

    merged = _read_settings_file()
    merged.update(_cache)
    try:
        _SETTINGS_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        # 只帶原始錯誤；給使用者看的句子由 API 層依介面語言組裝。
        # config 不得反向匯入 messages（messages 要靠 config 讀 UI_LANGUAGE），否則循環匯入。
        raise RuntimeError(str(e))
    return dict(_cache)


def __getattr__(name: str) -> str:  # PEP 562：向後相容的模組層級常數存取
    if name in _FIELDS:
        return _cache.get(name, "")
    raise AttributeError(name)
