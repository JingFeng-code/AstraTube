# 桌面版 YouTube 播放器隔離說明

## 問題

舊版 `frontend/src/components/VideoPane.jsx` 在主視窗載入 `https://www.youtube.com/iframe_api`，桌面版 CSP 也為此允許 `script-src https://www.youtube.com https://s.ytimg.com`。

依 Tauri 2.12.5 原始碼（`src/manager/webview.rs`、`src/webview/mod.rs::on_message`）：

- `window.__TAURI_INTERNALS__` 與每次啟動產生的 invoke key **一定會注入主框架**，與 `withGlobalTauri` 無關（`withGlobalTauri` 只多加 `window.__TAURI__` 這個捷徑）。
- 這些腳本設定為 `for_main_frame_only: true`，**iframe 不會取得**。
- App 自訂指令（例如 `desktop_connection`）在沒有宣告 App ACL manifest 時，只要請求來自本機來源且 invoke key 正確就會執行。

因此 YouTube 的腳本一旦在主視窗執行，就和 React 共用同一個 JavaScript 環境，可以呼叫 `invoke('desktop_connection')` 取得本機後端的工作階段 Token，再以使用者身分呼叫所有 API（讀寫設定、Obsidian 路徑、消耗 API 額度）。Tauri 官方 CSP 文件也明確建議避免從 CDN 載入遠端腳本。

**重現證據**（`frontend/tests/e2e/desktop-player-isolation.mjs`，以 `main` 9c51bfd 建置）：替換成假的 `iframe_api` 後，該腳本在主視窗看到 IPC，且成功取得 Token（`"stolen": "TTTT…"`，`ipcCalls` 出現第二次 `desktop_connection`）。

## 新架構

```
主視窗 http://tauri.localhost（有 IPC，CSP script-src 只有 'self'）
  └─ <iframe src="http://astraplayer.localhost/player/youtube.html?v=<ID>&parent=<主視窗來源>#channel=<隨機值>">
       ├─ 自己的 CSP：只允許自身腳本與 YouTube 官方網域，frame-ancestors 只限 AstraTube
       ├─ 在這裡載入官方 YouTube IFrame Player API（沒有 IPC、讀不到主視窗）
       └─ <iframe src="https://www.youtube.com/embed/…">（YouTube 自己建立）
```

- `astraplayer` 是 Tauri 自訂協定（`desktop/src-tauri/src/player.rs`），只回應 `/player/youtube.html` 與 `/player/youtube-host.js` 兩個在編譯時嵌入的檔案，其餘路徑 404、非 GET／HEAD 回 405。
- 主視窗與播放器只透過 `postMessage` 交換三種訊息，雙方都檢查：訊息來源視窗（`event.source`）、來源網址（`event.origin`）、每支影片重新產生的 128 位元隨機頻道，以及數值範圍。
  - 主視窗 → 播放器：`seek`（秒數 0～360000、是否播放）
  - 播放器 → 主視窗：`ready`、`time`（秒數）、`error`
- 隨機頻道放在網址 fragment（`#channel=`），不會隨請求送到網路。
- 宿主頁 15 秒內沒有回報、或回報錯誤時，退回一般 YouTube 嵌入（仍可播放與跳轉，但沒有字幕高亮）。

Web／Codespaces 版沒有 Tauri IPC，同樣使用 `/player/youtube.html`，但與主頁同源；行為與舊版相同（第三方腳本原本就在同一個頁面），不是新增風險。

## 保留的功能

| 功能 | 狀態 |
|---|---|
| YouTube 播放、點擊字幕／卡片跳轉 | 保留（`seek` 訊息） |
| 字幕依播放進度高亮 | 保留（`time` 訊息，每 0.4 秒） |
| 播放器載入失敗時仍可觀看 | 保留（退回一般嵌入） |
| Bilibili 播放與時間戳跳轉 | 未修改 |
| Sidecar、Token、字幕匯入、摘要、問答、Ollama | 未修改 |

## 剩餘風險與限制

- **播放器 frame 內的 YouTube 腳本仍可讀到隨機頻道**，因此能送出假的播放時間；影響僅限字幕高亮位置錯誤，數值已限制在合法範圍，無法觸發其他動作。
- **WebView2 版本**：Tauri 在 WebView2 支援 `ICoreWebView2_22` 時才能讓 iframe 使用自訂協定（wry 0.57.1 `webview2/mod.rs`）；過舊的 WebView2 會在 15 秒後退回一般嵌入。目前 Windows 10／11 的常青版 WebView2 應已支援，**尚未實機驗證**。
- **YouTube 嵌入身分（Referer）**：YouTube 會依嵌入網頁的來源判斷是否允許播放；新的來源是 `http://astraplayer.localhost`。若 YouTube 拒絕，播放器回報錯誤後會退回一般嵌入（來源與舊版相同的 `http://tauri.localhost`）。**需實機確認。**
- 目標平台只有 Windows。macOS／Linux 的自訂協定網址（`astraplayer://localhost`）不是標準網址，`postMessage` 來源可能是 `null`，未驗證。
- `desktop_connection` 仍允許主框架任何腳本呼叫；本修正確保主框架只執行 AstraTube 自己的腳本（CSP `script-src 'self'`）。之後若加入其他第三方腳本，必須同樣放進隔離 iframe。

## 如何驗證

```bash
cd frontend && npm test && npm run build
```

```bash
cd desktop/src-tauri && cargo test
```

模擬桌面來源隔離的瀏覽器測試（需要 Playwright 與 Chromium；不連任何外部網站）：

```bash
node frontend/tests/e2e/desktop-player-isolation.mjs frontend/dist desktop/src-tauri/tauri.conf.json desktop/src-tauri/src/player.rs
```

預期輸出：主視窗 `mainThirdParty` 為 `null`、播放器 frame 的 `ipc` 為 `false` 且 `stolen` 為 `null`、`activeCue` 為「第二句」、`hostSeeks` 為 `[10]`、偽造訊息後仍為「第三句」、對照組變為「第一句」、`cspErrors` 為空。

**Windows 實機驗收**：安裝後播放一支有字幕的 YouTube 影片，確認（1）影片可播放、（2）字幕會跟著播放進度高亮、（3）點字幕會跳到該時間、（4）沒有出現「YouTube 錯誤 153」或黑畫面。
