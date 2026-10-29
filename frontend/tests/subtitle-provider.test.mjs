import test from 'node:test'
import assert from 'node:assert/strict'
import { effectiveSubtitleTranslationProvider as provider } from '../src/utils/subtitle-provider.js'

test('general mode always uses default free subtitle translation', () => {
  assert.equal(provider(false,'ollama:qwen3:4b',['qwen3:4b']), 'opencode')
  assert.equal(provider(false,'openai:gpt',['qwen3:4b']), 'opencode')
})
test('developer mode uses only installed Ollama models', () => {
  assert.equal(provider(true,'ollama:qwen3:4b',['qwen3:4b']), 'ollama:qwen3:4b')
  assert.equal(provider(true,'ollama:qwen3:8b',['qwen3:4b']), 'opencode')
  assert.equal(provider(true,'openai:gpt-4.1',['qwen3:4b']), 'opencode')
  assert.equal(provider(true,'opencode',['qwen3:4b']), 'opencode')
})
