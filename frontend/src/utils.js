export function fmtTime(sec) {
  if (sec==null||isNaN(sec)) return ''
  const s=Math.max(0,Math.floor(sec)),h=Math.floor(s/3600),m=Math.floor((s%3600)/60),ss=String(s%60).padStart(2,'0')
  return h>0?`${h}:${String(m).padStart(2,'0')}:${ss}`:`${m}:${ss}`
}
export const youtubeLink=(id,sec)=>sec!=null?`https://www.youtube.com/watch?v=${id}&t=${Math.floor(sec)}s`:`https://www.youtube.com/watch?v=${id}`
export const TRANSCRIPT_KEYS=['transcript_highlight','transcript','key_transcript','quote','original_text']
export const TRANSLATION_KEYS=['translation','translated_text','zh_translation']
export function pickField(card,keys){for(const k of keys)if(typeof card?.[k]==='string'&&card[k].trim())return card[k];return null}

// meta.transcript_source → i18n key
export const TRANSCRIPT_SOURCE_KEYS={deepsrt:'source.deepsrt','deepsrt+captions':'source.deepsrtCaptions',captions:'source.captions',whisper:'source.whisper'}

// 把 summary 字串拆成條列點（支援 •、-、換行）
export function summaryLines(summary){
  if(!summary) return []
  return summary.split(/\r?\n|(?=•\s)/).map(s=>s.replace(/^[•\-*]\s*/,'').trim()).filter(Boolean)
}

function knowledgeBlock(clips,t){
  const L=[]
  for(const c of clips){
    const ts=c.link&&c.ts!=null?` ([${fmtTime(c.ts)}](${c.link}))`:''
    L.push(`### ${c.heading}${ts}`,'')
    if(c.summary){for(const line of summaryLines(c.summary))L.push(`- ${line}`);L.push('')}
    if(c.transcript){L.push(`> ${t('note.quote')}：`+c.transcript.trim().replace(/\n/g,'\n> '),'');if(c.translation?.trim())L.push('> '+c.translation.trim().replace(/\n/g,'\n> '),'')}
    if(c.visual?.trim())L.push(`> ${t('note.visual')}：`+c.visual.trim().replace(/\n/g,'\n> '),'')
    if(c.note?.trim())L.push(`> ${t('note.myNote')}：${c.note.trim()}`,'')
  }
  return L
}

// mode: 'new' 產生含 frontmatter 的完整筆記；'append' 產生附加區塊
export function buildMarkdown({title,sourceUrl,clips,freeNote,mode='new',t}){
  const today=new Date().toISOString().slice(0,10)
  const L=[]
  if(mode==='append'){
    L.push('---','',`## ${title||t('note.summary')}　${today}`,'')
    if(sourceUrl)L.push(`${t('note.source')}: ${sourceUrl}`,'')
  }else{
    L.push('---',`${t('note.source')}: ${sourceUrl||''}`,`${t('note.date')}: ${today}`,`${t('note.tags')}: [youtube-card-reader]`,'---','',`# ${title||t('note.untitled')}`,'')
  }
  if(clips.length>0){L.push(`## ${t('note.highlights')}`,'');L.push(...knowledgeBlock(clips,t))}
  if(freeNote?.trim())L.push(`## ${t('note.scratch')}`,'',freeNote.trim(),'')
  return L.join('\n')
}
