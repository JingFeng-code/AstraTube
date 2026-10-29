"""本機 coding agent CLI 的偵測與執行。

實作階段刻意只接 Codex CLI 與 Claude Code——摘要可以用便宜模型，但「產出可以直接用的
東西」需要能讀寫檔案、能上網查證的 agent。便宜模型產不出真實可點的連結，只會編。

env 是這裡最容易出事的地方：從一個本身就是 agent 的行程去 spawn agent CLI，會把
CLAUDECODE／CLAUDE_CODE_*／ANTHROPIC_*／OPENAI_* 之類的變數繼承下去，讓子行程拿錯
端點或錯憑證而回報「未登入」。所以一律自建乾淨環境，只留必要的幾個變數——其中
HOME／USER／LOGNAME 缺一不可（CLI 要靠帳號名查 Keychain 憑證）。
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Iterator

from app.core import messages

# 執行任務時的預設上限。產一份教學 HTML 通常 2-5 分鐘，複雜專案包會更久
DEFAULT_TIMEOUT = 900

# 指令均為 2026-08-16 本機實測（codex-cli 0.146.0／Claude Code 2.1.206）：
# codex exec 的 prompt 用 "-" 從 stdin 讀；exec 預設沙盒是 read-only，
# 要讓它真的把檔案寫出來一定要給 workspace-write。--full-auto／--yolo 官方已標 deprecated。
CLIS: dict[str, dict] = {
    "codex": {
        "bin": "codex",
        "label": "Codex CLI",
        "args": ["exec", "--sandbox", "workspace-write", "--skip-git-repo-check", "-"],
        "version_args": ["--version"],
        "install": "npm install -g @openai/codex",
        "install_alt": "brew install --cask codex",
        "docs": "https://github.com/openai/codex",
        "auth_key": "cli.auth_codex",
        "model_flag": "--model",
        # 思考強度：實測同一份任務書 xhigh 13.9 分鐘、medium 3.8 分鐘，題數與結構相同，
        # 差別只在解釋的細膩度。所以這是值得給使用者選的取捨，預設偏快。
        "effort_arg": ('-c', 'model_reasoning_effort="{}"'),
        "efforts": ("medium", "high", "xhigh"),
        # 使用者自己的預設寫在這裡；讀得到就顯示在 UI 上，讓人知道現在跑的是哪個模型
        "config": "~/.codex/config.toml",
        "config_re": r'^\s*model\s*=\s*["\']([^"\']+)',
        # Codex 自己會把可用模型快取在這裡（它啟動時更新）。讀得到就變成下拉選項，
        # 使用者不必知道模型代號。格式是它的內部檔，所以讀取全程包在 try 裡。
        "models_cache": "~/.codex/models_cache.json",
        "model_hints": (),
    },
    "claude": {
        "bin": "claude",
        "label": "Claude Code",
        "args": ["-p", "--permission-mode", "acceptEdits"],
        "version_args": ["--version"],
        "install": "npm install -g @anthropic-ai/claude-code",
        "install_alt": "curl -fsSL https://claude.ai/install.sh | bash",
        "docs": "https://docs.claude.com/en/docs/claude-code/overview",
        "auth_key": "cli.auth_claude",
        "model_flag": "--model",
        # Claude Code 沒有等價的思考強度旗標
        "effort_arg": None,
        "efforts": (),
        "config": "~/.claude/settings.json",
        "config_re": r'"model"\s*:\s*"([^"]+)"',
        # claude 沒有可讀的模型清單檔；用 --help 明列的三個別名
        "models_cache": "",
        "model_hints": ("opus", "sonnet", "fable"),
    },
}

# 後端可能由 GUI／launchd 啟動，那時 PATH 短到只剩 /usr/bin:/bin，
# 找不到裝在家目錄或 homebrew 底下的 CLI。這裡補上常見安裝位置。
_EXTRA_PATHS = (
    "~/.local/bin", "/opt/homebrew/bin", "/usr/local/bin",
    "~/.npm-global/bin", "~/.bun/bin", "~/.volta/bin", "~/bin",
)


def default_model(name: str) -> str:
    """讀出該 CLI 目前設定的預設模型。讀不到就回空字串（代表用它內建的預設）。

    這是給 UI 顯示用的：使用者選「Codex CLI」時，至少要看得到它現在會用哪個模型。
    """
    spec = CLIS.get(name) or {}
    path = spec.get("config")
    if not path:
        return ""
    try:
        text = Path(path).expanduser().read_text(encoding="utf-8")
        m = re.search(spec["config_re"], text, re.M)
        return m.group(1) if m else ""
    except Exception:  # noqa: BLE001
        return ""


def available_models(name: str) -> list[dict]:
    """該 CLI 可選的模型清單，供 UI 做成下拉選單（不要讓使用者自己打模型代號）。

    Codex 讀它自己的快取檔；Claude Code 沒有這種檔案，用 --help 列的別名。
    讀不到就回空 list——UI 會退回「只顯示目前預設」，功能不受影響。
    """
    spec = CLIS.get(name) or {}
    cache = spec.get("models_cache")
    if cache:
        try:
            data = json.loads(Path(cache).expanduser().read_text(encoding="utf-8"))
            out = []
            for m in data.get("models") or []:
                slug = (m or {}).get("slug")
                if not slug:
                    continue
                out.append({"value": slug,
                            "label": m.get("display_name") or slug,
                            "note": (m.get("description") or "")[:60]})
            if out:
                return out
        except Exception:  # noqa: BLE001
            pass
    return [{"value": m, "label": m, "note": ""} for m in spec.get("model_hints") or ()]


def auth(name: str) -> str:
    """該 CLI 的登入說明（依介面語言）。前端與安裝教學都直接顯示這句。"""
    spec = CLIS.get(name) or {}
    return messages.t(spec.get("auth_key", ""))


def search_path() -> str:
    """組出用來找 CLI 的 PATH（系統 PATH ＋ 常見安裝位置，去重保序）。"""
    parts = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    parts += [str(Path(p).expanduser()) for p in _EXTRA_PATHS]
    seen, out = set(), []
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return os.pathsep.join(out)


def clean_env() -> dict[str, str]:
    """給子行程的乾淨環境。

    只帶必要變數：HOME／USER／LOGNAME 是 CLI 查 Keychain 憑證要用的（少了會誤報未登入），
    LANG／TMPDIR 影響輸出編碼與暫存位置。刻意**不**繼承 CLAUDECODE／CLAUDE_CODE_*／
    ANTHROPIC_*／OPENAI_*——那些會讓子行程連到錯的端點或用錯憑證。
    """
    keep = ("HOME", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "TMPDIR")
    env = {k: v for k, v in os.environ.items() if k in keep}
    env["PATH"] = search_path()
    env.setdefault("TERM", "dumb")      # 關掉互動式 CLI 的花俏輸出，讓串流好解析
    return env


def _version(binary: str, args: list[str]) -> str:
    try:
        out = subprocess.run([binary, *args], capture_output=True, text=True,
                             timeout=10, env=clean_env())
        return (out.stdout or out.stderr).strip().splitlines()[0][:60] if out.returncode == 0 else ""
    except Exception:  # noqa: BLE001
        return ""


def detect() -> list[dict]:
    """列出本機可用的 CLI。回傳順序即偏好順序（codex 優先）。"""
    path = search_path()
    found = []
    for name, spec in CLIS.items():
        binary = shutil.which(spec["bin"], path=path)
        if not binary:
            continue
        found.append({"name": name, "label": spec["label"], "path": binary,
                      "version": _version(binary, spec["version_args"])})
    return found


def command(name: str, model: str = "", effort: str = "") -> list[str]:
    """組出該 CLI 的完整指令（prompt 從 stdin 餵）。

    model／effort 留空就用 CLI 自己的設定。旗標要放在子指令之後、stdin 的 "-" 之前，
    否則 codex 會把它們當成 prompt 的一部分讀進去。
    """
    spec = CLIS[name]
    path = search_path()
    extra: list[str] = []
    if model and spec.get("model_flag"):
        extra += [spec["model_flag"], model]
    if effort and spec.get("effort_arg") and effort in (spec.get("efforts") or ()):
        flag, tpl = spec["effort_arg"]
        extra += [flag, tpl.format(effort)]
    args = list(spec["args"])
    if extra:
        pos = len(args) - 1 if args and args[-1] == "-" else len(args)
        args[pos:pos] = extra
    return [shutil.which(spec["bin"], path=path) or spec["bin"], *args]


def shell_hint(name: str, task_path: str, model: str = "", effort: str = "") -> str:
    """給使用者自己貼進終端機的一行指令。"""
    parts = command(name, model, effort)[1:]          # 去掉絕對路徑，用指令名比較好讀
    return f'cat "{task_path}" | {CLIS[name]["bin"]} ' + " ".join(parts)


def run(name: str, task: str, workdir: str,
        on_line: Callable[[str], None] | None = None,
        timeout: int = DEFAULT_TIMEOUT, model: str = "", effort: str = "") -> Iterator[dict]:
    """在 workdir 執行 CLI，把任務從 stdin 餵進去，逐行 yield 輸出。

    事件：{"type":"line","text":...}／{"type":"done","code":int}／{"type":"error","error":...}
    stderr 併進 stdout：CLI 的進度訊息大多走 stderr，分開讀會讓進度看起來是停住的。
    """
    if name not in CLIS:
        yield {"type": "error", "error": messages.t("cli.unsupported", name=name)}
        return
    Path(workdir).mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.Popen(
            command(name, model, effort), cwd=workdir, env=clean_env(),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1)
    except FileNotFoundError:
        yield {"type": "error",
               "error": messages.t("cli.not_found", label=CLIS[name]["label"])}
        return
    except Exception as e:  # noqa: BLE001
        yield {"type": "error",
               "error": messages.t("cli.start_failed", label=CLIS[name]["label"], error=e)}
        return

    try:
        proc.stdin.write(task)
        proc.stdin.close()
        for line in proc.stdout:
            text = line.rstrip("\n")
            if on_line:
                on_line(text)
            yield {"type": "line", "text": text}
        code = proc.wait(timeout=timeout)
        yield {"type": "done", "code": code}
    except subprocess.TimeoutExpired:
        proc.kill()
        yield {"type": "error", "error": messages.t("cli.timeout", minutes=timeout // 60)}
    except BrokenPipeError:
        proc.kill()
        yield {"type": "error",
               "error": messages.t("cli.early_exit", label=CLIS[name]["label"])}
    except Exception as e:  # noqa: BLE001
        proc.kill()
        yield {"type": "error", "error": messages.t("cli.run_failed", error=e)}
