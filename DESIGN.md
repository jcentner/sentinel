# Sentinel — Night Watch Design System

Dark-first monitoring dashboard. Warm amber accent on near-black canvas. Information-dense, low-distraction, evidence-grade.

> **Source of truth**: `src/sentinel/web/static/style.css` defines all tokens.
> This file is the human- and agent-readable reference. If they diverge, CSS wins.

---

## 1. Visual Theme & Atmosphere

| Attribute | Value |
|-----------|-------|
| Mood | Night watch / observatory — quiet authority, high signal-to-noise |
| Density | Information-dense. Tables, stats, badges, mono metadata. No decorative elements |
| Philosophy | Local-first, no external CDN dependencies. System fonts, no downloads |
| Default mode | Dark (near-black `#0a0a0f`). Light mode via `data-theme="light"` toggle |
| Accent | Warm amber — the single brand color. Every interactive element traces back to amber |
| Personality | Professional, utilitarian, precise. A tool for engineers, not a marketing site |

---

## 2. Color Palette & Roles

### Brand & Surface

| Name | Dark | Light | Role |
|------|------|-------|------|
| `--bg` | `#0a0a0f` | `#f8f7f4` | Page background |
| `--bg-raised` | `#111118` | `#f0efec` | Header, elevated panels |
| `--bg-overlay` | `#1a1a24` | `#e6e5e0` | Overlays, dropdowns |
| `--surface` | `#15151d` | `#ffffff` | Cards, inputs background |
| `--surface-hover` | `#1d1d28` | `#f5f4f1` | Hover state for rows and surfaces |

### Border

| Name | Dark | Light | Role |
|------|------|-------|------|
| `--border` | `#25252f` | `#dddbd6` | Default borders |
| `--border-vivid` | `#35354a` | `#c8c5be` | Hover/active borders |

### Text

| Name | Dark | Light | Role |
|------|------|-------|------|
| `--text` | `#e4e4ec` | `#1a1916` | Primary text, headings |
| `--text-dim` | `#9090a0` | `#5c5a52` | Secondary text, labels |
| `--text-faint` | `#58586a` | `#9c9a92` | Tertiary text, placeholders, table headers |

### Amber (Brand Accent)

| Name | Dark | Light | Role |
|------|------|-------|------|
| `--amber` | `#e5a000` | `#b45309` | Links, active nav, accent buttons, focus rings |
| `--amber-vivid` | `#f5b731` | `#92400e` | Hover state for amber elements |
| `--amber-glow` | `rgba(229,160,0,0.18)` | `rgba(180,83,9,0.1)` | Focus ring shadow |
| `--amber-subtle` | `rgba(229,160,0,0.07)` | `rgba(180,83,9,0.05)` | Active nav background, scope badges |

### Severity

| Name | Dark | Light | Role |
|------|------|-------|------|
| `--sev-critical` | `#f87171` | `#dc2626` | Critical findings — red |
| `--sev-critical-bg` | `rgba(248,113,113,0.12)` | `rgba(220,38,38,0.08)` | Critical badge/stat bg |
| `--sev-high` | `#fb923c` | `#ea580c` | High findings — orange |
| `--sev-high-bg` | `rgba(251,146,60,0.12)` | `rgba(234,88,12,0.08)` | High badge bg |
| `--sev-medium` | `#facc15` | `#ca8a04` | Medium findings — yellow |
| `--sev-medium-bg` | `rgba(250,204,21,0.10)` | `rgba(202,138,4,0.08)` | Medium badge bg |
| `--sev-low` | `#4ade80` | `#16a34a` | Low findings — green |
| `--sev-low-bg` | `rgba(74,222,128,0.10)` | `rgba(22,163,74,0.08)` | Low badge bg |

### Status

