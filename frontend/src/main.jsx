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
    <h1>AstraTube</h1>
    <p>桌面背景服務無法啟動，請重新開啟程式。如果問題持續，請回報啟動錯誤。</p>
    <pre style={{whiteSpace:'pre-wrap'}}>{String(error?.message||error)}</pre>
  </main>)
})
