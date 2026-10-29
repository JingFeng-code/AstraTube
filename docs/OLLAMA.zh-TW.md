# AstraTube 本地 Ollama 整合（開發者模式）

這個功能讓你用**自己電腦的模型**處理影片摘要、知識卡、深入解析與影片問答。一般使用者模式仍保持簡單介面、使用預設免費模型。Ollama 需要另外安裝及下載模型，不會在開啟 AstraTube 時自動安裝。

## 本機 Windows 使用方式

1. 先安裝並啟動 [Ollama](https://ollama.com/)；在 PowerShell 執行 `ollama list` 查看現有模型。
2. 若尚未有模型，可自行選擇適合顯示卡及記憶體的文字模型，用 `ollama pull <model>` 安裝（替換 `<model>` 為實際模型名稱）。
3. 在同一台電腦啟動 AstraTube 的 FastAPI／React（可使用現有 `scripts/start.ps1`）。
4. 開啟 **設定 → 開發者模式 → Ollama 本地 AI**；服務網址預設 `http://127.0.0.1:11434`。模型名稱選填：留空會選第一個已安裝模型。
5. 儲存設定、重新打開設定，按「測試已儲存的 Ollama 連線」查看已安裝模型清單。
6. 回到分析介面的 **模型下拉選單**，選擇 `ollama:<model>` 進行影片分析；**問答視窗有自己的模型選單**，若也希望問答走本地模型，請另外在問答面板選擇 Ollama。

## 安全與費用

- 本切片只允許 Ollama API 的 `http://127.0.0.1:11434` / `http://localhost:11434`（同環境 loopback）；避免把任意網址交給後端存取，造成 SSRF 風險。
- **不支援雲端轉發、公開 API、任意 LAN 主機或遠端隧道**。使用 Windows + WSL 時，請在實際執行 AstraTube 後端的環境確認 `localhost:11434` 可連到 Ollama。
- 在 GitHub Codespaces，`127.0.0.1` 指的是雲端容器，不是你自己的 Windows PC。因此目前**無法直接使用你電腦的 RTX 顯卡**。
- 請安裝**真正的本地模型**；Ollama 也可能提供雲端模型。若希望完全禁用 Ollama 雲端功能，請依官方文件設定 `OLLAMA_NO_CLOUD=1` 並重啟 Ollama。使用者有責任確認模型是否為本地執行。
- 選擇 `ollama:<model>` 是嚴格指定本機模型。失敗會顯示 Ollama 連線／模型錯誤，不會自動改用任何雲端付費 Provider。使用中的模型與效能、GPU 記憶體消耗依硬體而定。
- 本地模型能接收字幕**文字**並摘要／問答；它**不會自動看懂或下載影片畫面**。「讀畫面」功能仍需另行設定既有 Gemini 能力。
- 目前**逐句雙語字幕翻譯**仍採上游免費雲端模型，尚未切到 Ollama；請不要把它當成全離線產品。
- **開發者模式是 UI 切換，不是後端身分驗證**。如果要讓一般使用者透過網際網路共用你的伺服器，必須先實作認證、授權、速率限制及 API 隔離。
- 此切片只有 mock / CI 驗證；仍須在 Windows / WSL 做 Ollama 真實 API 與影片的端到端驗收，才適合發佈桌面安裝程式。

參考： [Ollama Chat API](https://docs.ollama.com/api/chat) · [列出模型 API](https://docs.ollama.com/api/tags)
