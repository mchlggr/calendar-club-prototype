Here’s a compact playbook for building an **agentic Ohio events calendar** that auto-spots “emerging scenes” and “dormant groups,” powered by a LangGraph-style workflow.

---

# What this is (in plain English)

A pipeline that pulls events from **Luma, Posh, Meetup, and River**, cleans/merges them, learns which clusters of people/venues/genres are heating up, and labels the graph (“emerging scene,” “steady,” “dormant”) so you get a living social map of Ohio—not just a feed.

---

# Core concepts

* **Event graph**: Nodes = {Event, Group, Host, Venue, Topic/Tag, City/Neighborhood, Attendee Cohort}; Edges = {hosted_by, belongs_to, near, similar_to, attended_with}.
* **Scene signal**: Rolling metrics (new-group velocity, cross-post overlap, repeat-attendee density, venue reuse, tag momentum).
* **Labels**:

  * *Emerging*: fast rise in unique hosts or first-timers + topic momentum.
  * *Dormant*: >X days without events + negative velocity and decaying interest.
  * *Steady*: stable cadence and attendance.

---

# Minimal data spec (pragmatic)

**Event**: {id, title, start/end, platform, url, host_id, group_id, venue_id, tags[], city, lat/lng, price, capacity, rsvp_count, created_at, updated_at}
**Group**: {id, name, platform, url, members, topics[], city, created_at, last_event_at}
**Venue**: {id, name, address, lat/lng, city, capacity_hint}
**Host**: {id, name, contact?, platform_profile}
**Derived** (daily job): {event_quality_score, topic_vector, cluster_id, scene_label}

---

# LangGraph-style agent plan (high level)

**Nodes (tools)**

1. **Ingestors** (Luma/Posh/Meetup/River): pull or scrape; normalize to canonical Event/Group/Host/Venue.
2. **Deduper/Merger**: fuzzy match on (title, datetime, venue radius, host/group) to collapse duplicates.
3. **Geocoder**: city → county/neighborhood; attach lat/lng if missing.
4. **Tagger**: expand tags with embeddings (e.g., “founders” ≈ “startup,” “pitch”).
5. **Clusterer**: build weekly topic+geo clusters; assign `cluster_id`.
6. **Scene Scorer**: compute velocities (7/14/30‑day), repeat-attendee and cross-platform overlap; emit `scene_label`.
7. **Anomaly Watcher**: detect spikes/ghost-towns; propose label changes.
8. **Publisher**: write to Postgres/ClickHouse + search index; push to UI.

**Control flow**

* Retry on source failure → quarantine bad rows → continue.
* Idempotent upserts by `(platform, external_id)` and by dedup hash.
* Daily “label refresh” pass with sliding windows.

---

# Simple scoring rules (start here, tune later)

* **Emerging** if: `events_30d >= 3 AND velocity_7d > p95(topic) AND unique_hosts_30d >= 2`
* **Dormant** if: `days_since_last_event >= 45 OR velocity_30d < p10(topic)`
* **Steady** else if cadence variance low and attendance stable.
  (Keep thresholds per-city to avoid bias toward Columbus/Cincy.)

---

# Storage & search

* **OLTP**: Postgres (clean entities, relationships, label history).
* **Analytics**: ClickHouse (time-series metrics, velocities, cohort overlap).
* **Search**: OpenSearch/Azure AI Search (free-text + facets: city, date, tags, label).
* **Embeddings**: per Event/Group/Tag for clustering and “similar events.”

---

# UI slices (what users see)

* **Heatmap** by city/topic over last 30 days.
* **Scene cards**: badge = Emerging/Steady/Dormant, with trend sparkline.
* **“First-timer friendly”**: filter where `first_timer_ratio > threshold`.
* **Cross-post radar**: Luma↔Meetup overlap reveals real activity.

---

# Ops & quality

* **Source health**: per-platform freshness and failure rates.
* **Dedup audit**: surface top ambiguous merges for human review.
* **Label drift**: alert if a scene flips labels too often (thresholding bug).
* **Ethics**: respect private/RSVP-only pages; honor robots/ToS; cache politely.

---

# Day‑1 milestone (2–3 sprints)

1. One city (Columbus) + two sources (Luma, Meetup).
2. Normalization, dedup, basic tags, daily labeler.
3. ClickHouse metrics + a minimal “Scenes” page with filters.
4. Webhooks (if offered) or 15‑min pollers with backoff.

---

# Stretch ideas

* **Cold-start agent**: “find new Ohio groups that are *not* in index yet.”
* **Event health**: predict likely cancellations/no-shows.
* **Community concierge**: weekly digest auto-personalized by interests.
* **Organizer loop**: nudge dormant groups with suggested collab partners/venues.

---

If you want, I can turn this into: (a) a concise ERD, (b) a LangGraph node/edge diagram, and (c) a first-pass scoring SQL for ClickHouse—ready to drop into your repo.
