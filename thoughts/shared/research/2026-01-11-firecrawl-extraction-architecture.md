---
date: 2026-01-12T04:14:40Z
researcher: michaelgeiger
git_commit: cfc3468c66e9d2f6b9a3ee1b6a10b9adc148cfb5
branch: main
repository: calendar-club-prototype
topic: "Firecrawl Extraction Architecture - LLM Usage and Data Flow"
tags: [research, codebase, firecrawl, extraction, llm]
status: complete
last_updated: 2026-01-12
last_updated_by: michaelgeiger
---

# Research: Firecrawl Extraction Architecture - LLM Usage and Data Flow

**Date**: 2026-01-12T04:14:40Z
**Researcher**: michaelgeiger
**Git Commit**: cfc3468c66e9d2f6b9a3ee1b6a10b9adc148cfb5
**Branch**: main
**Repository**: calendar-club-prototype

## Research Question

How do Firecrawl extractors work? Is the system receiving raw HTML and doing regex-based extraction, or is Firecrawl already returning structured output via LLM? Would we need to add LLM calls for more robust date extraction?

## Summary

**Key Finding: An LLM is ALREADY in the loop.** The Firecrawl API uses LLM-powered extraction internally when you provide a JSON schema. The system is NOT doing regex-based date extraction from HTML - instead:

1. **Firecrawl receives the schema** → calls an LLM internally to extract structured data
2. **Returns natural language strings** → e.g., `"date": "Saturday, Jan 15"`, `"time": "10 PM - 2 AM"`
3. **`dateparser` library converts** → transforms natural language dates to `datetime` objects
4. **Regex only used for** → splitting time ranges and extracting price amounts

The architecture already leverages LLM extraction via Firecrawl's built-in capabilities. No additional LLM calls needed for the extraction itself.

## Detailed Findings

### Data Format from Firecrawl

Firecrawl does NOT return raw HTML to the extractors. When called with an `extract_schema`, it returns structured JSON:

**Request** (firecrawl.py:89-93):
```python
if extract_schema:
    format_list.append({
        "type": "json",
        "schema": extract_schema
    })
```

**Response structure**:
```json
{
  "extract": {
    "title": "Tech Mixer at Columbus",
    "description": "Join us for an evening of networking...",
    "date": "Saturday, January 18",
    "time": "7:00 PM - 10:00 PM",
    "venue_name": "The Innovation Hub",
    "venue_address": "123 High Street, Columbus, OH",
    "price": "Free"
  }
}
```

The `extract` key contains structured data matching the provided schema, with values as human-readable strings.

### Extraction Schema Definition

Each platform extractor defines a JSON schema (firecrawl.py:261-275 for Posh):

```python
EVENT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Event title"},
        "description": {"type": "string", "description": "Event description"},
        "date": {"type": "string", "description": "Event date (e.g., 'Saturday, Jan 15')"},
        "time": {"type": "string", "description": "Event time (e.g., '10 PM - 2 AM')"},
        "venue_name": {"type": "string", "description": "Venue name"},
        "venue_address": {"type": "string", "description": "Venue address"},
        "price": {"type": "string", "description": "Ticket price (e.g., 'Free', '$20')"},
        "image_url": {"type": "string", "description": "Event image URL"},
        "organizer": {"type": "string", "description": "Event organizer name"},
    },
    "required": ["title"],
}
```

The `description` fields guide Firecrawl's internal LLM on what format to return.

### Date/Time Parsing (NOT Regex-Based)

Date parsing uses the `dateparser` library (firecrawl.py:285-321):

```python
def _parse_datetime(self, date_str: str | None, time_str: str | None):
    import dateparser

    combined = f"{date_str} {start_time}"  # e.g., "Saturday, January 18 7:00 PM"

    start_dt = dateparser.parse(
        combined,
        settings={"PREFER_DATES_FROM": "future"},
    )
```

**What `dateparser` handles:**
- "Saturday, January 18" → `datetime(2026, 1, 18)`
- "Jan 15, 2026" → `datetime(2026, 1, 15)`
- "Tomorrow at 7pm" → Correct date + time
- "Next Friday" → Resolves to actual date

**Regex is used only for:**
1. **Time range splitting** (firecrawl.py:297): `r"\s*[-–to]\s*"` to split "10 PM - 2 AM" into start/end
2. **Price extraction** (firecrawl.py:332): `r"\$?(\d+(?:\.\d{2})?"` to extract "$20" → 2000 cents

