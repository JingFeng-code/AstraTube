# AstraTube Windows 免安裝版 Alpha

這是 **Tauri v2 + React + FastAPI PyInstaller Sidecar** 的**內部測試版**，以**免安裝（Portable）資料夾**發行：解壓縮後直接執行，不需要安裝程式，也不需要安裝 Python／Node.js。它尚未完成實際影片、Ollama 或跨裝置驗收，不是正式公開產品。Web／Codespaces 版維持可使用。

## 資料夾內容

```
AstraTube-Portable\
  AstraTube.exe              主程式
  astratube-backend.exe      背景服務（由主程式自動啟動與關閉）
  README-使用說明.txt         給使用者的簡短說明
  LICENSE.txt、THIRD_PARTY_NOTICES.md
  data\                      第一次執行時建立
    app\                     設定（settings.json，含 API Key）、匯入字幕、翻譯與逐字稿快取
    webview\                 WebView2 瀏覽資料
```

- **所有使用者資料都在 `data` 資料夾**，不寫入 `%APPDATA%`／`%LOCALAPPDATA%`。整個資料夾可以搬到別台電腦或 USB；刪除資料夾就完全清除。
- **PyInstaller 的暫存檔例外**：背景服務是單一 exe，執行時會解壓到系統暫存資料夾（`%TEMP%\_MEI…`），正常結束後自動清除，不含使用者資料。
- **要放在可以寫入的位置**，例如「文件」、「桌面」或 USB。放在 `C:\Program Files` 這類需要系統管理員權限的位置時，程式仍會開啟，但會說明原因並請你移動資料夾，不會啟動背景服務。
- **更新**：解壓新版，把舊版的 `data` 資料夾複製到新版資料夾，再開新版的 `AstraTube.exe`。
- **從舊安裝版搬資料（選用）**：舊安裝版的資料在 `%APPDATA%\dev.jingfeng.astratube`。若要沿用設定與匯入字幕，把其中的內容複製到免安裝版的 `data\app`。注意其中含有 API Key。

## 架構與安全

- **背景服務的生命週期**：Tauri 主程式從自己所在的資料夾啟動 `astratube-backend.exe`，並告訴它資料要存在 `data\app`。正常關閉時，主程式會停止背景服務；主程式當掉或被強制結束時，背景服務每 2 秒確認主程式是否還在，不在就自行結束。
- **WebView2 資料**：主視窗在程式中建立並指定 `data\webview`。Tauri 預設會把這些資料寫到 `%LOCALAPPDATA%`，設定檔裡的相對路徑也只會落在那裡，所以在程式碼中指定絕對路徑。
- **連線與 Token**：每次啟動在回環位址選隨機埠，並產生新的高熵 Token；所有 API 請求都要帶 `X-Astra-Desktop-Token`。後端只監聽 `127.0.0.1`，並檢查 Host 與 Origin，其他網站即使猜到 Token 也會被拒絕。
- **網頁介面的權限**：Tauri 不提供任意 shell 指令權限給網頁介面。Coding Agent 自動執行強制關閉。
- **第三方腳本隔離**：主視窗不載入任何第三方腳本（CSP `script-src 'self'`）。YouTube 播放器 API 在獨立來源 `http://astraplayer.localhost` 的 iframe 內執行，拿不到 Tauri IPC 與後端 Token；詳見 [桌面版 YouTube 播放器隔離說明](DESKTOP_PLAYER_ISOLATION.zh-TW.md)。

## 需要的環境

- Windows 10／11 64 位元。
- **Microsoft Edge WebView2 Runtime**：Windows 11 與大多數 Windows 10 已內建。免安裝版無法替你安裝；若視窗空白或無法開啟，請從[微軟官網](https://developer.microsoft.com/microsoft-edge/webview2/)安裝 WebView2 Runtime。

## 目前不包含什麼？

- **不含 Whisper／yt-dlp**：沒有公開字幕的影片，可匯入你合法持有的 SRT／VTT。
- **沒有數位簽章與自動更新**：第一次執行可能出現「Windows 已保護您的電腦」。不要為此關閉防毒軟體。
- **可用性沒有保證**：外部 AI 服務、YouTube／Bilibili 字幕與嵌入播放器，不保證在所有地區、所有影片都能成功。
- **尚未在多台 Windows 10／11 實機驗收**。

## 從 GitHub 取得測試版

1. 打開儲存庫的 **Actions → Windows desktop alpha**。
2. 選擇一筆**成功**的執行紀錄。
3. 在頁面下方 Artifacts 下載 `AstraTube-Windows-x64-portable-unsigned`。下載的 ZIP 解壓縮後就是可直接執行的資料夾。
4. 只有在了解這是開發版、來源可信時才執行。請勿透過不明網站轉載。

下載 Actions Artifacts 需要登入有權限的 GitHub 帳號；這不是公開的 Release 下載頁。

## 自動化測試（CI）

Windows workflow 每次會依序：
1. 封裝背景服務並做後端冒煙測試：Token、來源檢查、主程式消失後自行結束。
2. 編譯主程式並組出免安裝資料夾。
3. 執行 `scripts/smoke_portable.ps1`，啟動**真正的主程式**：
   - 放在含中文與空白的路徑也能執行。
   - 背景服務只監聽 `127.0.0.1`。
   - 資料只寫在 `data`，沒有寫入 `%APPDATA%`／`%LOCALAPPDATA%`。
   - 正常關閉與強制結束後，都沒有殘留背景服務。
   - 資料夾無法寫入時不啟動背景服務，但視窗仍會開啟。
4. 執行 Rust 單元測試。

這些都是自動化測試，不等於 Windows 實機驗收；實機步驟見 [MANUAL_SMOKE_TEST.zh-TW.md](MANUAL_SMOKE_TEST.zh-TW.md)。

## 開發者在 Windows 編譯

需要 Windows x64、Python 3.12、Node.js 20+、Rust stable（MSVC 工具鏈）、Microsoft C++ Build Tools、網路連線。

```powershell
./scripts/build-desktop.ps1
```

```powershell
./scripts/smoke_portable.ps1 -PortableDir desktop/portable/AstraTube-Portable
```

產出：`desktop/portable/AstraTube-Portable/` 資料夾，以及 `desktop/portable/AstraTube-Portable-x64.zip`。

**安全提醒：** 這是**單機自用桌面架構**。不要把內部 FastAPI 暴露到網際網路；若將來提供雲端多人版，需要另外的登入、資料隔離、伺服器授權與費用限制。

官方技術文件：[Tauri Sidecar](https://v2.tauri.app/develop/sidecar/) · [WebView2 Runtime 部署](https://learn.microsoft.com/microsoft-edge/webview2/concepts/distribution)。
