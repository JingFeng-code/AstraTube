// 品牌標記：一張卡片疊上播放三角。純 CSS 形狀，不依賴任何圖檔或字型。
export default function BrandMark({ small = false }) {
  return (
    <span className={`brand-mark${small ? ' brand-mark-small' : ''}`} aria-hidden="true">
      <span className="brand-card" />
      <i className="brand-play" />
    </span>
  )
}
