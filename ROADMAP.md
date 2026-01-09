## 0) Updated Intake (New Inputs + Your Decisions)

### New input items received (assigned IDs)

| ID             | Input                                       | One-line description                                                                                                                                                                                                  |
| -------------- | ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **[FLOW-1]**   | BspokeCal / Calendar Club user flow diagram | Flow from curator discovery → clarifying questions → results → export/sync decision → (payment → calendar SSO → embeddable link) + profile parameter storage.                                                         |
| **[PM-ANS-1]** | Your PM survey selections + constraints     | Consumer-first discovery, free, web-only + read-only calendar integration, Human Week View required, SQLite preference, AI/temporal agent emphasis, social sharing (not social graph), “move fast” compliance stance. |

### Hard constraints (explicit from you)

* **Primary users:** consumers/event-goers; personas also include curator/host/admin. ([PM-ANS-1], [FLOW-1])
* **Core product surface:** **web-only**, with **read-only calendar integration**. ([PM-ANS-1])
* **UI:** **Human Week View is a must-have** (not optional). ([PM-ANS-1], [DOC-11])
* **Scope exclusions (MVP):** no attendance-based social graph; no “global event search” promise; no multi-city expansion. ([PM-ANS-1])
* **Data store preference:** **SQLite** (early). ([PM-ANS-1])
* **AI direction:** LLM-first “deep research agent” + temporal resolution as key wedge. ([PM-ANS-1], [DOC-14])
* **Governance UX:** interactive “shopping-researcher” style sampling + user rating feedback loop during discovery. ([PM-ANS-1])

### Missing “must-answer” items you did not specify (I will proceed with explicit assumptions)

To deliver the phased plan now (as requested), I’m proceeding with the following **assumptions** and flagging them in the decision log:

* **Assumption A1: Time horizon.** Plan is structured as **MVP in ~6 weeks**, V1 in **+6 weeks**, then V2/V3 as follow-ons. (You did not specify 6/12/18 months.)
* **Assumption A2: Team capacity.** Plan assumes a small team: **2 full-stack**, **1 frontend**, **1 product/design** (or fractional), **1 PM**. (Adjustable.)
* **Assumption A3: Initial geography.** MVP targets **one metro**, assumed **Columbus, OH** (consistent with examples in the docs), but the plan works for any single metro. ([DOC-4], [DOC-13], [DOC-19])

---

# Strategy Summary

## What we are building (product-first)

**Calendar Club** is a consumer event-discovery experience that feels like a **deep research assistant**, returning a **high-quality weekly calendar view** of in-person events across **Startups / AI / Community**—and driving repeat “boomerang” usage (discover → click out to RSVP/tickets → return to discover again). ([PM-ANS-1])

## The core loops we are optimizing

1. **Discovery loop (consumer):** Search → clarifying Qs → ranked events → week view → click out → return. ([FLOW-1], [PM-ANS-1])
2. **Feedback loop (quality):** While searching, show a small sample set and ask the user to rate relevance (like a shopping researcher), then re-rank results. ([PM-ANS-1], [DOC-4])
3. **Sharing loop (social but not social graph):** Share an event and/or share a curated week link; invite friends; collaborate lightly with curators. (No attendance graph required.) ([PM-ANS-1])
4. **Calendar context loop (read-only):** Connect user calendar (read-only) to improve relevance and reduce conflicts (e.g., hide conflicts, recommend “free slots”), without writing events back in MVP. ([PM-ANS-1], [DOC-6])

---

<!--# Phased Plan

Below is a phased plan aligned to the flow in **[FLOW-1]** and your product constraints in **[PM-ANS-1]**, while leveraging the proven building blocks in the research docs (schema, dedupe, temporal, hybrid retrieval, etc.). ([DOC-4], [DOC-9], [DOC-14], [DOC-23])

## Phase 0 — Product Definition + Experience Contract

**Goal:** Align team on what “good” looks like for MVP and lock the UX contract for Week View + research agent.

