AstraTube 免安裝版（Windows x64 測試版）
==========================================

【開始使用】
1. 把整個「AstraTube-Portable」資料夾放到你可以寫入的位置，例如「文件」、「桌面」或 USB 隨身碟。
   請不要放在 C:\Program Files 這類需要系統管理員權限的位置。
2. 雙擊 AstraTube.exe。
   第一次執行時 Windows 可能顯示「Windows 已保護您的電腦」：這是因為測試版尚未數位簽章。
   只有在確認檔案是你自己從 AstraTube 的 GitHub Actions 下載的情況下，才按「其他資訊 → 仍要執行」。
   不要為了執行而關閉防毒軟體。

【需要的環境】
- Windows 10／11 64 位元。
- Microsoft Edge WebView2 Runtime：Windows 11 與大多數 Windows 10 已內建。
  若開啟後視窗空白或無法啟動，請到微軟官網下載安裝「WebView2 Runtime」：
  https://developer.microsoft.com/microsoft-edge/webview2/
- 不需要安裝 Python 或 Node.js。

【資料存在哪裡】
所有資料都在這個資料夾裡的 data 資料夾：
- data\app      設定（含你輸入的 API Key）、匯入的字幕、翻譯與字幕快取
- data\webview  內建瀏覽器的資料
AstraTube 不會把資料寫到 %APPDATA%。
data\app\settings.json 含有 API Key：分享資料夾給別人前，請先刪除 data 資料夾。

【更新到新版本】
1. 關閉 AstraTube。
2. 下載並解壓縮新版。
3. 把舊版資料夾裡的 data 資料夾複製到新版資料夾（取代）。
4. 開啟新版的 AstraTube.exe。

【移除】
關閉 AstraTube 後，直接刪除整個資料夾即可，不會留下任何設定。

【檔案說明】
AstraTube.exe              主程式
astratube-backend.exe      背景服務（由主程式自動啟動與關閉，請勿單獨執行）
LICENSE.txt、THIRD_PARTY_NOTICES.md   授權與第三方聲明
