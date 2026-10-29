// 模擬 Tauri 桌面環境的瀏覽器端到端檢查（不在 npm test 內，需要 Playwright 與 Chromium）。
//
//   node tests/e2e/desktop-player-isolation.mjs <frontend dist 目錄> <tauri.conf.json> [player.rs]
//
// 做法：以 Playwright 攔截網路，把 dist 當作 http://tauri.localhost、把播放器宿主頁當作
// http://astraplayer.localhost 提供，並套用與桌面版相同的 CSP；只在主框架注入假的
// __TAURI_INTERNALS__（與 Tauri 只注入主框架的行為一致）。YouTube iframe_api 以假腳本取代，
// 該腳本會嘗試呼叫 invoke('desktop_connection')，用來證明第三方腳本能否拿到 Token。
// 這不是 Windows／WebView2 實機測試，只驗證瀏覽器層級的來源隔離與訊息流程。
import { readFileSync, existsSync } from 'node:fs'
import { extname, join, normalize } from 'node:path'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const { chromium } = require('playwright')

const [distDir, confPath, playerRsPath] = process.argv.slice(2)
if (!distDir || !confPath) {
  console.error('usage: desktop-player-isolation.mjs <dist> <tauri.conf.json> [player.rs]')
  process.exit(2)
}
const mainCsp = JSON.parse(readFileSync(confPath, 'utf8')).app.security.csp
const playerCsp = playerRsPath && existsSync(playerRsPath)
  ? readFileSync(playerRsPath, 'utf8').match(/PLAYER_CSP: &str = "([\s\S]*?)";/)[1].replace(/\\\n/g, '')
  : null
const VIDEO = 'dQw4w9WgXcQ'
const TOKEN = 'T'.repeat(64)
const PORT = 18555
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png' }

function serveFile(route, root, path, csp) {
  const file = normalize(join(root, path === '/' ? 'index.html' : path))
  if (!file.startsWith(normalize(root)) || !existsSync(file)) return route.fulfill({ status: 404, body: '' })
  const headers = { 'content-type': TYPES[extname(file)] || 'application/octet-stream' }
  if (csp && extname(file) === '.html') headers['content-security-policy'] = csp
  return route.fulfill({ status: 200, headers, body: readFileSync(file) })
}

// 假的 YouTube API：模擬播放器，並示範「惡意第三方腳本」會做的事
const FAKE_YT = `
  window.__thirdParty = { ran: true, sawIpc: !!window.__TAURI_INTERNALS__, stolen: null }
  if (window.__TAURI_INTERNALS__) {
    window.__TAURI_INTERNALS__.invoke('desktop_connection').then(r => { window.__thirdParty.stolen = r.token })
  }
  window.__seeks = []
  window.YT = { Player: class {
    constructor(el, opts) { this.t = 0; window.__player = this
      const f = document.createElement('div'); f.id = 'fake-yt'; (typeof el === 'string' ? document.getElementById(el) : el).replaceWith(f)
      setTimeout(() => opts.events.onReady({ target: this }), 50) }
    getCurrentTime() { return this.t }
    seekTo(s) { this.t = s; window.__seeks.push(s) }
    playVideo() {} destroy() {} } }
  window.onYouTubeIframeAPIReady && window.onYouTubeIframeAPIReady()
`

const FAKE_IPC = `
  if (window.top === window && location.hostname === 'tauri.localhost') {
    window.__ipcCalls = []
    const invoke = async (cmd) => { window.__ipcCalls.push(cmd); if (cmd === 'desktop_connection') return { port: ${PORT}, token: '${TOKEN}' }; throw new Error('denied') }
    Object.defineProperty(window, '__TAURI_INTERNALS__', { value: { invoke } })
    window.__TAURI__ = { core: { invoke } }
  }
`

const session = { url: `https://www.youtube.com/watch?v=${VIDEO}`, provider: 'opencode:deepseek-v4-flash-free',
  result: { source_type: 'youtube', youtube_video_id: VIDEO, title: 'E2E', source_url: `https://www.youtube.com/watch?v=${VIDEO}`,
    cards: [{ heading: '第一張', summary: 's', timestamp_seconds: 5 }] } }
const cues = [{ start: 0, end: 4, text: '第一句', translation: null }, { start: 5, end: 9, text: '第二句', translation: null },
  { start: 10, end: 14, text: '第三句', translation: null }]

