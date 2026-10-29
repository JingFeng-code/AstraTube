// 主視窗與隔離播放器（public/player/youtube.html）之間的訊息橋接。
// 安全重點：只接受來自「我們建立的那個 iframe」、正確來源、正確隨機頻道的訊息，
// 而且內容只能是 ready／time／error 三種、數值必須有限且在合理範圍內。

export const YOUTUBE_ID = /^[A-Za-z0-9_-]{11}$/
export const MAX_SECONDS = 360000
const PLAYER_PATH = '/player/youtube.html'

/**
 * 播放器宿主頁的來源。
 * 桌面版放在 astraplayer 自訂協定（與主視窗不同來源，且 Tauri 不注入 IPC）；
 * Windows 上 Tauri 自訂協定的網址是 http://<名稱>.localhost，其他平台是 <名稱>://localhost。
 * Web／Codespaces 沒有 IPC 可保護，使用同源的靜態頁。
 */
export function playerOrigin({ isTauri, userAgent = '', origin }) {
  if (!isTauri) return origin
  return /Windows/i.test(userAgent) ? 'http://astraplayer.localhost' : 'astraplayer://localhost'
}

export function randomChannel(cryptoObject = globalThis.crypto) {
  const bytes = new Uint8Array(16)
  cryptoObject.getRandomValues(bytes)
  return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('')
}

/** 組出 iframe 網址；影片 ID 不合法時回傳 null，不讓任意字串進入網址。 */
export function playerUrl({ playerOrigin: hostOrigin, parentOrigin, videoId, channel }) {
  if (!YOUTUBE_ID.test(videoId || '')) return null
  const query = new URLSearchParams({ v: videoId, parent: parentOrigin })
  return `${hostOrigin}${PLAYER_PATH}?${query}#channel=${encodeURIComponent(channel)}`
}

/** 驗證播放器送來的訊息；不符合任何條件就回傳 null。 */
export function parsePlayerMessage(event, expected) {
  if (!event || !expected.source || event.source !== expected.source) return null
  if (event.origin !== expected.origin) return null
  const data = event.data
  if (!data || typeof data !== 'object' || data.channel !== expected.channel) return null
  if (data.type === 'ready') return { type: 'ready' }
  if (data.type === 'error') return { type: 'error' }
  if (data.type === 'time') {
    const seconds = data.seconds
    if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds < 0 || seconds > MAX_SECONDS) return null
    return { type: 'time', seconds }
  }
  return null
}

export function seekMessage(channel, seconds, play) {
  const safe = Math.min(MAX_SECONDS, Math.max(0, Number(seconds) || 0))
  return { channel, type: 'seek', seconds: safe, play: play === true }
}
