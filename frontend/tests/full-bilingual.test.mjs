import test from 'node:test'
import assert from 'node:assert/strict'
import { DEFAULT_SUBTITLE_MODE, SUBTITLE_MODES, nextBatchStart, normalizeSubtitleMode, overlayLines } from '../src/utils/subtitles.js'
import { STRINGS } from '../src/i18n/strings.js'

const cue = (text, translation = null) => ({ start: 0, end: 1, text, translation })

test('播放器字幕依模式顯示，未翻譯時不會整行消失', () => {
  const done = cue('Hello', '你好')
  const pending = cue('World')
  assert.deepEqual(overlayLines(done, 'off'), [])
  assert.deepEqual(overlayLines(done, 'original'), [{ kind: 'original', text: 'Hello' }])
  assert.deepEqual(overlayLines(done, 'zh'), [{ kind: 'translation', text: '你好' }])
  assert.deepEqual(overlayLines(done, 'bilingual'), [{ kind: 'translation', text: '你好' }, { kind: 'original', text: 'Hello' }])
  assert.deepEqual(overlayLines(pending, 'zh'), [{ kind: 'pending', text: 'World' }])
  assert.deepEqual(overlayLines(pending, 'bilingual'), [{ kind: 'original', text: 'World' }])
  assert.deepEqual(overlayLines(null, 'bilingual'), [])
})

test('不認得的模式回到預設雙語', () => {
  assert.equal(normalizeSubtitleMode('zh'), 'zh')
  for (const bad of [null, '', 'chinese', undefined]) assert.equal(normalizeSubtitleMode(bad), DEFAULT_SUBTITLE_MODE)
})

test('整片翻譯從目前播放位置往後優先，後面完成才回頭補前面', () => {
  const cues = [cue('a'), cue('b', 'B'), cue('c'), cue('d', 'D'), cue('e')]
  assert.equal(nextBatchStart(cues, 0), 0)
  assert.equal(nextBatchStart(cues, 3), 4)
  assert.equal(nextBatchStart(cues, 99), 4)
  const tail = [cue('a'), cue('b', 'B'), cue('c', 'C')]
  assert.equal(nextBatchStart(tail, 1), 0, '後面都翻好了要回頭補')
  assert.equal(nextBatchStart([cue('a', 'A')], 0), -1)
  assert.equal(nextBatchStart([], 0), -1)
  assert.equal(nextBatchStart(null, 0), -1)
})

test('新增的字幕介面文字兩種語言都有', () => {
  for (const lang of Object.keys(STRINGS)) {
    const s = STRINGS[lang]
    for (const mode of SUBTITLE_MODES) assert.ok(s[`subtitles.mode.${mode}`], `${lang} ${mode}`)
    for (const key of ['subtitles.pause', 'subtitles.modeLabel']) assert.ok(s[key], `${lang} ${key}`)
    assert.match(s['subtitles.translateAll'](120), /120/)
    assert.match(s['subtitles.translateResume'](8), /8/)
    assert.match(s['subtitles.translatingAll'](3, 9), /3\/9/)
  }
})
