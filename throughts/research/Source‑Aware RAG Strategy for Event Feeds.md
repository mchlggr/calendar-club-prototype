Here’s a simple, practical way to level‑up your events work: start **logging source provenance** (which platform an event came from—Luma, Eventbrite, Posh, Meetup, etc.) alongside each retrieved event so you can learn which sources drive the most durable, community‑centric events over time.

---

### Why this matters (quick)

* **Quality signals:** Some platforms skew toward recurring, high‑retention communities; others skew toward promos. Tracking origin lets you quantify that.
* **Ranking:** Use source as a feature in relevance scoring (“boost Luma + recurring organizers for workshops,” “de‑weight one‑off promos”).
* **Ops & trust:** When an event goes stale, you’ll know which connector tends to rot fastest and can tighten that pipeline.

---

### Minimal data to capture per event

* `source.name` (e.g., `"luma"`, `"eventbrite"`, `"posh"`, `"meetup"`)
* `source.event_id` (stable external ID)
* `source.url` (canonical detail page)
* `source.fetched_at` (ISO timestamp)
* `source.connector_version` (your scraper/agent version)
* `source.webhook?` (was it pushed via webhook vs pulled)
* `event.lifecycle` signals:

  * `first_seen_at`, `last_seen_at`
  * `status` (`scheduled|updated|cancelled|past`)
  * `update_count` (how often it changes)
* Engagement (if available): `rsvp_count`, `waitlist`, `price`, `organizer_followers`

```json
{
  "id": "uuid-v4",
  "title": "Buckeye AI Meetup: Agentic Workflows",
  "start": "2026-01-12T23:30:00Z",
  "end": "2026-01-13T01:00:00Z",
  "venue": { "name": "UA Library", "city": "Columbus", "state": "OH" },
  "source": {
    "name": "luma",
    "event_id": "evt_9f3a2",
    "url": "https://lu.ma/evt_9f3a2",
    "fetched_at": "2026-01-03T10:00:00Z",
    "connector_version": "luma@0.4.3",
    "webhook": true
  },
  "lifecycle": {
    "first_seen_at": "2025-12-20T15:11:00Z",
    "last_seen_at": "2026-01-03T10:00:00Z",
    "status": "scheduled",
    "update_count": 3
  },
  "engagement": { "rsvp_count": 128, "waitlist": 12, "price": 0 }
}
```

---

### Easy scoring features to try

* **Source prior:** `score += prior[source.name]` (start equal; let data learn)
* **Stability bonus:** `+log(update_count+1)` or `+days_since_first_seen`
* **Organizer quality:** rolling avg attendance / cancellations per source
* **Freshness by source:** decay slower for sources that rarely go stale

---

### Lightweight analytics to learn fast

* **Cohorts by source:** retention of *organizers* and *attendees* per source
* **False‑positive rate:** share of events that get cancelled or missing details
* **Latency:** time from event creation → first seen (per source & connector version)
* **Coverage:** unique organizers per source in Ohio vs total events

---

### Storage & pipeline tips

* Put the `source.*` fields in your **primary event document** (not a side table) so they’re queryable for ranking.
* Write an **immutable audit log** row for each fetch/update (great for connector debugging).
* Tag every trace/span with `source.name` (your LangSmith/LangFuse setup will love this).
* When de‑duping across platforms, **retain a `source_links[]` array** so you don’t lose provenance on merges.

---

### Quick tasks to implement next

1. Add `source` + `lifecycle` fields to your event model.
2. Update each connector/agent to populate them.
3. Backfill `source.name` and `first_seen_at` for existing events.
4. Add a simple **per‑source dashboard**: events/week, cancellations, avg updates, RSVP medians.
5. Turn on a **feature flag** to include `source` priors in ranking and A/B the effect.

If you want, I can draft the DB migration and a tiny relevance function showing how to fold `source` into your current scoring.
