"""切段上限：單一句子或字幕行太長時也要切開，否則整段會超過模型額度。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import summarize as summarize_api  # noqa: E402
from app.services.chunker import MIN_TAIL_RATIO, chunk_content  # noqa: E402

LIMIT = 1800
# 碎尾段會併回前一段，所以單段最多是上限再加上一個碎尾段
MAX_WITH_TAIL = LIMIT * (1 + MIN_TAIL_RATIO) + 1


def test_chinese_article_without_spaces_is_split():
    text = "這是一段沒有空白的中文句子。" * 710
    chunks = chunk_content(text, False, chunk_chars=LIMIT, merge_overflow=False)
    assert len(chunks) > 1
    assert max(map(len, chunks)) <= MAX_WITH_TAIL
    assert "".join(chunks).replace(" ", "") == text


def test_text_without_any_punctuation_is_still_split():
    text = "字" * 5000
    chunks = chunk_content(text, False, chunk_chars=LIMIT, merge_overflow=False)
    assert len(chunks) > 1
    assert max(map(len, chunks)) <= MAX_WITH_TAIL
    assert "".join(chunks).replace(" ", "") == text


def test_oversized_caption_line_keeps_its_timestamp():
    chunks = chunk_content("[12] " + "字幕內容" * 1000, True, chunk_chars=LIMIT, merge_overflow=False)
    assert len(chunks) > 1
    assert max(map(len, chunks)) <= MAX_WITH_TAIL
    for chunk in chunks:
        assert all(line.startswith("[12] ") for line in chunk.split("\n"))


def test_normal_units_are_not_changed():
    lines = [f"[{index}] 一般長度的字幕" for index in range(400)]
    text = "\n".join(lines)
    chunks = chunk_content(text, True, chunk_chars=LIMIT)
    assert "\n".join(chunks) == text
    sentences = "第一句。 第二句。 第三句。"
    assert chunk_content(sentences, False, chunk_chars=LIMIT) == [sentences]


def test_groq_summary_splits_long_chinese_article():
    content = {"type": "article", "text": "這是一段沒有空白的中文句子。" * 710}
    chunks, skipped = summarize_api._split(content, "groq:qwen/qwen3.8-27b")
    assert skipped == 0 and len(chunks) > 1
    assert max(map(len, chunks)) < 9000


if __name__ == "__main__":
    test_chinese_article_without_spaces_is_split()
    test_text_without_any_punctuation_is_still_split()
    test_oversized_caption_line_keeps_its_timestamp()
    test_normal_units_are_not_changed()
    test_groq_summary_splits_long_chinese_article()
    print("切段上限測試通過。")
