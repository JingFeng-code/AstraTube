// 深視覺屬明確的額外功能，不以開發者身分限制。
const BILIBILI_HOSTS = new Set(['www.bilibili.com', 'm.bilibili.com', 'bilibili.com', 'b23.tv'])
export function isBilibiliUrl(url) {
  try { return BILIBILI_HOSTS.has(new URL(String(url || '').trim()).hostname.toLowerCase()) } catch { return false }
}
export function effectiveDeepVisual(enabled, url = '') {
  return Boolean(enabled && !isBilibiliUrl(url))
}
// 換新鍵：舊鍵 ycr-deep-visual 是開發者模式時期留下的，選項被收進進階分析後使用者看不到，
// 不能讓它繼續生效，否則選 Ollama 時影片仍可能被送到 Gemini。
export const DEEP_VISUAL_KEY = 'astratube-deep-visual'
// 讀畫面實際會發生什麼：'gemini'＝影片會送到 Gemini；'no-key'＝沒有金鑰，只會用字幕；null＝未開啟。
export function deepVisualNotice(enabled, url, geminiConfigured) {
  if (!effectiveDeepVisual(enabled, url)) return null
  return geminiConfigured ? 'gemini' : 'no-key'
}
