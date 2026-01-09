Here’s a clear, end‑to‑end plan for an events aggregator that crawls major platforms, normalizes data into one clean model, ranks what matters, and syncs out to calendars.

# Architecture at a glance

* **Loop:** crawl → extract → normalize → dedupe → enrich → rank → export (ICS/CalDAV).
* **Sources (P0→P2):** Luma, Eventbrite, Meetup, Facebook/IG pages, venue websites, Posh, etc. Prefer first‑party APIs; fall back to scrapes.
* **Model:** one canonical event shape so everything downstream is simple and fast.

## Canonical Event Model (normalized)

```ts
Event {
  id: string                // internal UID
  title: string
  description?: string
  organizer: {
    name?: string
    handle?: string         // @org (if known)
    url?: string
    qualityScore?: number
  }
  start: string             // ISO 8601
  end?: string              // ISO 8601
  timezone?: string         // IANA tz
  location: {
    name?: string
    address?: string
    lat?: number
    lon?: number
  }
  price?: { amount: number; currency: string } | null
  tags: string[]
  images?: { url: string; alt?: string }[]
  source: {
    system: 'luma'|'eventbrite'|'meetup'|'facebook'|'posh'|'web'
    url: string
    fetchedAt: string       // ISO
  }
  dedupeKey: string         // composite (see below)
  provenance: string[]      // merge trace of source records
  updatedAt: string         // ISO
}
```

## Crawling & extraction

* **APIs first** (rate‑limit aware): Luma API, Eventbrite API, Meetup API.
* **Scraping fallback:** venue and organizer sites, Facebook/IG pages (respect robots.txt & crawl‑delay).
* **Workers:** per‑source adapters producing a common “RawEvent” shape → queued to a **Normalizer**.

## Normalization

* Clean titles (“[FREE] …”), parse datetimes to ISO + tz, resolve currency, standardize tags, parse price ranges to min/typical.
* Address → geocode (primary: provider API; cache results).
* Images → fetch alt (from page captions or OG tags) and store first best.

## Dedupe & conflict resolution

* **Composite key:** hash(normalized_title, date_window(start±90m), venue_slug, organizer_name).
* **Fuzzy fallback:** trigram/Levenshtein on (title, venue, start).
* **Conflict policy:** prefer first‑party APIs over scrapes; prefer **latest update** over earlier listing; preserve a **provenance graph** showing merges.

## Enrichment

* Venue geocoding + neighborhood; organizer social handles; inferred tags (LLM or rules) from description/title; popularity proxy (RSVPs, followers if exposed).

## Ranking

Score = weighted sum of:

* **Interest fit:** user/segment embeddings dot‑product with event embedding.
* **Freshness/recency:** upcoming sooner (but not too soon) gets a lift.
* **Proximity:** distance to user/home base.
* **Organizer quality:** historical reliability, attendance, reviews.
* **Diversity:** re‑rank to avoid near‑duplicates in a feed.

## Freshness daemon & budgets

* Per‑source refresh budgets (e.g., Luma hourly, Eventbrite every 2h, scrapes daily).
* Backoff when unchanged; fast‑path re‑checks for soon events (next 72h).

## Export & sync

* **ICS feeds** per user/segment/collection; include ETags and stable UIDs.
* **CalDAV (bi‑directional) P2:** accept external edits; reconcile via provenance graph.
* Follow **RFC 5545 (iCalendar)** for VEVENT fields (UID, DTSTAMP, DTSTART/DTEND, SUMMARY, DESCRIPTION, LOCATION, GEO, URL, ORGANIZER, CATEGORIES).

## Privacy & compliance

* Minimize PII in logs; hash emails for subscriptions; honor robots.txt & crawl‑delay; “forget me” endpoint to purge user data and subscriptions.

## Milestones

* **P0 (Weeks 1–2):** Luma + Eventbrite APIs; normalization; dedupe; ICS out; minimal ranking (freshness + proximity).
* **P1 (Weeks 3–6):** Meetup + website scrapers; full ranking (embeddings + quality); daily refresh daemon; enrichment (geocoding, handles, tags).
* **P2 (Weeks 7–10):** Bi‑directional CalDAV; user preferences (interests, distance, price); on‑device cache/offline; provenance viewer.

## Data & infra sketch

* **Ingest:** Message queue (e.g., RabbitMQ/Redis Streams) per source.
* **Storage:** Postgres (events + provenance + ICS cache) + Vector DB (embeddings) + Redis (hot feed cache).
* **Jobs:** Containerized workers per source & per stage; scheduler for budgets.
* **Observability:** Traces across adapters; counters for rate limits, merge ops, rank timings.

## APIs (external)

* `GET /events?bbox=&start=&end=&tags=&q=&limit=`
* `GET /feeds/:id.ics` (ETag/If‑None‑Match)
* `POST /subscriptions` (webhook for updates)
* `POST /feedback` (like/save/hide → tune embeddings)

## Minimal schemas (storage)

```sql
events(id pk, title, start, "end", tz, venue_name, addr, lat, lon, price_amt, price_ccy, tags text[], source_system, source_url, dedupe_key, updated_at);
event_provenance(event_id fk, source_system, source_url, merged_at, note);
organizers(id pk, name, handle, url, quality_score);
rank_features(event_id fk, user_id fk, interest, freshness, proximity, org_quality, total);
```

## Testing checklist

* Duplicate detection across Luma↔Eventbrite for same event.
* Timezone correctness (DST edges).
* Cal app import (Apple/Google/Outlook) + updates via identical UID.
* Scraper politeness (crawl‑delay) and blocklist.
* Red‑team: malformed dates/prices, missing venues, images without alts.

## Hand‑off next steps (short)

1. Scaffold source adapters (Luma, Eventbrite) → emit `RawEvent`.
2. Build Normalizer → Canonical model + geocoding + tags.
3. Implement dedupe (composite key + fuzzy fallback) + provenance store.
4. Ship ICS feed with stable UID/ETag; verify in Apple/Google/Outlook.
5. Add simple rank (freshness+distance); then plug in embeddings.
6. Stand up refresh daemon with per‑source budgets and backoff.

If you want, I can generate the first pass of the event DB schema, ICS serializer stubs, and a per‑source adapter interface you can drop into your monorepo.
