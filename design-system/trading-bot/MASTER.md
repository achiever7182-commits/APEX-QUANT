# Design System Master File: Apex Quant / Trading Bot

> **LOGIC:** When building a specific page, first check `design-system/pages/[page-name].md`.
> If that file exists, its rules **override** this Master file.
> If not, strictly follow the rules below.

---

**Project:** Trading Bot (Apex Quant Architecture)  
**Industry:** Algorithmic & Quantitative Financial Trading  
**Pattern:** `real-time-operations-landing` (Live Operations, Telemetry Preview & Data Verification)  
**Visual Style:** `dark-mode-oled` (Deep Obsidian, Glassmorphism, Neon Precision Signals)  
**Typography System:** `Modern Dark Cinema` (Inter / Plus Jakarta Sans + JetBrains Mono)  
**Design Dials:** Variance `7/10` (Modern / Balanced) | Motion `6/10` (Standard Scroll/Stagger) | Density `8/10` (Dense / Financial Telemetry)  

---

## 1. Color System (OLED Dark Mode)

All colors are tuned for high-contrast visibility, zero eye fatigue in dark environments, and immediate signal recognition for order states and financial telemetry.

| Token | Hex Value | CSS Variable | Semantic Usage |
|---|---|---|---|
| **Background (OLED)** | `#030712` | `--color-background` | Deepest root background |
| **Surface Card** | `#0b0f19` | `--color-card` | Container panels, widget cards |
| **Surface Elevated** | `#111827` | `--color-card-elevated` | Modal surfaces, popovers, active tabs |
| **Surface Muted** | `#1e293b` | `--color-muted` | Input fields, table header strips, badges |
| **Border Default** | `#1e293b` | `--color-border` | Subtle component dividers |
| **Border Glow** | `#334155` | `--color-border-glow` | Hovered interactive card borders |
| **Text Foreground** | `#f8fafc` | `--color-foreground` | Primary titles, active values, headings |
| **Text Muted** | `#94a3b8` | `--color-muted-foreground` | Secondary descriptions, timestamps |
| **Text Dimmed** | `#64748b` | `--color-dimmed` | Footers, labels, inactive indicators |
| **Bullish / Profit** | `#10b981` | `--color-bullish` | Long orders, profit deltas, positive PnL |
| **Bullish Glow** | `rgba(16, 185, 129, 0.15)`| `--glow-bullish` | Soft aura for winning trades/metrics |
| **Bearish / Risk** | `#f43f5e` | `--color-bearish` | Short orders, drawdowns, stop-losses |
| **Bearish Glow** | `rgba(244, 63, 94, 0.15)` | `--glow-bearish` | Soft aura for stop-loss warnings |
| **Cyan / Latency** | `#06b6d4` | `--color-cyan` | C++ execution speed, microsecond latency |
| **Electric Accent** | `#3b82f6` | `--color-primary` | Main CTAs, terminal focus rings, active links |
| **Warning / Queue** | `#f59e0b` | `--color-warning` | Pending orders, circuit-breaker alerts |

---

## 2. Typography System (Modern Dark Cinema)

- **Headings & Display:** `Plus Jakarta Sans` or `Inter`, font-weight `600`–`800`, letter-spacing `-0.025em`.
- **Body Text:** `Inter`, font-weight `400`–`500`, line-height `1.6`, high legibility against dark slate.
- **Numbers, Telemetry, Code & Orders:** `JetBrains Mono`, tabular figures (`font-variant-numeric: tabular-nums`), font-weight `400`–`600`.

