"""DeepSRT 解析／補跑／重試／換金鑰的單元級測試（不打真 API，注入假回應）。

執行：backend 目錄下 `.venv/bin/python tests/test_deepsrt.py`（也相容 pytest）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.base import KeyExhaustedError          # noqa: E402
from app.transcript import deepsrt                  # noqa: E402

HEAD = """###TRANSCRIPT###
[00:00-00:06] 今天要講三個重點。
[00:06-00:12] 第一個是資料結構。
###VISUALS###
[00:05] 簡報：課程大綱 — 1 資料結構 2 演算法 3 實作
"""
TAIL = """###TRANSCRIPT###
[00:12-00:18] 第二個是演算法。
###VISUALS###
[00:15] 程式碼/螢幕操作：def bfs(g, s) 用 deque 走訪
###END###
"""
FULL = """###TRANSCRIPT###
[00:00-00:06] 今天要講三個重點。
[00:06-00:12] 第一個是資料結構。
[00:12-00:18] 第二個是演算法。
###VISUALS###
[00:05] 簡報：課程大綱 — 1 資料結構 2 演算法 3 實作
###END###
"""
JUNK = "抱歉，我無法轉錄這部影片。這部影片看起來是在講程式設計。"


def _recorder(responses):
    """回傳 (call, calls)：call 依序吐出 responses（可為字串或例外）。"""
    calls = []

    def call(directive, start_offset, key_index):
        calls.append({"directive": directive, "start_offset": start_offset, "key_index": key_index})
        r = responses[min(len(calls) - 1, len(responses) - 1)]
        if isinstance(r, Exception):
            raise r
        return r

    return call, calls


def test_parse_and_merge():
    """完整回應：解析出逐字稿與畫面筆記，畫面依時間插入正確位置。"""
    p = deepsrt.parse_response(FULL)
    assert p.has_marker and p.complete, p
    assert len(p.transcript) == 3 and len(p.visuals) == 1, p
    merged = deepsrt.merge(p.transcript, p.visuals)
    lines = merged.splitlines()
    assert lines[0] == "[0] 今天要講三個重點。", lines
    assert lines[1] == "【畫面 00:05】簡報：課程大綱 — 1 資料結構 2 演算法 3 實作", lines
    assert lines[2] == "[6] 第一個是資料結構。", lines
    print("✅ 分支1 解析＋合併：3 行逐字稿、1 行畫面筆記，插入位置正確")


def test_no_end_triggers_resume():
    """缺 ###END### → 觸發斷點補跑；不用 videoMetadata 裁切，起點寫在 prompt 裡。"""
    call, calls = _recorder([HEAD, TAIL])
    text, _ = deepsrt.transcribe("https://youtu.be/x", "x", call=call, key_count=1, use_cache=False)
    assert len(calls) == 2, calls
    assert all(c["start_offset"] is None for c in calls), calls   # 一律不裁切
    assert "接續補跑" in calls[1]["directive"] and "00:07" in calls[1]["directive"], calls[1]
    assert "完整影片" in calls[1]["directive"], calls[1]           # 明講座標系
    assert "[12] 第二個是演算法。" in text and "【畫面 00:15】" in text, text
    print(f"✅ 分支2 斷點補跑：呼叫 {len(calls)} 次，起點寫在 prompt（00:07）且未裁切，內容已合併")


def test_missing_marker_triggers_strict_retry():
    """缺 ###TRANSCRIPT### → 加強語氣重試一次。"""
    call, calls = _recorder([JUNK, FULL])
    text, _ = deepsrt.transcribe("https://youtu.be/x", "x", call=call, key_count=1, use_cache=False)
    assert len(calls) == 2, calls
    assert "再次強調" in calls[1]["directive"], calls[1]["directive"]
    assert "[0] 今天要講三個重點。" in text
    print("✅ 分支3 擺爛重試：第 2 次呼叫已加上加強語氣指令並成功解析")


def test_marker_missing_twice_raises():
    """加強語氣後仍不依格式 → 明確報錯（讓上層落到字幕層）。"""
    call, calls = _recorder([JUNK, JUNK])
    try:
        deepsrt.transcribe("https://youtu.be/x", "x", call=call, key_count=1, use_cache=False)
    except ValueError as e:
        assert "###TRANSCRIPT###" in str(e), e
        print(f"✅ 分支4 連兩次擺爛：呼叫 {len(calls)} 次後拋出「{e}」")
        return
    raise AssertionError("應該要拋出 ValueError")


def test_quota_switches_key_and_resumes():
    """首跑吐一半後遇 429 → 換下一把金鑰，只對缺的範圍補跑，最終合併完整。"""
    call, calls = _recorder([HEAD, KeyExhaustedError("429 RESOURCE_EXHAUSTED: quota"), TAIL])
    text, _ = deepsrt.transcribe("https://youtu.be/x", "x", call=call, key_count=2, use_cache=False)
    assert [c["key_index"] for c in calls] == [0, 0, 1], calls
    assert "00:07" in calls[2]["directive"], calls[2]
    assert "[0] 今天要講三個重點。" in text and "[12] 第二個是演算法。" in text, text
    assert "【畫面 00:05】" in text and "【畫面 00:15】" in text, text
    print(f"✅ 分支5 額度換金鑰：key_index 依序 {[c['key_index'] for c in calls]}，"
          f"補跑起點 00:07 寫在 prompt，內容完整合併")


