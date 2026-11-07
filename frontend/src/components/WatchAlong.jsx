import { useEffect, useRef, useState } from 'react'
import { cancelWatch, finishWatch, getSpeechStatus, getWatchStatus, sendWatchHeartbeat, startSpeechModelDownload, startWatch, updateWatchRegion } from '../api.js'
import { useI18n } from '../i18n/index.jsx'
import { formatClock, playerRegion } from '../utils/watch.js'
import { speechPercent } from '../utils/local-video.js'
import { YouTubePlayer } from './VideoPane.jsx'

const POLL_MS = 1000
const HEARTBEAT_MS = 2000

// 陪看模式：使用者照常播放官方播放器，AstraTube 記下自己播出的聲音和播放器畫面。
// 不下載影片；聲音交給本機語音轉文字，畫面交給本機 Ollama 視覺模型。
export default function WatchAlong({ target, onFinished, onClose }) {
  const { t } = useI18n()
  const frameRef = useRef(null)
  const lastBeat = useRef(0)
  const [support, setSupport] = useState(null)
  const [session, setSession] = useState({ state: 'idle' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const running = session.state === 'running'
  // YouTube 可以由程式開始播放：按下開始陪看就從目前位置播放，不必再點播放器
  const [startAt, setStartAt] = useState({ t: 0, key: 0, auto: false })
  const position = useRef(0)
  const [download, setDownload] = useState(null)

  const runningRef = useRef(false)
  useEffect(() => { runningRef.current = running }, [running])

  useEffect(() => {
    let alive = true
    getWatchStatus().then(result => { if (alive) setSupport(result) })
      .catch(() => { if (alive) setSupport({ available: false }) })
    return () => {
      alive = false
      // 換網址、切到本地影片或關掉陪看時元件會卸載：一定要停止擷取，
      // 否則舊的錄製會在背景繼續，之後還可能把別支影片的內容存到這支影片底下
      if (runningRef.current) cancelWatch().catch(() => {})
    }
  }, [])

  useEffect(() => {
    if (!running) return
    const timer = setInterval(() => {
      getWatchStatus().then(result => { if (result.session) setSession(result.session) }).catch(() => {})
    }, POLL_MS)
    // 視窗大小改變時播放器位置也會變，要告訴後端新的裁切範圍
    const observer = new ResizeObserver(() => {
      if (frameRef.current) updateWatchRegion(playerRegion(frameRef.current)).catch(() => {})
    })
    if (frameRef.current) observer.observe(frameRef.current)
    return () => { clearInterval(timer); observer.disconnect() }
  }, [running])

  // 陪看要用本機語音轉文字；模型和本地影片共用，按下才下載
  useEffect(() => {
    if (download?.state !== 'downloading') return
    const timer = setInterval(async () => {
      try {
        const speech = await getSpeechStatus()
        setDownload(speech.download)
        if (speech.model_ready) { setDownload(null); setSupport(await getWatchStatus()) }
        else if (speech.download.state === 'error') setError(speech.download.error)
      } catch { /* 下一輪再試 */ }
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [download?.state])

  async function downloadModel() {
    setError('')
    try { setDownload(await startSpeechModelDownload()) } catch (exc) { setError(exc.message) }
  }

  function onTime(seconds) {
    position.current = seconds
    const now = Date.now()
    if (!running || now - lastBeat.current < HEARTBEAT_MS) return
    lastBeat.current = now
    sendWatchHeartbeat(seconds).catch(() => {})
  }

  async function start() {
    setBusy(true); setError('')
    try {
      setSession(await startWatch({ platform: target.platform, video_id: target.videoId, page: target.page,
        region: playerRegion(frameRef.current), offset: 0 }))
      if (target.platform === 'youtube') setStartAt(previous => ({ t: position.current, key: previous.key + 1, auto: true }))
    } catch (exc) { setError(exc.message) } finally { setBusy(false) }
  }
  async function finish() {
    setBusy(true); setError('')
    try {
      const result = await finishWatch()
      setSession(result)
      if (result.state === 'done') onFinished?.()
      else setError(result.error)
    } catch (exc) { setError(exc.message) } finally { setBusy(false) }
  }
  async function cancel() {
    if (running) await cancelWatch().catch(() => {})
    onClose?.()
  }

  const biliSrc = `https://player.bilibili.com/player.html?bvid=${target.videoId}&p=${target.page}&autoplay=0`
  const warnings = session.warnings || []
  return (
    <section className="watch-along" aria-label={t('watch.title')}>
      <div className="watch-head">
        <strong>{t('watch.title')}</strong>
        <button type="button" className="btn-paper" onClick={cancel} disabled={busy}>{t(running ? 'watch.cancel' : 'watch.close')}</button>
      </div>
      <div className="video-frame watch-frame" ref={frameRef}>
        {target.platform === 'youtube' ?
          <YouTubePlayer videoId={target.videoId} startAt={startAt} onTime={onTime} /> :
          <iframe src={biliSrc} title="Bilibili" allow="autoplay; encrypted-media; picture-in-picture" allowFullScreen />}
      </div>
      <div className="watch-controls">
        {!support ? <span className="watch-hint">{t('watch.checking')}</span> :
          !support.available ? <span className="watch-hint">{t('watch.unavailable')}</span> :
          !support.speech_ready ? (download?.state === 'downloading' ?
            <span role="status" className="watch-hint">{t('local.speechDownloading', speechPercent(download.done, download.total))}</span> :
            <><button type="button" className="btn-paper" onClick={downloadModel}>{t('local.speechDownload')}</button>
              <span className="watch-hint">{t('watch.needSpeech')}</span></>) :
          running ?
            <>
              <span role="status" className="watch-live">{t('watch.recording', formatClock(session.elapsed), session.cue_count || 0, session.visual_count || 0)}</span>
              <button type="button" className="import-start" onClick={finish} disabled={busy}>{t(busy ? 'watch.finishing' : 'watch.finish')}</button>
            </> :
            <button type="button" className="import-start" onClick={start} disabled={busy || session.state === 'finishing'}>{t('watch.start')}</button>}
      </div>
      <p className="watch-hint">{t(running ? 'watch.playHint' : 'watch.intro')}</p>
      {running && session.vision_model && <p className="watch-hint">{t('watch.visionModel', session.vision_model)}</p>}
      {warnings.includes('no_vision_model') && <p className="watch-hint">{t('watch.noVisionModel')}</p>}
      {warnings.includes('frames_stalled') && <p className="import-error" role="alert">{t('watch.framesStalled')}</p>}
      {warnings.includes('frames_unavailable') && <p className="import-error" role="alert">{t('watch.framesUnavailable')}</p>}
      {warnings.includes('vision_failed') && <p className="watch-hint">{t('watch.visionFailed')}</p>}
      {(error || session.error) && <p className="import-error" role="alert">{error || session.error}</p>}
      {running && session.recent?.length > 0 && <ul className="watch-recent">
        {session.recent.map((line, index) => <li key={index}><span>{formatClock(line.t)}</span>{line.text}</li>)}
      </ul>}
    </section>
  )
}
