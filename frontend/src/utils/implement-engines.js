// 實作視窗可用的 API 引擎。雲端模型清單只在設定頁驗證連線時取得，不會常駐在 providers，
// 所以目前選定且已驗證的 AI 來源要另外補進來，否則有金鑰的使用者會一個雲端選項都看不到。
export function apiEngineOptions({ providers, selectedProvider, geminiReady, geminiModel }) {
  const options = []
  const add = (value, label) => {
    if (!options.some(option => option.value === value)) options.push({ value, label })
  }
  const selected = selectedProvider || ''
  const split = selected.indexOf(':')
  if (split > 0) {
    const kind = selected.slice(0, split)
    add(`${selected}::`, `${providers?.[kind]?.label || kind} · ${selected.slice(split + 1)}`)
  }
  if (geminiReady) add('gemini::', `Gemini · ${geminiModel}`)
  for (const key of Object.keys(providers || {})) {
    const provider = providers[key]
    if (key === 'gemini' || !provider || (!provider.free && !provider.configured)) continue
    for (const model of provider.models || []) add(`${key}:${model}::`, `${provider.label} · ${model}`)
  }
  return options
}
