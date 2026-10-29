"""文字生成供應商的共同介面與例外型別。"""
from typing import Protocol, Tuple


class ProviderError(Exception):
    """供應商呼叫失敗（可重試／可跨供應商備援）。"""


class NotConfiguredError(RuntimeError):
    """必要金鑰未設定（致命，重試無用，前端應提示使用者去設定）。"""


class RefusalError(RuntimeError):
    """模型的安全分類器婉拒了這個請求（HTTP 200 但 stop_reason=refusal）。

    這是內容層面的判定，不是傳輸錯誤——重試同一份 prompt 必然得到同樣結果，
    因此與 NotConfiguredError 同屬「致命、應直接回報使用者」那一類。
    """


class KeyExhaustedError(ProviderError):
    """這把金鑰用不了（額度耗盡或無效）——呼叫端應換下一把繼續，而非重頭來過。"""


class EmptyResponseError(ProviderError):
    """模型回了 200 但內容是空的（reasoning 模型常見）——屬暫時性，值得重試。"""


class LLMProvider(Protocol):
    """文字生成供應商：回傳 (生成文字, 模型標籤)。"""

    def generate(self, prompt: str, system: str = "", seg: int = 0) -> Tuple[str, str]:
        ...
