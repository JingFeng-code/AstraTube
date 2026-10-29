import { createContext, useContext, useMemo, useState } from 'react'
import { LANGS, STRINGS } from './strings.js'

const KEY = 'ycr-ui-lang'
const FALLBACK = 'en'

function detect() {
  try {
    const saved = localStorage.getItem(KEY)
    if (saved && STRINGS[saved]) return saved
  } catch {}
  // 沒存過就看瀏覽器語言：中文系使用者直接給中文，其餘一律英文
  try {
    const nav = (navigator.language || '').toLowerCase()
    if (nav.startsWith('zh')) return 'zh'
  } catch {}
  return FALLBACK
}

const I18nContext = createContext(null)

export function I18nProvider({ children }) {
  const [lang, setLangRaw] = useState(detect)

  const value = useMemo(() => {
    const dict = STRINGS[lang] || STRINGS[FALLBACK]
    // t(key, ...args)：值是函式就當模板呼叫，否則直接回字串。
    // 找不到 key 時回 key 本身——畫面上會看到一串 id，比空白更容易發現漏翻。
    const t = (key, ...args) => {
      const v = dict[key] ?? STRINGS[FALLBACK][key]
      if (v == null) return key
      return typeof v === 'function' ? v(...args) : v
    }
    const setLang = (next) => {
      setLangRaw(next)
      try { localStorage.setItem(KEY, next) } catch {}
      try { document.documentElement.lang = next === 'zh' ? 'zh-Hant' : next } catch {}
    }
    return { lang, setLang, t, langs: LANGS }
  }, [lang])

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n() {
  const ctx = useContext(I18nContext)
  if (!ctx) throw new Error('useI18n must be used inside <I18nProvider>')
  return ctx
}
