Here’s a compact, practical upgrade idea to make your event aggregator feel “near‑human” about dates/times—even when organizers use fuzzy phrases.

# Temporal-RAG for Calendar Club (fast path)

**Goal:** resolve phrases like “next Thursday in Columbus,” “this weekend,” “first Friday,” “2nd Tue @ 7,” and “tomorrow 6p near Short North” into precise UTC datetimes + location scopes before indexing/search—so your agents don’t miss or mis-rank events.

## Why this helps

* Event pages rarely include ISO dates; they say “this Saturday.”
* Cross‑platform imports (Luma, Eventbrite, Meetup, Posh, etc.) are inconsistent.
* Good temporal resolution improves **deduping**, **deconfliction**, **geo‑clustering**, and **week‑view ranking**.

## Minimal architecture

* **Ingestion graph (LangGraph):**

  1. **Scrape/Fetch → Normalize HTML/JSON**
  2. **Temporal Parse Node** (deterministic first): use a rules/CRF/chrono parser to emit candidates with spans (e.g., “next Thursday” → 2026‑01‑01 if today is 2025‑12‑30).
  3. **LLM Disambiguation Node** (guardrailed): confirm/choose candidates using context (venue hours, poster image text, timezone, city mentioned).
  4. **Temporal Embedding Node**: create **date‑vectors** + **place‑vectors** so you can retrieve by temporal/geo intent.
  5. **Index Writer**: store (a) canonical UTC start/end, (b) original phrase, (c) confidence, (d) embeddings, (e) provenance.

* **Serving graph (LangGraph):**

  1. **Query Intent Split**: classify “date‑heavy” vs “topic‑heavy” vs “geo‑heavy.”
  2. **Temporal Retriever**: hybrid search (BM25/keyword on phrases + ANN on date‑vectors + geo filter).
  3. **Reasoner**: resolves “next Thursday” relative to **user’s locale/clock**; backfills if multiple venues.

## Embedding strategy (simple & effective)

* Build a small feature vector for each event time window:

  * **Absolute time** (Unix ts normalized), **dow** (one‑hot), **week‑of‑month**, **month**, **is_weekend**, **is_first_friday**, **local_tz_offset**, **duration buckets**.
  * **Relative hints** from text (“next”, “this”, “first”, “every”, “biweekly”, “doors at”).
  * **Geo**: lat/long (scaled), city hash bucket, metro area id.
* Concatenate with a text embedding of the **temporal phrase + venue blurb**. Store in your vector DB (Azure AI Search vector fields or pgvector/ClickHouse).

## Data model additions

* `events.temporal`:

  * `text_span`: original phrase
  * `start_utc`, `end_utc`, `tz`
  * `resolution_confidence` (0–1)
  * `pattern` (e.g., SINGLE, RANGE, RECURRING_RULE)
  * `rrule` (if recurring)
  * `date_vector` (float[])
  * `geo_vector` (float[])
  * `provenance_id` (source URL + extractor version)

## Disambiguation rules (deterministic → LLM)

* **Anchor date**: use crawl_date if event page has no explicit posted date; else use page’s structured data date or known organizer timezone.
* **“Next” keyword**: “next Thursday” = the *next occurrence strictly after today*; if today is Thu, “next Thursday” = +7d.
* **Weekend buckets**: Friday 16:00 → Sunday 23:59 local.
* **City scoping**: if text includes “Columbus” or a known neighborhood, set `tz` = America/New_York and bias venues within 30km.

## Deduping boost

* Hash on `(start_utc±10m, normalized_title, venue_id)`; if conflict, prefer higher `resolution_confidence` and richer provenance.

## Eval plan (quick)

* Create a 200‑sample **temporal gold set**: screenshots + ground truth datetimes.
* Metrics: **Exact hit**, **±2h tolerance**, **timezone correctness**, **recurring rule accuracy**.
* Add **regression checks** in CI: any parser/LLM prompt change must not drop metrics >1%.

## Rollout checklist

* [ ] Add `Temporal Parse` node (chrono or similar)
* [ ] Add `LLM Disambiguation` node with few‑shot prompts from your gold set
* [ ] Implement `date_vector` builder + ANN field in Azure AI Search
* [ ] Backfill existing events; write migration to store `resolution_confidence`
* [ ] Update ranker: boost exact time matches, decay ambiguous items
* [ ] Add “Why this time?” UI tooltip (shows phrase → resolved date + source)

## Tiny prompt stub (LLM disambiguation)

* System: “You resolve ambiguous event times. Return JSON with start_utc, end_utc, tz, confidence (0–1). Use today={YYYY‑MM‑DD} {TZ}. Prefer explicit dates on page over relative phrases.”
* User: page text + any structured data (schema.org Event), detected phrases, venue hours, crawl timestamp.

If you want, I can draft the LangGraph nodes (TypeScript) and the Azure AI Search index schema you’re using (vector fields + hybrid profile) so you can drop this straight into Calendar Club.
