import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { STRINGS } from '../src/i18n/strings.js'

const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')

test('頁面名稱與語系使用 AstraTube 與繁體中文', () => {
  const html = read('../index.html')
  assert.match(html, /<html lang="zh-Hant">/)
  assert.match(html, /<title>AstraTube<\/title>/)
  assert.doesNotMatch(html, /Youtube Card Reader/)
})

test('介面文字不再使用舊產品名稱', () => {
  for (const [lang, table] of Object.entries(STRINGS)) {
    for (const [key, value] of Object.entries(table)) {
      if (typeof value === 'string') assert.doesNotMatch(value, /Youtube Card Reader/, `${lang}:${key}`)
    }
  }
})

test('浮動按鈕顯示看得懂的文字，不用 AI／NOTE 代號', () => {
  const app = read('../src/App.jsx')
  assert.doesNotMatch(app, /icon="(?:AI|NOTE)"/)
  assert.match(read('../src/components/FloatingPanel.jsx'), /<span>\{title\}<\/span>/)
})

test('樣式表沒有小於 12px 的字級', () => {
  const css = read('../src/index.css')
  const sizes = [...css.matchAll(/font(?:-size)?:[^;}]*?(\d+(?:\.\d+)?)px/g)].map(match => Number(match[1]))
  assert.ok(sizes.length > 50)
  assert.deepEqual(sizes.filter(size => size < 12), [])
})

test('手機版單欄不會被內容撐開', () => {
  assert.match(read('../src/index.css'), /\.workspace\{grid-template-columns:minmax\(0,1fr\)/)
})
