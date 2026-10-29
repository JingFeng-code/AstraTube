# YouTube Card Reader

> 看完，不只留下摘要。把教學真的做出來。

[繁體中文](#它現在能做什麼) · [English](#english)

YouTube Card Reader 是一個在本機執行的開源閱讀工具。貼上 YouTube 影片或文章，它會整理成可以翻閱的知識卡；YouTube 卡片保留時間戳，點一下就能跳回原片段。

這次改版加入完整的「把它做出來」流程。程式會辨識內容類型，依影片素材建議下一步，再把整支影片交給你電腦上的 **Codex CLI** 或 **Claude Code**。最後會在本機產出實際檔案：可以跑的專案、一步一步的操作引導、教學頁，或練習題庫。

![YouTube Card Reader 閱讀介面](docs/images/preview.png)

## 它現在能做什麼

### 從影片走到實作

按下「把它做出來」後，可以選四種產出：

- **可以跑的專案**：適合程式、AI 工具與建置教學。產出完整程式碼、README、設定步驟與驗收方式。
- **一步一步的操作引導**：適合沒有程式碼的工具教學。產出可離線開啟的 `guide.html`，包含操作步驟、完成判準與常見卡關處理。
- **一頁弄懂的教學**：把觀念、術語、難點與自我驗證題整理成 `study.html`。
- **練習題庫**：依影片實際內容產出可互動、可記錄進度的 `drill.html`。

教學影片會依內容自動建議「專案」或「操作引導」；觀念、訪談、評測與新聞預設走教學頁。判斷錯了也沒關係，執行前可以自己改。

### 實作不是黑箱

- 自動偵測本機的 Codex CLI 與 Claude Code，並列出可選模型。
- 執行時顯示目前在規劃、查證或寫檔，以及已經產出幾個檔案；不使用假的百分比。
- 做完後直接在 App 裡預覽 HTML、Markdown、文字與常見程式碼檔案，也可以打開完整產出資料夾。
- 不想讓 agent 直接執行，可以選「只要給我指令」：App 會建立 `TASK.md`，再給一行可自行貼進終端機的命令。
- 找不到 coding agent 時，不會只丟錯誤訊息；App 會提供安裝與登入引導。

實作檔案預設放在：

```text
~/Documents/YCR 實作產出
```

### 原本的閱讀功能都還在

- **知識卡，不是摘要牆**：每張卡片只講一件事，保留重點、原話、畫面資訊與時間戳。
- **時間戳可直接跳轉**：點卡片時間就回到影片對應位置。
- **讀得到畫面**：開啟「深視覺」後，Gemini 會讀取投影片、白板與畫面中的程式碼；若同時有字幕，語音時間軸仍以字幕為準。
- **問整支影片**：聊天室已讀過完整逐字稿，可以追問內容，也能在有 Gemini 金鑰時搜尋影片外資料。
- **深入解析單張卡片**：針對一個重點補背景與說明。
- **存進 Obsidian**：收集要留下的卡片，再寫入指定 vault。
- **影片與文章都能讀**：YouTube 走字幕／深視覺／本機 Whisper 瀑布；一般網頁文章直接抽取正文。
- **雙語介面、六種輸出語言**：介面支援繁體中文與英文；卡片可輸出繁中、簡中、英文、日文、韓文與西班牙文。

![卡片與問答面板](docs/images/cards.png)

## 安裝與啟動

需要 **Python 3.10+** 與 **Node.js 18+**。

```bash
git clone https://github.com/chang416/youtube-card-reader.git
cd youtube-card-reader
./scripts/start.sh
```

Windows：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```

也可以在 macOS 雙擊 `start.command`，或在 Windows 雙擊 `start.bat`。

第一次啟動會自動建立 Python 虛擬環境並安裝前後端套件。完成後瀏覽器會開啟：

```text
http://127.0.0.1:15273
```

停止服務：

```bash
./scripts/stop.sh
```

## 使用實作功能

### 建議：安裝一個本機 coding agent

摘要與知識卡不需要 coding agent；只有「把它做出來」需要能讀寫檔案、執行指令與查證資料的工具。

Codex CLI：

```bash
npm install -g @openai/codex
```

或使用 Homebrew：

```bash
brew install --cask codex
```

Claude Code：

```bash
npm install -g @anthropic-ai/claude-code
```

安裝後依各工具的畫面完成登入，再重新打開「把它做出來」。App 會自動偵測，不需要手動填路徑。

### 純 API 也能產出，但限制不同

如果已設定 Gemini 或其他模型供應商，也可以直接產生檔案。這條路徑是單次生成，無法像本機 CLI 一樣上網查證、多輪修正或實際執行測試，因此 App 會：

- 在開始前與交付時標示「未查證」。
- 禁止模型憑印象提供網址；素材沒有的資訊會標成「需自行確認」。
- 建議需要可靠連結、正確選單路徑或可執行專案時改用 Codex CLI／Claude Code。

## 設定與資料

所有金鑰都可以不填。有字幕的影片仍可使用免金鑰的 OpenCode Zen 免費模型整理。

| 服務 | 用途 | 是否必要 |
|---|---|---|
| OpenCode Zen | 免金鑰摘要與模型選擇 | 否 |
| Google Gemini | 深視覺、影片外搜尋、API 實作備援 | 否 |
| OpenAI | 額外的摘要／問答模型 | 否 |
| Anthropic | 額外的摘要／問答模型 | 否 |
| DeepSeek | 額外的摘要／問答模型 | 否 |

可以直接在右上角「設定」填寫，也可以複製 `.env.example` 為 `.env`。App 內設定會寫入專案根目錄的 `settings.json`；`.env`、`settings.json` 與 API keys 都在 `.gitignore` 內。

這是一個 local-first 工具：介面、快取、筆記與實作檔案都留在你的電腦，專案本身沒有帳號系統、遙測或自有後端。使用外部模型時，送出的逐字稿、卡片或問題仍會依你選擇的供應商政策傳給該供應商。

## 安全與誠實限制

- 「貼上網址」只會整理內容，不會直接執行程式。實作前一定會讓使用者選擇產出類型與執行工具。
- Codex CLI 以 `workspace-write` 執行，工作目錄限制在該次產出資料夾；預覽與「打開資料夾」端點也只接受產出根目錄底下的路徑。
- Coding agent 仍可能執行指令或建立錯誤內容。若不希望自動執行，選「只要給我指令」，或把 `AUTO_RUN_CLI` 設為 `0`，先閱讀 `TASK.md` 再自行執行。
- 「可以跑的專案」只適合真的包含程式碼、指令或可自動化步驟的教學。素材不足時，任務會要求 agent 誠實說明不適合，而不是硬做一個空殼。

## 它怎麼運作

### 內容整理

```text
YouTube／文章
    ↓
字幕 → 深視覺 → 本機 Whisper（依設定與可用性降級）
    ↓
分段整理、覆蓋率檢查、知識卡
    ↓
辨識內容類型與可行動卡片
```

預設優先使用字幕，因為快、免費、時間準。開啟深視覺時，Gemini 會優先讀影片畫面；若字幕存在，口說內容與時間軸仍以字幕為準，畫面筆記再按時間合併。

### 從知識卡到實體檔案

```text
整支影片的全部卡片
    ↓
選擇 project／SOP／study／drill
    ↓
建立 TASK.md 與獨立產出資料夾
    ↓
Codex CLI／Claude Code 執行，或純 API 單次產生
    ↓
串流進度、檔案清單、App 內預覽
```

實作使用整支影片的全部卡片，不會只拿目前畫面上的一張卡片斷章取義。

## 專案結構

```text
backend/app/
  agents/       Codex CLI／Claude Code 偵測、模型選擇與執行
  api/          summarize、ask、implement、models、notes、settings
  core/         設定、雙語訊息、語言與繁簡正規化
  llm/          Gemini、OpenCode、OpenAI、DeepSeek、Anthropic 與路由備援
  prompts/      卡片整理、問答、四種實作任務與 HTML 設計規則
  transcript/   字幕、深視覺、本機 Whisper、快取與轉錄瀑布
frontend/src/
  components/   閱讀、問答、設定、實作進度與產出預覽
  hooks/        卡片、模型、設定、串流摘要與實作狀態
  i18n/         繁體中文／英文介面
```

## 測試

測試不會呼叫真實模型，也不需要 API key。

```bash
cd backend
PYTHONPATH=. .venv/bin/python tests/test_deepsrt.py
PYTHONPATH=. .venv/bin/python tests/test_progress_stream.py
PYTHONPATH=. .venv/bin/python tests/test_providers.py
PYTHONPATH=. .venv/bin/python tests/test_content_type.py
PYTHONPATH=. .venv/bin/python tests/test_implement.py
PYTHONPATH=. .venv/bin/python tests/test_messages.py
```

前端：

```bash
cd frontend
npm ci
npm run build
```

---

## English

YouTube Card Reader is a local-first, open-source reader that turns YouTube videos and web articles into navigable knowledge cards. YouTube cards keep their timestamps, so every idea links back to the exact moment it came from.

The new release adds an end-to-end **Implement** workflow. After the cards are ready, the app classifies the content, suggests a useful next step, and can hand the full video to a local **Codex CLI** or **Claude Code** installation. The result is a folder of real files rather than another summary.

### Four output tracks

- **Build**: a runnable project or agent-ready instruction package for technical tutorials.
- **SOP**: a verified, step-by-step `guide.html` for tool tutorials.
- **Study**: a self-contained `study.html` with terminology, missing background, and comprehension checks.
- **Drill**: an interactive `drill.html` generated only from the source material.

The app detects installed coding agents and their available models, streams real phases and file creation, previews common output formats in-app, and supports a manual mode that writes `TASK.md` without running the agent automatically.

### Existing reader features

- Timestamped idea cards with transcript quotes and on-screen notes.
- Deep visual transcription for slides, whiteboards, and code shown on screen.
- Full-video Q&A, per-card deep dives, and Obsidian export.
- YouTube and web article input.
- English and Traditional Chinese UI with six output languages.
- Free, keyless summarization through OpenCode Zen when captions are available.

### Quick start

Requires Python 3.10+ and Node.js 18+.

```bash
git clone https://github.com/chang416/youtube-card-reader.git
cd youtube-card-reader
./scripts/start.sh
```

On Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```

For the Implement workflow, install and sign in to Codex CLI or Claude Code. API-only generation is available when a provider is configured, but it cannot browse or verify external facts; the app labels those outputs as unverified.

The UI, cache, notes, and generated files stay on your computer. The project has no account system, telemetry, or hosted backend. When you select an external model, submitted content is still handled under that provider's policies.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Issues and pull requests are welcome, especially around new content types, output tracks, languages, providers, and regression cases.

## License

MIT. See [LICENSE](LICENSE).

## Acknowledgements

Built on top of lootube, the Chinese-only predecessor this project grew out of. Transcripts come from `youtube-transcript-api`, local transcription from `faster-whisper`, and the free model chain from OpenCode Zen.
