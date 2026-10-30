import { useEffect, useState } from 'react'
import * as api from '../api.js'

// 供應商清單與可用性分開：模型必須等金鑰／連線檢查後才顯示。
export const STATIC_PROVIDERS = {
  ollama: { label:'Ollama（本機）', free:true, configured:false, source:'local', models:[] },
  gemini: { label:'Google Gemini', free:false, configured:false, source:'unverified', models:[] },
  openai: { label:'OpenAI', free:false, configured:false, source:'unverified', models:[] },
  deepseek: { label:'DeepSeek', free:false, configured:false, source:'unverified', models:[] },
  anthropic: { label:'Anthropic Claude', free:false, configured:false, source:'unverified', models:[] },
  openrouter: { label:'OpenRouter', free:false, configured:false, source:'unverified', models:[] },
  groq: { label:'Groq', free:false, configured:false, source:'unverified', models:[] },
  mistral: { label:'Mistral AI', free:false, configured:false, source:'unverified', models:[] },
  together: { label:'Together AI', free:false, configured:false, source:'unverified', models:[] },
}

export const PROVIDER_ORDER = ['ollama', 'gemini', 'openai', 'deepseek', 'anthropic',
  'openrouter', 'groq', 'mistral', 'together']

export const providerValue = (kind, model) => `${kind}:${model}`

function normalize(data) {
  if (!data?.providers || typeof data.providers !== 'object') return null
  return Object.fromEntries(PROVIDER_ORDER.map(key => {
    const defaults = STATIC_PROVIDERS[key]
    const remote = data.providers[key] || {}
    // 未經驗證的雲端模型，不能靠靜態預設清單顯示已可用。
    return [key, {...defaults, ...remote, models: key==='ollama' ? (remote.models || []) : []}]
  }))
}

export default function useModels() {
  const [providers, setProviders] = useState(STATIC_PROVIDERS)
  const [source, setSource] = useState('static')
  const [reloadKey, setReloadKey] = useState(0)
  useEffect(() => {
    let cancelled = false
    api.getModels().then(data => {
      if (cancelled) return
      const n = normalize(data)
      if (n) { setProviders(n); setSource('remote') }
    })
    return () => { cancelled = true }
  }, [reloadKey])
  const refresh = () => setReloadKey(k => k+1)
  return { providers, source, refresh }
}
