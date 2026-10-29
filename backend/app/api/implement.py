"""實作：把整支影片交給本機的 coding agent CLI，產出可以直接用的檔案。

三層降級，任何一層都要是「使用者拿得到東西」的狀態：
  1. 有 CLI ＋ 開啟自動執行 → 直接跑，檔案產在產出資料夾
  2. 有 CLI ＋ 關閉自動執行 → 產出任務書並給一行指令，使用者自己貼進終端機
  3. 沒有 CLI            → 用便宜模型產一份安裝教學（這條路徑本身也要有用，
                            不能只丟一句「請先安裝」讓人卡在這裡）
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.agents import cli as agent_cli
from app.core import config, messages
from app.core.zh import to_traditional
from app.llm import router as llm_router
from app.models.schemas import ImplementRequest, RevealRequest
from app.llm import gemini
from app.prompts.implement import (FILE_BEGIN, FILE_END, TRACKS, resolve_track,
                                   task_markdown, teach_prompt, teach_system)

router = APIRouter(tags=["implement"])

# 卡片裡出現這些東西，就當作是「要寫程式的教學」，預設走 build 而不是 sop。
# 只是預設值——使用者可以在 UI 直接改，所以寧可寬鬆也不要漏判。
_CODE_SIGNALS = re.compile(
    r"```|`[^`]+`|\b(npm|npx|pnpm|yarn|pip|pip3|brew|apt|git|docker|curl|sudo|cd|mkdir)\s"
    r"|\b(function|const|let|var|def|class|import|require|return|async|await)\b"
    r"|\.(py|js|jsx|ts|tsx|json|yml|yaml|sh|env|html|css)\b"
    r"|\b(API|SDK|endpoint|localhost|repo|commit|terminal|終端機|指令|程式碼|原始碼)\b",
    re.I)

_SLUG_STRIP = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Gemini 回覆裡的檔案區塊
_FILE_RE = re.compile(re.escape(FILE_BEGIN) + r"\s*([^\n>]+?)\s*>>>\n(.*?)"
                      + re.escape(FILE_END), re.S)
# 只允許安全檔名落地（模型可能吐出 ../ 或絕對路徑）
_SAFE_NAME = re.compile(r"^[\w.\- ()（）]{1,80}$")

# 一份教學 HTML 約 15-20k tokens；給 32k 留餘裕（模型硬上限 65536）
_GEMINI_MAX_OUT = 32768

# CLI 輸出行 → 目前在做什麼。進度條不假造百分比，只報「現在這一步是什麼」＋
# 「已經產出幾個檔案」，這兩個都是可驗證的事實。
_PHASE_SIGNALS = (
    ("verify", re.compile(r"web[_ ]search|web\.run|搜尋|browsing|fetch(ing)? url", re.I)),
    ("write", re.compile(r"apply_patch|\bwrite\b|\bedit\b|create[ds]? file|寫入|建立檔案", re.I)),
    ("run", re.compile(r"^\s*(exec|bash|shell|\$)|/bin/(ba|z)?sh", re.I)),
    ("think", re.compile(r"thinking|reasoning|planning|規劃", re.I)),
)


# CLI 自己的內部雜訊，跟使用者的任務無關。不過濾掉會把進度訊息洗版，
# 讓人以為卡住了（codex 的 models cache 每十幾秒就吐一次同樣的 ERROR）。
_NOISE = re.compile(
    r"codex_models_manager|failed to renew cache TTL|failed to load models cache"
    r"|^\s*$|^\s*\d{4}-\d{2}-\d{2}T[\d:.]+Z\s+(DEBUG|TRACE)\s", re.I)


def is_noise(text: str) -> bool:
    return bool(_NOISE.search(text))


# 挑出「值得顯示成目前動作」的行，而不是反過來猜哪些行沒價值。
# 猜路徑那條路試過：/bin/zsh -lc "..." 和 /usr/bin/env python3 都以 / 開頭卻是動作，
# 判準會越補越長。白名單漏掉幾行只是少更新一次心跳，不會在畫面上顯示垃圾。
_MEANINGFUL = re.compile(
    r"web[_ ]search|web\.run|apply_patch|PRODUCED:"
    r"|\b(exec|bash|shell|read|write|edit|create|install|run|search|fetch)\b"
    r"|^[一-鿿].{8,}"  # 中文開頭的完整句＝agent 在說明自己在做什麼
    r"""|["']|(^|\s)-{1,2}\w""",   # 帶引號或旗標＝在執行某個指令
    re.I)


