"""實作流程：track 分流、任務書內容、CLI 環境清理、三層降級。

最重要的三條：
1. spawn CLI 的環境不能繼承 CLAUDECODE／ANTHROPIC_*／OPENAI_*（會讓子行程用錯憑證
   而誤報未登入），但 HOME／USER／LOGNAME 一個都不能少（CLI 要靠帳號名查 Keychain）
2. 沒有 CLI 時仍然要交付東西（安裝教學），不能只回一句「請先安裝」
3. 任務書一定要帶著「連結必須查證過」的規則——那是這個功能跟便宜模型的差別所在
"""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.agents.cli as agent_cli  # noqa: E402
import app.api.implement as impl  # noqa: E402
from app.core import languages  # noqa: E402
from app.models.schemas import Card, ImplementRequest  # noqa: E402
from app.prompts.implement import (FILE_BEGIN, FILE_END, TRACK_LABELS,  # noqa: E402
                                   TRACKS, design_rules, resolve_track,
                                   task_markdown)

LANG = languages.DEFAULT
CODE_CARDS = [{"heading": "安裝套件", "summary": "• 跑 `npm install express`，然後 import express 建立 server.js"}]
PLAIN_CARDS = [{"heading": "設定同步", "summary": "• 打開設定畫面，找到同步選項，勾起來就好"}]
# 一支真的在教寫程式的影片，訊號會散在很多張卡上（單張卡不足以判定，門檻刻意設在 3 個訊號）
CODE_CARDS_FULL = [
    {"heading": "初始化專案", "summary": "• 先 `npm init -y`，再 `npm install express`"},
    {"heading": "寫第一個路由", "summary": "• 在 server.js 裡 import express，宣告 const app"},
    {"heading": "跑起來", "summary": "• 終端機下 node server.js，打開 localhost:3000 確認"},
]


def test_every_track_has_a_label_and_spec():
    """不變式：track 列表、標籤、任務規格三者要對得起來。"""
    from app.prompts.implement import _TRACK_SPEC
    for track in TRACKS:
        assert track in TRACK_LABELS, f"{track} 缺標籤"
        assert track in _TRACK_SPEC, f"{track} 缺任務規格"
    assert set(TRACK_LABELS) == set(TRACKS) == set(_TRACK_SPEC)


def test_tutorial_splits_by_whether_there_is_code():
    """『不是每個人的實作都是寫程式』在資料層的落點。"""
    assert resolve_track("tutorial", True) == "build"
    assert resolve_track("tutorial", False) == "sop"
    # 非教學型一律 study
    for ctype in ("concept", "interview", "review", "news", "other", ""):
        assert resolve_track(ctype, True) == "study", ctype
    # 使用者覆寫永遠優先，亂填則忽略
    assert resolve_track("tutorial", True, "drill") == "drill"
    assert resolve_track("tutorial", True, "亂寫") == "build"


def test_code_detection():
    assert impl.looks_technical(CODE_CARDS_FULL) is True
    assert impl.looks_technical(PLAIN_CARDS) is False
    assert impl.looks_technical([]) is False
    # 操作型但非程式的影片（Obsidian 設定、剪片、報稅）不該被誤判成 build
    obsidian = [{"heading": "安裝外掛", "summary": "• 左下角齒輪 → Community plugins → Browse，搜尋外掛名稱後按 Install"},
                {"heading": "設定同步資料夾", "summary": "• 在設定裡指定 vault 位置，勾選自動同步"}]
    assert impl.looks_technical(obsidian) is False


