// 陪看模式的小工具：從網址找出影片、計算播放器在視窗裡的位置。
const YOUTUBE_HOSTS = new Set(['youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be'])
const BILIBILI_HOSTS = new Set(['bilibili.com', 'www.bilibili.com', 'm.bilibili.com'])
const YOUTUBE_ID = /^[A-Za-z0-9_-]{11}$/
const BVID = /^BV[0-9A-Za-z]{10}$/

export function watchTarget(url) {
  let parsed
  try { parsed = new URL(String(url || '').trim()) } catch { return null }
  if (parsed.protocol !== 'https:') return null
  const host = parsed.hostname.toLowerCase()
  if (YOUTUBE_HOSTS.has(host)) {
    const id = host === 'youtu.be' ? parsed.pathname.slice(1).split('/')[0]
      : parsed.pathname === '/watch' ? parsed.searchParams.get('v')
      : (parsed.pathname.match(/^\/(?:shorts|embed|live)\/([^/]+)/) || [])[1]
    return YOUTUBE_ID.test(id || '') ? { platform: 'youtube', videoId: id, page: 1 } : null
  }
  if (BILIBILI_HOSTS.has(host)) {
    const id = (parsed.pathname.match(/^\/video\/([^/]+)/) || [])[1]
    const page = Number(parsed.searchParams.get('p') || 1)
    return BVID.test(id || '') && Number.isInteger(page) && page >= 1 && page <= 1000
      ? { platform: 'bilibili', videoId: id, page } : null
  }
  return null
}

// 後端用實際像素裁切擷取畫面：CSS 像素要乘上縮放比例
export function playerRegion(element, ratio = window.devicePixelRatio || 1) {
  const rect = element.getBoundingClientRect()
  return {
    x: Math.max(0, Math.round(rect.left)), y: Math.max(0, Math.round(rect.top)),
    width: Math.max(1, Math.round(rect.width)), height: Math.max(1, Math.round(rect.height)),
    dpr: ratio,
  }
}

export function formatClock(seconds) {
  const total = Math.max(0, Math.floor(seconds || 0))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor(total % 3600 / 60)
  const rest = String(total % 60).padStart(2, '0')
  return hours ? `${hours}:${String(minutes).padStart(2, '0')}:${rest}` : `${minutes}:${rest}`
}
