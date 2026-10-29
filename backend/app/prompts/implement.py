"""實作任務書：把整部影片的卡片，變成交給 CLI agent 執行的一份任務。

跟 summarize 的 prompt 不同，這裡的讀者是**有檔案系統與網路能力的 agent**，
所以要求可以（也應該）更高：不只是寫一份計畫，而是直接把可以用的東西做出來，
影片沒講清楚的部分自己去查官方文件補齊。

四條 track 都產出實體檔案：
  build  可以跑的專案包        study  弄懂用的教學 HTML
  sop    照著做的引導 HTML     drill  練習題庫 HTML
"""
from pathlib import Path

from app.core import languages

TRACKS = ("build", "sop", "study", "drill")

# 設計守則與 prompt 分開放，社群可以直接改這份 markdown 而不必動程式碼
_RULES_PATH = Path(__file__).with_name("design_rules.md")


def design_rules() -> str:
    """單檔 HTML 的設計守則。讀不到就回空字串——產出會醜一點，但不該因此整個失敗。"""
    try:
        return _RULES_PATH.read_text(encoding="utf-8").strip()
    except Exception:  # noqa: BLE001
        return ""

TRACK_LABELS = {
    "build": "可執行的專案包",
    "sop": "一步一步的操作引導",
    "study": "弄懂與驗證的教學頁",
    "drill": "練習題庫",
}


def resolve_track(content_type: str, has_code: bool, override: str | None = None) -> str:
    """決定 track。

    教學型影片再依「有沒有程式碼」分流：有就給可跑的專案包，沒有就給操作引導——
    這是「不是每個人的實作都是寫程式」在資料層的落點。其餘類型一律走 study，
    drill 由使用者自己選（任何有知識密度的影片都可以拿來出題）。
    """
    if override in TRACKS:
        return override
    if (content_type or "").lower() == "tutorial":
        return "build" if has_code else "sop"
    return "study"


# 能上網查證時的規則（Codex CLI／Claude Code）
_RULES_BROWSE = """1. 事實只能來自「影片素材」或你**實際查證過**的官方來源。素材沒講、你也查不到的，
   就在產出裡明寫「影片未說明，需自行確認」，禁止用你的印象填空。
2. **所有連結都必須是你實際開啟確認過存在的網址。** 不確定的連結一律不要放——
   放一個點下去 404 的連結，比不放更糟。官方文件優先於部落格。"""

# 不能上網時的規則（Gemini API 免費層拿不到 Google Search grounding）。
# 這裡是最容易產生幻覺的地方：模型會憑印象寫出看起來很像真的、但根本不存在的網址。
# 解法不是叫它「小心」，是**直接拿掉輸出網址這個選項**。
_RULES_NO_BROWSE = """1. 你**沒有辦法上網查證**。因此事實只能來自「影片素材」本身。
   素材沒講的細節，一律寫成「影片未說明，需自行確認」，禁止用你的印象補。
   包括：版本號、價格、選單的確切位置、按鈕的確切名稱、日期、統計數字。
2. **嚴禁輸出任何網址。** 不准寫 http、https、www 開頭的任何字串，也不准把網址
   寫成純文字或放進 `href`。需要指向外部資源時，改成「搜尋關鍵字」的形式：
   例如寫成「官方文件：搜尋 `Obsidian community plugins` 」而不是給連結。
   你憑印象寫出來的網址有很高機率不存在，那比不給連結更糟。
   唯一例外：素材裡**原文出現過**的網址可以照抄，但要標明「出自影片」。
3. 產出開頭要有一段醒目的提醒，告訴讀者：這份內容是在沒有網路查證的情況下產生的，
   影片沒講到的部分需要自行確認。"""

_TAIL_HTML = """3. 產出的 HTML 必須是**單一檔案、可離線開啟**：CSS 與 JS 全部內嵌，不要引用任何 CDN、
   不要用外部字型。圖片用內嵌 SVG，不要連外部圖床。
4. 版面要能在手機與桌機都讀得順；深色／淺色模式都要看得清楚（用 prefers-color-scheme）。
5. 所有文字使用指定的輸出語言，但專有名詞、指令、檔名、介面上的按鈕字樣保留原文
   （介面是英文的就寫英文，並在後面用括號附上翻譯）。
6. **設計守則是硬規則，逐條照做**（見文件末的「單檔 HTML 設計守則」）。
   交件前跑一次守則最後的自檢清單，任一條沒過就先修再交。
7. 做完後，最後一行輸出 `PRODUCED:` 後面接你建立的檔案名稱，用逗號分隔。
"""

