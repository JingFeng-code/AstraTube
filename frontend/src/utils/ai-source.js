// 智慧模式只用本機已下載的模型；不存在時不暗中呼叫免費／付費雲端 API。
export function initialAiSource(persisted, legacy) {
  const input = (persisted || legacy || '').trim()
  return !input || input === 'free' || input === 'auto' ||
    input === 'opencode' || input.startsWith('opencode:') ? 'smart' : input
}
export function resolveAiSource(selected, providers = {}) {
  const local = providers?.ollama
  const installed = local?.configured ? (local.models || []) : []
  if (selected === 'smart') return installed.length ? `ollama:${installed[0]}` : null
  if (selected?.startsWith('ollama:')) return installed.includes(selected.slice(7)) ? selected : null
  if (selected === 'gemini') return providers?.gemini?.configured ? 'gemini' : null // 舊版選項仍可讀取
  const sep = (selected || '').indexOf(':')
  if (sep < 1) return null
  const kind=selected.slice(0,sep), model=selected.slice(sep+1)
  if (kind === 'opencode') return null // 停用無法從外部穩定呼叫的舊版來源
  const service=providers?.[kind]
  // 連線驗證後的新模型可能不在舊版 /models 靜態清單，交由後端驗證。
  return kind!=='ollama' && !!service?.configured && /^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$/.test(model) ? selected : null
}
// 智慧模式只看本機 Ollama，檢查連線時絕不碰雲端供應商。
export function connectionCheckTarget(engine) {
  return engine === 'smart' ? 'ollama' : engine
}
// 設定頁的連線狀態：只依實際檢查結果判斷，已存金鑰不等於連線成功。
export function aiConnectionStatus({ engine, model = '', typedKey = '', keySaved = false, checking = false, connection = null, error = '' }) {
  if (checking) return { level: 'checking', code: 'checking' }
  const smart = engine === 'smart'
  if (error) return smart ? { level: 'warn', code: 'localMissing' } : { level: 'error', code: 'failed', detail: error }
  if (connection?.connected && connection.provider === connectionCheckTarget(engine)) {
    const models = connection.models || []
    if (!models.length) return { level: 'warn', code: 'noLocalModels' }
    if (smart) return { level: 'ok', code: 'smartReady', model: models[0] }
    return model ? { level: 'ok', code: 'ready', model } : { level: 'warn', code: 'pickModel', count: models.length }
  }
  // 智慧模式開啟時一定會檢查，這裡只是檢查開始前的瞬間
  if (smart) return { level: 'checking', code: 'checking' }
  if (engine !== 'ollama' && !typedKey.trim() && !keySaved) return { level: 'idle', code: 'needKey' }
  return { level: 'idle', code: 'unverified' }
}
export function aiSourceLabel(selection, resolved, t) {
  if (selection==='smart') return resolved ? t('ai.smartReady') : t('ai.setupRequired')
  if (selection?.startsWith('ollama:')) return resolved ? `Ollama · ${selection.slice(7)}` : t('ai.setupRequired')
  if (!resolved) return t('ai.setupRequired')
  const split = resolved.indexOf(':')
  if (split < 1) return selection === 'gemini' ? 'Google Gemini' : resolved
  const kind = resolved.slice(0, split)
  const model = resolved.slice(split + 1)
  const names = { gemini:'Google Gemini', openai:'OpenAI', deepseek:'DeepSeek', anthropic:'Claude',
    openrouter:'OpenRouter', groq:'Groq', mistral:'Mistral AI', together:'Together AI' }
  return `${names[kind] || kind} · ${model}`
}
