Here’s a compact playbook for turning your events data into a “who to meet next” engine using a semantic graph built on top of ClickHouse.

---

# Why a semantic network?

Instead of just listing events, model the ecosystem as connected nodes:

* **People** (attendees, speakers, organizers)
* **Events** (meetups, workshops)
* **Topics** (tags, embeddings)
* **Venues/Orgs** (hosts, sponsors)

Edges capture relationships like *co‑attendance*, *topic affinity*, *organizer→event*, *person→topic*. With that, you can rank introductions, surface relevant events, and recommend small groups.

---

# Minimal data model (ClickHouse)

```sql
-- Nodes
CREATE TABLE persons (
  person_id UUID,
  name String,
  org Nullable(String),
  title Nullable(String),
  PRIMARY KEY person_id
) ENGINE = MergeTree ORDER BY person_id;

CREATE TABLE events (
  event_id UUID,
  name String,
  start_at DateTime,
  venue_id UUID,
  topics Array(String),             -- raw tags
  topic_vec Array(Float32),         -- embedding for topics/desc
  PRIMARY KEY event_id
) ENGINE = MergeTree ORDER BY event_id;

CREATE TABLE venues (
  venue_id UUID,
  name String,
  city String,
  PRIMARY KEY venue_id
) ENGINE = MergeTree ORDER BY venue_id;

-- Edges
CREATE TABLE attendance (
  event_id UUID,
  person_id UUID,
  role Enum8('attendee'=1,'speaker'=2,'host'=3),
  checkin_at DateTime,
  PRIMARY KEY (event_id, person_id)
) ENGINE = ReplacingMergeTree ORDER BY (event_id, person_id);

-- Derived co-attendance edges (person-person)
CREATE TABLE co_attend (
  a UUID, b UUID,                  -- person_id pairs (ordered a<b)
  w UInt32                         -- weight = shared events count (or decay)
) ENGINE = SummingMergeTree ORDER BY (a,b);
```

**Build `co_attend`:**

```sql
INSERT INTO co_attend
SELECT
  least(p1.person_id, p2.person_id) AS a,
  greatest(p1.person_id, p2.person_id) AS b,
  count() AS w
FROM attendance AS p1
INNER JOIN attendance AS p2
  ON p1.event_id = p2.event_id AND p1.person_id < p2.person_id
GROUP BY a, b;
```

---

# “Who to meet next” (core ideas)

**1) Mutual context (graph signal).**
Score by shared neighbors, penalize popular hubs:

```sql
WITH
  {me:UUID} AS me
SELECT
  target AS person_id,
  sum(w / log2(2 + deg)) AS score
FROM
(
  SELECT c2.b AS target, c1.w, deg
  FROM co_attend c1
  INNER JOIN co_attend c2 ON c1.b = c2.a
  INNER JOIN
    (SELECT a AS pid, sum(w) AS deg FROM co_attend GROUP BY a) d
      ON d.pid = c2.b
  WHERE c1.a = me AND c2.b != me
)
GROUP BY person_id
ORDER BY score DESC
LIMIT 20;
```

**2) Topic fit (vector search).**
Find people whose historical event/topic embeddings align with your interests:

```sql
-- Assuming you store per-person topic_vec (mean of attended event vectors)
SELECT person_id, distanceCosine(topic_vec, {my_vec:Array(Float32)}) AS d
FROM person_profiles
ORDER BY d ASC
LIMIT 20;
```

**3) Freshness & locality.**
Boost scores for people attending *upcoming* events you’re eyeing and in your city:

```sql
WITH toDateTime('{now}') AS now
SELECT person_id, final_score
FROM
(
  SELECT p.person_id,
         0.6*topic_score + 0.3*graph_score + 0.1*recency_boost AS final_score
  FROM my_candidate_table
)
ORDER BY final_score DESC
LIMIT 20;
```

---

# How to compute embeddings quickly

* Use a background job to embed event titles+descriptions into `events.topic_vec`.
* Roll up `person_profiles(topic_vec)` by averaging embeddings of events they attended (time-decayed).
* ClickHouse supports vector indexes (`IVF`, `HNSW`) via `VectorIndex`—great for fast KNN on `Array(Float32)`.

---

# Smart group suggestions (micro‑mixers)

Once you have a candidate set, form small groups (3–5) that maximize:

* intra‑group topic similarity,
* minimal prior co‑attendance (encourages new intros),
* venue/time overlap (they’re likely to meet).

Start greedy: pick a seed (highest score), add members that increase average pairwise similarity while keeping co‑attendance low.

---

# Practical touches

* **Cold start:** use declared interests, org, and city as priors until attendance history accrues.
* **Privacy:** allow opt‑out and “do not suggest me to coworkers/competitors”; store only necessary fields.
* **UI:** show *why* (shared event X, common topics Y, attending Z next week) to build trust.
* **Ops:** refresh co‑attendance nightly; recompute candidate lists for active users; vector indexes weekly.

---

# Quick roadmap

1. Instrument ingestion (Luma/Eventbrite/Meetup/Google Calendar → `events`, `attendance`).
2. Add embeddings + vector index.
3. Build `co_attend` + degree table.
4. Ship the combined scorer (graph + topics + freshness).
5. Expose APIs: `/suggest/people`, `/suggest/groups`, `/suggest/events`.
6. Add feedback loops (“not relevant”, “already connected”) to retrain weights.

If you want, I can tailor the SQL and data flows to your “Calendar Club” stack (Nx monorepo, Next.js, ClickHouse) and sketch the API contracts next.