def is_meaningful(text: str) -> bool:
    """這一行適合當成「目前在做什麼」顯示給使用者看嗎？"""
    return bool(_MEANINGFUL.search(text.strip()))


def echo_filter(task: str):
    """CLI 會把整份任務書原樣回顯一遍。那些行不是「它在做什麼」，是我們自己送進去的。

    用任務書本身當排除清單，比猜 CLI 的輸出格式精準——換一個 CLI 也不會失效。
    只收長度夠的行，避免把「必須包含：」這種短句連帶排除掉正常輸出。
    """
    echoed = {ln.strip() for ln in task.splitlines() if len(ln.strip()) > 12}
    return lambda text: text.strip() not in echoed


def summarize_line(text: str) -> str:
    """把一行輸出壓成適合顯示在進度區的短句。"""
    t = re.sub(r"^\s*\d{4}-\d{2}-\d{2}T[\d:.]+Z\s+\w+\s+[\w:]+:\s*", "", text).strip()
    t = re.sub(r"\s+", " ", t)
    return t[:110]


def detect_phase(text: str) -> str:
    """從 CLI 的輸出行判斷目前階段。認不出來回空字串（前端就維持上一個階段）。"""
    for phase, pattern in _PHASE_SIGNALS:
        if pattern.search(text):
            return phase
    return ""


def parse_inline_files(raw: str) -> list[tuple[str, str]]:
    """從 Gemini 的回覆裡取出檔案。檔名不安全或內容空白的一律丟掉。"""
    out = []
    for name, body in _FILE_RE.findall(raw or ""):
        name = name.strip().strip("/")
        body = body.strip("\n")
        if not _SAFE_NAME.match(name) or ".." in name or not body.strip():
            continue
        # 模型有時仍會多包一層 markdown 程式碼框，這裡剝掉
        if body.lstrip().startswith("```"):
            lines = body.lstrip().splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            body = "\n".join(lines)
        out.append((name, body))
    return out


def _api_label(provider: str) -> str:
    """把 provider 字串變成看得懂的標籤。"""
    if provider == "gemini":
        return messages.t("implement.provider_gemini", model=gemini.MODEL_HEAVY)
    if ":" in provider:
        kind, model = provider.split(":", 1)
        return messages.t("implement.provider_label", kind=kind, model=model)
    return provider or messages.t("implement.provider_auto")


def looks_technical(cards: list[dict]) -> bool:
    """卡片內容看起來是不是在教寫程式（決定 build／sop 的預設分流）。"""
    text = " ".join(f"{c.get('heading') or ''} {c.get('summary') or ''} {c.get('visual') or ''}"
                    for c in cards)
    return len(_CODE_SIGNALS.findall(text)) >= 3


def output_root() -> Path:
    return Path(config.get("OUTPUT_DIR")).expanduser()


def _slug(title: str) -> str:
    """影片標題轉成安全的資料夾名（保留中文，砍掉檔名不合法的字元）。"""
    name = _SLUG_STRIP.sub("", (title or "").strip()).strip(". ")
    name = re.sub(r"\s+", " ", name)[:60].strip()
    return name or messages.t("implement.untitled_video")


def workdir_for(title: str, track: str) -> Path:
    """每次實作一個資料夾：日期-track-標題。同一天同一支影片重跑會沿用同一個。"""
    return output_root() / f"{time.strftime('%Y%m%d')}-{track}-{_slug(title)}"


