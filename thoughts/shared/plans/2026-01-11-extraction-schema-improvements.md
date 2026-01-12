# Extraction Schema Improvements Implementation Plan

## Overview

Improve the robustness and consistency of event data extraction across all sources by:
1. Standardizing Firecrawl extraction schemas with better LLM guidance
2. Adding schema support to Exa Research API
3. Adding lightweight LLM extraction for Exa Search results
4. Implementing cross-source validation for all event data

## Current State Analysis

### Firecrawl Extractors (6 platforms)
- **Location**: `api/services/firecrawl.py`
- **Current**: Each extractor has its own `EVENT_SCHEMA` with minimal field descriptions
- **Problem**: Inconsistent field names, no year requirements, no null guidance
- **Example** (Posh, lines 261-275):
  ```python
  "date": {"type": "string", "description": "Event date (e.g., 'Saturday, Jan 15')"}
  ```
  Missing year → `dateparser` must guess → edge case failures

### Exa Research API
- **Location**: `api/services/exa_research.py`
- **Current**: Supports `output_schema` parameter (line 54-61) but NOT used in adapter (line 180)
- **Problem**: Returns unstructured research results instead of event-structured data

### Exa Search API
- **Location**: `api/services/exa_client.py`
- **Current**: Returns `ExaSearchResult` with `text`, `highlights`, `published_date`
- **Problem**: `published_date` is page publish date, NOT event date. Event details buried in text.

### EventResult Model
- **Location**: `api/models/events.py:8-20`
- **Current**: All sources converge to this model
- **Problem**: No validation that date is in future, has year, etc.

## Desired End State

1. **Firecrawl**: All 6 extractors use a unified `BASE_EVENT_SCHEMA` with:
   - Explicit year requirements in date fields
   - Nullable types with null guidance
   - Negative examples (what NOT to return)
   - Consistent field naming

2. **Exa Research**: Returns structured event data matching the same schema

3. **Exa Search**: Lightweight LLM extracts event details from text/highlights

4. **Validation**: All `EventResult` objects validated before being returned to users

### Verification
- All existing tests pass
- Live scraping tests show improved date extraction
- No events with missing/ambiguous years in production output

## What We're NOT Doing

- Changing the Eventbrite or Meetup GraphQL integrations (they return structured data already)
- Modifying the agent/orchestrator prompts (separate concern)
- Adding new event sources
- Changing the `EventResult` model structure

## Implementation Approach

We'll implement in 4 phases, each independently testable:
1. Firecrawl schema standardization (highest impact, lowest risk)
2. Exa Research schema integration (medium impact, low risk)
3. Exa Search LLM extraction (high impact, medium complexity)
4. Cross-source validation (defensive, catches edge cases)

---

## Phase 1: Firecrawl Schema Standardization

### Overview
Create a unified `BASE_EVENT_SCHEMA` with improved descriptions and have all 6 extractors inherit from it.

### Changes Required:

#### 1.1 Add Base Schema Constant

**File**: `api/services/firecrawl.py`
**Location**: After line 38 (after `ScrapedEvent` model)
**Changes**: Add new `BASE_EVENT_SCHEMA` constant

