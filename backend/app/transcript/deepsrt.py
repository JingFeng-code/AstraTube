"""DeepSRT 轉錄路徑：把公開 YouTube 網址直接餵給 Gemini，一次取回逐字稿＋畫面筆記。

三條工程結論落實在這個模組：
  1. 攝取是固定成本 → 一支影片只打一次影片呼叫，同時要逐字稿與畫面筆記。
  2. 樂觀全量＋斷點補跑 → 用 ###END### 當哨兵，沒看到就對缺的時間範圍補跑（上限 2 次）。
  3. 模型會擺爛 → 找不到 ###TRANSCRIPT### 標記就用加強語氣重打。
  4. 模型的「畫面時間戳」準、「口說時間戳」不準（實測見下）→ 有官方字幕時，
     口說逐字稿一律以字幕為準，Gemini 只負責它獨有的畫面筆記。
另外，某把金鑰額度耗盡時換下一把金鑰接續補跑，已拿到的內容不丟棄。

實測（2026-08-13，TED-Ed MMmOLN5zBLY，5:04）：Gemini 自報的口說時間戳從片頭
誤差 0 秒，一路單調漂移到片尾 +98 秒，且最後約 90 秒的內容整段沒轉出來；
同一次回應裡的畫面筆記時間戳卻和字幕對得上（誤差 ≤3 秒）。
結論：能拿到字幕就別用模型的口說時間軸。
"""
import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from app.llm import gemini
from app.llm.base import KeyExhaustedError
from app.transcript import cache

CACHE_PREFIX = "deepsrt_v1:"
MAX_RESUMES = 2          # 斷點補跑次數上限
MAX_STRICT_RETRIES = 2   # 「模型擺爛」加強語氣重試上限
MAX_ERRORS = 3           # 非額度類錯誤的容忍次數

DIRECTIVE = """你是影片轉錄引擎。輸出以下三段，除此之外不要輸出任何文字：

###TRANSCRIPT###
逐字稿。每行格式：[MM:SS-MM:SS] 說話內容。每行涵蓋時間不得超過 8 秒。用影片原語言轉錄（中文影片輸出繁體中文）。
###VISUALS###
畫面筆記。影片中每個「有資訊量的畫面」各一行：[MM:SS] 類型：內容。
類型包括：簡報（抄錄標題與要點文字）、板書/手寫、程式碼/螢幕操作（摘述關鍵內容）、圖表（描述軸與結論）、示範動作。
沒有文字性畫面的片段不要硬寫。純談話頭影片此段可只有幾行或寫「（無）」。
###END###

規則：不要解釋、不要道歉、不要加 markdown 代碼框，直接從 ###TRANSCRIPT### 開始輸出。"""

_STRICT_SUFFIX = "\n\n再次強調：不要解釋、不要道歉、不要描述影片，直接從第一行 ###TRANSCRIPT### 開始輸出。"

# 判定「整批系統性偏移」的門檻：減去起點後有這個比例的行落回合理範圍，就視為模型重複加了偏移
_SHIFT_RATIO = 0.8

# 一行時間戳：[MM:SS]、[MM:SS-MM:SS]、[HH:MM:SS]、[123] 都吃
_TS_LINE = re.compile(
    r"^\s*[\[【]\s*([\d:]+)\s*(?:[-–—~]\s*[\d:]+\s*)?[\]】]\s*(.*)$"
)
_CJK = re.compile(r"[一-鿿]")

# call(directive, start_offset, key_index) -> 模型輸出文字
VideoCall = Callable[[str, Optional[str], int], str]


@dataclass
class Parsed:
    """一次模型輸出的解析結果。"""
    transcript: List[Tuple[int, str]] = field(default_factory=list)
    visuals: List[Tuple[int, str]] = field(default_factory=list)
    complete: bool = False     # 是否看到 ###END### 哨兵
    has_marker: bool = False   # 是否看到 ###TRANSCRIPT### 標記


def _to_seconds(ts: str) -> Optional[int]:
    """把 MM:SS / HH:MM:SS / 純秒數轉成秒。"""
    parts = ts.split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    if len(nums) == 1:
        return nums[0]
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    if len(nums) == 3:
        return nums[0] * 3600 + nums[1] * 60 + nums[2]
    return None


