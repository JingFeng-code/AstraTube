import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import VideoPane from './components/VideoPane.jsx'
import SubtitleImportControls from './components/SubtitleImportControls.jsx'
import CardDeck from './components/CardDeck.jsx'
import Splitter from './components/Splitter.jsx'
import NotesPanel from './components/NotesPanel.jsx'
import AskPanel from './components/AskPanel.jsx'
import FloatingPanel from './components/FloatingPanel.jsx'
import SettingsModal from './components/SettingsModal.jsx'
import ImplementModal from './components/ImplementModal.jsx'
import BrandMark from './components/BrandMark.jsx'
import useModels from './hooks/useModels.js'
import { initialAiSource, resolveAiSource, aiSourceLabel } from './utils/ai-source.js'
import useSettings from './hooks/useSettings.js'
import useSummarizeStream from './hooks/useSummarizeStream.js'
import useImplement from './hooks/useImplement.js'
import useCards from './hooks/useCards.js'
import useNotesVault from './hooks/useNotesVault.js'
import { useI18n } from './i18n/index.jsx'
import { DEEP_VISUAL_KEY, deepVisualNotice, effectiveDeepVisual, isBilibiliUrl } from './utils/user-mode.js'
import { detectSource, needsSubtitleImport, noCaptionAction, sourceHintKey } from './utils/source-info.js'
import { createNoteMarkdown, markdownFilename } from './utils/notes-export.js'
import { NARROW_QUERY, effectiveResultTab, resultTabs } from './utils/result-tabs.js'
import { isVideoFile, localVideoId, localVideoUrl } from './utils/local-video.js'
import { watchTarget } from './utils/watch.js'
import WatchAlong from './components/WatchAlong.jsx'
import { getWatchStatus } from './api.js'
import LocalSpeechControls from './components/LocalSpeechControls.jsx'

// 本機工作階段持久化：整理結果、卡片索引、筆記草稿都存在瀏覽器裡，重開仍在。
const SKEY='ycr-session-v1'
const SAVED=(()=>{try{return JSON.parse(localStorage.getItem(SKEY))||{}}catch{return {}}})()
// 深視覺開關：獨立存一把 key，跨網址/工作階段延續使用者的偏好
const DVKEY=DEEP_VISUAL_KEY
// 頂欄收合狀態：獨立存一把 key，跨工作階段延續使用者的偏好
// 影片欄／重點欄左右比例：獨立存一把 key，跨工作階段延續使用者拖過的比例
const SPKEY='ycr-split'
const SPLIT_MIN=20,SPLIT_MAX=80,SPLIT_DEFAULT=50
function readPreference(key){try{return localStorage.getItem(key)}catch{return null}}
function loadSplit(){try{const v=parseFloat(readPreference(SPKEY));return isFinite(v)&&v>=SPLIT_MIN&&v<=SPLIT_MAX?v:SPLIT_DEFAULT}catch{return SPLIT_DEFAULT}}

function GenerationProgress({ progress }){
  const { t } = useI18n()
  const [now,setNow]=useState(Date.now())
  useEffect(()=>{
    setNow(Date.now())
    if(!progress)return
    const timer=setInterval(()=>setNow(Date.now()),1000)
    return()=>clearInterval(timer)
  },[progress?.startedAt,!!progress])
  if(!progress)return null
  const total=Number(progress.total)||0
  const completed=Math.min(Number(progress.completed)||0,total||0)
  const ratio=total>0?completed/total:0
  const elapsed=Math.max(0,Math.floor((now-(progress.startedAt||now))/1000))
  const clock=`${String(Math.floor(elapsed/60)).padStart(2,'0')}:${String(elapsed%60).padStart(2,'0')}`
  const seg=Number.isInteger(progress.seg)?t('progress.segment',progress.seg+1):t('progress.preparing')
  const model=progress.model?` · ${progress.model}`:''
  const apiName=progress.provider==='opencode'?'OpenCode':(progress.provider||'API')
  let label=t('progress.generate')
  if(progress.stage==='source') label=t('progress.source')
  else if(progress.phase==='coverage') label=t('progress.coverage',seg,model)
  else if(progress.state==='rate_wait') label=t('progress.rateWait',seg,apiName,progress.delay||0)
  else if(progress.state==='retry_wait') label=t('progress.retry',seg,apiName,progress.delay||0,progress.attempt||'',progress.tries||'')
  else if(progress.state==='model_switch') label=t('progress.modelSwitch',seg,progress.model)
  else if(progress.state==='key_switch') label=t('progress.keySwitch',seg)
  else if(progress.state==='request') label=t('progress.waiting',seg,model,(progress.attempt||1)>1?t('progress.retrySuffix',progress.attempt,progress.tries):'')
  else if(progress.state==='next') label=completed<total?t('progress.next',completed+1):t('progress.done')
  return <div className="generation-progress" role="progressbar" aria-label={label} aria-valuemin="0" aria-valuemax={total||undefined} aria-valuenow={total?completed:undefined}>
    <div className="generation-meta"><span className="generation-label">{label}</span><span className="generation-count">{total>0?`${completed} / ${total} · `:''}{clock}</span></div>
    <div className="generation-track"><span style={{transform:`scaleX(${ratio})`}}/></div>
  </div>
}