```python
# Unified extraction schema for all Firecrawl extractors.
# Field descriptions guide Firecrawl's LLM for accurate extraction.
BASE_EVENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "Event title - the main headline or name of the event"
        },
        "description": {
            "type": ["string", "null"],
            "description": "Event description or summary. First 1000 characters if very long. Return null if no description found."
        },
        "start_date": {
            "type": "string",
            "description": "Event start date in format 'Month Day, Year' (e.g., 'January 15, 2026'). MUST include the full year - infer from context if not displayed on page. Never return relative dates like 'tomorrow' or 'next week'."
        },
        "start_time": {
            "type": ["string", "null"],
            "description": "Event start time with AM/PM (e.g., '7:00 PM', '10:30 AM'). Include timezone abbreviation if shown on page (e.g., 'EST', 'PT'). Return null if time not specified."
        },
        "end_time": {
            "type": ["string", "null"],
            "description": "Event end time with AM/PM. Same format as start_time. Return null if not specified."
        },
        "venue_name": {
            "type": ["string", "null"],
            "description": "Venue or location name. Return 'Online' for virtual/remote events. Return null if not specified or marked as TBA."
        },
        "venue_address": {
            "type": ["string", "null"],
            "description": "Full street address including city, state/region, and zip/postal code if available. Return null for online events or if address not disclosed."
        },
        "price": {
            "type": "string",
            "description": "Entry/ticket price. Return 'Free' if: event is free, RSVP-only, donation-based, or no price is shown. For paid events return price with currency symbol (e.g., '$25'). For price ranges use '$10-50' format. If multiple ticket tiers, return the lowest price."
        },
        "image_url": {
            "type": ["string", "null"],
            "description": "URL of the main event banner or cover image. Must be a full URL starting with https://. Do NOT return: logos, profile pictures, sponsor images, or advertisement banners. Return null if no event-specific image found."
        },
        "organizer": {
            "type": ["string", "null"],
            "description": "Name of the event organizer, host, or hosting organization. Return null if not specified."
        },
    },
    "required": ["title", "start_date"],
}
```

#### 1.2 Update BaseExtractor to Use Base Schema

**File**: `api/services/firecrawl.py`
**Location**: Lines 148-151
**Changes**: Reference new base schema

```python
SOURCE_NAME: str = "unknown"
BASE_URL: str = ""
EVENT_SCHEMA: dict[str, Any] = BASE_EVENT_SCHEMA  # Changed from empty dict
DEFAULT_CATEGORY: str = "community"
```

#### 1.3 Add Unified Date Parsing Method to BaseExtractor

**File**: `api/services/firecrawl.py`
**Location**: After line 172 (after `_parse_extracted_data` abstract method)
**Changes**: Add shared date parsing that handles the new schema format

```python
def _parse_datetime_from_schema(
    self,
    start_date: str | None,
    start_time: str | None,
    end_time: str | None,
) -> tuple[datetime | None, datetime | None]:
    """
    Parse date/time strings from BASE_EVENT_SCHEMA into datetime objects.

    This method handles the standardized format where:
    - start_date: 'Month Day, Year' (e.g., 'January 15, 2026')
    - start_time: 'H:MM AM/PM [TZ]' (e.g., '7:00 PM EST')
    - end_time: Same format as start_time
    """
    if not start_date:
        return None, None

    try:
        import dateparser

        # Combine date and start time
        combined = start_date
        if start_time:
            # Remove timezone abbreviation for parsing (dateparser handles it)
            combined = f"{start_date} {start_time}"

        start_dt = dateparser.parse(
            combined,
            settings={"PREFER_DATES_FROM": "future"},
        )

        # Parse end time if provided
        end_dt = None
        if end_time and start_dt:
            end_combined = f"{start_date} {end_time}"
            end_dt = dateparser.parse(
                end_combined,
                settings={"PREFER_DATES_FROM": "future"},
            )
            # Handle overnight events (end time before start time)
            if end_dt and start_dt and end_dt < start_dt:
                from datetime import timedelta
                end_dt = end_dt + timedelta(days=1)

        return start_dt, end_dt

    except Exception as e:
        logger.warning(
            "Failed to parse datetime: date=%s start=%s end=%s error=%s",
            start_date, start_time, end_time, e
        )
        return None, None

def _parse_price_from_schema(self, price_str: str | None) -> tuple[bool, int | None]:
    """
    Parse price string from BASE_EVENT_SCHEMA into (is_free, price_cents).

    Handles: 'Free', '$25', '$10-50', '$15+'
    """
    if not price_str:
        return True, None

    price_lower = price_str.lower().strip()
    if price_lower in ("free", "no cover", "complimentary", "donation", "rsvp", ""):
        return True, None

    # Extract first number from price string
    match = re.search(r"\$?(\d+(?:\.\d{2})?)", price_str)
    if match:
        price = float(match.group(1))
        return False, int(price * 100)  # Convert to cents

    return True, None
```

#### 1.4 Update PoshExtractor

