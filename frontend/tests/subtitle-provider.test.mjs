import test from 'node:test'
import assert from 'node:assert/strict'
import { effectiveSubtitleTranslationProvider as effective } from '../src/utils/subtitle-provider.js'
test('字幕與摘要、問答共用選定的 Provider',()=>{
  for(const choice of ['ollama:qwen3:4b','gemini','openai:gpt-4.1','opencode:some-free'])assert.equal(effective(choice),choice)
})
test('未準備 AI 仍可讀字幕舊快取，但不會啟動翻譯',()=>{
  assert.equal(effective(null),'opencode') // VideoPane 用 !provider 禁止生成
})
