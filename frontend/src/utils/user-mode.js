// 深視覺屬明確的額外功能，不以開發者身分限制。
const BILIBILI_HOSTS = new Set(['www.bilibili.com', 'm.bilibili.com', 'bilibili.com', 'b23.tv'])
export function isBilibiliUrl(url) {
  try { return BILIBILI_HOSTS.has(new URL(String(url || '').trim()).hostname.toLowerCase()) } catch { return false }
}
export function effectiveDeepVisual(enabled, url = '') {
  return Boolean(enabled && !isBilibiliUrl(url))
}
