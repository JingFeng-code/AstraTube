import { useEffect, useState } from 'react'
import * as api from '../api.js'

// 後端 /settings 狀態；首次啟動且尚未設定任何金鑰時 needsSetup=true，強制顯示設定導引
export default function useSettings() {
  const [settings, setSettings] = useState(null)
  useEffect(() => { api.getSettings().then(setSettings) }, [])
  const needsSetup = !!settings && !settings.offline && !settings.configured
  const refresh = () => api.getSettings().then(setSettings)
  return { settings, setSettings, needsSetup, refresh }
}
