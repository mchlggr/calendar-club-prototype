---
date: 2026-01-10T23:54:18-05:00
researcher: Claude Opus 4.5
git_commit: f9d1c74174b450b9e0134bee7b2514d6ebcd60cb
branch: main
repository: calendar-club-prototype
topic: "Exa.ai Websets for In-Person Event Search with Structured Output Extraction"
tags: [research, codebase, exa-ai, websets, event-discovery, structured-data, api-integration]
status: complete
last_updated: 2026-01-10
last_updated_by: Claude Opus 4.5
---

# Research: Exa.ai Websets for In-Person Event Search with Structured Output Extraction

**Date**: 2026-01-10 23:54:18 -05:00
**Researcher**: Claude Opus 4.5
**Git Commit**: f9d1c74174b450b9e0134bee7b2514d6ebcd60cb
**Branch**: main
**Repository**: calendar-club-prototype

## Research Question

How to use Exa.ai websets to search for in-person events and extract structured outputs including enrichments like image URL, summary, price, datetime, location/address, etc.

## Summary

Exa.ai provides three primary approaches for event discovery with structured data extraction:

1. **Websets API** (Async, High-Compute): Best for comprehensive event discovery with verification and custom enrichment columns. Creates curated datasets with AI-verified results.

2. **Research API** (Async, Multi-Agent): Best for complex queries requiring multi-source reasoning. Returns structured JSON matching custom schemas with citations.

3. **Search API with Summaries** (Sync, Fast): Best for real-time queries with schema-based structured extraction from individual results.

**Key Finding**: Exa has no dedicated "Event" entity type, but events can be effectively discovered using natural language queries with verification criteria. Enrichments extract structured fields (date, venue, price, location) from discovered event pages.

**Existing Integration**: No Exa.ai integration currently exists in the Calendar Club codebase.

## Detailed Findings

### 1. Exa.ai API Approaches Comparison

| Feature | Search API | Research API | Websets API |
|---------|------------|--------------|-------------|
| **Latency** | <450ms | Minutes | Minutes to 1 hour |
| **Best For** | Real-time queries | Complex research | Curated datasets |
| **Structured Output** | JSON schema summary | Custom output_schema | Enrichment columns |
| **Verification** | None | Multi-source reasoning | AI criteria validation |
| **Cost** | Per search | Per search + pages read | Credits per verified result |

### 2. Websets API - Primary Recommendation for Event Discovery

Websets deploys search agents to find and verify entities against specific criteria. Ideal for building event databases.

**Creating an Event Webset**:

```python
from exa_py import Exa
from exa_py.websets import CreateWebsetParameters, CreateEnrichmentParameters

exa = Exa(os.getenv('EXA_API_KEY'))

webset = exa.websets.create(
    params=CreateWebsetParameters(
        search={
            "query": "In-person tech conferences in San Francisco in 2026",
            "count": 20
        },
        criteria=[
            {"description": "Event is in-person (not virtual)"},
            {"description": "Event takes place in San Francisco"},
            {"description": "Event is scheduled for 2026"},
            {"description": "Result is an actual event page, not a news article"},
        ],
        enrichments=[
            CreateEnrichmentParameters(
                description="Event name",
                format="text",
            ),
            CreateEnrichmentParameters(
                description="Event start date",
                format="date",
            ),
            CreateEnrichmentParameters(
                description="Event end date",
                format="date",
            ),
            CreateEnrichmentParameters(
                description="Venue name",
                format="text",
            ),
            CreateEnrichmentParameters(
                description="Full address including city and state",
                format="text",
            ),
            CreateEnrichmentParameters(
                description="Ticket price in USD (lowest tier)",
                format="number",
            ),
            CreateEnrichmentParameters(
                description="Event registration/ticket URL",
                format="url",
            ),
            CreateEnrichmentParameters(
                description="Event banner or poster image URL",
                format="url",
            ),
            CreateEnrichmentParameters(
                description="Brief event description/summary",
                format="text",
            ),
        ],
    )
)

# Wait for completion (async operation)
webset = exa.websets.wait_until_idle(webset.id)

# Retrieve results
items = exa.websets.items.list(webset_id=webset.id)
for item in items:
    print(f"Event: {item.enrichments}")
```

