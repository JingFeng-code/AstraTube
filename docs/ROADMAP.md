# AstraTube 開發路線

> 以下保留各階段當時的紀錄。後續版本已移除開發者模式與 OpenCode 免費模型選項，目前做法請見 [AI 供應商設定](AI_PROVIDER_SETUP.zh-TW.md)。

## Phase 0：開源基底與開發環境

- [x] 保留 MIT 授權與來源紀錄
- [x] 匯入 YouTube Card Reader 前後端與測試（略去上游大型展示媒體）
- [x] 增加 Codespaces 設定及前端 /api 同源代理
- [x] 預設繁中介面與輸出；Coding Agent 自動執行關閉
- [x] GitHub Actions CI 通過（前端與後端自動測試；不等於實機驗收）
- [ ] 真人透過 Codespaces 成功觀看影片並產生知識卡

## Phase 1：本地模型與繁體品質

- [x] FastAPI 新增可設定 Ollama Provider（摘要、問答、模型清單與連線檢查；本地環境待驗收）
- [ ] 保留原始逐字稿，不直接對英文原文強制繁化
- [ ] 技術專有名詞表、翻譯快取與品質測試

## Phase 2：TT 類型影片閱讀

- [ ] YouTube IFrame API 播放進度同步
- [x] 原文 + 台灣繁中逐句字幕（免費模型按鈕翻譯、時間戳跳轉；實際平台驗收待辦）
- [x] SRT / VTT 匯入與字幕搜尋（自行持有檔案、平台 ID 綁定及本機儲存）
- [ ] 分段翻譯、模型切換、錯誤重試與快取

## Phase 3：選配 VideoToNo

- [ ] 只在有合法來源且原生轉錄不足時，整合 VideoToNo HTTP Adapter
- [ ] 不直接合併兩套後端，保留可替換的 TranscriptSegment 契約


## Phase 1a：Bilibili（Issue #5）
- [x] 公開 BV 影片／分 P 識別
- [x] 匿名公開字幕擷取 + 快取
- [x] 繁中知識卡與 AI 問答
- [x] 官方嵌入播放器與時間戳跳轉
- [x] 模擬 API 的單元測試
- [ ] Codespaces 實際 B 站連線／字幕驗收


## Phase 2a：時間軸字幕工作區（Issue #4 第一切片）
- [x] 從現有字幕快取生成帶起迄時間的段落，提供 API 與單元測試
- [x] YouTube 官方 IFrame API 讀取播放進度，點擊字幕跳轉
- [x] Bilibili 公開字幕搜尋及點擊時間戳跳轉（不宣稱站外 iframe 進度可讀）
- [x] 不需任何額外付費 API、無字幕時顯示原因
- [ ] 第二切片：可選的台灣繁體中文翻譯、同一段字幕雙語顯示、翻譯快取
- [x] 第三切片：SRT/VTT 匯入並保留匯入字幕的毫秒級起訖時間
- [ ] 真實瀏覽器跨平台及不同影片的端到端驗收


## Phase 2b：逐批字幕翻譯（Issue #4 第二切片）
- [x] 免費模型按鈕翻譯每次最多 16 句
- [x] 原文／台灣繁中同一時間軸顯示及顯示開關
- [x] 模型與文字版本分離的本機翻譯快取
- [x] 無自動付費備援、失敗保留原文與進度
- [x] Python / Node 對齊與快取測試
- [ ] 真人驗收：實際 YouTube / Bilibili 字幕 API、翻譯效果及播放器同步
- [x] SRT/VTT 匯入與準確保存匯入字幕的起訖時間；平台原始字幕的毫秒級時間仍待支援


## Phase 1b：本地 Ollama Provider（Issue #3 第一切片）
- [x] 以 `/api/chat` 接入本機摘要、問答與深入解析
- [x] 開發者模式設定網址／模型，透過 `/api/tags` 讀取已安裝模型
- [x] 嚴格指定 Ollama 時不 fallback 到雲端付費供應商
- [x] 本地併發限制 1、連線錯誤提示、回環網域與埠檢查
- [x] Mock Ollama API 回歸測試
- [ ] Windows / WSL 真實本地 Ollama 端到端驗收
- [x] 雙語字幕使用本地模型翻譯（見 Phase 2c）


## Phase 2c：本地 Ollama 字幕翻譯（Issue #3 第二切片）
- [x] 在開發者模式的字幕面板選擇已安裝的 Ollama 模型
- [x] 字幕翻譯 API 僅接受 OpenCode 免費模型或 Ollama 本地模型
- [x] 按模型／供應商隔離翻譯快取，切換時重新讀取、保留舊譯文
- [x] 回到一般模式後恢復預設免費模型，不自動 fallback 付費雲端
- [x] 增加後端與前端 Mock 測試
- [ ] Windows／WSL Ollama 實機驗收及真實影片翻譯品質檢查


## Phase 2d：SRT／VTT 字幕匯入與精確時間軸（Issue #4 第三切片）
- [x] 一般模式可先貼 YouTube／Bilibili 完整影片網址，再匯入合法持有的 SRT/VTT 字幕文字
- [x] 匯入與檢視限 1 MB / 6000 句，解析 SRT/VTT 時間戳並保留毫秒級起迄時間
- [x] 按影片 ID（Bilibili 另含分 P）區分儲存，移除匯入字幕可恢復平台來源
- [x] 摘要、問答及翻譯 API 能共用匯入字幕；不需下載任何影音
- [x] 後端測試涵蓋格式、時間精度、影片來源、分 P 隔離、拒絕不合法網址
- [ ] 真實瀏覽器驗收與跨平台播放器的毫秒級跳轉誤差測試
- [ ] 影片平台原生字幕時間精度保存（目前僅匯入 SRT/VTT 保留原始起迄）
- [ ] 公開多人部署前須完成使用者認證、隔離與檔案存取限制


## Phase 4a：Windows Desktop Alpha（Issue #14）
- [x] 建立 Tauri v2 Desktop Shell、重用 React 與 FastAPI
- [x] 新增 Windows PyInstaller Sidecar 封裝與 GitHub Actions 測試安裝包工作流程
- [x] 本機隨機埠與每次啟動的一次性 Token 驗證
- [x] Desktop 設定、字幕、逐字稿快取移入使用者資料目錄
- [x] 保留 Web／Codespaces 使用模式
- [ ] Windows 免安裝版（Portable）實機 UI 驗收（自動建置與 CI 冒煙測試通過不等於實機操作）
- [ ] 製作品質較佳的正式 App 圖示、數位簽章與更新功能
- [ ] 增加桌面端完整 Whisper 轉錄等原生依賴（Alpha 尚未包含）
- [ ] 公開下載前的版權合規、安全與隱私稽核
