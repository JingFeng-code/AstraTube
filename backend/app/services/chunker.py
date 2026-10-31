"""把長逐字稿／長文章切成多個片段，讓每段各自摘要，最後合併成大量卡片。"""
import re

# 每個片段大約的字元數（約對應 10~15 分鐘語音）。太大易超出輸出上限、太小則 API 呼叫過多。
CHUNK_CHARS = 12000
MAX_CHUNKS = 60  # 安全上限，避免異常超長輸入造成過多呼叫
# 尾段小於這個比例就併回前一段：剛好超過門檻一點點的影片會切出幾百字元的碎尾段，
# 那一段既多打一次 API，又因為內容太少只能生出空泛的卡片
MIN_TAIL_RATIO = 0.25
_TIMESTAMP_PREFIX = re.compile(r"\[\d+\]\s*")
_SENTENCE_END = re.compile(r".+?(?:[。！？!?；;]+|$)", re.S)


def _split_oversized(unit: str, limit: int, is_youtube: bool) -> list[str]:
    """把單獨就超過上限的句子或字幕行切開，否則整段送出會超過模型額度。

    先盡量切在句尾標點（中文句號後面通常沒有空白），還是太長才按字數硬切。
    字幕行的每一段都保留開頭的 [秒數]，時間戳才不會遺失。
    """
    if len(unit) <= limit:
        return [unit]
    match = _TIMESTAMP_PREFIX.match(unit) if is_youtube else None
    prefix = match.group(0) if match else ""
    body = unit[len(prefix):]
    room = max(1, limit - len(prefix))

    pieces, cur = [], ""
    for sentence in _SENTENCE_END.findall(body):
        while len(sentence) > room:
            if cur:
                pieces.append(cur)
                cur = ""
            pieces.append(sentence[:room])
            sentence = sentence[room:]
        if len(cur) + len(sentence) > room:
            pieces.append(cur)
            cur = sentence
        else:
            cur += sentence
    if cur:
        pieces.append(cur)
    return [prefix + piece for piece in pieces]


def chunk_content(text: str, is_youtube: bool, chunk_chars: int = CHUNK_CHARS,
                  merge_overflow: bool = True):
    """回傳片段列表。短內容回傳單一片段（行為與原本相同）。
    - YouTube：以「行」(每行 [秒數] 文字) 為單位切，保持時間戳完整。
    - 文章：以句子為單位切。
    - merge_overflow=False：超過 MAX_CHUNKS 也不合併，由呼叫端決定怎麼處理。
      有額度限制的模型不能合併，否則最後一段會大到必定失敗。
    """
    text = text or ""
    if len(text) <= chunk_chars:
        return [text]

    if is_youtube:
        units = [u for u in text.split("\n") if u]
        sep = "\n"
    else:
        units = [u for u in re.split(r"(?<=[。！？!?\.])\s+", text) if u]
        sep = " "

    units = [piece for u in units for piece in _split_oversized(u, chunk_chars, is_youtube)]

    chunks, cur = [], ""
    for u in units:
        if cur and len(cur) + len(u) + len(sep) > chunk_chars:
            chunks.append(cur)
            cur = u
        else:
            cur = (cur + sep + u) if cur else u
    if cur:
        chunks.append(cur)

    # 碎尾段併回前一段（例：12169 字元原本會切成 12000 + 169）
    if len(chunks) > 1 and len(chunks[-1]) < chunk_chars * MIN_TAIL_RATIO:
        chunks[-2] = chunks[-2] + sep + chunks[-1]
        chunks.pop()

    # 超過上限時，把多餘片段合併進最後一段，確保內容不遺漏
    if merge_overflow and len(chunks) > MAX_CHUNKS:
        head = chunks[:MAX_CHUNKS - 1]
        tail = sep.join(chunks[MAX_CHUNKS - 1:])
        chunks = head + [tail]
    return chunks
