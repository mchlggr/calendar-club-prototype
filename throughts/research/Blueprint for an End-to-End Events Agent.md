Here’s a compact, end‑to‑end plan for an **events aggregator** that pulls from many sources, dedupes/normalizes them, and measures “event quality” so you know where to invest next.

---

# Blueprint: multi‑source event aggregator

**Goal:** ingest events from sites like Eventbrite/Meetup/Luma/River/Posh, venue sites, and university calendars; unify them into one schema; dedupe across sources; rank by usefulness; and keep provenance for takedowns/safety.

## 1) Connectors (harvest layer)

* **Sources:** Eventbrite, Meetup, Luma, River, Posh, Google Calendar/iCal feeds, venue blogs, university calendars.
* **Mechanics:**

  * Prefer **official APIs** when available; otherwise **robots.txt‑aware crawlers** (polite rate limits, rotating UA, backoff, per‑domain schedules).
  * **Incremental fetch** (since cursor or updated_at).
  * **Provenance blob** per item: `{source, source_type(api|html|ics), fetched_at, url, selector/endpoint, checksum}`.

## 2) Normalization (unify layer)

Target schema (TypeScript‑style for clarity):

```ts
type Event = {
  id: string; // stable internal UID
  title: string;
  description?: string;
  startsAt: string; // ISO
  endsAt?: string; // ISO
  timeZone?: string; // IANA
  price?: { min?: number; max?: number; currency?: string; isFree?: boolean };
  venue?: {
    name?: string;
    room?: string;
    address?: string;
    lat?: number;
    lon?: number;
    city?: string; state?: string; country?: string;
  };
  organizers?: { name?: string; url?: string }[];
  tags?: string[]; // topic, audience, format, accessibility
  accessibility?: string[]; // e.g., wheelchair, captions
  images?: string[];
  urls: { canonical?: string; rsvp?: string; tickets?: string } ;
  source: { // provenance & takedown
    provider: string; // "meetup" | "eventbrite" | "scrape:osu"
    rawId?: string;
    fetchedAt: string;
    evidence: { url: string; hash?: string };
    rights?: string;
  };
  updatedAt: string;
};
```

**Normalization tactics**

* **Time zones:** resolve using venue geo + source tz hints; fall back to source default.
* **Prices:** parse tokens (“$10–$15”, “Free”) into numbers + flags.
* **Tags:** map provider categories to internal taxonomy (topic, community, format).
* **Accessibility:** extract common phrases (“ASL”, “wheelchair accessible”, “live captions”).
* **Geo:** geocode once per venue name+address and cache.

## 3) Deduplication (entity resolution)

* Build a **fuzzy key** per item:
  `key = norm(title) + date_bucket(startsAt) + venue_key(venue.name|latlon) + city`
* Use a **two‑stage approach**:

  1. **Blocking**: exact/phonetic blocks on date bucket + city.
  2. **Rerank** with weighted features: title similarity (cosine n‑grams), geo distance, overlapping URLs/organizer.
* **Merge policy:** prefer the richest metadata per field (e.g., best description, earliest updatedAt), keep **all provenance**.

## 4) Ranking (what to show first)

* Base score = **BM25** over `title + description + tags`, boosted by **local relevance** (distance to user metro), **freshness**, and **completeness** (see quality signals below).
* Store a **feature vector** per event for experimentation (e.g., `[bm25, has_price, has_geo, img, organizer_reputation]`).

## 5) Scheduler & ops

* **Continual seek:** per‑source cron with jitter; APIs hourly, HTML daily, iCal every 4–6h.
* **Rate limits:** per‑domain tokens; central throttle.
* **Change detection:** hash raw payloads; only re‑index on change.
* **Safety/takedown:** tombstone list keyed by provenance; soft‑delete and exclude from ranking.

---

# Small benchmark: measure quality & coverage

**Why:** quantify which connectors produce the best events and where to double down.

## 1) Dataset

* **200 in‑person events** sampled across target metros (e.g., Columbus, Cleveland, Cincinnati, Dayton).
* Label each with a **5‑point “quality” score** based on:

  1. **Clarity** (title readable, non‑spammy)
  2. **Complete metadata** (time zone, venue geo, price, organizer, accessibility)
  3. **Uniqueness** (is it a duplicate?)
  4. **Local relevance** (within metro bounds)

Provide binary flags for each metadata field to compute coverage.

## 2) Systems to compare

* **Baseline:** BM25 on `title+description`.
* **Candidate:** **Tag‑aware reranker** (BM25 candidate set → lightweight ML reranker that uses tags, geo distance, completeness features).

## 3) Metrics (report by metro and overall)

* **P@20** (precision of top 20 results per query/metro).
* **NDCG@20** (uses 0–4 labels for graded relevance).
* **Coverage**: % events with (a) valid tz, (b) geocoded venue, (c) price parsed, (d) accessibility tags.
* **Dup rate**: % of items collapsed by deduper.
* **Connector yield**: events/hour and quality distribution by source.

## 4) Queries for evaluation

* 8–12 real user intents, e.g.,

  * “free startup events this weekend”
  * “family‑friendly workshops in Short North”
  * “AI meetups near OSU next week”
  * “live jazz tonight downtown”

---

# Implementation notes (fast path)

* **Storage:**

  * Raw stash (parquet or JSONL) + **normalized Postgres** (or ClickHouse for analytics) with **pgvector** for embeddings if needed.
* **Search:**

  * Start with **Elastic / Azure AI Search** (BM25 + filters); add reranker (onnx/lightGBM).
* **Geospatial:** PostGIS or built‑ins from your search tier.
* **Pipelines:**

  * **Message queue** (e.g., SQS) → workers per connector.
  * Idempotency key = provenance.evidence.hash.
* **Testing:**

  * Golden samples per connector; contract tests on normalization; replay tests for dedupe merges.

---

# What you get out of this

* A **clean, deduped, metro‑aware events index** with strong provenance and takedown support.
* A **quality dashboard** that tells you: which connectors are worth it, where metadata is thin, and how reranking changes what users see.
* A concrete path to ship **Calendar Club** (and similar) with measurable gains: show better events first, expand where coverage is weak.

If you want, I can:

1. generate a minimal ERD for the schema,
2. draft the evaluation sheet (labels + rubric), and
3. stub a BM25→reranker experiment notebook you can run.
