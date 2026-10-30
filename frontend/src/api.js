import { getDesktopConnection } from './desktop.js'
// 預設透過 Vite 同源 /api 代理呼叫 FastAPI，支援 Codespaces 與本地開發。
// 正式部署時需提供 /api 反向代理；也可使用 VITE_API_BASE 覆寫。
const BASE = import.meta.env?.VITE_API_BASE || '/api'
export function apiFetch(path,options={}) {
  const desktop=getDesktopConnection()
  if (!desktop) return fetch(BASE+path,options)
  return fetch(desktop.origin+path,{...options,headers:{...options.headers,'X-Astra-Desktop-Token':desktop.token}})
}

async function post(path, body) {
  const res = await apiFetch(path, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
  if (!res.ok) { let m='HTTP '+res.status; try{const d=await res.json();m=d.detail||JSON.stringify(d)}catch{} throw new Error(m) }
  return res.json()
}
async function get(path) {
  const res = await apiFetch(path)
  if (!res.ok) throw new Error('HTTP '+res.status)
  return res.json()
}
// NDJSON 串流共用解析（摘要與實作都走這條）。
// 只吞壞行，不吞 onEvent 內拋出的錯（如 fatal）——那是呼叫端要處理的。
async function postStream(path, body, onEvent) {
  const res = await apiFetch(path, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
  if (!res.ok) { let m='HTTP '+res.status; try{const d=await res.json();m=d.detail||JSON.stringify(d)}catch{} throw new Error(m) }
  const reader = res.body.getReader(), dec = new TextDecoder()
  let buf = ''
  while (true) {
    const {done, value} = await reader.read()
    if (done) break
    buf += dec.decode(value, {stream:true})
    let i
    while ((i = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, i).trim(); buf = buf.slice(i+1)
      if (!line) continue
      let evt
      try { evt = JSON.parse(line) } catch { continue }
      onEvent(evt)
    }
  }
}
export const summarize = (url, provider, deep_visual=false) => post('/summarize', {url, provider, deep_visual})
// 串流版：邊生成邊回傳。segment_status 會帶出 API 等待、重試與模型切換狀態。
export const summarizeStream = (url, provider, deep_visual=false, onEvent) =>
  postStream('/summarize_stream', {url, provider, deep_visual}, onEvent)
export const deepdive  = (provider, source_title, card) => post('/deepdive', {provider, source_title, card})
// 實作：把整支影片交給本機 CLI agent 產出實體檔案。
// status 先問「這台機器有沒有 CLI」，前端據此決定顯示執行、指令、還是安裝教學。
export async function implementStatus() {
  try { return await get('/implement/status') }
  catch { return {clis:[],has_cli:false,auto_run:false,output_dir:'',install:[],offline:true} }
}
export const implementStream = (payload, onEvent) => postStream('/implement', payload, onEvent)
export const revealOutput = (path) => post('/implement/reveal', {path})
// 讀產出的單一檔案，讓結果直接顯示在 app 裡（不必使用者自己去開資料夾）
export const readOutputFile = (path) => get('/implement/file?path=' + encodeURIComponent(path))
// 自由聊天室：以整支影片為背景知識問答。history 為目前為止的對話（不含本次 question）
export const ask = (payload) => post('/ask', payload)
// 僅回傳可公開取得的字幕時間軸；翻譯會在後續獨立功能提供。
export async function getSubtitles(platform, videoId, page=1, translationProvider='opencode') {
  const path = '/subtitles?platform='+encodeURIComponent(platform)
    +'&video_id='+encodeURIComponent(videoId)
    +'&page='+encodeURIComponent(page)
    +'&translation_provider='+encodeURIComponent(translationProvider)
  const res = await apiFetch(path)
  if (!res.ok) {
    const data = await res.json().catch(() => null)
    throw new Error(data?.detail || 'HTTP '+res.status)
  }
  return res.json()
}
// 匯入的是使用者有權持有的字幕文字，不下載影片。
export const importSubtitleFile = (videoUrl, filename, content) => post('/subtitles/imported', {video_url:videoUrl, filename, content})
export const removeImportedSubtitles = videoUrl => post('/subtitles/imported/remove', {video_url:videoUrl})
export const importedSubtitleStatus = videoUrl => post('/subtitles/imported/status', {video_url:videoUrl})
export const translateSubtitles = (platform, videoId, page=1, startIndex=0, batchSize=16, translationProvider='opencode') =>
  post('/subtitles/translate', {platform, video_id:videoId, page, start_index:startIndex, batch_size:batchSize, translation_provider:translationProvider})
export const saveNote  = (payload) => post('/notes/save', payload)
export async function notesStatus() {
  try { const r=await apiFetch('/notes/status'); return r.ok?r.json():{configured:false,exists:false} }
  catch { return {configured:false,exists:false,offline:true} }
}
export async function notesFolders() {
  try { return await get('/notes/folders') } catch { return {folders:[],default:''} }
}
export async function notesFiles(folder) {
  try { return await get('/notes/files?folder='+encodeURIComponent(folder||'')) } catch { return {files:[]} }
}
export async function getSettings() {
  try { const r=await apiFetch('/settings'); return r.ok?r.json():{configured:false,offline:true} }
  catch { return {configured:false,offline:true} }
}
export const saveSettings = (payload) => post('/settings', payload)
// 只檢查指定供應商；暫時輸入的 API Key 不會儲存，成功後才讓使用者選模型。
export const checkProvider = (payload) => post('/providers/check', payload)
// 不需先儲存：帶入設定畫面上目前輸入的網址（後端仍只接受本機 11434 埠）
export const getOllamaStatus = (baseUrl) => get('/ollama/status' + (baseUrl ? '?base_url=' + encodeURIComponent(baseUrl) : ''))
// 模型下拉選單清單；後端未就緒時回 null，由呼叫端退回靜態清單
export async function getModels() {
  try { return await get('/models') } catch { return null }
}