def test_task_markdown_carries_all_cards_and_hard_rules():
    cards = [{"heading": f"重點 {i}", "summary": f"• 內容 {i}", "timestamp_seconds": i * 60}
             for i in range(1, 13)]
    task = task_markdown("測試影片", "https://youtu.be/abc", cards, "sop", LANG)
    # 實作對象是整支影片：每一張卡都要在任務書裡
    for i in range(1, 13):
        assert f"重點 {i}" in task, f"卡片 {i} 沒進任務書"
    assert "01:00" in task and "12:00" in task     # 時間戳有帶上，agent 可回頭對照
    assert "https://youtu.be/abc" in task
    # 防編造連結的規則不能掉——這是跟便宜模型的差別
    assert "實際開啟確認過存在的網址" in task
    # 設計守則要跟著任務書一起送出去，否則產出的美感全靠運氣
    assert "單檔 HTML 設計守則" in task and "禁止清單" in task
    assert "單一檔案、可離線開啟" in task
    assert "PRODUCED:" in task


def test_task_spec_differs_by_track():
    build = task_markdown("影片", "", CODE_CARDS, "build", LANG)
    sop = task_markdown("影片", "", PLAIN_CARDS, "sop", LANG)
    study = task_markdown("影片", "", PLAIN_CARDS, "study", LANG)
    drill = task_markdown("影片", "", PLAIN_CARDS, "drill", LANG)
    assert "README.md" in build and "guide.html" not in build
    # sop 是「使用者看不懂影片」的那條路線，引導細節不能少
    assert "guide.html" in sop
    for phrase in ("現在要點哪裡", "看到這個就對了", "如果卡住"):
        assert phrase in sop, f"sop 少了「{phrase}」"
    assert "術語表" in study and "每一個" in study
    assert "drill.html" in drill and "15-25 題" in drill


def test_clean_env_drops_agent_vars_but_keeps_identity():
    """我踩過的坑：少了 USER／LOGNAME，CLI 查不到 Keychain 憑證會誤報未登入。"""
    dirty = {"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "cli",
             "ANTHROPIC_BASE_URL": "http://proxy.local", "ANTHROPIC_API_KEY": "sk-x",
             "OPENAI_API_KEY": "sk-y", "OPENAI_BASE_URL": "http://proxy.local"}
    saved = {k: os.environ.get(k) for k in dirty}
    try:
        os.environ.update(dirty)
        env = agent_cli.clean_env()
        for leaked in dirty:
            assert leaked not in env, f"{leaked} 不該傳給子行程"
        for required in ("HOME", "USER", "LOGNAME"):
            assert env.get(required), f"{required} 必須帶給子行程（Keychain 要用）"
        assert env["PATH"] and "PATH" in env
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_search_path_includes_common_install_dirs():
    path = agent_cli.search_path().split(os.pathsep)
    assert str(Path("~/.local/bin").expanduser()) in path
    assert "/opt/homebrew/bin" in path
    assert len(path) == len(set(path)), "PATH 不該有重複項"


def test_shell_hint_is_runnable_shape():
    """給使用者自己貼的指令：codex 要有 workspace-write，否則它預設唯讀寫不出檔案。"""
    codex = agent_cli.shell_hint("codex", "/tmp/a b/TASK.md")
    assert '"/tmp/a b/TASK.md"' in codex        # 有空白的路徑要引號包起來
    assert "codex exec" in codex and "--sandbox workspace-write" in codex
    assert codex.rstrip().endswith("-")          # prompt 從 stdin 讀
    claude = agent_cli.shell_hint("claude", "/tmp/TASK.md")
    assert "claude -p" in claude and "acceptEdits" in claude


def test_model_flag_goes_before_the_stdin_dash():
    """codex 的 prompt 是最後那個 "-"；--model 插在它後面會被當成 prompt 內容。"""
    plain = agent_cli.command("codex")
    with_model = agent_cli.command("codex", "gpt-5.6")
    assert plain[-1] == "-" and with_model[-1] == "-"
    assert with_model[-3:-1] == ["--model", "gpt-5.6"]
    # claude 沒有 stdin 佔位符，附在最後即可
    assert agent_cli.command("claude", "opus")[-2:] == ["--model", "opus"]
    # 留空就完全不加旗標，讓 CLI 用自己的設定
    assert "--model" not in " ".join(plain)


