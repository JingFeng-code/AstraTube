# AstraTube

個人使用的 AI 影片學習與實作工作台。以 [YouTube Card Reader](https://github.com/chang416/youtube-card-reader) 為基底，目標是保留既有影片知識卡、影片問答、Obsidian 匯出與 Codex / Claude Code 任務產生功能，逐步加入台灣繁體中文體驗、Ollama 與同步雙語字幕。

> **專案狀態：階段 0（開源基底匯入 + Codespaces 開發設定）**。雙語逐句字幕、Ollama 專用設定、VideoToNo 整合尚未完成，請勿視為現有功能。

## 影片字幕閱讀（第一版）

YouTube 影片支援透過官方 IFrame API 對齊播放器時間的字幕閱讀；YouTube 與 Bilibili 均可搜尋公開字幕，點擊文字時間戳跳轉播放器。B 站官方站外播放器沒有同等可靠的公開讀取進度 API，目前僅支援點擊時間跳轉。

目前字幕工作區顯示的是**原文**；現在可以由使用者按鈕逐批翻譯字幕並在原文下方顯示繁中；翻譯依賴第三方免費模型且可能限流，尚未提供本地 Ollama。原本的摘要及卡片問答功能不受影響。詳情見 [開發路線](docs/ROADMAP.md)。

參閱 [繁中雙語字幕與快取說明](docs/BILINGUAL_SUBTITLES.zh-TW.md)。

## Bilibili 公開字幕分析（MVP）

輸入 B 站完整影片網址，例如 `https://www.bilibili.com/video/BV1B7411m7LV/`，若要指定分 P，可使用 `?p=2`。目前只分析可匿名取得的字幕；其餘經由已有的知識卡、繁體中文摘要、問答與 Markdown 功能處理。

B 站影片使用官方嵌入播放器，可透過知識卡跳至時間戳；部分影片可能禁止站外播放。無公開字幕、需要登入才能讀取字幕的影片會顯示原因，不嘗試繞過權限或下載影音。B 站深視覺分析、短網址與一次批次分析所有分 P 尚不支援。完整端到端驗收仍待在 Codespaces 操作。

## 一般使用者與開發者模式

AstraTube 現在預設使用**一般使用者模式**：不需要先設定 API 金鑰，可用公開字幕影片產生知識卡、進行 AI 問答，並將摘錄下載成 Markdown。可用性仍依賴免費模型服務與平台字幕權限。

在「設定」內切換**開發者模式**，即可顯示模型選擇、深視覺、API 金鑰、Obsidian 與 Codex／Claude Code 進階選項。切換僅改變本機介面顯示，並非後端權限控制。完整說明：[使用者模式指南](docs/USER_MODES.zh-TW.md)。

## 快速開始：GitHub Codespaces

1. 在 GitHub 的 **Code → Codespaces → Create codespace** 建立開發環境。
2. 開啟終端機執行：

   ```bash
   bash scripts/start.sh
   ```

3. 在 **Ports** 面板開啟 **AstraTube Web (15273)** 的轉送網址；保持 Port Visibility 為 **Private**。
4. 使用有現成字幕的影片測試知識卡與問答。外部免費模型的服務狀態與額度由提供者決定。

第一次執行會下載並安裝 Python/Node 套件；不需要先購買 API 額度。**Codespaces 無法直接使用你個人 Windows 的 Ollama / GPU**。本地運行請參閱 [繁中開發指南](docs/DEVELOPMENT.zh-TW.md)。

## 使用中的開源技術

- **React 18 + Vite**：保留上游 UI；現階段不重寫 Vue / .NET。
- **FastAPI**：影片字幕來源、知識卡、AI 問答、實作任務、Obsidian。
- **本地 Whisper**：沿用上游程式，但轉錄可能需要獲授權的音訊來源。
- **OpenCode Zen / 自備雲端 API**：沿用上游 Provider；Ollama 為後續工作。
- **GitHub Actions**：上游內建前端建置與後端單元測試。

## 安全與費用

- Coding Agent 的自動執行預設關閉（`AUTO_RUN_CLI=0`）；影片屬於不可信內容，執行前須審查任務。
- `.env`、`settings.json` 及逐字稿快取已加入 `.gitignore`；請勿提交 API Keys 或私人影片資料。
- Codespaces 會消耗 GitHub 用量；雲端 AI 也可能另行計費。
- 使用 YouTube 官方嵌入播放器；取得字幕與影音必須符合平台條款及內容授權。

## 開發文件

- [Codespaces / Windows / WSL 開發指南](docs/DEVELOPMENT.zh-TW.md)
- [分階段開發路線](docs/ROADMAP.md)
- [上游原始 README](docs/UPSTREAM_README.md)
- [第三方授權與來源](THIRD_PARTY_NOTICES.md)

## 開源來源與授權

原始碼來自 [chang416/youtube-card-reader](https://github.com/chang416/youtube-card-reader)，匯入時上游版本：[`7196505e9176`](https://github.com/chang416/youtube-card-reader/commit/7196505e91765059ba9fcda7c859de89d5a5ce04)。這是獨立 Repository 的程式碼匯入，**不是 GitHub Fork，也沒有直接保留上游 Git Commit 歷史**。本專案保留上游 MIT 授權及版權聲明；詳見 [LICENSE](LICENSE) 與 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
