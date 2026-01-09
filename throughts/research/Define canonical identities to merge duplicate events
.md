Here’s a simple, durable way to keep the “same event” synced across Eventbrite, Meetup, Google Calendar, etc., even when each source uses different IDs.

# Canonical Event Identity (CEI)

**Definition:**
`CEI = (normalized_title, utc_start_window, venue_or_url, source_authority)`

* **normalized_title**: lowercase, trimmed, stopwords removed, collapsed whitespace, common tokens stripped (e.g., “meetup”, “eventbrite”, “online event”).
* **utc_start_window**: `(start_utc, ±tolerance)`—e.g., ±30 minutes (or tighter/looser by source).
* **venue_or_url**: stable location key—prefer a venue slug when on-site; else the canonical URL host+path for online.
* **source_authority**: tie‑breaker rank (e.g., official Google Calendar > Eventbrite > Meetup > scraped pages).

## Why this works

Vendors churn titles, tweak URLs, or reissue IDs. The 4‑tuple above stays stable enough to *match* and *merge* without chasing third‑party IDs.

## Practical defaults

* Title normalization: lowercase → remove punctuation → remove boilerplate (“RSVP”, “Free”, “(Columbus)”) → stem.
* Tolerance:

  * Eventbrite: ±15–20 min
  * Meetup: ±30–45 min
  * Community calendars/scrapes: ±60 min
* Venue key: `(lat_round, lon_round, name_norm)` with geo rounding to ~50–100m, or `url_host + path_base` for virtual.

## Merge logic (deterministic)

1. Compute CEI for each incoming item.
2. **Candidate set** = events in the same day bucket with:

   * Jaro–Winkler (or cosine) on `normalized_title` ≥ threshold (e.g., 0.90), and
   * overlapping `utc_start_window`, and
   * same `venue_or_url` key.
3. If 1+ candidates: pick the one with the smallest composite distance; else create a new event cluster.
4. Inside a cluster, keep a **record-of-record** by `source_authority` then freshness (latest updated_at).
5. Track provenance: store all raw source payloads + a mapping table `{cluster_id ↔ source_event_id}`.

## Minimal schema (relational)

```sql
-- Canonical cluster
CREATE TABLE event_cluster (
  id UUID PRIMARY KEY,
  title_norm TEXT NOT NULL,
  start_utc TIMESTAMP WITH TIME ZONE NOT NULL,
  tolerance_minutes INT NOT NULL DEFAULT 30,
  venue_key TEXT NOT NULL,
  source_of_truth TEXT NOT NULL, -- e.g., 'gcal_official'
  hash_cei TEXT GENERATED ALWAYS AS (
    md5(title_norm || '|' || date_trunc('minute', start_utc) || '|' || tolerance_minutes || '|' || venue_key)
  ) STORED
);

-- Source instances
CREATE TABLE event_instance (
  id UUID PRIMARY KEY,
  cluster_id UUID REFERENCES event_cluster(id),
  source TEXT NOT NULL,          -- 'eventbrite', 'meetup', 'gcal', 'scrape'
  source_event_id TEXT NOT NULL, -- their foreign ID
  title_raw TEXT,
  start_utc TIMESTAMP WITH TIME ZONE,
  venue_raw JSONB,
  url TEXT,
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
  payload JSONB NOT NULL
);

CREATE UNIQUE INDEX ON event_instance (source, source_event_id);
CREATE INDEX ON event_cluster (hash_cei);
```

## CEI builder (TypeScript sketch)

```ts
export function normalizeTitle(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
    .replace(/\b(meetup|eventbrite|online|virtual|free|rsvp|tickets?)\b/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

export function venueKey({lat, lon, name, url}: {lat?: number; lon?: number; name?: string; url?: string}) {
  if (url) {
    try {
      const u = new URL(url);
      return `${u.host}${u.pathname.replace(/\/$/, '')}`;
    } catch { /* ignore */ }
  }
  if (lat != null && lon != null) {
    const r = (x:number)=> (Math.round(x*10000)/10000).toFixed(4); // ~11m; adjust
    return `geo:${r(lat)},${r(lon)}:${normalizeTitle(name ?? '')}`;
  }
  return `name:${normalizeTitle(name ?? '')}`;
}

export function cei(title: string, startUtc: Date, toleranceMin: number, venue: Parameters<typeof venueKey>[0], authority: string) {
  return {
    normalized_title: normalizeTitle(title),
    utc_start_window: { start_utc: startUtc.toISOString(), tolerance_min: toleranceMin },
    venue_or_url: venueKey(venue),
    source_authority: authority,
  };
}
```

## Matching thresholds (suggested)

* Title: Jaro–Winkler ≥ **0.90** (≥0.85 if same organizer).
* Time: windows overlap (|Δ| ≤ min(tolerances)).
* Venue: exact `venue_key` match (or fuzzy if indoor campus—then allow same campus slug).

## Stable merges over time

* Recompute CEI on every ingest; never mutate cluster IDs.
* If an instance’s CEI no longer matches its cluster (title/venue change), **re-evaluate** and possibly **relink**—but preserve history so URLs don’t break.
* Emit a deterministic **external_id** for your app: `cluster_id` (UUID) or `sha256(hash_cei || first_seen_date)`.

## Edge cases

* **Multi‑day events**: use per‑occurrence CEIs (expand recurrences).
* **Series with identical titles**: add an **organizer_norm** to the CEI tuple.
* **Venue moves (rain plan)**: allow a controlled venue_key fallback within N meters or same organizer+time.
* **Daylight savings**: convert everything to UTC at ingest; never compare local times.
* **Cross‑posts**: many sources share the same Eventbrite URL—`venue_or_url` handles it.

## What you get

* One stable cluster per real‑world event.
* Deterministic merges, reversible decisions, and explainable matches.
* Clean “deduped” feeds for your site/app, with source‑backlinks and auditability.

If you want, I can turn this into a drop‑in Nx library (functions, thresholds, migration SQL, and a tiny reconciliation service) that plugs into your Calendar Club pipeline.