def test_effort_defaults_to_medium_without_asking():
    """不放進 UI：這種「照著素材寫檔案」的任務不需要更深的思考，
    實測 medium 3.8 分鐘 vs xhigh 13.9 分鐘、題數與結構相同。"""
    from app.core import config
    assert config.get("CLI_EFFORT") == "medium"


def test_effort_flag_is_codex_only_and_validated():
    """強度值會進 -c 參數，所以只接受白名單內的值。"""
    plain = " ".join(agent_cli.command("codex"))
    med = " ".join(agent_cli.command("codex", "", "medium"))
    assert "model_reasoning_effort" not in plain
    assert 'model_reasoning_effort="medium"' in med
    assert med.rstrip().endswith("-"), "旗標要在 stdin 佔位符之前"
    # 不在白名單的值一律忽略，不能讓使用者送任意字串進 -c
    for bad in ("亂寫", "ultra; rm -rf /", ""):
        assert "model_reasoning_effort" not in " ".join(agent_cli.command("codex", "", bad))
    # Claude Code 沒有這個概念
    assert "model_reasoning_effort" not in " ".join(agent_cli.command("claude", "", "medium"))


def test_shell_hint_reflects_the_chosen_model():
    hint = agent_cli.shell_hint("codex", "/tmp/T.md", "gpt-5.6")
    assert "--model gpt-5.6" in hint and hint.rstrip().endswith("-")
    assert "--model" not in agent_cli.shell_hint("codex", "/tmp/T.md")


def test_available_models_never_makes_things_up():
    """模型清單只能來自 CLI 自己的檔案。讀不到就回空或別名，不准憑印象編模型代號。"""
    for name in ("codex", "claude"):
        got = agent_cli.available_models(name)
        assert isinstance(got, list)
        for m in got:
            assert set(m) == {"value", "label", "note"} and m["value"]
    assert agent_cli.available_models("不存在的cli") == []


def test_available_models_survives_a_broken_cache(tmpdir=None):
    """快取是 CLI 的內部檔，格式可能改。壞掉時要退回別名，不能讓整個端點掛掉。"""
    spec = agent_cli.CLIS["codex"]
    original = spec.get("models_cache")
    try:
        spec["models_cache"] = "/nonexistent/models_cache.json"
        assert agent_cli.available_models("codex") == []   # codex 沒有別名可退，回空
        spec["models_cache"] = __file__                     # 存在但不是合法 JSON
        assert agent_cli.available_models("codex") == []
    finally:
        spec["models_cache"] = original


def test_default_model_is_read_not_guessed():
    """UI 要顯示「現在會用哪個模型」，這個值必須讀自 CLI 的設定檔，不能用猜的。"""
    for name in ("codex", "claude"):
        got = agent_cli.default_model(name)
        assert isinstance(got, str)          # 讀不到回空字串，不能拋例外
    assert agent_cli.default_model("不存在的cli") == ""


def test_workdir_is_safe_for_weird_titles():
    root = impl.output_root()
    for title in ("正常標題", "有/斜線:冒號*星號?", "   ", "。" * 200):
        wd = impl.workdir_for(title, "build")
        assert wd.parent == root
        assert not {"/", ":", "*", "?"} & set(wd.name.replace(str(root), ""))
        assert wd.name.strip() and len(wd.name) < 120


def test_cli_noise_is_filtered_out():
    """codex 每十幾秒吐一次自己的 cache ERROR，不過濾會把進度訊息洗掉，看起來像當機。"""
    noise = [
        "2026-08-16T03:09:23.575271Z ERROR codex_models_manager::manager: failed to renew cache TTL",
        "2026-08-16T03:09:23.575271Z ERROR codex_models_manager::cache: failed to load models cache",
        "   ",
    ]
    real = [
        "web search: site:obsidian.md Community plugins",
        "官方頁面已確認目前的文件用語：建立 vault 會用 Vault name",
        "apply_patch: guide.html",
    ]
    for n in noise:
        assert impl.is_noise(n), f"應該當成雜訊：{n[:50]}"
    for r in real:
        assert not impl.is_noise(r), f"不該被濾掉：{r[:50]}"


