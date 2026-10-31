import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { detectSource, needsSubtitleImport, noCaptionAction, sourceHintKey } from '../src/utils/source-info.js'
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

test('本地影片入口：只存識別碼，檔案不離開這台電腦', () => {
  const app = read('../src/App.jsx')
  assert.match(app, /URL\.createObjectURL\(file\)/)
  assert.match(app, /localVideo:localVideo\?\{id:localVideo\.id,name:localVideo\.name\}:null/)
  assert.ok(STRINGS.zh['input.sourceLocal'].includes('不會上傳'))
  assert.equal(sourceHintKey('local'), 'input.sourceLocal')
  // 筆記來源綁定分析當時的影片；已有重點時仍可管理字幕
  assert.match(app, /noteSource=isLocalResult\?\(result\.local_name/)
  assert.doesNotMatch(app, /noteSource=isLocalResult\?\(localVideo/)
  assert.match(read('../src/hooks/useSummarizeStream.js'), /local_name: localName/)
  assert.match(app, /result\?\.local_video_id!==localVideo\.id/)
  assert.match(app, /result\?\.local_video_id===localVideo\.id&&<details/)
  const conf = readFileSync(new URL('../../desktop/src-tauri/tauri.conf.json', import.meta.url), 'utf8')
  assert.match(conf, /media-src blob:;/)
  for (const table of Object.values(STRINGS)) {
    for (const key of ['input.modeUrl', 'input.modeLocal', 'input.sourceLocal', 'local.pick', 'local.subtitles', 'local.none', 'local.repick', 'local.repickHint', 'local.playError', 'local.invalidFile', 'local.noSubtitleHint']) {
      assert.ok(table[key], key)
    }
  }
})

test('沒有字幕時只有 YouTube 能改用讀畫面，缺金鑰就先引導設定', () => {
  assert.equal(noCaptionAction('youtube', false, false), 'add-key')
  assert.equal(noCaptionAction('youtube', true, false), 'add-key')
  assert.equal(noCaptionAction('youtube', false, true), 'enable-visual')
  assert.equal(noCaptionAction('youtube', true, true), null)
  assert.equal(noCaptionAction('bilibili', false, true), null)
  assert.equal(noCaptionAction('bilibili', false, false), null)
  assert.equal(noCaptionAction(null, false, true), null)
})

test('讀畫面提示對齊輸入區；改用雲端要使用者按下才發生', () => {
  const app = read('../src/App.jsx')
  assert.match(app, /className=\{`source-hint visual-notice/)
  assert.doesNotMatch(app, /visualNotice&&<p className="subtitles-hint"/)
  assert.match(app, /onClick=\{analyzeWithVisual\}/)
  assert.match(app, /function analyzeWithVisual\(\)\{setDeepVisual\(true\);startAnalysis\(true\)\}/)
  for (const table of Object.values(STRINGS)) {
    for (const key of ['noCaption.addKey', 'noCaption.addKeyAction', 'noCaption.enableVisual', 'noCaption.enableVisualAction', 'subtitles.importNoFileVisual']) {
      assert.ok(table[key], key)
    }
    assert.match(table['noCaption.addKey'], /Google/)
    assert.match(table['noCaption.enableVisual'], /Google/)
  }
})

test('讀畫面的金鑰可以單獨保存，不會切換 AI 來源', () => {
  const modal = read('../src/components/SettingsModal.jsx')
  // 先驗證才保存；驗證失敗不能把金鑰寫進設定
  assert.match(modal, /checkProvider\(\{ provider: 'gemini', api_key: visualKey\.trim\(\) \}\)[\s\S]*?return\s*\n\s*\}\s*\n\s*\}\s*\n\s*const next = await api\.saveSettings/)
  assert.match(modal, /visualKey\.trim\(\) \? \{ gemini_api_key: visualKey\.trim\(\) \}/)
  assert.doesNotMatch(modal, /setEngine\('gemini'\)/)
  assert.doesNotMatch(modal.match(/const \[visualKey[\s\S]*?useRef\(null\)/)[0], /Provider/)
})

test('分析失敗後可以直接匯入字幕並開始，一般入口維持原樣', () => {
  const app = read('../src/App.jsx')
  const controls = read('../src/components/SubtitleImportControls.jsx')
  assert.match(app, /errorNeedsImport&&!isLocalMode&&<SubtitleImportControls .*?onAnalyze=\{handleSummarize\}/)
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
