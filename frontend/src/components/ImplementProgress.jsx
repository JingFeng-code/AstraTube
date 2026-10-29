import { useEffect, useState } from 'react'
import { useI18n } from '../i18n/index.jsx'

// 階段順序。刻意不做百分比：agent 的工作量事先無法預估，假的進度條只會騙人。
// 這裡顯示的兩件事都是可驗證的事實——現在在做什麼、已經有幾個檔案落地。
const PHASES = ['start', 'think', 'verify', 'write', 'done']

function clock(ms) {
  const s = Math.max(0, Math.floor(ms / 1000))
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

export default function ImplementProgress({ phase, files, startedAt, running, activity }) {
  const { t } = useI18n()
  const [now, setNow] = useState(Date.now())

  useEffect(() => {
    if (!running) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [running])

  const active = Math.max(0, PHASES.indexOf(phase === 'run' ? 'write' : phase))
  return (
    <div className="impl-progress">
      <div className="impl-steps">
        {PHASES.map((p, i) => (
          <div key={p} className={`impl-step ${i < active ? 'done' : ''} ${i === active ? 'on' : ''}`}>
            <span className="dot"/>
            <span className="txt">{t(`implement.phase.${p}`)}</span>
          </div>
        ))}
      </div>
      {/* 階段可能停在「查證資料」好幾分鐘。沒有這一行，靜止的紅點看起來就像當掉了 */}
      {activity && <div className="impl-activity">
        <span className="impl-pulse"/>
        <span className="impl-act-text">{activity.text}</span>
        <span className="impl-act-age mono">{t('implement.agoSeconds', Math.max(0, Math.round((now - activity.at) / 1000)))}</span>
      </div>}
      <div className="impl-meta">
        <span>{t('implement.filesSoFar', files.length)}</span>
        <span className="mono">{clock(now - startedAt)}</span>
      </div>
      {files.length > 0 && <ul className="impl-live">
        {files.map(f => <li key={f.name}><span className="impl-file">{f.name}</span></li>)}
      </ul>}
    </div>
  )
}
