//! 免安裝版（Portable）的資料位置。
//!
//! 所有使用者資料都放在主程式旁的 `data` 資料夾，不寫入 `%APPDATA%`／`%LOCALAPPDATA%`：
//!   data/app      設定（settings.json）、匯入字幕、翻譯與逐字稿快取（交給 FastAPI 後端）
//!   data/webview  WebView2 的瀏覽資料（Cookie、localStorage）
//! 整個資料夾可以搬到別台電腦或 USB；刪除資料夾即完全清除。

use std::fs;
use std::path::{Path, PathBuf};

pub struct PortableDirs {
    pub root: PathBuf,
    pub app: PathBuf,
    pub webview: PathBuf,
}

pub fn dirs_for(exe_dir: &Path) -> PortableDirs {
    let root = exe_dir.join("data");
    PortableDirs {
        app: root.join("app"),
        webview: root.join("webview"),
        root,
    }
}

/// 建立資料夾並實際寫入測試檔，確認這個位置可以寫入。
/// 失敗時回傳給使用者看的繁中說明（含路徑與建議），由前端顯示。
pub fn prepare(dirs: &PortableDirs) -> Result<(), String> {
    let check = || -> std::io::Result<()> {
        fs::create_dir_all(&dirs.app)?;
        fs::create_dir_all(&dirs.webview)?;
        let probe = dirs.root.join(".write-test");
        fs::write(&probe, b"ok")?;
        fs::remove_file(&probe)
    };
    check().map_err(|error| {
        format!(
            "AstraTube 無法在程式所在位置建立資料夾：{}（{}）。\
             免安裝版會把設定與快取存在程式旁的 data 資料夾，請把整個 AstraTube 資料夾\
             移到「文件」、「桌面」或 USB 隨身碟等可以寫入的位置後再開啟，\
             不要放在 C:\\Program Files 這類需要系統管理員權限的位置。",
            dirs.root.display(),
            error
        )
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_dir(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("astratube-portable-{}-{}", name, std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn data_lives_next_to_the_executable() {
        let dirs = dirs_for(Path::new("D:/工具/AstraTube 可攜"));
        assert_eq!(dirs.root, Path::new("D:/工具/AstraTube 可攜").join("data"));
        assert_eq!(dirs.app, dirs.root.join("app"));
        assert_eq!(dirs.webview, dirs.root.join("webview"));
    }

    #[test]
    fn prepare_creates_writable_folders_with_unicode_and_spaces() {
        let base = temp_dir("中文 路徑");
        let dirs = dirs_for(&base);
        prepare(&dirs).expect("writable location");
        assert!(dirs.app.is_dir() && dirs.webview.is_dir());
        assert!(!dirs.root.join(".write-test").exists(), "測試檔要清掉");
        let _ = fs::remove_dir_all(&base);
    }

    #[test]
    fn prepare_explains_unwritable_location() {
        let base = temp_dir("blocked");
        // data 已經是一個檔案：無法建立資料夾，模擬沒有寫入權限的位置
        fs::write(base.join("data"), b"not a folder").unwrap();
        let message = prepare(&dirs_for(&base)).unwrap_err();
        assert!(message.contains("無法在程式所在位置建立資料夾"));
        assert!(message.contains("Program Files"));
        let _ = fs::remove_dir_all(&base);
    }
}
