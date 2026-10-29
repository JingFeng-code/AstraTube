# AstraTube Windows 桌面版 Alpha

這是 **Tauri v2 + React + FastAPI PyInstaller Sidecar** 的**內部測試安裝包**；不是已完成實際影片、Ollama 或跨裝置驗收的正式公開產品。原本 Web／Codespaces 版維持可使用。

## 目前的架構

- Tauri 負責 Windows 桌面視窗及後端 Sidecar 啟停，關閉程式後會停止由它啟動的 FastAPI 行程。
- React 依然使用現有的字幕、影片摘要、知識卡、Obsidian、Ollama 及 AI 問答畫面。
- FastAPI 以 PyInstaller 包裝成獨立 `astratube-backend.exe`，**安裝後一般使用者不需要自己安裝 Python/Node.js**。
- 每次啟動由 Rust 選擇回環位址上的隨機埠，產生新的高熵會話 Token；桌面 React 啟動時經 Tauri invoke 取得本次 Token，所有 API 請求都要帶 `X-Astra-Desktop-Token`。
- FastAPI 只監聽 `127.0.0.1`，不會監聽 `0.0.0.0`。遠端網頁不能因為得知埠號就無認證呼叫本機 API。
- 桌面模式的 `settings.json` 與 `.cache/` 會存在**目前 Windows 使用者的應用程式資料目錄**（由 Tauri `app_data_dir` 指定），不寫進安裝資料夾或 Git。
- Tauri 不提供任意 shell 命令權限給網頁介面。Coding Agent 自動執行仍預設關閉。

## 目前不包含什麼？

- **Whisper / yt-dlp 不會封裝到第一版 Windows Sidecar**，因為它們依賴大型的原生組件及模型；無公開字幕的影片可先使用自己合法取得的 SRT／VTT。這是有意識的 Alpha 範圍限制，不代表未來會永久取消。
- Tauri 介面目前是網頁原型的桌面外殼，不是完整新的 Windows UX。
- 對於外部免費模型、YouTube/Bilibili API、嵌入播放器的可用性，仍**不保證**所有地區／影片都能成功。
- 尚未測試 Windows 10/11 不同電腦、WebView2、GPU、Ollama/Whisper、Unicode 路徑、NSIS 安裝或解除安裝流程。
- 尚未設定程式碼簽章、自動更新、隱私與開源授權合規審查；不得用此版本宣稱已可正式公開發布。
- 使用 Tauri 的 Windows 桌面程式必須符合 WebView2 執行環境的部署需求。

## 從 GitHub 取得內部測試安裝檔

1. 打開儲存庫的 **Actions → Windows desktop alpha**。
2. 選擇一筆**成功**的工作流程執行紀錄。
3. 在頁面下方的 Artifacts 下載 `AstraTube-Windows-x64-alpha-unsigned`。這是 ZIP，裡面包含**未簽章的 NSIS 安裝程式**。
4. 只有在了解這是自己的開發版、來源可信且準備測試時才安裝。請勿透過不明網站轉載，也不要為了安裝而關閉 Windows 防毒或安全機制。
5. 安裝後先測試一支合法的公開字幕影片；再測試 SRT／VTT 匯入、免費模型、翻譯、Ollama 及關閉軟體後行程是否正常結束。測試失敗記錄影片類型、錯誤訊息與系統版本。

下載 Actions Artifacts 可能需要登入有權限的 GitHub 帳號；這不是 GitHub Release 公開下載頁。

## 開發者在 Windows 編譯

需要 Windows x64、Python 3.12、Node.js 20+、Rust stable（MSVC 工具鏈）、Microsoft C++ Build Tools、WebView2 工具鏈、網路連線。

```powershell
git checkout main
git pull origin main
./scripts/build-desktop.ps1
```

編譯腳本會安裝 PyInstaller 等開發依賴、產生測試版圖示、封裝 FastAPI、在本機以 Token 做 Sidecar 健康檢查，再編譯 React 與 NSIS 安裝程式。

**安全提醒：** 這個 Alpha 是**單機自用桌面架構**。不要直接將內部 FastAPI 暴露到網際網路；若將來提供雲端多人版，仍需要獨立的登入、資料隔離、伺服器授權及費用限制。

官方技術文件：[Tauri Sidecar](https://v2.tauri.app/develop/sidecar/) · [Tauri Windows 安裝](https://v2.tauri.app/distribute/windows-installer/)。