**Available Enrichment Formats**:
- `text`: Free-form text (event name, description, venue, address)
- `number`: Numeric values (price, attendance count)
- `date`: Date values (start/end dates)
- `url`: URLs (registration link, image URL)
- `email`: Email addresses (organizer contact)
- `phone`: Phone numbers
- `options`: Multiple choice from predefined labels (event type)

**Verification Criteria Best Practices**:
- Maximum 5 criteria per search
- Use criteria to filter out non-event pages (news articles, blog posts)
- Be specific about location, date range, and event type requirements
- Criteria are evaluated by AI agents against each discovered result

### 3. Research API - Complex Multi-Source Queries

Best when you need to synthesize information from multiple sources about events.

```python
from exa_py import Exa

exa = Exa(os.environ["EXA_API_KEY"])

schema = {
    "type": "object",
    "required": ["events"],
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "date", "venue"],
                "properties": {
                    "name": {"type": "string"},
                    "date": {"type": "string"},
                    "venue": {"type": "string"},
                    "location": {"type": "string"},
                    "price_range": {"type": "string"},
                    "image_url": {"type": "string"},
                    "ticket_url": {"type": "string"},
                    "summary": {"type": "string"}
                }
            }
        }
    },
    "additionalProperties": False
}

research = exa.research.create(
    model="exa-research",  # or "exa-research-pro" for higher quality
    instructions="Find upcoming in-person tech conferences in San Francisco happening in 2026. Include event name, dates, venue, location, ticket prices, and official event image.",
    output_schema=schema
)

# Poll until completion
result = exa.research.poll_until_finished(research.researchId)
# result.data contains structured JSON matching schema
```

### 4. Search API with Structured Summaries - Real-Time Queries

Best for fast, synchronous queries with per-result structured extraction.

```python
from exa_py import Exa

exa = Exa("EXA_API_KEY")

event_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "date": {"type": "string"},
        "venue": {"type": "string"},
        "address": {"type": "string"},
        "price": {"type": "string"},
        "image_url": {"type": "string"},
        "summary": {"type": "string"}
    },
    "required": ["name", "date", "venue"]
}

results = exa.search_and_contents(
    "tech conferences San Francisco 2026",
    summary={
        "query": "Extract event details: name, date, venue, address, price, image URL",
        "schema": event_schema
    },
    num_results=10,
    start_published_date="2025-06-01",  # Filter by date
)

for result in results.results:
    import json
    event_data = json.loads(result.summary)
    print(f"Event: {event_data.get('name')}")
    print(f"Date: {event_data.get('date')}")
```

**Additional Content Extraction Options**:

```python
results = exa.search_and_contents(
    "music festivals 2026",
    text={"max_characters": 2000},  # Full text extraction
    highlights={
        "query": "event date and location",
        "num_sentences": 2,
        "highlights_per_url": 3
    },
    extras={
        "imageLinks": True,  # Extract image URLs from page
        "links": True        # Extract hyperlinks
    },
    livecrawl="preferred"  # Get fresh content
)
```

### 5. Webhooks for Async Processing

Websets supports webhooks for event-driven architectures:

```python
# Create webhook to receive notifications
webhook = exa.websets.webhooks.create(
    url="https://yourapp.com/webhooks/exa",
    events=[
        "webset.item.created",
        "webset.item.enriched",
        "webset.search.completed",
        "webset.idle"
    ]
)

# Events received include:
# - webset.item.created: New event discovered
# - webset.item.enriched: Enrichment data extracted
# - webset.search.completed: Search phase done
# - webset.idle: All processing complete
```

### 6. Monitors for Continuous Event Discovery

Set up recurring searches for new events:

```python
monitor = exa.websets.monitors.create(
    webset_id="ws_abc123",
    cadence={
        "cron": "0 9 * * 1",  # Every Monday at 9am
        "timezone": "America/New_York"
    },
    behavior={
        "type": "search",
        "config": {
            "parameters": {
                "query": "New tech conferences announced in the Bay Area",
                "count": 10,
                "criteria": [
                    {"description": "Event announced in the last week"},
                    {"description": "Event is in the San Francisco Bay Area"}
                ]
            }
        }
    }
)
```

### 7. API Authentication and Endpoints

**Base URLs**:
- Search/Research API: `https://api.exa.ai/`
- Websets API: `https://api.exa.ai/websets/v0/`

**Authentication**:
```bash
# Header-based authentication
x-api-key: YOUR_EXA_API_KEY
```

