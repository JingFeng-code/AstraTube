# 單檔 HTML 設計守則（教學頁／引導頁／題庫頁）

情境：單一 `.html`、CSS 全部內嵌於 `<style>`、零外部資源、離線可開、淺色與深色都要能看。
下列每條都是硬規則，不是建議。衝突時以「§9 禁止清單」優先。

## 1. 技術硬限制
- 禁止任何外部請求：`<link href="http...">`、`@import url()`、CDN 的 JS/CSS/字型/圖片。全部內嵌。
- 禁止 Google Fonts、Tailwind CDN、任何套件。只寫原生 CSS 與原生 JS。
- 禁止 `<img src="http...">`、`picsum.photos`、`unsplash`。需要圖示時用內嵌 `<svg>`，單色、`stroke-width:1.5`、全頁統一。
- 顏色、間距、圓角一律走 `:root` 的 CSS 變數，禁止在 section 裡直接寫 hex 或 magic number。

## 2. 字體與文字
- 字體堆疊固定兩組，不另外選字：
  `--font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang TC", "Noto Sans TC", "Microsoft JhengHei", sans-serif;`
  `--font-mono: ui-monospace, SFMono-Regular, Menlo, Consolas, "Noto Sans Mono CJK TC", monospace;`
- 禁止把中文正文設成襯線體。襯線只允許用在單一大標題，且全頁最多出現一處。
- 字級階梯只用這 8 級（比例 1.25），不得插入中間值：
  `12 / 14 / 16 / 20 / 25 / 31 / 39 / 49 px`。
- 正文 `16px`（桌機可 17px），行高 `1.75`（中文必須 ≥1.7，禁止 1.5 以下）。
- 標題 `31-49px`，行高 `1.2`；小標 `20-25px`，行高 `1.35`。
- 字距：中文一律 `letter-spacing: 0`；拉丁大標 `-0.02em`；全大寫小標 `0.08em`。
- 正文段落容器 `max-width: 720px`（中文一行 33-38 字）。禁止整行文字橫跨 1120px。
- 字重只用 `400 / 500 / 700` 三級。禁止 `font-weight:600` 與 `700` 同頁混用當兩種強調。
- 強調用同一字體的 `font-weight:700` 或 `font-style:italic`，禁止換另一種字體做強調。

## 3. 顏色與深色模式
- 單一策略：CSS 變數 + `@media (prefers-color-scheme: dark)`，另加 `:root[data-theme="dark"]` / `[data-theme="light"]` 覆寫。禁止用 `dark:` 式的雙寫 class。
- 中性底色 + **最多 1 個** accent。accent 飽和度 < 80%，全頁只用這一個 accent，禁止第二個彩色（狀態色 success/danger 例外，且各只准 1 個）。
- 禁止純 `#000000` 與純 `#ffffff` 當頁面背景或正文色。
- 預設 token（可換色相，結構不可改）：
  淺色 `--bg:#fafaf9; --surface:#ffffff; --text:#18181b; --muted:#52525b; --border:rgba(0,0,0,.10);`
  深色 `--bg:#0f0f11; --surface:#18181b; --text:#ededf0; --muted:#a1a1aa; --border:rgba(255,255,255,.11);`
- 對比：正文與 `--muted` 皆須 ≥ 4.5:1；大字（≥20px）≥ 3:1。深色模式的 accent 要提亮，不可沿用淺色值。
- 禁止 AI 紫／藍紫漸層（`#6366f1`→`#a855f7` 這類）、禁止 neon glow、禁止漸層填滿的大標題文字。
- 禁止 section 之間翻轉主題（深色頁中夾一段米白段落）。同一主題內的層次用 `--bg` / `--surface` 兩階即可。