**File**: `api/services/firecrawl.py`
**Location**: Lines 249-391 (PoshExtractor class)
**Changes**: Remove custom schema, use base schema, simplify parsing

```python
class PoshExtractor(BaseExtractor):
    """
    Extractor for Posh (posh.vip) events.

    Posh is a social events platform popular for nightlife,
    parties, and social gatherings.
    """

    SOURCE_NAME = "posh"
    BASE_URL = "https://posh.vip"
    DEFAULT_CATEGORY = "nightlife"
    # Uses BASE_EVENT_SCHEMA from parent class

    def _extract_event_id(self, url: str) -> str:
        """Extract event ID from Posh URL."""
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        if path.startswith("e/"):
            return path[2:]
        return path or url

    def _parse_extracted_data(
        self,
        url: str,
        extracted: dict[str, Any],
    ) -> ScrapedEvent | None:
        """Parse Posh extracted data into ScrapedEvent."""
        start_dt, end_dt = self._parse_datetime_from_schema(
            extracted.get("start_date"),
            extracted.get("start_time"),
            extracted.get("end_time"),
        )
        is_free, price_amount = self._parse_price_from_schema(extracted.get("price"))

        return ScrapedEvent(
            source=self.SOURCE_NAME,
            event_id=self._extract_event_id(url),
            title=extracted["title"],
            description=extracted.get("description") or "",
            start_time=start_dt,
            end_time=end_dt,
            venue_name=extracted.get("venue_name"),
            venue_address=extracted.get("venue_address"),
            category=self.DEFAULT_CATEGORY,
            is_free=is_free,
            price_amount=price_amount,
            url=url,
            logo_url=extracted.get("image_url"),
            raw_data=extracted,
        )
```

#### 1.5 Update Remaining Extractors (Luma, Partiful, Meetup, Facebook, River)

**File**: `api/services/firecrawl.py`
**Changes**: For each extractor, remove custom `EVENT_SCHEMA` and update `_parse_extracted_data` to use the new field names (`start_date`, `start_time`, `end_time`) and call `_parse_datetime_from_schema`.

Pattern for each:
1. Remove `EVENT_SCHEMA = {...}` class variable (will inherit from base)
2. Update `_parse_extracted_data` to use new field names
3. Call `self._parse_datetime_from_schema()` and `self._parse_price_from_schema()`

### Success Criteria:

#### Automated Verification:
- [x] All tests pass: `pytest api/services/tests/test_live_sources.py -v`
- [x] Type checking passes: `mypy api/services/firecrawl.py`
- [x] No linting errors: `ruff check api/services/firecrawl.py`

#### Manual Verification:
- [ ] Run live scraping against each platform and verify dates include years
- [ ] Check that "Free" events are correctly identified
- [ ] Verify image URLs are event banners, not logos

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation that live scraping shows improved date extraction before proceeding to the next phase.

---

## Phase 2: Exa Research Schema Integration

### Overview
Wire up the existing `output_schema` parameter in Exa Research to return structured event data.

### Changes Required:

#### 2.1 Add Event Schema for Research

**File**: `api/services/exa_research.py`
**Location**: After line 28 (after `ExaResearchResult` model)
**Changes**: Add schema constant matching Firecrawl's base schema

```python
# Schema for structured event extraction via Exa Research
EVENT_RESEARCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "description": "List of events found",
            "items": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Event title"
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Date in 'Month Day, Year' format (e.g., 'January 15, 2026'). MUST include year."
                    },
                    "start_time": {
                        "type": ["string", "null"],
                        "description": "Time with AM/PM (e.g., '7:00 PM')"
                    },
                    "venue_name": {
                        "type": ["string", "null"],
                        "description": "Venue name or 'Online' for virtual events"
                    },
                    "venue_address": {
                        "type": ["string", "null"],
                        "description": "Full address with city, state"
                    },
                    "price": {
                        "type": "string",
                        "description": "'Free' or price like '$25'"
                    },
                    "url": {
                        "type": "string",
                        "description": "Event page URL"
                    },
                    "description": {
                        "type": ["string", "null"],
                        "description": "Brief event description"
                    },
                },
                "required": ["title", "start_date", "url"]
            }
        }
    },
    "required": ["events"]
}
```

