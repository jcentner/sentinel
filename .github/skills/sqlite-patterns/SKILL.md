---
name: sqlite-patterns
description: "SQLite database patterns for Sentinel. Use when working with the store layer, migrations, queries, or schema changes. Covers the migration framework, finding CRUD, embedding storage, and thread safety."
---

# SQLite Patterns Skill

## Official Documentation

- [Python sqlite3 docs](https://docs.python.org/3/library/sqlite3.html) — always consult for API questions
- [SQLite docs](https://www.sqlite.org/docs.html) — query syntax, pragmas, data types

## Project Conventions

- Store layer lives in `src/sentinel/store/` — `db.py` (connection + migrations), `findings.py` (CRUD), `embeddings.py` (vectors), `runs.py` (scan history)
- Migrations are `(version, description, sql)` tuples in `MIGRATIONS` list in `db.py`
- Schema version tracked in `schema_version` table — migrations applied sequentially on DB open
- Each migration + version stamp commits atomically (no `executescript()`)
- ALTER TABLE guarded with "duplicate column" tolerance for partial recovery
- Embedding vectors stored as float32 BLOBs (no sqlite-vec dependency)
- `repo_path` column scopes chunks table for multi-repo isolation
- `retention_days` parameter on fingerprint queries to bound historical data

## Common Patterns

### Adding a migration
```python
MIGRATIONS = [
    # ... existing migrations ...
    (N, "description of change", """
        ALTER TABLE findings ADD COLUMN new_field TEXT DEFAULT '';
    """),
]
```

### Thread safety in web app
```python
# Per-request connection — do NOT share connections across threads
def get_db(request):
    db_path = request.app.state.db_path
    return sqlite3.connect(db_path)
```

### Parameterized queries (ALWAYS)
```python
# CORRECT
cursor.execute("SELECT * FROM findings WHERE detector = ?", (detector_name,))

# NEVER — SQL injection risk
cursor.execute(f"SELECT * FROM findings WHERE detector = '{detector_name}'")
```

## Pitfalls

- Never use string formatting/f-strings for SQL queries — always parameterize
- `executescript()` auto-commits and cannot be rolled back — use `execute()` per statement
- SQLite connections are NOT thread-safe — one connection per thread
- `datetime('now')` in SQLite is UTC — be consistent
- Test fixtures should use `:memory:` databases for isolation
- When adding columns, use `DEFAULT` values so existing rows don't break
