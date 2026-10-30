import { useEffect, useState } from 'react'
import * as api from '../api.js'

// 首次開啟不強制進入設定；開始分析時若尚未選擇 AI，才會開啟設定並提示。
export default function useSettings() {
  const [settings, setSettings] = useState(null)
  useEffect(() => { api.getSettings().then(setSettings) }, [])
  const needsSetup = false
  const refresh = () => api.getSettings().then(setSettings)
  return { settings, setSettings, needsSetup, refresh }
}