## 4. 間距與版面
- 間距只用 4 的倍數階梯：`4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 / 96 / 128 px`。禁止 5px、13px、18px 這類非階梯值。
- 頁面容器 `max-width:1120px; margin-inline:auto; padding-inline:24px`（<768px 時 `16px`）。
- 區塊垂直間距：桌機 `padding-block: 64-96px`；手機 `40-56px`。同一頁只准兩種區塊間距值。
- 多欄一律用 CSS Grid（`grid-template-columns: repeat(N, minmax(0,1fr)); gap:24px`）。禁止 `width: calc(33% - 1rem)` 這種 flex 百分比算式。
- 每個多欄版面都要明寫 `@media (max-width:767px)` 的單欄退場，禁止靠瀏覽器自然換行。
- 斷點固定三個：`640 / 768 / 1024 px`。禁止自創第四個。
- 滿版高度用 `min-height:100dvh`，禁止 `height:100vh`。
- 禁止同一頁出現 3 個以上結構相同的區塊（例如連續三組「左圖右字」）。第三個必須換版式。
- 禁止「3 張等寬等高卡片」當特色區。改用 2 欄不等寬、清單加分隔線、或直接用留白分組。

## 5. 圓角、邊框、陰影
- 全頁只用一組圓角：`--r-sm:8px`（按鈕／輸入／tag）、`--r-md:12px`（卡片／程式碼區塊）、`--r-full:999px`（只給 badge）。
- 禁止卡片 `border-radius > 16px`，禁止同頁出現方角卡片與 pill 卡片並存。
- 邊框一律 `1px solid var(--border)`。禁止 ≥2px 的裝飾性邊框，禁止彩色外框當強調。
- 陰影只准這兩級，且僅用於浮層（下拉、彈窗、sticky nav）：
  `--sh-1: 0 1px 2px rgb(0 0 0/.05), 0 4px 12px rgb(0 0 0/.06);`
  `--sh-2: 0 8px 32px rgb(0 0 0/.12);`
- 禁止純黑不帶透明度的陰影。深色模式關掉陰影，改用 `--surface` 提亮 + `--border` 表達層次。
- 靜態卡片預設不加陰影。要分群就用 `border` 或 `border-top` 或留白，不要每個容器都給陰影。

## 6. 元件規格（教學／題庫頁常用）
- 按鈕：`padding:10px 18px; font-size:15px; font-weight:500; border-radius:var(--r-sm)`，可點區高度 ≥ 44px。
- 按鈕文字 1-3 個詞，必須單行不折行；折行即為不合格。同一頁相同意圖的按鈕只准一種文案。
- 按鈕文字與底色對比 ≥ 4.5:1。禁止白底白字、禁止無邊框的透明按鈕貼在同色背景上。
- `:active` 加 `transform: translateY(1px)` 或 `scale(.98)`，`:hover` 只改背景／邊框，不改尺寸造成版面位移。
- 焦點樣式必寫 `:focus-visible { outline:2px solid var(--accent); outline-offset:2px }`。禁止只寫 `outline:none`。
- 表單：label 在 input 上方，錯誤訊息在下方，間距 `gap:8px`。禁止用 placeholder 當 label。
- 程式碼區塊：`font-family:var(--font-mono); font-size:14px; line-height:1.6; padding:16px; border-radius:var(--r-md); overflow-x:auto`。禁止程式碼區塊撐破版面造成整頁橫向捲動。
- 表格：只在 `<thead>` 下加一條分隔線，列與列之間最多一條 `border-bottom`。禁止每列同時有 `border-top` 與 `border-bottom`。
- 超過 5 項的清單不要用預設 `<ul>` 條列到底：改成 2 欄分組、卡片格、或摺疊 `<details>`。
- 題庫選項：垂直堆疊、左對齊、每項 `padding:12px 16px`、間距 `8px`；正解／錯誤狀態用邊框色 + 文字標示，不要只靠顏色（要同時有文字或圖示）。
- 引用／提示框：左側 `border-left:3px solid var(--accent)`，`padding:12px 16px`，背景用 `--surface`。同一頁提示框樣式只准一種。

