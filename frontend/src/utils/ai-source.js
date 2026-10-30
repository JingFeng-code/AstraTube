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
  if (selected === 'gemini') return providers?.gemini?.configured ? 'gemini' : null
  const sep = (selected || '').indexOf(':')
  if (sep < 1) return null
  const kind=selected.slice(0,sep), model=selected.slice(sep+1)
  const service=providers?.[kind]
  return kind!=='ollama' && !!service?.configured && service.models?.includes(model) ? selected : null
}
export function aiSourceLabel(selection, resolved, t) {
  if (selection==='smart') return resolved ? t('ai.smartReady') : t('ai.setupRequired')
  if (selection?.startsWith('ollama:')) return resolved ? `Ollama · ${selection.slice(7)}` : t('ai.setupRequired')
  if (!resolved) return t('ai.setupRequired')
  return selection === 'gemini' ? 'Gemini' : resolved
}
