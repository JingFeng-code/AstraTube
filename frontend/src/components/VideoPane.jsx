import { useEffect, useMemo, useRef, useState } from 'react'
import { fmtTime } from '../utils.js'
import { getSubtitles, translateSubtitles } from '../api.js'
import { activeCueIndex, visibleCues, applyTranslations, nextBatchStart, normalizeSubtitleMode, overlayLines, SUBTITLE_MODES } from '../utils/subtitles.js'
import { useI18n } from '../i18n/index.jsx'
import { effectiveSubtitleTranslationProvider } from '../utils/subtitle-provider.js'
import { parsePlayerMessage, playerOrigin, playerUrl, randomChannel, seekMessage } from '../utils/player-bridge.js'

const MODE_KEY = 'astratube-subtitle-mode'

// YouTube 播放器放在獨立來源的 iframe（public/player/youtube.html）內，
// 官方 IFrame API 腳本只在那個 iframe 執行，不會進入具有 Tauri IPC 的主視窗。
function YouTubePlayer({ videoId, startAt, onTime }) {
  const frameRef = useRef(null)
  const readyRef = useRef(false)
  const seekRef = useRef(startAt)
  const onTimeRef = useRef(onTime)
  const [fallback, setFallback] = useState(false)
  // 每支影片一組新的隨機頻道；來源與網址只在影片切換時計算一次
  const session = useMemo(() => {
    const parentOrigin = window.location.origin
    const hostOrigin = playerOrigin({
      isTauri: Boolean(window.__TAURI_INTERNALS__),
      userAgent: navigator.userAgent,
      origin: parentOrigin,
    })
    const channel = randomChannel()
    return { hostOrigin, channel, src: playerUrl({ playerOrigin: hostOrigin, parentOrigin, videoId, channel }) }
  }, [videoId])

  useEffect(() => { onTimeRef.current = onTime }, [onTime])

  function sendSeek(target) {
    const frame = frameRef.current?.contentWindow
    if (!frame || !readyRef.current) return
    frame.postMessage(seekMessage(session.channel, target.t, target.auto), session.hostOrigin)
  }

  useEffect(() => {
    if (!startAt.key) return
    seekRef.current = startAt
    sendSeek(startAt)
  }, [startAt.key, startAt.t, startAt.auto])

  useEffect(() => {
    readyRef.current = false
    seekRef.current = startAt
    setFallback(!session.src)
    if (!session.src) return
    // 宿主頁 15 秒內都沒回報就退回一般嵌入（沒有進度同步，但仍可播放）
    const timer = window.setTimeout(() => { if (!readyRef.current) setFallback(true) }, 15000)
    function onMessage(event) {
      const message = parsePlayerMessage(event, {
        source: frameRef.current?.contentWindow,
        origin: session.hostOrigin,
        channel: session.channel,
      })
      if (!message) return
      if (message.type === 'ready') {
        readyRef.current = true
        window.clearTimeout(timer)
        const next = seekRef.current
        if (next.t > 0 || next.auto) sendSeek(next)
      } else if (message.type === 'time') {
        onTimeRef.current(message.seconds)
      } else {
        window.clearTimeout(timer)
        setFallback(true)
      }
    }
    window.addEventListener('message', onMessage)
    return () => {
      window.clearTimeout(timer)
      window.removeEventListener('message', onMessage)
      readyRef.current = false
    }
  }, [session])

  if (fallback) {
    return <iframe key={startAt.key} title="YouTube"
      src={`https://www.youtube.com/embed/${videoId}?start=${Math.floor(startAt.t)}&autoplay=${startAt.auto?1:0}&rel=0`}
      allow="autoplay; encrypted-media; picture-in-picture" allowFullScreen />
  }
  return <iframe ref={frameRef} className="player-host" src={session.src} title="YouTube video player"
    allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowFullScreen
    referrerPolicy="strict-origin-when-cross-origin" />
}