def _produced_files(workdir: Path) -> list[dict]:
    """列出產出資料夾裡的檔案（不含任務書本身，那是輸入不是產出）。"""
    if not workdir.exists():
        return []
    out = []
    for p in sorted(workdir.rglob("*")):
        if p.is_file() and p.name != "TASK.md" and not p.name.startswith("."):
            out.append({"name": str(p.relative_to(workdir)), "path": str(p),
                        "bytes": p.stat().st_size})
    return out


@router.get("/implement/status")
def implement_status() -> dict:
    """本機有哪些 CLI、產出放哪、要不要自動執行。前端據此決定顯示什麼。"""
    found = agent_cli.detect()
    for c in found:
        # 讓 UI 顯示「這個 CLI 現在會用哪個模型」，以及可以填哪些值
        c["default_model"] = agent_cli.default_model(c["name"])
        c["models"] = agent_cli.available_models(c["name"])
        c["efforts"] = list(agent_cli.CLIS[c["name"]].get("efforts") or ())
        c["effort"] = config.get("CLI_EFFORT")
    return {
        "clis": found,
        "has_cli": bool(found),
        # Gemini 是備援：免費層拿不到 Google Search grounding，產不出查證過的連結。
        # 前端要據此顯示警語並建議改用 CLI。
        "gemini_ready": gemini.key_count() > 0,
        "gemini_model": gemini.MODEL_HEAVY,
        "auto_run": config.get("AUTO_RUN_CLI") != "0",
        "output_dir": str(output_root()),
        # 沒偵測到時，前端要能顯示「怎麼裝」——資訊由後端給，不讓模型自己回想
        "install": [{"name": n, "label": s["label"], "install": s["install"],
                     "install_alt": s["install_alt"], "docs": s["docs"],
                     "auth": agent_cli.auth(n)}
                    for n, s in agent_cli.CLIS.items()],
    }


