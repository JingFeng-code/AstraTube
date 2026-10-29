// 使用者模式只控制介面可見性，不是 API 授權機制。
export const DEFAULT_FREE_PROVIDER = 'opencode:deepseek-v4-flash-free'

export function isDeveloperModeSetting(value) {
  return value === '1'
}

export function effectiveProvider(developerMode, selectedProvider) {
  return developerMode ? (selectedProvider || DEFAULT_FREE_PROVIDER) : DEFAULT_FREE_PROVIDER
}

export function effectiveDeepVisual(developerMode, enabled) {
  return Boolean(developerMode && enabled)
}
