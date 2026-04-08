# Energy Audio - Design System (Energy Intelligence)

Energy Audio のデザインシステムは、高精度なデータ解析とエネルギー業界の未来を象徴する「Energy Intelligence」をテーマとしています。深海のような深いダークテーマを基調とし、エネルギーの輝き（Sky Blue & Emerald）を感じさせる視覚体験を提供します。

## 1. Visual Theme
- **Concept**: 高情報密度、静寂、エネルギーの躍動感。
- **Aesthetic**: 「Oceanic Dark (深い紺・黒)」 × 「Energy Glow (ネオン発光)」。
- **Key Elements**: グラスモルフィズム、広大な余白（Spaciousness）、マイクロアニメーション、大型の背景ブラー。

## 2. Color Palette
- **Backgrounds**:
    - `Deep (Primary)`: `#020617` (Deep Indigo-Black)
    - `Surface`: `#0f172a` (Card Backgrounds)
    - `Elevated`: `#1e293b` (Hover states)
- **Accents (Energy Flows)**:
    - `Primary (Sky)`: `#38bdf8` - メインアクセント、プライマリボタングロウ
    - `Secondary (Emerald)`: `#10b981` - 成功、完了、サブアクセント
    - `Accent (Sunset Peach)`: `#FFB38A` - 差し色、エピソード一覧等のサブボタン用
    - `Accent (Sunset Orange)`: `#F26522` - RSS、外部連携等の強調用
    - `Gradient (Energy)`: `linear-gradient(135deg, #38bdf8, #10b981)` (Sky to Emerald)
    - `Gradient (Sunset)`: `linear-gradient(135deg, #FFB38A, #F26522)` (Peach to Orange)
- **Text Hierarchy**:
    - `Main`: `#f8fafc` (純白に近いグレー)
    - `Muted`: `#94a3b8` (サブテキス、説明文)
    - `Dim`: `#64748b` (メタデータ、注釈)
- **Borders**:
    - `Default`: `rgba(255, 255, 255, 0.08)`
    - `Bright`: `rgba(255, 255, 255, 0.15)` (強調・ホバー用)

## 3. Typography
- **Display & Headings**: `Outfit`, sans-serif
    - 特徴: 幾何学的で洗練された印象。
    - 使用場所: タイトル、ロゴ、数字、キャッチコピー。
- **UI & Body**: `Inter`, sans-serif
    - 特徴: 高い可読性とエンジニアリング的な精密さ。
    - 使用場所: 説明文、リンク、UIラベル。
- **Hero Copy**: `clamp(2.5rem, 8vw, 4.5rem)`, line-height: `1.1`.
- **Text Rendering**: `-webkit-font-smoothing: antialiased`. 

## 4. Component Styles
- **Cards (Glassmorphism)**:
    - `Background`: `rgba(15, 23, 42, 0.6)` + `blur(12px)`.
    - `Border-radius`: `1.5rem` (24px).
    - `Interactivity`: ホバー時に `translateY(-5px)` かつ背景の輝度を向上。
- **Icon Boxes (Three-Step Progression)**:
    - `Base Style`: すべての `icon-box` で `bg-white-soft` (白5%透過) と `border-white-soft` (白10%透過) を適用し、枠のデザインを統一する。
    - `Color Stepping`: 3つの要素が並ぶ場合、アイコンの「線のみ」に以下のステップを適用する。
        1. 1つ目: `text-white` (純白)
        2. 2つ目: `text-sunset-peach` (ピーチ)
        3. 3つ目: `text-sunset-orange` (オレンジ)
- **Icons**:
    - `Provider`: Lucide
    - `Treatment`: アクセントカラーの背景ボックス（1.25rem radius）に配置。

## 5. Layout Principles
- **Grid**: `1280px` センター配置。
- **Spacing**: セクション間は `4rem` (64px) 以上の大きな余白。
- **Background elements**: 画面の隅に大きなぼかし円（`blur-120px`）を配置し、奥行きを出す。
- **Text Alignment**: 原則「中央揃え」または「整然とした左揃え」。

## 6. Elevation & Glow
- **Shadows**: 物理的な黒い影は避け、**「光（Glow）」**で浮き上がりを表現。
- **Glow states**: 
    - `primary-glow`: `rgba(56, 189, 248, 0.4)`
    - `secondary-glow`: `rgba(16, 185, 129, 0.3)`
- **Border Elevation**: ホバー時にボーダーの色を明るくすることで深さを演出。

## 7. Do's & Don'ts
- **✅ Do**:
    - 見出しには `Outfit` を使用する。
    - 文字のグラデーション（Sky -> Emerald）をベースとし、Sunset Orange を効果的な差し色として使用する。
    - 3連のカード等では、アイコンボックスの枠を統一し、アイコンの線のみを白→ピーチ→オレンジへ変化させる。
    - 十分な余白（Whitespace）を確保し、情報を詰め込みすぎない。
- **❌ Don't**:
    - 純粋な黒（#000000）を背景に使用しない。
    - 物理的なドロップシャドウを多用しない（グロウを使用する）。
    - 派手すぎる原色（純粋な赤、青、緑）を使用しない。

## 8. Responsive Design
- **Breakpoints**: 
    - `MD` (768px): ヒーローコピーの縮小、グリッドの1カラム化。
    - `LG` (1024px): 複雑なレイアウトの開始。
- **Padding**: モバイルでは `1.5rem`、デスクトップでは `2rem` 以上のマージン。

## 9. Agent Prompt Guide
今後の実装・修正では、以下のスタイルガイドを遵守すること：
> "Energy Audio のデザインシステムに基づき、Slate-950 背景、Outfit/Inter のタイポグラフィ、Sky/Emerald のグラデーション、および明瞭な1pxボーダーとグラスモルフィズムを用いた、プレミアムで情報の透明性が高い UI を生成してください。物理的な影ではなく、グロウと輝度の調整で奥行きを表現してください。"
