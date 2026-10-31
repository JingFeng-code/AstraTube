import { useEffect, useRef, useState } from 'react'
import { importSubtitleFile, importedSubtitleStatus, removeImportedSubtitles } from '../api.js'
import { useI18n } from '../i18n/index.jsx'

const MAX_FILE_SIZE = 1024 * 1024

// onAnalyze 只在分析失敗後的錯誤區傳入：匯入完可以直接開始，不必再回頭找「開始」按鈕
export default function SubtitleImportControls({ videoUrl, onChanged, onAnalyze }) {
  const { t } = useI18n()
  const inputRef = useRef(null)
  const [state, setState] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    let alive = true
    setState(null)
    setError('')
    setMessage('')
    if (!videoUrl.trim()) return
    const timer = setTimeout(() => {
      importedSubtitleStatus(videoUrl).then(result => {
        if (alive) setState(result)
      }).catch(() => {
        if (alive) setState(null)
      })
    }, 400)
    return () => { alive = false; clearTimeout(timer) }
  }, [videoUrl, revision])

  async function selected(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    if (!videoUrl.trim()) { setError(t('subtitles.importNoUrl')); return }
    if (!/\.(srt|vtt)$/i.test(file.name)) { setError(t('subtitles.importFormat')); return }
    if (file.size > MAX_FILE_SIZE) { setError(t('subtitles.importLarge')); return }
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const text = await file.text()
      const result = await importSubtitleFile(videoUrl, file.name, text)
      setMessage(t('subtitles.importSuccess', result.cue_count))
      setRevision(v => v+1)
      onChanged?.()
    } catch (exc) {
      setError(t('subtitles.importFailed', exc.message))
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (!state?.exists || busy) return
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await removeImportedSubtitles(videoUrl)
      setMessage(t('subtitles.importRemoved'))
      setRevision(v => v+1)
      onChanged?.()
    } catch (exc) {
      setError(t('subtitles.importFailed', exc.message))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="subtitle-import-bar" aria-label={t('subtitles.importAction')}>
      <input ref={inputRef} type="file" accept=".srt,.vtt,text/vtt,application/x-subrip"
             onChange={selected} hidden aria-label={t('subtitles.importAction')}/>
      <button type="button" className="btn-paper" disabled={busy || !videoUrl.trim()}
              onClick={() => inputRef.current?.click()}>
        {busy?t('subtitles.importLoading'):t('subtitles.importAction')}
      </button>
      {onAnalyze && state?.exists && <button type="button" className="import-start"
          disabled={busy} onClick={onAnalyze}>{t('subtitles.importAnalyze')}</button>}
      {state?.exists && <button type="button" className="btn-paper"
          disabled={busy} onClick={remove}>{t('subtitles.removeAction')}</button>}
      {state?.exists && <span className="import-status">
        {t('subtitles.importPresent',state.format,state.cue_count)}
      </span>}
      {message && <span className="import-status" role="status">{message}</span>}
      {error && <span className="import-error" role="alert">{error}</span>}
      {!state?.exists && <span className="import-hint">{t(onAnalyze ? 'subtitles.importNoFile' : 'subtitles.importHint')}</span>}
    </section>
  )
}
