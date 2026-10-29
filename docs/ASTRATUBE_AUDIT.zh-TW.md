# AstraTube 技術稽核報告

- 稽核基準：`main` 分支 commit `9c51bfd`（2026-10-29，Windows 桌面 Alpha 合併後）
- 稽核方式：逐檔閱讀程式碼、執行既有測試、以 FastAPI TestClient／curl／Playwright Chromium 重現問題，並查看 GitHub Actions 紀錄
- 修正分支：`claude/nifty-galileo-ky1e46`（PR [JingFeng-code/AstraTube#17](https://github.com/JingFeng-code/AstraTube/pull/17)）
- **限制**：本次在 Linux 雲端容器執行，沒有 Windows 真機或 VM。所有 Windows 結論只到「自動化測試通過，實機未驗收」。

## 1. 架構摘要

```
Web／Codespaces：瀏覽器 → Vite（15273，/api 同源代理）→ FastAPI（127.0.0.1:8420）
Windows 桌面   ：Tauri v2 視窗（WebView2）→ FastAPI sidecar（PyInstaller onefile，127.0.0.1 隨機埠）
                 每次啟動產生隨機 Token，所有 API 請求必須帶 X-Astra-Desktop-Token
```

| 區塊 | 位置 | 重點 |
|---|---|---|
| 前端 | `frontend/src/` | React 18 + Vite；一般／開發者模式只控制介面可見性（`utils/user-mode.js`） |
| 後端 | `backend/app/` | 字幕擷取（YouTube／Bilibili／SRT・VTT 匯入）、摘要、問答、翻譯、Obsidian、Coding Agent 任務 |
| 模型路由 | `backend/app/llm/router.py` | `auto` 會先用免費模型，失敗才用已填金鑰的付費供應商；`<kind>:<model>` 為嚴格模式，不跨供應商 |
| 桌面殼 | `desktop/src-tauri/` | 只授權 `core:default`；shell 外掛僅用於啟動 sidecar，網頁介面沒有 shell 權限 |
| 建置 | `scripts/build-desktop.ps1`、`.github/workflows/desktop-windows.yml` | PyInstaller → sidecar smoke test → React build → Tauri NSIS；上傳 7 天的私有 Artifact |

## 2. 測試基線（修正前）

| 項目 | 指令 | 結果 |
|---|---|---|
| 後端匯入 | `python -c "from app.main import app"` | ✅ |
| 後端單元測試（12 檔） | CI 列出的 `python tests/test_*.py` | 11 檔 ✅；`test_implement.py` ❌，原因是容器沒有 `USER` 環境變數（設定後通過，屬測試本身依賴環境，已修正） |
| 前端 | `npm ci && npm test && npm run build` | ✅ 11/11 測試、建置成功 |
| `npm audit` | 全部依賴 | 只有開發用套件（vite 5.4.21／esbuild、browserslist）有 moderate／high 公告；正式依賴 0 筆 |
| GitHub Actions（main 9c51bfd） | CI、Windows desktop alpha | 兩者皆 ✅（Windows run [40844617137](https://github.com/JingFeng-code/AstraTube/actions/runs/40844617137)） |
| Windows 打包／Rust／NSIS | — | 本環境無法執行；僅能看 CI 紀錄 |

## 3. 已驗證問題（依「風險 × 可能性 × 修復成本」排序）

### P0：安全／資料遺失

**P0-1　Web 模式任何網站都能操作本機 API**（✅ 已修正）

- 位置：`backend/app/main.py`（舊版 `allowed_origins = [...] if _DESKTOP else ["*"]`，且 Web 模式沒有任何存取控制）
- 重現：後端啟動後，以 `Origin: https://evil.example` 呼叫
  - `OPTIONS /settings` → 200、`access-control-allow-origin: *`（瀏覽器會放行 JSON POST）
  - `GET /settings` → 200（可讀到 Obsidian 路徑與金鑰前後 4 碼）
  - `POST /settings {"obsidian_vault_path": "/"}` → 200
  - `Host: attacker.example`（DNS rebinding）→ 200
- 影響：使用者在本機跑 AstraTube 時打開惡意網頁，對方可以：改設定、把 vault 指到 `/` 或家目錄後用 `/notes/folders` 列出整棵目錄、用 `/notes/save` 在任意資料夾寫入 `.md`、消耗使用者付費 API 額度。若使用者自行開啟 `AUTO_RUN_CLI=1`，還能把攻擊者寫的卡片送給本機 Coding Agent 執行。
- 解法：新增 `backend/app/core/access.py`
  1. Host 只接受 `127.0.0.1`／`localhost`／`::1`（或 `ASTRA_ALLOWED_HOSTS`）；
  2. 有 Origin 時只接受回環網址、Tauri 視窗、**目前這個** Codespace 的轉送網址（或 `ASTRA_ALLOWED_ORIGINS`）；
  3. 沒有 Origin 但瀏覽器標示 `Sec-Fetch-Site: cross-site` 時拒絕；
  4. CORS 改為只回應上述來源。
- 決策依據：Vite 代理會把 Host 改成 `127.0.0.1:8420`、原樣轉送頁面 Origin，所以既有本機與 Codespaces 流程不受影響；curl、健康檢查沒有 Origin，仍可使用。桌面 Token 機制保留，兩層防護疊加。
- 測試：`backend/tests/test_local_access.py`（舊程式碼會失敗）、Playwright 實測本機頁面正常、curl 經 Vite 代理帶惡意 Origin 回 403。

### P1：主要流程或可靠性問題

**P1-1　桌面 sidecar 可能殘留在背景**（✅ 已修正，待 Windows 實機確認）

- 位置：`desktop/src-tauri/src/main.rs`（只在 `RunEvent::Exit` 時 `kill()`）；`scripts/build-desktop.ps1` 使用 `--onefile`
- 風險：Tauri 當掉或被工作管理員結束時不會跑 Exit；PyInstaller onefile 在 Windows 有外層 bootloader 與內層 Python 兩個行程，`kill()` 只保證停掉外層。殘留行程會持續佔用埠、鎖住 `%APPDATA%` 檔案，重開時可能出現兩個後端。
- 解法：Tauri 把自己的 PID 傳給 sidecar（`ASTRA_DESKTOP_PARENT_PID`），`desktop_server.py` 每 2 秒檢查，父行程消失就 `os._exit(0)`；Windows 用 `OpenProcess`＋`WaitForSingleObject`（不能用 `os.kill(pid, 0)`，那會直接結束行程）。
- 測試：`test_desktop_security.py` 以真實子行程模擬；`scripts/smoke_desktop.py` 在 Windows CI 對**打包後的 exe** 驗證「啟動程式被殺後，後端埠在 20 秒內停止回應」。

**P1-2　選 Ollama／一般模式時，會默默改用 Gemini 雲端轉錄**（✅ 已修正）

- 位置：`backend/app/transcript/router.py::_youtube`
- 重現：影片無公開字幕＋設定裡有 `GEMINI_API_KEY`，即使 provider 是 `ollama:<model>` 或一般模式固定的 `opencode:deepseek-v4-flash-free`，仍會呼叫 `deepsrt.transcribe`（把影片交給 Gemini）。
- 違反原則：「選擇 Ollama 不得無聲改用付費或雲端模型」「一般模式不可意外使用開發者已設定的付費模型」。
- 解法：只有 `auto`／`gemini` 才允許字幕失敗後改用 DeepSRT；使用者主動開「深視覺」仍照常使用 Gemini（那是明確選擇）。
- 測試：`backend/tests/test_cloud_fallback.py`。

**P1-3　桌面版遇到無字幕影片時會重複啟動自己**（✅ 已修正）

- 位置：`backend/app/transcript/whisper_local.py::download_audio` 執行 `[sys.executable, "-m", "yt_dlp", ...]`
- 風險：打包後 `sys.executable` 就是 `astratube-backend.exe`，結果是再開一份後端（繼承同一組 Token／埠），埠衝突失敗後顯示看不懂的錯誤；Windows onefile 還要先解壓整包，等待很久。
- 解法：打包版（`sys.frozen`）直接回覆「桌面測試版尚未內建本機語音轉錄，請匯入 SRT／VTT」。
- 測試：`backend/tests/test_desktop_transcription.py`。

**P1-4　`settings.json` 非原子寫入，當機可能「清空」所有金鑰**（✅ 已修正）

- 位置：`backend/app/core/config.py::save`（舊版 `write_text` 直接覆寫）
- 風險：寫到一半當機或斷電，檔案會壞掉；`_read_settings_file` 讀不到就回空 dict，使用者看起來像是所有設定消失。兩個桌面實例同時存檔也會互相覆寫半個檔案。
- 解法：暫存檔 → `fsync` → `os.replace`，POSIX 權限 0600。
- 測試：`backend/tests/test_settings_persistence.py`（模擬替換失敗，舊檔完整、不殘留暫存檔；中文與空白路徑）。

### P2：效能、可維護性、UX（尚未修正，列為下一步）

| # | 問題 | 位置／證據 | 風險 | 建議 |
|---|---|---|---|---|
| P2-1 | 桌面版主視窗載入 YouTube `iframe_api` 第三方腳本，該腳本與 React 同一個執行環境，理論上可呼叫 `invoke('desktop_connection')` 取得 Token | `frontend/src/components/VideoPane.jsx:33`、`tauri.conf.json` CSP `script-src https://www.youtube.com https://s.ytimg.com` | 依賴 YouTube 供應鏈不被入侵；低可能性、高影響 | 改用純 `<iframe enablejsapi=1>` ＋ `postMessage` 讀取進度，CSP 移除外部 `script-src` |
| P2-2 | API 金鑰以明文存在 `%APPDATA%\dev.jingfeng.astratube\settings.json` | `config.py` | 其他程式或備份可讀 | 改存 Windows Credential Manager／DPAPI |
| P2-3 | 沒有單一實例限制；開兩次會有兩個後端 | `main.rs` 未使用 `tauri-plugin-single-instance` | 重複存檔、使用者困惑 | 加入 single-instance，第二次開啟改為聚焦既有視窗 |
| P2-4 | 安裝檔未簽章 | `build-desktop.ps1` | SmartScreen 警告，一般使用者會被嚇退或被教導「忽略警告」 | Beta 前取得程式碼簽章（可評估 Azure Trusted Signing）|
| P2-5 | 桌面建置不可重現：沒有 `Cargo.lock`、`npx --yes @tauri-apps/cli@2` 未鎖版本、`requirements-desktop.txt` 只用 `>=` | `desktop/src-tauri/`、`scripts/build-desktop.ps1` | 同一 commit 隔天可能產生不同安裝檔或突然失敗 | 提交 `Cargo.lock`、鎖定 Tauri CLI 版本、為桌面版產生 pip 鎖定檔 |
| P2-6 | 開發用依賴有安全公告（vite 5.4.21／esbuild dev server、browserslist） | `npm audit` | 只影響 `npm run dev`；正式建置不受影響 | 規劃升級 Vite（主版本升級需另開 PR 測試） |
| P2-7 | 桌面安裝檔的第三方授權清單不完整（Python、PyInstaller bootloader、Tauri、WebView2、Python 套件） | `THIRD_PARTY_NOTICES.md` 只列上游專案 | 公開散布前的合規缺口 | 用 `pip-licenses`、`cargo about`／`cargo-license` 產生清單並隨安裝檔附上 |
| P2-8 | 第一次啟動沒有引導步驟 | `App.jsx` 空狀態只有標語 | 非工程師不知道下一步 | 空狀態加入「貼網址 → 開始 → 點字幕跳轉 → 翻譯 → 問答 → 匯出」三步驟卡片與範例影片 |

### P3：低影響（列入 Roadmap，不在本次修改）

- 字幕／Ollama／匯入 API 的錯誤訊息寫死繁中（例如 `api/subtitles.py:74`），英文介面會看到中文錯誤；應改用 `messages.t`。
- `main.rs` 以「bind → drop → 交給 sidecar」選埠，理論上有極短的競爭空窗；可改成失敗時重試。
- `agents/cli.py::clean_env` 只保留 POSIX 變數，Windows 上若開啟自動執行可能缺 `USERPROFILE`／`APPDATA`／`SystemRoot`；桌面版已強制 `AUTO_RUN_CLI=0`，影響有限。
- `/notes/folders` 以 `os.walk` 走完整個 vault，超大 vault 會很慢。
- 開發者模式「自動」問答會優先使用已填金鑰的付費供應商（`api/ask.py`）；行為有文件但介面可再加註。
- GitHub Actions 使用標籤（`@v4`、`@stable`）而非 commit SHA；`dtolnay/rust-toolchain@stable` 每次取最新版。
- `App.jsx` 鍵盤監聽每次 render 重新註冊（功能正確，但多餘）。
- `frontend/package.json` 名稱仍為 `youtube-card-reader`。

## 4. 已檢查、未發現問題的項目

- **桌面 Token**：每次啟動以兩個 UUIDv4 產生（約 244 bits），比對使用 `secrets.compare_digest`；`/health` 與 `/settings` 都需要 Token；只監聽 `127.0.0.1`。
- **Tauri 權限**：capability 只有 `core:default`，網頁沒有 shell／檔案系統權限；sidecar 啟動不經網頁。
- **字幕匯入**：限制 1 MB、6000 句、單句 800 字、最長 100 小時；只接受 `.srt`／`.vtt`；VTT 標籤移除且前端不以 HTML 渲染；儲存檔名為 SHA-256，無路徑穿越；原子寫入。
- **Ollama**：只允許 `http://127.0.0.1|localhost|[::1]:11434`、不跟隨重新導向、`trust_env=False`（不走系統 Proxy）、拒絕 `-cloud`／`:cloud` 模型；失敗時不會自動改用其他供應商。
- **字幕翻譯**：只接受預設免費模型或明確的 `ollama:<model>`；伺服器自己取原文（不能拿 API 翻任意文字）；回傳 JSON 逐一核對 id，部分缺漏整批不寫快取；快取鍵含模型與版本。
- **跨影片切換**：`VideoPane` 以 `sourceGeneration` 丟棄舊影片的翻譯結果；問答紀錄依 `video_id` 分開；Bilibili 分 P 以 `bilibili:BV…:pN` 區分。
- **Bilibili 進度**：程式與文件都只宣稱「點擊跳轉」，沒有宣稱可讀取站外播放器進度。
- **時間精度**：匯入字幕標示 `milliseconds_original`；平台字幕標示 `seconds_estimated`，結束時間為估算並限制 12 秒內。
- **一般模式模型**：摘要、深入解析、問答都固定送出嚴格的 `opencode:deepseek-v4-flash-free`，不會進入付費備援鏈（P1-2 修正後，轉錄層也不會）。
- **路徑安全**：`/implement/file`、`/implement/reveal`、`/notes/save` 都以 `resolve()` 後的父目錄檢查限制範圍。

## 5. 不建議的做法

- **不要**把 FastAPI 當成多人公用服務公開：沒有帳號、沒有使用者隔離，字幕與設定都是單機共用。
- **不要**為了消除 SmartScreen 警告而教使用者關閉防毒或安全機制。
- **不要**在沒有 Windows 實機紀錄時把安裝檔標示為「可用」。
