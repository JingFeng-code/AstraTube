import { useEffect, useRef, useState } from 'react'
import * as api from '../api.js'
import MarkdownText from './MarkdownText.jsx'
import ImplementProgress from './ImplementProgress.jsx'
import OutputViewer from './OutputViewer.jsx'
import { TRACKS, hasCode } from '../hooks/useImplement.js'
import { useI18n } from '../i18n/index.jsx'

function Bytes({ n }) {
  return <span className="impl-size">{n < 1024 ? `${n} B` : `${Math.round(n / 1024)} KB`}</span>
}

export default function ImplementModal({ state, providers, onClose, onToast }) {
  const { t } = useI18n()
  const { status, track, setTrack, cli, setCli, cliModel, setCliModel, running, lines, outcome,
          suggested, cardCount, phase, liveFiles, startedAt, activity } = state
  const [copied, setCopied] = useState(false)
  const logRef = useRef(null)

  // 執行中把輸出釘在底部，看得到最新進度
  useEffect(() => { logRef.current?.scrollTo({ top: logRef.current.scrollHeight }) }, [lines.length])

  const hasCli = status?.has_cli
  const kind = outcome?.kind
  const started = !!kind
  // 純 API 引擎（gemini / opencode:xxx …）：單次生成，上不了網，也沒辦法多輪修正
  const cliNames = new Set((status?.clis || []).map(c => c.name))
  const usingApi = !!cli && !cliNames.has(cli)
  // 一個選單講完「哪個工具跑、用哪個模型」。value 是 "<引擎>::<模型>"，模型留空＝用該工具的預設。
  const cliOptions = []
  for (const c of status?.clis || []) {
    // 每個 CLI 自己一段，段內才排序——否則「預設」選項會跑到整份清單的最前面
    const group = []
    const models = c.models || []
    if (!c.default_model) {
      group.push({ value: `${c.name}::`, label: `${c.label} · ${t('implement.builtinModel')}` })
    }
    for (const m of models) {
      // 目前生效的那個標出來，值留空＝不加 --model，交回 CLI 自己決定
      const isDefault = m.value === c.default_model
      group.push({ value: `${c.name}::${isDefault ? '' : m.value}`,
                   label: `${c.label} · ${m.label}${isDefault ? t('implement.currentDefault') : ''}` })
    }
    if (!group.length) group.push({ value: `${c.name}::`, label: `${c.label} · ${c.default_model || t('implement.builtinModel')}` })
    cliOptions.push(...group)
  }
  const apiOptions = []
  if (status?.gemini_ready) apiOptions.push({ value: 'gemini::', label: `Gemini · ${status.gemini_model}` })
  for (const key of Object.keys(providers || {})) {
    const p = providers[key]
    if (key === 'gemini' || !p || (!p.free && !p.configured)) continue
    for (const m of p.models || []) apiOptions.push({ value: `${key}:${m}::`, label: `${p.label} · ${m}` })
  }
  // build 的前提是「影片教你做出某個東西」。不成立的話產出會變成把影片重講一遍，
  // 所以選了就一定提醒；卡片裡連指令或程式碼都沒有時再加重成警告。
  const activeTrack = track || suggested
  const buildRisky = activeTrack === 'build' && !hasCode(state.cards || [])
  const engineValue = `${cli}::${cliModel}`
  const pickEngine = (v) => { const i = v.lastIndexOf('::'); setCli(v.slice(0, i)); setCliModel(v.slice(i + 2)) }

  async function copy(text) {
    try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000) }
    catch { onToast(t('implement.copyFailed'), true) }
  }

  async function reveal(path) {
    try { await api.revealOutput(path); onToast(t('implement.opened')) }
    catch (e) { onToast(e.message, true) }
  }

  return (
    <div className="settings-overlay" onMouseDown={e => { if (e.target === e.currentTarget && !running) onClose() }}>
      <div className="settings-card impl-card" role="dialog" aria-modal="true" aria-label={t('implement.heading')}>
        <div className="settings-head">
          <div>
            <h2>{t('implement.heading')}</h2>
            <p className="settings-sub">{t('implement.sub', cardCount)}</p>
          </div>
          <button className="settings-x" onClick={onClose} disabled={running} aria-label={t('implement.close')}>×</button>
        </div>

        <div className="settings-body">
          {!started && <>
            <label className="settings-field">
              <span className="settings-label">{t('implement.track')}</span>
              <select value={track || suggested} onChange={e => setTrack(e.target.value)}>
                {TRACKS.map(tr => <option key={tr} value={tr}>{t(`implement.track.${tr}`)}</option>)}
              </select>
              <span className="settings-hint">{t(`implement.trackHint.${activeTrack}`)}</span>
            </label>

            {activeTrack === 'build' && <p className={buildRisky ? 'impl-warn' : 'impl-note'}>
              {buildRisky ? t('implement.buildRisky') : t('implement.buildCheck')}
            </p>}

            {/* CLI 只給 Codex 與 Claude Code：實作要能讀寫檔案、能上網查證，
                摘要用的那些便宜模型做不到，只會編出點下去 404 的連結 */}
            {status && (hasCli || apiOptions.length > 0) && <label className="settings-field">
              <span className="settings-label">{t('implement.engine')}</span>
              <select value={engineValue} onChange={e => pickEngine(e.target.value)}>
                {hasCli && <optgroup label={t('implement.engineCli')}>
                  {cliOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                </optgroup>}
                {apiOptions.length > 0 && <optgroup label={t('implement.engineApi')}>
                  {apiOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                </optgroup>}
              </select>
              <span className="settings-hint">{t('implement.outputTo', status.output_dir)}</span>
            </label>}

            {/* 這段是這個功能最重要的誠實揭露：API 產出的內容沒有經過任何查證 */}
            {usingApi && <p className="impl-warn">{t('implement.apiWarn')}</p>}
            {status && !hasCli && <p className="impl-warn">{t('implement.noCliWarn')}</p>}

            <div className="impl-actions">
              <button className="btn-clip" disabled={!status || running} onClick={() => state.run({ autoRun: true })}>
                {hasCli || apiOptions.length > 0 ? t('implement.run') : t('implement.teachMe')}
              </button>
              {hasCli && <button className="btn-paper" disabled={running} onClick={() => state.run({ autoRun: false })}>
                {t('implement.manualOnly')}
              </button>}
            </div>
          </>}

          {kind === 'running' && <>
            <p className="impl-status">{t('implement.running', outcome.cli_label, t(`implement.track.${outcome.track}`))}</p>
            <ImplementProgress phase={phase} files={liveFiles} startedAt={startedAt} running={running} activity={activity}/>
          </>}
          {kind === 'teaching' && <p className="impl-status">{t('implement.teaching')}</p>}

          {/* 原始輸出留著但收起來：要除錯的人打得開，一般使用者不必看 */}
          {lines.length > 0 && <details className="impl-logwrap">
            <summary>{t('implement.rawLog', lines.length)}</summary>
            <div className="impl-log" ref={logRef}>
              {lines.map((l, i) => <div key={i}>{l}</div>)}
            </div>
          </details>}

          {kind === 'teach' && <div className="impl-teach">
            <MarkdownText>{outcome.content}</MarkdownText>
          </div>}

          {kind === 'manual' && <section className="impl-block">
            <h3>{t('implement.manualHeading')}</h3>
            <p className="settings-hint">{t('implement.manualHint')}</p>
            <div className="brief-cmd">
              <code>{outcome.command}</code>
              <button className="btn-paper" onClick={() => copy(outcome.command)}>{copied ? t('implement.copied') : t('implement.copyCmd')}</button>
            </div>
            <button className="btn-paper" onClick={() => reveal(outcome.workdir)}>{t('implement.openFolder')}</button>
          </section>}

          {kind === 'error' && <>
            <p className="impl-warn">{outcome.error}</p>
            {outcome.command && <div className="brief-cmd">
              <code>{outcome.command}</code>
              <button className="btn-paper" onClick={() => copy(outcome.command)}>{copied ? t('implement.copied') : t('implement.copyCmd')}</button>
            </div>}
          </>}

          {kind === 'done' && <section className="impl-block">
            <h3>{t('implement.doneHeading', outcome.produced ?? 0)}</h3>
            {/* API 產出沒有經過查證，交付時要再講一次，不能只在開始前提醒 */}
            {outcome.unverified && <p className="impl-warn">{t('implement.doneUnverified')}</p>}
            {outcome.files?.length > 0
              ? <ul className="impl-files">{outcome.files.map(f => <li key={f.path}>
                  <span className="impl-file">{f.name}</span><Bytes n={f.bytes} />
                </li>)}</ul>
              : <p className="settings-hint">{t('implement.nothingProduced')}</p>}
            <button className="btn-paper" onClick={() => reveal(outcome.workdir)}>{t('implement.openFolder')}</button>
          </section>}

          {/* 做完就直接看得到，不用再點一次「打開資料夾」 */}
          {kind === 'done' && <OutputViewer files={outcome.files || []} onToast={onToast}/>}
        </div>

        <div className="settings-foot brief-foot">
          {started && !running && <button className="btn-paper" onClick={() => state.run({ autoRun: true })}>{t('implement.again')}</button>}
          <button className="btn-paper" onClick={onClose} disabled={running}>{running ? t('implement.working') : t('implement.close')}</button>
        </div>
      </div>
    </div>
  )
}
