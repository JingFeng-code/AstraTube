import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')
const css = read('../src/index.css')
const lightBlock = css.match(/:root\{([\s\S]*?)\n\}/)[1]
const darkBlock = css.match(/prefers-color-scheme:dark\)\{\s*:root\{([\s\S]*?)\n\s*\}/)[1]
const token = (block, name) => block.match(new RegExp(`--${name}:(#[0-9a-f]{6})`))[1]
const luminance = hex => {
  const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map(c => c <= .03928 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4)
  return .2126 * r + .7152 * g + .0722 * b
}
const contrast = (a, b) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + .05) / (lo + .05)
}

for (const [mode, block] of [['淺色', lightBlock], ['深色', darkBlock]]) {
  test(`${mode}模式的文字和主色按鈕都達到 4.5:1`, () => {
    const check = (fg, bg) => assert.ok(contrast(token(block, fg), token(block, bg)) >= 4.5, `${fg} on ${bg}`)
    for (const fg of ['text', 'text-soft', 'text-faint']) {
      for (const bg of ['bg', 'surface']) check(fg, bg)
    }
    check('text', 'surface-2')
    check('on-accent', 'accent')
    check('on-accent', 'accent-hover')
    check('accent', 'accent-soft')
  })

  test(`${mode}模式圖示的星星和月亮看得清楚`, () => {
    assert.ok(contrast(token(block, 'brand-star'), token(block, 'accent')) >= 3)
    assert.ok(contrast(token(block, 'on-accent'), token(block, 'accent')) >= 3)
  })
}

test('主色底上的文字一律用 on-accent，深色模式才不會白字配銀底', () => {
  assert.doesNotMatch(css, /background:var\(--accent\);color:#fff/)
  assert.doesNotMatch(css, /::selection\{background:var\(--accent\);color:#fff/)
  assert.doesNotMatch(css, /rgba\(88,0,0|rgba\(90,0,0/)
})

test('品牌標記換成新月，不再使用像 YouTube 的紅底播放鍵', () => {
  const mark = read('../src/components/BrandMark.jsx')
  assert.match(mark, /<svg viewBox="0 0 100 100">/)
  assert.match(mark, /var\(--brand-star\)/)
  assert.doesNotMatch(mark, /brand-play|brand-card/)
  assert.doesNotMatch(css, /brand-play|brand-card/)
  assert.doesNotMatch(css, /--accent:#e53838|--accent:#ef4747/)
  assert.match(read('../index.html'), /rel="icon"/)
  assert.doesNotMatch(read('../../scripts/make_desktop_icons.py'), /placeholder/i)
})