### Complete Data Flow

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Event Page     │     │   Firecrawl API  │     │  Calendar Club  │
│  (HTML/JS)      │────▶│   (LLM inside)   │────▶│   Extractor     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                              │                         │
                              ▼                         ▼
                        JSON Schema            Natural language strings
                        provided by us         returned by Firecrawl
                                                       │
                                                       ▼
                                              ┌─────────────────┐
                                              │  Post-Process   │
                                              │  - dateparser   │
                                              │  - regex price  │
                                              └─────────────────┘
                                                       │
                                                       ▼
                                              ┌─────────────────┐
                                              │  ScrapedEvent   │
                                              │  (typed model)  │
                                              └─────────────────┘
```

### Current Extractors

| Extractor | File Location | Schema Lines |
|-----------|---------------|--------------|
| PoshExtractor | firecrawl.py:249-391 | 261-275 |
| LumaExtractor | firecrawl.py:500-745 | 530-546 |
| PartifulExtractor | firecrawl.py:749-966 | 773-787 |
| MeetupExtractor | firecrawl.py:970-1161 | 981-995 |
| FacebookExtractor | firecrawl.py:1165-1347 | 1177-1190 |
| RiverExtractor | firecrawl.py:1351-1540 | 1363-1376 |

### Firecrawl API Capabilities

From web research, Firecrawl supports:

1. **Schema-based extraction**: Define JSON schema, LLM extracts matching data
2. **Prompt-based extraction**: Natural language prompt without schema
3. **Multiple URL extraction**: `/extract` endpoint can process multiple URLs
4. **Scrape modes**: `/scrape` (single URL), `/crawl` (recursive), `/extract` (multi-URL AI)

**Documentation links:**
- [JSON mode / LLM Extract](https://docs.firecrawl.dev/features/llm-extract)
- [Extract Endpoint](https://docs.firecrawl.dev/features/extract)
- [Scrape API Reference](https://docs.firecrawl.dev/api-reference/endpoint/scrape)

## Code References

- `api/services/firecrawl.py:22-38` - `ScrapedEvent` data model
- `api/services/firecrawl.py:41-101` - `FirecrawlClient` API wrapper
- `api/services/firecrawl.py:140-247` - `BaseExtractor` abstract class
- `api/services/firecrawl.py:261-275` - Posh extraction schema
- `api/services/firecrawl.py:285-321` - Date parsing with `dateparser`
- `api/services/firecrawl.py:323-337` - Price parsing with regex
- `api/services/temporal_parser.py:1-203` - Standalone temporal parser

## Architecture Documentation

### Pattern: LLM-Powered Schema Extraction

The system delegates LLM extraction to Firecrawl rather than running its own LLM:

**Pros:**
- Firecrawl handles prompt engineering for web extraction
- No need to manage OpenAI/Anthropic API keys for extraction
- Extraction happens at scrape time (single API call)
- Firecrawl optimizes for web page structure

**Current approach:**
- Schema defines field names and example formats
- Firecrawl's LLM extracts and formats values
- Local post-processing converts strings to types

### Where Additional LLM Could Help

If robustness issues arise, consider:

1. **Validation LLM call** - After Firecrawl returns, use lightweight model to validate/clean extracted data
2. **Fallback extraction** - If Firecrawl extraction fails, use local LLM on markdown
3. **Enhanced schemas** - Add more specific descriptions to guide Firecrawl's LLM better

However, given `dateparser` handles most date formats well, the current architecture may be sufficient. The question is whether extraction failures are from:
- Firecrawl's LLM missing data (schema needs better descriptions)
- `dateparser` failing on edge cases (might need custom handlers)
- Source websites having unusual formats (platform-specific handling)

## Related Research

- `/thoughts/shared/research/2026-01-11-exa-firecrawl-sdk-migration.md` - SDK migration notes
- `/thoughts/shared/research/2026-01-11-firecrawl-multi-source-expansion.md` - Multi-source expansion

## Open Questions

1. What specific date formats is `dateparser` failing on? (Would help target fixes)
2. Are extraction failures coming from Firecrawl's LLM or post-processing?
3. Could enhanced schema descriptions improve Firecrawl's extraction accuracy?