#### 2.2 Update Research Adapter to Use Schema

**File**: `api/services/exa_research.py`
**Location**: Lines 156-202 (`research_events_adapter` function)
**Changes**: Pass schema to research task

```python
async def research_events_adapter(profile: Any) -> list[ExaSearchResult]:
    """
    Adapter for registry pattern - uses Exa Research for deep discovery.
    """
    client = get_exa_research_client()

    # Build research query
    query_parts = [
        "Find upcoming events in Columbus, Ohio",
        "For each event, extract: title, date (with year), time, venue, address, price, URL, and description",
    ]

    if hasattr(profile, "time_window") and profile.time_window:
        if profile.time_window.start:
            query_parts.append(f"Events starting from {profile.time_window.start.strftime('%B %d, %Y')}")
        if profile.time_window.end:
            query_parts.append(f"Events before {profile.time_window.end.strftime('%B %d, %Y')}")

    if hasattr(profile, "categories") and profile.categories:
        query_parts.append(f"Focus on: {', '.join(profile.categories)}")

    if hasattr(profile, "keywords") and profile.keywords:
        query_parts.append(f"Related to: {', '.join(profile.keywords)}")

    query = ". ".join(query_parts)

    # Create research task WITH schema
    task_id = await client.create_research_task(
        query,
        output_schema=EVENT_RESEARCH_SCHEMA,  # NEW: Pass schema
    )
    if not task_id:
        return []

    # Poll for results (max 60 seconds)
    max_polls = 12
    poll_interval = 5.0

    for _ in range(max_polls):
        await asyncio.sleep(poll_interval)

        status = await client.get_task_status(task_id)
        if not status:
            continue

        if status.status == "completed":
            # Parse structured results
            return _parse_research_results(status)
        elif status.status == "failed":
            logger.warning("Exa research task %s failed", task_id)
            return []

    logger.warning("Exa research task %s timed out", task_id)
    return []


def _parse_research_results(status: ExaResearchResult) -> list[ExaSearchResult]:
    """Parse structured research results into ExaSearchResult objects."""
    results = []

    # Results should be in the structured format from our schema
    if status.results:
        for r in status.results:
            results.append(r)

    return results
```

### Success Criteria:

#### Automated Verification:
- [x] Tests pass: `pytest api/services/tests/test_live_sources.py::TestExaResearch -v`
- [x] Type checking: `mypy api/services/exa_research.py`

#### Manual Verification:
- [ ] Run Exa Research query and verify results include structured event data with years

**Implementation Note**: Pause for manual verification before proceeding.

---

## Phase 3: Exa Search LLM Extraction

### Overview
Add a lightweight LLM extraction step to parse event details from Exa Search text/highlights. This addresses the core problem that `published_date` is page date, not event date.

### Changes Required:

#### 3.1 Add Extraction Function

**File**: `api/services/exa_client.py`
**Location**: After line 109 (after `_convert_sdk_result` method)
**Changes**: Add LLM extraction helper

```python
async def _extract_event_from_text(
    self,
    title: str,
    text: str | None,
    highlights: list[str] | None,
    url: str,
) -> dict[str, Any] | None:
    """
    Use lightweight LLM to extract event details from search result text.

    Returns dict with: title, start_date, start_time, venue_name, price, description
    """
    if not text and not highlights:
        return None

    # Combine text sources
    content = ""
    if highlights:
        content = " ".join(highlights[:3])
    if text and len(content) < 500:
        content += " " + text[:500]

    if len(content.strip()) < 50:
        return None  # Not enough content to extract from

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI()

        response = await client.chat.completions.create(
            model="gpt-4o-mini",  # Lightweight model for cost/speed
            messages=[
                {
                    "role": "system",
                    "content": """Extract event details from the text. Return JSON with:
- title: Event name
- start_date: Date as 'Month Day, Year' (e.g., 'January 15, 2026'). MUST include year.
- start_time: Time with AM/PM if found, else null
- venue_name: Venue name if found, 'Online' for virtual, else null
- price: 'Free' or '$XX' format, else null
- description: One sentence summary

If this is NOT an event page or details cannot be extracted, return {"is_event": false}."""
                },
                {
                    "role": "user",
                    "content": f"Page title: {title}\n\nContent: {content[:1000]}"
                }
            ],
            response_format={"type": "json_object"},
            max_tokens=200,
            temperature=0,
        )

        result = response.choices[0].message.content
        if result:
            import json
            data = json.loads(result)
            if data.get("is_event") is False:
                return None
            return data

    except Exception as e:
        logger.debug("Event extraction failed for %s: %s", url, e)

    return None
```

