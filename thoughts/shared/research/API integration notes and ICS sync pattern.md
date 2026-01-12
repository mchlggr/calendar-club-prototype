You should know **the practical API behaviors, limits, and calendaring format expectations** before building syncing & normalization layers — especially how rate limits differ in docs vs terms, how other services like Meetup and Luma enforce quotas, and what it means to emit a proper **RFC 5545/VCALENDAR** feed for downstream calendar clients.

![Image](https://s3.us-west-1.wasabisys.com/idbwmedia.com/images/api/eventbriteresult.png)

![Image](https://graphql.org/_next/static/media/logo-stacked.fa10db21.svg)

![Image](https://cdn.readme.io/og-image/create?color=%23ffffff\&description=For+each+account+on+%22Build%22+tier+these+limits+are+in+effect%0AModel+Concurrent+generations+Create+API+requests%2Fmin+Ray+%28Video%29+10+20+Photon+%26+Photon+Flash+%28Image%29+40+80%0A%0AThese+limits+exist+to+help+us+maintain+a+high+quality+of+service+for+everyone+and+we+are+working+to+increase+these+further.+If+you%27d%E2%80%A6\&logoUrl=https%3A%2F%2Ffiles.readme.io%2F45785f4-brandmark-blue.svg\&projectTitle=Dream+Machine+API\&title=Rate+Limits\&type=docs\&variant=light)

![Image](https://substackcdn.com/image/fetch/%24s_%212f7J%21%2Cf_auto%2Cq_auto%3Agood%2Cfl_progressive%3Asteep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F266a776e-5031-4b0f-8d4a-8ab40cefa87d_1600x1180.png)

**Eventbrite API rate limits & OAuth**
Eventbrite authenticates via **OAuth 2.0**, and different parts of their public docs contradict each other: the *Rate Limits* page lists a default of **2,000 calls per hour and 48,000/day** for integrated apps, but Eventbrite’s **API Terms of Use (May 30, 2025)** clearly state **1,000 calls per hour on each OAuth token**. In practice the **API Terms limit (1,000/h)** is what you should plan for unless Eventbrite explicitly increases it for your app — exceeding it will return rate errors (HTTP 429/limit reached) in `x-rate-limit` headers. ([Eventbrite][1])

There are also **endpoint‑specific throttles** (e.g., publishing events things like “parent events published per time window”) that aren’t always reflected in the global rate headers — so you may need custom tracking for those. ([Google Groups][2])

**Meetup GraphQL API rate policy**
Meetup’s **GraphQL API** uses a **points‑based quota** rather than simple request counts: you’re allowed **500 points per 60 seconds** across your GraphQL queries. Each query has a “cost,” and hitting the 500‑point budget within a minute triggers rate‑limit rejections (with rate error responses including reset hints). ([Meetup][3])

**Luma API key & limits**
Luma’s API (authenticated with an API key in the `x‑luma‑api‑key` header) enforces **endpoint‑specific quotas**: ~**500 GET requests per 5 minutes per calendar** and ~**100 POSTs per 5 minutes per calendar**, with a **1‑minute block on receiving a 429** response if you exceed them. These are tracked separately for GET vs POST. ([Luma][4])

**iCalendar (RFC 5545) — VCALENDAR output**
The **iCalendar standard (RFC 5545)** defines the textual format for a `.ics` or `.ical` calendar feed — it is what calendar clients (Google, Outlook, Apple, etc.) expect when you emit a VCALENDAR. RFC 5545 lays out the full structure (begin/end tokens, event components like `VEVENT`, `VTODO`, timezone info, properties like `DTSTART`, `UID`, etc.) and the MIME type `text/calendar` that clients parse. This format is essential for proper downstream calendar syncing after you’ve gone through **normalize → dedupe → upsert** in your pipeline. ([IETF Datatracker][5])

**What to build around these facts**

* Enforce **the stricter OAuth token limit** for Eventbrite in your rate‑limit logic.
* Throttle GraphQL calls by **points per minute** for Meetup rather than raw count.
* Treat Luma as **separate GET/POST buckets** per calendar, with 429 block periods.
* Generate **VCALENDAR/ICS** feeds that follow RFC 5545 exactly so calendar clients can subscribe, parse, and display events correctly.

If you want examples of VCALENDAR entries or pragmatic throttling logic templates for these APIs, I can share those next.

[1]: https://www.eventbrite.com/platform/docs/rate-limits?utm_source=chatgpt.com "Rate Limits - Documentation | Eventbrite Platform"
[2]: https://groups.google.com/g/eventbrite-api/c/dwlJjL3Ix7w?utm_source=chatgpt.com "Understanding Publish Endpoint Rate Limits and Monitoring"
[3]: https://www.meetup.com/graphql/guide/?utm_source=chatgpt.com "API Doc Guide"
[4]: https://docs.luma.com/reference/rate-limits?utm_source=chatgpt.com "Rate Limits"
[5]: https://datatracker.ietf.org/doc/html/rfc5545?utm_source=chatgpt.com "RFC 5545 - Internet Calendaring and Scheduling Core ..."