### Outcomes

* A single-page **MVP PRD** (scope, non-goals, metrics, launch checklist).
* A **Week View UX spec** that is implementable and testable (what must ship vs. later polish). ([DOC-11])
* A **Discovery Agent conversation script** (clarifying questions rubric + result explanation style). ([FLOW-1])

### Key deliverables

1. **User journeys (minimum):**

   * “I want something to do this week” (consumer)
   * “I want AI/startup/community events this weekend” (consumer)
   * “I want to share my week plan with friends” (consumer)
2. **Instrumentation plan (must be in MVP):**

   * `search_performed`
   * `results_viewed`
   * `event_clicked_out`
   * `boomerang_return` (return within X hours/days after click-out)
   * `feedback_rated` (the shopping-researcher ratings)
3. **MVP acceptance criteria** (quality bar):

   * Week view loads quickly and is scannable (density cues, “today” prominence). ([DOC-11])
   * Results include time, location, and a canonical link.
   * Duplicate events are rare in the top results (dedupe correctness threshold). ([DOC-9])

### Non-goals (Phase 0)

* No new sources added here; this is definition + design + measurement contract.-->

---

<!--## Phase 1 — MVP: Search + Clarifying Questions + Week View + Share Link

**Goal:** Ship the core **consumer discovery experience** end-to-end, consistent with **[FLOW-1]** up through “Calendar returns results,” plus lightweight sharing.

### What ships (product scope)

#### 1) “Ask clarifying questions” (from your flow)

* A guided chat/search intake that asks 3–6 clarifying questions max:

  * location (defaults to your single metro)
  * date/time window (“this weekend”, “next Thursday”) with temporal parsing
  * category (Startups / AI / Community)
  * constraints (free vs paid, distance radius, time-of-day)
* Output: a structured query profile stored in the user’s profile (even if anonymous session-based initially). ([FLOW-1], [PM-ANS-1])

**Why:** This matches your flow and enables the “deep research” framing without requiring a perfect universal search API.-->

<!--#### 2) “Results calculated” → “Calendar returns results”

* Results rendered into:

  * **Human Week View** (primary)
  * **List view** fallback (secondary)
* Each event card includes:

  * title, start/end, neighborhood/venue, category tag (startup/ai/community)
  * “Why this event?” short rationale (LLM-generated but short)
  * primary outbound link (“RSVP/Tickets”)
* Week view patterns to ship in MVP (minimum viable subset):

  * weekend shading, now marker, all-day strip, density cue, hover peek card. ([DOC-11])

#### 3) “Embeddable link” (lightweight share)

* A share link that renders the same week view with filters locked (e.g., “AI events in Columbus this weekend”).
* Social sharing features (MVP-safe):

  * share event link
  * share week link
  * copy link / share sheet
* **Explicitly not**: attendance graph, friend suggestions, or co-attendance. ([PM-ANS-1])

#### 4) Data foundation (just enough for MVP)

Product-facing requirements (not deep technical):

* A canonical event object and basic dedupe so the week view isn’t spammed by duplicates. ([DOC-9], [DOC-4])
* Provenance captured per event (source + URL) so you can fix/remove issues later. ([DOC-24])

> Note: You prefer **SQLite**. Use it for MVP, but keep the schema clean and migration-friendly. ([PM-ANS-1])

### Success metrics (MVP)

Aligned to what you said:

* **Searches per user per week**
* **Return users / retention** (D1/D7-style, even if informal)
* **Boomerang rate:** % of users who click out to an event and return within a defined window to find more events. ([PM-ANS-1])
-->
<!--### Non-goals (Phase 1)

* No payment processing (despite [FLOW-1] showing it). You stated free/limited token spend. ([PM-ANS-1], [FLOW-1])
* No exporting/syncing events *into* external calendars (read-only integration only). ([PM-ANS-1])
* No multi-city. ([PM-ANS-1])
* No “global search” guarantee. ([PM-ANS-1])

