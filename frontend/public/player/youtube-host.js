// YouTube 播放器宿主頁：在獨立來源的 iframe 內載入官方 IFrame Player API。
//
// 為什麼要獨立：Tauri 只把 IPC（window.__TAURI_INTERNALS__ 與 invoke key）注入主框架。
// 若在主視窗直接載入 https://www.youtube.com/iframe_api，YouTube 的第三方腳本就和 React
// 同一個執行環境，能呼叫 invoke('desktop_connection') 取得本機後端 Token。
// 這個頁面放在另一個來源（桌面版為 astraplayer 自訂協定），與主視窗只透過下列
// 已驗證的 postMessage 溝通：
//   主視窗 → 本頁：{channel, type:'seek', seconds, play}
//   本頁 → 主視窗：{channel, type:'ready'} / {channel, type:'time', seconds} / {channel, type:'error', reason}
// 本檔不 import 任何東西，方便直接被 Node 測試載入。

export const YOUTUBE_ID = /^[A-Za-z0-9_-]{11}$/
export const CHANNEL = /^[A-Za-z0-9]{16,64}$/
export const MAX_SECONDS = 360000
const ALLOWED_PARENT_PROTOCOLS = new Set(['http:', 'https:', 'tauri:'])

/** 從本頁網址讀出設定；任何欄位不合法就回傳 null（不嘗試修正）。 */
export function readConfig(href) {
  let url
  try { url = new URL(href) } catch { return null }
  const videoId = url.searchParams.get('v') || ''
  const parentOrigin = url.searchParams.get('parent') || ''
  const channel = new URLSearchParams(url.hash.slice(1)).get('channel') || ''
  if (!YOUTUBE_ID.test(videoId) || !CHANNEL.test(channel)) return null
  let parent
  try { parent = new URL(parentOrigin) } catch { return null }
  // 只接受「純來源」，不接受帶路徑、帳密或 null 的值
  if (!ALLOWED_PARENT_PROTOCOLS.has(parent.protocol) || parent.origin !== parentOrigin) return null
  return { videoId, parentOrigin, channel }
}

/** 驗證主視窗送來的指令；只認得 seek，其餘一律丟棄。 */
export function parseParentMessage(event, expected) {
  if (!event || event.source !== expected.parent || event.origin !== expected.parentOrigin) return null
  const data = event.data
  if (!data || typeof data !== 'object' || data.channel !== expected.channel) return null
  if (data.type !== 'seek') return null
  const seconds = data.seconds
  if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds < 0 || seconds > MAX_SECONDS) return null
  return { type: 'seek', seconds, play: data.play === true }
}

function loadYouTubeApi(win, doc) {
  return new Promise((resolve, reject) => {
    if (win.YT?.Player) { resolve(win.YT); return }
    const timer = win.setTimeout(() => reject(new Error('timeout')), 10000)
    win.onYouTubeIframeAPIReady = () => { win.clearTimeout(timer); resolve(win.YT) }
    const script = doc.createElement('script')
    script.src = 'https://www.youtube.com/iframe_api'
    script.async = true
    script.addEventListener('error', () => { win.clearTimeout(timer); reject(new Error('load')) }, { once: true })
    doc.head.appendChild(script)
  })
}

export function start(win = window) {
  const config = readConfig(win.location.href)
  if (!config || win.parent === win) return
  const send = message => win.parent.postMessage({ ...message, channel: config.channel }, config.parentOrigin)
  let player = null
  let ready = false
  let pending = null

  function apply(command) {
    if (!ready || !player) { pending = command; return }
    player.seekTo(command.seconds, true)
    if (command.play) player.playVideo()
  }

  win.addEventListener('message', event => {
    const command = parseParentMessage(event, { ...config, parent: win.parent })
    if (command) apply(command)
  })

  loadYouTubeApi(win, win.document).then(YT => {
    player = new YT.Player(win.document.getElementById('player'), {
      videoId: config.videoId,
      width: '100%',
      height: '100%',
      playerVars: { playsinline: 1, rel: 0, origin: win.location.origin },
      events: {
        onReady: () => {
          ready = true
          send({ type: 'ready' })
          if (pending) { const next = pending; pending = null; apply(next) }
          win.setInterval(() => {
            const current = player.getCurrentTime?.()
            if (Number.isFinite(current)) send({ type: 'time', seconds: current })
          }, 400)
        },
        onError: () => send({ type: 'error', reason: 'player' }),
      },
    })
  }).catch(() => send({ type: 'error', reason: 'api' }))
}

if (typeof window !== 'undefined' && window.document) start(window)