# build 不產網頁，就不該帶那份 10KB 的守則，規則也不能指向不存在的東西
_TAIL_PLAIN = """3. 所有文字使用指定的輸出語言，但專有名詞、指令、檔名保留原文。
4. 指令要能直接複製貼上執行；不能自動化的步驟標成 `# 手動：…`。
5. 做完後，最後一行輸出 `PRODUCED:` 後面接你建立的檔案名稱，用逗號分隔。
"""


# Gemini 是單次生成，沒有檔案系統工具，所以要它把檔案寫進回覆裡由後端落檔。
# 用純文字分隔而不是 JSON：HTML 裡滿是引號與反斜線，包成 JSON 幾乎必然解析失敗。
FILE_BEGIN = "<<<YCR-FILE:"
FILE_END = "<<<YCR-END>>>"

_FILE_FORMAT = f"""
## 輸出格式（很重要，格式錯了整份就白做）

你沒有檔案系統可以寫入，所以請把每個檔案**原樣寫在回覆裡**，用下列標記包起來：

{FILE_BEGIN}檔名>>>
（檔案的完整內容，不要用 markdown 程式碼框包住）
{FILE_END}

規則：
- 每個檔案一組標記，標記必須各自獨占一行。
- 檔名只寫名稱不要路徑，例如 `guide.html`。
- 標記之間放**完整可用**的檔案內容，不要寫「（其餘省略）」「...」這類佔位。
- 標記以外不要輸出任何解釋文字。
- 最後一行輸出 `PRODUCED:` 加上所有檔名，用逗號分隔。
"""


def file_format() -> str:
    return _FILE_FORMAT


# 只有這幾條 track 會產出網頁，也只有它們需要（並值得）帶上設計守則
HTML_TRACKS = ("sop", "study", "drill")


def _common_rules(can_browse: bool, with_design: bool) -> str:
    head = _RULES_BROWSE if can_browse else _RULES_NO_BROWSE
    tail = _TAIL_HTML if with_design else _TAIL_PLAIN
    return f"\n共同鐵則（每一條都會被檢查）：\n{head}\n{tail}"