### Risks & mitigations (MVP)

* **Risk:** “Breadth” expectation vs reality of platform APIs.
  **Mitigation:** Define breadth as “coverage of top events in one metro across our three signals,” not “everything.” Use curation + seed sources. ([PM-ANS-1], [DOC-17])
* **Risk:** Quality issues (duplicates, wrong times).
  **Mitigation:** deterministic dedupe and stable normalization rules first; add a “report issue” link on event cards. ([DOC-9], [DOC-5])
-->
---

<!--## Phase 2 — V1: Deep Research Agent + Interactive Rating Loop + More Coverage in the Same Metro

**Goal:** Make the experience feel materially smarter and more complete without changing the core wedge.

### What ships (product scope)

#### 1) “Shopping-researcher” style feedback inside discovery

You explicitly want: “Here are a few examples—rate them—then we incorporate that while continuing research.” ([PM-ANS-1])

Ship:

* A **lightweight “taste calibration” step** after the first results:

  * show 5–10 candidate events
  * user taps: “Yes / No / Maybe”
  * optionally: “Too far / Too expensive / Wrong vibe”
* The system immediately refreshes results and explains what changed (“I prioritized hands-on meetups and de-emphasized conferences.”)

This is the simplest path to personalization **without** requiring social graph or long-term history.

#### 2) Temporal Agentic-RAG upgrades

Because temporal resolution is your explicit wedge: ([PM-ANS-1], [DOC-14])

* Handle fuzzy queries better: “this weekend”, “first Friday”, “tomorrow night”
* Explain time resolution (“Interpreted ‘this weekend’ as Fri 4pm–Sun 11:59pm local.”)

#### 3) Coverage expansion (still one metro)

You said “many connectors early,” but also “no global search promise.” ([PM-ANS-1])
So V1 should expand **depth within your metro**, not geography:

* Add more **seed sources** (venues/universities/community calendars) and/or additional connectors as feasible.
* Add a “Suggest a source” / “Submit event URL” intake (fast supply growth without overengineering). (Concept aligns with submission mechanics mentioned in prior research: “paste URL” pattern. ([DOC-13]))

#### 4) “Parameters stored to profile only” (strengthen profiles)

* Persist:

  * preferred categories (startup/ai/community)
  * time-of-day preferences
  * max distance
  * free/paid preference
* Add “Reset my tastes” and transparency (“why you’re seeing this”).

### Success metrics (V1)

* Increase **boomerang rate**
* Increase **repeat searches per returning user**
* Reduce “bad result” signals (bounces, quick back from outbound links, thumbs-down frequency)

### Non-goals (Phase 2)

* Still no writing events into calendars.
* Still no social graph (co-attendance).

---
-->
<!--## Phase 3 — V2: Calendar Connection (SSO) + Read-Only Context + Optional Export Later

**Goal:** Match the **“Connect calendar SSO”** step in **[FLOW-1]** in a way that is consistent with your “read-only calendar integration” requirement. ([PM-ANS-1], [FLOW-1])

### What ships (product scope)

#### 1) Connect calendar SSO (read-only)

* User connects Google/Microsoft calendar **for read-only context**. ([PM-ANS-1])
* Product benefits:

  * show “conflict” badges on suggested events
  * optionally filter out conflicts
  * suggest “best slots” based on availability

This leverages known patterns for calendar sync reliability (renewals/deltas), but product-level behavior is what matters. ([DOC-6])

#### 2) Export/sync (defer or optional)

Your note: “We are reading through iCal but not submitting. That’s down the road V2.” ([PM-ANS-1])
So treat export as:

* **Option A (safer V2):** “Download .ics for a single event” (user-initiated, not full sync)
* **Option B (later):** “Subscribe to a Calendar Club feed” (webcal/ICS)
* **Option C (later still):** push events into Google/Outlook calendars

If you truly do not want any ICS export yet, keep V2 as “calendar context only” and schedule export for V3.