def test_activity_line_picks_actions_not_noise_or_echo():
    """心跳只該顯示「它在做什麼」。三種東西不算：CLI 雜訊、設定行、任務書的回顯。

    樣本取自真實的 codex 輸出。用白名單挑有價值的行，而不是猜哪些沒價值——
    猜路徑那條路走過，`/bin/zsh -lc "..."` 也以 / 開頭卻是動作，判準會越補越長。
    """
    task = task_markdown("測試影片", "", PLAIN_CARDS, "drill", LANG)
    not_echo = impl.echo_filter(task)

    def shows(text):
        return (not impl.is_noise(text)) and impl.is_meaningful(text) and not_echo(text)

    for hidden in [
        "2026-08-16T03:47:22Z ERROR codex_models_manager::cache: failed to load models cache",
        "workdir: /private/tmp/claude-501/ab-medium",
        "session id: 01a008ae-7513-71d3-a3fb-1f423eb88e89",
        "--------",
        "做一份 `drill.html`：把影片內容變成可以反覆練習的題庫。",   # 任務書回顯
        "必須包含：",
    ]:
        assert not shows(hidden), f"不該顯示：{hidden[:40]}"

    for shown in [
        "web search: site:obsidian.md Community plugins",
        '/bin/zsh -lc "cat TASK.md"',
        "apply_patch: drill.html",
        "PRODUCED: drill.html",
        "官方頁面已確認目前的文件用語，接下來開始寫檔案",
    ]:
        assert shows(shown), f"應該顯示：{shown[:40]}"


def test_summarize_line_strips_log_prefix():
    got = impl.summarize_line("2026-08-16T03:09:23.575271Z INFO codex_core::x: 正在查證官方文件")
    assert got == "正在查證官方文件"
    assert len(impl.summarize_line("x" * 500)) <= 110


def test_design_rules_only_ride_along_when_there_is_html():
    """守則將近 10KB，而 agent 每輪工具呼叫都重送整份 context。
    不產網頁的 track 不該付這個成本，而且規則也不能指向一份沒附上的文件。"""
    cards = PLAIN_CARDS
    for track in ("sop", "study", "drill"):
        t = task_markdown("影片", "", cards, track, LANG)
        assert "border-radius" in t, f"{track} 應該帶設計守則"
        assert "文件末的" in t, f"{track} 的規則要指得到那份守則"
    build = task_markdown("影片", "", cards, "build", LANG)
    assert "border-radius" not in build, "build 不產網頁，不該帶守則"
    assert "文件末的" not in build, "沒附守則就不能提到它（斷掉的指標）"
    assert "PRODUCED:" in build       # 但共同鐵則的其他條還在
    assert len(build) < len(task_markdown("影片", "", cards, "sop", LANG))


def test_build_refuses_to_fake_a_project():
    """build 的前提是影片真的教你做出某個東西。做不到時要誠實說，不能把影片重講一遍。"""
    task = task_markdown("影片", "", PLAIN_CARDS, "build", LANG)
    assert "失敗條件" in task and "跑得起來嗎" in task
    assert "不適合做成可執行的專案" in task     # 給模型的原句，讓它照抄回覆
    assert "不要硬做" in task
    # 「教你怎麼用某個工具」那類要走指令包，不是空殼專案
    assert "AGENTS.md" in task and "setup.sh" in task
    assert "手動：" in task                      # 不能自動化的步驟要標出來


