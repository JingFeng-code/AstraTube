// 品牌標記：新月和星星，呼應名稱裡的 Astra。顏色跟著主題變，不依賴圖檔或字型。
export default function BrandMark({ small = false }) {
  return (
    <span className={`brand-mark${small ? ' brand-mark-small' : ''}`} aria-hidden="true">
      <svg viewBox="0 0 100 100">
        <rect width="100" height="100" fill="var(--accent)" />
        <circle cx="46" cy="52" r="30" fill="var(--on-accent)" />
        <circle cx="58" cy="44" r="26" fill="var(--accent)" />
        <path d="M66.0 27.0L69.4 35.3L78.4 36.0L71.6 41.8L73.6 50.5L66.0 45.9L58.4 50.5L60.4 41.8L53.6 36.0L62.6 35.3Z" fill="var(--brand-star)" stroke="var(--brand-star)" strokeWidth="1.8" strokeLinejoin="round" />
        <path d="M84 64Q84 70 90 70Q84 70 84 76Q84 70 78 70Q84 70 84 64Z" fill="var(--on-accent)" />
      </svg>
    </span>
  )
}
