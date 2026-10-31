import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { STRINGS } from '../src/i18n/strings.js'
import { NARROW_QUERY, effectiveResultTab, resultTabs } from '../src/utils/result-tabs.js'

const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')

test('單欄才有重點分頁，寬螢幕的重點固定在右欄', () => {
  assert.deepEqual(resultTabs(true), ['cards', 'subtitles', 'chapters'])
  assert.deepEqual(resultTabs(false), ['subtitles', 'chapters'])
})

test('跨過斷點時，不存在的分頁會退回第一個分頁', () => {
  assert.equal(effectiveResultTab('cards', false), 'subtitles')
  assert.equal(effectiveResultTab('cards', true), 'cards')
  assert.equal(effectiveResultTab('chapters', false), 'chapters')
  assert.equal(effectiveResultTab('chapters', true), 'chapters')
  assert.equal(effectiveResultTab('unknown', true), 'cards')
})

test('JavaScript 與樣式表使用同一個單欄斷點', () => {
  assert.equal(NARROW_QUERY, '(max-width:980px)')
  assert.match(read('../src/index.css'), /@media\(max-width:980px\)\{\s*\.workspace\{grid-template-columns:minmax\(0,1fr\)/)
})

test('切換分頁不會卸載或隱藏播放器', () => {
  const pane = read('../src/components/VideoPane.jsx')
  const frame = pane.match(/<div className="video-frame"[^>]*>/)
  assert.ok(frame)
  assert.doesNotMatch(frame[0], /hidden/)
  // 字幕翻譯迴圈在元件卸載時會停止，所以分頁只用 hidden 切換內容
  assert.match(pane, /className="subtitles-panel" hidden=\{tab!=='subtitles'\}/)
  assert.match(pane, /className="chapters" hidden=\{tab!=='chapters'\}/)
})

test('兩種語言都有分頁文字', () => {
  for (const [lang, table] of Object.entries(STRINGS)) {
    for (const key of ['result.tabs', 'result.tab.cards', 'result.tab.subtitles', 'result.tab.chapters']) {
      assert.ok(table[key], `${lang}:${key}`)
    }
  }
})
