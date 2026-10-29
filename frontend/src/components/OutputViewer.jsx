import { useEffect, useState } from 'react'
import * as api from '../api.js'
import MarkdownText from './MarkdownText.jsx'
import { useI18n } from '../i18n/index.jsx'

// 產出直接在 app 裡看完，不要求使用者自己去開資料夾。
// HTML 走 iframe srcdoc，且**只給 allow-scripts**：內容是 agent 生成的，
// 給了 allow-same-origin 它就能碰到父頁。代價是預覽裡的 localStorage 會失敗
// （勾選進度不會被記住），所以旁邊放一顆「用瀏覽器開」給真的要用的時候。
const SANDBOX = 'allow-scripts allow-popups allow-popups-to-escape-sandbox'

function pickFirst(files) {
  const order = ['.html', '.md', '.py', '.js', '.sh', '.txt']
  for (const ext of order) {
    const hit = files.find(f => f.name.toLowerCase().endsWith(ext))
    if (hit) return hit
  }
  return files[0]
}

export default function OutputViewer({ files, onToast }) {
  const { t } = useI18n()
  const [current, setCurrent] = useState(null)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)

  // 做完就自動把第一個檔案叫出來，不用再點一次
  useEffect(() => {
    if (!files?.length) return
    setCurrent(c => c || pickFirst(files))
  }, [files])

  useEffect(() => {
    if (!current) return
    let cancelled = false
    setLoading(true); setData(null)
    api.readOutputFile(current.path)
      .then(d => { if (!cancelled) setData(d) })
      .catch(e => { if (!cancelled) { setData({ error: e.message }) } })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [current])

  if (!files?.length) return null

  return (
    <section className="impl-viewer">
      {files.length > 1 && <div className="impl-tabs">
        {files.map(f => (
          <button key={f.path} className={`impl-tab ${current?.path === f.path ? 'on' : ''}`}
                  onClick={() => setCurrent(f)}>{f.name}</button>
        ))}
      </div>}

      <div className="impl-view-body">
        {loading && <p className="settings-hint">{t('implement.loadingPreview')}</p>}
        {data?.error && <p className="impl-warn">{data.error}</p>}
        {data?.kind === 'html' && <>
          <iframe className="impl-frame" title={data.name} sandbox={SANDBOX} srcDoc={data.content}/>
          <p className="settings-hint">{t('implement.previewNote')}</p>
        </>}
        {data?.kind === 'markdown' && <div className="impl-md"><MarkdownText>{data.content}</MarkdownText></div>}
        {(data?.kind === 'code' || data?.kind === 'text') &&
          <pre className="impl-code"><code>{data.content}</code></pre>}
      </div>
    </section>
  )
}
