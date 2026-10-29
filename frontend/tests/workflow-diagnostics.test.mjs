import test from 'node:test'
import assert from 'node:assert/strict'
import { effectiveDeepVisual, isBilibiliUrl } from '../src/utils/user-mode.js'
import { STRINGS } from '../src/i18n/strings.js'

test('Bilibili 網址一律不送出讀畫面（Issue #19 案例 B）', () => {
  for (const url of ['https://www.bilibili.com/video/BV1WQHP66EPS/?trackid=web', 'https://m.bilibili.com/video/BV1WQHP66EPS', 'https://b23.tv/abc']) {
    assert.equal(isBilibiliUrl(url), true, url)
    assert.equal(effectiveDeepVisual(true, true, url), false, url)
  }
  for (const url of ['https://www.youtube.com/watch?v=Y5UobXTOZEY', 'https://bilibili.com.evil.example/video/BV1', 'not a url', '']) {
    assert.equal(isBilibiliUrl(url), false, url)
  }
  assert.equal(effectiveDeepVisual(true, true, 'https://www.youtube.com/watch?v=Y5UobXTOZEY'), true)
  assert.equal(effectiveDeepVisual(false, true, 'https://www.youtube.com/watch?v=Y5UobXTOZEY'), false)
})

test('段落失敗提示會附上真正原因，兩種語言都有新字串', () => {
  for (const lang of Object.keys(STRINGS)) {
    const strings = STRINGS[lang]
    const toast = strings['toast.segFailed'](1, 'OpenCode HTTP 429')
    assert.match(toast, /1/)
    assert.match(toast, /OpenCode HTTP 429/)
    assert.doesNotMatch(strings['toast.segFailed'](2, ''), /undefined/)
    assert.ok(strings['input.deepVisualBilibili'], lang)
    assert.ok(strings['input.deepVisualBilibiliShort'], lang)
  }
})
