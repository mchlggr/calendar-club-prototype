Here’s a clean, scalable way to structure your Calendar Club event‑discovery agent so it’s explainable and easy to expand across regions.

![Simple pipeline sketch showing source collectors flowing into a normalizer, then a signal classifier, then routed to intent-specific nodes like startup, AI, community, then a deduper/enricher, ending in storage and notifications.]

# Intent‑graph approach (not source‑graph)

Instead of hard‑coding separate flows for Luma, Posh, Meetup, etc., build a small graph where **nodes represent intents (what the step does)**, not the site. Sources become swappable inputs.

**Core idea**

* **Signal types** (taxonomy): `startup`, `community`, `ai` (you can add `design`, `funding`, etc.).
* **Reusable nodes**: `Collect`, `Normalize`, `ClassifySignal`, `RouteBySignal`, `Dedup/Cluster`, `Enrich`, `GeoGate`, `Persist`, `Notify`.
* **Per‑region policies** are config (ZIPs, metros, radius, keywords), not code.

## Minimal graph (concept)

```
[Collect] ─▶ [Normalize] ─▶ [ClassifySignal] ─▶ [RouteBySignal]
                                                     ├─▶ [StartupPipeline]
                                                     ├─▶ [AIPipeline]
                                                     └─▶ [CommunityPipeline]
                                          (all) ─▶ [Dedup/Cluster] ─▶ [Enrich] ─▶ [GeoGate] ─▶ [Persist] ─▶ [Notify]
```

## What each node does (and reuses across sources)

* **Collect**: Pull raw events from any source (Luma/Posh/Meetup/Eventbrite/River/Discord/ICS/RSS). Output: raw JSON.
* **Normalize**: Map fields to a unified schema (title, start/end, venue, city, host, price, tags, URL, images).
* **ClassifySignal**: Assign `signal_type ∈ {startup, community, ai}` using rules + model (title/desc/host/tags).
* **RouteBySignal**: Fan‑out to intent pipelines (e.g., AI events may need model/speaker extraction).
* **Dedup/Cluster**: Merge duplicates across sources (same event appearing on Luma + Meetup).
* **Enrich**: Expand with org metadata, speakers, social links, timezone fixes, geocoding, image proxy.
* **GeoGate**: Apply region filters (metro, radius, state) and quiet‑hours.
* **Persist**: Upsert to your store (Postgres/ClickHouse) with idempotency.
* **Notify**: Downstream actions (weekly digest, Slack/Discord post, site publish, RSS, webhook).

## Practical LangGraph shape (TypeScript-ish, high level)

```ts
// Nodes = intents. Sources are just inputs to Collect.
graph(
  Collect,         // source: ["luma","posh","meetup",...]
  Normalize,       // map to UnifiedEvent
  ClassifySignal,  // -> "startup" | "ai" | "community"
  RouteBySignal({  // dynamic edge by signal_type
    startup: StartupPipeline,
    ai: AIPipeline,
    community: CommunityPipeline,
  }),
  DedupCluster,
  Enrich,
  GeoGate,
  Persist,
  Notify
)
```

### Example: Classifier prompt (concise rubric)

* **startup**: pitch nights, founder meetups, VC, accelerators, hackathons, product demos.
* **ai**: LLMs, RAG, agents, model evals, AI hack nights, MLOps.
* **community**: general tech socials, study groups, coworking, code & coffee, user groups.

## Config, not code (per region)

```json
{
  "region": "ohio-columbus",
  "metros": ["Columbus, OH", "Dublin, OH", "Hilliard, OH"],
  "radius_km": 80,
  "quiet_hours_utc": ["02:00-09:00"],
  "source_feeds": {
    "luma": ["org/kickstart-ohio", "org/buckeye-ai"],
    "meetup": ["Columbus-AI", "Startup-Grind-Columbus"],
    "posh": ["tag:tech,ai,startups"]
  },
  "keywords": {
    "ai": ["AI","LLM","RAG","agent","LangGraph","OpenAI","Anthropic","vector"],
    "startup": ["pitch","founder","accelerator","demo day","venture","SaaS"],
    "community": ["meetup","social","study group","coworking","code & coffee"]
  }
}
```

## Why this works for Calendar Club

* **Explainable**: Every step is a labeled intent; easy to debug (“bad label at ClassifySignal”).
* **Reusable**: Add River/Eventbrite later without touching downstream nodes.
* **Regional scale**: New city = new config, same graph.
* **A/B friendly**: Swap classifiers (rules ↔ model) without changing the pipeline.
* **Observability**: Emit spans per node (`source`, `signal_type`, `dedup_group`, `region`) for LangSmith/LangFuse/OTel.

## Storage sketch (minimal tables)

* `events_raw(source, external_id, payload_json, fetched_at)`
* `events_unified(event_id, title, starts_at, ends_at, venue, city, lat, lon, organizer, price, url, signal_type, tags, hash, region, updated_at)`
* `events_clusters(cluster_id, event_id, confidence)`
* `events_enrichment(event_id, speakers, org_urls, twitter, linkedin, image_url, notes)`

## Quick start checklist

* Stand up **Collect** for Luma/Posh/Meetup (API or scraper).
* Implement **Normalize** to your unified schema.
* Ship a simple **Classifier** (keyword rules + fallback LLM).
* Add **Dedup** (title+time+venue fuzzy hash).
* Gate by **region** and publish via **Notify** (site + Slack).
* Add traces on each node for easy post‑mortems.

If you want, I can drop in a ready‑to‑paste LangGraph node skeleton and a tiny Postgres schema that fits your Nx monorepo conventions.