@router.post("/implement")
def implement(req: ImplementRequest) -> StreamingResponse:
    """執行實作（NDJSON 串流）。"""
    cards = [c.model_dump() for c in req.cards]
    if not cards:
        raise HTTPException(400, messages.t("implement.no_cards"))

    language = config.get("OUTPUT_LANGUAGE")
    track = resolve_track(req.content_type, looks_technical(cards), req.track)
    if track not in TRACKS:
        track = "study"
    title = req.video_title or messages.t("implement.untitled_video")

    def line(obj: dict) -> str:
        return json.dumps(obj, ensure_ascii=False) + "\n"

    def gen() -> Iterator[str]:
        found = agent_cli.detect()
        want = (req.cli or "").lower()
        gemini_ready = gemini.key_count() > 0

        # 選執行者。三種可能：
        #   1. 本機 CLI（codex／claude）——唯一能上網查證、能多輪修正的
        #   2. 純 API provider（gemini／opencode:xxx／deepseek:xxx…）——單次生成，看得到什麼寫什麼
        #   3. 都沒有 → 走安裝教學
        cli_names = {c["name"] for c in found}
        if want and want not in cli_names:
            # 不是 CLI 名稱，就當成 provider 字串交給 llm_router 解析
            engine, label = ("api:" + want, _api_label(want))
            if want == "gemini" and not gemini_ready:
                engine, label = (None, "")
        else:
            cli = next((c for c in found if c["name"] == want), found[0] if found else None)
            engine, label = (cli["name"], cli["label"]) if cli else (None, "")

        # 沒有任何可用引擎 → 產一份安裝教學，讓使用者至少知道下一步做什麼
        if engine is None:
            yield line({"type": "no_cli"})
            specs = [{**s, "auth": agent_cli.auth(n)}
                     for n, s in agent_cli.CLIS.items()]
            try:
                text, model_used = llm_router.generate(
                    req.provider, teach_prompt(specs, language), teach_system(language))
                yield line({"type": "teach", "content": to_traditional(text, language),
                            "model": model_used})
            except Exception as e:  # noqa: BLE001
                # 連便宜模型都失敗時，至少把後端已知的安裝資訊原樣給出去
                yield line({"type": "teach", "content": _fallback_teach(), "model": "",
                            "note": str(e)[:120]})
            return

        cli_model = (req.cli_model or "").strip()
        # 沒指定就用設定值（預設 medium）；API 仍留參數給進階使用者覆寫
        effort = (req.effort or config.get("CLI_EFFORT") or "").strip()
        # 任務書隨執行者的能力改寫：純 API 上不了網，就不能叫它「去查證」
        via_gemini = engine.startswith("api:")
        api_provider = engine[4:] if via_gemini else ""
        task = task_markdown(title, req.video_url, cards, track, language,
                             can_browse=not via_gemini, inline_files=via_gemini)

        workdir = workdir_for(title, track)
        workdir.mkdir(parents=True, exist_ok=True)
        task_path = workdir / "TASK.md"
        task_path.write_text(task, encoding="utf-8")

        yield line({"type": "start", "track": track,
                    "track_label": messages.t(f"track.{track}"),
                    "cli": engine, "cli_label": label, "can_browse": not via_gemini,
                    "workdir": str(workdir), "task_path": str(task_path),
                    "cards": len(cards)})

        # ── 純 API：單次生成，檔案寫在回覆裡由這邊落檔 ────────────────
        if via_gemini:
            yield line({"type": "line",
                        "text": messages.t("implement.api_generating", label=label)})
            try:
                if api_provider == "gemini":
                    # 只有 Gemini 這條能把輸出上限開到 32k；其他 provider 走 router 的預設值，
                    # 所以截斷風險高很多（見前端的提醒）
                    raw, model_used = gemini.generate(
                        task, seg=0, model=gemini.MODEL_HEAVY,
                        max_output_tokens=_GEMINI_MAX_OUT)
                else:
                    raw, model_used = llm_router.generate(api_provider, task, "")
            except Exception as e:  # noqa: BLE001
                yield line({"type": "fatal",
                            "error": messages.t("implement.api_failed", label=label, error=e),
                            "workdir": str(workdir)})
                return
            parsed = parse_inline_files(raw)
            if not parsed:
                # 最常見的原因是被 max_output_tokens 截斷，收尾標記沒吐出來
                (workdir / "gemini-raw.txt").write_text(raw or "", encoding="utf-8")
                yield line({"type": "fatal",
                            "error": messages.t("implement.api_no_files", label=label),
                            "workdir": str(workdir)})
                return
            for name, body in parsed:
                (workdir / name).write_text(body, encoding="utf-8")
                yield line({"type": "line",
                            "text": messages.t("implement.wrote_file", name=name,
                                               chars=len(body))})
            files = _produced_files(workdir)
            yield line({"type": "files", "files": files})
            yield line({"type": "done", "code": 0, "workdir": str(workdir),
                        "produced": len(files), "model": model_used,
                        # 前端據此提醒：這份沒有經過查證
                        "unverified": True})
            return

        # ── CLI：有 CLI 但關掉自動執行 → 給指令讓使用者自己跑 ─────────
        if config.get("AUTO_RUN_CLI") == "0" or not req.auto_run:
            yield line({"type": "manual", "cli": engine,
                        "command": agent_cli.shell_hint(engine, str(task_path), cli_model, effort),
                        "workdir": str(workdir)})
            return

        # ── CLI：直接跑 ─────────────────────────────────────────
        code = None
        phase = "start"
        not_echo = echo_filter(task)
        seen_files: set[str] = set()
        last_scan = 0.0
        for event in agent_cli.run(engine, task, str(workdir), model=cli_model, effort=effort):
            if event["type"] == "line":
                text = event["text"]
                if not text.strip() or is_noise(text):
                    continue
                yield line({"type": "line", "text": text[:2000]})
                # 「還活著」的訊號：長時間停在同一階段時，使用者靠這句知道它在做什麼。
                # 純路徑不算動作，跳過它讓上一個真正的動作留在畫面上。
                if is_meaningful(text) and not_echo(text):
                    yield line({"type": "activity", "text": summarize_line(text)})
                # 階段變了才發事件，不然前端會被洗版
                found = detect_phase(text)
                if found and found != phase:
                    phase = found
                    yield line({"type": "phase", "phase": phase})
                # 檔案真的落地才算進度——這是唯一誠實的「做了多少」訊號
                now = time.time()
                if now - last_scan > 1.5:
                    last_scan = now
                    for f in _produced_files(workdir):
                        if f["name"] not in seen_files:
                            seen_files.add(f["name"])
                            yield line({"type": "file_progress", "file": f,
                                        "count": len(seen_files)})
            elif event["type"] == "error":
                yield line({"type": "fatal", "error": event["error"],
                            "command": agent_cli.shell_hint(engine, str(task_path), cli_model, effort),
                            "workdir": str(workdir)})
                return
            else:
                code = event.get("code")

        files = _produced_files(workdir)
        yield line({"type": "files", "files": files})
        yield line({"type": "done", "code": code, "workdir": str(workdir),
                    "produced": len(files)})

    return StreamingResponse(gen(), media_type="application/x-ndjson")