| Name | Dark | Light | Role |
|------|------|-------|------|
| `--st-new` | `#60a5fa` | `#2563eb` | New/confirmed findings, primary action buttons — blue |
| `--st-new-bg` | `rgba(96,165,250,0.12)` | `rgba(37,99,235,0.08)` | New badge bg |
| `--st-approved` | `#34d399` | `#059669` | Approved/pass — green |
| `--st-approved-bg` | `rgba(52,211,153,0.12)` | `rgba(5,150,105,0.08)` | Approved badge bg |
| `--st-suppressed` | `#9ca3af` | `#6b7280` | Suppressed — gray |
| `--st-suppressed-bg` | `rgba(156,163,175,0.10)` | `rgba(107,114,128,0.08)` | Suppressed badge bg |
| `--st-resolved` | `#a78bfa` | `#7c3aed` | Resolved — purple |
| `--st-resolved-bg` | `rgba(167,139,250,0.12)` | `rgba(124,58,237,0.08)` | Resolved badge bg |

### Quality Ratings (Compat Badges)

| Rating | Dark bg | Dark text | Light bg | Light text |
|--------|---------|-----------|----------|------------|
| Excellent | `#166534` | `#bbf7d0` | `#dcfce7` | `#166534` |
| Good | `#1e40af` | `#bfdbfe` | `#dbeafe` | `#1e40af` |
| Fair | `#854d0e` | `#fef08a` | `#fef9c3` | `#854d0e` |
| Poor | `#991b1b` | `#fecaca` | `#fee2e2` | `#991b1b` |

---

## 3. Typography

### Font Families

| Usage | Stack | Rationale |
|-------|-------|-----------|
| Body | `system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif` | Local-first, no downloads |
| Code / Mono | `'JetBrains Mono', 'Cascadia Code', monospace` | Developer-native monospace |

### Scale

| Element | Size | Weight | Extras |
|---------|------|--------|--------|
| Page heading (`h1`) | `1.5rem` | 700 | `letter-spacing: -0.02em` |
| Empty state heading | `1.15rem` | 600 | — |
| Logo text | `1.05rem` | 700 | `letter-spacing: -0.01em` |
| Card title | `0.92rem` | 600 | — |
| Body / finding title | `0.9rem` | 500 | — |
| Nav link / inputs | `0.88rem` | 500 | — |
| Subtitle / secondary text | `0.88rem` | 400 | — |
| Toast | `0.85rem` | 400 | — |
| Back link | `0.85rem` | 400 | — |
| Button | `0.82rem` | 500 | — |
| Form label | `0.82rem` | 600 | uppercase, `letter-spacing: 0.03em` |
| Finding meta / mono data | `0.78rem` | 400 | mono |
| Severity group heading | `0.78rem` | 600 | uppercase, `letter-spacing: 0.06em` |
| Button small | `0.78rem` | 500 | — |
| Form hint | `0.75rem` | 400 | faint color |
| Table header | `0.72rem` | 600 | uppercase, `letter-spacing: 0.05em` |
| Badge | `0.72rem` | 600 | uppercase, `letter-spacing: 0.04em` |
| Stat label | `0.72rem` | 600 | uppercase, `letter-spacing: 0.05em` |
| Stat value | `1.75rem` | 700 | `letter-spacing: -0.02em` |

### Conventions

- **Uppercase labels** for: table headers, form labels, badge text, stat labels, severity group headings, DL keys
- **Letter-spacing** widens for uppercase text (`0.03em` to `0.06em`), tightens for large headings (`-0.02em`)
- **Monospace** for: code, file paths, finding metadata, evidence blocks, repo indicator, chart labels
- **Line height**: body `1.6`, evidence blocks `1.65`, buttons `1.3`, badges `1.5`

---

## 4. Component Styles

### Buttons

| Variant | Background | Text | Border | Hover |
|---------|-----------|------|--------|-------|
| Default (`.btn`) | `var(--surface)` | `var(--text)` | `var(--border)` | surface-hover, border-vivid |
| Accent (`.btn-accent`) | `var(--amber)` | `#0a0a0f` | `var(--amber)` | amber-vivid |
| Primary (`.btn-primary`) | `var(--st-new)` | `#fff` | `var(--st-new)` | opacity 0.9 |
| Success (`.btn-success`) | `var(--st-approved)` | `#fff` | `var(--st-approved)` | opacity 0.9 |
| Danger (`.btn-danger`) | transparent | `var(--sev-critical)` | `var(--sev-critical)` | critical-bg fill |
| Ghost (`.btn-ghost`) | transparent | `var(--text-dim)` | transparent | surface-hover |
| Icon (`.btn-icon`) | transparent | `var(--text-dim)` | transparent | surface-hover, 36×36px |

