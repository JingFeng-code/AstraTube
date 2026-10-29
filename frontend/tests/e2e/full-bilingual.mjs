// 整片雙語字幕的瀏覽器端到端檢查（不在 npm test 內，需要 Playwright 與 Chromium，不連外部網站）。
//
//   npm run build && npx vite preview --port 15276 --strictPort &
//   node tests/e2e/full-bilingual.mjs http://127.0.0.1:15276
//
// 以 Playwright 攔截 /api 與 YouTube iframe_api：字幕 40 句、翻譯 API 第二批第一次回 502（模擬限流），
// 驗證整片翻譯迴圈、從播放位置開始、失敗顯示原因後可繼續、播放器字幕四種模式與偏好記憶。
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const { chromium } = require('playwright')
const base = process.argv[2] || 'http://127.0.0.1:15276'
const VIDEO = 'dQw4w9WgXcQ'
const cues = Array.from({ length: 40 }, (_, i) => ({ start: i * 5, end: i * 5 + 4.5, text: `Line ${i}`, translation: null }))
const session = { result: { source_type: 'youtube', youtube_video_id: VIDEO, title: 'E2E', cards: [] } }
const FAKE_YT = `window.YT={Player:class{constructor(e,o){window.__p=this;this.t=0;setTimeout(()=>o.events.onReady({}),30)}
  getCurrentTime(){return this.t}seekTo(s){this.t=s}playVideo(){}}};onYouTubeIframeAPIReady()`

const translateCalls = []
let failedOnce = false
const browser = await chromium.launch()
const context = await browser.newContext()
await context.addInitScript(`try{if(!sessionStorage.getItem('seeded')){localStorage.setItem('ycr-session-v1',${JSON.stringify(JSON.stringify(session))});sessionStorage.setItem('seeded','1')}}catch{}`)
await context.route('**/*', async route => {
  const url = new URL(route.request().url())
  if (url.pathname === '/api/subtitles') {
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ source: 'platform', cues, timing_precision: 'seconds_estimated', translated_count: 0 }) })
  }
  if (url.pathname === '/api/subtitles/translate') {
    const body = route.request().postDataJSON()
    translateCalls.push(body.start_index)
    if (translateCalls.length === 2 && !failedOnce) {
      failedOnce = true
      return route.fulfill({ status: 502, contentType: 'application/json', body: JSON.stringify({ detail: '免費字幕翻譯服務暫時無法使用（OpenCode HTTP 429：rate limited），請檢查連線或模型設定。' }) })
    }
    const ids = cues.map((_, i) => i).filter(i => i >= body.start_index && i < body.start_index + body.batch_size)
    await new Promise(r => setTimeout(r, 400))
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ translations: ids.map(id => ({ id, translation: `第 ${id} 行` })), next_index: ids.at(-1) + 1, total: cues.length }) })
  }
  if (url.pathname.startsWith('/api/')) return route.fulfill({ contentType: 'application/json', body: '{}' })
  if (url.href.startsWith('https://www.youtube.com/iframe_api')) return route.fulfill({ contentType: 'text/javascript', body: FAKE_YT })
  if (url.hostname === '127.0.0.1') return route.continue()
  return route.fulfill({ status: 404, body: '' })
})

const page = await context.newPage()
await page.goto(base)
await page.waitForSelector('.subtitle-cue')
const host = () => page.frames().find(f => f.url().includes('/player/youtube.html'))
await page.waitForFunction(() => true)
await new Promise(r => setTimeout(r, 600))
const report = {}

// 播放到第 21 句（105 秒）後才開始翻譯：第一批應從 21 開始
await host().evaluate(() => { window.__p.t = 106 })
await new Promise(r => setTimeout(r, 900))
report.overlayBeforeTranslate = await page.locator('.subtitle-overlay').innerText().catch(() => null)
await page.getByRole('button', { name: /翻譯整支影片|Translate all/ }).click()
await page.waitForSelector('.subtitles-hint[role=alert]', { timeout: 10000 })
report.errorShown = await page.locator('.subtitles-hint[role=alert]').innerText()
report.resumeButton = await page.locator('.subtitles-controls .btn-paper').innerText()
// 繼續翻譯後立刻暫停：目前這批完成後就停，不會跑完整支
await page.locator('.subtitles-controls .btn-paper').click()
await page.waitForFunction(() => /暫停|Pause/.test(document.querySelector('.subtitles-controls .btn-paper')?.textContent || ''))
await page.locator('.subtitles-controls .btn-paper').click()
await new Promise(r => setTimeout(r, 1500))
report.afterPause = { calls: translateCalls.length, button: await page.locator('.subtitles-controls .btn-paper').innerText() }
await page.locator('.subtitles-controls .btn-paper').click()
await page.waitForFunction(() => /全部|All lines/.test(document.querySelector('.subtitles-controls .btn-paper')?.textContent || ''), null, { timeout: 15000 })
report.translateCalls = translateCalls
report.progress = await page.locator('.subtitles-head span').innerText()
report.overlayBilingual = await page.locator('.subtitle-overlay').innerText()
report.overlayPassesClicks = await page.evaluate(() => getComputedStyle(document.querySelector('.subtitle-overlay')).pointerEvents === 'none')
await page.getByRole('button', { name: '中文', exact: true }).click()
report.overlayZh = await page.locator('.subtitle-overlay').innerText()
await page.getByRole('button', { name: '原文', exact: true }).click()
report.overlayOriginal = await page.locator('.subtitle-overlay').innerText()
await page.getByRole('button', { name: '無', exact: true }).click()
report.overlayOffCount = await page.locator('.subtitle-overlay').count()
await page.reload()
await page.waitForSelector('.subtitle-mode')
report.modeAfterReload = await page.locator('.subtitle-mode button[aria-pressed=true]').innerText()
console.log(JSON.stringify(report, null, 2))
await browser.close()
