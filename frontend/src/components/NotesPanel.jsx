import { fmtTime } from '../utils.js'
import { useI18n } from '../i18n/index.jsx'

export default function NotesPanel({ vault, clips, onClipNoteChange, onRemoveClip, freeNote, setFreeNote, filename, setFilename, onSave, saving, folders, noteFiles, saveOpts, onSaveOptsChange }) {
  const { t } = useI18n()
  const vs=!vault.configured?{cls:'warn',text:t('vault.notConfigured')}:!vault.exists?{cls:'warn',text:t('vault.missing')}:{cls:'ok',text:t('vault.connected')}
  const isAppend=saveOpts.mode==='append'
  const canSave=!saving&&(clips.length>0||freeNote.trim())&&(!isAppend||saveOpts.targetFile)
  return (
    <aside className="notes">
      <div className="notes-head"><h3>{t('notes.title')}</h3><span className="count">{t('notes.count',clips.length)}</span></div>
      <div className="clip-list">
        {clips.length===0?<p className="empty-clip">{t('notes.empty')}</p>
          :clips.map(c=>(
            <div className="clip-item" key={c.id}>
              <div className="clip-head">{c.ts!=null&&<span className="ts">{fmtTime(c.ts)}</span>}<strong>{c.heading}</strong><button className="rm" onClick={()=>onRemoveClip(c.id)} aria-label={t('notes.remove')}>×</button></div>
              <textarea placeholder={t('notes.thought')} value={c.note} onChange={e=>onClipNoteChange(c.id,e.target.value)}/>
            </div>
          ))
        }
      </div>
      <textarea className="free-note" placeholder={t('notes.free')} value={freeNote} onChange={e=>setFreeNote(e.target.value)}/>

      {vault.configured&&(
        <div className="save-config">
          <label className="cfg-row">
            <span className="cfg-label">{t('notes.folder')}</span>
            <select value={saveOpts.folder} onChange={e=>onSaveOptsChange({folder:e.target.value})}>
              {folders.length===0&&<option value="">{t('notes.folderDefault')}</option>}
              {folders.map(f=><option key={f} value={f}>{f===''?t('notes.vaultRoot'):f}</option>)}
            </select>
          </label>
          <div className="mode-toggle">
            <button className={!isAppend?'on':''} onClick={()=>onSaveOptsChange({mode:'new'})}>{t('notes.modeNew')}</button>
            <button className={isAppend?'on':''} onClick={()=>onSaveOptsChange({mode:'append'})}>{t('notes.modeAppend')}</button>
          </div>
          {isAppend?(
            <label className="cfg-row">
              <span className="cfg-label">{t('notes.pick')}</span>
              <select value={saveOpts.targetFile} onChange={e=>onSaveOptsChange({targetFile:e.target.value})}>
                <option value="">{t('notes.pickPlaceholder')}</option>
                {noteFiles.map(f=><option key={f} value={f}>{f.replace(/\.md$/,'')}</option>)}
              </select>
            </label>
          ):(
            <input className="fname" type="text" placeholder={t('notes.filename')} value={filename} onChange={e=>setFilename(e.target.value)}/>
          )}
          {isAppend&&noteFiles.length===0&&<p className="cfg-note">{t('notes.emptyFolder')}</p>}
        </div>
      )}

      <button className="btn-save" onClick={onSave} disabled={!canSave}>{saving?t('notes.saving'):isAppend?t('notes.append'):t('notes.save')}</button>
      <p className="save-hint"><span className={`vault-chip ${vs.cls}`} style={{marginLeft:0}}><span className="dot"/> {vs.text}</span><br/>{vault.configured?`vault：${vault.path?.replace(/[/\\][^/\\]*$/,'')||vault.path}`:t('notes.vaultHint')}</p>
    </aside>
  )
}
