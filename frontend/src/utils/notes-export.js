// 沒有 Obsidian 的一般使用者，也能把已整理的重點留在自己的電腦。
function oneLine(value) {
  return String(value || '').replace(/[\r\n]+/g, ' ').trim()
}

export function markdownFilename(title) {
  const base = oneLine(title).replace(/[\\/:*?"<>|\x00-\x1f]/g, '-').replace(/\.+$/g, '').slice(0, 90).trim()
  return (base || 'AstraTube-notes') + '.md'
}

export function createNoteMarkdown({title, sourceUrl, clips = [], freeNote = ''}) {
  const lines = ['# ' + (oneLine(title) || 'AstraTube 筆記'), '']
  if (sourceUrl) {
    // 不將任意輸入插入 Markdown link 語法，避免影片網址中含特殊括號。
    lines.push('來源：' + oneLine(sourceUrl), '')
  }
  if (clips.length) {
    lines.push('## 學習重點', '')
    for (const clip of clips) {
      lines.push('### ' + (oneLine(clip.heading) || '重點'))
      if (clip.ts != null && Number.isFinite(Number(clip.ts))) {
        const secs = Math.max(0, Math.floor(Number(clip.ts)))
        lines.push('時間：' + Math.floor(secs / 60) + ':' + String(secs % 60).padStart(2, '0'))
      }
      if (clip.summary) lines.push('', String(clip.summary).trim())
      if (clip.transcript) lines.push('', '**原文**', '', '> ' + String(clip.transcript).trim().replace(/\n/g, '\n> '))
      if (clip.translation) lines.push('', '**翻譯**', '', String(clip.translation).trim())
      if (clip.visual) lines.push('', '**畫面重點**', '', String(clip.visual).trim())
      if (clip.note) lines.push('', '**我的註記**', '', String(clip.note).trim())
      lines.push('')
    }
  }
  if (freeNote.trim()) lines.push('## 隨手筆記', '', freeNote.trim(), '')
  return lines.join('\n').trimEnd() + '\n'
}
