import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import { I18nProvider } from './i18n/index.jsx'
import { bootstrapDesktop } from './desktop.js'
import './index.css'

const root=ReactDOM.createRoot(document.getElementById('root'))
bootstrapDesktop().then(()=>{
  root.render(<React.StrictMode><I18nProvider><App /></I18nProvider></React.StrictMode>)
}).catch(error=>{
  root.render(<main style={{padding:32,fontFamily:'sans-serif'}}>
    <h1>AstraTube 無法啟動</h1>
    {/* 原因由桌面程式提供（例如資料夾無法寫入），直接顯示給使用者 */}
    <p style={{whiteSpace:'pre-wrap',lineHeight:1.7}}>{String(error?.message||error)}</p>
    <p>如果問題持續，請把這段文字回報給開發者。</p>
  </main>)
})