def _mmss(sec: int) -> str:
    """秒數轉 MM:SS（超過一小時仍用累加分鐘表示，與模型輸出慣例一致）。"""
    return f"{sec // 60:02d}:{sec % 60:02d}"


def _parse_lines(block: str) -> List[Tuple[int, str]]:
    """把一段文字裡有時間戳的行解析成 (秒數, 內容)。"""
    out: List[Tuple[int, str]] = []
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("```") or line in ("（無）", "(無)", "無"):
            continue
        m = _TS_LINE.match(line)
        if not m:
            continue
        sec = _to_seconds(m.group(1))
        content = m.group(2).strip()
        if sec is None or not content:
            continue
        out.append((sec, content))
    return out


def parse_response(raw: str) -> Parsed:
    """把模型輸出拆成逐字稿行、畫面筆記行，並回報是否完整／是否依格式輸出。"""
    text = raw or ""
    has_marker = "###TRANSCRIPT###" in text
    complete = "###END###" in text

    body = text.split("###TRANSCRIPT###", 1)[1] if has_marker else text
    body = body.split("###END###", 1)[0]
    if "###VISUALS###" in body:
        t_block, v_block = body.split("###VISUALS###", 1)
    else:
        t_block, v_block = body, ""

    return Parsed(transcript=_parse_lines(t_block), visuals=_parse_lines(v_block),
                  complete=complete, has_marker=has_marker)


def merge(transcript: List[Tuple[int, str]], visuals: List[Tuple[int, str]]) -> str:
    """把畫面筆記依時間戳插入逐字稿對應位置，形成單一合併文字。

    逐字稿行輸出成 `[秒數] 內容`（與其他轉錄來源一致），
    畫面筆記行輸出成 `【畫面 MM:SS】類型：內容`，同時間點時畫面排在口說之前。
    """
    rows = [(sec, 1, f"[{sec}] {txt}") for sec, txt in transcript]
    rows += [(sec, 0, f"【畫面 {_mmss(sec)}】{txt}") for sec, txt in visuals]
    rows.sort(key=lambda r: (r[0], r[1]))
    return "\n".join(r[2] for r in rows)


def _is_chinese(transcript: List[Tuple[int, str]]) -> bool:
    """以中文字比例判斷逐字稿語言。"""
    sample = "".join(t for _, t in transcript[:200])
    if not sample:
        return False
    return len(_CJK.findall(sample)) >= max(10, len(sample) * 0.1)


def _extend(dst: List[Tuple[int, str]], new: List[Tuple[int, str]], since: Optional[int]) -> int:
    """把補跑拿到的行併入既有清單（去重、只收 since 之後），回傳實際新增筆數。"""
    seen = set(dst)
    added = 0
    for sec, txt in new:
        if since is not None and sec < since:
            continue
        if (sec, txt) in seen:
            continue
        seen.add((sec, txt))
        dst.append((sec, txt))
        added += 1
    return added


def _build_directive(start_sec: Optional[int], strict: bool,
                     duration: Optional[int] = None) -> str:
    """組出這一次呼叫要用的指令（補跑時明講起點與座標系，擺爛時加強語氣）。"""
    d = DIRECTIVE
    if duration is not None:
        d += (f"\n\n這支影片全長 {_mmss(duration)}。時間戳一律使用「從影片開頭起算的絕對時間」，"
              f"不得輸出超過 {_mmss(duration)} 的時間戳。")
    if start_sec is not None:
        d += (f"\n\n這是接續補跑：你看到的仍然是**完整影片**（沒有被裁切）。"
              f"只輸出影片 {_mmss(start_sec)} 之後的內容，{_mmss(start_sec)} 之前的部分已經有了，不要重複輸出。"
              f"時間戳照舊用影片開頭起算的絕對時間，"
              f"不要因為這是接續就對時間戳做任何偏移或加總。")
    if strict:
        d += _STRICT_SUFFIX
    return d


