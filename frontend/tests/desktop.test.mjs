import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
test('desktop session stays in memory and uses a token',()=>{
  const src=readFileSync(new URL('../src/desktop.js',import.meta.url),'utf8')
  assert.match(src,/desktop_connection/)
  assert.match(src,/X-Astra-Desktop-Token/)
  assert.doesNotMatch(src,/localStorage|sessionStorage/)
})

test('免安裝版資料夾無法寫入時，畫面顯示桌面程式提供的原因', async () => {
  const reason = 'AstraTube 無法在程式所在位置建立資料夾：C:\\Program Files\\AstraTube\\data（拒絕存取）。'
  globalThis.window = { __TAURI_INTERNALS__: {}, __TAURI__: { core: { invoke: () => Promise.reject(reason) } } }
  try {
    const { bootstrapDesktop } = await import('../src/desktop.js?unwritable')
    await assert.rejects(bootstrapDesktop(), error => error.message === reason)
  } finally {
    delete globalThis.window
  }
})
