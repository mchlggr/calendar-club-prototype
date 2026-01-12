Here’s a concise snapshot of where the major event‑platform APIs stand today — what you *can* integrate with, what’s been retired, and where you should plan for manual or partner‑level access.

**Across the board, none of these event platforms offers a broad, public “search all events” API anymore — the tide has shifted toward scoped access, webhooks, or partner/enterprise paths.**

![Image](https://cdn.prod.website-files.com/65b8f370a600366bc7cf9b20/6715801b1132abd91ba67e19_67157dffd532522308b20d00_2024-10-20_22-13-29.png)

![Image](https://community.hubspot.com/t5/image/serverpage/image-id/117177i06A5041D06BAFC58/image-size/large?px=999\&v=v2)

![Image](https://browserstack.wpenginepowered.com/wp-content/uploads/2025/09/Mastering-GraphQL-Introspection-Benefits-Best-Practices-and-Debugging-Tips.png)

![Image](https://tailcall.run/images/graphql/graphql-introspection.png)

### 🛠️ **Luma (Luma API) — Calendar‑Scoped API Keys**

* Luma’s API is designed for calendar and event management integrations, but **you must have a Luma Plus subscription** for the calendar you want to access. ([Luma Help Center][1])
* Each calendar issues its **own API key** through the dashboard (Settings → Developer) which you include in the `x-luma-api-key` header. ([Luma Help Center][1])
* The docs include rate‑limit info and common patterns (events, guests, tickets, webhooks). ([Luma][2])

👉 **This isn’t a global event search API** — it’s scoped to calendars you control.

---

### 📉 **Eventbrite — Public Search API Removed**

* Eventbrite *long ago* retired its public “Event Search” API (the `/v3/events/search/` endpoint) and does **not** currently expose a platform‑wide search endpoint. ([Eventbrite][3])
* All API access uses **OAuth 2.0** tied to organizer accounts. ([Eventbrite][4])
* For syncing events, you must:
  **• Use organizer‑scoped endpoints** (e.g., list events by organization/venue). ([Rollout][5])
  **• Use webhooks** for real‑time updates (event created/updated etc.). ([Eventbrite][6])

👉 No “search all events by query/region” via API anymore — it’s just scoped data for authenticated orgs.

---

### 🔄 **Meetup — New GraphQL Version (2025)**

* Meetup released a **new GraphQL API** in **February 2025** with full schema introspection support. ([Meetup][7])
* You interact via OAuth tokens and can explore the schema with tools like GraphQL Playground. ([Meetup][7])
* Some legacy fields were renamed, so existing clients *may need updates* (e.g., groupSearch, eventsSearch subqueries). ([Meetup][7])

👉 This is a modern, flexible API — but it still requires authenticated access and isn’t a public search endpoint you can hit without proper OAuth scopes.

---

### ⚡ **Posh.vip — Webhooks Only, No Public Events API**

* Posh supports configuring **webhooks** from the organizer dashboard for things like *Order Created* and *Pending Order Created*. ([Posh University][8])
* Integration stories use tools like Zapier to receive real‑time purchase data; there’s **no publicly documented event search API**. ([Posh Support][9])
* There are community‑generated OpenAPI specs via third‑party projects (like scraped Apify definitions), but these are *not official public APIs*. ([Apify][10])

👉 Plan around **dashboard webhooks / exports / Zapier workflows** for Posh data.

---

### 🤷 **River (getriver.io) — No Published API**

* River runs community dinners/meetups and markets itself as infrastructure for branded experiences, but **no developer API docs are published** on the site. ([River][11])
* Without a surfaced API, integrations likely require **inbox‑based ingestion, partner access, or consented scraping**.

👉 You *can’t* build against a documented River event API today.

---

**TL;DR:**

* **Luma** — API exists but is bound to Luma Plus calendars and per‑calendar keys. ([Luma Help Center][1])
* **Eventbrite** — global search API removed; use organizer endpoints + webhooks. ([Eventbrite][3])
* **Meetup** — new GraphQL API that requires client updates. ([Meetup][7])
* **Posh.vip** — supports webhooks but no public search API. ([Posh University][8])
* **River** — no public API documentation; expect partner routes. ([River][11])

If you want **code snippets or workflow recipes** for any of these integrations, just ask.

[1]: https://help.luma.com/p/luma-api?utm_source=chatgpt.com "Luma API"
[2]: https://docs.luma.com/reference/getting-started-with-your-api?utm_source=chatgpt.com "Luma API"
[3]: https://www.eventbrite.com/platform/docs/changelog?utm_source=chatgpt.com "Changelog - Documentation | Eventbrite Platform"
[4]: https://www.eventbrite.com/platform/api?utm_source=chatgpt.com "API Reference | Eventbrite Platform"
[5]: https://rollout.com/integration-guides/eventbrite/api-essentials?utm_source=chatgpt.com "Eventbrite API Essential Guide - Rollout"
[6]: https://www.eventbrite.com/platform/docs/webhooks?utm_source=chatgpt.com "Using Webhooks - Documentation | Eventbrite Platform"
[7]: https://www.meetup.com/graphql/guide/?utm_source=chatgpt.com "API Doc Guide"
[8]: https://university.posh.vip/university/post/a-guide-to-webhooks-at-posh?utm_source=chatgpt.com "A Guide to Webhooks at Posh"
[9]: https://support.posh.vip/en/articles/10723719-how-to-receive-real-time-purchase-data-with-webhooks?utm_source=chatgpt.com "How To Receive Real Time Purchase Data with Webhooks"
[10]: https://apify.com/hypebridge/posh-vip/api/openapi?utm_source=chatgpt.com "Posh VIP OpenAPI definition"
[11]: https://www.getriver.io/?utm_source=chatgpt.com "River powers branded dinner clubs and community meetups."