const browser = await chromium.launch()
// 目標平台是 Windows WebView2：Tauri 自訂協定在 Windows 上是 http://<名稱>.localhost
const context = await browser.newContext({ userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36 Edg/130.0' })
await context.addInitScript(FAKE_IPC)
await context.addInitScript(`try { if (location.hostname === 'tauri.localhost') localStorage.setItem('ycr-session-v1', ${JSON.stringify(JSON.stringify(session))}) } catch {}`)
await context.route('**/*', route => {
  const url = new URL(route.request().url())
  if (url.hostname === 'tauri.localhost') return serveFile(route, distDir, url.pathname, mainCsp)
  if (url.hostname === 'astraplayer.localhost') {
    if (!url.pathname.startsWith('/player/')) return route.fulfill({ status: 404, body: '' })
    return serveFile(route, distDir, url.pathname, playerCsp)
  }
  if (url.href.startsWith('https://www.youtube.com/iframe_api')) return route.fulfill({ status: 200, contentType: 'text/javascript', body: FAKE_YT })
  if (url.hostname === '127.0.0.1' && url.port === String(PORT)) {
    const ok = route.request().headers()['x-astra-desktop-token'] === TOKEN
    const headers = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*' }
    if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers })
    if (!ok) return route.fulfill({ status: 403, headers, body: '{}' })
    const body = url.pathname === '/health' ? { status: 'ok' }
      : url.pathname === '/subtitles' ? { source: 'platform', cues, timing_precision: 'seconds_estimated', translated_count: 0 }
      : url.pathname === '/settings' ? { configured: true } : {}
    return route.fulfill({ status: 200, headers, contentType: 'application/json', body: JSON.stringify(body) })
  }
  return route.fulfill({ status: 404, body: '' })  // 其他外部網路一律不連
})

const page = await context.newPage()
const cspErrors = []
page.on('console', msg => { if (/Content Security Policy|Refused/i.test(msg.text())) cspErrors.push(msg.text()) })
await page.goto('http://tauri.localhost/')
await page.waitForSelector('.subtitle-cue', { timeout: 20000 })
await page.waitForTimeout(1500)

const frames = page.frames()
const report = { mainThirdParty: await page.evaluate(() => window.__thirdParty || null),
  mainHasYouTubeScript: await page.evaluate(() => !!document.querySelector('script[src*="youtube.com"]')),
  playerFrames: [] }
for (const frame of frames) {
  if (frame === page.mainFrame()) continue
  const info = await frame.evaluate(() => ({ origin: location.origin, ipc: !!window.__TAURI_INTERNALS__,
    thirdParty: window.__thirdParty || null,
    parentReadable: (() => { try { return !!window.parent.document } catch { return false } })() })).catch(e => ({ error: String(e) }))
  report.playerFrames.push(info)
}
const host = frames.find(f => f.url().startsWith('http://astraplayer.localhost/'))
if (host) {
  // 播放到第 6 秒，主視窗應高亮「第二句」
  await host.evaluate(() => { window.__player.t = 6 })
  await page.waitForTimeout(900)
  report.activeCue = await page.evaluate(() => document.querySelector('.subtitle-cue.active')?.textContent || null)
  // 點擊「第三句」，宿主頁應收到 seekTo(10)
  await page.locator('.subtitle-cue', { hasText: '第三句' }).click()
  await page.waitForTimeout(500)
  report.hostSeeks = await host.evaluate(() => window.__seeks)
  // 偽造訊息：先讓播放器停止回報（getCurrentTime 回 NaN），再由主視窗自己與另一個 frame
  // 送出 time=1 的訊息；若被接受，高亮會跳回「第一句」
  await host.evaluate(() => { window.__player.getCurrentTime = () => NaN })
  await page.waitForTimeout(500)
  await page.evaluate(() => window.postMessage({ type: 'time', seconds: 1, channel: 'guess' }, '*'))
  // 播放器 frame 內的第三方腳本：猜錯頻道、或送出不合法的數值
  await host.evaluate(() => {
    const channel = new URLSearchParams(location.hash.slice(1)).get('channel')
    parent.postMessage({ type: 'time', seconds: 1, channel: 'wrong' }, '*')
    parent.postMessage({ type: 'time', seconds: -5, channel }, '*')
    parent.postMessage({ type: 'invoke', cmd: 'desktop_connection', channel }, '*')
  })
  await page.waitForTimeout(900)
  report.activeCueAfterForgery = await page.evaluate(() => document.querySelector('.subtitle-cue.active')?.textContent || null)
  // 對照組：同一個 frame 送出正確頻道的合法訊息，高亮應改變（證明上面的檢查真的有效）
  await host.evaluate(() => {
    const channel = new URLSearchParams(location.hash.slice(1)).get('channel')
    parent.postMessage({ type: 'time', seconds: 1, channel }, new URLSearchParams(location.search).get('parent'))
  })
  await page.waitForTimeout(500)
  report.activeCueAfterValidControl = await page.evaluate(() => document.querySelector('.subtitle-cue.active')?.textContent || null)
}
report.ipcCalls = await page.evaluate(() => window.__ipcCalls)
report.cspErrors = cspErrors
console.log(JSON.stringify(report, null, 2))
await browser.close()
