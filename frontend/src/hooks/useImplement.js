import { useCallback, useEffect, useState } from 'react'
import * as api from '../api.js'

// 影片類型 → 預設行動路線（與後端 prompts/implement.py 的 resolve_track 一致）。
// 教學型再依「有沒有程式碼」分流，這裡只做樂觀顯示，真正的判斷在後端。
export const TRACKS = ['build', 'sop', 'study', 'drill']

export function defaultTrack(contentType, hasCode) {
  if ((contentType || '') === 'tutorial') return hasCode ? 'build' : 'sop'
  return 'study'
}

// 卡片裡有沒有程式訊號（跟後端同一組判準，只用來預選按鈕文案）
const CODE_RE = /```|`[^`]+`|\b(npm|npx|pnpm|yarn|pip|brew|git|docker|curl|sudo|cd|mkdir)\s|\b(function|const|let|def|class|import|require|async|await)\b|\.(py|js|jsx|ts|tsx|json|yml|sh|html|css)\b/i

export function hasCode(cards) {
  const text = (cards || []).map(c => `${c.heading || ''} ${c.summary || ''} ${c.visual || ''}`).join(' ')
  return (text.match(CODE_RE) || []).length >= 3
}

export default function useImplement({ result, provider, t }) {
  const [open, setOpen] = useState(false)
  const [status, setStatus] = useState(null)      // /implement/status 的結果
  const [track, setTrack] = useState('')
  const [cli, setCli] = useState('')
  const [cliModel, setCliModel] = useState('')   // 留空＝用該 CLI 自己的預設模型
  const [running, setRunning] = useState(false)
  const [lines, setLines] = useState([])          // CLI 輸出（只留尾端，避免無限長）
  // 進度不假造百分比：階段是從 CLI 輸出認出來的，檔案是真的落地了才算數
  const [phase, setPhase] = useState('')
  const [liveFiles, setLiveFiles] = useState([])
  const [startedAt, setStartedAt] = useState(0)
  const [activity, setActivity] = useState(null)   // {text, at}：最近一次有意義的動作
  const [outcome, setOutcome] = useState(null)    // {kind:'done'|'manual'|'teach'|'error', ...}

  const cards = result?.cards || []
  const suggested = defaultTrack(result?.content_type, hasCode(cards))

  // 開啟時才問狀態：偵測要跑 which + --version，不值得在每次載入時做
  useEffect(() => {
    if (!open || status) return
    api.implementStatus().then(s => {
      setStatus(s)
      setCli(c => c || s.clis?.[0]?.name || '')
    })
  }, [open, status])

  const start = useCallback(() => {
    setOpen(true); setLines([]); setOutcome(null)
    setTrack(tr => tr || suggested)
  }, [suggested])

  const close = useCallback(() => { setOpen(false) }, [])

  const run = useCallback(async (opts = {}) => {
    if (running || !cards.length) return
    const useTrack = opts.track || track || suggested
    const autoRun = opts.autoRun !== undefined ? opts.autoRun : true
    setRunning(true); setLines([]); setOutcome(null); setTrack(useTrack)
    setPhase('start'); setLiveFiles([]); setStartedAt(Date.now()); setActivity(null)
    try {
      await api.implementStream({
        provider,
        video_title: result?.title || '',
        video_url: result?.source_url || '',
        content_type: result?.content_type || 'other',
        track: useTrack,
        cli: cli || null,
        cli_model: cliModel || null,
        auto_run: autoRun,
        cards,
      }, ev => {
        if (ev.type === 'line') {
          // 只留最後 200 行：CLI 輸出可能上千行，全存會讓畫面卡住
          setLines(prev => (prev.length > 200 ? [...prev.slice(-199), ev.text] : [...prev, ev.text]))
        } else if (ev.type === 'activity') {
          setActivity({ text: ev.text, at: Date.now() })
        } else if (ev.type === 'phase') {
          setPhase(ev.phase)
        } else if (ev.type === 'file_progress') {
          setLiveFiles(prev => prev.some(f => f.name === ev.file.name) ? prev : [...prev, ev.file])
        } else if (ev.type === 'start') {
          setOutcome({ kind: 'running', ...ev })
        } else if (ev.type === 'manual') {
          setOutcome(o => ({ ...(o || {}), kind: 'manual', ...ev }))
        } else if (ev.type === 'no_cli') {
          setOutcome({ kind: 'teaching' })
        } else if (ev.type === 'teach') {
          setOutcome({ kind: 'teach', content: ev.content, model: ev.model })
        } else if (ev.type === 'files') {
          setOutcome(o => ({ ...(o || {}), files: ev.files }))
        } else if (ev.type === 'done') {
          setPhase('done')
          setOutcome(o => ({ ...(o || {}), kind: 'done', ...ev }))
        } else if (ev.type === 'fatal') {
          setOutcome(o => ({ ...(o || {}), kind: 'error', ...ev }))
        }
      })
    } catch (e) {
      setOutcome({ kind: 'error', error: t('implement.failed', e.message) })
    } finally {
      setRunning(false)
    }
  }, [running, cards, track, suggested, provider, result, cli, cliModel, t])

  return { open, status, track, setTrack, cli, setCli, cliModel, setCliModel, running, lines, outcome,
           phase, liveFiles, startedAt, activity,
           suggested, cards, cardCount: cards.length, start, close, run }
}
