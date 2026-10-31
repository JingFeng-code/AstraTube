import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { isVideoFile, localVideoId, localVideoUrl, speechPercent } from '../src/utils/local-video.js'
import { STRINGS } from '../src/i18n/strings.js'

const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')

test('進度百分比不會超出範圍', () => {
  assert.equal(speechPercent(0, 0), 0)
  assert.equal(speechPercent(50, 200), 25)
  assert.equal(speechPercent(0.999, 1), 99)
  assert.equal(speechPercent(5, 1), 100)
  assert.equal(speechPercent(-1, 1), 0)
})

test('語音模型要使用者按下才下載，兩種語言都有說明', () => {
  const controls = read('../src/components/LocalSpeechControls.jsx')
  assert.match(controls, /onClick=\{downloadModel\}/)
  assert.doesNotMatch(controls.match(/useEffect\(\(\) => \{\s*aliveRef[\s\S]*?\}, \[\]\)/)[0], /startSpeechModelDownload/)
  assert.match(read('../src/api.js'), /X-Astra-Desktop-Token', desktop\.token/)
  for (const table of Object.values(STRINGS)) {
    for (const key of ['local.speechAction', 'local.speechHint', 'local.speechRepick', 'local.speechDownload', 'local.speechDownloadHint', 'local.speechSource', 'local.speechNoEngine', 'local.speechRemote', 'source.localSpeech']) {
      assert.equal(typeof table[key], 'string', key)
    }
    assert.match(table['local.speechDownloading'](7), /7%/)
    assert.match(table['local.speechPresent'](3), /3/)
  }
})

test('只接受影片檔', () => {
  assert.equal(isVideoFile({ type: 'video/mp4', name: 'a.mp4' }), true)
  assert.equal(isVideoFile({ type: '', name: 'lesson.MKV' }), true)
  assert.equal(isVideoFile({ type: 'text/plain', name: 'a.srt' }), false)
  assert.equal(isVideoFile({ type: '', name: 'a.mp4.exe' }), false)
  assert.equal(isVideoFile(null), false)
})

test('識別碼符合後端格式，改名不變，內容不同就不同', async () => {
  const content = new Uint8Array(200 * 1024).fill(7)
  const id = await localVideoId(new File([content], 'first.mp4'))
  assert.match(id, /^[0-9a-f]{16}$/)
  assert.match(localVideoUrl(id), /^local:\/\/[0-9a-f]{16}$/)
  assert.equal(await localVideoId(new File([content], 'renamed.mp4')), id)
  const tail = content.slice()
  tail[tail.length - 1] = 8
  assert.notEqual(await localVideoId(new File([tail], 'first.mp4')), id)
  assert.notEqual(await localVideoId(new File([content.slice(1)], 'first.mp4')), id)
})