_TRACK_SPEC = {
    "build": """## 你要做的事

在目前這個工作目錄裡，把影片教的東西做成一份**別人拿了就能跑**的東西。

先判斷影片屬於哪一種，兩種的產出不一樣：

**A. 影片在教寫程式／建專案** → 做成可執行的專案包
- `README.md`：這是什麼、需要哪些環境與版本、**逐步執行指令**、怎麼確認成功了。
  影片講到的版本號、套件名、參數要原樣寫進去。
- 實際的程式碼檔案（不是片段，是能跑的完整檔案）。影片示範到哪就做到哪。
- 流程需要多個指令就寫成 `setup.sh`，每行加註解說明在做什麼。

**B. 影片在教「怎麼使用某個工具或 AI」** → 做成可以交給另一個 AI 執行的指令包
  （例如影片教怎麼用某個 AI 剪片、怎麼裝某個 skill／外掛／MCP，
   產出就該是「照著這份跑，就會把那套環境裝好並跑起來」）
- `AGENTS.md`：寫給 coding agent 看的任務書。內容是**祈使句的操作步驟**，
  不是說明文。例如「下載 X 並安裝到 Y」「建立設定檔 Z，內容如下」。
  Codex 與 Claude Code 都會自動讀取 repo 根目錄的 AGENTS.md／CLAUDE.md，
  所以這份放進專案後，之後在那個資料夾開 agent 就直接有脈絡。
- `setup.sh`：影片裡所有可以自動化的步驟，逐行寫成指令並加註解。
  不能自動化的（要在網頁上點、要登入、要付費）明確標成 `# 手動：…`。
- `README.md`：怎麼用這份包——先跑什麼、再把 AGENTS.md 交給誰、做完會得到什麼。

兩種都要產出 `NOTES.md`：影片沒講清楚、由你補上的部分逐條列出並附來源；
以及你做了哪些合理推斷。這份是給使用者判斷「哪些能全信」用的。

⚠️ **失敗條件（比做不完更嚴重）**：產出如果只是把影片內容換個排版重講一遍，
就是失敗。判準很簡單——**跑得起來嗎？** 專案包要有可以執行的檔案；指令包要有
可以貼進終端機或交給 agent 的步驟。兩者都不成立的東西，不管排版多漂亮都不算數。

如果影片內容**兩種都不像**（例如心得分享、觀念介紹、產品開箱、只是示範某個
工具長什麼樣，沒有任何可以照著執行的操作），**不要硬做**。改成產出一份
`README.md`，開頭第一行就寫「這支影片不適合做成可執行的專案」，說明原因，
再列出它實際適合的做法（例如改用操作引導或教學頁），然後停手。
誠實說做不到，比交出一個跑不起來的空殼有用得多。

驗收標準寫進 README 最後一節：一個具體的指令或操作，跑完看到什麼就代表成功。""",

    "sop": """## 你要做的事

使用者**看不懂那支影片**，或看了跟不上。你要做一份比影片更好懂的引導頁 `guide.html`，
讓他照著點就能完成影片裡做的事。

這是這份工作最重要的部分，請認真做：

- **每一步都要說清楚「現在要點哪裡」**：確切的選單路徑（例如「左下角齒輪 → Community plugins
  → Browse」）、按鈕上的原文字樣、以及**可以直接點的連結**（下載頁、外掛頁、設定文件）。
  影片裡一閃而過的畫面，你要去官方網站查清楚實際的位置與名稱。
- **每一步都要有「看到這個就對了」**：完成後畫面上會出現什麼，讓他能自己確認沒做錯。
- **每一步都要有「如果卡住」**：最常見的失敗狀況與解法。這是影片通常不會講、但新手一定會遇到的。
- **專有名詞就地解釋**：頁面裡出現的每一個術語，第一次出現時就用一句話說明它是什麼、
  為什麼需要它。不要假設使用者知道。
- 影片沒交代的前置步驟（要先裝什麼、要先註冊什麼）要補上，並標明是你補的。

`guide.html` 的功能要求：
- 每個步驟一張卡片，有 checkbox 可以勾「我做完了」，用 localStorage 記住進度（重開還在）。
- 頂部有進度條顯示完成幾步。
- 術語用 `<details>` 或 hover 卡片就地展開，不要另開一區讓人來回捲。
- 最後一段是「完成後你應該可以做到什麼」，讓使用者確認整件事成功了。

另外產出 `SOURCES.md`：你查證過的每個連結，加一句「這裡查到什麼」。""",

    "study": """## 你要做的事

做一份 `study.html`，讓使用者**真的弄懂**這支影片在講什麼，而不只是「看過了」。

必須包含：
- **術語表**：把影片裡出現的**每一個**專有名詞、縮寫、行話都列出來，一個都不要漏。
  每個給：一句話白話解釋、為什麼會用到它、以及跟哪些概念容易搞混。
- **難點拆解**：影片裡講得快、跳步驟、或需要背景知識才聽得懂的地方，逐個展開。
  用「影片說了什麼 → 它預設你已經知道什麼 → 補上那塊」的結構。
- **延伸**：想更深入該讀什麼。每則附**查證過的真實連結**與一句話說明為什麼值得讀。
- **自我驗證**：8-12 題可以自問的問題，答案用 `<details>` 收起來。
  題目要能檢查「有沒有真的懂」，不是背誦題——例如「如果把 X 改成 Y 會發生什麼」。

版面用可折疊區塊，讓使用者能先掃過大綱再下鑽。""",

    "drill": """## 你要做的事

做一份 `drill.html`：把影片內容變成可以反覆練習的題庫。

必須包含：
- **15-25 題**，涵蓋影片的所有重點（不要只出前面幾段的）。題型混合：
  觀念判斷、情境應用、找錯、以及「這種情況你會怎麼做」的開放題。
- 每題附：正確答案、**為什麼**（不是只給答案）、以及對應影片的哪個段落。
- 開放題給評分要點（自己對照著看有沒有講到）。
- 互動：作答後才顯示答案；最後統計答對幾題；可以「只重做答錯的」。
  進度用 localStorage 記住。

題目要從影片實際內容出的——禁止出影片沒提過的東西來湊題數。""",
}


def _cards_block(cards: list[dict]) -> str:
    """整部影片的卡片攤平成素材。實作是針對整支影片，不是單張卡。"""
    out = []
    for i, card in enumerate(cards, start=1):
        parts = [f"### 卡片 {i}：{card.get('heading') or ''}"]
        ts = card.get("timestamp_seconds")
        if ts is not None:
            parts.append(f"（影片 {int(ts) // 60:02d}:{int(ts) % 60:02d}）")
        parts.append(str(card.get("summary") or ""))
        if card.get("visual"):
            parts.append(f"【畫面】{card['visual']}")
        if card.get("transcript_highlight"):
            parts.append(f"【原話】{card['transcript_highlight']}")
        out.append("\n".join(p for p in parts if str(p).strip()))
    return "\n\n".join(out)


