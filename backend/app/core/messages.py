"""會外露給使用者的後端訊息（中英雙語）。

前端已經完整 i18n，但後端回傳的錯誤與狀態標籤如果寫死中文，外國使用者就會在
畫面上看到中文——功能等於半殘。所以凡是「會傳到前端、被使用者看到」的字串
（HTTPException detail、串流事件裡的 error／label、API 回傳的顯示欄位）一律
走這裡取字，依 UI_LANGUAGE 決定語言。

**不進這裡的**：print() 的 log（那是給開發者看的）、註解、docstring，以及
app/prompts/ 底下給模型看的指令文字（那是 prompt 工程，不是介面文案）。

設計原則：
1. **絕不拋例外**。訊息機制自己壞掉（key 打錯、format 參數少給）不該讓 API 掛掉，
   一律降級回退：找不到語言 → 回 zh-Hant；找不到 key → 回 key 本身（畫面上看到
   一串 id，比空白更容易發現漏翻）；format 失敗 → 回未代入的原句。
2. **不匯入 config 以外的東西**。config 也不得反向匯入 messages，否則會循環匯入。
3. 每個 key 兩種語言都要有——`tests/test_messages.py` 把「兩邊 key 集合完全相同」
   與「英文句子不含中日韓字元」當成不變式在驗。
"""
from typing import Any

from app.core import config

FALLBACK = "zh-Hant"
LANGUAGES = ("zh-Hant", "en")

