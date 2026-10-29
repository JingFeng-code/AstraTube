import { useEffect, useState } from 'react'
import * as api from '../api.js'

// 後端 /models 尚未就緒或抓取失敗時的退回清單。
// free: 不需金鑰就能用；configured: 是否已填金鑰（離線時無從得知，一律當 false）。
export const STATIC_PROVIDERS = {
  opencode: {
    label: 'OpenCode', free: true, configured: true, source: 'static',
    models: ['deepseek-v4-flash-free','big-pickle','mimo-v2.5-free','laguna-s-2.1-free','ling-3.0-flash-free','ling-3.0-tiny-free','nemotron-3-ultra-free','north-mini-code-free','longcat-2.0-free'],
  },
  gemini: { label: 'Google Gemini', free: false, configured: false, source: 'static', models: ['gemini-3.5-flash-lite'] },
  deepseek: { label: 'DeepSeek', free: false, configured: false, source: 'static', models: ['deepseek-chat','deepseek-reasoner'] },
  openai: { label: 'OpenAI', free: false, configured: false, source: 'static', models: ['gpt-5.1','gpt-5.1-mini','gpt-4.1','gpt-4o-mini'] },
  anthropic: { label: 'Anthropic Claude', free: false, configured: false, source: 'static', models: ['claude-opus-5','claude-sonnet-5','claude-opus-4-8','claude-haiku-4-5'] },
}

// 下拉選單的供應商顯示順序：免費的排最前，其餘依常用度
export const PROVIDER_ORDER = ['opencode', 'gemini', 'deepseek', 'openai', 'anthropic']

// Gemini 在後端是「整個供應商只有一個模型」，provider 字串就是 "gemini"（不帶 :model）
export const providerValue = (kind, model) => (kind === 'gemini' ? 'gemini' : `${kind}:${model}`)

function normalize(data) {
  if (!data) return null
  if (data.providers && typeof data.providers === 'object') {
    const out = {}
    for (const key of PROVIDER_ORDER) {
      const p = data.providers[key]
      if (p && Array.isArray(p.models) && p.models.length) {
        out[key] = { ...STATIC_PROVIDERS[key], ...p }
      } else if (STATIC_PROVIDERS[key]) {
        out[key] = STATIC_PROVIDERS[key]
      }
    }
    return out
  }
  // 舊版後端只回 {gemini:[], opencode:[]}
  if (Array.isArray(data.opencode) || Array.isArray(data.gemini)) {
    return {
      ...STATIC_PROVIDERS,
      opencode: { ...STATIC_PROVIDERS.opencode, models: data.opencode || STATIC_PROVIDERS.opencode.models },
      gemini: { ...STATIC_PROVIDERS.gemini, models: data.gemini || STATIC_PROVIDERS.gemini.models },
    }
  }
  return null
}

// 掛載時抓 GET /models 供模型下拉選單使用；失敗一律退回內建靜態清單
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
  // 存完設定後呼叫，讓「已填金鑰」狀態與動態模型清單立刻更新
  const refresh = () => setReloadKey(k => k + 1)
  return { providers, source, refresh }
}
