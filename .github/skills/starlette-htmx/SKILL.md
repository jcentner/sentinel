---
name: starlette-htmx
description: "Starlette + htmx web UI patterns for Sentinel. Use when working with web routes, templates, static assets, or browser-based features. Covers Starlette routing, Jinja2 templates, htmx progressive enhancement, and CSRF middleware."
---

# Starlette + htmx Skill

## Official Documentation

- [Starlette docs](https://www.starlette.io/) — always consult for routing, middleware, request/response API
- [htmx docs](https://htmx.org/docs/) — follow these for progressive enhancement patterns
- [Jinja2 docs](https://jinja.palletsprojects.com/) — template syntax and filters

## Design System

Read [DESIGN.md](../../../DESIGN.md) before creating or modifying any web UI component. It defines:
- Color tokens (`var(--amber)`, `var(--surface)`, etc.) — never hardcode hex in templates
- Typography scale and conventions (uppercase labels, mono for data)
- Component patterns (cards, badges, buttons, forms, tables)
- Do's and don'ts (single amber accent, no decorative elements, no external fonts)

## Project Conventions

- Web app lives in `src/sentinel/web/` — `app.py` (factory + index), route modules in `web/routes/`, `csrf.py` (middleware), `templates/`, `static/`
- Templates use Jinja2 with `{% extends "base.html" %}` base layout
- All forms use CSRF tokens via `CSRFMiddleware` — include `{{ csrf_hidden_field }}` in forms
- htmx is loaded from static, not CDN — `static/htmx.min.js`
- htmx requests use `hx-post`/`hx-get` with `hx-target` for partial page updates
- CSRF token sent via `hx-headers='{"X-CSRF-Token": "{{ csrf_token }}"}'` on htmx elements
- Dark/light theme toggle persisted via localStorage, class on `<html>` element
- No JS build step — vanilla JS in `<script>` tags within templates or `static/`
- Tests in `tests/test_web.py` use Starlette `TestClient` with CSRF-aware helpers

## Common Patterns

### Route handler
```python
async def my_page(request: Request) -> Response:
    # Load data
    data = get_data()
    return templates.TemplateResponse(request, "my_page.html", {"data": data})
```

### htmx partial update
```html
<button hx-post="/action" hx-target="#result" hx-headers='{"X-CSRF-Token": "{{ csrf_token }}"}'>
    Do Thing
</button>
<div id="result"></div>
```

### Form with CSRF
```html
<form method="post" action="/submit">
    {{ csrf_hidden_field }}
    <input type="text" name="field" />
    <button type="submit">Submit</button>
</form>
```

## Pitfalls

- Always validate paths from user input with `Path.resolve()` — see TD-025 for the scan endpoint fix
- htmx responses for partial updates should return HTML fragments, not full pages
- Use `request.query_params` not `request.path_params` for query string values
- Starlette `TestClient` is synchronous even though handlers are async
- Thread safety: use per-request DB connections in production (see `get_db` pattern in app.py)
