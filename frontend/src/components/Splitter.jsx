import { useCallback, useRef } from 'react'

// 影片欄／重點欄之間的可拖曳分隔線。
// 拖曳中只直接改 DOM 上的 CSS 變數 --split（避免每次 pointermove 都觸發整棵樹 re-render），
// 放開滑鼠才把最終值回報給上層（onCommit）去 setState + 寫 localStorage。
const MIN_PCT = 20
const MAX_PCT = 80

export default function Splitter({ onCommit }) {
  const latest = useRef(50)

  const handlePointerDown = useCallback((e) => {
    if (e.button !== undefined && e.button !== 0) return
    const trackEl = e.currentTarget
    const containerEl = trackEl.parentElement
    if (!containerEl) return
    trackEl.setPointerCapture(e.pointerId)
    trackEl.classList.add('dragging')
    document.body.style.userSelect = 'none'

    function move(ev) {
      const rect = containerEl.getBoundingClientRect()
      if (!rect.width) return
      let pct = ((ev.clientX - rect.left) / rect.width) * 100
      pct = Math.min(MAX_PCT, Math.max(MIN_PCT, pct))
      latest.current = pct
      containerEl.style.setProperty('--split', pct.toFixed(2))
    }
    function up() {
      try { trackEl.releasePointerCapture(e.pointerId) } catch {}
      trackEl.classList.remove('dragging')
      document.body.style.userSelect = ''
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      onCommit(latest.current)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }, [onCommit])

  function handleDoubleClick(e) {
    const containerEl = e.currentTarget.parentElement
    containerEl?.style.setProperty('--split', '50')
    onCommit(50)
  }

  return (
    <div
      className="splitter"
      onPointerDown={handlePointerDown}
      onDoubleClick={handleDoubleClick}
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize video / cards split"
      title="Drag to resize, double-click to reset 50/50"
    />
  )
}
