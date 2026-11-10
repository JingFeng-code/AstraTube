import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { STRINGS } from '../src/i18n/strings.js'

const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')

test('按下停止會中斷串流，不再處理後面的事件', async () => {
  const original = globalThis.fetch
  let sentSignal = null
  // 假後端：先送一段知識卡，之後一直不結束，直到連線被中斷
  globalThis.fetch = async (_url, options) => {
    sentSignal = options.signal
    const encoder = new TextEncoder()
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(JSON.stringify({ type: 'cards', cards: [{ title: 'a' }] }) + '\n'))
        options.signal.addEventListener('abort', () => controller.error(new DOMException('aborted', 'AbortError')))
      },
    })
    return new Response(body, { status: 200 })
  }
  try {
    const { summarizeStream } = await import('../src/api.js')
    const controller = new AbortController()
    const events = []
    const running = summarizeStream('https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'ollama', false, ev => {
      events.push(ev)
      controller.abort()
    }, controller.signal)
    await assert.rejects(running, { name: 'AbortError' })
    assert.equal(sentSignal, controller.signal)
    assert.equal(events.length, 1)
  } finally {
    globalThis.fetch = original
  }
})

test('整理中把開始按鈕換成停止，停止後保留已產生的知識卡', () => {
  const app = read('../src/App.jsx')
  assert.match(app, /className="btn-go btn-stop" onClick=\{stream\.stop\}/)
  assert.match(app, /stream\.stopped&&/)
  const hook = read('../src/hooks/useSummarizeStream.js')
  assert.match(hook, /new AbortController\(\)/)
  assert.match(hook, /\}, controller\.signal\)/)
  // 被使用者停止不算錯誤；有卡片就保留
  assert.match(hook, /if \(controller\.signal\.aborted\) \{\s*setStopped\(true\)\s*if \(draft\.cards\.length\) setResult/)
  assert.match(hook, /function stop\(\) \{ controllerRef\.current\?\.abort\(\) \}/)
  for (const table of Object.values(STRINGS)) {
    for (const key of ['input.stop', 'input.stopHint', 'input.stopped', 'input.stoppedPartial']) assert.equal(typeof table[key], 'string', key)
  }
})
