Here’s a compact playbook for building a fast “deep‑research” events agent that actually finds the right in‑person events (not just anything with “AI” in the title).

---

# Hybrid event data model + retrieval that feels instant

**Idea:** use a **hybrid schema**—strict fields for facts, and a flexible “vibes” blob for everything qualitative—then index both for **keyword filters + vector search**.

## 1) Data model (Postgres example)

* **Structured columns** (exact facts you can filter/sort on):

  * `id`, `title`, `start_time`, `end_time`, `timezone`
  * `venue_name`, `venue_city`, `venue_region`, `lat`, `lon`
  * `organizer_name`, `source` (eventbrite/luma/etc.), `url`
  * `price_min`, `price_max`, `currency`, `is_free`, `capacity`
  * `tags` (string[]: “meetup”, “conference”, “hackathon”…)
* **Flexible column**:

  * `vibes JSONB` — extracted descriptors your agent infers:

    * `tone`: “hands‑on”, “founder‑y”, “academic”, “corporate”
    * `audience`: “beginner devs”, “AI researchers”, “sales”
    * `format`: “workshop”, “panel”, “career fair”
    * `topics`: [“langgraph”, “vector db”, “design systems”]
    * `relevance_reason`: short model‑authored rationale
    * `embedding`: vector (store separately if using pgvector)
* **Embeddings:**

  * Build from `title + description + vibes.topics + organizer_name`
  * Also keep a second smaller “query‑optimized” embedding if helpful

**DDL sketch (conceptual, keep it simple):**

```sql
-- facts
CREATE TABLE events (
  id TEXT PRIMARY KEY,
  title TEXT,
  description TEXT,
  start_time TIMESTAMP WITH TIME ZONE,
  end_time   TIMESTAMP WITH TIME ZONE,
  timezone   TEXT,
  venue_name TEXT,
  venue_city TEXT,
  venue_region TEXT,
  lat DOUBLE PRECISION,
  lon DOUBLE PRECISION,
  organizer_name TEXT,
  source TEXT,
  url TEXT,
  price_min NUMERIC,
  price_max NUMERIC,
  currency TEXT,
  is_free BOOLEAN,
  tags TEXT[],
  vibes JSONB
);

-- vectors (pgvector) – optional if you also push to Azure AI Search
ALTER TABLE events ADD COLUMN embedding VECTOR(1536);
CREATE INDEX idx_events_tags ON events USING GIN (tags);
CREATE INDEX idx_events_vibes ON events USING GIN (vibes jsonb_path_ops);
CREATE INDEX idx_events_time ON events (start_time);
```

## 2) Indexing in Azure AI Search (dual strategy)

Create one index with **both**:

* **Searchable text** fields: `title`, `description`, `organizer_name`, `vibes.topics`, `venue_city`, `venue_region`
* **Filterable/facetable** fields: `start_time`, `is_free`, `tags`, `venue_region`, `source`, `price_min/price_max`
* **Vector fields**: `embedding` (primary), optionally a “lite” embedding

**Query pattern (at runtime):**

1. **Boolean prefilter** (cheap): date range, city/region, free/paid, tags.
2. **Vector similarity** over the filtered set using the user’s natural‑language query.
3. **Rerank** with a lightweight cross‑encoder or hybrid BM25+vector score.
4. **Return justification** from `vibes.relevance_reason`.

This keeps the feel **snappy**: filters cut the candidate set; vector ranks quality.

## 3) Extraction pipeline (how you fill `vibes`)

* Ingest from sources (Luma/Eventbrite/Meetup/etc.).
* Normalize obvious facts (times/venue/price).
* Run an **LLM extraction** step to populate `vibes`:

  * Ask for tone, audience, topics (top 5 nouns/phrases), and a one‑sentence “who would love this & why”.
  * Keep outputs short, lowercase, underscore‑friendly for filters.
* Create/update the `embedding` using the concatenated “signal text.”

## 4) Retrieval API (simple, predictable)

**Request:**

```json
{
  "query": "hands-on langgraph workshop for practitioners",
  "when": {"start": "2026-01-06", "end": "2026-02-15"},
  "where": {"region": "OH"},
  "filters": {"is_free": true, "tags_any": ["workshop","meetup"]},
  "limit": 25
}
```

**Server flow:**

* Translate to Azure AI Search:

  * `filter`: `start_time ge X and start_time le Y and is_free eq true and tags/any(t: t eq 'workshop' or t eq 'meetup') and venue_region eq 'OH'`
  * `vector`: user‑query embedding against `embedding`
  * `search`: optional BM25 text query = raw user text
* Merge scores (weighted).
* Return: top N with `vibes.relevance_reason`.

## 5) Why this works

* **Facts stay reliable** (dead‑simple filtering and faceting).
* **Vibes stay flexible** (you can evolve descriptors without migrations).
* **Hybrid ranking** catches fuzzy intent (“beginner‑friendly hands‑on”).
* **Great UX**: users slice by time/place/price, then type intent in plain English.

## 6) Extras you’ll likely want

* **Geo**: add a `geo_point` in Search and support “within X miles”.
* **Deduping**: fuzzy dedupe across sources on `(title ~ venue ~ datetime)`.
* **Alerting**: store user queries; nightly job re‑runs them and emails new hits.
* **Telemetry**: log query → results → clicks; fine‑tune your rerank weights.

---

If you want, I can spit out:

* an Azure AI Search index template (fields + analyzers + vector def),
* a minimal ETL script outline,
* and a sample LLM extraction prompt for `vibes`.
