import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { detectSource, needsSubtitleImport, sourceHintKey } from '../src/utils/source-info.js'
import { STRINGS } from '../src/i18n/strings.js'

const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')

test('從網址判斷來源', () => {
  assert.equal(detectSource('https://www.youtube.com/watch?v=abc'), 'youtube')
  assert.equal(detectSource('https://youtu.be/abc'), 'youtube')
  assert.equal(detectSource('https://www.bilibili.com/video/BV1B7411m7LV/'), 'bilibili')
  assert.equal(detectSource('https://b23.tv/abc'), 'bilibiliShort')
  assert.equal(detectSource('https://example.com/post'), 'article')
})

test('相似網域不會被當成影片平台', () => {
  assert.equal(detectSource('https://evil-youtube.com/watch'), 'article')
  assert.equal(detectSource('https://bilibili.com.evil.com/video/x'), 'article')
})

test('空白、不是網址或非 http(s) 時不顯示來源', () => {
  for (const value of ['', '   ', null, undefined, 'youtube', 'file:///C:/a.mp4', 'javascript:alert(1)']) {
    assert.equal(detectSource(value), null, String(value))
  }
})

test('每種來源在兩種語言都有說明，Bilibili 明說不支援的功能', () => {
  for (const source of ['youtube', 'bilibili', 'bilibiliShort', 'article']) {
    for (const table of Object.values(STRINGS)) assert.ok(table[sourceHintKey(source)], source)
  }
  assert.match(STRINGS.zh['input.sourceBilibili'], /不支援讀畫面與疊加字幕/)
  assert.match(STRINGS.zh['input.sourceYoutube'], /需 Gemini/)
  assert.equal(sourceHintKey(null), null)
})

test('只有請使用者匯入字幕的錯誤才顯示匯入按鈕', () => {
  assert.equal(needsSubtitleImport('沒有公開字幕。可以匯入你有權使用的 SRT／VTT 字幕檔後再按「開始」。'), true)
  assert.equal(needsSubtitleImport('Import an SRT/VTT file you are allowed to use.'), true)
  assert.equal(needsSubtitleImport('HTTP 429'), false)
  assert.equal(needsSubtitleImport(''), false)
})

test('分析失敗後可以直接匯入字幕並開始，一般入口維持原樣', () => {
  const app = read('../src/App.jsx')
  const controls = read('../src/components/SubtitleImportControls.jsx')
  assert.match(app, /errorNeedsImport&&<SubtitleImportControls .*?onAnalyze=\{handleSummarize\}/)
  assert.match(app, /const subtitleImport=<SubtitleImportControls videoUrl=\{url\} onChanged=\{[^}]*\}\/>/)
  // 確實匯入後才出現開始按鈕，匯入後也不再提示沒有字幕檔
  assert.match(controls, /onAnalyze && state\?\.exists && <button[^>]*className="import-start"/)
  assert.match(controls, /!state\?\.exists && <span className="import-hint">/)
  for (const table of Object.values(STRINGS)) {
    assert.ok(table['subtitles.importAnalyze'])
    assert.ok(table['subtitles.importNoFile'])
  }
  assert.match(STRINGS.zh['input.sourceBilibili'], /部分影片的字幕需要登入/)
})

test('窄螢幕的分析選項面板對齊整列，不會超出畫面', () => {
  const css = read('../src/index.css')
  assert.match(css, /\.input-options\{position:relative\}\s*\.ai-advanced\[open\]\{position:static\}/)
  assert.match(css, /\.ai-advanced-panel,\.input-row-compact \.ai-advanced-panel\{left:0;right:0;width:auto\}/)
})

test('有結果時頂部自動收成一行，不再有手動收合', () => {
  const app = read('../src/App.jsx')
  assert.match(app, /const compact=!!result\|\|stream\.loading\|\|!!stream\.progress/)
  assert.doesNotMatch(app, /topbarCollapsed|lang-switch/)
})
