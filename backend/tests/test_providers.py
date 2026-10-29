"""供應商路由、輸出語言與設定表的單元測試（不打任何真 API）。

執行：backend 目錄下 `.venv/bin/python tests/test_providers.py`（也相容 pytest）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import languages                      # noqa: E402
from app.core.zh import to_traditional              # noqa: E402
from app.llm import anthropic_api, openai_compat    # noqa: E402
from app.llm import router as llm_router            # noqa: E402
from app.prompts.ask import ask_system              # noqa: E402
from app.llm import gemini  # noqa: E402
from app.prompts.summarize import (deepdive_system, summarize_prompt,  # noqa: E402
                                   summarize_system)


def test_parse_every_provider():
    """每一種 provider 字串都要解析成正確的 (種類, 模型)。"""
    cases = {
        "anthropic:claude-opus-5": ("anthropic", "claude-opus-5"),
        "openai:gpt-5.1": ("openai", "gpt-5.1"),
        "deepseek:deepseek-reasoner": ("deepseek", "deepseek-reasoner"),
        "opencode:mimo-v2.5-free": ("opencode", "mimo-v2.5-free"),
        # 對照常數而不是抄一份字串：模型換版時測試不該跟著壞，但兩邊不一致要被抓到
        "gemini": ("gemini", gemini.MODEL),
        "auto": ("auto", llm_router.DEFAULT_AUTO_MODEL),
        "": ("auto", llm_router.DEFAULT_AUTO_MODEL),
        None: ("auto", llm_router.DEFAULT_AUTO_MODEL),
    }
    for raw, expected in cases.items():
        got = llm_router.parse(raw)
        assert got == expected, f"parse({raw!r}) = {got}，預期 {expected}"

    # 前綴帶了但模型名為空 → 回該供應商的預設模型，而不是整條爛掉
    assert llm_router.parse("anthropic:") == ("anthropic", anthropic_api.DEFAULT_MODEL)
    assert llm_router.parse("openai:") == ("openai", openai_compat.OPENAI.default_model)
    # 不認得的字串一律當自動（舊設定殘留的模型 id 不該讓使用者卡住）
    assert llm_router.parse("no-such-provider:x")[0] == "auto"
    print("✅ provider 解析：5 種供應商＋auto／空值／未知字串全部正確")


def test_language_directive_in_prompts():
    """每種輸出語言都要把硬指令壓在 prompt 最前面，且三組 prompt 都吃得到。"""
    for lang in languages.LANGUAGES:
        directive = lang.directive
        s_sys = summarize_system(lang.code)
        assert s_sys.startswith(directive), f"{lang.code}: summarize_system 沒帶語言指令"
        d_sys = deepdive_system(lang.code)
        assert d_sys.startswith(directive), f"{lang.code}: deepdive_system 沒帶語言指令"
        a_sys = ask_system("[0] hello", has_search=False, language=lang.code)
        assert a_sys.startswith(directive), f"{lang.code}: ask_system 沒帶語言指令"
        prompt = summarize_prompt({"type": "youtube", "text": "[0] hi\n[30] there",
                                   "has_timestamps": True}, lang.code)
        assert prompt.startswith(directive), f"{lang.code}: summarize_prompt 沒帶語言指令"
    # 未知語言代碼要退回預設而不是丟例外
    assert languages.get("kl-Ingon").code == languages.DEFAULT
    assert languages.get(None).code == languages.DEFAULT
    print(f"✅ 輸出語言：{len(languages.LANGUAGES)} 種語言 × 4 組 prompt 都帶到硬指令，未知代碼退回預設")


def test_simplified_conversion_scoped_to_traditional():
    """簡繁轉換只能在輸出繁體中文時發生——英文/日文輸出套上去只會弄壞內容。"""
    simplified = "内存管理"
    converted = to_traditional(simplified, "zh-Hant")
    assert converted != simplified, "繁體輸出時應該做簡繁轉換（若 opencc 未安裝此測試會失敗）"
    for other in ("en", "ja", "zh-Hans"):
        assert to_traditional(simplified, other) == simplified, f"{other} 不該被簡繁轉換動到"
    print(f"✅ 簡繁轉換：zh-Hant 轉成「{converted}」，en／ja／zh-Hans 原樣放行")


def test_paid_chain_only_lists_configured(monkeypatch=None):
    """自動模式的付費備援鏈只能列出有填金鑰的供應商。"""
    from app.core import config

    original = config.all_settings()
    try:
        # 全部清空 → 沒有任何付費備援
        config._cache.update({k: "" for k in ("GEMINI_API_KEY", "DEEPSEEK_API_KEY",
                                              "OPENAI_API_KEY", "ANTHROPIC_API_KEY")})
        assert llm_router.configured_paid_chain() == [], "沒填任何金鑰時不該有付費備援"

        # 只填 Anthropic → 鏈上只有 Anthropic
        config._cache["ANTHROPIC_API_KEY"] = "sk-test-not-a-real-key"
        chain = llm_router.configured_paid_chain()
        assert chain == [("anthropic", anthropic_api.DEFAULT_MODEL)], chain

        # 再填 DeepSeek → DeepSeek 排在 Anthropic 前面（便宜的先試）
        config._cache["DEEPSEEK_API_KEY"] = "sk-test-not-a-real-key"
        kinds = [k for k, _ in llm_router.configured_paid_chain()]
        assert kinds == ["deepseek", "anthropic"], kinds
        print("✅ 付費備援鏈：只列出已填金鑰的供應商，順序 deepseek → anthropic")
    finally:
        config._cache.update(original)


if __name__ == "__main__":
    test_parse_every_provider()
    test_language_directive_in_prompts()
    test_simplified_conversion_scoped_to_traditional()
    test_paid_chain_only_lists_configured()
    print("\n全部通過。")
