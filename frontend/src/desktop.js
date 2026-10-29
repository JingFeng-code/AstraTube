// Tauri v2 bridge. The session token is never persisted to storage.
let connection=null
export function getDesktopConnection(){return connection}
export async function bootstrapDesktop(){
  if(!window.__TAURI_INTERNALS__)return false
  const invoke=window.__TAURI__?.core?.invoke
  if(typeof invoke!=='function')throw new Error('Tauri bridge unavailable.')
  const result=await invoke('desktop_connection')
  const port=Number(result?.port), token=result?.token
  if(!Number.isInteger(port)||port<1024||port>65535||typeof token!=='string'||token.length<32)
    throw new Error('Invalid desktop session.')
  const session={origin:'http://127.0.0.1:'+port,token}
  for(let attempt=0;attempt<80;attempt++){
    try{
      const r=await fetch(session.origin+'/health',{headers:{'X-Astra-Desktop-Token':token}})
      if(r.ok&&(await r.json()).status==='ok'){connection=session;return true}
    }catch{/* Packaged Python backend is starting. */}
    await new Promise(resolve=>setTimeout(resolve,300))
  }
  throw new Error('AstraTube background service did not start.')
}
