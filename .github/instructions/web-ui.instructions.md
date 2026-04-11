---
name: 'Web UI Design System'
description: 'Enforces the Night Watch design system for web UI consistency'
applyTo: 'src/sentinel/web/**'
---

# Web UI Design Conventions

Before creating or modifying any web UI component, read [DESIGN.md](../../DESIGN.md) for the full design token reference.

## Rules

- Use CSS custom properties (`var(--token)`) for all colors — never hardcode hex values in templates or inline styles
- Amber (`var(--amber)`) is the only brand accent — do not introduce new accent colors
- Use the three text tokens for hierarchy: `var(--text)`, `var(--text-dim)`, `var(--text-faint)`
- Use severity tokens semantically: `--sev-critical` (red), `--sev-high` (orange), `--sev-medium` (yellow), `--sev-low` (green)
- Use status tokens semantically: `--st-new` (blue), `--st-approved` (green), `--st-suppressed` (gray), `--st-resolved` (purple)
- All label-type text must be uppercase with letter-spacing (`0.03em` to `0.06em`)
- All code/path/metadata content must use monospace font
- No external font imports — system fonts only
- No decorative elements or illustrations
- Both dark and light themes must be supported via `data-theme` attribute
- Add new design tokens to `style.css` `:root` and `[data-theme="light"]` blocks — update DESIGN.md in the same commit
