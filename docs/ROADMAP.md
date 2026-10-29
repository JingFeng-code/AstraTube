# AstraTube 開發路線

## Phase 0：開源基底與開發環境

- [x] 保留 MIT 授權與來源紀錄
- [x] 匯入 YouTube Card Reader 前後端與測試（略去上游大型展示媒體）
- [x] 增加 Codespaces 設定及前端 /api 同源代理
- [x] 預設繁中介面與輸出；Coding Agent 自動執行關閉
- [ ] GitHub Actions CI 通過
- [ ] 真人透過 Codespaces 成功觀看影片並產生知識卡

## Phase 1：本地模型與繁體品質

- [ ] FastAPI 新增可設定 Ollama Provider（模型與本機位址）
- [ ] 保留原始逐字稿，不直接對英文原文強制繁化
- [ ] 技術專有名詞表、翻譯快取與品質測試

## Phase 2：TT 類型影片閱讀

- [ ] YouTube IFrame API 播放進度同步
- [ ] 原文 + 台灣繁中逐句字幕，時間戳跳轉
- [ ] SRT / VTT 匯入與字幕搜尋
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
- [ ] 第三切片：SRT/VTT 匯入、較準確的原始字幕起訖時間
- [ ] 真實瀏覽器跨平台及不同影片的端到端驗收