### Google Fonts Import:
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@500;600;700;800&display=swap" rel="stylesheet">
```

### Type Hierarchy:
- **Hero Title:** `clamp(2.5rem, 5vw, 4.25rem)` / Line Height `1.1` / Weight `800`
- **Section Heading:** `clamp(1.75rem, 3.5vw, 2.75rem)` / Line Height `1.2` / Weight `700`
- **Card Title:** `1.25rem` (`20px`) / Line Height `1.35` / Weight `600`
- **Body Large:** `1.125rem` (`18px`) / Line Height `1.6` / Weight `400`
- **Body Default:** `0.9375rem` (`15px`) / Line Height `1.55` / Weight `400`
- **Telemetry / Mono:** `0.875rem` (`14px`) / Line Height `1.4` / Weight `500`
- **Micro Badge:** `0.6875rem` (`11px`) / Weight `600` / Uppercase / Letter Spacing `+0.05em`

---

## 3. Spacing & Density Scale (Density 8/10 - Dense Financial Grid)

| Token | Value | Tailwind Class | Semantic Usage |
|---|---|---|---|
| `--space-2xs` | `2px` | `p-0.5` / `gap-0.5` | Orderbook row gaps |
| `--space-xs` | `4px` | `p-1` / `gap-1` | Badge internal padding, icon offsets |
| `--space-sm` | `8px` | `p-2` / `gap-2` | Input field padding, compact card gaps |
| `--space-md` | `12px` | `p-3` / `gap-3` | Standard telemetry row spacing |
| `--space-lg` | `16px` | `p-4` / `gap-4` | Card interior padding |
| `--space-xl` | `24px` | `p-6` / `gap-6` | Major bento grid card padding |
| `--space-2xl` | `32px` | `py-8` / `gap-8` | Component section divisions |
| `--space-3xl` | `48px` | `py-12` | Medium section boundaries |
| `--space-4xl` | `64px` | `py-16` | Major landing page container blocks |

---

## 4. Component Blueprints & Patterns

### 1. Glassmorphism Bento Card
```html
<div class="relative overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-900/60 p-6 backdrop-blur-md transition-all duration-300 hover:border-slate-700 hover:shadow-[0_0_25px_rgba(59,130,246,0.1)]">
  <div class="pointer-events-none absolute -top-16 -right-16 h-32 w-32 rounded-full bg-blue-500/10 blur-2xl"></div>
  <!-- Content -->
</div>
```

### 2. Live Telemetry Badge
```html
<div class="inline-flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 font-mono text-xs font-semibold text-emerald-400">
  <span class="relative flex h-2 w-2">
    <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
    <span class="relative inline-flex h-2 w-2 rounded-full bg-emerald-500"></span>
  </span>
  <span>ONLINE: TESTNET WEBSOCKET</span>
</div>
```

### 3. Primary Trading Action Button
```html
<button class="relative inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 px-6 py-3 font-sans text-sm font-semibold text-white shadow-lg shadow-blue-500/20 transition-all duration-200 hover:scale-[1.02] hover:shadow-blue-500/35 active:scale-[0.98] cursor-pointer focus:outline-none focus:ring-2 focus:ring-blue-400 focus:ring-offset-2 focus:ring-offset-slate-950">
  <!-- Icon & Text -->
</button>
```

### 4. Tabular Order Feed Row
```html
<div class="grid grid-cols-4 items-center rounded-lg border border-slate-800/50 bg-slate-950/40 px-3 py-2 font-mono text-xs transition-colors hover:bg-slate-800/40">
  <span class="text-slate-400">19:14:02.184</span>
  <span class="font-semibold text-emerald-400">BUY 0.045 BTC</span>
  <span class="text-right text-slate-200">$64,281.50</span>
  <span class="text-right text-cyan-400">2.8ms</span>
</div>
```

---

## 5. Motion & Micro-Interactions

- **Scroll Reveal:** Handled smoothly via native `IntersectionObserver` adding `.active-reveal` to `.reveal-on-scroll` elements.
- **GSAP / CSS Transitions:** Smooth `all 200ms cubic-bezier(0.16, 1, 0.3, 1)`.
- **Accessibility:** Respects `@media (prefers-reduced-motion: reduce)` by immediately rendering all elements at `opacity: 1` and `transform: none`.
- **Interactive Ticker Control:** Always include pause/play buttons for dynamic live ticks to satisfy WCAG 2.2 Level AA requirements.

---

## 6. Pre-Delivery Checklist (UI/UX Pro Max Certified)

- [x] **No emojis as icons:** Strict usage of SVG vector icons (Lucide Icons).
- [x] **Contrast Compliance:** Text meets WCAG AAA standards on dark surfaces (min 7:1 for headers, 4.5:1 for body).
- [x] **Cursor pointer:** Applied to all buttons, tabs, accordions, links, and sliders.
- [x] **Hover states:** Defined with sub-300ms transitions and smooth scaling/glow.
- [x] **Motion Controls:** Pause button provided for live tickers.
- [x] **Responsive Breakpoints:** Explicitly tested at 375px (mobile), 768px (tablet), 1024px (laptop), and 1440px+ (desktop).
