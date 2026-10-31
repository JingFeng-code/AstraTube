import test from 'node:test'
import assert from 'node:assert/strict'
import { isVideoFile, localVideoId, localVideoUrl } from '../src/utils/local-video.js'

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
