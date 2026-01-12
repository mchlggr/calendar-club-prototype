Here’s a clean, practical blueprint for an events aggregator that pulls from Eventbrite + Meetup, normalizes/dedupes, and speaks iCalendar (including recurrence) for export/sync.

---

## 1) Sources & connectors

* **Eventbrite (REST):** OAuth2 auth; fetch events/organizers and expand fields as needed. ([Eventbrite][1])
* **Meetup (GraphQL):** single endpoint; craft queries/mutations and use the Playground for schema discovery. ([Meetup][2])
* **ICS feeds (any venue/org):** ingest `.ics` URLs and parse items. ([IETF Datatracker][3])

**Tip:** Eventbrite’s API explorer is handy for field trials; Meetup’s Playground helps iterate queries quickly. ([Eventbrite][4])

---

## 2) Minimal internal event model (normalized)

* `id_source` (e.g., `eventbrite:123`, `meetup:abc`), `title_norm`, `description`, `start`, `end`, `tz`, `venue_name`, `venue_addr`, `lat`, `lon`, `url`, `image`, `organizer`, `price`, `recurrence` (RRULE/EXDATE if present), `source_kind`.
* Normalize `title_norm` (lowercase, trim, collapse whitespace, strip emojis/punct.)

---

## 3) Dedupe strategy

* **Key:** `(title_norm) + (start within ±75–120 min window) + (venue_name OR geo ~100–300m)`.
* Keep the richest record (more fields) as the “primary,” attach others as `duplicates[]`.

---

## 4) Recurrence & exceptions

* Follow **RFC 5545** (RRULE, RDATE, EXDATE). ([IETF Datatracker][3])
* Use **rrule.js** for expansion (also has human-readable `toText()`), and **ical.js** to parse inbound ICS. For simple export, **ics (npm)** works well. ([GitHub][5])

---

## 5) Export & two‑way sync

* **Export:** generate `.ics` feeds for any query (city, organizer, tag). Include `VEVENT` with `UID`, `DTSTART/DTEND`, `SUMMARY`, `LOCATION`, `URL`, and RRULE/EXDATE when applicable (per RFC 5545). ([IETF Datatracker][3])
* **Two‑way sync (advanced):** implement **CalDAV** (calendar-access) to publish a server-side calendar so users can subscribe/update with native apps; spec is **RFC 4791** (Scheduling: **RFC 6638**). ([IETF Datatracker][6])

---

## 6) Pagination & freshness

* **Eventbrite:** page through results; prefer organizer/venue-scoped queries to reduce noise. (Use the API Explorer to confirm expansions.) ([Eventbrite][4])
* **Meetup:** GraphQL lets you request precisely the fields (and past/upcoming ranges). Start with group → events queries. ([Meetup][7])

---

## 7) Practical library picks

* **Parse/expand recurrence:** `rrule.js` (browser/Node). ([GitHub][5])
* **Parse inbound ICS:** `ical.js`. ([GitHub][8])
* **Generate ICS:** `ics` (Node/browser). ([npm][9])

---

## 8) Gotchas

* **Time zones:** always store `start/end` as UTC + original `tz`; expand recurrences in the event’s local TZ (DST-safe per RFC 5545). ([IETF Datatracker][3])
* **Meetup schema drift:** verify available fields in Playground; don’t assume parity with older REST docs. ([Meetup][10])
* **CalDAV scope:** it’s WebDAV extensions; plan auth, ETags, and sync tokens. ([IETF Datatracker][6])

---

If you want, I can sketch a quick JSON schema for the minimal event model and a sample dedupe function next.

[1]: https://www.eventbrite.com/platform/api?utm_source=chatgpt.com "API Reference | Eventbrite Platform"
[2]: https://www.meetup.com/graphql/?utm_source=chatgpt.com "API Doc Introduction"
[3]: https://datatracker.ietf.org/doc/html/rfc5545?utm_source=chatgpt.com "RFC 5545 - Internet Calendaring and Scheduling Core ..."
[4]: https://www.eventbrite.com/platform/docs/api-explorer?utm_source=chatgpt.com "Exploring the API — Documentation | Eventbrite Platform"
[5]: https://github.com/jkbrzt/rrule?utm_source=chatgpt.com "jkbrzt/rrule: JavaScript library for working with recurrence ..."
[6]: https://datatracker.ietf.org/doc/html/rfc4791?utm_source=chatgpt.com "RFC 4791 - Calendaring Extensions to WebDAV (CalDAV)"
[7]: https://www.meetup.com/graphql/guide/?utm_source=chatgpt.com "API Doc Guide"
[8]: https://github.com/mozilla-comm/ical.js/?utm_source=chatgpt.com "kewisch/ical.js: Javascript parser for ics (rfc5545) and vcard ..."
[9]: https://www.npmjs.com/package/ics?utm_source=chatgpt.com "ics"
[10]: https://www.meetup.com/graphql/playground/?utm_source=chatgpt.com "API Doc Playground"
