import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { STRINGS } from '../src/i18n/strings.js'
import { aiConnectionStatus, connectionCheckTarget } from '../src/utils/ai-source.js'

const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')
const live = (provider, models) => ({ provider, connected: true, models })

test('智慧模式檢查連線只會碰本機 Ollama', () => {
  assert.equal(connectionCheckTarget('smart'), 'ollama')
  assert.equal(connectionCheckTarget('openai'), 'openai')
})

test('智慧模式依本機檢查結果顯示狀態', () => {
  assert.equal(aiConnectionStatus({ engine: 'smart' }).code, 'checking')
  assert.deepEqual(aiConnectionStatus({ engine: 'smart', connection: live('ollama', ['qwen3:4b', 'gemma3:4b']) }),
    { level: 'ok', code: 'smartReady', model: 'qwen3:4b' })
  assert.equal(aiConnectionStatus({ engine: 'smart', connection: live('ollama', []) }).code, 'noLocalModels')
  // 沒開 Ollama 是一般情況，不算錯誤，也不會改用雲端
  assert.deepEqual(aiConnectionStatus({ engine: 'smart', error: '無法連線' }), { level: 'warn', code: 'localMissing' })
})

test('已存金鑰或只輸入金鑰，都不算連線成功', () => {
  assert.equal(aiConnectionStatus({ engine: 'openai' }).code, 'needKey')
  assert.equal(aiConnectionStatus({ engine: 'openai', typedKey: '   ' }).code, 'needKey')
  assert.deepEqual(aiConnectionStatus({ engine: 'openai', keySaved: true, model: 'gpt-x' }), { level: 'idle', code: 'unverified' })
  assert.equal(aiConnectionStatus({ engine: 'openai', typedKey: 'sk-x' }).code, 'unverified')
  assert.equal(aiConnectionStatus({ engine: 'ollama' }).code, 'unverified')
})

test('連線成功後，選好模型才算就緒', () => {
  const connection = live('openai', ['gpt-x', 'gpt-y'])
  assert.deepEqual(aiConnectionStatus({ engine: 'openai', connection }), { level: 'warn', code: 'pickModel', count: 2 })
  assert.deepEqual(aiConnectionStatus({ engine: 'openai', connection, model: 'gpt-y' }), { level: 'ok', code: 'ready', model: 'gpt-y' })
})

test('其他供應商的結果不能算進目前選擇，檢查中和失敗優先顯示', () => {
  assert.equal(aiConnectionStatus({ engine: 'openai', keySaved: true, connection: live('ollama', ['qwen3:4b']) }).code, 'unverified')
  assert.equal(aiConnectionStatus({ engine: 'openai', checking: true, connection: live('openai', ['gpt-x']) }).code, 'checking')
  assert.deepEqual(aiConnectionStatus({ engine: 'ollama', error: '連不上' }), { level: 'error', code: 'failed', detail: '連不上' })
})

test('設定頁先放 AI 來源，語言合併成一組', () => {
  const modal = read('../src/components/SettingsModal.jsx')
  const order = ["t('ai.source')", "t('settings.language')", "t('settings.uiLanguage')", "t('settings.outputLanguage')", "t('ai.advancedTools')"]
    .map(key => modal.indexOf(key))
  assert.ok(order.every(at => at >= 0), String(order))
  assert.deepEqual(order, [...order].sort((a, b) => a - b))
})

test('步驟不再編號，內建模型的預告只在找不到本機 AI 時出現', () => {
  for (const table of Object.values(STRINGS)) {
    for (const key of ['ai.chooseProvider', 'ai.apiKey', 'ai.chooseModel']) assert.doesNotMatch(table[key], /^\d/)
  }
  assert.match(read('../src/components/SettingsModal.jsx'), /status\.code === 'localMissing' && <p className="settings-hint">\{t\('ai\.localPlanned'\)\}/)
})

test('兩種語言都有狀態文字', () => {
  for (const [lang, table] of Object.entries(STRINGS)) {
    for (const key of ['settings.language', 'ai.recheck', 'ai.status.localMissing', 'ai.status.needKey', 'ai.status.unverified']) {
      assert.equal(typeof table[key], 'string', `${lang}:${key}`)
    }
    assert.match(table['ai.status.smartReady']('qwen3:4b'), /qwen3:4b/)
    assert.match(table['ai.status.ready']('gpt-x'), /gpt-x/)
    assert.match(table['ai.status.pickModel'](7), /7/)
  }
})
