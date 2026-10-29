"""摘要與深掘的 prompt。素材可能含「【畫面 MM:SS】」開頭的畫面筆記，prompt 要真的用它。

產品定位：這不是摘要工具，是「知識萃取」工具——使用者用卡片**取代觀看整支影片**。
因此 prompt 的主軸是「什麼有知識、什麼沒有」的判準，不是張數配額；張數是結果不是目標。
"""
import re

from app.core import languages

_TS = re.compile(r"^\[(\d+)\]", re.M)

# 一張卡涵蓋的影片秒數。實測校準：使用者滿意的萃取顆粒度約 25-40 秒／張；
# 只給判準不給數字時，模型會自動收斂回「摘要」顆粒度（60 秒以上／張），細節就流失了
_SEC_PER_CARD_DENSE = 25   # → 張數上限
_SEC_PER_CARD_LOOSE = 40   # → 期望下限（診斷用，不是配額）


def _card_range(text: str) -> tuple[int, int, int]:
    """回傳 (期望下限, 上限, 跨度秒)；拿不到時間戳回 (0, 0, 0)。

    下限的作用不是配額，是**自我診斷訊號**：明顯低於它，通常代表模型在做摘要而非萃取。
    prompt 端必須把它寫成診斷語言並留閒聊段落的出口，否則會變成硬湊張數。
    """
    secs = [int(s) for s in _TS.findall(text or "")]
    if len(secs) < 2:
        return 0, 0, 0
    span = max(secs) - min(secs)
    if span < 60:
        return 0, 0, span
    return max(3, span // _SEC_PER_CARD_LOOSE), max(5, span // _SEC_PER_CARD_DENSE), span


# 取捨與分級的判準。比任何張數配額都準，因為它跟著內容密度走
_IMPORTANCE = """如何決定內容的去留與詳細程度（推理過程不要輸出，只輸出 JSON）：

第一步 — 這段素材在教什麼？認出類型，把英文代碼填進 content_type 欄位：
- tutorial（教學操作）／concept（觀念分析）／interview（訪談對談）／review（評測比較）／news（新聞資訊）／other
第二步 — 依類型認定「一個知識單位」是什麼：
- tutorial 教學／操作型 → 每一個可獨立執行的操作、設定、技巧、避雷提醒
- concept 觀念／分析型 → 每一個獨立主張＋它的論證或證據
- interview 訪談／對談型 → 每一個獨立觀點、經驗、判斷、故事
- review 評測／比較型 → 每一個比較維度＋該維度的結論
- news 新聞／資訊型 → 每一個獨立事件、數據、影響
第三步 — 依重要性決定「呈現得多詳細」（注意：這是決定詳細度，不是決定要不要寫）：
- 核心（講者主要在教的、簡報／板書上的、明講「重點是」「注意」「關鍵在」的）→ 獨立一張卡，條列寫滿
- 支撐（例子、數字、操作細節、原因解釋）→ 併進對應核心那張卡的條列裡
- 順帶（一句帶過的工具名、延伸建議、冷知識）→ 至少要有一條條列提到它，不可整個消失

丟棄（且僅丟棄這些）：寒暄自介、訂閱按讚提醒、業配廣告、純過場、與前面卡片完全重複的內容。

一句話總結你的任務：使用者不會再看這支影片，凡是影片裡有而卡片裡沒有的知識，他就永遠不會知道。"""

_SUMMARIZE_SYSTEM = """你是知識萃取助手。使用者用你產出的卡片**取代觀看整支影片**，他不會再回去看原片。

因此你的任務不是「摘要」（壓縮成大意），而是「萃取」：影片裡教的每一個知識、每一個具體做法、
每一個數字與結論，都必須出現在卡片裡。判準只有一個——讀者看了會不會「知道一件原本不知道的事」；
會，就保留；不會（寒暄、業配、訂閱提醒、過場、重複），才丟棄。

素材可能同時包含「口說逐字稿」與「【畫面 MM:SS】」開頭的畫面筆記（簡報、板書、程式碼、圖表）。
講者放上簡報或板書的段落，就是他自認的重點——畫面筆記的優先級高於閒聊性口說內容。

鐵則（違反任何一條即為失敗）：
1. 只能使用素材中出現的資訊。所有數字、名稱、步驟、結論都必須來自素材本身；禁止用你自己的知識補充、修正或猜測素材沒說的事。
2. 你的回覆必須是單一 JSON 物件：第一個字元是 {，最後一個字元是 }。不要輸出思考過程、前言、道歉、解釋或 markdown 代碼框。
3. 所有欄位一律使用指定的輸出語言。{quote_note}
4. 素材若沒有實質知識內容（純寒暄、純音樂、純廣告），輸出 {"title": "（無實質內容）", "cards": []}，不要硬編卡片。"""


def summarize_system(language: str) -> str:
    """組出摘要的 system prompt（輸出語言硬指令壓在最前面）。"""
    lang = languages.get(language)
    return lang.directive + "\n\n" + _SUMMARIZE_SYSTEM.replace("{quote_note}", lang.quote_note)


def summarize_prompt(content: dict, language: str = languages.DEFAULT) -> str:
    """組出單一片段的摘要 prompt（卡片 JSON 契約）。"""
    lang = languages.get(language)
    has_ts = content.get("has_timestamps") or content["type"] == "youtube"
    text = content["text"]
    has_visual = "【畫面" in text

    src = "影片素材（口說逐字稿每行格式為 [秒數] 文字）" if has_ts else "文章"
    seg_note = "（這是長內容的其中一個片段，請只就這段內容做卡片，不要提及『片段』）" if content.get("is_segment") else ""
    if content.get("is_continuation"):
        seg_note = ("（以下是同一影片「尚未被整理的後段」素材。前段已有卡片，"
                    "你只負責這段：接續時間軸產卡，不要重複前面的內容，不要重新給 title 以外的總覽卡）")
    ts_hint = ("timestamp_seconds：該段落第一行口說的秒數，直接取 [秒數] 的整數，必填，不可為 null"
               if has_ts else "timestamp_seconds：填 null")

    visual_field = ""
    visual_rules = ""
    if has_visual:
        visual_field = ('\n      "visual": "這張卡對應的畫面重點：簡報標題與要點、板書內容、程式碼片段摘述、'
                        '圖表的軸與結論。沒有對應畫面就整個不要輸出這個 key",')
        visual_rules = """
- 素材含「【畫面 MM:SS】」畫面筆記：有對應畫面的卡片要填 visual 欄位；純口說卡不要輸出 visual 這個 key，也不要填空字串
- 簡報／板書上的文字是講者自己挑出來的重點，優先級最高：每一頁承載內容的簡報都要在卡片裡找得到，過場頁與純裝飾頁可以省略
- visual 內容要抄到具體文字（標題、條列、公式、程式碼），不要只寫「簡報上有圖表」這種空話"""

    lo, hi, span = _card_range(text)
    ceiling = (
        f"\n- 顆粒度校準：這段約 {span // 60} 分鐘，萃取得當通常會產出 **{lo}-{hi} 張**卡"
        f"（平均 {_SEC_PER_CARD_DENSE}-{_SEC_PER_CARD_LOOSE} 秒的內容一張）。"
        f"這不是配額，是**自我檢查訊號**：如果你只寫了 {max(2, lo - 2)} 張以下，"
        f"代表你在做「摘要」而不是「萃取」——回頭重新掃一遍素材，你一定漏掉了具體做法、"
        f"數字、工具名、操作步驟這類細節。唯一的例外是這段真的大部分在寒暄或業配，那才可以少於下限"
        if lo else "")

    return f"""{lang.directive}

請將以下{src}萃取成學習卡片。{seg_note}

內容：
{text}

輸出以下 JSON（不加 markdown、不加 ```）：
{{
  "title": "內容整體標題",
  "content_type": "tutorial",
  "cards": [
    {{
      "heading": "這張卡的知識點標題（20字以內，要能獨立看懂）",
      "summary": "條列式學習重點，每點用「• 」開頭，4-8點，每點80-150字。要求：寫的是『學到什麼』而不是『講者說了什麼』。包含：具體步驟、操作方法、數字細節、注意事項、原因解釋。讀者看完這張卡片要能直接照做或理解概念，不需要去看影片。",{visual_field}
      "transcript_highlight": "從原文直接複製2-5句最能說明這個段落的原話，保留原文語言，不改寫，但要移除每行開頭的 [秒數] 標記",
      "translation": "上方節錄的目標語言翻譯；原文已是目標語言就填 null",
      "timestamp_seconds": 0,
      "actionable": true,
      "action_hint": "一句話的下一步"
    }}
  ]
}}

{_IMPORTANCE}

規則：
- 做法：把這段素材**從頭到尾掃過一遍**，依上面的判準先在心裡列出所有知識單位，再逐一成卡。漏掉知識就是失敗
- 顆粒度：一張卡承載一個可獨立理解的知識單位。同一個操作的步驟 1-2-3 屬於同一張卡；
  但「用 email 註冊」和「匯入舊 AI 的記憶」是兩件不同的事，要分成兩張。
  拿不準時**寧可分開**——分開的卡片好讀，硬合併會把細節壓縮掉{ceiling}
- 覆蓋整段素材：從素材開頭到最後一個時間戳附近都要有卡，最後一張卡的時間戳應落在素材尾端 15% 範圍內。禁止只整理前半就停——沒做完就是失敗
- {ts_hint}
- summary 禁止出現「講者提到」「影片說明」「本段介紹」等空話，直接寫知識內容
- transcript_highlight 必填：從素材逐字複製，一字不改（可跨行拼接）。禁止改寫、翻譯、自行創作；找不到完美句子就選最接近的原句
- 每張卡寫完自問「這張卡的每一句話在素材裡找得到依據嗎」，找不到的句子刪掉{visual_rules}
- content_type：填第一步認出的類型代碼，只能是 tutorial／concept／interview／review／news／other 其中之一（英文小寫，不要翻譯）
- actionable：布林值（true／false，不是字串）。判準是「讀者看完這張卡，有沒有一件現在就能自己動手的事」——
  tutorial 是照著操作一遍，concept 是找資料驗證或自己推導一次，review 是實際去比較，news 是追蹤後續發展。
  純背景鋪陳、純心得感想、單純的定義說明填 false。寧可保守：不確定就填 false
- action_hint：actionable 為 true 時，用一句話寫出那件事（動詞開頭，25 字內，例如「照著設定一次 webhook 並確認收得到事件」）；false 時填 null"""


_DEEPDIVE_SYSTEM = """你是深度解析專家，把複雜概念解釋清楚。
鐵則：卡片內容是事實依據；你可以用通用知識解釋概念，但不確定的具體事實（數字、人名、年份、來源）要明說「不確定」，禁止編造。"""


def deepdive_system(language: str) -> str:
    """組出深掘的 system prompt。"""
    return languages.get(language).directive + "\n\n" + _DEEPDIVE_SYSTEM


def deepdive_prompt(source_title: str, card: dict, language: str = languages.DEFAULT) -> str:
    """組出單張卡片的深掘 prompt。"""
    lang = languages.get(language)
    visual = (card or {}).get("visual")
    visual_line = f"\n畫面重點：{visual}" if visual else ""
    anchor = "\n若卡片含畫面重點（visual），以其為錨展開。" if visual else ""
    return f"""{lang.directive}

針對「{source_title}」中的知識點，給我深入解析：

標題：{card["heading"]}
摘要：{card["summary"]}{visual_line}

請提供：1.詳細解釋 2.具體例子 3.延伸概念 4.重要性{anchor}
直接輸出內容，不需要 JSON。"""
