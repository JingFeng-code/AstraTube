// 使用者模式只控制介面可見性，不是 API 授權機制。
export const DEFAULT_FREE_PROVIDER = 'opencode:deepseek-v4-flash-free'

export function isDeveloperModeSetting(value) {
  return value === '1'
}

export function effectiveProvider(developerMode, selectedProvider) {
  return developerMode ? (selectedProvider || DEFAULT_FREE_PROVIDER) : DEFAULT_FREE_PROVIDER
}

// Bilibili 官方網域（與後端 transcript/bilibili.py 的判斷一致）
const BILIBILI_HOSTS = new Set(['www.bilibili.com', 'm.bilibili.com', 'bilibili.com', 'b23.tv'])

export function isBilibiliUrl(url) {
  try { return BILIBILI_HOSTS.has(new URL(String(url || '').trim()).hostname.toLowerCase()) } catch { return false }
}

// 讀畫面（Gemini 深視覺）目前只支援 YouTube；Bilibili 網址一律不送出，後端也會再擋一次。
export function effectiveDeepVisual(developerMode, enabled, url = '') {
  return Boolean(developerMode && enabled && !isBilibiliUrl(url))
}
