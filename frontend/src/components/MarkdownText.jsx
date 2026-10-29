import { Fragment } from 'react'

function inline(text, keyPrefix) {
  const parts = []
  const token = /(\*\*.+?\*\*|__.+?__|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^\s)]+\))/g
  let cursor = 0
  let match
  let index = 0
  while ((match = token.exec(text)) !== null) {
    if (match.index > cursor) parts.push(text.slice(cursor, match.index))
    const value = match[0]
    const key = `${keyPrefix}-${index++}`
    if ((value.startsWith('**') && value.endsWith('**')) || (value.startsWith('__') && value.endsWith('__'))) {
      parts.push(<strong key={key}>{value.slice(2, -2)}</strong>)
    } else if (value.startsWith('`')) {
      parts.push(<code key={key}>{value.slice(1, -1)}</code>)
    } else {
      const link = value.match(/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/)
      parts.push(link
        ? <a key={key} href={link[2]} target="_blank" rel="noreferrer">{link[1]}</a>
        : value)
    }
    cursor = match.index + value.length
  }
  if (cursor < text.length) parts.push(text.slice(cursor))
  return parts
}

function isBlockStart(line) {
  return !line.trim() || /^\s*```/.test(line) || /^\s*#{1,6}\s*/.test(line) ||
    /^\s*[-*+]\s+/.test(line) || /^\s*\d+[.)]\s+/.test(line) || /^\s*>\s?/.test(line)
}

// 只建立 React 節點，不注入 HTML；AI 回覆即使含標籤或腳本也只會顯示成文字。
export default function MarkdownText({ children }) {
  const lines = String(children || '').replace(/\r/g, '').split('\n')
  const blocks = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]
    if (!line.trim()) { i++; continue }

    if (/^\s*```/.test(line)) {
      const language = line.trim().slice(3).trim()
      const code = []
      i++
      while (i < lines.length && !/^\s*```/.test(lines[i])) code.push(lines[i++])
      if (i < lines.length) i++
      blocks.push(<pre key={`code-${i}`} data-language={language || undefined}><code>{code.join('\n')}</code></pre>)
      continue
    }

    const heading = line.match(/^\s*(#{1,6})\s*(.+)$/)
    if (heading) {
      const Heading = `h${heading[1].length}`
      blocks.push(<Heading key={`heading-${i}`}>{inline(heading[2], `heading-${i}`)}</Heading>)
      i++
      continue
    }

    const bullet = line.match(/^\s*[-*+]\s+(.+)$/)
    if (bullet) {
      const items = []
      while (i < lines.length) {
        const item = lines[i].match(/^\s*[-*+]\s+(.+)$/)
        if (!item) break
        items.push(<li key={`bullet-${i}`}>{inline(item[1], `bullet-${i}`)}</li>)
        i++
      }
      blocks.push(<ul key={`list-${i}`}>{items}</ul>)
      continue
    }

    const numbered = line.match(/^\s*\d+[.)]\s+(.+)$/)
    if (numbered) {
      const items = []
      while (i < lines.length) {
        const item = lines[i].match(/^\s*\d+[.)]\s+(.+)$/)
        if (!item) break
        items.push(<li key={`number-${i}`}>{inline(item[1], `number-${i}`)}</li>)
        i++
      }
      blocks.push(<ol key={`list-${i}`}>{items}</ol>)
      continue
    }

    if (/^\s*>\s?/.test(line)) {
      const quote = []
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) quote.push(lines[i++].replace(/^\s*>\s?/, ''))
      blocks.push(<blockquote key={`quote-${i}`}>{inline(quote.join(' '), `quote-${i}`)}</blockquote>)
      continue
    }

    const paragraph = [line.trim()]
    i++
    while (i < lines.length && !isBlockStart(lines[i])) paragraph.push(lines[i++].trim())
    blocks.push(<p key={`paragraph-${i}`}>{inline(paragraph.join(' '), `paragraph-${i}`)}</p>)
  }

  return <Fragment>{blocks}</Fragment>
}
