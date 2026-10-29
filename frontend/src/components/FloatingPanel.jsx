import { useState } from 'react'
import { useI18n } from '../i18n/index.jsx'

// 可最小化的浮動視窗：最小化時縮成角落小圖示，展開為 overlay 浮層（不擠壓主版面）。
// 開合狀態記在 localStorage，key 依 id 區分（例如 notes / ask）。
const KEY_PREFIX = 'ycr-panel-'
function readMinimized(id, def) {
  try { const v = localStorage.getItem(KEY_PREFIX + id); return v == null ? def : v === '1' } catch { return def }
}
function writeMinimized(id, val) {
  try { localStorage.setItem(KEY_PREFIX + id, val ? '1' : '0') } catch {}
}

export default function FloatingPanel({ id, corner = 'br', title, icon, badge, children, defaultMinimized = true }) {
  const { t } = useI18n()
  const [minimized, setMinimized] = useState(() => readMinimized(id, defaultMinimized))
  function toggle(next) { setMinimized(next); writeMinimized(id, next) }
  return (
    <div className={`float-panel ${corner}`}>
      {minimized ? (
        <button className="float-chip" onClick={() => toggle(false)} aria-label={t('panel.expand', title)} title={title}>
          <span>{icon}</span>
          {badge ? <span className="badge">{badge}</span> : null}
        </button>
      ) : (
        <div className="float-window" role="dialog" aria-label={title}>
          <div className="float-window-head">
            <h3>{icon} {title}</h3>
            <button className="float-window-min" onClick={() => toggle(true)} aria-label={t('panel.minimize')}>─</button>
          </div>
          <div className="float-window-body">{children}</div>
        </div>
      )}
    </div>
  )
}
