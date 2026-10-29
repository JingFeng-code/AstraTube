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


// 播放器上的字幕顯示模式：無／原文／中文／雙語
export const SUBTITLE_MODES = ['off', 'original', 'zh', 'bilingual']
export const DEFAULT_SUBTITLE_MODE = 'bilingual'

export function normalizeSubtitleMode(value) {
  return SUBTITLE_MODES.includes(value) ? value : DEFAULT_SUBTITLE_MODE
}

// 依模式決定播放器上要顯示哪幾行。尚未翻譯的句子在「中文」模式先顯示原文並標示待翻譯，
// 不讓畫面突然沒有字幕。
export function overlayLines(cue, mode) {
  if (!cue || mode === 'off') return []
  const text = (cue.text || '').trim()
  const translation = (cue.translation || '').trim()
  if (mode === 'original') return text ? [{kind:'original', text}] : []
  if (mode === 'zh') return translation ? [{kind:'translation', text:translation}] : (text ? [{kind:'pending', text}] : [])
  return [
    ...(translation ? [{kind:'translation', text:translation}] : []),
    ...(text ? [{kind:'original', text}] : []),
  ]
}

// 整片翻譯的下一批起點：優先從目前播放位置往後找，後面都翻好了才回頭補前面。
// 全部翻完回傳 -1。
export function nextBatchStart(cues, from = 0) {
  if (!Array.isArray(cues) || !cues.length) return -1
  const start = Number.isInteger(from) && from > 0 ? Math.min(from, cues.length - 1) : 0
  const ahead = nextUntranslatedIndex(cues, start)
  if (ahead < cues.length) return ahead
  const behind = nextUntranslatedIndex(cues, 0)
  return behind < cues.length ? behind : -1
}
