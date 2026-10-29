// 後端位址。預設 127.0.0.1:8420；用 VITE_API_BASE 覆寫（例如把後端跑在別台機器上）。
const BASE = import.meta.env?.VITE_API_BASE || 'http://127.0.0.1:8420'

async function post(path, body) {
  const res = await fetch(BASE+path, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
  if (!res.ok) { let m='HTTP '+res.status; try{const d=await res.json();m=d.detail||JSON.stringify(d)}catch{} throw new Error(m) }
  return res.json()
}
async function get(path) {
  const res = await fetch(BASE+path)
  if (!res.ok) throw new Error('HTTP '+res.status)
  return res.json()
}
// NDJSON 串流共用解析（摘要與實作都走這條）。
// 只吞壞行，不吞 onEvent 內拋出的錯（如 fatal）——那是呼叫端要處理的。
async function postStream(path, body, onEvent) {
  const res = await fetch(BASE+path, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
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
  catch { return {clis:[],has_cli:false,auto_run:true,output_dir:'',install:[],offline:true} }
}
export const implementStream = (payload, onEvent) => postStream('/implement', payload, onEvent)
export const revealOutput = (path) => post('/implement/reveal', {path})
// 讀產出的單一檔案，讓結果直接顯示在 app 裡（不必使用者自己去開資料夾）
export const readOutputFile = (path) => get('/implement/file?path=' + encodeURIComponent(path))
// 自由聊天室：以整支影片為背景知識問答。history 為目前為止的對話（不含本次 question）
export const ask = (payload) => post('/ask', payload)
export const saveNote  = (payload) => post('/notes/save', payload)
export async function notesStatus() {
  try { const r=await fetch(BASE+'/notes/status'); return r.ok?r.json():{configured:false,exists:false} }
  catch { return {configured:false,exists:false,offline:true} }
}
export async function notesFolders() {
  try { return await get('/notes/folders') } catch { return {folders:[],default:''} }
}
export async function notesFiles(folder) {
  try { return await get('/notes/files?folder='+encodeURIComponent(folder||'')) } catch { return {files:[]} }
}
export async function getSettings() {
  try { const r=await fetch(BASE+'/settings'); return r.ok?r.json():{configured:false,offline:true} }
  catch { return {configured:false,offline:true} }
}
export const saveSettings = (payload) => post('/settings', payload)
// 模型下拉選單清單；後端未就緒時回 null，由呼叫端退回靜態清單
export async function getModels() {
  try { return await get('/models') } catch { return null }
}
