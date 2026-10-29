import { useEffect, useState } from 'react'
import * as api from '../api.js'
import { buildMarkdown } from '../utils.js'

// Obsidian vault 連線狀態、資料夾/筆記清單、存檔選項與存檔動作
export default function useNotesVault(initialSaveOpts) {
  const [vault, setVault] = useState({ configured: false, exists: false, path: null })
  const [folders, setFolders] = useState([])
  const [noteFiles, setNoteFiles] = useState([])
  const [saveOpts, setSaveOpts] = useState(initialSaveOpts || { folder: '', mode: 'new', targetFile: '' })
  const [saving, setSaving] = useState(false)

  function refresh() {
    api.notesStatus().then(v => {
      setVault(v)
      if (v.configured) api.notesFolders().then(r => {
        setFolders(r.folders || [])
        setSaveOpts(s => ({ ...s, folder: s.folder || r.default || '' }))
      })
    })
  }
  useEffect(() => { refresh() }, [])
  // 切到「附加到現有筆記」或更換資料夾時，載入該資料夾的筆記清單
  useEffect(() => {
    if (saveOpts.mode === 'append' && vault.configured) api.notesFiles(saveOpts.folder).then(r => setNoteFiles(r.files || []))
  }, [saveOpts.folder, saveOpts.mode, vault.configured])

  const onSaveOptsChange = patch => setSaveOpts(prev => {
    const next = { ...prev, ...patch }
    if ('folder' in patch) next.targetFile = ''
    return next
  })

  // t 由呼叫端傳入：筆記內容的區塊標題要跟著介面語言走
  async function save({ title, sourceUrl, clips, freeNote, t }) {
    if (saving) return null
    if (saveOpts.mode === 'append' && !saveOpts.targetFile) throw new Error(t('error.pickNote'))
    const md = buildMarkdown({ title, sourceUrl, clips, freeNote, mode: saveOpts.mode, t })
    setSaving(true)
    try {
      const res = await api.saveNote({ filename: title, content: md, folder: saveOpts.folder, mode: saveOpts.mode, target_file: saveOpts.targetFile })
      if (saveOpts.mode === 'append') api.notesFiles(saveOpts.folder).then(r => setNoteFiles(r.files || []))
      return res
    } finally {
      setSaving(false)
    }
  }

  return { vault, folders, noteFiles, saveOpts, onSaveOptsChange, saving, save, refresh }
}
