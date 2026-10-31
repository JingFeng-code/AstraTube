# AstraTube

個人使用的 AI 影片學習與實作工作台。以 [YouTube Card Reader](https://github.com/chang416/youtube-card-reader) 為基底，目標是保留既有影片知識卡、影片問答、Obsidian 匯出與 Codex / Claude Code 任務產生功能，逐步加入台灣繁體中文體驗、Ollama 與同步雙語字幕。

> **專案狀態：持續開發中的 Web App**。目前已加入雙語逐句字幕、Ollama 供應商、SRT／VTT 匯入等程式功能，GitHub Actions 提供回歸測試；尚未完成真實影片的瀏覽器驗收、Windows 實機驗收或公開多人服務所需的安全控管。

## 影片字幕閱讀（第一版）

YouTube 影片支援透過官方 IFrame API 對齊播放器時間的字幕閱讀；YouTube 與 Bilibili 均可搜尋公開字幕，點擊文字時間戳跳轉播放器。B 站官方站外播放器沒有同等可靠的公開讀取進度 API，目前僅支援點擊時間跳轉。

字幕工作區支援原文與台灣繁中對照；選定本機 Ollama 或自行設定金鑰的雲端 AI 後，可逐批翻譯字幕。模型供應商、字幕翻譯、摘要及問答共用同一選擇。詳情見 [開發路線](docs/ROADMAP.md)。

參閱 [繁中雙語字幕與快取說明](docs/BILINGUAL_SUBTITLES.zh-TW.md)。

## 匯入你擁有的 SRT／VTT 字幕

先貼上 YouTube 或 Bilibili **完整官方影片網址**，再選擇「分析選項」→「匯入字幕檔」，選取你有權使用的 `.srt` 或 `.vtt` 檔案。匯入後重新按「開始」，AstraTube 就能以這份字幕製作知識卡和問答，即使該影片沒有公開字幕 API。匯入字幕會優先使用，支援移除、替換，且保留原始毫秒級起迄時間。

字幕暫時以單機工作區模式儲存在後端的 `.cache/imported_subtitles`；**尚無多使用者登入及資料隔離，不適合直接公開部署給其他人使用**。詳見 [字幕匯入指南](docs/IMPORT_SUBTITLES.zh-TW.md)。

## Bilibili 公開字幕分析（MVP）

輸入 B 站完整影片網址，例如 `https://www.bilibili.com/video/BV1B7411m7LV/`，若要指定分 P，可使用 `?p=2`。目前只分析可匿名取得的字幕；其餘經由已有的知識卡、繁體中文摘要、問答與 Markdown 功能處理。

B 站影片使用官方嵌入播放器，可透過知識卡跳至時間戳；部分影片可能禁止站外播放。沒有公開字幕或需要登入的影片可嘗試匯入自己合法持有的字幕檔，但不會繞過權限或下載影音。B 站深視覺分析、短網址與一次批次分析所有分 P 尚不支援。完整端到端驗收仍待在 Codespaces 操作。

## AI 來源設定（單一設定，不區分使用者模式）

在設定選擇「AI 供應商 → 驗證連線 → 選擇模型 → 儲存」。使用者不用一開始就面對一大串模型 ID；需要 API Key 的供應商先驗證憑證，再載入實際可見模型。已存過金鑰則可直接驗證，不須重新輸入。

智慧模式只使用可用的本地 Ollama，不會暗中改用雲端服務；可另選 Gemini、OpenAI、DeepSeek、Anthropic、OpenRouter、Groq、Mistral AI、Together AI 等自備金鑰供應商。已移除不可穩定供第三方程式呼叫的 OpenCode 免費線上選項。完整步驟見 [AI 供應商與模型設定](docs/AI_PROVIDER_SETUP.zh-TW.md)。

## Ollama（選用的本地 AI）

已安裝 Ollama 的使用者可在 AI 設定選擇「Ollama」，檢查本機服務並選擇已下載的模型。不需要 API Key；摘要、知識卡、問答與字幕翻譯共用所選模型。若本機沒有 Ollama，AstraTube 會顯示未就緒，不會自行呼叫其他雲端 API。內建 llama.cpp 模型自動下載仍尚未實作。

## Windows 免安裝版 Alpha（測試專用）

Windows 版以**免安裝資料夾**發行：解壓縮後雙擊 `AstraTube.exe` 即可，不需要安裝程式、Python 或 Node.js；設定與快取都存在程式旁的 `data` 資料夾，整個資料夾可以搬移或直接刪除。**尚未完成 Windows 實機使用驗收、數位簽章及對外發布**。請參閱 [Windows 桌面版開發／測試指南](docs/DESKTOP.zh-TW.md)。

## 快速開始：GitHub Codespaces

1. 在 GitHub 的 **Code → Codespaces → Create codespace** 建立開發環境。
2. 開啟終端機執行：

   ```bash
   bash scripts/start.sh
   ```

3. 在 **Ports** 面板開啟 **AstraTube Web (15273)** 的轉送網址；保持 Port Visibility 為 **Private**。
4. 如需知識卡與問答，請先在 AI 設定中選擇可用的供應商（本機 Ollama 或自行提供 API Key）。

第一次執行會下載並安裝 Python/Node 套件；影片字幕閱讀可不設定雲端金鑰，但使用 AI 生成功能須準備本機 Ollama 或可用的雲端 API Key。**Codespaces 無法直接使用你個人 Windows 的 Ollama / GPU**。本地運行請參閱 [繁中開發指南](docs/DEVELOPMENT.zh-TW.md)。

## 使用中的開源技術

- **React 18 + Vite**：保留上游 UI；現階段不重寫 Vue / .NET。
- **FastAPI**：影片字幕來源、知識卡、AI 問答、實作任務、Obsidian。
- **本地 Whisper**：沿用上游程式，但轉錄可能需要獲授權的音訊來源。
- **自備雲端 API / Ollama**：支援多家雲端 AI 供應商與同環境的本地 Ollama；不依賴 OpenCode 免費接力。
- **GitHub Actions**：上游內建前端建置與後端單元測試。

## 安全與費用

- Coding Agent 的自動執行預設關閉（`AUTO_RUN_CLI=0`）；影片屬於不可信內容，執行前須審查任務。
- `.env`、`settings.json` 及逐字稿快取已加入 `.gitignore`；請勿提交 API Keys 或私人影片資料。
- Codespaces 會消耗 GitHub 用量；雲端 AI 也可能另行計費。
- 使用 YouTube 官方嵌入播放器；取得字幕與影音必須符合平台條款及內容授權。

## 開發文件

- [Codespaces / Windows / WSL 開發指南](docs/DEVELOPMENT.zh-TW.md)
- [分階段開發路線](docs/ROADMAP.md)
- [技術稽核報告](docs/ASTRATUBE_AUDIT.zh-TW.md)・[Beta 發布門檻](docs/BETA_READINESS.zh-TW.md)・[Windows 實機驗收腳本](docs/MANUAL_SMOKE_TEST.zh-TW.md)・[常見錯誤訊息與處理](docs/TROUBLESHOOTING.zh-TW.md)
- [上游原始 README](docs/UPSTREAM_README.md)
- [第三方授權與來源](THIRD_PARTY_NOTICES.md)

## 開源來源與授權

原始碼來自 [chang416/youtube-card-reader](https://github.com/chang416/youtube-card-reader)，匯入時上游版本：[`7196505e9176`](https://github.com/chang416/youtube-card-reader/commit/7196505e91765059ba9fcda7c859de89d5a5ce04)。這是獨立 Repository 的程式碼匯入，**不是 GitHub Fork，也沒有直接保留上游 Git Commit 歷史**。本專案保留上游 MIT 授權及版權聲明；詳見 [LICENSE](LICENSE) 與 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
