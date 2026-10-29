import { useState } from 'react'
import * as api from '../api.js'
import { pickField, youtubeLink, TRANSCRIPT_KEYS, TRANSLATION_KEYS } from '../utils.js'

// 卡片瀏覽／摘進筆記／Deep Dive 狀態，圍繞目前的摘要結果 (result) 運作
export default function useCards(result, provider, initial = {}) {
  const cards = result?.cards || []
  const [index, setIndexRaw] = useState(initial.index || 0)
  const [startAt, setStartAt] = useState({ t: 0, auto: false, key: 0 })
  const [deepdives, setDeepdives] = useState(initial.deepdives || {})
  const [ddLoading, setDdLoading] = useState(null)
  const [clips, setClips] = useState(initial.clips || [])
  const clippedIds = new Set(clips.map(c => c.cardIndex))

  function jumpToCard(i, play = false) {
    setIndexRaw(i)
    const t = cards[i]?.timestamp_seconds
    if (play && t != null) setStartAt(s => ({ t: Math.floor(t), auto: true, key: s.key + 1 }))
  }

  function clipCard(i) {
    const c = cards[i]
    if (!c || clippedIds.has(i)) return null
    const clip = {
      id: Date.now() + '-' + i, cardIndex: i, heading: c.heading, summary: c.summary,
      transcript: pickField(c, TRANSCRIPT_KEYS), translation: pickField(c, TRANSLATION_KEYS),
      visual: c.visual || null,
      ts: c.timestamp_seconds ?? null,
      link: result?.youtube_video_id != null ? youtubeLink(result.youtube_video_id, c.timestamp_seconds) : result?.source_url || null,
      note: '',
    }
    setClips(prev => [...prev, clip])
    return c
  }
  function removeClip(id) { setClips(prev => prev.filter(c => c.id !== id)) }
  function updateClipNote(id, note) { setClips(prev => prev.map(c => c.id === id ? { ...c, note } : c)) }

  async function handleDeepDive(i) {
    const c = cards[i]
    if (!c || deepdives[i] || ddLoading != null) return
    setDdLoading(i)
    try {
      const data = await api.deepdive(provider, result.title, { heading: c.heading, summary: c.summary, timestamp_seconds: c.timestamp_seconds ?? null })
      const text = typeof data === 'string' ? data : (data.content || JSON.stringify(data))
      setDeepdives(prev => ({ ...prev, [i]: { text, model: (data && data.model_used) || '' } }))
    } finally {
      setDdLoading(null)
    }
  }

  function resetForNewResult() {
    setIndexRaw(0); setDeepdives({}); setClips([]); setStartAt({ t: 0, auto: false, key: 0 })
  }

  return {
    index, setIndex: i => jumpToCard(i, true), jumpToCard, startAt,
    clips, setClips, clippedIds, clipCard, removeClip, updateClipNote,
    deepdives, ddLoading, handleDeepDive, resetForNewResult,
  }
}