def test_prompt_switches_by_whether_the_engine_can_browse():
    """關鍵不變式：上不了網的執行者，prompt 必須直接禁止它輸出網址。

    叫一個沒有搜尋能力的模型「去查證」，換來的只會是看起來很像真的、但不存在的網址。
    """
    browse = task_markdown("影片", "", PLAIN_CARDS, "sop", LANG, can_browse=True)
    blind = task_markdown("影片", "", PLAIN_CARDS, "sop", LANG, can_browse=False)
    assert "實際開啟確認過存在的網址" in browse
    assert "嚴禁輸出任何網址" in blind and "搜尋關鍵字" in blind
    # track 說明裡仍寫著「去官方網站查」，盲眼版必須明講以共同鐵則為準，否則模型會照 track 說明做
    assert "做不到" in blind
    assert "嚴禁輸出任何網址" not in browse


def test_inline_file_format_only_for_single_shot_engines():
    """CLI 自己會寫檔；只有 Gemini 這種單次生成才需要把檔案包在回覆裡。"""
    cli = task_markdown("影片", "", PLAIN_CARDS, "sop", LANG, inline_files=False)
    api = task_markdown("影片", "", PLAIN_CARDS, "sop", LANG, inline_files=True)
    assert FILE_BEGIN not in cli
    assert FILE_BEGIN in api and FILE_END in api


def test_design_rules_are_loadable_and_actionable():
    rules = design_rules()
    assert len(rules.splitlines()) > 60, "設計守則讀不到或被截斷"
    assert "禁止" in rules and "border-radius" in rules


def test_parse_inline_files_rejects_unsafe_names():
    """模型會吐出 ../ 或絕對路徑；一律不落地。"""
    def block(name, body):
        return f"{FILE_BEGIN}{name}>>>\n{body}\n{FILE_END}"

    raw = "\n".join([
        block("guide.html", "<h1>ok</h1>"),
        block("../evil.sh", "rm -rf /"),
        block("/etc/passwd", "root"),
        block("empty.html", "   "),
        block("有中文 (1).html", "<p>可以</p>"),
    ])
    got = dict(impl.parse_inline_files(raw))
    assert set(got) == {"guide.html", "有中文 (1).html"}, got
    assert got["guide.html"] == "<h1>ok</h1>"


def test_parse_inline_files_strips_stray_code_fence():
    raw = f"{FILE_BEGIN}a.html>>>\n```html\n<h1>hi</h1>\n```\n{FILE_END}"
    assert impl.parse_inline_files(raw) == [("a.html", "<h1>hi</h1>")]


async def _events(response):
    items = []
    async for chunk in response.body_iterator:
        text = chunk.decode() if isinstance(chunk, bytes) else chunk
        items.extend(json.loads(line) for line in text.splitlines() if line.strip())
    return items


def test_no_cli_falls_back_to_a_real_install_guide():
    """第 3 層降級：沒有 CLI 也要交付東西，不能只說『請先安裝』。"""
    original_detect, original_generate = agent_cli.detect, impl.llm_router.generate
    try:
        impl.agent_cli.detect = lambda: []
        impl.llm_router.generate = lambda *_a, **_k: ("## 安裝步驟\n1. 先裝 Node.js", "cheap-model")
        events = asyncio.run(_events(impl.implement(
            ImplementRequest(video_title="影片", cards=[Card(heading="卡", summary="內容")]))))
        assert [e["type"] for e in events] == ["no_cli", "teach"]
        assert "安裝步驟" in events[1]["content"]
    finally:
        impl.agent_cli.detect = original_detect
        impl.llm_router.generate = original_generate


def test_no_cli_and_no_model_still_returns_something():
    """連便宜模型都掛掉時，至少把後端已知的安裝指令原樣給出去。"""
    original_detect, original_generate = agent_cli.detect, impl.llm_router.generate
    try:
        impl.agent_cli.detect = lambda: []

        def boom(*_a, **_k):
            raise RuntimeError("沒有可用的模型")
        impl.llm_router.generate = boom
        events = asyncio.run(_events(impl.implement(
            ImplementRequest(video_title="影片", cards=[Card(heading="卡", summary="內容")]))))
        teach = events[-1]
        assert teach["type"] == "teach"
        assert "npm install -g @openai/codex" in teach["content"]
        assert "npm install -g @anthropic-ai/claude-code" in teach["content"]
    finally:
        impl.agent_cli.detect = original_detect
        impl.llm_router.generate = original_generate