Base: `padding: 0.45rem 0.9rem`, `border-radius: var(--radius-sm)`, `font-size: 0.82rem`, weight 500.
Small: `padding: 0.3rem 0.6rem`, `font-size: 0.78rem`.
Transition: `all 0.15s`.

### Cards

- Background: `var(--surface)` with `1px solid var(--border)`
- Radius: `var(--radius)` (8px)
- Padding: `1.25rem`
- Shadow: `var(--shadow)`
- Stacking: `card + card` gets `margin-top: 1rem`

### Badges

- Pill shape: `border-radius: 999px`
- Padding: `0.15rem 0.55rem`
- Font: `0.72rem`, weight 600, uppercase, `letter-spacing: 0.04em`
- Each severity/status gets its own `color` + `background` pair from token variables
- Color-on-transparent-color pattern: text color is the vivid hue, background is the same hue at 8–12% opacity

### Tables

- Full width, collapsed borders
- Header: small uppercase faint text, bottom border
- Cells: `0.6rem 0.75rem` padding
- Row hover: `var(--surface-hover)`
- Last row: no bottom border

### Forms

- Inputs: full width, `var(--bg)` background, `var(--border)` border, `var(--radius-sm)` radius
- Focus: `border-color: var(--amber)`, `box-shadow: 0 0 0 2px var(--amber-glow)`
- Labels: small uppercase, dim color, 600 weight
- Hints: tiny faint text below input
- Checkboxes: `accent-color: var(--amber)`, 16×16px
- Two-column grid (`.form-row`): `1fr 1fr` with `1rem` gap

### Toasts

- Fixed position: `top: 68px`, `right: 1.5rem`, z-index 200
- Card-like: surface bg, border, radius, shadow-lg
- Left accent border (3px): success → green, error → red, info → blue
- Slide-in animation: `translateX(20px → 0)`, 0.3s ease
- Auto-dismiss: 4 seconds via JavaScript

### Stat Cards

- Grid: `repeat(auto-fit, minmax(180px, 1fr))`
- Label: tiny uppercase faint text
- Value: `1.75rem` bold, colored by severity/status when applicable

### Finding Rows

- Flex row: checkbox → badge → title → meta → location
- Hover: `var(--surface-hover)`
- Collapsible clusters: `<details>` with amber border when open

### Evidence Blocks

- Background: `var(--bg)` (deepest surface)
- Mono font, `0.8rem`, `line-height: 1.65`, `white-space: pre-wrap`
- Subtle border, small radius

### Empty State

- Centered, generous padding (`4rem 2rem`)
- Heading + dim description + inline code snippet

---

## 5. Layout

| Property | Value |
|----------|-------|
| Max content width | `1200px` |
| Container padding | `0 1.5rem` |
| Header height | `56px` |
| Header position | `sticky`, `z-index: 100`, `backdrop-filter: blur(12px)` |
| Main padding | `2rem 0` |
| Main min-height | `calc(100vh - 56px)` |

### Navigation

- Horizontal nav links in header, pill-shaped hover/active states
- Active link: amber text on amber-subtle background
- Right side: repo indicator chip → "New Scan" accent button → theme toggle
- Logo: shield SVG (26×26) + "Sentinel" text

### Grid Patterns

| Pattern | Columns | Gap |
|---------|---------|-----|
| Stat grid | `auto-fit, minmax(180px, 1fr)` | `1rem` |
| Form row | `1fr 1fr` | `1rem` |
| DL metadata | `auto 1fr` | `0.4rem 1.25rem` |

---

## 6. Depth & Elevation

| Level | Shadow | Usage |
|-------|--------|-------|
| 0 — Flat | none | Default surfaces, table rows |
| 1 — Surface | `var(--shadow)`: `0 2px 8px rgba(0,0,0,0.4)` | Cards |
| 2 — Elevated | `var(--shadow-lg)`: `0 8px 24px rgba(0,0,0,0.5)` | Toasts, modals |
| Blur | `backdrop-filter: blur(12px)` | Sticky header |

### Border Radius Scale

