# Tech Stack — Calendar Club

> An opinionated, minimal architecture for a pre-revenue consumer event-discovery product.

---

## Context

Calendar Club is a consumer-first event discovery experience with an LLM-powered "deep research agent" that surfaces relevant local events in a Human Week View calendar UI. The product optimizes for **boomerang behavior** (discover → click out → return) and **temporal intelligence** (understanding "this weekend" or "next Thursday night").

**Key constraints driving these choices:**

- **Pre-revenue, pre-customer:** Every decision optimizes for speed-to-learning over scale
- **Defer complexity:** No premature infrastructure—add persistence and services only when pain is real
- **AI-native:** The LLM is the product, not a feature bolted on
- **Web-only MVP:** Read-only calendar integration initially

---

## Runtime & Application Frameworks

### Backend: FastAPI + Python 3.12

```
uv                    # Package manager (fast, handles Python version)
FastAPI               # Async API framework
Pydantic v2           # Request/response validation
uvicorn               # ASGI server
python-dotenv         # Environment configuration
```

**Why FastAPI:**
- Async-native for LLM streaming and external API calls
- First-class OpenAPI docs at `/docs` (zero config)
- Pydantic v2 for type-safe validation with minimal boilerplate
- Hot reload via `uvicorn --reload` for tight dev loops

**Structure:**
```
api/
├── index.py          # Main app + routes (Vercel entrypoint)
├── routers/          # Route modules (discovery, events, etc.)
├── services/         # Business logic (agent, temporal parsing)
├── models/           # Pydantic schemas
└── core/             # Config, dependencies
```

### Frontend: Next.js 14+ (App Router)

```
Next.js 14+           # React framework with App Router
TypeScript            # Type safety
React 18+             # UI library
```

**Why Next.js App Router:**
- Server Components reduce client bundle (calendar UI can be heavy)
- Streaming responses work naturally with LLM output
- File-based routing matches our simple page structure
- Vercel deployment is zero-config

**Structure:**
```
frontend/
├── app/              # App Router pages
│   ├── page.tsx      # Discovery home
│   ├── week/         # Week view
│   └── share/        # Shareable calendar links
├── components/       # UI components
│   ├── calendar/     # Week view components
│   └── discovery/    # Search + clarifying questions
├── lib/              # Utilities, API client
└── styles/           # Global styles
```

---

## Data & Content Layer

### MVP: No Database (In-Memory + File)

```
In-memory caching     # For session state, search results
JSON files            # For seed event data, configs
localStorage          # Anonymous user preferences + session UUID
```

**Why defer the database:**
- Events come from external APIs/sources (not user-generated content in MVP)
- User state is minimal (preferences, recent searches)
- Session UUID in localStorage provides anonymous telemetry identity
- Profile parameters can live client-side initially

### V1: SQLite / Turso (When Persistence is Required)

```
SQLite                # Local development
Turso                 # Production (hosted SQLite at the edge)
libsql-client         # Python client for Turso
```

**When to add:**
- Caching external API responses to reduce rate limit pressure
- Storing user feedback/ratings from the shopping-researcher loop
- Persisting search history for returning users

**Why Turso:**
- SQLite semantics you already know
- Edge replication (low latency reads)
- Generous free tier, scales with usage
- No connection pooling headaches

**Schema principles:**
- Events table with stable canonical ID (for deduplication)
- Provenance columns (source, source_url, fetched_at)
- SQLite FTS5 for full-text search when needed

---

## Frontend & Styling

### UI Framework

```
Tailwind CSS          # Utility-first styling
shadcn/ui             # Accessible component primitives
Radix UI              # Headless components (via shadcn)
Lucide React          # Icons
```

**Why this stack:**
- Tailwind + shadcn = rapid iteration without CSS architecture debates
- shadcn components are copy-paste, not npm dependencies (you own the code)
- Radix provides accessibility baked in
- Consistent with modern Next.js patterns

### Calendar UI

The Human Week View is a must-have ([DOC-11]). Build it with:

```
date-fns              # Date manipulation (tree-shakeable)
@dnd-kit/core         # Drag interactions (if needed later)
```

**Week View requirements (from research):**
- Weekend shading, now marker, density cues
- Hover peek cards for event details
- All-day event strip
- Focus day expansion
- Mobile-responsive grid

### State Management