def _video_duration(youtube_url: str) -> Optional[int]:
    """取得影片總長度（秒），當作時間戳的權威上界。拿不到回 None（略過上界檢查）。"""
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True,
                               "no_warnings": True}) as y:
            info = y.extract_info(youtube_url, download=False)
        sec = (info or {}).get("duration")
        return int(sec) if sec else None
    except Exception as e:  # noqa: BLE001
        print(f"[deepsrt] 取得影片長度失敗，略過時間戳上界檢查：{e}", flush=True)
        return None


def sanitize(lines: List[Tuple[int, str]], start_sec: Optional[int],
             duration: Optional[int], label: str = "") -> List[Tuple[int, str]]:
    """以影片長度為上界，校正／丟棄不合理的時間戳。

    模型在補跑時可能誤把起點偏移再加一次（座標系混淆），也可能單純幻覺出超過
    影片長度的時間戳。時間戳格式合法但語義錯誤，不檢查就會靜默污染整份逐字稿：
      1. 整批超出、但減去 start_sec 後多數落回範圍 → 判定重複偏移，整批修正
      2. 個別仍超出上界的行 → 丟棄
    """
    if not lines or duration is None:
        return lines
    over = [s for s, _ in lines if s > duration]
    if not over:
        return lines

    if start_sec:
        shifted = [(s - start_sec, t) for s, t in lines]
        ok = sum(1 for s, _ in shifted if 0 <= s <= duration)
        if ok >= len(lines) * _SHIFT_RATIO:
            print(f"[deepsrt] {label}偵測到重複偏移：{len(over)}/{len(lines)} 行超出片長 "
                  f"{_mmss(duration)}，整批減去起點 {_mmss(start_sec)} 修正", flush=True)
            return [(s, t) for s, t in shifted if 0 <= s <= duration]

    kept = [(s, t) for s, t in lines if s <= duration]
    print(f"[deepsrt] {label}丟棄 {len(over)} 行超出片長 {_mmss(duration)} 的時間戳"
          f"（最大 {_mmss(max(over))}）", flush=True)
    return kept


_REF_LINE = re.compile(r"^\[(\d+)\]\s*(.+)$")


def _parse_reference(text: str) -> List[Tuple[int, str]]:
    """把字幕文字（每行 `[秒數] 內容`）解析成 (秒數, 內容)。"""
    out: List[Tuple[int, str]] = []
    for line in (text or "").splitlines():
        m = _REF_LINE.match(line.strip())
        if m:
            content = m.group(2).strip()
            if content:
                out.append((int(m.group(1)), content))
    return out


def _gemini_call(youtube_url: str) -> VideoCall:
    """預設的影片呼叫實作（真的打 Gemini）。"""
    def call(directive: str, start_offset: Optional[str], key_index: int) -> str:
        return gemini.generate_video(youtube_url, directive,
                                     start_offset=start_offset, key_index=key_index)
    return call