def test_resume_cap():
    """一直看不到 ###END### → 補跑 2 次後帶著已有內容收工。"""
    r1 = "###TRANSCRIPT###\n[00:00-00:06] A\n"
    r2 = "###TRANSCRIPT###\n[00:10-00:16] B\n"
    r3 = "###TRANSCRIPT###\n[00:20-00:26] C\n"
    call, calls = _recorder([r1, r2, r3, r3])
    text, _ = deepsrt.transcribe("https://youtu.be/x", "x", call=call, key_count=1, use_cache=False)
    assert len(calls) == 3, calls
    assert text.splitlines() == ["[0] A", "[10] B", "[20] C"], text
    print(f"✅ 分支6 補跑上限：共呼叫 {len(calls)} 次（1 首跑 + 2 補跑）後停止，內容保留")


def test_drops_timestamps_beyond_duration():
    """模型幻覺出超過片長的時間戳 → 丟棄，不讓它污染逐字稿。"""
    r = ("###TRANSCRIPT###\n[00:00-00:06] 正常內容。\n"
         "[44:31-44:38] 超出片長的幻覺內容。\n###END###\n")
    call, _ = _recorder([r])
    text, _ = deepsrt.transcribe("https://youtu.be/x", "x", call=call, key_count=1,
                                 use_cache=False, duration=1587)  # 影片 26:27
    assert "[0] 正常內容。" in text, text
    assert "幻覺" not in text, text
    print("✅ 分支7 超長丟棄：44:31 超出片長 26:27 的行已被丟掉，正常行保留")


def test_fixes_double_offset():
    """補跑整批重複加了起點偏移 → 自動減回來，而不是整批丟掉。"""
    head = "###TRANSCRIPT###\n[00:00-00:06] 開頭。\n[00:06-00:12] 續。\n"   # 覆蓋到 6s → 起點 7s
    # 模型把 7s 起點又加到自己算出的絕對時間上：真實 10s/20s 變成 17s/27s… 這裡放大到超出片長
    shifted = ("###TRANSCRIPT###\n[00:37-00:43] 真正在 30 秒的內容。\n"
               "[00:47-00:53] 真正在 40 秒的內容。\n###END###\n")
    call, _ = _recorder([head, shifted])
    text, _ = deepsrt.transcribe("https://youtu.be/x", "x", call=call, key_count=1,
                                 use_cache=False, duration=45)   # 片長 45 秒
    assert "[30] 真正在 30 秒的內容。" in text, text
    assert "[40] 真正在 40 秒的內容。" in text, text
    print("✅ 分支8 重複偏移修正：37s/47s 全部超出片長 45s，整批減去起點 7s 還原成 30s/40s")


def test_reference_transcript_replaces_spoken_timeline():
    """有字幕基準時：口說行與時間軸來自字幕，畫面筆記仍來自 Gemini。

    這條測的是實測發現的漂移問題（模型的口說時間戳會單調偏移，畫面時間戳卻準），
    所以刻意讓假回應的口說時間戳全錯，確認它們不會出現在最終輸出裡。
    """
    drifted = """###TRANSCRIPT###
[01:40] 完全錯位的口說內容甲。
[02:30] 完全錯位的口說內容乙。
###VISUALS###
[00:12] 簡報：第一頁標題
###END###
"""
    reference = "[0] 真正的第一句。\n[7] 真正的第二句。\n[19] 真正的第三句。"
    call, calls = _recorder([drifted])
    text, _ = deepsrt.transcribe("u", "v", call=call, key_count=1, use_cache=False,
                                 reference_transcript=reference)
    lines = text.splitlines()

    assert "完全錯位的口說內容甲。" not in text, "模型的口說行不該出現在有字幕基準的輸出裡"
    assert "[0] 真正的第一句。" in lines and "[19] 真正的第三句。" in lines, lines
    assert "【畫面 00:12】簡報：第一頁標題" in lines, "畫面筆記應保留（它的時間戳是準的）"
    # 畫面 12s 要插在口說 7s 與 19s 之間，證明兩條來源是依時間軸合併而非前後相接
    assert lines.index("【畫面 00:12】簡報：第一頁標題") == lines.index("[19] 真正的第三句。") - 1, lines
    print("✅ 字幕基準：口說改用字幕時間軸、畫面筆記保留並依時間插入正確位置")


def test_no_reference_keeps_model_timeline():
    """沒有字幕可用時（例如關閉字幕的影片），仍完全採用模型的口說輸出。"""
    call, _ = _recorder([HEAD + "###END###\n"])
    text, _ = deepsrt.transcribe("u", "v", call=call, key_count=1, use_cache=False)
    assert "今天要講三個重點。" in text, text
    print("✅ 無字幕基準：仍採用模型自己的口說逐字稿，不會變成空的")


if __name__ == "__main__":
    for fn in (test_parse_and_merge, test_no_end_triggers_resume,
               test_missing_marker_triggers_strict_retry, test_marker_missing_twice_raises,
               test_quota_switches_key_and_resumes, test_resume_cap,
               test_drops_timestamps_beyond_duration, test_fixes_double_offset):
        fn()
    test_reference_transcript_replaces_spoken_timeline()
    test_no_reference_keeps_model_timeline()
    print("\n全部通過。")

