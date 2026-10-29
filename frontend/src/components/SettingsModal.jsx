import { useState } from 'react'
import * as api from '../api.js'
import { useI18n } from '../i18n/index.jsx'

// 每個引擎一列：欄位名 → 標籤／說明／輸入型別
const ENGINES = [
  { name: 'gemini',    field: 'gemini_api_key',    multiline: true },
  { name: 'anthropic', field: 'anthropic_api_key' },
  { name: 'openai',    field: 'openai_api_key' },
  { name: 'deepseek',  field: 'deepseek_api_key' },
  { name: 'opencode',  field: 'opencode_api_key' },
]

// state: 後端 /settings 回傳的公開狀態
// mandatory: 首次啟動（尚未設定任何金鑰）→ 不可關閉，作為導引畫面
export default function SettingsModal({ state, mandatory, onClose, onSaved, developerMode=false, onDeveloperModeChange }) {
  const { t, lang, setLang, langs } = useI18n()
  const [keys, setKeys] = useState({})   // 只放使用者「這次有輸入」的金鑰
  const [vault, setVault] = useState(state?.obsidian_vault_path || '')
  const [folder, setFolder] = useState(state?.obsidian_notes_folder || 'Youtube Card Reader')
  const [outputLanguage, setOutputLanguage] = useState(state?.output_language || 'zh-Hant')
  const [ollamaUrl, setOllamaUrl] = useState(state?.ollama_base_url || 'http://127.0.0.1:11434')
  const [ollamaModel, setOllamaModel] = useState(state?.ollama_model || '')
  const [ollamaStatus, setOllamaStatus] = useState(null)
  const [checkingOllama, setCheckingOllama] = useState(false)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  const languages = state?.languages || [{ code: 'zh-Hant', label: '繁體中文' }, { code: 'en', label: 'English' }]
  const setKey = (field, value) => setKeys(prev => ({ ...prev, [field]: value }))

  async function handleSave() {
    if (saving) return
    setErr('')
    const payload = {
      // 金鑰：留空代表「維持原本設定」，只送有輸入的
      ...(developerMode ? Object.fromEntries(Object.entries(keys).filter(([, v]) => v.trim()).map(([k, v]) => [k, v.trim()])) : {}),
      // 這些總是送出（清空即代表停用）
      ...(developerMode ? {
        obsidian_vault_path: vault.trim(),
        obsidian_notes_folder: folder.trim() || 'Youtube Card Reader',
        ollama_base_url: ollamaUrl.trim() || 'http://127.0.0.1:11434',
        ollama_model: ollamaModel.trim(),
      } : {}),
      output_language: outputLanguage,
    }
    setSaving(true)
    try {
      const next = await api.saveSettings(payload)
      onSaved?.(next)
    } catch (e) {
      setErr(t('settings.saveFailed', e.message))
    } finally {
      setSaving(false)
    }
  }

  async function checkOllama() {
    setCheckingOllama(true)
    setOllamaStatus(null)
    try {
      setOllamaStatus(await api.getOllamaStatus())
    } catch {
      setOllamaStatus({connected:false,models:[],message:t('settings.ollamaUnavailable')})
    } finally {
      setCheckingOllama(false)
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
          {/* 介面語言擺第一個：外國使用者打開設定，第一件想做的事就是把介面換成看得懂的 */}
          <div className="settings-divider"><span>{t('settings.interface')}</span></div>
          <label className="settings-field">
            <span className="settings-label">{t('settings.uiLanguage')}</span>
            <select value={lang} onChange={e => setLang(e.target.value)}>
              {langs.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
            </select>
            <span className="settings-hint">{t('settings.uiLanguageHint')}</span>
          </label>

          <div className="settings-divider"><span>{t('settings.modeSection')}</span></div>
          <label className="settings-mode-toggle">
            <span className="settings-mode-copy">
              <strong>{t('settings.developerMode')}</strong>
              <small>{t('settings.developerModeHint')}</small>
            </span>
            <input type="checkbox" role="switch" checked={developerMode}
                   onChange={e => onDeveloperModeChange?.(e.target.checked)}/>
          </label>

          <div className="settings-divider"><span>{t('settings.output')}</span></div>
          <label className="settings-field">
            <span className="settings-label">{t('settings.outputLanguage')}</span>
            <select value={outputLanguage} onChange={e => setOutputLanguage(e.target.value)}>
              {languages.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
            </select>
            <span className="settings-hint">{t('settings.outputLanguageHint')}</span>
          </label>

          {developerMode && <>
          <div className="settings-divider"><span>{t('settings.ollamaSection')}</span></div>
          <label className="settings-field">
            <span className="settings-label">{t('settings.ollamaUrl')}</span>
            <input type="text" value={ollamaUrl} onChange={e=>setOllamaUrl(e.target.value)}
                   autoComplete="off" spellCheck={false} placeholder="http://127.0.0.1:11434"/>
            <span className="settings-hint">{t('settings.ollamaUrlHint')}</span>
          </label>
          <label className="settings-field">
            <span className="settings-label">{t('settings.ollamaModel')}</span>
            <input type="text" value={ollamaModel} onChange={e=>setOllamaModel(e.target.value)}
                   autoComplete="off" spellCheck={false} placeholder={t('settings.ollamaModelPlaceholder')}/>
            <span className="settings-hint">{t('settings.ollamaModelHint')}</span>
          </label>
          <div className="settings-ollama-check">
            <button type="button" className="settings-cancel" onClick={checkOllama} disabled={checkingOllama}>
              {checkingOllama?t('settings.ollamaChecking'):t('settings.ollamaCheck')}
            </button>
            {ollamaStatus && <p className={ollamaStatus.connected?'settings-hint':'settings-err'} role="status">
              {ollamaStatus.message}{ollamaStatus.models?.length?' ('+ollamaStatus.models.join(', ')+')':''}
            </p>}
          </div>
          <p className="settings-hint">{t('settings.ollamaCheckHint')}</p>
          <div className="settings-divider"><span>{t('settings.engines')}</span></div>
          {ENGINES.map(({ name, field, multiline }) => {
            const already = !!state?.[`${name}_set`]
            const placeholder = already
              ? t('settings.keySet', state[`${name}_preview`])
              : t(name === 'gemini' ? 'settings.geminiPlaceholder'
                  : name === 'opencode' ? 'settings.opencodePlaceholder'
                  : 'settings.keyPlaceholder')
            return (
              <label className="settings-field" key={field}>
                <span className="settings-label">{t(`settings.${name}`)}</span>
                {multiline ? (
                  <textarea rows={3} autoComplete="off" spellCheck={false} className="settings-keys"
                            value={keys[field] || ''} onChange={e => setKey(field, e.target.value)}
                            placeholder={placeholder}/>
                ) : (
                  <input type="password" autoComplete="off" spellCheck={false}
                         value={keys[field] || ''} onChange={e => setKey(field, e.target.value)}
                         placeholder={placeholder}/>
                )}
                <span className="settings-hint">{t(`settings.${name}Hint`)}</span>
              </label>
            )
          })}

          <div className="settings-divider"><span>{t('settings.obsidian')}</span></div>
          <label className="settings-field">
            <span className="settings-label">{t('settings.vault')}</span>
            <input type="text" autoComplete="off" spellCheck={false}
                   value={vault} onChange={e => setVault(e.target.value)}
                   placeholder={t('settings.vaultPlaceholder')}/>
            <span className="settings-hint">{t('settings.vaultHint')}</span>
          </label>
          <label className="settings-field">
            <span className="settings-label">{t('settings.folder')}</span>
            <input type="text" autoComplete="off" spellCheck={false}
                   value={folder} onChange={e => setFolder(e.target.value)}
                   placeholder="Youtube Card Reader"/>
          </label>

          </>}

          {err && <p className="settings-err">{err}</p>}
        </div>

        <div className="settings-foot">
          {!mandatory && <button className="settings-cancel" onClick={onClose} disabled={saving}>{t('settings.cancel')}</button>}
          <button className="settings-save" onClick={handleSave} disabled={saving}>
            {saving ? t('settings.saving') : (mandatory ? t('settings.saveStart') : t('settings.save'))}
          </button>
        </div>
      </div>
    </div>
  )
}
