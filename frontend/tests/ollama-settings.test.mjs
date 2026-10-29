import test from 'node:test'
import assert from 'node:assert/strict'
import { ollamaModelOptions } from '../src/utils/ollama-settings.js'
import { STRINGS } from '../src/i18n/strings.js'

test('下拉選單只列已安裝模型，第一項是自動選擇', () => {
  assert.deepEqual(ollamaModelOptions(['qwen3:4b', 'gemma3:4b'], 'qwen3:4b'), [
    { value: '', kind: 'auto' },
    { value: 'qwen3:4b', kind: 'installed' },
    { value: 'gemma3:4b', kind: 'installed' },
  ])
})

test('已儲存但未安裝的模型保留並標示，不會被默默換掉', () => {
  assert.deepEqual(ollamaModelOptions(['gemma3:4b'], 'llama3.2:3b').at(-1), { value: 'llama3.2:3b', kind: 'missing' })
  assert.deepEqual(ollamaModelOptions(null, ''), [{ value: '', kind: 'auto' }])
  assert.deepEqual(ollamaModelOptions([null, '', 'qwen3:4b'], ' '), [{ value: '', kind: 'auto' }, { value: 'qwen3:4b', kind: 'installed' }])
})

test('Ollama 設定的新介面文字兩種語言都有', () => {
  for (const lang of Object.keys(STRINGS)) {
    const s = STRINGS[lang]
    for (const key of ['settings.ollamaAuto', 'settings.ollamaNoModels', 'settings.ollamaRefresh']) assert.ok(s[key], `${lang} ${key}`)
    assert.match(s['settings.ollamaMissing']('llama3.2:3b'), /llama3\.2:3b/)
  }
})
