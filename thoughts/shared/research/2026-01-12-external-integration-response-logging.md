---
date: 2026-01-12T08:59:49Z
researcher: Claude
git_commit: 4d2ab20e61dd3f35bdeec7c039890e98fe7e309e
branch: main
repository: calendarclub/rig
topic: "External System Integration Response Logging Audit"
tags: [research, logging, external-apis, error-handling, observability]
status: complete
last_updated: 2026-01-12
last_updated_by: Claude
---

# Research: External System Integration Response Logging Audit

**Date**: 2026-01-12T08:59:49Z
**Researcher**: Claude
**Git Commit**: 4d2ab20e61dd3f35bdeec7c039890e98fe7e309e
**Branch**: main
**Repository**: calendarclub/rig

## Research Question

Audit the codebase for locations where external system integrations fail but the server response is not logged. The goal is to identify all locations where response logging should be added for debugging integration failures.

## Summary

The codebase integrates with multiple external services (Eventbrite, Meetup, Exa, Firecrawl, Google Calendar, Microsoft Graph). Current error handling logs exception messages and context, but **does not log the actual response body from external servers** when errors occur. This makes debugging integration failures difficult because the response often contains critical information about what went wrong.

## Current Logging Infrastructure

### Configuration
**File**: `api/config.py:67-81`

```python
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
```

### Logging Patterns Used
- Emoji-prefixed structured logging for visual categorization
- Timing information tracked with `time.perf_counter()`
- Context logged as `| field=value` pipe-separated format
- Error messages truncated to 100 characters in some locations

## Detailed Findings: Locations Missing Response Logging

### 1. Eventbrite API (`api/services/eventbrite.py`)

**Location**: Lines 254-262

```python
except httpx.HTTPError as e:
    elapsed = time.perf_counter() - start_time if 'start_time' in locals() else 0
    logger.debug(
        "❌ [Eventbrite] HTTP error | error=%s duration=%.2fs",
        str(e)[:100],
        elapsed,
    )
    logger.warning("Eventbrite destination API error: %s", e)
    return []
```

**Issue**: Logs exception message only. If the HTTP request succeeded but returned error JSON (e.g., `{"error": "rate_limited"}`), the response body is not captured.

**Response available via**: `e.response.text` if `e.response` exists

---

**Location**: Lines 341-343

```python
except (KeyError, ValueError, TypeError) as e:
    logger.warning("Error parsing destination event: %s", e)
    return None
```

**Issue**: Logs parse error but not the data that failed to parse. The raw `data` dict that caused the failure is available but not logged.

---

### 2. Meetup GraphQL API (`api/services/meetup.py`)

**Location**: Lines 210-212

```python
except Exception as e:
    logger.error("Meetup API error: %s", e, exc_info=True)
    return []
```

**Issue**: Logs exception with traceback but not the GraphQL response. GraphQL errors return 200 OK with error details in the response body.

**Response available via**: The `result` variable contains the response before exception handling

---

**Location**: Lines 281-283

```python
except (KeyError, ValueError, TypeError) as e:
    logger.warning("Error parsing Meetup event: %s", e)
    return None
```

**Issue**: Logs parse error but not the `data` dict that failed to parse.

---

### 3. Exa Search API (`api/services/exa_client.py`)

**Location**: Lines 325-327

```python
except Exception as e:
    logger.warning("Exa search error: %s", e)
    return []
```

**Issue**: SDK exception message only. The underlying HTTP response is wrapped by the SDK.

---

**Location**: Lines 373-375

```python
except Exception as e:
    logger.warning("Exa findSimilar error: %s", e)
    return []
```

**Issue**: Same pattern - no response details.

---

**Location**: Lines 420-423

```python
except httpx.HTTPError as e:
    logger.debug("❌ [Exa] Webset creation failed | error=%s", str(e)[:100])
    logger.warning("Exa create webset error: %s", e)
    return None
```

**Issue**: HTTP error logged but response body not captured.

---

**Location**: Lines 465-468

```python
except httpx.HTTPError as e:
    logger.debug("❌ [Exa] Webset poll failed | id=%s error=%s", webset_id, str(e)[:100])
    logger.warning("Exa get webset error: %s", e)
    return None
```

**Issue**: Same pattern.

---

**Location**: Lines 493-495

```python
except (KeyError, ValueError) as e:
    logger.warning("Error parsing Exa webset result: %s", e)
    return None
```

**Issue**: Parse error without the data that failed.

---

### 4. Exa Research API (`api/services/exa_research.py`)

**Location**: Lines 147-149

