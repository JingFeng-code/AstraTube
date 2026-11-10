import { useEffect, useRef, useState } from 'react'
import { cancelWatch, finishWatch, getSpeechStatus, getWatchStatus, getWatchVisionModels, sendWatchHeartbeat, startSpeechModelDownload, startWatch, updateWatchRegion } from '../api.js'
import { useI18n } from '../i18n/index.jsx'
import { VISION_OFF, formatClock, pickVisionModel, playerRegion, watchPhase } from '../utils/watch.js'
import { speechPercent } from '../utils/local-video.js'
import { YouTubePlayer } from './VideoPane.jsx'

const POLL_MS = 1000
const HEARTBEAT_MS = 2000
const VISION_KEY = 'astra.watch.visionModel'

function savedVision() {
  try { return window.localStorage.getItem(VISION_KEY) || '' } catch { return '' }
}
function saveVision(value) {
  try { window.localStorage.setItem(VISION_KEY, value) } catch { /* 無痕視窗等情況存不了，下次重選即可 */ }
}

// 陪看模式：使用者照常播放官方播放器，AstraTube 記下自己播出的聲音和播放器畫面。
// 不下載影片；聲音交給本機語音轉文字，畫面交給使用者選的本機 Ollama 視覺模型。
//
// 版面原則（實機驗收回饋）：
// - 主要動作只有一個按鈕：開始前是「開始陪看」，開始後是「完成並整理重點」，都在狀態列右邊。
// - 會丟掉記錄的「放棄」是不起眼的文字按鈕，而且要再確認一次。
// - 狀態跟著播放器走：暫停、播完時要看得出來，不能一直顯示「陪看中」。
export default function WatchAlong({ target, provider, onFinished, onClose }) {
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
  const [clock, setClock] = useState(0)
  const [playerState, setPlayerState] = useState('waiting')
  const [download, setDownload] = useState(null)
  const [models, setModels] = useState(null)
  const [vision, setVision] = useState('')
  const [confirmDiscard, setConfirmDiscard] = useState(false)

  const runningRef = useRef(false)
  useEffect(() => { runningRef.current = running; if (!running) setConfirmDiscard(false) }, [running])

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

  // 看畫面的模型清單：只有本機已安裝、能看圖的 Ollama 模型
  useEffect(() => {
    if (!support?.available) return
    let alive = true
    getWatchVisionModels().then(result => {
      if (!alive) return
      const list = result.models || []
      setModels(list)
      setVision(pickVisionModel(list, savedVision(), provider))
    }).catch(() => { if (alive) { setModels([]); setVision(VISION_OFF) } })
    return () => { alive = false }
  }, [support?.available])

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

  function onTime(seconds, state) {
    position.current = seconds
    if (state) setPlayerState(state)
    setClock(Math.floor(seconds))
    const now = Date.now()
    if (!running || now - lastBeat.current < HEARTBEAT_MS) return
    lastBeat.current = now
    sendWatchHeartbeat(seconds).catch(() => {})
  }

  function chooseVision(value) {
    setVision(value)
    saveVision(value)
  }

  async function start() {
    setBusy(true); setError('')
    try {
      const useVision = vision !== VISION_OFF
      setSession(await startWatch({ platform: target.platform, video_id: target.videoId, page: target.page,
        region: playerRegion(frameRef.current), offset: 0,
        use_vision: useVision, vision_model: useVision && vision ? vision : null }))
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
  async function discard() {
    setConfirmDiscard(false)
    await cancelWatch().catch(() => {})
    onClose?.()
  }

  const biliSrc = `https://player.bilibili.com/player.html?bvid=${target.videoId}&p=${target.page}&autoplay=0`
  const warnings = session.warnings || []
  const phase = watchPhase({ platform: target.platform, playerState, audible: session.audible })
  const shownClock = formatClock(target.platform === 'youtube' ? clock : session.elapsed)
  const ready = support?.available && support.speech_ready

  let bar
  if (!support) bar = <span className="watch-hint">{t('watch.checking')}</span>
  else if (!support.available) bar = <span className="watch-hint">{t('watch.unavailable')}</span>
  else if (!support.speech_ready) {
    bar = download?.state === 'downloading' ?
      <span role="status" className="watch-hint">{t('local.speechDownloading', speechPercent(download.done, download.total))}</span> :
      <><span className="watch-hint">{t('watch.needSpeech')}</span>
        <button type="button" className="import-start" onClick={downloadModel}>{t('local.speechDownload')}</button></>
  } else if (running || session.state === 'finishing') {
    bar = <>
      <span role="status" className={`watch-state watch-state-${phase}`}>
        <i aria-hidden="true" />{t(`watch.state.${phase}`, shownClock)}
      </span>
      <span className="watch-counts">{t('watch.counts', session.cue_count || 0, session.visual_count || 0)}</span>
      <button type="button" className={`import-start watch-primary ${phase === 'ended' ? 'is-ready' : ''}`} onClick={finish} disabled={busy}>
        {t(busy ? 'watch.finishing' : 'watch.finish')}
      </button>
    </>
  } else {
    bar = <>
      <label className="watch-model">
        <span>{t('watch.modelLabel')}</span>
        <select value={vision} onChange={event => chooseVision(event.target.value)} disabled={models === null || busy}>
          {models === null && <option value="">{t('watch.modelLoading')}</option>}
          {(models || []).map(name => <option key={name} value={name}>{name}</option>)}
          {models !== null && <option value={VISION_OFF}>{t('watch.modelOff')}</option>}
        </select>
      </label>
      <button type="button" className="import-start watch-primary" onClick={start} disabled={busy || models === null}>{t('watch.start')}</button>
    </>
  }

  return (
    <section className="watch-along" aria-label={t('watch.title')}>
      <div className="watch-head">
        <strong>{t('watch.title')}</strong>
        {!running && session.state !== 'finishing' && <button type="button" className="btn-paper" onClick={onClose} disabled={busy}>{t('watch.close')}</button>}
      </div>
      <div className="video-frame watch-frame" ref={frameRef}>
        {target.platform === 'youtube' ?
          <YouTubePlayer videoId={target.videoId} startAt={startAt} onTime={onTime} /> :
          <iframe src={biliSrc} title="Bilibili" allow="autoplay; encrypted-media; picture-in-picture" allowFullScreen />}
      </div>
      <div className="watch-bar">{bar}</div>
      {running && <div className="watch-sub">
        <span className="watch-hint">{session.vision_model ? t('watch.visionModel', session.vision_model) : t('watch.audioOnly')}</span>
        {confirmDiscard ?
          <span className="watch-discard-confirm" role="alert">
            {t('watch.discardConfirm')}
            <button type="button" className="btn-paper danger" onClick={discard}>{t('watch.discardYes')}</button>
            <button type="button" className="btn-paper" onClick={() => setConfirmDiscard(false)}>{t('watch.discardNo')}</button>
          </span> :
          <button type="button" className="watch-discard" onClick={() => setConfirmDiscard(true)} disabled={busy}>{t('watch.discard')}</button>}
      </div>}
      {ready && <p className="watch-hint">{t(running ? 'watch.playHint' : 'watch.intro')}{running && target.platform === 'bilibili' ? ` ${t('watch.biliHint')}` : ''}</p>}
      {!running && models?.length === 0 && ready && <p className="watch-hint">{t('watch.noVisionModel')}</p>}
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
