import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
test('desktop session stays in memory and uses a token',()=>{
  const src=readFileSync(new URL('../src/desktop.js',import.meta.url),'utf8')
  assert.match(src,/desktop_connection/)
  assert.match(src,/X-Astra-Desktop-Token/)
  assert.doesNotMatch(src,/localStorage|sessionStorage/)
})
