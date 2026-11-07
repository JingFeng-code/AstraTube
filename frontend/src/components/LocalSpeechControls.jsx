import { useEffect, useRef, useState } from 'react'
import { cancelSpeechModelDownload, cancelTranscribe, getSpeechStatus, getTranscribeStatus, startSpeechModelDownload, uploadLocalVideo } from '../api.js'
import { useI18n } from '../i18n/index.jsx'
import { speechPercent } from '../utils/local-video.js'

const POLL_MS = 1000

// 本機語音轉文字：模型要使用者按下才下載；影片只傳到這台電腦上的後端，轉完就刪除。
export default function LocalSpeechControls({ file, videoId, onDone }) {
  const { t } = useI18n()
  const [speech, setSpeech] = useState(null)
  const [job, setJob] = useState({ state: 'idle', progress: 0 })
  const [error, setError] = useState('')
  const aliveRef = useRef(true)
  const uploadRef = useRef(null)
  const onDoneRef = useRef(onDone)
  useEffect(() => { onDoneRef.current = onDone }, [onDone])

  const downloading = speech?.download?.state === 'downloading'
  const working = job.state === 'uploading' || job.state === 'running'

  useEffect(() => {
    aliveRef.current = true
    getSpeechStatus().then(result => { if (aliveRef.current) setSpeech(result) }).catch(() => {})
    return () => { aliveRef.current = false; uploadRef.current?.abort() }
  }, [])

  useEffect(() => {
    if (!downloading) return
    const timer = setInterval(() => {
      getSpeechStatus().then(result => { if (aliveRef.current) setSpeech(result) }).catch(() => {})
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [downloading])

  useEffect(() => {
    if (job.state !== 'running') return
    const timer = setInterval(async () => {
      try {
        const result = await getTranscribeStatus(videoId)
        if (!aliveRef.current) return
        setJob(result)
        if (result.state === 'done') onDoneRef.current?.()
        if (result.state === 'error') setError(result.error)
      } catch { /* 下一輪再試 */ }
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [job.state, videoId])

  // 切換畫面後元件會重新掛載，但後端的工作還在跑：要接回進度和取消按鈕
  useEffect(() => {
    setJob({ state: 'idle', progress: 0 })
    setError('')
    let current = true
    getTranscribeStatus(videoId).then(result => {
      if (current && aliveRef.current && result.state === 'running') setJob(result)
    }).catch(() => {})
    return () => { current = false }
  }, [videoId])

  async function downloadModel() {
    setError('')
    try { setSpeech(previous => ({ ...previous, download: { ...previous.download, ...{ state: 'downloading' } } })); await startSpeechModelDownload() } catch (exc) { setError(exc.message); getSpeechStatus().then(setSpeech).catch(() => {}) }
  }
  async function start() {
    setError('')
    setJob({ state: 'uploading', progress: 0 })
    const upload = uploadLocalVideo(videoId, file, value => { if (aliveRef.current) setJob({ state: 'uploading', progress: value }) })
    uploadRef.current = upload
    try {
      await upload.promise
      if (aliveRef.current) setJob({ state: 'running', progress: 0 })
    } catch (exc) {
      if (aliveRef.current) { setJob({ state: 'idle', progress: 0 }); if (!upload.aborted) setError(exc.message) }
    } finally { uploadRef.current = null }
  }
  function cancel() {
    if (job.state === 'uploading') uploadRef.current?.abort()
    else cancelTranscribe(videoId).catch(() => {})
  }

  if (!speech) return null
  if (!speech.available_here || !speech.engine) {
    return <p className="local-speech-hint">{t(speech.available_here ? 'local.speechNoEngine' : 'local.speechRemote')}</p>
  }
  if (!speech.model_ready) {
    return <div className="local-speech" aria-label={t('local.speechAction')}>
      {downloading ?
        <>
          <span role="status">{t('local.speechDownloading', speechPercent(speech.download.done, speech.download.total))}</span>
          <button type="button" className="btn-paper" onClick={() => cancelSpeechModelDownload().catch(() => {})}>{t('settings.cancel')}</button>
        </> :
        <button type="button" className="btn-paper" onClick={downloadModel}>{t('local.speechDownload')}</button>}
      <span className="local-speech-hint">{t('local.speechDownloadHint')}</span>
      {(error || speech.download?.error) && <span className="import-error" role="alert">{error || speech.download.error}</span>}
    </div>
  }
  return <div className="local-speech" aria-label={t('local.speechAction')}>
    {working ?
      <>
        <span role="status">{t(job.state === 'uploading' ? 'local.speechReading' : 'local.speechRunning', speechPercent(job.progress, 1))}</span>
        <button type="button" className="btn-paper" onClick={cancel}>{t('settings.cancel')}</button>
      </> :
      <button type="button" className="btn-paper" disabled={!file} onClick={start}>{t('local.speechAction')}</button>}
    <span className="local-speech-hint">{t(file ? 'local.speechHint' : 'local.speechRepick')}</span>
    {error && <span className="import-error" role="alert">{error}</span>}
  </div>
}