# key 命名：<模組>.<情境>。值一律 str，需要變數就用 str.format 的具名欄位。
MESSAGES: dict[str, dict[str, str]] = {
    # ── 設定 ────────────────────────────────────────────────
    "settings.save_failed": {
        "zh-Hant": "無法寫入設定檔：{error}",
        "en": "Could not write the settings file: {error}",
    },
    "settings.key_count": {
        "zh-Hant": "{count} 把金鑰",
        "en": "{count} keys",
    },

    # ── Obsidian 筆記 ───────────────────────────────────────
    "notes.path_outside_vault": {
        "zh-Hant": "非法路徑：超出 vault 範圍",
        "en": "Invalid path: outside the vault",
    },
    "notes.vault_not_set": {
        "zh-Hant": "尚未設定 OBSIDIAN_VAULT_PATH",
        "en": "OBSIDIAN_VAULT_PATH is not set",
    },
    "notes.vault_missing": {
        "zh-Hant": "vault 路徑不存在",
        "en": "That vault path does not exist",
    },
    "notes.target_missing": {
        "zh-Hant": "目標筆記不存在，請重新選擇或改用新增",
        "en": "That note no longer exists. Pick another one, or create a new note.",
    },
    # strftime 格式字串（新筆記的預設檔名）
    "notes.default_filename": {
        "zh-Hant": "筆記 %Y-%m-%d %H%M",
        "en": "Note %Y-%m-%d %H%M",
    },

    # ── 問模型 ──────────────────────────────────────────────
    "ask.no_transcript": {
        "zh-Hant": "找不到這支影片的逐字稿。請先整理影片，再來問問題。",
        "en": "No transcript for this video yet. Extract the cards first, then ask.",
    },
    "ask.failed": {
        "zh-Hant": "問模型失敗：{error}",
        "en": "The model could not answer: {error}",
    },

    # ── 摘要 ────────────────────────────────────────────────
    "summarize.fetch_failed": {
        "zh-Hant": "擷取失敗：{error}",
        "en": "Could not fetch the source: {error}",
    },
    "summarize.all_segments_failed": {
        "zh-Hant": "摘要失敗：所有片段都無法產生，請稍後再試或換模型。",
        "en": "Extraction failed: no part produced cards. Try again or switch models.",
    },
    "summarize.deepdive_failed": {
        "zh-Hant": "深入解析失敗：{error}",
        "en": "Deep dive failed: {error}",
    },
    "summarize.untitled": {
        "zh-Hant": "未知標題",
        "en": "Untitled",
    },

    # ── 實作 ────────────────────────────────────────────────
    "implement.outside_output_dir": {
        "zh-Hant": "只能讀產出資料夾底下的檔案。",
        "en": "Only files inside the output folder can be opened.",
    },
    "implement.file_missing": {
        "zh-Hant": "檔案不存在。",
        "en": "That file no longer exists.",
    },
    "implement.not_viewable": {
        "zh-Hant": "這種檔案沒辦法在畫面上直接顯示，請用「打開資料夾」查看。",
        "en": "This file type cannot be shown here. Use \"Open folder\" instead.",
    },
    "implement.file_too_big": {
        "zh-Hant": "檔案太大，無法直接顯示，請用「打開資料夾」查看。",
        "en": "File is too large to show here. Use \"Open folder\" instead.",
    },
    "implement.file_read_failed": {
        "zh-Hant": "讀取檔案失敗：{error}",
        "en": "Could not read the file: {error}",
    },
    "implement.no_cards": {
        "zh-Hant": "這支影片還沒有卡片，無法實作。",
        "en": "This video has no cards yet, so there is nothing to build from.",
    },
    "implement.untitled_video": {
        "zh-Hant": "未命名影片",
        "en": "Untitled video",
    },
    "implement.reveal_outside": {
        "zh-Hant": "只能打開產出資料夾底下的位置。",
        "en": "Only paths inside the output folder can be opened.",
    },
    "implement.folder_missing": {
        "zh-Hant": "資料夾不存在。",
        "en": "That folder does not exist.",
    },
    "implement.reveal_failed": {
        "zh-Hant": "打不開資料夾：{error}",
        "en": "Could not open the folder: {error}",
    },
    "implement.provider_auto": {
        "zh-Hant": "自動",
        "en": "Auto",
    },
    "implement.provider_gemini": {
        "zh-Hant": "Gemini（{model}）",
        "en": "Gemini ({model})",
    },
    "implement.provider_label": {
        "zh-Hant": "{kind}／{model}",
        "en": "{kind}/{model}",
    },
    "implement.api_generating": {
        "zh-Hant": "正在請 {label} 產出檔案…",
        "en": "Asking {label} to write the files…",
    },
    "implement.api_failed": {
        "zh-Hant": "{label} 產出失敗：{error}",
        "en": "{label} failed to produce anything: {error}",
    },
    "implement.api_no_files": {
        "zh-Hant": "{label} 沒有回傳可解析的檔案（多半是輸出被截斷）。"
                   "原始輸出已存成 gemini-raw.txt，建議改用 Codex 或 Claude Code。",
        "en": "{label} returned nothing parsable — the output was most likely cut off. "
              "The raw output is saved as gemini-raw.txt. Try Codex CLI or Claude Code instead.",
    },
    "implement.wrote_file": {
        "zh-Hant": "寫入 {name}（{chars} 字）",
        "en": "Wrote {name} ({chars} chars)",
    },
    # 沒有任何模型可用時，直接排版輸出後端已知的安裝資訊
    "implement.teach_heading": {
        "zh-Hant": "## 先安裝一個 coding agent CLI",
        "en": "## Install a coding agent CLI first",
    },
    "implement.teach_intro": {
        "zh-Hant": "「實作」功能需要能讀寫檔案、能上網查證的工具，兩個擇一安裝即可：",
        "en": "This step needs a tool that can read and write files and check links on the web. "
              "Either one will do:",
    },
    "implement.teach_or": {
        "zh-Hant": "或：`{command}`",
        "en": "or: `{command}`",
    },
    "implement.teach_auth": {
        "zh-Hant": "- 登入：{auth}",
        "en": "- Sign in: {auth}",
    },
    "implement.teach_docs": {
        "zh-Hant": "- 官方文件：{url}",
        "en": "- Docs: {url}",
    },
    "implement.teach_outro": {
        "zh-Hant": "裝好並登入後，回到這裡重新按一次「開始實作」。",
        "en": "Once it is installed and signed in, come back and hit Make it again.",
    },

    # ── track 標籤（前端直接顯示；prompts/implement.py 的 TRACK_LABELS 是給模型看的，不動）
    "track.build": {
        "zh-Hant": "可執行的專案包",
        "en": "a project you can run",
    },
    "track.sop": {
        "zh-Hant": "一步一步的操作引導",
        "en": "a step-by-step guide",
    },
    "track.study": {
        "zh-Hant": "弄懂與驗證的教學頁",
        "en": "a study page",
    },
    "track.drill": {
        "zh-Hant": "練習題庫",
        "en": "a practice quiz",
    },

    # ── coding agent CLI ────────────────────────────────────
    "cli.auth_codex": {
        "zh-Hant": "裝好後在終端機執行 codex，照畫面用 ChatGPT 帳號登入一次即可。",
        "en": "After installing, run codex in your terminal and sign in once with your ChatGPT account.",
    },
    "cli.auth_claude": {
        "zh-Hant": "裝好後在終端機執行 claude，照畫面用 Claude 帳號登入一次即可。",
        "en": "After installing, run claude in your terminal and sign in once with your Claude account.",
    },
    "cli.unsupported": {
        "zh-Hant": "不支援的 CLI：{name}",
        "en": "Unsupported CLI: {name}",
    },
    "cli.not_found": {
        "zh-Hant": "找不到 {label}，請先安裝。",
        "en": "Could not find {label}. Install it first.",
    },
    "cli.start_failed": {
        "zh-Hant": "啟動 {label} 失敗：{error}",
        "en": "Could not start {label}: {error}",
    },
    "cli.timeout": {
        "zh-Hant": "執行超過 {minutes} 分鐘，已中止。",
        "en": "Stopped after {minutes} minutes.",
    },
    "cli.early_exit": {
        "zh-Hant": "{label} 提前結束（可能尚未登入）。",
        "en": "{label} exited early — you may not be signed in yet.",
    },
    "cli.run_failed": {
        "zh-Hant": "執行失敗：{error}",
        "en": "Run failed: {error}",
    },

    # ── 本機轉寫 ────────────────────────────────────────────
    "whisper.download_failed": {
        "zh-Hant": "無法下載此影片的音訊（可能不支援、需登入或已下架）：{detail}",
        "en": "Could not download this video's audio — it may be unsupported, "
              "private, or taken down: {detail}",
    },
    "whisper.download_timeout": {
        "zh-Hant": "下載音訊逾時，影片可能過長或網路太慢。",
        "en": "Timed out downloading the audio. The video may be too long, or the connection too slow.",
    },
    "whisper.audio_missing": {
        "zh-Hant": "找不到下載的音訊檔。",
        "en": "The downloaded audio file is missing.",
    },
    "whisper.no_speech": {
        "zh-Hant": "這段音訊沒有可辨識的語音內容。",
        "en": "No recognisable speech in this audio.",
    },

    # ── 供應商（LLM）────────────────────────────────────────
    "provider.no_key": {
        "zh-Hant": "尚未設定 {vendor} API key，請點右上角「設定」填入。",
        "en": "No {vendor} API key yet. Open Settings (top right) and add one.",
    },
    "provider.connect_failed": {
        "zh-Hant": "{vendor} 連線失敗：{error}",
        "en": "Could not reach {vendor}: {error}",
    },
    "provider.http_error": {
        "zh-Hant": "{vendor} HTTP {status}：{detail}",
        "en": "{vendor} HTTP {status}: {detail}",
    },
    "provider.not_json": {
        "zh-Hant": "{vendor} 回應非 JSON：{detail}",
        "en": "{vendor} did not return JSON: {detail}",
    },
    "provider.error": {
        "zh-Hant": "{vendor} 錯誤：{detail}",
        "en": "{vendor} error: {detail}",
    },
    "provider.empty_response": {
        "zh-Hant": "{vendor} 回應內容為空（{reason}）。",
        "en": "{vendor} returned an empty response ({reason}).",
    },
    "provider.refusal": {
        "zh-Hant": "{vendor} 婉拒了這個請求（{category}）。請改用其他模型處理這支影片。",
        "en": "{vendor} declined this request ({category}). Try another model for this video.",
    },
    "provider.refusal_uncategorized": {
        "zh-Hant": "未分類",
        "en": "uncategorised",
    },
    "provider.opencode_label": {
        "zh-Hant": "OpenCode（免費）",
        "en": "OpenCode (free)",
    },
    "gemini.search_suffix": {
        "zh-Hant": "＋搜尋",
        "en": " + search",
    },
    "gemini.video_failed": {
        "zh-Hant": "Gemini 影片呼叫失敗",
        "en": "The Gemini video call failed",
    },
    "llm.all_free_failed": {
        "zh-Hant": "OpenCode 免費模型全數失敗，且沒有任何付費供應商金鑰可備援。",
        "en": "Every free OpenCode model failed, and no paid provider key is set as a fallback.",
    },
}


def language() -> str:
    """目前的介面語言；認不得的值一律回退 zh-Hant。"""
    try:
        lang = config.get("UI_LANGUAGE")
    except Exception:  # noqa: BLE001  設定壞掉也不該讓訊息機制炸掉
        return FALLBACK
    return lang if lang in LANGUAGES else FALLBACK


def t(key: str, **kw: Any) -> str:
    """取一條介面訊息。

    kw 會以 str.format 代入（例如 t("ask.failed", error=e)）。
    任何一步失敗都降級回退，絕不拋例外——見模組 docstring 的設計原則 1。
    """
    try:
        entry = MESSAGES.get(key)
        if not entry:
            return key
        text = entry.get(language()) or entry.get(FALLBACK) or key
        if not kw:
            return text
        try:
            return text.format(**kw)
        except Exception:  # noqa: BLE001  參數少給／多給都只是少了代入，不該中斷請求
            return text
    except Exception:  # noqa: BLE001
        return key


__all__ = ["MESSAGES", "LANGUAGES", "FALLBACK", "language", "t"]
