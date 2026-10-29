"""後端介面訊息（app/core/messages.py）的不變式。

這支測試守四件事，每一件都對應一個「壞掉時外國使用者會直接看到」的失敗模式：
1. 兩種語言的 key 集合必須完全相同——只補一邊等於沒翻。
2. 英文訊息裡不得出現中日韓字元（含全形標點）——最容易漏的是「：」「（）」「、」
   這種夾在句中的全形符號，肉眼掃過去很難發現。
3. t() 絕不拋例外：key 不存在、format 參數少給，都只能降級，不能讓 API 掛掉。
4. 程式碼裡寫死的 key 都要真的存在（打錯字會在畫面上變成一串 id）。
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import config, messages  # noqa: E402
from app.core.messages import LANGUAGES, MESSAGES, t  # noqa: E402

APP_DIR = Path(__file__).resolve().parents[1] / "app"

# 中日韓字元與全形標點。　-〿 是「，。、「」（）」那一區，
# ＀-￯ 是全形英數與全形符號（＋／：），兩區都是英文句子裡的雜訊。
_CJK = re.compile(r"[　-〿぀-ヿ㐀-䶿一-鿿"
                  r"가-힯＀-￯]")

# 程式碼裡 messages.t("key") 的字面 key（f-string 動態組出來的不在此列）
_CALL = re.compile(r'messages\.t\(\s*"([^"]+)"')


def _with_language(lang: str, fn):
    """在指定介面語言下執行 fn，結束後還原（不落檔，只動記憶體快取）。"""
    original = config._cache.get("UI_LANGUAGE")
    try:
        config._cache["UI_LANGUAGE"] = lang
        return fn()
    finally:
        if original is None:
            config._cache.pop("UI_LANGUAGE", None)
        else:
            config._cache["UI_LANGUAGE"] = original


def test_every_key_has_every_language():
    """不變式：兩種語言的 key 集合完全相同，且沒有空字串。"""
    assert MESSAGES, "訊息表是空的"
    per_lang = {lang: {k for k, v in MESSAGES.items() if v.get(lang)} for lang in LANGUAGES}
    zh, en = per_lang["zh-Hant"], per_lang["en"]
    assert zh == en, (f"兩邊 key 不一致：只有中文 {sorted(zh - en)}；只有英文 {sorted(en - zh)}")
    assert zh == set(MESSAGES), f"有 key 兩邊都空：{sorted(set(MESSAGES) - zh)}"
    for key, entry in MESSAGES.items():
        extra = set(entry) - set(LANGUAGES)
        assert not extra, f"{key} 有不認得的語言：{sorted(extra)}"
    print(f"✅ 語言完整性：{len(MESSAGES)} 個 key × {len(LANGUAGES)} 種語言，無缺漏")


def test_english_has_no_cjk_characters():
    """最容易漏的一項：英文句子裡混進中文字或全形標點（：（）、＋）。"""
    bad = []
    for key, entry in MESSAGES.items():
        hits = _CJK.findall(entry["en"])
        if hits:
            bad.append(f"{key}: {''.join(sorted(set(hits)))} ← {entry['en'][:60]}")
    assert not bad, "英文訊息含中日韓字元／全形標點：\n" + "\n".join(bad)
    print("✅ 英文純淨度：所有英文訊息都不含中日韓字元與全形標點")


def test_language_switch_actually_changes_output():
    """切 UI_LANGUAGE 後 t() 要真的回不同語言（而不是永遠回退中文）。"""
    key = "notes.vault_missing"
    zh = _with_language("zh-Hant", lambda: t(key))
    en = _with_language("en", lambda: t(key))
    assert zh == MESSAGES[key]["zh-Hant"], zh
    assert en == MESSAGES[key]["en"], en
    assert zh != en, "中英文回同一句，代表語言切換沒生效"
    # 認不得的語言碼一律回退 zh-Hant，不是回 key 也不是報錯
    assert _with_language("fr", lambda: t(key)) == MESSAGES[key]["zh-Hant"]
    assert _with_language("", lambda: t(key)) == MESSAGES[key]["zh-Hant"]
    print(f"✅ 語言切換：zh-Hant「{zh}」／en「{en}」，未知語言碼回退中文")


def test_t_never_raises():
    """訊息機制自己壞掉時，只能降級，不能把 API 一起拖下水。"""
    assert t("nope.not.a.key") == "nope.not.a.key"      # 找不到就回 key 本身
    assert t("") == ""
    assert t("nope", error="x") == "nope"
    # format 參數少給／多給都不該炸，最壞情況是回未代入的原句
    assert t("ask.failed") == MESSAGES["ask.failed"][messages.language()]
    assert t("ask.failed", wrong_name="x") == MESSAGES["ask.failed"][messages.language()]
    assert t("summarize.untitled", unused=1)            # 不需要參數的訊息多給也沒事
    print("✅ 容錯：未知 key／空 key／參數對不上，t() 都回退而不拋例外")


def test_formatting_substitutes_variables():
    """帶變數的訊息要真的代進去（兩種語言都要，翻譯時漏掉 {} 就會漏資訊）。"""
    zh = _with_language("zh-Hant", lambda: t("cli.timeout", minutes=15))
    en = _with_language("en", lambda: t("cli.timeout", minutes=15))
    assert "15" in zh and "15" in en, (zh, en)

    err = ValueError("boom")
    for lang in LANGUAGES:
        got = _with_language(lang, lambda: t("ask.failed", error=err))
        assert "boom" in got, (lang, got)
        assert "{" not in got, f"{lang} 有未代入的欄位：{got}"

    # 帶多個欄位的訊息：每個欄位都要落地
    got = _with_language("en", lambda: t("provider.http_error", vendor="OpenCode",
                                         status=429, detail="rate limited"))
    assert "OpenCode" in got and "429" in got and "rate limited" in got, got

    # 每條有 {欄位} 的訊息，兩種語言的欄位集合必須一樣，否則某個語言會漏掉資訊
    field = re.compile(r"\{(\w+)\}")
    for key, entry in MESSAGES.items():
        fields = {lang: set(field.findall(entry[lang])) for lang in LANGUAGES}
        assert fields["zh-Hant"] == fields["en"], f"{key} 兩種語言的變數不一致：{fields}"
    print("✅ 變數代入：單／多欄位都正確，且中英文的變數集合一致")


def test_every_literal_key_in_code_exists():
    """程式碼裡寫死的 messages.t("...") key 都要存在（打錯字會在畫面上變成一串 id）。"""
    used: dict[str, str] = {}
    for path in sorted(APP_DIR.rglob("*.py")):
        for key in _CALL.findall(path.read_text(encoding="utf-8")):
            used.setdefault(key, str(path.relative_to(APP_DIR.parent)))
    missing = {k: v for k, v in used.items() if k not in MESSAGES}
    assert not missing, f"用到不存在的 key：{missing}"
    assert used, "掃不到任何 messages.t() 呼叫，掃描邏輯可能壞了"
    # track 標籤是用 f-string 動態組的，掃不到，這裡單獨顧
    from app.prompts.implement import TRACKS
    for track in TRACKS:
        assert f"track.{track}" in MESSAGES, f"track.{track} 缺標籤"
    print(f"✅ key 對得上：程式碼引用的 {len(used)} 個 key 全部存在，"
          f"{len(TRACKS)} 條 track 標籤齊全")


if __name__ == "__main__":
    test_every_key_has_every_language()
    test_english_has_no_cjk_characters()
    test_language_switch_actually_changes_output()
    test_t_never_raises()
    test_formatting_substitutes_variables()
    test_every_literal_key_in_code_exists()
    print("\n全部通過。")
