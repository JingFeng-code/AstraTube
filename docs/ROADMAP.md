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
