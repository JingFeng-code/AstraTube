import { useEffect, useMemo, useRef, useState } from 'react'
import { fmtTime } from '../utils.js'
import { getSubtitles, translateSubtitles } from '../api.js'
import { activeCueIndex, visibleCues, applyTranslations, nextUntranslatedIndex } from '../utils/subtitles.js'
import { useI18n } from '../i18n/index.jsx'
import { effectiveSubtitleTranslationProvider } from '../utils/subtitle-provider.js'

// 官方 YouTube IFrame API；只建立一份載入 Promise，避免重複注入 script。
let ytApiPromise
function youtubeApi() {
  if (window.YT?.Player) return Promise.resolve(window.YT)
  if (ytApiPromise) return ytApiPromise
  ytApiPromise = new Promise((resolve, reject) => {
    const previous = window.onYouTubeIframeAPIReady
    let finished = false
    const fail = () => {
      if (finished) return
      finished = true
      ytApiPromise = null
      reject(new Error('YouTube IFrame API unavailable'))
    }
    const timer = window.setTimeout(fail, 10000)
    window.onYouTubeIframeAPIReady = () => {
      window.clearTimeout(timer)
      if (finished) return
      finished = true
      if (typeof previous === 'function') previous()
      resolve(window.YT)
    }
    let script = document.querySelector('script[data-astratube-youtube-api]')
    if (!script) {
      script = document.createElement('script')
      script.src = 'https://www.youtube.com/iframe_api'
      script.async = true
      script.dataset.astratubeYoutubeApi = '1'
      document.head.appendChild(script)
    }
    script.addEventListener('error', fail, { once: true })
  })
  return ytApiPromise
}

function YouTubePlayer({ videoId, startAt, onTime }) {
  const rootRef = useRef(null)
  const playerRef = useRef(null)
  const readyRef = useRef(false)
  const seekRef = useRef(startAt)
  const onTimeRef = useRef(onTime)
  const [fallback, setFallback] = useState(false)

  useEffect(() => { onTimeRef.current = onTime }, [onTime])
  useEffect(() => {
    if (!startAt.key) return
    seekRef.current = startAt
    if (readyRef.current && playerRef.current?.seekTo) {
      playerRef.current.seekTo(startAt.t, true)
      if (startAt.auto) playerRef.current.playVideo()
    }
  }, [startAt.key, startAt.t, startAt.auto])

  useEffect(() => {
    let disposed = false
    let poll
    const root = rootRef.current
    if (!root) return
    setFallback(false)
    readyRef.current = false
    seekRef.current = startAt
    const mount = document.createElement('div')
    root.appendChild(mount)
    youtubeApi().then(YT => {
      if (disposed) return
      playerRef.current = new YT.Player(mount, {
        videoId,
        width: '100%',
        height: '100%',
        playerVars: { playsinline: 1, rel: 0, origin: window.location.origin },
        events: {
          onReady: ({ target }) => {
            if (disposed) return
            readyRef.current = true
            const next = seekRef.current
            if (next.t > 0) target.seekTo(next.t, true)
            if (next.auto) target.playVideo()
            poll = window.setInterval(() => {
              const current = target.getCurrentTime?.()
              if (Number.isFinite(current)) onTimeRef.current(current)
            }, 400)
          },
        },
      })
    }).catch(() => { if (!disposed) setFallback(true) })
    return () => {
      disposed = true
      window.clearInterval(poll)
      readyRef.current = false
      try { playerRef.current?.destroy?.() } catch {}
      playerRef.current = null
      root.replaceChildren()
    }
  // 影片 ID 變更才重新初始化播放器，時間戳跳轉用 seekTo，避免 iframe 重新載入。
  }, [videoId])

  if (fallback) {
    return <iframe key={startAt.key} title="YouTube"
      src={`https://www.youtube.com/embed/${videoId}?start=${startAt.t}&autoplay=${startAt.auto?1:0}&rel=0`}
      allow="autoplay; encrypted-media; picture-in-picture" allowFullScreen />
  }
  return <div className="player-host" ref={rootRef} aria-label="YouTube video player" />
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
  const [nextIndex, setNextIndex] = useState(0)
  const [showBilingual, setShowBilingual] = useState(true)
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
    setNextIndex(0)
    setShowBilingual(true)
    setLoading(true)
    getSubtitles(platform, videoId, page, translationProvider).then(result => {
      if (!cancelled) {
        const data = result.cues || []
        setCues(data)
        setSubtitleSource(result.source || 'platform')
        setSubtitleTiming(result.timing_precision || 'seconds_estimated')
        setNextIndex(nextUntranslatedIndex(data))
      }
    }).catch(err => {
      if (!cancelled) setSubtitleError(err.message)
    }).finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [platform, videoId, page, translationProvider, subtitleRevision])

  const [seek, setSeek] = useState(startAt)
  useEffect(() => { setSeek(startAt) }, [startAt.key])
  useEffect(() => { if (manualSeek.key) setSeek(manualSeek) }, [manualSeek.key])

  async function handleTranslate() {
    if (!cues.length || translating || nextIndex >= cues.length) return
    const generation = sourceGeneration.current
    const index = nextIndex
    setTranslating(true)
    setTranslateError('')
    try {
      const response = await translateSubtitles(platform, videoId, page, index, 16, translationProvider)
      if (sourceGeneration.current !== generation) return
      const updated = applyTranslations(cues, response.translations)
      setCues(updated)
      setNextIndex(nextUntranslatedIndex(updated, response.next_index))
      setShowBilingual(true)
    } catch (error) {
      if (sourceGeneration.current === generation) setTranslateError(error.message)
    } finally {
      if (sourceGeneration.current === generation) setTranslating(false)
    }
  }

  function jumpTo(seconds) {
    setTime(seconds)
    setManualSeek(s => ({t:seconds,auto:true,key:s.key+1}))
  }

  // YouTube 的原生 API 可讀取真實進度；Bilibili 官方 iframe 目前只支援帶秒數重新開啟。
  const active = platform === 'youtube' ? activeCueIndex(cues, time) : -1
  const translatedCount = cues.filter(c => !!c.translation).length
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
          <button className="btn-paper" onClick={handleTranslate}
                  disabled={translating || nextIndex >= cues.length}>
            {translating ? t(translationProvider.startsWith('ollama:') ? 'subtitles.translatingLocal' : 'subtitles.translating') :
              nextIndex>=cues.length ? t('subtitles.translateDone') :
              t('subtitles.translateNext',Math.min(16,cues.length-nextIndex))}
          </button>
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
