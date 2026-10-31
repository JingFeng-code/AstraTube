// 從網址判斷來源，讓使用者按「開始」前就知道這個來源能做什麼。實際處理仍由後端決定。
const YOUTUBE_HOSTS = new Set(['youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtu.be'])
const BILIBILI_HOSTS = new Set(['bilibili.com', 'www.bilibili.com', 'm.bilibili.com'])

export function detectSource(url) {
  let parsed
  try { parsed = new URL(String(url || '').trim()) } catch { return null }
  if (!['http:', 'https:'].includes(parsed.protocol)) return null
  const host = parsed.hostname.toLowerCase()
  if (YOUTUBE_HOSTS.has(host)) return 'youtube'
  if (BILIBILI_HOSTS.has(host)) return 'bilibili'
  if (host === 'b23.tv') return 'bilibiliShort'
  return 'article'
}

const SOURCE_HINT_KEYS = {
  youtube: 'input.sourceYoutube',
  bilibili: 'input.sourceBilibili',
  bilibiliShort: 'input.sourceBilibiliShort',
  article: 'input.sourceArticle',
}

export const sourceHintKey = source => SOURCE_HINT_KEYS[source] || null

// 後端沒有字幕時，兩種語言的錯誤訊息都會請使用者匯入 SRT／VTT
export const needsSubtitleImport = error => /SRT/.test(String(error || ''))
