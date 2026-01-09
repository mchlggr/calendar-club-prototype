Here’s a quick, practical guide to being a “good citizen” when your apps crawl APIs or websites—so you get reliable data without getting blocked.

---

### 1) Honor `robots.txt` (Robots Exclusion Protocol)

* Always fetch and follow a site’s `robots.txt` before crawling. It’s now an IETF standard (RFC 9309), clarifying syntax, error handling, and caching. It’s advisory (not auth), but widely respected by legitimate crawlers. ([RFC Editor][1])

**Tips**

* Cache `robots.txt` per RFC guidance; re‑check periodically rather than on every request. ([RFC Editor][1])
* Don’t treat `Disallow` as security—protect sensitive paths server‑side. ([Wikipedia][2])

---

### 2) Handle 429s correctly (rate limits)

* If you hit **HTTP 429 Too Many Requests**, slow down. RFC 6585 defines 429 and allows servers to include **`Retry-After`** telling you how long to wait. Honor it. ([IETF Datatracker][3])
* MDN: 429 means you’ve exceeded a limit; back off based on `Retry-After`. ([MDN Web Docs][4])

**Tips**

* Parse `Retry-After` (seconds or HTTP date). Use **exponential backoff with jitter**, capped by any `Retry-After`. ([MDN Web Docs][5])
* Some APIs expose **RateLimit** headers—use them to shape request pace. ([IETF][6])

---

### 3) Use conditional requests to cut bandwidth & load

* Send **ETag/If-None-Match** or **If-Modified-Since** so the server can return **304 Not Modified** when nothing changed. That saves bytes and quota. ([IETF HTTP Working Group][7])

**Tips**

* Prefer ETags for precise validation; Last‑Modified is simpler and works well for mostly static assets. ([IETF HTTP Working Group][7])
* Build your client to store validators and revalidate on subsequent fetches. ([Ilija Eftimov ‍][8])

---

### 4) Production‑ready crawl etiquette (checklist)

* **Identify your bot** with a descriptive UA and contact URL/email.
* **Stagger & randomize** request timing; avoid bursts.
* **Per‑host concurrency caps** (e.g., 1–2 in flight) + **global QPS**.
* **Respect sitemaps** to discover canonical URLs efficiently.
* **Circuit breakers**: pause a domain on repeated 429/503s; resume after `Retry-After`. ([MDN Web Docs][4])

---

If you want, I can drop in a tiny Node/TS helper that: (a) fetches & caches `robots.txt`, (b) enforces per‑host crawl windows, (c) auto‑parses `Retry-After`, and (d) adds ETag/Last‑Modified revalidation.

[1]: https://www.rfc-editor.org/rfc/rfc9309.html?utm_source=chatgpt.com "RFC 9309: Robots Exclusion Protocol"
[2]: https://en.wikipedia.org/wiki/Robots.txt?utm_source=chatgpt.com "Robots.txt"
[3]: https://datatracker.ietf.org/doc/html/rfc6585?utm_source=chatgpt.com "RFC 6585 - Additional HTTP Status Codes"
[4]: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/429?utm_source=chatgpt.com "429 Too Many Requests - HTTP - MDN Web Docs"
[5]: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Retry-After?utm_source=chatgpt.com "Retry-After header - HTTP - MDN Web Docs"
[6]: https://www.ietf.org/archive/id/draft-polli-ratelimit-headers-02.html?utm_source=chatgpt.com "RateLimit Header Fields for HTTP"
[7]: https://httpwg.org/specs/rfc7232.html?utm_source=chatgpt.com "RFC 7232 - Conditional Requests"
[8]: https://ieftimov.com/posts/conditional-http-get-fastest-requests-need-no-response-body/?utm_source=chatgpt.com "Conditional HTTP GET: The fastest requests need no ..."
