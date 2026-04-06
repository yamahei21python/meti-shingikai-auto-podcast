# Energy Audio - Design System (Linear-Inspired)

## 🎨 Visual Language
Linear の「静寂・高精度・信頼」という空気感を継承した UI です。深みのあるダークテーマを基調とし、鮮明なタイポグラフィと 1px の微細な発光を特徴とします。

## 🌗 Color Palette
- **Deep Slate (Marketing Black)**: `#08090a` (Page Background)
- **Soft Dark (Panel Dark)**: `#0f1011` (Component Background)
- **Brand Indigo**: `#5e6ad2` (Primary CTA / Accents)
- **Primary Text**: `#f7f8f8` (Heading)
- **Secondary Text**: `#8a8f98` (Body / Subtitle)
- **Border Subtle**: `rgba(255,255,255,0.05)` (Default Border)
- **Border Standard**: `rgba(255,255,255,0.08)` (Active / Hover Border)

## 🖋 Typography
- **Primary Font**: `Inter Variable`
- **Settings**: `font-feature-settings: "cv01", "ss03"` (Linear 固有のシャープな字体)
- **Display Weights**: Default `400`, Emphasis `510`, Announcement `590`
- **Letter Spacing**: 
    - 48px以上: `-1.5px`
    - 32px以上: `-1.0px`
    - 16px以上: `-0.4px`
    - それ以下: `-0.165px`

## 💎 Elevation & Shadows
- **Shadows**: 影（Dark shadow）は使用禁止。
- **Treatments**:
    - `Level 0`: `#08090a` 基調。
    - `Level 1 (Surface)`: `rgba(255,255,255,0.02)` の背景 + 境界線。
    - `Level 2 (Elevated)`: `rgba(255,255,255,0.05)` の背景 + 境界線。
    - `Inset`: `inset rgba(0,0,0,0.2) 0px 0px 12px 0px` (沈み込み表現用)

## 📏 Corner Radius
- **Micro**: `2px` (Badges)
- **Standard**: `6px` (Buttons, Inputs)
- **Comfortable**: `8px` (Cards, Dropdowns)
- **Panel**: `12px` (Feature Layers)

## ⚡️ Motion & Interactivity
- **Hover**: 境界線の透過度を上げ、背景の輝度を一段階上げる (Luminance stepping)
- **Transitions**: `all 0.4s cubic-bezier(0.4, 0, 0.2, 1)`

## 🖋 Writing Style & Brand Voice
- **Engineered Accuracy (設計された正確性)**: 感情的な装飾を排し、事実と性能を中心とした言葉を選ぶ。
- **Authoritative Calm (静かな権威)**: 「〜できます」という説明ではなく、「〜する (Syncs, Analyzes, Deploys)」という断定的・能動的な表現を用いる。
- **Clarity over Hype (煽りより明瞭さ)**: 言葉を詰め込まず、見出しは極限まで短く、余白の中で「声」が響くように配置する。