def _fallback_teach() -> str:
    """模型也不可用時的最低保證：把後端已知的安裝資訊直接排版輸出。"""
    lines = [messages.t("implement.teach_heading"), "",
             messages.t("implement.teach_intro"), ""]
    for name, spec in agent_cli.CLIS.items():
        lines += [f"### {spec['label']}", "",
                  "```bash", spec["install"], "```",
                  messages.t("implement.teach_or", command=spec["install_alt"]), "",
                  messages.t("implement.teach_auth", auth=agent_cli.auth(name)),
                  messages.t("implement.teach_docs", url=spec["docs"]), ""]
    lines.append(messages.t("implement.teach_outro"))
    return "\n".join(lines)


# 可以在 app 內直接開的檔案類型。二進位檔不給讀（沒意義，也避免把大檔灌進瀏覽器）
_VIEWABLE = {".html": "html", ".md": "markdown", ".txt": "text", ".py": "code",
             ".js": "code", ".jsx": "code", ".ts": "code", ".css": "code",
             ".json": "code", ".sh": "code", ".yml": "code", ".yaml": "code",
             ".toml": "code", ".env": "code"}
_MAX_VIEW_BYTES = 2_000_000


@router.get("/implement/file")
def read_output_file(path: str) -> dict:
    """讀產出資料夾裡的一個檔案，讓前端直接顯示，不必使用者自己去開。

    只允許產出目錄底下的路徑——這個端點會把檔案內容原樣吐出去，路徑檢查是唯一的閘門。
    """
    target = Path(path).expanduser().resolve()
    root = output_root().resolve()
    if root not in target.parents:
        raise HTTPException(400, messages.t("implement.outside_output_dir"))
    if not target.is_file():
        raise HTTPException(404, messages.t("implement.file_missing"))
    kind = _VIEWABLE.get(target.suffix.lower())
    if not kind:
        raise HTTPException(415, messages.t("implement.not_viewable"))
    size = target.stat().st_size
    if size > _MAX_VIEW_BYTES:
        raise HTTPException(413, messages.t("implement.file_too_big"))
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, messages.t("implement.file_read_failed", error=e))
    return {"name": target.name, "kind": kind, "bytes": size, "content": content}


@router.post("/implement/reveal")
def reveal(req: RevealRequest) -> dict:
    """在檔案總管／Finder 裡打開產出資料夾。只允許產出目錄底下的路徑。"""
    target = Path(req.path).expanduser().resolve()
    root = output_root().resolve()
    if not (target == root or root in target.parents):
        raise HTTPException(400, messages.t("implement.reveal_outside"))
    if not target.exists():
        raise HTTPException(404, messages.t("implement.folder_missing"))
    opener = {"darwin": ["open"], "win32": ["explorer"]}.get(sys.platform, ["xdg-open"])
    try:
        subprocess.Popen([*opener, str(target)])
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, messages.t("implement.reveal_failed", error=e))
    return {"opened": str(target)}
