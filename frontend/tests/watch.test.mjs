import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { formatClock, playerRegion, watchTarget } from '../src/utils/watch.js'
import { STRINGS } from '../src/i18n/strings.js'

const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')

test('只接受 YouTube 和 Bilibili 官方影片網址', () => {
  assert.deepEqual(watchTarget('https://www.youtube.com/watch?v=xslkY2Voy0A'), { platform: 'youtube', videoId: 'xslkY2Voy0A', page: 1 })
  assert.deepEqual(watchTarget('https://youtu.be/xslkY2Voy0A?t=3'), { platform: 'youtube', videoId: 'xslkY2Voy0A', page: 1 })
  assert.deepEqual(watchTarget('https://www.bilibili.com/video/BV1jhns6DEzi/?p=2'), { platform: 'bilibili', videoId: 'BV1jhns6DEzi', page: 2 })
  for (const url of ['http://www.youtube.com/watch?v=xslkY2Voy0A', 'https://evil-youtube.com/watch?v=xslkY2Voy0A',
    'https://www.youtube.com/watch?v=short', 'https://www.bilibili.com/video/BV1jhns6DEzi/?p=0', 'https://b23.tv/x', '', null]) {
    assert.equal(watchTarget(url), null, String(url))
  }
})

test('播放器位置換成實際像素用的資料', () => {
  const element = { getBoundingClientRect: () => ({ left: 12.4, top: -3, width: 640.6, height: 360.2 }) }
  assert.deepEqual(playerRegion(element, 1.5), { x: 12, y: 0, width: 641, height: 360, dpr: 1.5 })
})

test('時間格式', () => {
  assert.equal(formatClock(0), '0:00')
  assert.equal(formatClock(75.9), '1:15')
  assert.equal(formatClock(3725), '1:02:05')
})

test('陪看模式只在可用時出現，結束後沿用既有分析流程', () => {
  const app = read('../src/App.jsx')
  assert.match(app, /const watchVideo=!isLocalMode&&watchAvailable\?watchTarget\(url\):null/)
  assert.match(app, /function finishWatching\(\)\{setWatching\(false\);startAnalysis\(false\)\}/)
  const component = read('../src/components/WatchAlong.jsx')
  // 模型要使用者按下才下載；陪看本身不碰雲端供應商
  assert.match(component, /onClick=\{downloadModel\}/)
  // 換影片或關掉陪看時要停止背景擷取
  assert.match(component, /return \(\) => \{[\s\S]*?if \(runningRef\.current\) cancelWatch\(\)/)
  assert.doesNotMatch(component, /gemini|openai|anthropic/i)
  for (const table of Object.values(STRINGS)) {
    for (const key of ['watch.title', 'watch.close', 'watch.cancel', 'watch.checking', 'watch.unavailable', 'watch.needSpeech',
      'watch.start', 'watch.finish', 'watch.finishing', 'watch.intro', 'watch.playHint', 'watch.noVisionModel',
      'watch.framesStalled', 'watch.framesUnavailable', 'watch.visionFailed', 'watch.offer', 'watch.open',
      'watch.optionButton', 'watch.subtitleSource', 'source.watchAlong']) {
      assert.equal(typeof table[key], 'string', key)
    }
    assert.match(table['watch.recording']('1:00', 3, 2), /1:00/)
    assert.match(table['watch.visionModel']('qwen'), /qwen/)
  }
  assert.match(STRINGS.zh['watch.intro'], /不會下載影片/)
  // 可以陪看時，沒有字幕檔的提示要指向陪看，不能說「目前無法分析」
  assert.match(app, /noFileHint=\{watchVideo\?t\('subtitles\.importNoFileWatch'\)/)
  for (const table of Object.values(STRINGS)) assert.equal(typeof table['subtitles.importNoFileWatch'], 'string')
  assert.match(STRINGS.zh['subtitles.importNoFileWatch'], /陪看模式/)
})
