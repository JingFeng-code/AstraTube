"""輸出語言表。

prompt 本體維持繁體中文——那組判準是實測校準過的，翻譯過去等於重新調一次品質。
語言切換改成在 prompt 最前面壓一條「輸出語言」硬指令：模型可以用 A 語言讀指令、
用 B 語言作答，這是實測穩定的作法，也讓新增語言只要多一列表格。
"""
from typing import NamedTuple


class Language(NamedTuple):
    code: str
    label: str          # 前端下拉選單顯示的名稱（用該語言自己的寫法）
    directive: str      # 壓在 prompt 最前面的硬指令
    quote_note: str     # 「原文引用」欄位的語言規則（逐字引用不該被翻譯）


DEFAULT = "zh-Hant"

_TRANSLATE_HINT = "若原文非目標語言，translation 欄位提供目標語言翻譯；原文已是目標語言則填 null。"

LANGUAGES: tuple[Language, ...] = (
    Language(
        "zh-Hant", "繁體中文",
        "【輸出語言】所有輸出一律使用**繁體中文（台灣用語）**。禁止簡體字。",
        "transcript_highlight 保留素材原文，不翻譯。" + _TRANSLATE_HINT,
    ),
    Language(
        "zh-Hans", "简体中文",
        "【输出语言】所有输出一律使用**简体中文**。",
        "transcript_highlight 保留素材原文，不翻译。" + _TRANSLATE_HINT,
    ),
    Language(
        "en", "English",
        "[OUTPUT LANGUAGE] Write every field in **English**, regardless of the language "
        "of these instructions or of the source material.",
        "Keep transcript_highlight verbatim in the source language; do not translate it. "
        "Put the English translation in the translation field (null if the source is already English).",
    ),
    Language(
        "ja", "日本語",
        "【出力言語】すべての出力を**日本語**で書いてください。",
        "transcript_highlight は原文のまま引用し、翻訳しないこと。"
        "translation 欄には日本語訳を入れる（原文が日本語なら null）。",
    ),
    Language(
        "ko", "한국어",
        "[출력 언어] 모든 출력을 **한국어**로 작성하세요.",
        "transcript_highlight 는 원문 그대로 인용하고 번역하지 마세요. "
        "translation 에 한국어 번역을 넣으세요(원문이 한국어면 null).",
    ),
    Language(
        "es", "Español",
        "[IDIOMA DE SALIDA] Escribe todos los campos en **español**.",
        "Mantén transcript_highlight textual en el idioma original; no lo traduzcas. "
        "Pon la traducción al español en el campo translation (null si ya está en español).",
    ),
)

_BY_CODE = {lang.code: lang for lang in LANGUAGES}


def get(code: str | None) -> Language:
    """取得語言設定；不認得的代碼一律回預設，避免舊設定卡住使用者。"""
    return _BY_CODE.get((code or "").strip(), _BY_CODE[DEFAULT])


def codes() -> list[dict[str, str]]:
    """給前端下拉選單用的 [{code, label}] 清單。"""
    return [{"code": lang.code, "label": lang.label} for lang in LANGUAGES]
