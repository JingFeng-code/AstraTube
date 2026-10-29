"""字幕繁體翻譯快取：依原文與翻譯模型識別，不保存金鑰。

只有成功且完整驗證的翻譯才寫入；壞掉或版本不相符的快取一律當作沒有。
"""
from __future__ import annotations

import hashlib
import os
import json
from pathlib import Path

CACHE_DIR = (Path(os.environ["ASTRA_DESKTOP_DATA_DIR"]) if os.environ.get("ASTRA_DESKTOP_DATA_DIR") else Path(__file__).resolve().parents[3]) / ".cache" / "subtitle_translations"
_VERSION = "zh-hant-tw-v1"


def _path(text: str, model: str) -> Path:
    token = f"{_VERSION}\0{model}\0{text}"
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def get(text: str, model: str) -> str | None:
    try:
        value = json.loads(_path(text, model).read_text(encoding="utf-8"))
        if value.get("version") != _VERSION or value.get("model") != model:
            return None
        translated = value.get("translation")
        return translated if isinstance(translated, str) and translated.strip() else None
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def put(text: str, model: str, translation: str) -> None:
    if not translation or not translation.strip():
        return
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _path(text, model)
        path.write_text(
            json.dumps({"version": _VERSION, "model": model, "translation": translation.strip()},
                       ensure_ascii=False), encoding="utf-8")
    except OSError:
        # 快取不能影響翻譯結果：無寫入權限時仍可使用這次的結果。
        pass