```python
except Exception as e:
    logger.warning("Exa research task creation error: %s", e)
    return None
```

**Issue**: SDK exception only, no response details.

---

**Location**: Lines 228-230

```python
except Exception as e:
    logger.warning("Exa research task status error: %s", e)
    return None
```

**Issue**: Same pattern. The `result` object from the SDK call is not logged on failure.

---

### 5. Firecrawl API (`api/services/firecrawl.py`)

**Location**: Lines 180-182

```python
except Exception as e:
    logger.error("Firecrawl scrape error for %s: %s", url, e)
    raise
```

**Issue**: Exception re-raised but response not logged. The `result` from `client.scrape()` is not captured on failure.

---

**Location**: Lines 216-218

```python
except Exception as e:
    logger.error("Firecrawl crawl error for %s: %s", url, e)
    raise
```

**Issue**: Same pattern.

---

**Location**: Lines 355-357

```python
except Exception as e:
    logger.error("Failed to extract %s event from %s: %s", self.SOURCE_NAME, url, e)
    return None
```

**Issue**: The `data` dict from scraping is not logged when extraction fails.

---

**Location**: Lines 401-403

```python
except Exception as e:
    logger.error("Failed to discover %s events: %s", self.SOURCE_NAME, e)
    return []
```

**Issue**: Discovery failure without response details.

---

### 6. Search Agent Aggregation (`api/agents/search.py`)

**Location**: Lines 540-546

```python
if isinstance(result, BaseException):
    logger.debug(
        "❌ [Search] Source failed | source=%s error=%s",
        source_name,
        str(result)[:100],
    )
    logger.warning("%s fetch failed: %s", source_name, result)
```

**Issue**: When a source fails, only the exception is logged. Any partial response or error details from the source are lost.

---

**Location**: Lines 470-471

```python
except Exception as e:
    logger.warning("Error converting result from %s: %s", source_name, e)
```

**Issue**: Conversion failure without logging the `result` object that failed to convert.

---

## Code References Summary

| File | Line(s) | Error Type | Response Logged? |
|------|---------|------------|------------------|
| `api/services/eventbrite.py` | 254-262 | HTTP Error | No |
| `api/services/eventbrite.py` | 341-343 | Parse Error | No |
| `api/services/meetup.py` | 210-212 | API Error | No |
| `api/services/meetup.py` | 281-283 | Parse Error | No |
| `api/services/exa_client.py` | 325-327 | SDK Error | No |
| `api/services/exa_client.py` | 373-375 | SDK Error | No |
| `api/services/exa_client.py` | 420-423 | HTTP Error | No |
| `api/services/exa_client.py` | 465-468 | HTTP Error | No |
| `api/services/exa_client.py` | 493-495 | Parse Error | No |
| `api/services/exa_research.py` | 147-149 | SDK Error | No |
| `api/services/exa_research.py` | 228-230 | SDK Error | No |
| `api/services/firecrawl.py` | 180-182 | SDK Error | No |
| `api/services/firecrawl.py` | 216-218 | SDK Error | No |
| `api/services/firecrawl.py` | 355-357 | Extraction Error | No |
| `api/services/firecrawl.py` | 401-403 | Discovery Error | No |
| `api/agents/search.py` | 540-546 | Source Failure | No |
| `api/agents/search.py` | 470-471 | Conversion Error | No |

## Architecture Documentation

### Current Error Handling Patterns

1. **HTTP Client Errors (`httpx.HTTPError`)**: Exception message logged, response body not captured
2. **SDK Errors (Exa, Firecrawl)**: Wrapped exceptions only expose message, underlying response hidden
3. **Parse Errors (`KeyError`, `ValueError`, `TypeError`)**: Error message logged, failed data not logged
4. **Generic Exceptions**: Catch-all with message only

### Response Access Patterns

For `httpx.HTTPError`:
```python
if hasattr(e, 'response') and e.response is not None:
    response_text = e.response.text
    status_code = e.response.status_code
```

For parse errors, the data is available in scope:
```python
except (KeyError, ValueError) as e:
    logger.warning("Parse error: %s | data=%s", e, data)  # data available
```

## Related Research

- `2026-01-11-emoji-observability-logging-research.md` - Logging infrastructure design
- `2026-01-11-event-source-api-failures.md` - Event source failure patterns

## Open Questions

1. Should response bodies be logged at WARNING level or DEBUG level?
2. Should response body truncation be applied (e.g., first 500 chars)?
3. Should sensitive data be redacted from logged responses?
4. For SDK-wrapped errors (Exa, Firecrawl), is there a way to access underlying HTTP response?
