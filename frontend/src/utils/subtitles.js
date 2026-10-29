// 字幕索引只依照影片播放時間，不由 React 渲染次數決定。
export function activeCueIndex(cues, time) {
  if (!Array.isArray(cues) || !cues.length || !Number.isFinite(time) || time < 0) return -1
  let left = 0, right = cues.length
  while (left < right) {
    const mid = Math.floor((left + right) / 2)
    if (cues[mid].start <= time) left = mid + 1
    else right = mid
  }
  const idx = left - 1
  return idx >= 0 && time < cues[idx].end ? idx : -1
}

export function visibleCues(cues, filter) {
  const q = (filter || '').trim().toLocaleLowerCase()
  return q ? cues.filter(c => [c.text, c.translation].some(s => (s || '').toLocaleLowerCase().includes(q))) : cues
}