export default function App() {
  const { t } = useI18n()
  const [url,setUrl]=useState(SAVED.url||'')
  const [sourceMode,setSourceMode]=useState(SAVED.sourceMode==='local'?'local':'url')
  // 影片檔只保留在記憶體；重新開啟 App 後只記得識別碼和名稱，要再選一次檔案才能播放
  const [localVideo,setLocalVideo]=useState(()=>SAVED.localVideo?.id?{id:SAVED.localVideo.id,name:SAVED.localVideo.name||'',src:null}:null)
  const localPickerRef=useRef(null)
  const [provider,setProvider]=useState(()=>initialAiSource(readPreference('astratube-ai-source'),SAVED.provider))
  const [deepVisual,setDeepVisualRaw]=useState(()=>readPreference(DVKEY)==='1')
  const setDeepVisual=v=>{setDeepVisualRaw(v);try{localStorage.setItem(DVKEY,v?'1':'0')}catch{}}
  // 頂欄收合：只反映使用者手動設定，不受 loading 等程式狀態影響
  // 影片／重點欄比例：拖曳中只直接改 DOM 上的 CSS 變數，放開才落到 state
  const [split,setSplitRaw]=useState(loadSplit)
  const workspaceRef=useRef(null)
  const setSplit=v=>{setSplitRaw(v);try{localStorage.setItem(SPKEY,String(v))}catch{}}
  useLayoutEffect(()=>{workspaceRef.current?.style.setProperty('--split',String(split))},[split])
  const [freeNote,setFreeNote]=useState(SAVED.freeNote||''), [filename,setFilename]=useState(SAVED.filename||'')
  const [showSettings,setShowSettings]=useState(false)
  const [settingsFocus,setSettingsFocus]=useState(null)
  const [subtitleRevision,setSubtitleRevision]=useState(0)
  const [toast,setToast]=useState(null)
  const toastTimer=useRef(null)
  const showToast=(msg,isErr=false)=>{clearTimeout(toastTimer.current);setToast({msg,isErr});toastTimer.current=setTimeout(()=>setToast(null),4200)}

  const { providers, refresh: refreshModels } = useModels()
  const activeProvider=resolveAiSource(provider,providers)
  const setAiSource=next=>{setProvider(next);try{localStorage.setItem('astratube-ai-source',next)}catch{}}
  const { settings, needsSetup, setSettings } = useSettings()
  const stream = useSummarizeStream({
    initialResult: SAVED.result||null,
    onSegError: ev=>showToast(t('toast.segFailed',ev.seg+1,typeof ev.error==='string'?ev.error.trim().slice(0,160):''),true),
    onSegTruncated: ev=>showToast(t('toast.segTruncated',ev.seg+1),true),
    t,
  })
  const { result } = stream
  const cardsHook = useCards(result, activeProvider, { index: SAVED.index, deepdives: SAVED.deepdives, clips: SAVED.clips })
  const notes = useNotesVault(SAVED.saveOpts)
  const implement = useImplement({ result, provider: activeProvider, t })

  // 摘要標題一到就當作預設檔名
  useEffect(()=>{ if(result?.title) setFilename(f=>f||result.title) },[result?.title])
  // 工作階段持久化：任何整理狀態改變就寫回 localStorage
  useEffect(()=>{
    try{localStorage.setItem(SKEY,JSON.stringify({url,sourceMode,localVideo:localVideo?{id:localVideo.id,name:localVideo.name}:null,provider,result,index:cardsHook.index,deepdives:cardsHook.deepdives,clips:cardsHook.clips,freeNote,filename,saveOpts:notes.saveOpts}))}catch{}
  },[url,sourceMode,localVideo?.id,localVideo?.name,provider,result,cardsHook.index,cardsHook.deepdives,cardsHook.clips,freeNote,filename,notes.saveOpts])

  function handleSettingsSaved(next){
    setSettings(next)
    setShowSettings(false)
    setSettingsFocus(null)
    notes.refresh()
    refreshModels()   // 剛填的金鑰要立刻反映在模型下拉選單上
    showToast(t('toast.settingsSaved'))
  }

  // Bilibili 不支援讀畫面：停用勾選框並說明原因（不改動使用者對 YouTube 的偏好設定）
  const bilibiliUrl=isBilibiliUrl(url)
  const isLocalMode=sourceMode==='local'
  const localUrl=localVideo?localVideoUrl(localVideo.id):''
  const visualNotice=isLocalMode?null:deepVisualNotice(deepVisual,url,!!providers?.gemini?.configured)
  const cards=result?.cards||[]
  const isBilibili=result?.source_type==='bilibili'&&!!result?.bilibili_video_id
  const isLocalResult=result?.source_type==='local'&&!!result?.local_video_id
  const hasVideo=(result?.source_type==='youtube'&&!!result?.youtube_video_id)||isBilibili||isLocalResult

  // 陪看模式只在這台電腦的桌面版可用；網頁版不顯示入口
  const [watchAvailable,setWatchAvailable]=useState(false)
  const [watching,setWatching]=useState(false)
  useEffect(()=>{getWatchStatus().then(r=>setWatchAvailable(!!r.available)).catch(()=>{})},[])
  function finishWatching(){setWatching(false);startAnalysis(false)}
  async function startAnalysis(useVisual){
    if(!activeProvider){setShowSettings(true);showToast(t('ai.notReady'),true);return}
    cardsHook.resetForNewResult()
    await stream.summarize(isLocalMode?localUrl:url,activeProvider,useVisual,isLocalMode?localVideo?.name:null)
  }
  const handleSummarize=()=>startAnalysis(!isLocalMode&&effectiveDeepVisual(deepVisual,url))
  async function pickLocalVideo(event){
    const file=event.target.files?.[0]
    event.target.value=''
    if(!file)return
    if(!isVideoFile(file)){showToast(t('local.invalidFile'),true);return}
    try{
      const id=await localVideoId(file)
      setLocalVideo(previous=>{if(previous?.src)URL.revokeObjectURL(previous.src);return{id,name:file.name,src:URL.createObjectURL(file),file}})
      setSourceMode('local')
    }catch{showToast(t('local.invalidFile'),true)}
  }
  // 使用者明確按下才開啟：影片會交給 Google，不能因為有金鑰就自動改走這條路
  function analyzeWithVisual(){setDeepVisual(true);startAnalysis(true)}
  function openVisualKeySettings(){setSettingsFocus('visual-key');setShowSettings(true)}
  // 記在分析結果上：之後選了別的影片，這份筆記的來源仍是當初分析的那支
  const noteSource=isLocalResult?(result.local_name||t('input.modeLocal')):(result?.source_url||url)
  function clipCard(i){const c=cardsHook.clipCard(i); if(c)showToast(t('toast.clipped',c.heading))}
  async function onDeepDive(i){if(!activeProvider){setShowSettings(true);showToast(t('ai.notReady'),true);return}try{await cardsHook.handleDeepDive(i)}catch(e){showToast(t('toast.deepdiveFailed',e.message),true)}}
  async function handleSave(){
    try{
      const res=await notes.save({title:filename||result?.title||t('note.summary'),sourceUrl:noteSource,clips:cardsHook.clips,freeNote,t})
      showToast(res.mode==='append'?t('toast.appendedTo',res.saved_to):t('toast.savedTo',res.saved_to))
    }catch(e){showToast(e.message===t('error.pickNote')?e.message:t('toast.saveFailed',e.message),true)}
  }

  function handleExportNotes(){
    const markdown=createNoteMarkdown({title:filename||result?.title||t('note.summary'),sourceUrl:noteSource,clips:cardsHook.clips,freeNote})
    const blob=new Blob([markdown],{type:'text/markdown;charset=utf-8'})
    const href=URL.createObjectURL(blob)
    const element=document.createElement('a')
    element.href=href
    element.download=markdownFilename(filename||result?.title||t('note.summary'))
    document.body.appendChild(element)
    element.click()
    element.remove()
    setTimeout(()=>URL.revokeObjectURL(href),1000)
  }

  useEffect(()=>{function onKey(e){const tag=document.activeElement?.tagName;if(tag==='INPUT'||tag==='TEXTAREA'||tag==='SELECT')return;if(!cards.length)return;if(e.key==='ArrowRight')cardsHook.jumpToCard(Math.min(cardsHook.index+1,cards.length-1),true);else if(e.key==='ArrowLeft')cardsHook.jumpToCard(Math.max(cardsHook.index-1,0),true);else if(e.key.toLowerCase()==='n')clipCard(cardsHook.index)};window.addEventListener('keydown',onKey);return()=>window.removeEventListener('keydown',onKey)})

  const vc=!notes.vault.configured?{cls:'warn',text:t('vault.notConfigured')}:!notes.vault.exists?{cls:'warn',text:t('vault.missing')}:{cls:'ok',text:t('vault.connected')}

  // 結果頁分頁：單欄時先看重點，換一支影片也回到重點
  const [narrow,setNarrow]=useState(()=>window.matchMedia(NARROW_QUERY).matches)
  const [resultTab,setResultTab]=useState('cards')
  useEffect(()=>{const media=window.matchMedia(NARROW_QUERY);const onChange=e=>setNarrow(e.matches);media.addEventListener('change',onChange);return()=>media.removeEventListener('change',onChange)},[])
  useEffect(()=>{setResultTab('cards')},[result?.source_url])
  const activeTab=effectiveResultTab(resultTab,narrow)
  // 只有影片結果才鎖定版面高度、讓左右兩欄各自捲動；純文章維持整頁捲動
  const splitLayout=!stream.loading&&!!result&&hasVideo&&!watching

  // 還沒有結果時以網址與開始按鈕為主；開始分析後收成一行，把空間留給影片和卡片
  const compact=!!result||stream.loading||!!stream.progress
  const source=isLocalMode?'local':detectSource(url)
  const showSourceHint=!!source&&(isLocalMode?!compact:(!compact||url.trim()!==(result?.source_url||'').trim()))
  const errorNeedsImport=needsSubtitleImport(stream.error)
  const watchVideo=!isLocalMode&&watchAvailable?watchTarget(url):null
  const watchOffer=watchVideo&&<div className="no-caption-option"><span>{t('watch.offer')}</span><button type="button" className="btn-paper" onClick={()=>setWatching(true)}>{t('watch.open')}</button></div>
  const captionAction=errorNeedsImport?noCaptionAction(source,deepVisual,!!providers?.gemini?.configured):null
  const subtitleImport=<SubtitleImportControls videoUrl={url} onChanged={()=>setSubtitleRevision(v=>v+1)}/>
  const localSubtitleControls=localVideo&&<SubtitleImportControls key={localVideo.id} videoUrl={localUrl} onChanged={()=>setSubtitleRevision(v=>v+1)} onAnalyze={handleSummarize} noFileHint={t('local.noSubtitleHint')} refreshKey={subtitleRevision}/>
  const localSpeechControls=localVideo&&<LocalSpeechControls key={`speech-${localVideo.id}`} file={localVideo.file} videoId={localVideo.id} onDone={()=>setSubtitleRevision(v=>v+1)}/>
  // 已分析的影片把字幕控制收進選單；選了別支影片就要直接看得到，不必先丟掉目前的重點
  const showLocalSubtitleRow=isLocalMode&&!!localVideo&&!stream.loading&&!stream.progress&&result?.local_video_id!==localVideo.id
  const sourceForm=(
    <section className={`input-row ${compact?'input-row-compact':'input-row-home'}`} aria-label={t('input.section')}>
      {isLocalMode?<div className="url-field local-file-field">
        <button type="button" className="btn-paper" onClick={()=>localPickerRef.current?.click()}>{t('local.pick')}</button>
        <span className="local-file-name" title={localVideo?.name||''}>{localVideo?.name||t('local.none')}</span>
      </div>:<label className="url-field">
        <input type="url" placeholder={t('input.placeholder')} aria-label={t('input.placeholder')} value={url} onChange={e=>setUrl(e.target.value)} onKeyDown={e=>e.key==='Enter'&&handleSummarize()}/>
      </label>}
      <button className="btn-go" onClick={handleSummarize} disabled={stream.loading||!!stream.progress||(isLocalMode&&!localVideo)}>{(stream.progress||stream.loading)?t('input.running'):t('input.go')}</button>
      <div className="input-options">
        <div className="source-mode" role="group" aria-label={t('input.section')}>
          <button type="button" aria-pressed={!isLocalMode} className={isLocalMode?'':'active'} onClick={()=>setSourceMode('url')}>{t('input.modeUrl')}</button>
          <button type="button" aria-pressed={isLocalMode} className={isLocalMode?'active':''} onClick={()=>setSourceMode('local')}>{t('input.modeLocal')}</button>
        </div>
        <button className="btn-paper" type="button" onClick={()=>setShowSettings(true)} title={t('ai.choose')}>{t('ai.source')}: {aiSourceLabel(provider,activeProvider,t)}</button>
        {!isLocalMode&&<details className="ai-advanced"><summary>{t('ai.advancedAnalysis')}</summary>
          <div className="ai-advanced-panel">
            <label className="deep-visual-toggle" title={bilibiliUrl?t('input.deepVisualBilibili'):t('input.deepVisualTitle')}>
              <input type="checkbox" checked={deepVisual&&!bilibiliUrl} disabled={bilibiliUrl} aria-describedby={bilibiliUrl?'deep-visual-note':undefined} onChange={e=>setDeepVisual(e.target.checked)}/>
              <span><strong>{t('input.deepVisual')}</strong>{bilibiliUrl&&<small id="deep-visual-note"> · {t('input.deepVisualBilibiliShort')}</small>}</span>
            </label>
            {!errorNeedsImport&&subtitleImport}
            {watchVideo&&<button type="button" className="btn-paper watch-option" onClick={()=>setWatching(true)}>{t('watch.optionButton')}</button>}
          </div>
        </details>}
        {isLocalMode&&localVideo&&result?.local_video_id===localVideo.id&&<details className="ai-advanced"><summary>{t('local.subtitles')}</summary>
          <div className="ai-advanced-panel">{localSubtitleControls}{localSpeechControls}</div>
        </details>}
      </div>
    </section>
  )

  return (
    <>
      <header className={`topbar ${compact?'topbar-compact':''}`}>
        <div className="brand">
          <BrandMark/>
          <div className="brand-copy"><h1>{t('app.name')}</h1></div>
        </div>
        {compact&&sourceForm}
        {notes.vault.configured&&<span className={`vault-chip ${vc.cls}`}><span className="dot"/> {vc.text}</span>}
        <button className="btn-gear" onClick={()=>setShowSettings(true)}>{t('topbar.settings')}</button>
      </header>
      {!compact&&sourceForm}
      <input ref={localPickerRef} type="file" accept="video/*,.mkv,.mov,.m4v,.avi" hidden onChange={pickLocalVideo} aria-label={t('local.pick')}/>
      {showSourceHint&&<p className={`source-hint ${compact?'source-hint-compact':''}`} role="status">{t(sourceHintKey(source))}</p>}
      {visualNotice&&<p className={`source-hint visual-notice ${compact?'source-hint-compact':''}`} role="status"><span>{t(visualNotice==='gemini'?'ai.deepVisualGemini':'ai.deepVisualNoKey')}</span>{visualNotice==='no-key'&&<button type="button" className="btn-paper" onClick={openVisualKeySettings}>{t('noCaption.addKeyAction')}</button>}</p>}
      <GenerationProgress progress={stream.progress}/>
      {showLocalSubtitleRow&&<div className="local-subtitle-row">{localSubtitleControls}{localSpeechControls}</div>}
      {stream.error&&<div className="error-block"><p className="error-bar">{stream.error}</p>{errorNeedsImport&&!isLocalMode&&<SubtitleImportControls videoUrl={url} onChanged={()=>setSubtitleRevision(v=>v+1)} onAnalyze={handleSummarize} noFileHint={watchVideo?t('subtitles.importNoFileWatch'):captionAction?t('subtitles.importNoFileVisual'):undefined}/>}{errorNeedsImport&&watchOffer}{captionAction&&<div className="no-caption-option"><span>{t(captionAction==='add-key'?'noCaption.addKey':'noCaption.enableVisual')}</span>{captionAction==='add-key'?<button type="button" className="btn-paper" onClick={openVisualKeySettings}>{t('noCaption.addKeyAction')}</button>:<button type="button" className="btn-paper" onClick={analyzeWithVisual}>{t('noCaption.enableVisualAction')}</button>}</div>}</div>}
      {stream.notice&&<p className="error-bar" role="status">{stream.notice}</p>}
      {/* 有影片時左右並排；純文章來源則讓重點區佔滿 */}
      <main className={`workspace ${splitLayout?'workspace-split':''}`} data-result-tab={splitLayout&&narrow?activeTab:undefined} ref={workspaceRef}>
        {watching&&watchVideo?<WatchAlong key={`${watchVideo.platform}:${watchVideo.videoId}:${watchVideo.page}`} target={watchVideo} onFinished={finishWatching} onClose={()=>setWatching(false)}/>:stream.loading?<div className="loading-space" aria-hidden="true"/>
        :!result?<div className="empty-state"><span className="empty-logo"><BrandMark/><strong>{t('app.name')}</strong></span><p className="empty-tagline">{t('app.tagline')}</p><ol className="empty-steps"><li>{t('empty.step1')}</li><li>{t('empty.step2')}</li><li>{t('empty.step3')}</li></ol></div>
        :<>{hasVideo&&<VideoPane localSrc={localVideo?.id===result.local_video_id?localVideo.src:null} onPickLocal={()=>localPickerRef.current?.click()} videoId={isLocalResult?result.local_video_id:isBilibili?result.bilibili_video_id:result.youtube_video_id} platform={isLocalResult?'local':isBilibili?'bilibili':'youtube'} page={result.bilibili_page||1} provider={activeProvider} subtitleRevision={subtitleRevision} startAt={cardsHook.startAt} cards={cards} activeIndex={cardsHook.index} onJump={i=>cardsHook.jumpToCard(i,true)} tabs={resultTabs(narrow)} tab={activeTab} onTabChange={setResultTab}/>}{hasVideo&&<Splitter onCommit={setSplit}/>}<CardDeck result={result} index={cardsHook.index} setIndex={cardsHook.setIndex} clippedIds={cardsHook.clippedIds} onClip={clipCard} onJumpVideo={i=>cardsHook.jumpToCard(i,true)} deepdives={cardsHook.deepdives} onDeepDive={onDeepDive} deepdiveLoading={cardsHook.ddLoading} onImplement={implement.start} fullWidth={!hasVideo} /></>}
      </main>
      {/* 筆記／問模型：可最小化浮窗，不佔用主版面，展開/收合狀態記在 localStorage */}
      {result&&<>
        <FloatingPanel id="notes" corner="br" title={t('panel.notes')} badge={cardsHook.clips.length||null}>
          <NotesPanel onExport={handleExportNotes} vault={notes.vault} clips={cardsHook.clips} onClipNoteChange={cardsHook.updateClipNote} onRemoveClip={cardsHook.removeClip} freeNote={freeNote} setFreeNote={setFreeNote} filename={filename} setFilename={setFilename} onSave={handleSave} saving={notes.saving} folders={notes.folders} noteFiles={notes.noteFiles} saveOpts={notes.saveOpts} onSaveOptsChange={notes.onSaveOptsChange}/>
        </FloatingPanel>
        <FloatingPanel id="ask" corner="bl" title={t('panel.ask')}>
          <AskPanel provider={activeProvider} videoId={result?.local_video_id?`local:${result.local_video_id}`:result?.youtube_video_id||(result?.bilibili_video_id?`bilibili:${result.bilibili_video_id}:p${result.bilibili_page||1}`:null)}/>
        </FloatingPanel>
      </>}
      {implement.open&&<ImplementModal state={implement} providers={providers} selectedProvider={activeProvider} onClose={implement.close} onToast={showToast}/>}
      {toast&&<div className={`toast ${toast.isErr?'err':''}`}>{toast.msg}</div>}
      {(needsSetup||showSettings)&&<SettingsModal state={settings} mandatory={needsSetup} focus={settingsFocus} provider={provider} providers={providers} onProviderChange={setAiSource} onClose={()=>{setShowSettings(false);setSettingsFocus(null);refreshModels()}} onSaved={handleSettingsSaved}/>}
    </>
  )
}
