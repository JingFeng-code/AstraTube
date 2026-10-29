from typing import List, Optional

from pydantic import BaseModel


class Card(BaseModel):
    heading: str
    summary: str
    visual: Optional[str] = None            # 對應的畫面重點（簡報／板書／程式碼），純口說卡無此欄
    timestamp_seconds: Optional[int] = None
    transcript_highlight: Optional[str] = None
    translation: Optional[str] = None
    # 「下一步」用：模型判斷這張卡有沒有可動手的事。沒有 structured output，模型漏欄位是常態，
    # 所以一律 optional 帶預設值——新欄位缺失絕不能讓整份摘要 parse 失敗。
    # actionable 只決定 UI 要不要主動把按鈕推到眼前；任何卡片都必須能手動觸發下一步（模型會誤判）
    actionable: bool = False
    action_hint: Optional[str] = None


class SummarizeRequest(BaseModel):
    url: str
    # provider："auto"／None＝免費模型優先、失敗才備援到有金鑰的付費供應商；
    #           "gemini"＝只用 gemini-flash-lite-latest；
    #           "opencode:／deepseek:／openai:／anthropic:<model_id>"＝只用該模型
    provider: Optional[str] = None
    # 深視覺：True 時 DeepSRT（Gemini 讀畫面）優先於字幕；預設關（字幕優先，省 Gemini 額度）
    deep_visual: bool = False


class AskMessage(BaseModel):
    role: str      # "user" / "assistant"
    content: str


class AskRequest(BaseModel):
    question: str
    video_id: Optional[str] = None   # 用來從快取撈逐字稿當背景知識
    history: List[AskMessage] = []   # 之前的對話（不含本次 question）
    provider: Optional[str] = None   # 同 SummarizeRequest；auto 時優先 Gemini（有搜尋工具）


class DeepDiveRequest(BaseModel):
    provider: Optional[str] = None
    source_title: str
    card: Card


class SaveNoteRequest(BaseModel):
    filename: str
    content: str
    folder: str = ""          # vault 內的相對資料夾；空字串代表預設筆記資料夾
    mode: str = "new"         # "new" 建立新筆記 / "append" 附加到現有筆記
    target_file: str = ""     # mode=append 時，要附加的現有 .md 檔名


class ImplementRequest(BaseModel):
    """把整支影片交給本機 CLI agent 產出實體檔案。

    cards 是**整支影片**的全部卡片，不是單張——實作的對象是影片，不是某個片段。
    """
    provider: Optional[str] = None    # 只在沒有 CLI、要產安裝教學時才會用到
    video_title: str = ""
    video_url: str = ""
    content_type: str = "other"
    track: Optional[str] = None       # 使用者覆寫用（類型判斷會誤判，要留逃生門）
    cli: Optional[str] = None         # "codex" / "claude"；不指定就用偵測到的第一個
    cli_model: Optional[str] = None   # 指定 CLI 要用哪個模型；留空用該 CLI 自己的預設
    effort: Optional[str] = None      # 思考強度（只有 Codex 有）：快一點還是深一點
    auto_run: bool = True             # False 時只產任務書並回傳指令
    cards: List[Card] = []


class RevealRequest(BaseModel):
    path: str


class SettingsUpdate(BaseModel):
    # 只更新有提供的欄位；傳空字串代表清除該設定
    gemini_api_key: Optional[str] = None
    opencode_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    output_language: Optional[str] = None
    ui_language: Optional[str] = None      # 介面語言（zh-Hant／en），也決定後端錯誤訊息的語言
    obsidian_vault_path: Optional[str] = None
    obsidian_notes_folder: Optional[str] = None
