// 讀取字幕快取可用舊相容鍵，實際翻譯必須由 VideoPane 檢查是否選定 AI。
export function effectiveSubtitleTranslationProvider(selection) { return selection || 'opencode' }
