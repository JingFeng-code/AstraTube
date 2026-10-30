# AstraTube AI 供應商與模型設定（Windows Portable / Web）

## 不需要先了解模型 ID

在主畫面點擊「AI 來源」進入設定，只要按照以下順序操作：

1. **選擇供應商**：智慧選擇、Ollama、OpenCode，或自備 API Key 的 Gemini／OpenAI／DeepSeek／Anthropic。
2. **驗證連線**：需要 API Key 的供應商，先填入金鑰；已儲存過金鑰可直接檢查，不必重新輸入。
3. **選擇模型**：只有連線成功後，才會顯示該供應商實際回傳的模型。
4. **儲存**：確認後才儲存新 API Key 與模型選擇。字幕翻譯、摘要及影片問答共用該來源。

**特別注意**：驗證成功代表金鑰能讀取模型清單，並不保證每個模型都有生成權限或免費額度。
實際生成失敗時，請查看供應商帳號的額度、付款資訊與模型權限。

## 不同供應商如何使用

| 供應商 | 使用條件 | 模型來源 |
| --- | --- | --- |
| 智慧選擇 | 本機已有可用 Ollama 模型 | 僅使用本機，不會默默連雲端 |
| Ollama | 同一環境啟動 Ollama 並安裝模型 | 本機 `/api/tags` |
| OpenCode | 無金鑰也可嘗試免費服務；可能限流 | 線上免費模型清單 |
| Gemini | 自備 Gemini API Key | Google 模型清單 |
| OpenAI | 自備 OpenAI API Key | OpenAI 模型清單 |
| DeepSeek | 自備 DeepSeek API Key | DeepSeek 模型清單 |
| Anthropic | 自備 Anthropic API Key | Anthropic 模型清單 |

如果供應商斷線或模型清單 API 失敗，設定介面會顯示錯誤；**不把靜態候選模型冒充成已通過驗證的模型**。
本地 OpenCode 免費模型可能下架或限流；不保證長期免費與穩定可用。

## 金鑰保護與資料處理

- 輸入的 API Key 會送到 AstraTube 本地後端，由後端向選定供應商驗證；驗證當下不會寫入設定檔。
- 按下儲存後，金鑰才會寫到本機設定，前端只能取得遮罩後的提示。
- Windows Portable 的設定位於 `data/app` 下，包含敏感金鑰，請勿把整個 `data` 資料夾公開分享。
- 雲端模型產生摘要或翻譯時，相關字幕內容將送往使用者明確選擇的供應商。
- 選擇智慧模式或 Ollama 時，不會自動降級使用雲端，遇到不可用會直接提示。

## 仍未包含的功能

AstraTube 內建 llama.cpp 模型下載、Whisper 轉錄，以及 Windows 多設備實機驗收仍在後續工作範圍。
此設定介面不代表已提供完全免下載的內建 AI 或雲端免費保證。