| Token | Value | Usage |
|-------|-------|-------|
| `--radius-sm` | `5px` | Buttons, inputs, finding rows, badges (non-pill) |
| `--radius` | `8px` | Cards, toasts, bulk bar |
| `--radius-lg` | `12px` | Large containers |
| `999px` | pill | Status/severity badges |

---

## 7. Do's and Don'ts

### Do

- Use CSS custom properties (`var(--token)`) for all colors — never hardcode hex in templates
- Keep the amber accent as the only brand color — all interactive elements use amber
- Use severity colors semantically: red=critical, orange=high, yellow=medium, green=low
- Use status colors semantically: blue=new/active, green=approved/pass, gray=suppressed, purple=resolved
- Use uppercase + letter-spacing for all label-type text (table headers, form labels, badges, stat labels)
- Use monospace for all data/code/path/metadata content
- Keep information density high — engineers scan, they don't browse
- Use system fonts only (local-first, no CDN dependencies)
- Apply hover transitions at `0.15s` for interactive elements
- Show focus rings with amber glow on form inputs

### Don't

- Don't introduce new accent colors — amber is the only brand color
- Don't use decorative elements, illustrations, or rounded-friendly aesthetics
- Don't add external font dependencies or CDN imports
- Don't use opacity for text hierarchy — use the three text tokens (`--text`, `--text-dim`, `--text-faint`)
- Don't create cards without borders — every surface needs a `1px solid var(--border)` edge
- Don't use large padding or whitespace — this is a dense dashboard, not a marketing page
- Don't add animations beyond subtle transitions (0.15s) and toast slide-in (0.3s)
- Don't use inline styles with hardcoded colors — add CSS classes or use existing tokens

---

## 8. Responsive Behavior

**Single breakpoint**: `768px`

| Element | Desktop | Mobile (≤768px) |
|---------|---------|-----------------|
| Header gap | `2rem` | `1rem` |
| Container padding | `0 1.5rem` | `0 1rem` |
| Nav links gap | `0.25rem` | `0` |
| Repo indicator | Visible | Hidden |
| Form row | `1fr 1fr` | `1fr` |
| Stat grid | `auto-fit, minmax(180px, 1fr)` | `repeat(2, 1fr)` |
| Finding location | Visible | Hidden |

Touch targets: buttons minimum `36px` height (`.btn-icon`), checkboxes `16×16px`.

---

## 9. Agent Prompt Guide

### Quick Color Reference

```
Background:  #0a0a0f (dark) / #f8f7f4 (light)
Surface:     #15151d (dark) / #ffffff (light)
Amber:       #e5a000 (dark) / #b45309 (light)
Text:        #e4e4ec (dark) / #1a1916 (light)
Text dim:    #9090a0 (dark) / #5c5a52 (light)
Critical:    #f87171 (dark) / #dc2626 (light)
Success:     #34d399 (dark) / #059669 (light)
Blue/New:    #60a5fa (dark) / #2563eb (light)
```

### Ready-to-Use Prompts

**New page**: "Create a Sentinel web page using the Night Watch design system. Dark background `#0a0a0f`, card surfaces `#15151d`, amber `#e5a000` accent. Use system-ui fonts, 8px card radius, 5px button radius. Dense layout, max-width 1200px. Use CSS custom properties from `style.css` — never hardcode colors."

**New component**: "Add a component to the Sentinel web UI following the Night Watch design system. Use `var(--surface)` for backgrounds, `var(--border)` for edges, `var(--amber)` for interactive elements. Font sizes between 0.72rem (labels) and 0.92rem (titles). Uppercase letter-spaced labels for headers."

**Status indicator**: "Use Sentinel severity badges: critical (red `--sev-critical`), high (orange `--sev-high`), medium (yellow `--sev-medium`), low (green `--sev-low`). Pill shape, 999px radius, 0.72rem uppercase text on 8-12% opacity background."

### Technology Stack

| Layer | Technology |
|-------|-----------|
| Server | Starlette (Python ASGI) |
| Templates | Jinja2 (server-rendered HTML) |
| Interactivity | htmx (progressive enhancement, no JS build step) |
| Styling | Single CSS file, CSS custom properties, no preprocessor |
| Fonts | System fonts only — no external loading |
| Icons | Inline SVG |
