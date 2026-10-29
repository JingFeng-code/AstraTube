import test from 'node:test'
import assert from 'node:assert/strict'
import {DEFAULT_FREE_PROVIDER, isDeveloperModeSetting, effectiveProvider, effectiveDeepVisual} from '../src/utils/user-mode.js'
import {createNoteMarkdown, markdownFilename} from '../src/utils/notes-export.js'

test('一般模式為預設、明確選擇後才會顯示開發者模式', () => {
  assert.equal(isDeveloperModeSetting(null), false)
  assert.equal(isDeveloperModeSetting('0'), false)
  assert.equal(isDeveloperModeSetting('1'), true)
})

test('一般模式不會沿用開發者付費 Provider 或深視覺設定', () => {
  assert.equal(effectiveProvider(false, 'openai:paid-model'), DEFAULT_FREE_PROVIDER)
  assert.equal(effectiveDeepVisual(false, true), false)
  assert.equal(effectiveProvider(true, 'openai:paid-model'), 'openai:paid-model')
  assert.equal(effectiveDeepVisual(true, true), true)
})

test('無須 Obsidian 即可產出包含影片來源與註記的 Markdown', () => {
  const text = createNoteMarkdown({
    title: '我的學習筆記',
    sourceUrl: 'https://www.bilibili.com/video/BV1B7411m7LV/',
    clips: [{heading:'知識點',summary:'需要記住的內容',ts:63,transcript:'Hello',note:'稍後練習'}],
    freeNote: '學習心得',
  })
  assert.match(text, /# 我的學習筆記/)
  assert.match(text, /1:03/)
  assert.match(text, /Hello/)
  assert.match(text, /稍後練習/)
  assert.match(text, /學習心得/)
  assert.equal(markdownFilename('非法/路徑:*?'), '非法-路徑---.md')
})
