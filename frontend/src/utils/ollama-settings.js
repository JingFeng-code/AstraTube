// 設定畫面的 Ollama 模型下拉選單：只列出這台電腦真的已安裝的模型。
// 已儲存但目前不在清單中的模型會保留並標示，不會被默默換掉。
export function ollamaModelOptions(installed, saved = '') {
  const models = Array.isArray(installed) ? installed.filter(m => typeof m === 'string' && m) : []
  const options = [{ value: '', kind: 'auto' }, ...models.map(value => ({ value, kind: 'installed' }))]
  const current = (saved || '').trim()
  if (current && !models.includes(current)) options.push({ value: current, kind: 'missing' })
  return options
}