def task_markdown(video_title: str, video_url: str, cards: list[dict], track: str,
                  language: str = languages.DEFAULT, can_browse: bool = True,
                  inline_files: bool = False) -> str:
    """組出完整任務書。

    can_browse 決定「查證」那一段規則怎麼寫——執行者是 CLI agent（能上網）還是
    Gemini API（免費層沒有搜尋）。prompt 必須誠實反映執行者的能力，
    否則就是在叫一個上不了網的模型「去查證」，那只會換來編造的網址。
    """
    lang = languages.get(language)
    spec = _TRACK_SPEC.get(track, _TRACK_SPEC["study"])
    source = (f"\n影片網址：{video_url}"
              f"（{'可以打開來對照，但不要只依賴它' if can_browse else '你打不開它，僅供標註來源'}——"
              f"素材已經是整理過的重點）") if video_url else ""
    note = "" if can_browse else (
        "\n\n> 注意：上面這段 track 說明裡若提到「查證過的連結」「去官方網站查」，"
        "在你這次的執行環境下**做不到**，一律以下面共同鐵則第 1、2 條為準。")
    # 設計守則將近 10KB，而 agent 每輪工具呼叫都會重送整份 context。
    # 只有真的要產出網頁的 track 才帶上它。
    rules_doc = design_rules() if track in HTML_TRACKS else ""
    design_block = f"\n\n---\n\n{rules_doc}\n" if rules_doc else ""
    fmt = _FILE_FORMAT if inline_files else ""
    return f"""# 實作任務：{video_title}

{lang.directive}

你是一個會直接把東西做出來的助手。以下是使用者看完一支影片後整理出的**完整重點卡片**，
請據此在**目前的工作目錄**產出檔案。做完就好，不要只給建議、不要問問題、不要等確認。
{source}

{spec}{note}
{fmt}
{_common_rules(can_browse, bool(rules_doc))}

---

## 影片素材（整支影片的全部重點）

{_cards_block(cards)}
{design_block}"""


_TEACH_SYSTEM = """你在教一個沒有裝過命令列工具的人，把 coding agent CLI 裝起來。
對方可能沒用過終端機，所以每一步都要講清楚在哪裡打字、會看到什麼。
鐵則：只寫你確定的指令與網址；不確定的地方明說「請以官方文件為準」並附文件連結。"""


def teach_system(language: str) -> str:
    return languages.get(language).directive + "\n\n" + _TEACH_SYSTEM


def teach_prompt(specs: list[dict], language: str = languages.DEFAULT) -> str:
    """沒偵測到 CLI 時的降級路徑：用便宜模型產一份安裝教學。

    這條路徑本身也要是有用的產出，不能只是一句「請先安裝」——使用者卡在這裡就走不下去了。
    已知的安裝指令由後端提供（不讓模型自己回想，那是編造的溫床），模型負責把它寫成
    對新手友善的步驟。
    """
    lang = languages.get(language)
    known = "\n".join(
        f"- {s['label']}：安裝指令 `{s['install']}`（或 `{s['install_alt']}`）；"
        f"登入方式：{s['auth']}；官方文件：{s['docs']}"
        for s in specs)
    return f"""{lang.directive}

使用者想用「實作」功能，但他的電腦上找不到任何 coding agent CLI。
請寫一份安裝教學，讓他能自己裝起來。

以下是**確定正確**的資訊，請直接使用，不要改寫指令本身：
{known}

教學要包含：
1. 一句話說明這兩個工具是什麼、為什麼這個功能需要它（它們能讀寫檔案、能上網查證，
   所以能真的把東西做出來，而不只是給文字建議）。
2. 兩者擇一即可，各自的安裝步驟：怎麼打開終端機（Mac 是 Spotlight 搜尋 Terminal，
   Windows 是 PowerShell）、要貼什麼指令、跑完看到什麼代表成功。
3. 安裝前需要什麼（Node.js）：怎麼確認自己有沒有、沒有的話去哪裡裝（附官方下載頁連結）。
4. 登入步驟，以及怎麼確認登入成功。
5. 裝好之後回到這個 App 要做什麼（重新按一次「開始實作」）。
6. 常見問題：指令找不到（command not found）通常是什麼原因、怎麼處理。

輸出格式：Markdown，用編號步驟。指令用程式碼區塊。不要輸出 JSON。"""
