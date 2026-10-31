import test from 'node:test'
import assert from 'node:assert/strict'
import { apiEngineOptions } from '../src/utils/implement-engines.js'

const providers = {
  ollama: { label: 'Ollama', configured: true, models: ['qwen3:4b'] },
  openai: { label: 'OpenAI', configured: true, models: [] },
  groq: { label: 'Groq', configured: false, models: [] },
}

test('目前選定的雲端模型會出現在實作引擎，而且排在最前面', () => {
  const options = apiEngineOptions({ providers, selectedProvider: 'openai:gpt-x' })
  assert.deepEqual(options[0], { value: 'openai:gpt-x::', label: 'OpenAI · gpt-x' })
  assert.deepEqual(options.map(option => option.value), ['openai:gpt-x::', 'ollama:qwen3:4b::'])
})

test('模型名稱保留大小寫與斜線', () => {
  const options = apiEngineOptions({ providers: { together: { label: 'Together AI', configured: true, models: [] } },
    selectedProvider: 'together:meta-llama/Llama-3' })
  assert.equal(options[0].value, 'together:meta-llama/Llama-3::')
})

test('選定 Ollama 時不會重複列出同一個模型', () => {
  const options = apiEngineOptions({ providers, selectedProvider: 'ollama:qwen3:4b' })
  assert.deepEqual(options.map(option => option.value), ['ollama:qwen3:4b::'])
})

test('沒有選定 AI 時不會列出未驗證的雲端模型', () => {
  assert.deepEqual(apiEngineOptions({ providers: { openai: providers.openai, groq: providers.groq }, selectedProvider: null }), [])
})

test('Gemini 就緒時保留既有選項', () => {
  const options = apiEngineOptions({ providers: {}, selectedProvider: null, geminiReady: true, geminiModel: 'gemini-x' })
  assert.deepEqual(options, [{ value: 'gemini::', label: 'Gemini · gemini-x' }])
})
