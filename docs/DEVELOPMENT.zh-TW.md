# AstraTube 開發指南（繁體中文）

## GitHub Codespaces

1. 建立 Codespace（專案包含 `.devcontainer/devcontainer.json`，提供 Python 3.11 與 Node.js 20）。
2. 終端機執行 `bash scripts/start.sh`，第一次安裝依賴會花一些時間。
3. 開啟 Ports 面板中的 15273，確認 **Port Visibility = Private**；不要將 8420 公開轉送。
4. 先測試首頁、字幕可用影片的摘要和問答。

設計：瀏覽器 → `/api/*`（Vite Proxy）→ `127.0.0.1:8420/*`（FastAPI）；避免外部 Codespace 轉送網址上的前端誤連使用者本機 127.0.0.1。正式部署需自行設定反向代理或 `VITE_API_BASE`。

## Windows / PowerShell

需要 Python 3.10+ 和 Node.js 18+。在專案根目錄執行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```

瀏覽器網址 `http://127.0.0.1:15273`；後端預設 `http://127.0.0.1:8420`。若本機已設定 `VITE_API_BASE`，會優先使用該值。

## WSL Ubuntu

```bash
bash scripts/start.sh
```

## 安全建議

- `AUTO_RUN_CLI=0` 預設不自動呼叫 Coding Agent 執行指令；要手動確認 TASK.md。
- 不要提交 `.env`、`settings.json`、錄音、私有字幕或 API Key。
- Codespaces 不會自動存取你 Windows / WSL 上的 Ollama、RTX 4060 Ti 或私人 Obsidian Vault；須另外安排本地模式。
- 只有獲授權的影片/字幕來源才用來進行下載、轉錄與保存。

### 本機 API 來源防護

後端只接受「AstraTube 自己的介面」發出的請求，避免你瀏覽的其他網站偷偷讀取設定、改掉 Obsidian 路徑或消耗你的 API 額度：

- `Host` 必須是 `127.0.0.1`、`localhost` 或 `::1`（防 DNS rebinding）。Vite 代理會自動改成 `127.0.0.1:8420`，一般不需設定。
- 瀏覽器帶來的 `Origin` 只接受本機網址（任何埠）、桌面版 Tauri 視窗，以及**目前這個** Codespace 的轉送網址（依 `CODESPACE_NAME` 判斷）。
- 確實需要額外來源時，才用環境變數加入，以逗號分隔：`ASTRA_ALLOWED_ORIGINS=https://example.internal`、`ASTRA_ALLOWED_HOSTS=my-pc.local`。這不是登入系統，**不要**因此把後端公開到網際網路。
- 若 Codespaces 畫面出現「Request origin is not allowed」，請確認後端是在該 Codespace 的終端機以 `bash scripts/start.sh` 啟動。

## 測試與除錯

```bash
cd frontend && npm ci && npm run build
```

上游已提供 `.github/workflows/ci.yml`，在 PR 上檢查前端 build 與後端單元測試。需要查看詳細結果時，開啟 GitHub Actions；本次原始碼匯入不代表已在你的 Codespace 真正啟動測試。若第一次啟動失敗，先看 `/tmp/ycr-backend.log` 與 `/tmp/ycr-frontend.log`（Linux）。
