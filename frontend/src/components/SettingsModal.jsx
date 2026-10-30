import { useEffect, useRef, useState } from 'react'
import * as api from '../api.js'
import { useI18n } from '../i18n/index.jsx'
import { PROVIDER_ORDER, providerValue } from '../hooks/useModels.js'
import { aiSourceLabel, resolveAiSource } from '../utils/ai-source.js'

// 同一頁只處理一個供應商，不再把所有供應商的模型攤平成選單。
const KEY_FIELDS = {
  gemini: 'gemini_api_key',
  openai: 'openai_api_key',
  deepseek: 'deepseek_api_key',
  anthropic: 'anthropic_api_key',
}
function sourceParts(value = 'smart') {
  if (value === 'smart') return { engine: 'smart', model: '' }
  if (value === 'gemini') return { engine: 'gemini', model: '' } // 舊版 Gemini 無模型後綴
  const colon = value.indexOf(':')
  return colon < 1 ? { engine: 'smart', model: '' } :
    { engine: value.slice(0, colon), model: value.slice(colon + 1) }
}

export default function SettingsModal({ state, mandatory, onClose, onSaved, provider='smart', providers={}, onProviderChange }) {
  const { t, lang, setLang, langs } = useI18n()
  const initial = sourceParts(provider)
  const [engine, setEngine] = useState(initial.engine)
  const [model, setModel] = useState(initial.model)
  const [keys, setKeys] = useState({})
  const [connection, setConnection] = useState(null)
  const [checking, setChecking] = useState(false)
  const checkVersion = useRef(0)
  const [vault, setVault] = useState(state?.obsidian_vault_path || '')
  const [folder, setFolder] = useState(state?.obsidian_notes_folder || 'Youtube Card Reader')
  const [outputLanguage, setOutputLanguage] = useState(state?.output_language || 'zh-Hant')
  const [ollamaUrl, setOllamaUrl] = useState(state?.ollama_base_url || 'http://127.0.0.1:11434')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  const languages = state?.languages || [{ code: 'zh-Hant', label: '繁體中文' }, { code: 'en', label: 'English' }]
  const keyField = KEY_FIELDS[engine]
  const keySaved = keyField && !!state?.[`${engine}_set`]
  const typedKey = keyField ? (keys[keyField] || '') : ''
  const isSmart = engine === 'smart'
  const verified = !!connection?.connected && connection.provider === engine
  const available = verified ? connection.models : []
  const chosenSource = isSmart ? 'smart' : model ? providerValue(engine, model) : ''
  const unchangedSource = chosenSource === provider || (provider === 'gemini' && engine === 'gemini' && !model)

  function switchEngine(next) {
    ++checkVersion.current
    setEngine(next)
    setModel(next === initial.engine ? initial.model : '')
    setConnection(null)
    setChecking(false)
    setErr('')
  }
  function editKey(value) {
    ++checkVersion.current
    setKeys(prev => ({ ...prev, [KEY_FIELDS[engine]]: value }))
    setConnection(null)
    setChecking(false)
    setErr('')
  }
  function editOllamaUrl(value) {
    ++checkVersion.current
    setOllamaUrl(value)
    setConnection(null)
    setChecking(false)
  }
  async function checkProvider(target = engine, key = typedKey, url = ollamaUrl) {
    if (target === 'smart') return
    const version = ++checkVersion.current
    setChecking(true)
    setConnection(null)
    setErr('')
    try {
      const result = await api.checkProvider({
        provider: target,
        ...(key?.trim() ? { api_key: key.trim() } : {}),
        ...(target === 'ollama' ? { ollama_base_url: url.trim() } : {}),
      })
      if (version !== checkVersion.current) return
      setConnection(result)
      setModel(prev => result.models.includes(prev) ? prev : '')
    } catch (e) {
      if (version === checkVersion.current) setErr(t('ai.verifyFailed', e.message))
    } finally {
      if (version === checkVersion.current) setChecking(false)
    }
  }

  // 已設定金鑰不用再輸入；本機與匿名服務也可直接檢查連線。
  // 只檢查目前所選的供應商，不同時向所有雲端服務發出請求。
  useEffect(() => {
    if (engine === 'smart' || (KEY_FIELDS[engine] && !state?.[`${engine}_set`])) return
    if (KEY_FIELDS[engine] && keys[KEY_FIELDS[engine]]?.trim()) return
    checkProvider(engine, '', ollamaUrl)
    return () => { ++checkVersion.current }
  }, [engine])

  async function handleSave() {
    if (saving || checking) return
    setErr('')
    const changing = !unchangedSource
    if (!isSmart && (changing || !!typedKey.trim()) &&
        (!verified || !model || !available.includes(model))) {
      setErr(t('ai.verifyBeforeSave'))
      return
    }
    const payload = {
      obsidian_vault_path: vault.trim(),
      obsidian_notes_folder: folder.trim() || 'Youtube Card Reader',
      ollama_base_url: ollamaUrl.trim() || 'http://127.0.0.1:11434',
      output_language: outputLanguage,
      // 保留原有金鑰；只在驗證成功且使用者確認儲存時寫入新金鑰。
      ...(typedKey.trim() && verified ? { [keyField]: typedKey.trim() } : {}),
    }
    setSaving(true)
    try {
      const next = await api.saveSettings(payload)
      onProviderChange?.(isSmart ? 'smart' : changing ? chosenSource : provider)
      onSaved?.(next)
    } catch (e) {
      setErr(t('settings.saveFailed', e.message))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="settings-overlay" onMouseDown={e => { if (!mandatory && e.target === e.currentTarget) onClose?.() }}>
      <div className="settings-card" role="dialog" aria-modal="true">
        <div className="settings-head">
          <div>
            <h2>{mandatory ? t('settings.welcome') : t('settings.title')}</h2>
            <p className="settings-sub">{mandatory ? t('settings.subWelcome') : t('settings.sub')}</p>
          </div>
          {!mandatory && <button className="settings-x" onClick={onClose} aria-label={t('settings.close')}>✕</button>}
        </div>
        <div className="settings-body">
          <div className="settings-divider"><span>{t('settings.interface')}</span></div>
          <label className="settings-field">
            <span className="settings-label">{t('settings.uiLanguage')}</span>
            <select value={lang} onChange={e=>setLang(e.target.value)}>
              {langs.map(l=><option key={l.code} value={l.code}>{l.label}</option>)}
            </select>
          </label>

          <div className="settings-divider"><span>{t('ai.source')}</span></div>
          <label className="settings-field">
            <span className="settings-label">{t('ai.chooseProvider')}</span>
            <select value={engine} onChange={e=>switchEngine(e.target.value)}>
              <option value="smart">{t('ai.smart')}</option>
              <optgroup label={t('ai.local')}>
                <option value="ollama">Ollama</option>
              </optgroup>
              <optgroup label={t('ai.cloud')}>
                {PROVIDER_ORDER.filter(p=>p!=='ollama').map(p=>
                  <option key={p} value={p}>{providers?.[p]?.label || p}</option>
                )}
              </optgroup>
            </select>
            {isSmart && <span className="settings-hint">{aiSourceLabel('smart',resolveAiSource('smart',providers),t)} · {t('ai.smartHint')}</span>}
          </label>

          {!isSmart && <>
            {keyField && <label className="settings-field">
              <span className="settings-label">{t('ai.apiKey')}</span>
              <input type="password" autoComplete="off" spellCheck={false}
                value={typedKey} onChange={e=>editKey(e.target.value)}
                placeholder={keySaved ? t('settings.keySet', state?.[`${engine}_preview`] || '••••') : t('settings.keyPlaceholder')} />
              <span className="settings-hint">{keySaved && !typedKey ? t('ai.savedKeyHint') : t('ai.keyHint')}</span>
            </label>}
            {engine === 'ollama' && <label className="settings-field">
              <span className="settings-label">{t('settings.ollamaUrl')}</span>
              <input type="text" value={ollamaUrl} onChange={e=>editOllamaUrl(e.target.value)}
                placeholder="http://127.0.0.1:11434" autoComplete="off" spellCheck={false} />
              <span className="settings-hint">{t('settings.ollamaUrlHint')}</span>
            </label>}
            <div className="settings-ollama-check">
              <button type="button" className="settings-cancel" disabled={checking || saving ||
                (keyField && !keySaved && !typedKey.trim())} onClick={()=>checkProvider()}>
                {checking ? t('ai.verifying') : t('ai.verifyConnection')}
              </button>
              <p className={verified?'settings-hint':'settings-err'} role="status">
                {verified ? t('ai.verified', available.length) : checking ? t('ai.verifying') : ''}
              </p>
            </div>
            {verified && <label className="settings-field">
              <span className="settings-label">{t('ai.chooseModel')}</span>
              <select value={model} onChange={e=>setModel(e.target.value)} disabled={!available.length}>
                <option value="">{t('ai.selectModel')}</option>
                {available.map(m=><option key={m} value={m}>{m}</option>)}
              </select>
              <span className="settings-hint">{available.length ? t('ai.modelsLiveHint') : t('ai.noModels')}</span>
            </label>}
          </>}
          <p className="settings-hint">{t('ai.sharedHint')}</p>
          <p className="settings-hint">{t('ai.localPlanned')}</p>

          <div className="settings-divider"><span>{t('settings.output')}</span></div>
          <label className="settings-field">
            <span className="settings-label">{t('settings.outputLanguage')}</span>
            <select value={outputLanguage} onChange={e=>setOutputLanguage(e.target.value)}>
              {languages.map(l=><option key={l.code} value={l.code}>{l.label}</option>)}
            </select>
          </label>

          <details className="settings-advanced">
            <summary>{t('ai.advancedTools')}</summary>
            <div className="settings-divider"><span>{t('settings.obsidian')}</span></div>
            <label className="settings-field">
              <span className="settings-label">{t('settings.vault')}</span>
              <input type="text" autoComplete="off" spellCheck={false}
                value={vault} onChange={e=>setVault(e.target.value)}
                placeholder={t('settings.vaultPlaceholder')} />
              <span className="settings-hint">{t('settings.vaultHint')}</span>
            </label>
            <label className="settings-field">
              <span className="settings-label">{t('settings.folder')}</span>
              <input type="text" autoComplete="off" spellCheck={false}
                value={folder} onChange={e=>setFolder(e.target.value)}
                placeholder="Youtube Card Reader" />
            </label>
          </details>

          {err && <p className="settings-err" role="alert">{err}</p>}
        </div>
        <div className="settings-foot">
          {!mandatory && <button className="settings-cancel" onClick={onClose} disabled={saving}>{t('settings.cancel')}</button>}
          <button className="settings-save" onClick={handleSave} disabled={saving || checking}>
            {saving ? t('settings.saving') : (mandatory ? t('settings.saveStart') : t('settings.save'))}
          </button>
        </div>
      </div>
    </div>
  )
}