export default function VideoPane({ videoId, startAt, cards, activeIndex, onJump, platform='youtube', page=1, developerMode=false, localModels=[], subtitleRevision=0 }) {
  const { t } = useI18n()
  const [cues, setCues] = useState([])
  const [subtitleError, setSubtitleError] = useState('')
  const [subtitleSource, setSubtitleSource] = useState('')
  const [subtitleTiming, setSubtitleTiming] = useState('')
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('')
  const [time, setTime] = useState(0)
  const [manualSeek, setManualSeek] = useState({t:0,key:0,auto:false})
  const [translating, setTranslating] = useState(false)
  const [translateError, setTranslateError] = useState('')
  const [showBilingual, setShowBilingual] = useState(true)
  // 播放器上的字幕模式跨影片保留（本機偏好，不影響後端）
  const [subtitleMode, setSubtitleModeRaw] = useState(() => {
    try { return normalizeSubtitleMode(localStorage.getItem(MODE_KEY)) } catch { return normalizeSubtitleMode(null) }
  })
  const setSubtitleMode = mode => {
    setSubtitleModeRaw(mode)
    try { localStorage.setItem(MODE_KEY, mode) } catch {}
  }
  // 整片翻譯迴圈讀的是最新字幕與播放位置，不能依賴舊的 render 閉包
  const cuesRef = useRef([])
  const activeRef = useRef(-1)
  const runningRef = useRef(false)
  const [developerTranslation, setDeveloperTranslation] = useState('opencode')
  // 回到一般模式就只使用免費模型；本地模型若不存在也退回預設，
  // 切換模式時不刪掉開發者上次選擇。
  const translationProvider = effectiveSubtitleTranslationProvider(
    developerMode, developerTranslation, localModels
  )
  const sourceGeneration = useRef(0)

  useEffect(() => {
    let cancelled = false
    sourceGeneration.current++
    setCues([])
    setFilter('')
    setTime(0)
    setSubtitleError('')
    setSubtitleSource('')
    setSubtitleTiming('')
    setTranslateError('')
    setTranslating(false)
    runningRef.current = false
    setShowBilingual(true)
    setLoading(true)
    getSubtitles(platform, videoId, page, translationProvider).then(result => {
      if (!cancelled) {
        const data = result.cues || []
        setCues(data)
        setSubtitleSource(result.source || 'platform')
        setSubtitleTiming(result.timing_precision || 'seconds_estimated')
      }
    }).catch(err => {
      if (!cancelled) setSubtitleError(err.message)
    }).finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [platform, videoId, page, translationProvider, subtitleRevision])

  const [seek, setSeek] = useState(startAt)
  useEffect(() => { setSeek(startAt) }, [startAt.key])
  useEffect(() => { if (manualSeek.key) setSeek(manualSeek) }, [manualSeek.key])

  useEffect(() => { cuesRef.current = cues }, [cues])
  // 離開這支影片（元件卸載）時停止翻譯迴圈
  useEffect(() => () => { runningRef.current = false }, [])

  // 整片翻譯：一次一批（最多 16 句）依序送出，從目前播放位置往後優先。
  // 一般模式只用免費模型；失敗就停下並顯示原因，按「繼續翻譯」從未完成處接續（已翻譯的有快取）。
  async function translateAll() {
    if (runningRef.current || !cuesRef.current.length) return
    const generation = sourceGeneration.current
    runningRef.current = true
    setTranslating(true)
    setTranslateError('')
    try {
      while (runningRef.current && sourceGeneration.current === generation) {
        const index = nextBatchStart(cuesRef.current, Math.max(0, activeRef.current))
        if (index < 0) break
        const response = await translateSubtitles(platform, videoId, page, index, 16, translationProvider)
        if (sourceGeneration.current !== generation) return
        const before = nextBatchStart(cuesRef.current, index)
        const updated = applyTranslations(cuesRef.current, response.translations)
        cuesRef.current = updated
        setCues(updated)
        // 回應成功卻沒有新譯文時停下，避免在同一處無限重送
        if (nextBatchStart(updated, index) === before) throw new Error(t('subtitles.noProgress'))
      }
    } catch (error) {
      if (sourceGeneration.current === generation) setTranslateError(error.message)
    } finally {
      if (sourceGeneration.current === generation) {
        runningRef.current = false
        setTranslating(false)
      }
    }
  }

  function pauseTranslation() {
    runningRef.current = false
  }

  function jumpTo(seconds) {
    setTime(seconds)
    setManualSeek(s => ({t:seconds,auto:true,key:s.key+1}))
  }

  // YouTube 的原生 API 可讀取真實進度；Bilibili 官方 iframe 目前只支援帶秒數重新開啟。
  const active = platform === 'youtube' ? activeCueIndex(cues, time) : -1
  useEffect(() => { activeRef.current = active }, [active])
  const translatedCount = cues.filter(c => !!c.translation).length
  const allTranslated = cues.length > 0 && translatedCount === cues.length
  const overlay = active >= 0 ? overlayLines(cues[active], subtitleMode) : []
  const matched = useMemo(() => visibleCues(cues, filter), [cues, filter])
  const visible = filter.trim() ? matched.slice(0, 120) : cues.slice(Math.max(0, active - 25), Math.max(80, active + 55))
  const biliSrc = `https://player.bilibili.com/player.html?bvid=${videoId}&p=${page}&t=${seek.t}&autoplay=${seek.auto?1:0}`
  if (!videoId) return null
  return (
    <section className="pane-video">
      <p className="pane-label">{t('video.pane')}</p>
      <div className="video-frame">
        {platform === 'youtube' ?
          <YouTubePlayer key={videoId} videoId={videoId} startAt={seek} onTime={setTime} /> :
          <iframe key={`${startAt.key}:${manualSeek.key}`} src={biliSrc} title="Bilibili"
            allow="autoplay; encrypted-media; picture-in-picture" allowFullScreen />}
        {/* 只有 YouTube 能讀到播放進度，才能把字幕對到畫面上；不攔截滑鼠，不影響播放器操作 */}
        {overlay.length > 0 && <div className="subtitle-overlay" aria-hidden="true">
          {overlay.map(line => <span key={line.kind} className={`subtitle-overlay-line ${line.kind}`}>{line.text}</span>)}
        </div>}
      </div>
      <section className="subtitles-panel" aria-label={t('subtitles.title')}>
        <div className="subtitles-head">
          <strong>{t('subtitles.title')}</strong>
          <span>{t('subtitles.translationProgress', translatedCount, cues.length)}</span>
        </div>
        {subtitleSource === 'imported' && <p className="subtitles-hint">
          {t('subtitles.importedTiming', subtitleTiming === 'milliseconds_original')}
        </p>}
        {developerMode && <label className="subtitles-provider">
          <span>{t('subtitles.engine')}</span>
          <select value={translationProvider} onChange={e => setDeveloperTranslation(e.target.value)}
                  aria-label={t('subtitles.engine')}>
            <option value="opencode">{t('subtitles.freeEngine')}</option>
            {localModels.map(model => <option key={model} value={`ollama:${model}`}>Ollama · {model}</option>)}
          </select>
          {!localModels.length && <small>{t('subtitles.noLocalModels')}</small>}
        </label>}
        {!loading && !subtitleError && cues.length>0 && <div className="subtitles-controls">
          {translating ?
            <button className="btn-paper" onClick={pauseTranslation}>
              {t(translationProvider.startsWith('ollama:') ? 'subtitles.translatingAllLocal' : 'subtitles.translatingAll', translatedCount, cues.length)}
              {' · '}{t('subtitles.pause')}
            </button> :
            <button className="btn-paper" onClick={translateAll} disabled={allTranslated}>
              {allTranslated ? t('subtitles.translateDone') :
                translatedCount > 0 ? t('subtitles.translateResume', cues.length - translatedCount) : t('subtitles.translateAll', cues.length)}
            </button>}
          {platform === 'youtube' && <div className="subtitle-mode" role="group" aria-label={t('subtitles.modeLabel')}>
            {SUBTITLE_MODES.map(mode => (
              <button key={mode} type="button" aria-pressed={subtitleMode === mode}
                className={subtitleMode === mode ? 'active' : ''} onClick={() => setSubtitleMode(mode)}>
                {t(`subtitles.mode.${mode}`)}
              </button>
            ))}
          </div>}
          <label className="subtitles-bilingual-toggle">
            <input type="checkbox" checked={showBilingual} onChange={e=>setShowBilingual(e.target.checked)}/>
            {t('subtitles.showTranslation')}
          </label>
        </div>}
        {translateError && <p className="subtitles-hint" role="alert">{t('subtitles.translateFailed',translateError)}</p>}
        <input className="subtitles-search" type="search" value={filter} onChange={e=>setFilter(e.target.value)}
          placeholder={t('subtitles.search')} aria-label={t('subtitles.search')}/>
        {platform === 'bilibili' && <p className="subtitles-hint">{t('subtitles.bilibiliLimit')}</p>}
        {loading ? <p className="subtitles-hint">{t('subtitles.loading')}</p> :
          subtitleError ? <p className="subtitles-hint" role="status">{t('subtitles.unavailable',subtitleError)}</p> :
          <>
            <div className="subtitles-list">
              {visible.map((cue,i) => (
                <button className={`subtitle-cue ${active>=0&&cues[active]===cue?'active':''}`}
                  key={cue.start+'-'+i} onClick={()=>jumpTo(cue.start)}>
                  <span className="subtitle-time">{fmtTime(cue.start)}</span>
                  <span className="subtitle-words">
                    <span>{cue.text}</span>
                    {showBilingual&&cue.translation&&<span className="subtitle-translation">{cue.translation}</span>}
                  </span>
                </button>
              ))}
            </div>
            {filter.trim()&&matched.length>120&&<p className="subtitles-hint">{t('subtitles.moreResults', matched.length)}</p>}
          </>}
      </section>
      <div className="chapters">
        {cards.map((c,i) => (
          <button key={i} className={`chapter ${i===activeIndex?'active':''}`} onClick={()=>onJump(i)}>
            <span className="ts">{c.timestamp_seconds!=null?fmtTime(c.timestamp_seconds):'--:--'}</span>
            <span>{c.heading}</span>
          </button>
        ))}
      </div>
    </section>
  )
}
