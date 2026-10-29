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
    "summarize.model_output_invalid": {
        "zh-Hant": "模型回應不是有效的知識卡格式（可能只輸出了思考過程、內容被截斷，或模型不支援 JSON 輸出）。請重試，或在開發者模式更換模型。",
        "en": "The model did not return valid card data (it may have returned only its reasoning, been cut off, or not support JSON output). Try again, or switch models in developer mode.",
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

    # ── YouTube 字幕 ────────────────────────────────────────
    "captions.missing": {
        "zh-Hant": "這支 YouTube 影片沒有提供公開字幕（作者未上傳或已停用）。",
        "en": "This YouTube video has no public captions (none uploaded or captions are disabled).",
    },
    "captions.unavailable": {
        "zh-Hant": "YouTube 表示這支影片無法播放或受到限制（私人、已移除、年齡或地區限制），因此讀不到字幕。",
        "en": "YouTube reports this video is unavailable or restricted (private, removed, age- or region-limited), so captions cannot be read.",
    },
    "captions.blocked": {
        "zh-Hant": "YouTube 暫時拒絕了字幕請求（常見於短時間請求過多或目前網路被限制）。影片本身可能有字幕，請稍後再試或換一個網路。",
        "en": "YouTube temporarily refused the caption request (often too many requests or a restricted network). The video may still have captions; try again later or from another network.",
    },
    "captions.network": {
        "zh-Hant": "無法連線到 YouTube 取得字幕（網路、Proxy 或防火牆問題）。影片本身可能有字幕，請確認網路後重試。",
        "en": "Could not reach YouTube to fetch captions (network, proxy or firewall). The video may still have captions; check your connection and retry.",
    },
    "captions.service": {
        "zh-Hant": "YouTube 字幕服務回應異常（可能是平台介面變更），目前無法判斷影片是否有字幕。請稍後再試；若持續發生，請回報給開發者。",
        "en": "YouTube's caption service returned an unexpected response (possibly a platform change), so it is unclear whether captions exist. Try again later and report it if it keeps happening.",
    },
    # ── 本機轉寫 ────────────────────────────────────────────
    "whisper.unavailable_desktop": {
        "zh-Hant": "桌面測試版尚未內建本機語音轉錄，無法改用語音辨識。"
                   "可以匯入你有權使用的 SRT／VTT 字幕檔後再按「開始」。",
        "en": "The desktop preview does not include local speech-to-text yet, so it cannot "
              "transcribe the audio. Import an SRT/VTT file you are allowed to use, then press Start.",
    },
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
    "provider.hint_auth": {
        "zh-Hant": "服務拒絕存取：可能需要 API Key、金鑰無效，或目前網路／地區被限制。可在開發者模式改用其他模型或本機 Ollama。",
        "en": "Access was refused: an API key may be required or invalid, or this network/region is blocked. In developer mode, try another model or local Ollama.",
    },
    "provider.hint_not_found": {
        "zh-Hant": "模型可能已下架或名稱有誤，請在開發者模式更換模型。",
        "en": "The model may have been retired or renamed. Pick another model in developer mode.",
    },
    "provider.hint_rate_limit": {
        "zh-Hant": "免費額度或請求次數已達上限，請稍等幾分鐘再試，或更換模型。",
        "en": "The free quota or rate limit was reached. Wait a few minutes or switch models.",
    },
    "provider.hint_server": {
        "zh-Hant": "模型服務暫時故障，請稍後再試。",
        "en": "The model service is having trouble. Please try again later.",
    },
    "provider.hint_timeout": {
        "zh-Hant": "模型回應逾時，請稍後再試，或改用回應較快的模型。",
        "en": "The model timed out. Try again later or use a faster model.",
    },
    "provider.hint_network": {
        "zh-Hant": "請確認網路連線，以及 Proxy／防火牆是否允許連到模型服務。",
        "en": "Check your internet connection and whether a proxy or firewall blocks the model service.",
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
