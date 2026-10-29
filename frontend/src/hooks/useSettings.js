import { useEffect, useState } from 'react'
import * as api from '../api.js'

// 開源免費文字模型不需要 API Key；首次開啟不強制使用者進入金鑰設定。
export default function useSettings() {
  const [settings, setSettings] = useState(null)
  useEffect(() => { api.getSettings().then(setSettings) }, [])
  const needsSetup = false
  const refresh = () => api.getSettings().then(setSettings)
  return { settings, setSettings, needsSetup, refresh }
}
