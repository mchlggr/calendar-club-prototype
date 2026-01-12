Here’s a compact, end‑to‑end plan for an events aggregator (Eventbrite + Meetup + Ticketmaster) with calendar sync, normalization, and dedupe—plus what to measure and the guardrails to stay within each platform’s rules.

# High‑level architecture

* **Ingest adapters**

  * Eventbrite REST (org events, create/list/publish). Auth via API key. Respect org scoping and rate limits. ([Eventbrite][1])
  * Meetup API (current GraphQL; legacy references exist). Expect pagination/limits; some features require Meetup Pro. ([Meetup][2])
  * Ticketmaster Discovery API for search/browse; Partner/Publish APIs are separate and restricted. ([The Ticketmaster Developer Portal][3])
* **Normalizer → “Event” schema** (persist in your DB/search index)
  Minimal fields: `source`, `source_event_id`, `name`, `description`, `category/tags`, `status`, `start/end (UTC)`, `timezone`, `venue {name, address, lat, lon}`, `organizer`, `images[]`, `price/ticketing {currency, min,max,url}`, `url`, `updated_at`, `raw`. Map per‑adapter from provider shapes. (Ticketmaster provides rich venue/attraction/genre data; Eventbrite has event/ticket classes; Meetup provides group context.) ([The Ticketmaster Developer Portal][3])
* **Dedupe service**

  * Candidate matching window: same city ±1–2 days; compare normalized `name` (fuzzy), venue (geohash proximity), and start time; prefer exact URL or known cross‑IDs when available.
  * Use scoring; merge into a canonical event record with `aliases[]` of (source, id, url).
* **Sync/feeds**

  * **iCalendar (ICS)** export per collection (region, organizer, user filters). Follow RFC 5545 (VEVENT with DTSTART/DTEND/UID/DTSTAMP/LOCATION/SUMMARY/DESCRIPTION/URL). ([IETF Datatracker][4])
  * **CalDAV** (optional server) to expose read‑only calendars to Apple/Thunderbird/etc., per RFC 4791 (“calendar-access”). ([IETF Datatracker][5])

# Adapter notes (gotchas)

* **Eventbrite**: org‑scoped operations; create/publish endpoints exist; get an API key in the dev portal. Rate‑limit and backoff. ([Eventbrite][6])
* **Meetup**: GraphQL docs + Playground; historical/event pagination limits differ from older REST (v2/3) so plan incremental syncs. ([Meetup][7])
* **Ticketmaster**: Discovery API is for search/browse; inventory/transactions generally require Partner APIs. Use the API Explorer for testing. ([The Ticketmaster Developer Portal][8])

# Data model (suggested)

* `events` (canonical) and `event_sources` (per‑platform raw)
* `venues` (normalized) and `venue_sources`
* `images` (deduped by URL/hash)
* `organizers` / `groups` (for Meetup & Eventbrite)
  Keep `updated_at` from source to drive incremental pulls.

# Dedupe heuristics (practical set)

1. **Hard keys**: same `url` or same (source, id) → link as alias.
2. **Venue+time**: start time within ±15 min AND geodistance <100m AND name similarity >0.85 → merge.
3. **Text + actor**: name similarity >0.9 AND same organizer/attraction slug (e.g., Ticketmaster attraction) → merge.

# Calendar sync details

* ICS feed per user/filter; set stable `UID` (hash of canonical id), include `URL` back to your site and `LAST-MODIFIED`. ([IETF Datatracker][4])
* Optional CalDAV server to let users subscribe/manage via native clients; you only need “calendar‑access” (not scheduling). ([IETF Datatracker][5])

# Metrics & evaluation

* **Coverage**: % of relevant events per metro captured from each source.
* **Freshness latency**: time from source update → your index.
* **Dedupe accuracy**: precision/recall on a hand‑labeled set.
* **Feed health**: ICS validity rate (lint against RFC 5545). ([IETF Datatracker][4])
* **Engagement**: CTR from lists → detail → external ticket links.

# Compliance & ToS/privacy

* Use official APIs, auth flows, and respect quotas. Avoid scraping where prohibited. Export to users via ICS/CalDAV so they control access in their calendar clients. (Eventbrite API key + org scope; Meetup API access; Ticketmaster Discovery vs. Partner boundaries.) ([Eventbrite][9])

# Quick next steps (build order)

1. Ship **Ticketmaster Discovery** adapter (broad coverage/search). ([The Ticketmaster Developer Portal][3])
2. Add **Eventbrite** (great for local/startup events). ([Eventbrite][1])
3. Add **Meetup GraphQL** (groups/communities). ([Meetup][7])
4. Implement normalizer + dedupe + ICS feed; later layer in CalDAV. ([IETF Datatracker][4])

If you want, I can draft the exact JSON “Event” schema and the field‑mapping tables for each provider, plus a sample ICS output for a single event.

[1]: https://www.eventbrite.com/platform/docs/api-basics?utm_source=chatgpt.com "API Basics — Documentation | Eventbrite Platform"
[2]: https://www.meetup.com/graphql/?utm_source=chatgpt.com "API Doc Introduction"
[3]: https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/?utm_source=chatgpt.com "Discovery API"
[4]: https://datatracker.ietf.org/doc/html/rfc5545?utm_source=chatgpt.com "RFC 5545 - Internet Calendaring and Scheduling Core ..."
[5]: https://datatracker.ietf.org/doc/html/rfc4791?utm_source=chatgpt.com "RFC 4791 - Calendaring Extensions to WebDAV (CalDAV)"
[6]: https://www.eventbrite.com/platform/docs/create-events?utm_source=chatgpt.com "Creating an Event — Documentation | Eventbrite Platform"
[7]: https://www.meetup.com/graphql/guide/?utm_source=chatgpt.com "API Doc Guide"
[8]: https://developer.ticketmaster.com/products-and-docs/apis/getting-started/?utm_source=chatgpt.com "Build Better Experiences – The Ticketmaster ..."
[9]: https://www.eventbrite.com/help/en-us/articles/849962/generate-an-api-key/?utm_source=chatgpt.com "Generate an API key | Eventbrite Help Center"