def transcribe(youtube_url: str, video_id: Optional[str] = None, *,
               call: Optional[VideoCall] = None,
               key_count: Optional[int] = None,
               use_cache: bool = True,
               duration: Optional[int] = None,
               reference_transcript: Optional[str] = None) -> Tuple[str, bool]:
    """對一支公開 YouTube 影片做 DeepSRT 轉錄，回傳 (合併逐字稿, is_chinese)。

    reference_transcript 是官方字幕（每行 `[秒數] 文字`）。有給的話，最終輸出的
    口說部分用它、時間軸也用它，Gemini 的口說輸出只留著驅動補跑判斷；沒給才退回
    完全採用 Gemini 的口說輸出。理由見模組 docstring 的實測數據。

    call／key_count／duration 可注入，用於測試；正式流程使用 Gemini、目前設定的
    金鑰把數，並自行查出影片長度當時間戳上界。
    """
    # 有無字幕基準會產出不同結果，快取鍵要分開，否則兩種模式互相污染
    cache_key = f"{CACHE_PREFIX}{'ref:' if reference_transcript else ''}{video_id or youtube_url}"
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            print(f"[deepsrt] 命中快取，直接回傳（{cache_key}）", flush=True)
            return cached

    do_call = call or _gemini_call(youtube_url)
    keys = key_count if key_count is not None else max(1, gemini.key_count())
    if duration is None and call is None:  # 注入 call 的測試流程不打網路
        duration = _video_duration(youtube_url)
    if duration:
        print(f"[deepsrt] 影片長度 {_mmss(duration)}，作為時間戳上界", flush=True)

    transcript: List[Tuple[int, str]] = []
    visuals: List[Tuple[int, str]] = []
    complete = False
    key_index = 0
    resumes = strict_retries = errors = 0
    strict = False

    while True:
        # 用「已覆蓋到的最大秒數」當補跑起點：模型輸出未必單調遞增，不能取清單最後一筆
        start_sec = (max(s for s, _ in transcript) + 1) if transcript else None
        directive = _build_directive(start_sec, strict, duration)

        try:
            # 一律不用 videoMetadata 裁切：官方回報有 bug，且裁切不省攝取成本
            # （每次呼叫仍重新攝取整支影片），卻會讓模型的時間戳座標系變得曖昧
            raw = do_call(directive, None, key_index)
        except KeyExhaustedError as e:
            key_index += 1
            if key_index >= keys:
                if not transcript:
                    raise ValueError(f"DeepSRT：Gemini 金鑰額度耗盡或無效（{e}）")
                print(f"[deepsrt] 所有金鑰額度耗盡，以現有內容繼續（可能不完整）：{e}", flush=True)
                break
            print(f"[deepsrt] 金鑰額度耗盡，換第 {key_index + 1} 把金鑰接續補跑：{e}", flush=True)
            continue  # 換金鑰只對缺的時間範圍補跑，不算補跑次數
        except Exception as e:  # noqa: BLE001
            errors += 1
            if not transcript or errors >= MAX_ERRORS:
                raise
            print(f"[deepsrt] 補跑失敗，以現有內容繼續（可能不完整）：{e}", flush=True)
            break

        parsed = parse_response(raw)
        if not parsed.has_marker:
            strict_retries += 1
            # strict 為真代表這次已經是「加強語氣」的重試了，還不聽話就放棄
            if strict or strict_retries > MAX_STRICT_RETRIES:
                if transcript:
                    print("[deepsrt] 模型持續不依格式輸出，以現有內容繼續（可能不完整）", flush=True)
                    break
                raise ValueError("DeepSRT：模型未依格式輸出（找不到 ###TRANSCRIPT### 標記）")
            strict = True
            continue
        strict = False

        good_t = sanitize(parsed.transcript, start_sec, duration, "逐字稿：")
        good_v = sanitize(parsed.visuals, start_sec, duration, "畫面筆記：")
        added = _extend(transcript, good_t, start_sec)
        _extend(visuals, good_v, start_sec)

        if parsed.complete:
            complete = True
            break
        if not transcript:
            raise ValueError("DeepSRT：模型沒有輸出任何逐字稿內容。")
        resumes += 1
        if resumes > MAX_RESUMES:
            print("[deepsrt] 補跑 2 次仍未見 ###END###，以現有內容繼續（內容不完整）", flush=True)
            break
        if not added:
            print("[deepsrt] 補跑沒有拿到新內容，停止補跑（內容可能不完整）", flush=True)
            break

    if not transcript:
        raise ValueError("DeepSRT：模型沒有輸出任何逐字稿內容。")

    spoken = transcript
    if reference_transcript:
        ref = _parse_reference(reference_transcript)
        if ref:
            spoken = ref
            print(f"[deepsrt] 口說改用官方字幕的 {len(ref)} 行（時間軸以字幕為準），"
                  f"Gemini 的 {len(transcript)} 行只用於判斷補跑", flush=True)

    text = merge(spoken, visuals)
    is_chinese = _is_chinese(spoken)
    print(f"[deepsrt] 完成：逐字稿 {len(spoken)} 行、畫面筆記 {len(visuals)} 行、"
          f"{'完整' if complete else '不完整'}", flush=True)
    if use_cache and complete:
        cache.put(cache_key, text, is_chinese)
    return text, is_chinese
