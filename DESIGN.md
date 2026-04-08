# Energy Audio - Design System (Energy Intelligence)

Energy Audio のデザインシステムは、高精度なデータ解析とエネルギー業界の未来を象徴する「Energy Intelligence」をテーマとしています。深い紺・黒のダークテーマを基調とし、サンセットカラー（Peach/Orange）のアクセントを用いた、機能的かつプレミアムな視覚体験を提供します。

## 1. Visual Theme
- **Concept**: 高情報密度（High-Density）、タイムライン、エネルギーの躍動感。
- **Aesthetic**: 「Oceanic Dark (深い紺・黒)」 × 「Sunset Glow (サンセット発光)」。
- **Key Elements**: タイムライン、アコーディオン、グラスモルフィズム、高密度テキスト、詳細カード。

## 2. Color Palette
- **Backgrounds**:
    - `Deep (Primary)`: `#020617` (Deep Indigo-Black)
    - `Surface`: `rgba(15, 23, 42, 0.6)` (Card backgrounds with blur)
- **Accents (Sunset Energy)**:
    - `Accent (Sunset Peach)`: `#FFB38A` - タイムライン光、詳細確認ボタン、ガイドカード
    - `Accent (Sunset Orange)`: `#F26522` - RSS強調、アジェンダカード
    - `Timeline Line`: `rgba(242, 101, 34, 0.5)` (Orange with transparency)
- **Text Hierarchy**:
    - `Main`: `#f8fafc` (純白に近いグレー)
    - `Muted`: `#94a3b8` (サブテキスト)
    - `Dim`: `#64748b` (メタデータ、注釈)

## 3. Typography & Density
- **Headings**: `Outfit`, sans-serif (Bold, 3xl-5xl)
- **UI & Details**: `Inter`, sans-serif
- **Extreme High-Density (Detail Cards)**:
    - `Guide Font`: `14px` (text-sm相当) / `leading-tight`.
    - `Details Font`: `13px` / `leading-tight`.
    - `Indentation`: リストインデントを最小限 (`ml-1`) にし、横幅を最大限活用する。
    - `Spacing`: `mb-0` (リスト内), `p-2` (カード全体パディング) まで圧縮し、情報の可読性と密度を両立。

## 4. Interaction Model: Timeline-Accordion
- **Core Structure**: 左側に垂直なタイムライン（光るドット + オレンジライン）を配置し、全てのカードを紐付ける。
- **Main Card**: タイトル、日付、再生プレイヤーのみを含むコンパクトなカード。
- **Accordion Expansion**: 
    - 「詳細確認」ボタンでスライド展開。
    - 最新の1件はデフォルトで `is-open` 状態。
- **Two-Tone Detail Deck**:
    - `Left (Guide)`: Sunset Peach の左ボーダー。
    - `Right (Details)`: Sunset Orange の左ボーダー。
    - 両者とも `h-[600px]` の固定高を持ち、独立してスクロール可能。

## 5. Layout Principles
- **Grid / Max-Width**: 
    - `Explorer (index.html)`: `max-w-6xl` (1152px) - 大画面での閲覧効率を優先。
    - `LP (lp.html)`: セクション全体の `container` 幅に準拠。
- **Pagination**: 10件ずつのバッチ読み込み（Infinite Scroll）を採用し、初期表示速度を担保。

## 6. Elevation & Masking
- **Scroll Masks**: スクロールコンテナの上下に `5px` の極薄フェードをかけ、カードの境界を感じさせつつ、隠れている情報を暗示。
- **Glow**: タイムラインのドットには強めの `box-shadow` グロウを適用。

## 7. Do's & Don'ts
- **✅ Do**:
    - エピソードは垂直タイムラインに沿って配置する。
    - 詳細カードの情報密度は極力高く保つ（余白を恐れず、情報を詰める）。
    - 最新1件は即座に読めるよう開いた状態にする。
- **❌ Don't**:
    - メインカードに不必要な余白を作らない。
    - スクロールを阻害する大きなグラデーションマスクを使用しない。
    - デザインのために情報の可読性（文字サイズ）を犠牲にしない。

## 8. Responsive Design
- **MD (768px)**: アコーディオン内の「Guide」と「Details」が縦に並ぶ。
- **SM (640px)**: パディングの最小化 (`p-4` -> `p-2` 等)。

## 9. Agent Prompt Guide
> "Energy Audio のデザインシステムに基づき、垂直タイムラインとアコーディオンを用いた『Timeline-Accordion UI』を生成してください。詳細カードは高密度・高可読性を追求し、h-[600px] の固定高、p-2 の極小パディング、および 13-14px のフォントサイズを適用してください。Sunset Peach (#FFB38A) と Sunset Orange (#F26522) をアクセントラインとして使い、機能的でプレミアムな閲覧体験を提供してください。"