#### 3.2 Update Search Method to Use Extraction

**File**: `api/services/exa_client.py`
**Location**: `search` method (around line 146)
**Changes**: Add optional extraction step

```python
async def search(
    self,
    query: str,
    num_results: int = 10,
    include_text: bool = True,
    include_highlights: bool = True,
    start_published_date: str | None = None,
    end_published_date: str | None = None,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    extract_events: bool = False,  # NEW: Enable LLM extraction
) -> list[ExaSearchResult]:
    """
    Search for content.

    Args:
        ...existing args...
        extract_events: If True, run lightweight LLM extraction on results
                       to parse event details from text/highlights.
    """
    # ... existing search logic ...

    results = [self._convert_sdk_result(r) for r in raw_results]

    # NEW: Optional LLM extraction
    if extract_events:
        results = await self._enrich_with_extraction(results)

    return results


async def _enrich_with_extraction(
    self,
    results: list[ExaSearchResult],
) -> list[ExaSearchResult]:
    """Enrich search results with LLM-extracted event details."""
    import asyncio

    async def extract_one(result: ExaSearchResult) -> ExaSearchResult:
        extracted = await self._extract_event_from_text(
            result.title,
            result.text,
            result.highlights,
            result.url,
        )
        if extracted:
            # Update result with extracted data
            # Store in a new field or override fields
            result.extracted_event = extracted
        return result

    # Run extractions in parallel (batch of 5 at a time to avoid rate limits)
    enriched = []
    for i in range(0, len(results), 5):
        batch = results[i:i+5]
        batch_results = await asyncio.gather(*[extract_one(r) for r in batch])
        enriched.extend(batch_results)

    return enriched
```

#### 3.3 Update ExaSearchResult Model

**File**: `api/services/exa_client.py`
**Location**: Lines 22-32
**Changes**: Add extracted_event field

```python
class ExaSearchResult(BaseModel):
    """Parsed search result from Exa API."""

    id: str
    title: str
    url: str
    score: float | None = None
    published_date: datetime | None = None
    author: str | None = None
    text: str | None = None
    highlights: list[str] | None = None
    extracted_event: dict[str, Any] | None = None  # NEW: LLM-extracted event data
```

#### 3.4 Update Search Adapter to Enable Extraction

**File**: `api/services/exa_client.py`
**Location**: `search_events_adapter` function (around line 422)
**Changes**: Enable extraction for event searches

```python
async def search_events_adapter(profile: Any) -> list[ExaSearchResult]:
    """Search adapter for event discovery."""
    client = get_exa_client()

    # ... existing query building ...

    results = await client.search(
        query=query,
        num_results=10,
        include_text=True,
        include_highlights=True,
        extract_events=True,  # NEW: Enable LLM extraction
    )

    return results
```

### Success Criteria:

#### Automated Verification:
- [x] Tests pass: `pytest api/services/tests/test_live_sources.py::TestExaSearch -v`
- [x] Type checking: `mypy api/services/exa_client.py`

#### Manual Verification:
- [ ] Run Exa search and verify `extracted_event` contains parsed event dates with years
- [ ] Verify non-event pages return `extracted_event: null`
- [ ] Check latency impact is acceptable (< 2s additional per batch of 5)

**Implementation Note**: Pause for manual verification. This phase has cost implications (LLM calls).

---

## Phase 4: Cross-Source Validation

### Overview
Add a validation layer that ensures all events have valid dates, titles, and URLs before being returned to users.

