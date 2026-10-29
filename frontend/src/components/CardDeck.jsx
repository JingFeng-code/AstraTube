import { useEffect, useRef } from 'react'
import { fmtTime, pickField, summaryLines, TRANSCRIPT_KEYS, TRANSLATION_KEYS, TRANSCRIPT_SOURCE_KEYS } from '../utils.js'
import { defaultTrack, hasCode } from '../hooks/useImplement.js'
import { useI18n } from '../i18n/index.jsx'

// 重點數量多時把導覽縮小排密，避免撐破標題列
const COMPACT_FROM = 24

export default function CardDeck({ result, index, setIndex, clippedIds, onClip, onJumpVideo, deepdives, onDeepDive, deepdiveLoading, onImplement, fullWidth }) {
  const { t } = useI18n()
  const cards=result.cards||[], card=cards[index]
  const dotsRef=useRef(null)
  // 圓點列可橫向捲動，切換卡片時把目前的圓點帶進視野
  useEffect(()=>{
    const el=dotsRef.current?.children[index]
    el?.scrollIntoView({block:'nearest',inline:'nearest'})
  },[index])
  if (!card) return null
  const transcript=pickField(card,TRANSCRIPT_KEYS), translation=pickField(card,TRANSLATION_KEYS)
  const points=summaryLines(card.summary)
  const isClipped=clippedIds.has(index), dive=deepdives[index], isYT=result.source_type==='youtube'
  // 舊的工作階段（localStorage）沒有 content_type，defaultTrack 會退回 study
  const suggestedTrack=defaultTrack(result.content_type,hasCode(cards))
  const sourceKey=result.transcript_source&&TRANSCRIPT_SOURCE_KEYS[result.transcript_source]
  const [kbdL,kbdR,kbdMid,kbdN,kbdTail]=t('deck.kbdHint','←','→','N')
  return (
    <section className={`deck ${fullWidth?'deck-full':''}`}>
      <div className="deck-head">
        <h2 className="deck-title">{result.title}</h2>
        {result.model_used&&<span className="model-badge" title={t('deck.modelTitle')}>{result.model_used}{result.segments>1?t('deck.segments',result.segments):''}</span>}
        {sourceKey&&<span className="model-badge" title={t('deck.sourceTitle')}>{t(sourceKey)}</span>}
        <span className="deck-count">{t('deck.count',index+1,cards.length)}</span>
        {/* 實作的對象是整支影片，不是單張卡——所以按鈕在標題列，不在卡片上 */}
        <button className="btn-implement" onClick={onImplement} title={t('implement.ctaTitle')}>{t(`implement.cta.${suggestedTrack}`)}</button>
      </div>
      {/* 重點導覽常駐頂部，不必捲到底才能切換 */}
      <div className="deck-nav deck-nav-top">
        <button className="nav-arrow" onClick={()=>setIndex(index-1)} disabled={index===0} aria-label={t('deck.prev')}>←</button>
        <div className={`dots ${cards.length>=COMPACT_FROM?'compact':''}`} ref={dotsRef}>{cards.map((_,i)=><button key={i} className={`dot-btn ${i===index?'on':clippedIds.has(i)?'was-clipped':''}`} onClick={()=>setIndex(i)} title={t('deck.goto',i+1)} aria-label={t('deck.goto',i+1)}/>)}</div>
        <button className="nav-arrow" onClick={()=>setIndex(index+1)} disabled={index===cards.length-1} aria-label={t('deck.next')}>→</button>
      </div>
      <article className={`card ${isClipped?'clipped':''}`} key={index}>
        <div className="card-meta">
          <span>{t('deck.card',String(index+1).padStart(2,'0'))}</span>
          {isYT&&card.timestamp_seconds!=null&&<button className="card-ts" onClick={()=>onJumpVideo(index)}>▶ {fmtTime(card.timestamp_seconds)}</button>}
        </div>
        <h2>{card.heading}</h2>
        {points.length>1?<ul className="summary-list">{points.map((p,i)=><li key={i}>{p}</li>)}</ul>:<p className="summary">{card.summary}</p>}
        {transcript&&<blockquote className="transcript"><span className="label">{t('deck.transcript')}</span>{transcript}{translation&&<><br/><span style={{color:'var(--ink)'}}>{translation}</span></>}</blockquote>}
        {card.visual&&<blockquote className="transcript"><span className="label">{t('deck.visual')}</span>{card.visual}</blockquote>}
        {/* 模型認為這張卡有可動手的事時，把它明講出來 */}
        {card.actionable&&card.action_hint&&<p className="action-hint"><span className="label">{t('deck.actionHint')}</span>{card.action_hint}</p>}
        <div className="card-actions">
          <button className="btn-clip" onClick={()=>onClip(index)} disabled={isClipped}>{isClipped?t('deck.clipped'):t('deck.clip')}</button>
          <button className="btn-paper" onClick={()=>onDeepDive(index)} disabled={deepdiveLoading===index||!!dive}>{deepdiveLoading===index?t('deck.deepdiveLoading'):dive?t('deck.deepdiveDone'):t('deck.deepdive')}</button>
        </div>
        {dive&&<div className="deepdive"><span className="label">{t('deck.deepdiveLabel')}{dive.model?` / ${dive.model}`:''}</span>{dive.text}</div>}
      </article>
      <p className="kbd-hint"><kbd>{kbdL}</kbd> <kbd>{kbdR}</kbd>{kbdMid}<kbd>{kbdN}</kbd>{kbdTail}</p>
    </section>
  )
}
