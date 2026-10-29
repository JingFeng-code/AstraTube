import { useState } from 'react'
import * as api from '../api.js'

// 串流生成重點：封裝 NDJSON 事件解析、樂觀顯示與生成進度追蹤。
export default function useSummarizeStream({ initialResult = null, onSegError, t } = {}) {
  const [result, setResult] = useState(initialResult)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [progress, setProgress] = useState(null)

  async function summarize(url, provider, deepVisual=false) {
    const u = url.trim()
    if (!u || loading) return null
    const startedAt = Date.now()
    setLoading(true); setError(''); setResult(null); setProgress({ stage: 'source', completed: 0, total: 0, startedAt })
    const draft = { title: '', source_type: '', source_url: u, youtube_video_id: null, cards: [], model_used: '', segments: 0, transcript_source: null, content_type: 'other' }
    let segsDone = 0
    try {
      await api.summarizeStream(u, provider, deepVisual, ev => {
        if (ev.type === 'progress') {
          setProgress(p => ({ ...p, stage: ev.stage, completed: ev.completed || 0, total: ev.total || 0, startedAt: p?.startedAt || startedAt }))
        } else if (ev.type === 'meta') {
          draft.source_type = ev.source_type; draft.youtube_video_id = ev.youtube_video_id
          draft.segments = ev.segments; draft.transcript_source = ev.transcript_source || null
          setProgress({ stage: 'generate', state: 'starting', completed: 0, total: ev.segments, startedAt })
        } else if (ev.type === 'segment_status') {
          setProgress(p => ({ ...p, stage: 'generate', state: ev.state, seg: ev.seg,
            provider: ev.provider || p?.provider, model: ev.model || p?.model,
            attempt: ev.attempt, tries: ev.tries, delay: ev.delay, phase: ev.phase }))
        } else if (ev.type === 'title') {
          draft.title = ev.title
        } else if (ev.type === 'cards') {
          segsDone++
          draft.cards = [...draft.cards, ...(ev.cards || [])]
          // 先採用第一個非 other 的段落判定（開場段常判 other），done 事件再用多數決校正
          if (ev.content_type && ev.content_type !== 'other' && draft.content_type === 'other') draft.content_type = ev.content_type
          if (ev.model && !draft.model_used.includes(ev.model)) draft.model_used = draft.model_used ? draft.model_used + '、' + ev.model : ev.model
          setResult({ ...draft }); setLoading(false)
          setProgress(p => ({ ...p, stage: 'generate', state: 'next', completed: segsDone, total: draft.segments, startedAt }))
        } else if (ev.type === 'seg_error') {
          segsDone++; setProgress(p => ({ ...p, stage: 'generate', state: 'next', completed: segsDone, total: draft.segments, startedAt })); onSegError?.(ev)
        } else if (ev.type === 'fatal') {
          throw new Error(ev.error)
        } else if (ev.type === 'done') {
          draft.title = draft.title || ev.title; draft.model_used = ev.model_used || draft.model_used
          draft.content_type = ev.content_type || draft.content_type
          setResult({ ...draft }); setProgress(null)
        }
      })
      if (!draft.cards.length) setError(t('error.noCards'))
    } catch (e) {
      setError(t('error.generate', e.message))
    } finally {
      setLoading(false); setProgress(null)
    }
    return draft
  }

  return { result, setResult, loading, error, progress, summarize }
}