## 7. 動效
- 只動 `transform` 與 `opacity`。禁止動 `width` / `height` / `top` / `left` / `margin`。
- 時長：顏色與邊框 `150ms`；位移與展開 `220ms`；進場 `400ms` 為上限。禁止 > 600ms 的動畫。
- 緩動固定兩條：互動回饋 `cubic-bezier(0.2, 0, 0, 1)`；進場 `cubic-bezier(0.16, 1, 0.3, 1)`。禁止 `linear` 用於 UI 位移。
- 禁止 `animation-iteration-count: infinite`（跑馬燈、呼吸光、閃爍點）。載入指示器例外，且全頁最多一個。
- 禁止 `window.addEventListener('scroll', ...)`。捲動觸發用 `IntersectionObserver` 或 CSS `animation-timeline: view()`。
- 進場動畫只掛在高度 < 800px 的小元件；整頁容器與長列表禁止掛 `animation`（會停在 `opacity:0`）。
- 必寫 `@media (prefers-reduced-motion: reduce) { *,*::before,*::after { animation-duration:.01ms !important; transition-duration:.01ms !important } }`。

## 8. 內容與文案
- 標題 ≤ 12 字；區塊說明文字 ≤ 40 字。超過就砍，不要縮字級。
- 首屏（第一個 100dvh）內必須看得到：標題、一句說明、主要操作按鈕。禁止首屏 `padding-top > 96px`。
- 禁止在每個區塊上方放全大寫小標籤（eyebrow）。全頁 eyebrow 數量 ≤ `ceil(區塊數 / 3)`。
- 禁止編號式標籤：`01 / INDEX`、`Step 1`、`Phase 02`、`第一階段`。直接寫該步驟在做什麼。
- 禁止捲動提示（`Scroll`、`↓ 向下捲動`、滑鼠滾輪圖示）。
- 禁止版本／時間／地點裝飾字串：`v1.4.2`、`Build 0048`、`最後同步 4 秒前`、`Taipei 14:23 · 18°C`。
- 禁止假資料人名與品牌名：`John Doe`、`王小明`、`Acme`、`Nexus`、`SmartFlow`。要舉例就用具體、貼合主題的真實感名稱。
- 禁止造假精準數字（`92%`、`4.1×`、`5.8mm`）除非資料真實或明確標註為範例。
- 禁止空洞動詞：`賦能`、`打造`、`全新升級`、`Elevate`、`Seamless`、`Unleash`。用具體動詞。
- 禁止 emoji 出現在標題、按鈕、導覽列（正文舉例時可少量使用）。

## 9. 禁止清單（出稿前逐條機械檢查）
1. 禁止破折號 `—` 與 `–` 出現在任何可見文字（標題、按鈕、正文、註解、alt）。一律改用 `-`、逗號、句號或括號。零容忍。
2. 禁止任何外部 URL 資源（grep `http` 應只剩註解或連結文字）。
3. 禁止純 `#000` / `#fff` 當頁面背景或正文色。
4. 禁止兩個以上 accent 色；grep 全部 hex，非中性色應只有一組。
5. 禁止三張等寬等高的特色卡片。
6. 禁止 `border-radius` 出現第四種數值。
7. 禁止非 4 倍數的 padding / margin / gap。
8. 禁止 `animation: ... infinite`（載入指示器除外）。
9. 禁止 `height:100vh`、`outline:none`（無替代焦點樣式）、`window.addEventListener('scroll')`。
10. 禁止用 `<div>` 堆假的產品截圖／假終端機／假儀表板。要示範就放真的可運作 HTML。
11. 禁止按鈕文字在桌機折成兩行。
12. 禁止只用顏色傳達狀態（對／錯／必填）；必須同時有文字或形狀。

## 10. 交付前自檢
- 在 `prefers-color-scheme` 淺色與深色兩種模式下各看過一次，兩邊層次與對比都成立。
- 在 375px 與 1440px 兩個寬度各看過一次，無橫向捲動、無元素重疊。
- 全文搜尋 `—`、`–`、`http`、`100vh`、`infinite`、`outline:none`，結果應全為 0（或有明確理由）。
- 上述任一項未過，即為未完成，先修再交。
