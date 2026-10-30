# AstraTube AI 供應商設定（Windows Portable / Web）

## 使用方式

1. 在主畫面點擊「AI 來源」。
2. **選擇供應商**：智慧選擇、Ollama，或自備金鑰的雲端 AI。
3. **驗證連線**：雲端供應商先驗證 API Key。已儲存過金鑰，可直接重新檢查；不需重新輸入。
4. **選擇模型**：只有驗證成功才會顯示供應商回傳的模型。大型清單可搜尋名稱。
5. **儲存**：才會保存新金鑰；摘要、知識卡、問答與字幕翻譯共用此模型。

模型清單成功取得 **不代表該模型一定可生成或免付費**；部分供應商的模型清單包含使用者尚無權限呼叫的模型。若遇到額度不足或模型不支援，請改選有權使用的模型。

## 可設定的來源

| 來源 | 連線條件 | 說明 |
| --- | --- | --- |
| 智慧選擇 | 本機已安裝 Ollama 模型 | 只用本機，不自行呼叫雲端 |
| Ollama | 電腦本機啟動 Ollama | 使用已下載模型，免 API Key |
| Google Gemini | Gemini API Key | 動態取得可用 Gemini 模型 |
| OpenAI | OpenAI API Key | 動態取得模型 |
| DeepSeek | DeepSeek API Key | 動態取得模型 |
| Anthropic Claude | Anthropic API Key | 動態取得模型 |
| OpenRouter | OpenRouter API Key | 可選多家模型，先向 /key 驗證金鑰，再查詢 /models |
| Groq | Groq API Key | 模型由 Groq API 提供 |
| Mistral AI | Mistral API Key | 優先顯示具聊天能力的模型 |
| Together AI | Together API Key | 模型由 Together API 提供 |

這些雲端供應商是否有免費額度及是否要求信用卡，依供應商當時的條款為準；AstraTube 不承諾免費。**OpenCode／免費線上 AI 已從新介面移除**，因為先前實際使用時無法可靠供外部程式呼叫。舊版記住的 OpenCode 偏好會遷移回智慧選擇。為了舊版用戶的相容性，內部舊程式碼暫時保留，但不作為一般使用者的選項。

## 隱私、金鑰與安全

- API Key 驗證由 AstraTube 的本機後端連線至**選定供應商的官方 HTTPS API**；不回傳金鑰到前端、不把金鑰傳給其他供應商。
- 新金鑰只有按下「儲存」後才寫入本機設定檔，設定檔包含敏感資訊，不要公開分享 Windows Portable 的 `data` 資料夾。
- 目前本機設定是檔案儲存而非 Windows Credential Manager；請務必保護電腦和備份檔案。
- 雲端生成時，影片字幕與對話資料會傳給**使用者選定的供應商**，可能計費。不支援未同意自動切換至其他雲端供應商。
- 模型與金鑰驗證失敗時，顯示明確狀態，**不使用靜態候選名單假裝連線成功**。
- OpenRouter 可能由平台自身將模型路由至後端服務商；平台內部路由不等同 AstraTube 擅自改動使用者選定的供應商。

## 還沒做的項目

- Windows 真實金鑰與多家供應商的端到端驗收。
- 內建 llama.cpp 模型一鍵下載與本地語音轉字幕。
- 不同供應商模型的價格、權限、支援功能及 context 限制之完整同步。
