// UI 模式切換不應意外使用雲端付費翻譯或未知的 Ollama 模型。
export function effectiveSubtitleTranslationProvider(developerMode, selection, installedModels = []) {
  if (!developerMode || typeof selection !== 'string') return 'opencode'
  if (!selection.startsWith('ollama:')) return 'opencode'
  const model = selection.slice('ollama:'.length)
  return installedModels.includes(model) ? selection : 'opencode'
}
