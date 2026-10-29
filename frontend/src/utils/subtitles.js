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


// 後端回傳的翻譯以字幕原始陣列 index 對應；其他時間戳欄位絕不改動。
export function applyTranslations(cues, translations) {
  const byId = new Map((translations || []).filter(row =>
    Number.isInteger(row?.id) && typeof row?.translation === 'string'
  ).map(row => [row.id, row.translation]))
  return cues.map((cue, idx) =>
    byId.has(idx) ? {...cue, translation:byId.get(idx)} : cue)
}


// 再次進入同一支影片時，從快取已有的翻譯之後接續；避免重頭處理。
export function nextUntranslatedIndex(cues, start=0) {
  if (!Array.isArray(cues)) return 0
  const from = Number.isInteger(start) ? Math.max(0,start) : 0
  const index = cues.findIndex((cue,i) => i >= from && !cue.translation)
  return index === -1 ? cues.length : index
}