def test_manual_mode_writes_task_and_returns_command():
    """第 2 層降級：不自動跑時，任務書要真的寫出來，指令要指向它。"""
    original_detect = agent_cli.detect
    try:
        impl.agent_cli.detect = lambda: [
            {"name": "codex", "label": "Codex CLI", "path": "/fake/codex", "version": "0.0.0"}]
        events = asyncio.run(_events(impl.implement(ImplementRequest(
            video_title="手動模式測試", content_type="tutorial", auto_run=False,
            cards=[Card(**c) for c in CODE_CARDS_FULL]))))
        kinds = [e["type"] for e in events]
        assert kinds == ["start", "manual"]
        start, manual = events
        assert start["track"] == "build" and start["cards"] == len(CODE_CARDS_FULL)
        task_path = Path(start["task_path"])
        assert task_path.exists() and task_path.name == "TASK.md"
        assert "手動模式測試" in task_path.read_text(encoding="utf-8")
        assert str(task_path) in manual["command"]
        # 清掉測試產物，不要留在使用者的產出資料夾
        task_path.unlink()
        task_path.parent.rmdir()
    finally:
        impl.agent_cli.detect = original_detect


def test_gemini_path_writes_files_and_flags_unverified():
    """Gemini 產出要落檔，而且必須標記 unverified——那份沒有經過任何查證。"""
    original_detect, original_keys = agent_cli.detect, impl.gemini.key_count
    original_gen = impl.gemini.generate
    try:
        impl.agent_cli.detect = lambda: []
        impl.gemini.key_count = lambda: 1
        impl.gemini.generate = lambda *_a, **_k: (
            f"{FILE_BEGIN}guide.html>>>\n<h1>做出來了</h1>\n{FILE_END}\nPRODUCED: guide.html",
            "gemini-flash-latest")
        events = asyncio.run(_events(impl.implement(ImplementRequest(
            video_title="Gemini 路徑測試", cli="gemini",
            cards=[Card(heading="卡", summary="內容")]))))
        kinds = [e["type"] for e in events]
        assert kinds[0] == "start" and kinds[-1] == "done"
        start, done = events[0], events[-1]
        assert start["cli"] == "api:gemini" and start["can_browse"] is False
        assert done["unverified"] is True and done["produced"] >= 1
        produced = Path(done["workdir"]) / "guide.html"
        assert produced.exists() and "做出來了" in produced.read_text(encoding="utf-8")
        # 清掉測試產物
        for f in Path(done["workdir"]).iterdir():
            f.unlink()
        Path(done["workdir"]).rmdir()
    finally:
        impl.agent_cli.detect = original_detect
        impl.gemini.key_count = original_keys
        impl.gemini.generate = original_gen


def test_any_api_provider_can_drive_implementation():
    """opencode／deepseek 這類純 API 走的是同一條單次生成路徑，只是換 provider 字串。"""
    original_detect, original_router = agent_cli.detect, impl.llm_router.generate
    try:
        impl.agent_cli.detect = lambda: []
        seen = {}

        def fake(provider, prompt, system="", *a, **k):
            seen["provider"] = provider
            seen["has_file_format"] = FILE_BEGIN in prompt
            seen["forbids_urls"] = "嚴禁輸出任何網址" in prompt
            return (f"{FILE_BEGIN}study.html>>>\n<h1>ok</h1>\n{FILE_END}", "deepseek-v4-flash-free")

        impl.llm_router.generate = fake
        events = asyncio.run(_events(impl.implement(ImplementRequest(
            video_title="opencode 測試", cli="opencode:deepseek-v4-flash-free",
            cards=[Card(heading="卡", summary="內容")]))))
        assert seen["provider"] == "opencode:deepseek-v4-flash-free"
        assert seen["has_file_format"] and seen["forbids_urls"]
        done = events[-1]
        assert done["type"] == "done" and done["unverified"] is True
        wd = Path(done["workdir"])
        assert (wd / "study.html").exists()
        for f in wd.iterdir():
            f.unlink()
        wd.rmdir()
    finally:
        impl.agent_cli.detect = original_detect
        impl.llm_router.generate = original_router


