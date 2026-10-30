import test from 'node:test'
import assert from 'node:assert/strict'
import { providerValue } from '../src/hooks/useModels.js'
import { resolveAiSource } from '../src/utils/ai-source.js'

test('供應商模型必須保留獨立的模型識別碼，包含 Gemini', () => {
  assert.equal(providerValue('gemini', 'gemini-3.5-flash'), 'gemini:gemini-3.5-flash')
  assert.equal(providerValue('openai', 'gpt-4.1'), 'openai:gpt-4.1')
})

test('已設定供應商可以選用剛驗證的模型，不依賴舊版靜態清單', () => {
  const p = {gemini:{configured:true, models:['old']},
    openai:{configured:true, models:['old']},
    ollama:{configured:false, models:[]}}
  assert.equal(resolveAiSource('gemini:gemini-new', p), 'gemini:gemini-new')
  assert.equal(resolveAiSource('openai:gpt-new', p), 'openai:gpt-new')
  assert.equal(resolveAiSource('openai:bad model!', p), null)
  assert.equal(resolveAiSource('smart', p), null)
  p.openai.configured = false
  assert.equal(resolveAiSource('openai:gpt-new', p), null)
})
