import test from 'node:test'
import assert from 'node:assert/strict'
import { DEEP_VISUAL_KEY, deepVisualNotice, effectiveDeepVisual } from '../src/utils/user-mode.js'
import { initialAiSource, resolveAiSource } from '../src/utils/ai-source.js'
import { createNoteMarkdown, markdownFilename } from '../src/utils/notes-export.js'

test('讀畫面不沿用開發者模式時期的舊設定，開啟時明確說明影片去向',()=>{
  assert.notEqual(DEEP_VISUAL_KEY,'ycr-deep-visual')
  const video='https://www.youtube.com/watch?v=dQw4w9WgXcQ'
  assert.equal(deepVisualNotice(false,video,true),null)
  assert.equal(deepVisualNotice(true,video,true),'gemini')
  assert.equal(deepVisualNotice(true,video,false),'no-key')
  assert.equal(deepVisualNotice(true,'https://www.bilibili.com/video/BV1B7411m7LV/',true),null)
})

test('舊一般模式遷移為本機智慧模式，保留舊 Ollama 選擇',()=>{
  assert.equal(initialAiSource(null,'free'),'smart')
  assert.equal(initialAiSource('auto','openai:paid'),'smart')
  assert.equal(initialAiSource(null,'ollama:qwen3:14b'),'ollama:qwen3:14b')
  assert.equal(initialAiSource('opencode:mimo-free',null),'smart')
})
test('智慧模式只用本機，不暗中轉雲端；明確選擇才可用雲端',()=>{
  const providers={ollama:{configured:false,models:[]},gemini:{configured:true,models:['x']},opencode:{configured:true,models:['x-free']}}
  assert.equal(resolveAiSource('smart',providers),null)
  assert.equal(resolveAiSource('gemini',providers),'gemini')
  assert.equal(resolveAiSource('opencode:x-free',providers),null)
  providers.ollama={configured:true,models:['qwen3:4b','qwen3:14b']}
  assert.equal(resolveAiSource('smart',providers),'ollama:qwen3:4b')
  assert.equal(resolveAiSource('ollama:qwen3:14b',providers),'ollama:qwen3:14b')
  assert.equal(resolveAiSource('ollama:unknown',providers),null)
  assert.equal(effectiveDeepVisual(true,'https://www.bilibili.com/video/BV1B7411m7LV/'),false)
  assert.equal(effectiveDeepVisual(true,'https://www.youtube.com/watch?v=M7lc1UVf-VE'),true)
})
test('Markdown 匯出不需 Obsidian',()=>{
  const md=createNoteMarkdown({title:'學習筆記',sourceUrl:'https://www.youtube.com',clips:[{heading:'重點',summary:'說明',ts:63,transcript:'Hello',note:'心得'}],freeNote:'備註'})
  assert.match(md,/學習筆記/)
  assert.match(md,/Hello/)
  assert.equal(markdownFilename('非法/路徑:*?'),'非法-路徑---.md')
})
