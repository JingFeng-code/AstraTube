// 本地影片的識別碼與檔案檢查。影片不會離開這台電腦；分析時後端只會拿到識別碼和字幕。
const VIDEO_EXTENSION = /\.(mp4|m4v|webm|mov|mkv|avi|ogv)$/i
const SAMPLE_BYTES = 64 * 1024

export const localVideoUrl = id => `local://${id}`

export function speechPercent(done, total) {
  const ratio = total > 0 ? done / total : 0
  return Math.max(0, Math.min(100, Math.floor(ratio * 100)))
}

export function isVideoFile(file) {
  return Boolean(file) && (String(file.type || '').startsWith('video/') || VIDEO_EXTENSION.test(String(file.name || '')))
}

// 用檔案頭尾內容和大小算識別碼：不必讀完整支影片；檔案改名後也能找回已匯入的字幕。
export async function localVideoId(file) {
  const parts = [
    new TextEncoder().encode(String(file.size)),
    new Uint8Array(await file.slice(0, SAMPLE_BYTES).arrayBuffer()),
    new Uint8Array(await file.slice(Math.max(0, file.size - SAMPLE_BYTES)).arrayBuffer()),
  ]
  const joined = new Uint8Array(parts.reduce((total, part) => total + part.length, 0))
  let offset = 0
  for (const part of parts) {
    joined.set(part, offset)
    offset += part.length
  }
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', joined))
  return Array.from(digest.slice(0, 8), byte => byte.toString(16).padStart(2, '0')).join('')
}
