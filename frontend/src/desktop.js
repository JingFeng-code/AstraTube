// Tauri v2 bridge. The session token is never persisted to storage.
let connection=null
export function getDesktopConnection(){return connection}
export async function bootstrapDesktop(){
  if(!window.__TAURI_INTERNALS__)return false
  const invoke=window.__TAURI__?.core?.invoke
  if(typeof invoke!=='function')throw new Error('桌面程式介面無法使用，請重新開啟 AstraTube。')
  // 桌面程式無法啟動後端時會回傳原因字串（例如免安裝版的資料夾無法寫入）
  const result=await invoke('desktop_connection').catch(reason=>{throw new Error(typeof reason==='string'?reason:'AstraTube 桌面程式沒有回應，請重新開啟。')})
  const port=Number(result?.port), token=result?.token
  if(!Number.isInteger(port)||port<1024||port>65535||typeof token!=='string'||token.length<32)
    throw new Error('桌面工作階段資訊不正確，請重新開啟 AstraTube。')
  const session={origin:'http://127.0.0.1:'+port,token}
  for(let attempt=0;attempt<80;attempt++){
    try{
      const r=await fetch(session.origin+'/health',{headers:{'X-Astra-Desktop-Token':token}})
      if(r.ok&&(await r.json()).status==='ok'){connection=session;return true}
    }catch{/* Packaged Python backend is starting. */}
    await new Promise(resolve=>setTimeout(resolve,300))
  }
  throw new Error('AstraTube 背景服務沒有在時間內啟動。請重新開啟程式；如果持續發生，請確認防毒軟體沒有阻擋程式資料夾中的 astratube-backend.exe。')
}
