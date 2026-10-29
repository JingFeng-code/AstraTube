"""settings.json 寫入中途失敗時，既有設定（含金鑰）不得被寫壞或清空。"""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core import config


def test_failed_write_keeps_previous_settings():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "settings.json"
        cache = config.all_settings()
        with patch.object(config, "_SETTINGS_PATH", path), patch.dict(config._cache, cache, clear=True):
            config.save({"GEMINI_API_KEY": "key-before", "OBSIDIAN_NOTES_FOLDER": "筆記 資料夾"})
            assert json.loads(path.read_text(encoding="utf-8"))["GEMINI_API_KEY"] == "key-before"

            with patch.object(config.os, "replace", side_effect=OSError("disk full")):
                try:
                    config.save({"GEMINI_API_KEY": "key-after"})
                    assert False, "寫入失敗必須回報給 API 層"
                except RuntimeError:
                    pass
            saved = json.loads(path.read_text(encoding="utf-8"))
            assert saved["GEMINI_API_KEY"] == "key-before"
            assert saved["OBSIDIAN_NOTES_FOLDER"] == "筆記 資料夾"
            assert [p.name for p in Path(folder).iterdir()] == ["settings.json"], "不得殘留暫存檔"


def test_unknown_fields_are_preserved():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "中文 路徑" / "settings.json"
        path.parent.mkdir()
        path.write_text(json.dumps({"CUSTOM_FIELD": "keep"}), encoding="utf-8")
        with patch.object(config, "_SETTINGS_PATH", path), \
             patch.dict(config._cache, config.all_settings(), clear=True):
            config.save({"UI_LANGUAGE": "en"})
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["CUSTOM_FIELD"] == "keep" and saved["UI_LANGUAGE"] == "en"


if __name__ == "__main__":
    test_failed_write_keeps_previous_settings()
    test_unknown_fields_are_preserved()
    print("Settings persistence tests passed")
