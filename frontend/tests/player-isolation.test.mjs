import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parsePlayerMessage, playerOrigin, playerUrl, randomChannel, seekMessage } from '../src/utils/player-bridge.js'
import { parseParentMessage, readConfig } from '../public/player/youtube-host.js'

const CHANNEL = 'a1b2c3d4e5f60718293a4b5c6d7e8f90'
const VIDEO = 'dQw4w9WgXcQ'
const HOST = 'http://astraplayer.localhost'
const APP = 'http://tauri.localhost'

test('桌面版播放器放在與主視窗不同的來源', () => {
  assert.equal(playerOrigin({ isTauri: true, userAgent: 'Mozilla/5.0 (Windows NT 10.0) Edg/130', origin: APP }), HOST)
  assert.equal(playerOrigin({ isTauri: true, userAgent: 'Macintosh', origin: 'tauri://localhost' }), 'astraplayer://localhost')
  assert.equal(playerOrigin({ isTauri: false, origin: 'http://127.0.0.1:15273' }), 'http://127.0.0.1:15273')
})

test('播放器網址只接受合法影片 ID，頻道放在不會送到網路的 fragment', () => {
  const url = playerUrl({ playerOrigin: HOST, parentOrigin: APP, videoId: VIDEO, channel: CHANNEL })
  assert.equal(url, `${HOST}/player/youtube.html?v=${VIDEO}&parent=http%3A%2F%2Ftauri.localhost#channel=${CHANNEL}`)
  for (const bad of ['', 'short', `${VIDEO}x`, 'javascript:a', '../../etc/x', '<script>abc']) {
    assert.equal(playerUrl({ playerOrigin: HOST, parentOrigin: APP, videoId: bad, channel: CHANNEL }), null, bad)
  }
  assert.match(randomChannel(), /^[0-9a-f]{32}$/)
  assert.notEqual(randomChannel(), randomChannel())
})

test('主視窗只接受來自自己 iframe、正確來源與頻道的訊息', () => {
  const frame = {}
  const expected = { source: frame, origin: HOST, channel: CHANNEL }
  const ok = data => ({ source: frame, origin: HOST, data: { channel: CHANNEL, ...data } })
  assert.deepEqual(parsePlayerMessage(ok({ type: 'ready' }), expected), { type: 'ready' })
  assert.deepEqual(parsePlayerMessage(ok({ type: 'time', seconds: 12.5 }), expected), { type: 'time', seconds: 12.5 })
  assert.deepEqual(parsePlayerMessage(ok({ type: 'error', reason: 'api' }), expected), { type: 'error' })
  // 其他視窗（例如 YouTube 內層 iframe 或惡意 frame）送來的訊息
  assert.equal(parsePlayerMessage({ ...ok({ type: 'time', seconds: 1 }), source: {} }, expected), null)
  assert.equal(parsePlayerMessage({ ...ok({ type: 'time', seconds: 1 }), origin: 'https://www.youtube.com' }, expected), null)
  assert.equal(parsePlayerMessage(ok({ type: 'time', seconds: 1, channel: 'wrong' }), expected), null)
  assert.equal(parsePlayerMessage(ok({ type: 'time', seconds: 1 }), { ...expected, source: null }), null)
  // 內容不合法
  for (const seconds of [NaN, Infinity, -1, 360001, '12', null]) {
    assert.equal(parsePlayerMessage(ok({ type: 'time', seconds }), expected), null, String(seconds))
  }
  for (const type of ['invoke', 'desktop_connection', 'seek', undefined]) {
    assert.equal(parsePlayerMessage(ok({ type }), expected), null, String(type))
  }
  assert.equal(parsePlayerMessage({ source: frame, origin: HOST, data: 'string' }, expected), null)
})

test('跳轉訊息會把秒數夾在合理範圍', () => {
  assert.deepEqual(seekMessage(CHANNEL, 42.5, true), { channel: CHANNEL, type: 'seek', seconds: 42.5, play: true })
  assert.equal(seekMessage(CHANNEL, -3, false).seconds, 0)
  assert.equal(seekMessage(CHANNEL, 1e9, 'yes').seconds, 360000)
  assert.equal(seekMessage(CHANNEL, 'x', 1).play, false)
})

test('宿主頁只接受合法設定', () => {
  const href = `${HOST}/player/youtube.html?v=${VIDEO}&parent=${encodeURIComponent(APP)}#channel=${CHANNEL}`
  assert.deepEqual(readConfig(href), { videoId: VIDEO, parentOrigin: APP, channel: CHANNEL })
  assert.equal(readConfig(href.replace(VIDEO, 'bad')), null)
  assert.equal(readConfig(href.replace(`#channel=${CHANNEL}`, '')), null)
  assert.equal(readConfig(href.replace(encodeURIComponent(APP), 'null')), null)
  assert.equal(readConfig(href.replace(encodeURIComponent(APP), encodeURIComponent(APP + '/path'))), null)
  assert.equal(readConfig(href.replace(encodeURIComponent(APP), encodeURIComponent('javascript:alert(1)'))), null)
  assert.equal(readConfig('not a url'), null)
})

test('宿主頁只接受來自父視窗、正確來源與頻道的 seek 指令', () => {
  const parent = {}
  const expected = { parent, parentOrigin: APP, channel: CHANNEL }
  const ok = data => ({ source: parent, origin: APP, data: { channel: CHANNEL, ...data } })
  assert.deepEqual(parseParentMessage(ok({ type: 'seek', seconds: 30, play: true }), expected), { type: 'seek', seconds: 30, play: true })
  assert.equal(parseParentMessage({ ...ok({ type: 'seek', seconds: 30 }), source: {} }, expected), null)
  assert.equal(parseParentMessage({ ...ok({ type: 'seek', seconds: 30 }), origin: 'https://evil.example' }, expected), null)
  assert.equal(parseParentMessage(ok({ type: 'seek', seconds: 30, channel: 'x' }), expected), null)
  assert.equal(parseParentMessage(ok({ type: 'eval', code: 'alert(1)' }), expected), null)
  assert.equal(parseParentMessage(ok({ type: 'seek', seconds: -1 }), expected), null)
})

test('桌面主視窗 CSP 不再允許任何外部腳本，播放器 iframe 來源已列入 frame-src', () => {
  const config = JSON.parse(readFileSync(new URL('../../desktop/src-tauri/tauri.conf.json', import.meta.url), 'utf8'))
  const directives = Object.fromEntries(config.app.security.csp.split(';').map(part => {
    const [name, ...values] = part.trim().split(/\s+/)
    return [name, values]
  }))
  assert.deepEqual(directives['script-src'], ["'self'"])
  assert.ok(directives['frame-src'].includes('http://astraplayer.localhost'))
  assert.ok(!directives['frame-src'].includes('*'))
  // 能力設定維持最小：網頁沒有 shell／檔案權限，也沒有開放遠端來源
  const capability = JSON.parse(readFileSync(new URL('../../desktop/src-tauri/capabilities/default.json', import.meta.url), 'utf8'))
  assert.deepEqual(capability.permissions, ['core:default'])
  assert.equal(capability.remote, undefined)
})

test('主視窗程式碼不再載入 YouTube iframe_api', () => {
  const source = readFileSync(new URL('../src/components/VideoPane.jsx', import.meta.url), 'utf8')
  assert.ok(!source.includes('iframe_api'))
  assert.ok(!/window\.YT\b/.test(source))
})
