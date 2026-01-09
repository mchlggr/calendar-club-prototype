Here’s a concise view of the ecosystem and standards shaping an event sourcing/enrichment plan you’d architect — from API access to normalized calendar outputs — distilled from latest docs and specs.

Event sources rely on **authorized APIs and real‑time notifications** as canonical feeds to reduce scraping and improve quality:

* **Eventbrite’s platform** exposes a **REST API** with **OAuth 2.0 authorization**, letting your app fetch and manage event data and user scopes via standard bearer tokens. You register a client, handle the OAuth app flow, and then call endpoints to list events, attendees, orders, etc. ([Eventbrite][1])
* **Meetup offers a public GraphQL API** with a single endpoint and token‑based access (via OAuth flows) that returns exactly what you request — from group lists to specific event details like title, description, and date/time — with pagination and introspection support. ([Meetup][2])
* **Posh supports webhooks** that deliver notifications on key eCommerce actions (e.g., order/ticket purchases) instead of polling for changes; this real‑time push lets you dedupe by provider + ID and enrich only meaningful updates. ([Posh University][3])
* **Luma exposes APIs** and integration points allowing event workflows and external syncs (e.g., webhooks/Zapier flows to downstream calendars), though direct Luma API docs aren’t highlighted in the usual developer portal — you often connect vendor‑provided triggers for events/attendees and then transform them. ([Luma Help Center][4])

Once you have canonical events collected, the real challenge is **normalization, timezone handling, and recurrence compliance**:

* The **iCalendar standard (RFC 5545)** defines the syntax and semantics for calendar exchange — covering `VCALENDAR`, `VEVENT`, `VTIMEZONE` with `TZID`, and recurrence rules (`RRULE`, `RDATE`, `EXDATE`). It’s the foundation for interoperable feeds and `.ics` output you can emit for clients. ([IETF Datatracker][5])
* **Timezone components (`VTIMEZONE`)** with proper `STANDARD` and `DAYLIGHT` blocks and the correct `TZID` are essential for downstream clients (Google Calendar, Outlook, etc.) to interpret start/end and recurrences correctly — malformed definitions can yield offsets or import failures. ([Drupal.org][6])
* Recurrences via **RRULE** (e.g., weekly, monthly patterns) must follow the spec so clients generate instances correctly across zones and exceptions — libraries for many languages parse and build these properly to avoid bugs. ([iCalendar Documentation][7])

Best practice here is to **consume provider webhooks for incremental change, use provider APIs for full state, normalize timestamps and recurrences into iCalendar RFC‑compliant structures, then emit ICS feeds** that can be subscribed to by calendars or transformed into other client formats — respecting scopes, rate limits, and terms of each source.

If you want the specific links to each API doc page for bookmarking or integration planning, I can list them next.

[1]: https://www.eventbrite.com/platform/api?utm_source=chatgpt.com "API Reference | Eventbrite Platform"
[2]: https://www.meetup.com/graphql/guide/?utm_source=chatgpt.com "API Doc Guide"
[3]: https://university.posh.vip/university/post/a-guide-to-webhooks-at-posh?utm_source=chatgpt.com "A Guide to Webhooks at Posh"
[4]: https://help.luma.com/?utm_source=chatgpt.com "Luma · Help Center"
[5]: https://datatracker.ietf.org/doc/html/rfc5545?utm_source=chatgpt.com "RFC 5545 - Internet Calendaring and Scheduling Core ..."
[6]: https://www.drupal.org/project/addtocal_augment/issues/3252918?utm_source=chatgpt.com "ics import problems due to malformed VTIMEZONE definition"
[7]: https://icalendar.readthedocs.io/en/latest/api.html?utm_source=chatgpt.com "icalendar package — icalendar 7.0.0a4.dev58 documentation"