def test_gemini_truncated_output_fails_loudly():
    """被截斷時不能默默交出空資料夾，要明講並建議改用 CLI。"""
    original_detect, original_keys = agent_cli.detect, impl.gemini.key_count
    original_gen = impl.gemini.generate
    try:
        impl.agent_cli.detect = lambda: []
        impl.gemini.key_count = lambda: 1
        impl.gemini.generate = lambda *_a, **_k: (f"{FILE_BEGIN}a.html>>>\n<h1>被截斷", "m")
        events = asyncio.run(_events(impl.implement(ImplementRequest(
            video_title="截斷測試", cli="gemini", cards=[Card(heading="卡", summary="內容")]))))
        fatal = events[-1]
        assert fatal["type"] == "fatal" and "截斷" in fatal["error"]
        assert "Codex" in fatal["error"]
        wd = Path(fatal["workdir"])
        assert (wd / "gemini-raw.txt").exists(), "原始輸出要留下來給人查"
        for f in wd.iterdir():
            f.unlink()
        wd.rmdir()
    finally:
        impl.agent_cli.detect = original_detect
        impl.gemini.key_count = original_keys
        impl.gemini.generate = original_gen


def test_reveal_rejects_paths_outside_output_dir():
    from app.models.schemas import RevealRequest
    try:
        impl.reveal(RevealRequest(path="/etc"))
        raise AssertionError("產出目錄以外的路徑應該被擋下")
    except Exception as e:  # noqa: BLE001
        assert getattr(e, "status_code", None) == 400


if __name__ == "__main__":
    test_every_track_has_a_label_and_spec()
    test_tutorial_splits_by_whether_there_is_code()
    test_code_detection()
    test_task_markdown_carries_all_cards_and_hard_rules()
    test_task_spec_differs_by_track()
    test_clean_env_drops_agent_vars_but_keeps_identity()
    test_search_path_includes_common_install_dirs()
    test_shell_hint_is_runnable_shape()
    test_model_flag_goes_before_the_stdin_dash()
    test_effort_defaults_to_medium_without_asking()
    test_effort_flag_is_codex_only_and_validated()
    test_shell_hint_reflects_the_chosen_model()
    test_available_models_never_makes_things_up()
    test_available_models_survives_a_broken_cache()
    test_default_model_is_read_not_guessed()
    test_workdir_is_safe_for_weird_titles()
    test_cli_noise_is_filtered_out()
    test_activity_line_picks_actions_not_noise_or_echo()
    test_summarize_line_strips_log_prefix()
    test_design_rules_only_ride_along_when_there_is_html()
    test_build_refuses_to_fake_a_project()
    test_prompt_switches_by_whether_the_engine_can_browse()
    test_inline_file_format_only_for_single_shot_engines()
    test_design_rules_are_loadable_and_actionable()
    test_parse_inline_files_rejects_unsafe_names()
    test_parse_inline_files_strips_stray_code_fence()
    test_gemini_path_writes_files_and_flags_unverified()
    test_any_api_provider_can_drive_implementation()
    test_gemini_truncated_output_fails_loudly()
    test_no_cli_falls_back_to_a_real_install_guide()
    test_no_cli_and_no_model_still_returns_something()
    test_manual_mode_writes_task_and_returns_command()
    test_reveal_rejects_paths_outside_output_dir()
    print("實作流程測試通過。")