**Key Websets Endpoints**:
- `POST /v0/websets` - Create webset
- `GET /v0/websets/{id}` - Get webset status
- `GET /v0/websets/{webset}/items` - List discovered items
- `POST /v0/websets/{webset}/enrichments` - Add enrichment column
- `POST /v0/websets/{webset}/searches` - Trigger new search
- `GET /v0/events` - List async events (for polling)

### 8. Pricing Considerations

**Websets Pricing**:
- **Free**: 1,000 credits, up to 25 results per Webset
- **Starter** ($49/mo): 8,000 credits, up to 100 results, 10 enrichment columns
- **Pro** ($449/mo): 100,000 credits, up to 1,000 results, 50 enrichment columns

**Credit Usage**: 10 credits = 1 verified result (all criteria pass)

**Research API**: $5 per 1,000 searches + $5 per 1,000 webpages read

**Search API**: Lower per-query cost, best for high-volume real-time queries

## Code References

No existing Exa.ai integration in Calendar Club codebase. Related research documents:

- `throughts/research/2026-01-10-firecrawl-integration-research.md` - Alternative web crawling approach
- `throughts/research/Key Event API Sources and Their Limits.md` - Event API landscape
- `throughts/research/Schema Patterns for Event Discovery Agents.md` - Event schema design

## Architecture Documentation

### Recommended Integration Pattern

```
┌─────────────────┐
│  Event Request  │
│  (user query)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────────┐
│  Exa Search API │────►│  Quick Results   │
│  (real-time)    │     │  (< 500ms)       │
└─────────────────┘     └──────────────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────────┐
│  Exa Websets    │────►│  Verified Events │
│  (async/deep)   │     │  with Enrichment │
└─────────────────┘     └──────────────────┘
         │
         ▼
┌─────────────────┐
│  Webhook/Poll   │
│  for completion │
└─────────────────┘
```

### Event Schema Mapping

| Calendar Club Field | Exa Enrichment | Format |
|---------------------|----------------|--------|
| `title` | Event name | text |
| `start_datetime` | Event start date | date |
| `end_datetime` | Event end date | date |
| `venue_name` | Venue name | text |
| `address` | Full address | text |
| `price_min` | Lowest ticket price | number |
| `price_max` | Highest ticket price | number |
| `url` | Event page URL | (from item.url) |
| `ticket_url` | Registration link | url |
| `image_url` | Event banner image | url |
| `description` | Event summary | text |

## Limitations and Considerations

1. **No Dedicated Event Entity**: Websets doesn't have a built-in "Event" type like "Company" or "Person". Must use natural language queries and criteria.

2. **Image URL Extraction**: No dedicated image format. Use `url` format with specific description like "Event banner or poster image URL".

3. **Processing Time**: Large Websets searches (1000+ results) can take up to 1 hour. Plan for async processing.

4. **Address Parsing**: Addresses come as free-text. May need additional parsing for structured address components.

5. **Price Variability**: Events often have tiered pricing. Consider extracting both min and max price enrichments.

6. **Date Formats**: Date enrichment returns dates, but timezone handling may require additional processing.

## Sources

- [Exa Websets Overview](https://docs.exa.ai/websets/overview)
- [Exa Websets API Documentation](https://exa.ai/docs/websets/api/overview)
- [Exa Search API Reference](https://exa.ai/docs/reference/search)
- [Exa Research API](https://exa.ai/docs/reference/exa-research)
- [Create Enrichment API](https://exa.ai/docs/websets/api/websets/enrichments/create-an-enrichment)
- [Python SDK Specification](https://exa.ai/docs/sdks/python-sdk-specification)
- [Exa Pricing](https://exa.ai/pricing)
- [GitHub: exa-py SDK](https://github.com/exa-labs/exa-py)
- [Websets vs Google Evaluation](https://exa.ai/blog/websets-evals)

## Open Questions

1. **Rate Limits**: Documentation doesn't clearly specify rate limits for Websets API. May need to test empirically.

2. **Result Quality**: How well does Websets perform specifically for event discovery vs. its documented use cases (companies, people)?

3. **Deduplication**: When using monitors for continuous discovery, how to handle duplicate events across searches?

4. **Freshness**: For time-sensitive event data, what's the optimal combination of Search API (fast) vs Websets (comprehensive)?