### Changes Required:

#### 4.1 Add Validation Function

**File**: `api/agents/search.py`
**Location**: After deduplication function
**Changes**: Add validation helper

```python
def _validate_event(event: EventResult) -> EventResult | None:
    """
    Validate event has required fields and reasonable values.
    Returns None if event should be filtered out.
    """
    # Must have title
    if not event.title or event.title.lower() in ("untitled", "untitled event", ""):
        logger.debug("Filtered event: missing title | id=%s", event.id)
        return None

    # Must have date
    if not event.date:
        logger.debug("Filtered event: missing date | id=%s title=%s", event.id, event.title)
        return None

    # Date must be parseable and include year
    try:
        from datetime import datetime
        parsed = datetime.fromisoformat(event.date.replace("Z", "+00:00"))

        # Date should be in the future (or at least today)
        from datetime import timezone
        now = datetime.now(timezone.utc)
        if parsed < now - timedelta(days=1):  # Allow 1 day buffer
            logger.debug(
                "Filtered event: date in past | id=%s title=%s date=%s",
                event.id, event.title, event.date
            )
            return None

    except ValueError:
        logger.debug(
            "Filtered event: unparseable date | id=%s title=%s date=%s",
            event.id, event.title, event.date
        )
        return None

    # URL should be valid if present
    if event.url:
        if not event.url.startswith(("http://", "https://")):
            event.url = None  # Clear invalid URL rather than filtering

    return event


def _validate_events(events: list[EventResult]) -> list[EventResult]:
    """Validate all events and filter out invalid ones."""
    validated = []
    for event in events:
        valid = _validate_event(event)
        if valid:
            validated.append(valid)

    if len(validated) < len(events):
        logger.info(
            "Validation filtered %d/%d events",
            len(events) - len(validated),
            len(events),
        )

    return validated
```

#### 4.2 Integrate Validation into Search Flow

**File**: `api/agents/search.py`
**Location**: In `search_events` function, after deduplication
**Changes**: Add validation step

```python
# Deduplicate merged results
unique_events = _deduplicate_events(all_events)

# NEW: Validate all events
validated_events = _validate_events(unique_events)

# Sort by date and limit
sorted_events = sorted(validated_events, key=lambda e: e.date if e.date else "")
final_events = sorted_events[:15]
```

### Success Criteria:

#### Automated Verification:
- [x] All tests pass: `pytest api/agents/tests/ -v`
- [x] Type checking: `mypy api/agents/search.py`

#### Manual Verification:
- [ ] Run search and verify no events with past dates appear
- [ ] Verify events with unparseable dates are filtered
- [ ] Check logs show validation filtering metrics

**Implementation Note**: This phase is defensive - it catches any remaining edge cases from all sources.

---

## Testing Strategy

### Unit Tests:
- Test `BASE_EVENT_SCHEMA` field validation
- Test `_parse_datetime_from_schema` with various date formats
- Test `_parse_price_from_schema` with edge cases
- Test `_validate_event` filtering logic

### Integration Tests:
- Live scraping tests for each Firecrawl extractor
- Exa Research structured output test
- Exa Search extraction test
- End-to-end search with all sources

### Manual Testing Steps:
1. Run `python -m api.cli.scrape posh-event <url>` for each extractor
2. Verify dates include years in output
3. Search for "events this weekend" and verify all results have valid future dates
4. Test with edge cases: overnight events, free events, online events

## Performance Considerations

- **Phase 3 (Exa LLM Extraction)**: Adds ~1-2s per batch of 5 results due to GPT-4o-mini calls
  - Mitigation: Run in parallel, batch size tunable
  - Consider: Cache extraction results by URL
- **Phase 4 (Validation)**: Negligible overhead (in-memory filtering)

## Migration Notes

- No database changes required
- No API changes required
- Backward compatible - existing callers unaffected
- Can deploy phases independently

## References

- Research document: `thoughts/shared/research/2026-01-11-firecrawl-extraction-architecture.md`
- Firecrawl docs: https://docs.firecrawl.dev/features/extract
- Exa Research docs: https://docs.exa.ai/reference/research
