// 和 index.css 單欄版面的斷點一致
export const NARROW_QUERY = '(max-width:980px)'

// 寬螢幕的重點固定在右欄，所以分頁只有字幕和章節；單欄時重點才需要自己的分頁。
export function resultTabs(narrow) {
  return narrow ? ['cards', 'subtitles', 'chapters'] : ['subtitles', 'chapters']
}

// 視窗跨過斷點時，原本選的分頁可能不存在，這時退回第一個分頁
export function effectiveResultTab(tab, narrow) {
  const tabs = resultTabs(narrow)
  return tabs.includes(tab) ? tab : tabs[0]
}
