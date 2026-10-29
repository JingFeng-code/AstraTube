"""輸出語言的後處理。

目前只有一種後處理：簡體→繁體正規化。
中國廠商的免費模型（deepseek、longcat、mimo…）常無視 prompt 的「繁體中文」要求吐出簡體，
而且這種輸出完全合法、不會報錯——只能在程式端無條件正規化，不能指望模型自律。

其他輸出語言（英文、日文…）不需要也不應該套這層轉換，因此以 language 參數把關。
"""
from typing import Optional

_converter = None  # None=未初始化, False=不可用（缺套件時原樣放行）

# 只有輸出繁體中文時才做簡繁轉換
_TRADITIONAL = "zh-Hant"


def to_traditional(text: Optional[str], language: Optional[str] = _TRADITIONAL) -> Optional[str]:
    """簡體→繁體（台灣用詞，如「内存」→「記憶體」）。

    language 不是繁體中文時原樣回傳——對英文或日文輸出做簡繁轉換只會弄壞內容。
    """
    global _converter
    if not text:
        return text
    if (language or _TRADITIONAL) != _TRADITIONAL:
        return text
    if _converter is None:
        try:
            import opencc
            _converter = opencc.OpenCC("s2twp")
        except Exception as e:  # noqa: BLE001
            print(f"[zh] 簡繁轉換不可用，輸出原樣放行：{e}", flush=True)
            _converter = False
    if _converter is False:
        return text
    try:
        return _converter.convert(text)
    except Exception:  # noqa: BLE001
        return text
