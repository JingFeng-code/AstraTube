# AstraTube Beta 發布門檻

本文件定義「可以邀請少量一般使用者測試（Beta）」前必須達成的條件。**Beta 不是正式公開發布**，測試版仍只透過私下管道提供給知情的測試者。

## 1. 目前狀態（2026-10-29）

| 層級 | 狀態 | 說明 |
|---|---|---|
| 內部測試 Alpha（開發者自己用） | ✅ 可以 | CI 與 Windows workflow 通過；P0／P1 修正見 PR [JingFeng-code/AstraTube#17](https://github.com/JingFeng-code/AstraTube/pull/17) |
| 少量使用者 Beta | ❌ 尚未 | 缺 Windows 實機驗收紀錄、程式碼簽章與授權清單（見第 4 節） |
| 公開發布 | ❌ 不可 | 另需更新機制、隱私說明、完整授權審查、長期支援計畫 |

驗收層級必須分開記錄，不能互相代替：

1. **免安裝版成功產出**：Windows workflow 綠燈並上傳 Artifact；CI 內也會啟動真正的主程式，檢查資料位置與關閉後無殘留（`scripts/smoke_portable.ps1`）。
2. **Sidecar smoke test 通過**：打包後的後端能啟動、Token 與來源檢查有效、啟動程式消失後會自行結束（CI 內自動執行）。
3. **完整桌面操作通過**：真人在 Windows 10／11 依 [MANUAL_SMOKE_TEST.zh-TW.md](MANUAL_SMOKE_TEST.zh-TW.md) 操作並留下紀錄。**目前尚無任何一筆。**

## 2. Beta 必要門檻（全部打勾才可發出邀請）

### 安全與隱私

- [x] 其他網站不能讀寫本機 API（Web 模式 Origin／Host 檢查；桌面 Token）
- [x] 一般模式與 Ollama 不會默默改用付費或雲端模型
- [x] Coding Agent 自動執行預設關閉，桌面版強制關閉
- [ ] 執行檔有程式碼簽章（避免教使用者忽略 SmartScreen）
- [ ] 隨免安裝版附上完整第三方授權清單（Python、PyInstaller、Tauri、WebView2、Python 套件）
- [ ] 一頁式隱私說明：哪些資料留在本機（設定、字幕、快取位置）、哪些會送到外部（YouTube／Bilibili 字幕、免費模型服務、使用者自填的雲端 API）

### Windows 桌面可靠性

- [x] 啟動程式消失後後端自行結束（CI 自動驗證打包 exe）
- [x] 設定檔原子寫入，不會因當機清空
- [ ] Windows 11 實機：解壓縮 → 首次啟動 → 關閉 → 工作管理員確認沒有 `astratube-backend.exe`
- [ ] Windows 10 實機（WebView2 可能需自行安裝）同上
- [ ] 資料夾路徑含中文或空白、搬到 USB 後可正常啟動與存檔（CI 已自動測試中文與空白路徑）
- [ ] 換新版並複製 `data` 資料夾後，設定與匯入字幕仍在
- [ ] 刪除資料夾後不留任何設定；`%APPDATA%`／`%LOCALAPPDATA%` 沒有 AstraTube 資料（CI 已自動檢查）
- [ ] 加入單一實例限制，或實測確認開兩次不會損壞資料

### 主要流程（一般模式，不需任何 API Key）

- [ ] 貼上有公開字幕的 YouTube 網址 → 產生知識卡
- [ ] 播放器可播放，點擊字幕／卡片可跳到對應時間
- [ ] 按「翻譯」可逐批取得台灣繁中字幕，失敗時保留原文並可重試
- [ ] AI 問答只回答目前這支影片，切換影片後不混用
- [ ] 匯出 Markdown 筆記可在記事本或 Obsidian 開啟
- [ ] Bilibili 公開字幕影片同上（進度只能點擊跳轉，不宣稱同步）
- [ ] 無字幕影片：顯示「請匯入 SRT／VTT」，匯入後可分析
- [ ] 斷網時：錯誤訊息看得懂，恢復網路後重試成功

### 開發者模式

- [ ] 開關切換不會清掉已選模型或已存設定
- [ ] Ollama：未啟動、模型不存在、正常三種情況都有清楚訊息，且不會改用雲端
- [ ] 自填 API Key 存檔後，重開程式仍有效；畫面只顯示遮罩

## 3. Windows 與 Web 版差異

| 項目 | Windows 免安裝版 Alpha | Web／Codespaces |
|---|---|---|
| 需要 Python／Node | 不需要（已打包） | 需要 |
| 後端存取控制 | 每次啟動隨機 Token ＋ 來源檢查 | 來源檢查（只限本機頁面與目前 Codespace） |
| 資料位置 | 程式旁的 `data\app`（`settings.json`、`.cache\`）與 `data\webview` | 專案根目錄的 `settings.json`、`.cache/` |
| 無字幕影片 | 只能匯入 SRT／VTT（未內建 Whisper／yt-dlp） | 可走本機 Whisper（需安裝完整 `requirements.txt`） |
| Ollama | 同一台電腦的 `127.0.0.1:11434` | 只能連到後端所在環境；Codespaces 連不到你電腦上的 Ollama |
| Coding Agent 自動執行 | 強制關閉 | 預設關閉，可用 `.env` 開啟（不建議） |
| 多人使用 | 不支援 | 不支援，**不可**公開成多人服務 |

## 4. 目前阻擋 Beta 的事項（依優先順序）

1. **沒有任何 Windows 實機驗收紀錄**——請依 [MANUAL_SMOKE_TEST.zh-TW.md](MANUAL_SMOKE_TEST.zh-TW.md) 至少在一台 Windows 11 完成並保存結果。
2. **未簽章執行檔**——一般使用者會看到「Windows 已保護您的電腦」。
3. **完整第三方授權清單與隱私說明**尚未隨免安裝版提供。
4. **建置不可重現**（沒有 `Cargo.lock`、Tauri CLI 與 Python 套件未鎖版本）——Beta 期間回報的問題可能無法用同一份原始碼重現。
5. **首次使用引導不足**——非工程師打開後只看到標語與輸入框。
