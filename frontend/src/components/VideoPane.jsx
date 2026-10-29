import { fmtTime } from '../utils.js'
import { useI18n } from '../i18n/index.jsx'
export default function VideoPane({ videoId, startAt, cards, activeIndex, onJump, platform='youtube', page=1 }) {
  const { t } = useI18n()
  if (!videoId) return null
  const src = platform==='bilibili' ? `https://player.bilibili.com/player.html?bvid=${videoId}&p=${page}&t=${startAt.t}&autoplay=${startAt.auto?1:0}` : `https://www.youtube.com/embed/${videoId}?start=${startAt.t}&autoplay=${startAt.auto?1:0}&rel=0`
  return (
    <section className="pane-video">
      <p className="pane-label">{t('video.pane')}</p>
      <div className="video-frame">
        <iframe key={startAt.key} src={src} title={platform==='bilibili'?'Bilibili':'YouTube'} allow="autoplay; encrypted-media; picture-in-picture" allowFullScreen />
      </div>
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
