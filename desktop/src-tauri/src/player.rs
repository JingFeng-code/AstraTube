//! astraplayer 自訂協定：只提供隔離的 YouTube 播放器宿主頁。
//!
//! 主視窗（tauri.localhost）擁有 Tauri IPC；YouTube 官方 IFrame API 是第三方腳本，
//! 不能和主視窗共用同一個 JavaScript 執行環境。這裡把宿主頁放在另一個來源
//! （Windows 為 http://astraplayer.localhost），Tauri 只把 IPC 腳本與 invoke key
//! 注入主框架，所以這個 iframe 內的腳本拿不到 invoke key，也就無法取得後端 Token。
//!
//! 檔案在編譯時嵌入，不讀取磁碟、不接受任意路徑。

use tauri::http::{header, Method, Request, Response, StatusCode};

pub const SCHEME: &str = "astraplayer";

const PLAYER_HTML: &[u8] = include_bytes!("../../../frontend/public/player/youtube.html");
const PLAYER_JS: &[u8] = include_bytes!("../../../frontend/public/player/youtube-host.js");

/// 宿主頁自己的 CSP：只允許自身腳本與 YouTube 官方網域，且只能被 AstraTube 主視窗嵌入。
pub const PLAYER_CSP: &str = "default-src 'none'; \
script-src 'self' https://www.youtube.com https://s.ytimg.com; \
frame-src https://www.youtube.com https://www.youtube-nocookie.com; \
connect-src https://www.youtube.com; \
img-src https: data:; \
style-src 'unsafe-inline'; \
base-uri 'none'; form-action 'none'; object-src 'none'; \
frame-ancestors http://tauri.localhost https://tauri.localhost tauri://localhost http://127.0.0.1:15273";

fn asset(path: &str) -> Option<(&'static str, &'static [u8])> {
    match path {
        "/player/youtube.html" => Some(("text/html; charset=utf-8", PLAYER_HTML)),
        "/player/youtube-host.js" => Some(("text/javascript; charset=utf-8", PLAYER_JS)),
        _ => None,
    }
}

fn plain(status: StatusCode) -> Response<Vec<u8>> {
    Response::builder()
        .status(status)
        .header(header::CONTENT_TYPE, "text/plain; charset=utf-8")
        .header(header::CACHE_CONTROL, "no-store")
        .body(Vec::new())
        .expect("static response headers are valid")
}

/// 依請求回應；只接受 GET／HEAD 與兩個固定路徑，其餘回 404／405。
pub fn respond(request: &Request<Vec<u8>>) -> Response<Vec<u8>> {
    let method = request.method();
    if method != Method::GET && method != Method::HEAD {
        return plain(StatusCode::METHOD_NOT_ALLOWED);
    }
    let Some((content_type, body)) = asset(request.uri().path()) else {
        return plain(StatusCode::NOT_FOUND);
    };
    Response::builder()
        .status(StatusCode::OK)
        .header(header::CONTENT_TYPE, content_type)
        .header(header::CONTENT_SECURITY_POLICY, PLAYER_CSP)
        .header(header::X_CONTENT_TYPE_OPTIONS, "nosniff")
        .header(header::REFERRER_POLICY, "strict-origin-when-cross-origin")
        .header(header::CACHE_CONTROL, "no-store")
        .body(if method == Method::HEAD { Vec::new() } else { body.to_vec() })
        .expect("static response headers are valid")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn get(uri: &str) -> Response<Vec<u8>> {
        respond(&Request::builder().method(Method::GET).uri(uri).body(Vec::new()).unwrap())
    }

    #[test]
    fn serves_only_the_two_player_files() {
        let html = get("http://astraplayer.localhost/player/youtube.html");
        assert_eq!(html.status(), StatusCode::OK);
        assert!(html.headers()[header::CONTENT_TYPE].to_str().unwrap().starts_with("text/html"));
        assert_eq!(html.headers()[header::CONTENT_SECURITY_POLICY], PLAYER_CSP);
        assert!(String::from_utf8_lossy(html.body()).contains("youtube-host.js"));

        let js = get("astraplayer://localhost/player/youtube-host.js");
        assert_eq!(js.status(), StatusCode::OK);
        assert!(js.headers()[header::CONTENT_TYPE].to_str().unwrap().starts_with("text/javascript"));
    }

    #[test]
    fn rejects_other_paths_and_methods() {
        for uri in [
            "http://astraplayer.localhost/",
            "http://astraplayer.localhost/index.html",
            "http://astraplayer.localhost/player/../index.html",
            "http://astraplayer.localhost/player/%2e%2e/index.html",
            "http://astraplayer.localhost/player/youtube.html/extra",
        ] {
            assert_eq!(get(uri).status(), StatusCode::NOT_FOUND, "{uri}");
        }
        let post = respond(
            &Request::builder()
                .method(Method::POST)
                .uri("http://astraplayer.localhost/player/youtube.html")
                .body(Vec::new())
                .unwrap(),
        );
        assert_eq!(post.status(), StatusCode::METHOD_NOT_ALLOWED);
    }

    #[test]
    fn player_csp_keeps_scripts_to_self_and_youtube() {
        assert!(PLAYER_CSP.contains("default-src 'none'"));
        assert!(!PLAYER_CSP.contains("unsafe-eval"));
        assert!(!PLAYER_CSP.contains("script-src 'self' 'unsafe-inline'"));
        assert!(PLAYER_CSP.contains("frame-ancestors http://tauri.localhost"));
    }
}