```
React Context         # For lightweight global state (user prefs, filters)
TanStack Query        # Server state, caching, request deduplication
Zustand (optional)    # Only if Context becomes unwieldy
```

**Keep it simple:** Context + TanStack Query handles 90% of needs. Avoid Redux/MobX complexity for an MVP.

---

## Tooling & Quality

### Development

```
uv                    # Python package/version management
pnpm                  # Node package manager (fast, efficient)
Biome                 # JS/TS linting + formatting (faster than ESLint+Prettier)
Ruff                  # Python linting + formatting
pyright               # Python type checking
```

**Why Biome over ESLint+Prettier:**
- Single tool, 10-100x faster
- Sensible defaults, less config
- Active development, good Next.js support

### Testing

```
pytest                # Python tests
pytest-asyncio        # Async test support
vitest                # Frontend unit tests
Playwright            # E2E tests (when needed)
```

**Testing philosophy for MVP:**
- Unit tests for temporal parsing (critical path)
- Integration tests for LLM agent flows
- Skip E2E until user flows stabilize
- Manual QA is acceptable for V0

### Pre-commit & CI

```
pre-commit            # Git hooks
GitHub Actions        # CI/CD
```

**Pre-commit hooks:**
- ruff check + format
- pyright
- biome check

---

## Infrastructure & Delivery

### Hosting: Vercel (Unified)

```
Vercel                # Frontend + API (via Python runtime)
```

**Why Vercel for everything:**
- Zero-config deploys from git push
- Python runtime supports FastAPI (via `vercel.json` rewrites)
- Preview deployments per PR
- Edge network for frontend assets
- Environment variable management

**`vercel.json` pattern:**
```json
{
  "rewrites": [
    { "source": "/api/(.*)", "destination": "/api/index.py" }
  ]
}
```

### Telemetry: HyperDX

```
HyperDX               # Unified logs, traces, metrics
OpenTelemetry         # Instrumentation standard
```

**Implementation:**
- OpenTelemetry SDK in both Python and TypeScript
- HyperDX collector endpoint
- Anonymous user tracking via localStorage UUID:

```typescript
// lib/telemetry.ts
const getSessionId = () => {
  let id = localStorage.getItem('cc_session_id');
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem('cc_session_id', id);
  }
  return id;
};
```

**Key events to track:**
- `search_performed` (with parsed intent)
- `results_viewed` (count, latency)
- `event_clicked_out` (event ID, source)
- `boomerang_return` (time since click-out)
- `feedback_rated` (rating, event ID)

### Secrets & Config

```
Vercel Environment Variables    # Production secrets
.env.local                      # Local development
python-dotenv                   # Load .env in Python
```

**Required secrets:**
- `OPENAI_API_KEY` — LLM provider
- `HYPERDX_API_KEY` — Telemetry
- `TURSO_DATABASE_URL` — Turso database URL
- `TURSO_AUTH_TOKEN` — Turso auth token
- External API keys as sources are added

### CI/CD Pipeline

```yaml
# .github/workflows/ci.yml
- Install deps (uv sync, pnpm install)
- Lint (ruff, biome)
- Type check (pyright, tsc)
- Test (pytest, vitest)
- Deploy preview (Vercel auto)
- Deploy production (on main merge)
```

---

## Additional Notes

### Architecture Principles

1. **Monolith first:** One FastAPI app, one Next.js app. Split when you must, not before.

2. **Client-side session:** Anonymous users get a UUID, preferences live in localStorage. Auth comes later.

3. **External APIs are the database:** Event data lives in Eventbrite/Meetup/Luma. We cache minimally.

4. **LLM as first-class citizen:** The agent isn't a plugin—streaming, tool calls, and token management are core concerns.

5. **Measure before optimizing:** HyperDX telemetry from day one. Boomerang rate is the north star.

### Security Baseline

- CORS configured for frontend origin only (not `*` in production)
- API keys in environment variables, never in code
- Rate limiting on LLM endpoints (token budget per session)
- Input sanitization via Pydantic models
- HTTPS enforced via Vercel

### Cost Control (Pre-Revenue)

- Vercel Hobby/Pro tier (~$0-20/mo)
- OpenAI API with per-request token limits
- Turso free tier (9GB storage, 500M reads/mo)
- HyperDX free tier for telemetry
- No background infrastructure until needed

---

*Last updated: January 2025*
