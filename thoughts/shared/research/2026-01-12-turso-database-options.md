---
date: 2026-01-12T16:49:23Z
researcher: Claude
git_commit: 8e4a333
branch: main
repository: calendar-club-prototype
topic: "Turso Database Connection Options Decision"
tags: [research, database, turso, libsql, sqlite, graceful-degradation]
status: complete
last_updated: 2026-01-12
last_updated_by: Claude
---

# Research: Turso Database Connection Options

**Date**: 2026-01-12T16:49:23Z
**Git Commit**: 8e4a333
**Branch**: main

## Research Question

Evaluate options for Turso database connectivity:
1. Can auth tokens be embedded in the connection URL string?
2. Can we gracefully handle missing database and skip persistence?

## Executive Summary

**Neither option works as simply hoped:**

| Option | Feasibility | Why |
|--------|-------------|-----|
| URL-embedded token | **No** | Python libsql-client requires separate `auth_token` param |
| Current SQLiteSession with Turso URL | **No** | SQLiteSession only supports local files, not remote URLs |
| Graceful no-persistence mode | **Yes** | Session is optional in agents SDK |

**Recommended path**: Option 2 (graceful degradation) is the simplest to implement now, with Option 3 (libsql integration) as a future enhancement.

---

## Option 1: URL-Embedded Authentication Token

### Research Findings

**Python libsql-client does NOT support URL-embedded tokens.**

Unlike JavaScript clients which accept `libsql://db.turso.io?authToken=xxx`, the Python packages require a **separate parameter**:

```python
import libsql_client

# This is the ONLY way in Python
client = libsql_client.create_client_sync(
    url="libsql://your-database.turso.io",
    auth_token="your-auth-token"  # Must be separate
)
```

### Security Note

This is actually a **security benefit**. URL-embedded credentials risk exposure through:
- Server/proxy logs
- Browser history
- Referrer headers
- Stack traces

### Verdict

**Not viable.** Cannot embed token in URL string for Python.

---

## Option 2: Graceful Degradation (No Persistence)

### Research Findings

**The OpenAI agents SDK session is OPTIONAL.**

From `agents/run.py:319`:
```python
session: Session | None = None,  # <- Optional, defaults to None
```

Without a session:
- Agent functions normally
- Each request is stateless
- No conversation history across requests
- Search preferences not persisted

### Existing Patterns in Codebase

The codebase already has robust graceful degradation patterns:

| Pattern | Example | Behavior |
|---------|---------|----------|
| Empty return + warning | `firecrawl_agent.py:138` | Returns `[]`, logs warning |
| `is_configured()` check | `google_calendar.py:87` | Returns 503 or status info |
| Error stream response | `index.py:286` | Sends error event in stream |
| Skip tests | `test_live_sources.py:162` | Tests skip when API keys missing |

### Implementation Approach

```python
# api/services/session.py
def _get_database_path() -> str | None:
    """Return database path or None if not configured for local use."""
    settings = get_settings()
    if settings.database_url:
        # Remote URL configured but not supported by SQLiteSession
        logger.warning("DATABASE_URL configured but SQLiteSession only supports local files. Running stateless.")
        return None
    return str(DEFAULT_DB_PATH)

# In SessionManager
def get_session(self, session_id: str) -> SQLiteSession | None:
    if self.db_path is None:
        return None  # Stateless mode
    return SQLiteSession(session_id, self.db_path)
```

### User Impact

| Feature | With Session | Without Session |
|---------|--------------|-----------------|
| Chat works | Yes | Yes |
| Search works | Yes | Yes |
| Conversation history | Persisted | Lost on refresh |
| "Remember my preferences" | Works | Doesn't persist |
| Multi-turn context | Maintained | Each message standalone |

### Verdict

**Viable and simple.** Can implement today with minimal changes.

---

## Option 3: Full Turso Integration (Future)

### What It Would Require

1. **Add `libsql-client` dependency**
   ```
   pip install libsql-client
   ```

2. **Create custom TursoSession class** implementing the `Session` protocol:
   ```python
   import libsql_client
   from agents import Session

   class TursoSession(Session):
       def __init__(self, session_id: str, url: str, auth_token: str):
           self.client = libsql_client.create_client_sync(
               url=url,
               auth_token=auth_token
           )
           # ... implement Session protocol methods
   ```

3. **Use conditional logic in SessionManager**:
   ```python
   def get_session(self, session_id: str) -> Session:
       settings = get_settings()
       if settings.database_url.startswith("libsql://"):
           return TursoSession(
               session_id,
               settings.database_url,
               settings.turso_auth_token
           )
       return SQLiteSession(session_id, self.db_path)
   ```

### Effort Estimate

- Create TursoSession class: ~100 lines
- Match SQLiteSession schema/behavior: ~2-4 hours
- Testing: ~1-2 hours

### Verdict

**Viable but more work.** Good future enhancement when persistence matters.

---

## Recommendation

### Immediate (Today)

**Implement Option 2: Graceful degradation**

1. Modify `session.py` to return `None` when `DATABASE_URL` is set (indicating remote intent but unsupported)
2. Modify `index.py` chat endpoint to handle `session=None`
3. Local development continues using `conversations.db`
4. Production runs stateless (no session persistence)

### Future (When Needed)

**Implement Option 3: Full Turso integration**

When conversation persistence becomes important for production users, implement the `TursoSession` class.

---

## Code References

- `api/services/session.py:22-32` - Current `_get_database_path()` implementation
- `api/index.py:298-303` - Session creation in chat endpoint
- `.venv/.../agents/run.py:319` - Session parameter is optional
- `.venv/.../agents/memory/sqlite_session.py:53` - Only supports `sqlite3.connect()` (local files)
- `api/services/google_calendar.py:87-91` - `is_configured()` pattern example
- `api/services/firecrawl_agent.py:138-140` - Empty return pattern example

## External Documentation

- [Turso Python SDK](https://docs.turso.tech/sdk/python/quickstart)
- [libsql-client-py GitHub](https://github.com/tursodatabase/libsql-client-py)
- [libSQL Database URLs](https://docs.turso.tech/reference/libsql-urls)
