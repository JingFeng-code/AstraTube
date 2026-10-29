import { useEffect, useRef, useState } from 'react'
import { ask } from '../api.js'
import useModels, { PROVIDER_ORDER, providerValue } from '../hooks/useModels.js'
import MarkdownText from './MarkdownText.jsx'
import { useI18n } from '../i18n/index.jsx'

// 問答用的模型選擇（與摘要的選擇各自獨立記憶）
const PKEY = 'ycr-ask-provider'

// 每支影片各自一份對話紀錄，key 依 video_id 區分
const HKEY_PREFIX = 'ycr-ask-'
function loadHistory(videoId) {
  if (!videoId) return []
  try { return JSON.parse(localStorage.getItem(HKEY_PREFIX + videoId)) || [] } catch { return [] }
}
function saveHistory(videoId, history) {
  if (!videoId) return
  try { localStorage.setItem(HKEY_PREFIX + videoId, JSON.stringify(history)) } catch {}
}

// 「問影片」浮動視窗內容：以當前影片為背景知識的自由聊天室（不是卡片上的 Deep Dive 功能）。
export default function AskPanel({ videoId }) {
  const { t } = useI18n()
  const [history, setHistory] = useState(() => loadHistory(videoId))
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [provider, setProviderRaw] = useState(() => {
    try { return localStorage.getItem(PKEY) || '' } catch { return '' }
  })
  const { providers } = useModels()
  const listRef = useRef(null)

  function setProvider(v) {
    setProviderRaw(v)
    try { localStorage.setItem(PKEY, v) } catch {}
  }

  // 切換影片：載入該 video_id 對應的歷史紀錄
  useEffect(() => { setHistory(loadHistory(videoId)); setError(null) }, [videoId])

  // 新訊息／等待中狀態改變時自動捲到底
  useEffect(() => { if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight }, [history, loading])

  async function send() {
    const q = input.trim()
    if (!q || !videoId || loading) return
    setError(null)
    const prevForRequest = history.map(m => ({ role: m.role, content: m.content }))
    const userMsg = { role: 'user', content: q }
    const withUser = [...history, userMsg]
    setHistory(withUser)
    saveHistory(videoId, withUser)
    setInput('')
    setLoading(true)
    try {
      const res = await ask({ question: q, video_id: videoId, history: prevForRequest, provider: provider || null })
      const assistantMsg = { role: 'assistant', content: res.answer, model: res.model_used, searched: !!res.searched }
      const withAnswer = [...withUser, assistantMsg]
      setHistory(withAnswer)
      saveHistory(videoId, withAnswer)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  function onKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  function clearChat() {
    setHistory([])
    saveHistory(videoId, [])
    setError(null)
  }

  const disabled = !videoId || loading
  const groups = PROVIDER_ORDER.map(k => providers[k] ? { key: k, ...providers[k] } : null).filter(Boolean)

  return (
    <div className="ask-panel ask-chat">
      <div className="ask-chat-head">
        <span className="ask-chat-hint">{videoId ? t('ask.hint') : t('ask.noVideo')}</span>
        <select className="ask-provider" value={provider} onChange={e => setProvider(e.target.value)}
                title={t('ask.providerTitle')}>
          <option value="">{t('ask.auto')}</option>
          {groups.map(p => (
            <optgroup key={p.key} label={p.label}>
              {p.models.map(m => <option key={`${p.key}:${m}`} value={providerValue(p.key, m)}>{m}</option>)}
            </optgroup>
          ))}
        </select>
        <button className="ask-clear" onClick={clearChat} disabled={!videoId || !history.length} title={t('ask.clearTitle')}>{t('ask.clear')}</button>
      </div>
      <div className="ask-chat-list" ref={listRef}>
        {!history.length && !loading && <p className="empty-clip">{videoId ? t('ask.example') : t('ask.noVideo')}</p>}
        {history.map((m, i) => (
          <div key={i} className={`ask-bubble ${m.role}`}>
            <div className={`ask-bubble-text ${m.role === 'assistant' ? 'ask-markdown' : ''}`}>
              {m.role === 'assistant' ? <MarkdownText>{m.content}</MarkdownText> : m.content}
            </div>
            {m.role === 'assistant' && (m.model || m.searched) && (
              <div className="ask-bubble-meta">
                {m.model && <span className="ask-model">{m.model}</span>}
                {m.searched && <span className="ask-searched" title={t('ask.searchedTitle')}>{t('ask.searched')}</span>}
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div className="ask-bubble assistant loading">
            <div className="ask-bubble-text ask-typing"><span/><span/><span/></div>
          </div>
        )}
      </div>
      {error && <p className="ask-error">{error}</p>}
      <div className="ask-input-row">
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={videoId ? t('ask.placeholder') : t('ask.noVideo')}
          disabled={disabled}
          rows={2}
        />
        <button className="btn-paper ask-send" onClick={send} disabled={disabled || !input.trim()}>{t('ask.send')}</button>
      </div>
    </div>
  )
}
