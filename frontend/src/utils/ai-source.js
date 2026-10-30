// 智慧模式只用本機已下載的模型；不存在時不暗中呼叫免費／付費雲端 API。
export function initialAiSource(persisted, legacy) {
  const input = (persisted || legacy || '').trim()
  return !input || input === 'free' || input === 'auto' ? 'smart' : input
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
  const service=providers?.[kind]
  // 連線驗證後的新模型可能不在舊版 /models 靜態清單，交由後端驗證。
  return kind!=='ollama' && !!service?.configured && /^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$/.test(model) ? selected : null
}
export function aiSourceLabel(selection, resolved, t) {
  if (selection==='smart') return resolved ? t('ai.smartReady') : t('ai.setupRequired')
  if (selection?.startsWith('ollama:')) return resolved ? `Ollama · ${selection.slice(7)}` : t('ai.setupRequired')
  if (!resolved) return t('ai.setupRequired')
  const split = resolved.indexOf(':')
  if (split < 1) return selection === 'gemini' ? 'Google Gemini' : resolved
  const kind = resolved.slice(0, split)
  const model = resolved.slice(split + 1)
  const names = { gemini:'Google Gemini', opencode:'OpenCode', openai:'OpenAI', deepseek:'DeepSeek', anthropic:'Claude' }
  return `${names[kind] || kind} · ${model}`
}