#### 3) “Embeddable link” upgrades

* Embeddable week view widget for partners (still free), or “shareable mini-calendar” for communities.

### Success metrics (V2)

* Increase weekly active usage via conflict-aware recommendations
* Increase boomerang rate (calendar context reduces decision friction)

### Non-goals (Phase 3)

* Payments still optional; you’re prioritizing engagement. ([PM-ANS-1])

---
-->
## Phase 4 — V3: Monetization + Multi-City + Higher-Risk Social Features

**Goal:** Only after you have repeat usage and a clear value signal.

### Potential directions (choose based on traction)

1. **Monetization (lightweight):**

   * not necessarily payment processing first; could be:

     * sponsored placements (clearly labeled)
     * paid “pro discovery” features
2. **Multi-city expansion:**

   * replicate the metro config model (same product, new city). ([DOC-12])
3. **Higher-risk social:**

   * Only if you can solve privacy + data sourcing responsibly.
   * You explicitly excluded attendance graph in MVP; treat this as later-stage. ([PM-ANS-1], [DOC-15])

---

# Milestone Timeline (Relative)

Assuming A1/A2 (small team; 6-week MVP):

* **Week 1:** Phase 0 complete (PRD + UX contract + metrics plan)
* **Weeks 2–6:** Phase 1 MVP build and launch
* **Weeks 7–12:** Phase 2 V1 (feedback loop, temporal upgrades, coverage depth)
* **Weeks 13–18:** Phase 3 V2 (calendar SSO read-only context, share/embed improvements)
* **Post-18:** Phase 4 V3 options based on traction

---

# MVP PRD Skeleton (Team Hand-off)

## 1. Problem

Consumers want to discover in-person events in {metro} across Startups/AI/Community, but discovery is noisy and calendars don’t show “what’s worth doing.”

## 2. Target users

* Primary: event-goers
* Secondary: curators (power users) who create shareable weeks/filters ([FLOW-1], [PM-ANS-1])

## 3. Value proposition

Deep-research-like discovery + human week view + easy sharing; optimize for boomerangs.

## 4. Core user flow (MVP)

Based on [FLOW-1]:

1. User starts search
2. Product asks clarifying questions
3. Product returns ranked events
4. User views in Human Week View
5. User clicks out to RSVP/tickets
6. User returns and repeats
7. User shares event/week link

## 5. MVP scope

* Search + clarifying Qs + temporal parsing
* Week view (minimum viable subset from [DOC-11])
* Share links
* Basic dedupe/quality
* Instrumentation

## 6. Non-goals (MVP)

* No payment processing
* No calendar write-back / export sync
* No multi-city
* No attendance graph ([PM-ANS-1])

## 7. Metrics

* searches/user/week
* return users
* boomerang rate (definition + measurement window)

## 8. Launch plan

* Private beta → public beta
* Feedback collection: thumbs up/down on results + “report issue”

---

# Decision Log (Including Your Choices + My Assumptions)

## Confirmed by you ([PM-ANS-1])

* Consumer-first discovery, free
* Web-only; read-only calendar integration
* Must-have Human Week View ([DOC-11])
* AI: LLM-first deep research agent + temporal resolution
* MVP exclusions: no social graph, no global search promise, no multi-city
* SQLite preferred early
* Interactive rating loop during discovery

## Assumed to proceed now

* A1: MVP in ~6 weeks, V1 in +6 weeks
* A2: Small team (2–3 engineers + design/PM)
* A3: Single metro assumed Columbus, OH (replaceable)

---

# Immediate Next Step (so your team can start tomorrow)

If you reply with just three confirmations, I will re-issue the same plan with tighter dates and resourcing:

1. **Which metro for MVP?** (If not Columbus)
2. **Team size/roles actually available?**
3. **MVP deadline date or hard event you’re targeting?**

You do not need to answer these to begin execution, but confirming them will let me turn Phase 1 into a sprint-by-sprint delivery plan with clear ownership per epic.
